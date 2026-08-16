#!/usr/bin/env python3
"""
Comprehensive test suite for strategy_logic.py.
Tests all static methods with mocked data to ensure correctness.
"""

import unittest
from strategy_logic import DeltaNeutralLogic


class TestDriftedPositionVisibility(unittest.TestCase):
    """A position that drifts past the balance tolerance must stay visible.

    `is_delta_neutral` used to mean "imbalance <= 2%", and it gates both the health
    check and the dashboard's closeable list. So the moment a position drifted past
    2% it disappeared from monitoring AND could no longer be closed from the UI --
    precisely the position that needed attention. It now means "both legs present",
    with `is_balanced` carrying the health question.
    """

    @staticmethod
    def _positions(spot_qty, perp_qty):
        return DeltaNeutralLogic.analyze_position_data(
            perp_positions=[{
                'symbol': 'BTCUSDT', 'positionAmt': str(perp_qty),
                'markPrice': '100.0', 'leverage': '1',
            }],
            spot_balances={'BTC': spot_qty},
            perp_symbol_map={'BTCUSDT': {'baseAsset': 'BTC'}},
        )

    def test_balanced_position_is_both_neutral_and_balanced(self):
        pos = self._positions(10.0, -10.0)['BTCUSDT']
        self.assertTrue(pos['is_delta_neutral'])
        self.assertTrue(pos['is_balanced'])

    def test_drifted_position_stays_visible_but_flagged_unbalanced(self):
        # 8% imbalance: well past the 2% tolerance.
        pos = self._positions(10.8, -10.0)['BTCUSDT']
        self.assertTrue(pos['is_delta_neutral'],
                        "a drifted position must remain listed and closeable")
        self.assertFalse(pos['is_balanced'])
        self.assertGreater(pos['imbalance_pct'], 5.0)

    def test_single_legged_position_is_not_delta_neutral(self):
        pos = self._positions(0.0, -10.0)['BTCUSDT']
        self.assertFalse(pos['is_delta_neutral'],
                         "a naked leg is not a delta-neutral position")

    def test_imbalance_warnings_are_actually_reachable(self):
        """These branches were dead code: filtered to <=2%, then warned at >5%."""
        drifted = self._positions(10.8, -10.0)['BTCUSDT']
        health_issues, critical_issues, count = \
            DeltaNeutralLogic.perform_portfolio_health_analysis([drifted])

        self.assertEqual(count, 1)
        self.assertTrue(health_issues or critical_issues,
                        "an 8% imbalance must produce a health warning")

    def test_critical_imbalance_is_escalated(self):
        badly_drifted = self._positions(12.0, -10.0)['BTCUSDT']  # ~16.7%
        _health, critical, _count = \
            DeltaNeutralLogic.perform_portfolio_health_analysis([badly_drifted])
        self.assertTrue(any('imbalance' in c.lower() for c in critical))


class TestFundingIntervalAnnualization(unittest.TestCase):
    """APR must follow each symbol's actual settlement cadence, not a constant."""

    # 0.0002 per interval clears ANNUALIZED_APR_THRESHOLD (15%) on BOTH cadences:
    # 21.9% at 8h, 43.8% at 4h. A smaller rate would leave the 8h row filtered out
    # by the display threshold and the comparison would silently test nothing.
    RATES = {'A4H': [0.0002] * 20, 'A8H': [0.0002] * 20}
    PRICES = {'A4H': 100.0, 'A8H': 100.0}

    def test_four_hour_symbol_earns_double_an_eight_hour_symbol(self):
        opps = DeltaNeutralLogic.analyze_funding_opportunities(
            self.RATES, self.PRICES, interval_hours={'A4H': 4.0, 'A8H': 8.0})
        by_symbol = {o['symbol']: o['annualized_apr'] for o in opps}

        self.assertIn('A4H', by_symbol)
        self.assertIn('A8H', by_symbol)
        self.assertAlmostEqual(by_symbol['A4H'], by_symbol['A8H'] * 2, places=6)

    def test_symbol_with_unknown_interval_is_skipped_not_guessed(self):
        opps = DeltaNeutralLogic.analyze_funding_opportunities(
            self.RATES, self.PRICES, interval_hours={'A4H': 4.0})
        self.assertEqual([o['symbol'] for o in opps], ['A4H'])

    def test_eight_hour_apr_matches_the_old_constant(self):
        """Sanity check that the refactor did not shift the 8h baseline."""
        opps = DeltaNeutralLogic.analyze_funding_opportunities(
            {'A8H': [0.0002] * 20}, {'A8H': 100.0}, interval_hours={'A8H': 8.0})
        self.assertAlmostEqual(opps[0]['annualized_apr'], 0.0002 * 3 * 365 * 100, places=6)


class TestDeltaNeutralLogic(unittest.TestCase):
    """Test suite for DeltaNeutralLogic static methods."""

    def test_opportunity_analyzer(self):
        """Test analyze_funding_opportunities with various scenarios."""

        # Mock funding histories
        funding_histories = {
            'BTCUSDT': [0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002],  # Good opportunity: low volatility, good yield
            'ETHUSDT': [-0.0001, -0.0002, -0.00015],  # Negative funding (should be filtered)
            'XRPUSDT': [0.001, 0.005, 0.002, 0.008, 0.001],  # High volatility (should be filtered)
            'ADAUSDT': [0.00005, 0.00004, 0.00006],  # Low yield (should be filtered)
            'DOGEUSDT': [0.0001, 0.0002]  # Insufficient data (should be filtered)
        }

        spot_prices = {
            'BTCUSDT': 50000.0,
            'ETHUSDT': 3000.0,
            'XRPUSDT': 0.5,
            'ADAUSDT': 0.4,
            'DOGEUSDT': 0.08
        }

        opportunities = DeltaNeutralLogic.analyze_funding_opportunities(funding_histories, spot_prices)

        # Should only return BTCUSDT as it meets all criteria
        self.assertEqual(len(opportunities), 1)
        btc_opp = opportunities[0]

        self.assertEqual(btc_opp['symbol'], 'BTCUSDT')
        self.assertAlmostEqual(btc_opp['mean_funding'], 0.0002, places=6)
        self.assertGreater(btc_opp['annualized_apr'], 15.0)  # Above threshold
        self.assertLess(btc_opp['coefficient_of_variation'], 0.05)  # Stable enough
        self.assertEqual(btc_opp['data_points_count'], 11)
        self.assertEqual(btc_opp['spot_price'], 50000.0)

    def test_position_sizing(self):
        """Test calculate_position_size for basic delta-neutral sizing."""

        # Test 1x leverage (proper delta-neutral)
        result = DeltaNeutralLogic.calculate_position_size(
            total_usd_capital=1000.0,
            spot_price=50.0,
            leverage=1
        )

        expected_quantity = 20.0  # 1000 / 50

        self.assertAlmostEqual(result['spot_quantity'], expected_quantity, places=6)
        self.assertAlmostEqual(result['perp_quantity'], expected_quantity, places=6)
        self.assertEqual(result['spot_quantity'], result['perp_quantity'])  # Should be equal for delta-neutral
        self.assertTrue(result['is_proper_delta_neutral'])
        self.assertEqual(result['leverage_used'], 1)

        # Test higher leverage (not recommended for delta-neutral)
        result_leveraged = DeltaNeutralLogic.calculate_position_size(
            total_usd_capital=1000.0,
            spot_price=50.0,
            leverage=5
        )

        # Quantities should still be equal for true delta-neutral
        self.assertAlmostEqual(result_leveraged['spot_quantity'], expected_quantity, places=6)
        self.assertAlmostEqual(result_leveraged['perp_quantity'], expected_quantity, places=6)
        self.assertFalse(result_leveraged['is_proper_delta_neutral'])
        self.assertEqual(result_leveraged['leverage_used'], 5)

    def test_health_checks(self):
        """Test check_position_health with different scenarios."""

        # Scenario 1: Healthy position
        mock_healthy_pos = {
            'positionAmt': '-10.0',  # Short 10 units
            'liquidationPrice': '1000.0',
            'markPrice': '2000.0',
            'unrealizedProfit': '100.0'
        }
        spot_balance_qty = 10.0  # Long 10 units spot

        health = DeltaNeutralLogic.check_position_health(mock_healthy_pos, spot_balance_qty)

        self.assertAlmostEqual(health['net_delta'], 0.0, places=6)  # Perfect hedge
        self.assertAlmostEqual(health['imbalance_percentage'], 0.0, places=6)
        self.assertEqual(health['liquidation_risk_level'], 'LOW')
        self.assertAlmostEqual(health['position_value_usd'], 20000.0, places=2)  # 10 * 2000

        # Scenario 2: Imbalanced position
        mock_imbalanced_pos = {
            'positionAmt': '-10.0',
            'liquidationPrice': '1000.0',
            'markPrice': '2000.0',
            'unrealizedProfit': '100.0'
        }
        spot_balance_qty = 11.0  # 1 unit imbalance

        health = DeltaNeutralLogic.check_position_health(mock_imbalanced_pos, spot_balance_qty)

        self.assertAlmostEqual(health['net_delta'], 1.0, places=6)  # 11 + (-10)
        # Denominator is max(|spot|, |perp|) = 11, matching analyze_position_data.
        # It was |perp| = 10 here, so the same position reported 10% on one screen
        # and 9.09% on another.
        self.assertAlmostEqual(health['imbalance_percentage'], 100 / 11, places=6)

        # Scenario 3: High liquidation risk (liquidation price very close to mark price)
        mock_risky_pos = {
            'positionAmt': '-10.0',
            'liquidationPrice': '1960.0',  # Very close to mark price for high risk
            'markPrice': '2000.0',
            'unrealizedProfit': '-50.0'
        }
        spot_balance_qty = 10.0

        health = DeltaNeutralLogic.check_position_health(mock_risky_pos, spot_balance_qty)

        self.assertAlmostEqual(health['liquidation_risk_pct'], -2.0, places=1)  # (1960-2000)/2000 * 100 = -2.0
        self.assertEqual(health['liquidation_risk_level'], 'HIGH')

        # Scenario 4: Test leverage impact on risk calculations
        mock_leveraged_pos = {
            'positionAmt': '-10.0',
            'liquidationPrice': '1900.0',
            'markPrice': '2000.0',
            'unrealizedProfit': '50.0'
        }

        # With 1x leverage (proper delta-neutral)
        health_1x = DeltaNeutralLogic.check_position_health(mock_leveraged_pos, spot_balance_qty, leverage=1)
        self.assertEqual(health_1x['leverage_risk_factor'], 1)
        self.assertFalse(health_1x['leverage_warning'])

        # With 5x leverage (improper delta-neutral)
        health_5x = DeltaNeutralLogic.check_position_health(mock_leveraged_pos, spot_balance_qty, leverage=5)
        self.assertEqual(health_5x['leverage_risk_factor'], 5)
        self.assertTrue(health_5x['leverage_warning'])

        # Wrong leverage is reported in its own field rather than overwriting the
        # liquidation reading. Overwriting it destroyed information: a position at
        # 5x that was ALSO near liquidation reported 'CRITICAL' instead of 'HIGH',
        # and determine_rebalance_action tested only for 'HIGH' -- so the worst
        # state the bot can reach returned ACTION_HOLD.
        self.assertTrue(health_5x['leverage_critical'])
        self.assertIn(health_5x['liquidation_risk_level'], ('LOW', 'MEDIUM', 'HIGH'))

        # ...and it must now actually provoke a close.
        self.assertEqual(
            DeltaNeutralLogic.determine_rebalance_action(health_5x),
            'ACTION_CLOSE_POSITION',
        )

    def test_action_determination(self):
        """Test determine_rebalance_action decision logic."""

        # Test 1: High liquidation risk -> Close position
        high_risk_report = {
            'liquidation_risk_level': 'HIGH',
            'imbalance_percentage': 2.0
        }
        action = DeltaNeutralLogic.determine_rebalance_action(high_risk_report)
        self.assertEqual(action, 'ACTION_CLOSE_POSITION')

        # Test 2: High imbalance -> Rebalance
        imbalanced_report = {
            'liquidation_risk_level': 'LOW',
            'imbalance_percentage': 10.0
        }
        action = DeltaNeutralLogic.determine_rebalance_action(imbalanced_report)
        self.assertEqual(action, 'ACTION_REBALANCE')

        # Test 3: Healthy position -> Hold
        healthy_report = {
            'liquidation_risk_level': 'LOW',
            'imbalance_percentage': 2.0
        }
        action = DeltaNeutralLogic.determine_rebalance_action(healthy_report)
        self.assertEqual(action, 'ACTION_HOLD')

    def test_rebalance_quantity_calculation(self):
        """Test calculate_rebalance_quantities for different imbalance scenarios."""

        # Scenario 1: Too much spot (positive delta)
        health_report_excess_spot = {'net_delta': 2.0}

        rebalance = DeltaNeutralLogic.calculate_rebalance_quantities(
            health_report=health_report_excess_spot,
            current_spot_balance=12.0,
            current_perp_quantity=-10.0,
            spot_price=100.0
        )

        self.assertEqual(rebalance['action_type'], 'REDUCE_SPOT_INCREASE_SHORT')
        self.assertEqual(rebalance['spot_action'], 'SELL')
        self.assertEqual(rebalance['perp_action'], 'INCREASE_SHORT')
        self.assertAlmostEqual(rebalance['spot_quantity'], 1.0, places=6)  # 2.0 / 2
        self.assertAlmostEqual(rebalance['perp_quantity'], 1.0, places=6)
        self.assertAlmostEqual(rebalance['estimated_cost_usd'], 100.0, places=2)

        # Scenario 2: Too much short perp (negative delta)
        health_report_excess_short = {'net_delta': -2.0}

        rebalance = DeltaNeutralLogic.calculate_rebalance_quantities(
            health_report=health_report_excess_short,
            current_spot_balance=8.0,
            current_perp_quantity=-12.0,
            spot_price=100.0
        )

        self.assertEqual(rebalance['action_type'], 'INCREASE_SPOT_REDUCE_SHORT')
        self.assertEqual(rebalance['spot_action'], 'BUY')
        self.assertEqual(rebalance['perp_action'], 'REDUCE_SHORT')

        # Scenario 3: Already balanced
        health_report_balanced = {'net_delta': 0.0}

        rebalance = DeltaNeutralLogic.calculate_rebalance_quantities(
            health_report=health_report_balanced,
            current_spot_balance=10.0,
            current_perp_quantity=-10.0,
            spot_price=100.0
        )

        self.assertEqual(rebalance['action_type'], 'NO_ACTION')
        self.assertIsNone(rebalance['spot_action'])
        self.assertIsNone(rebalance['perp_action'])

    def test_strategy_preconditions(self):
        """Test validate_strategy_preconditions for various balance scenarios."""

        # Test 1: Sufficient balances and proper leverage
        is_valid, errors = DeltaNeutralLogic.validate_strategy_preconditions(
            spot_balance_usdt=30.0,
            perp_balance_usdt=30.0,
            current_leverage=1,
            min_capital_usd=50.0
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Test 2: Insufficient spot balance
        is_valid, errors = DeltaNeutralLogic.validate_strategy_preconditions(
            spot_balance_usdt=20.0,
            perp_balance_usdt=30.0,
            min_capital_usd=50.0
        )
        self.assertFalse(is_valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("Insufficient spot balance", errors[0])

        # Test 3: Insufficient perp balance
        is_valid, errors = DeltaNeutralLogic.validate_strategy_preconditions(
            spot_balance_usdt=30.0,
            perp_balance_usdt=20.0,
            min_capital_usd=50.0
        )
        self.assertFalse(is_valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("Insufficient perp balance", errors[0])

        # Test 4: Both balances insufficient
        is_valid, errors = DeltaNeutralLogic.validate_strategy_preconditions(
            spot_balance_usdt=10.0,
            perp_balance_usdt=15.0,
            min_capital_usd=50.0
        )
        self.assertFalse(is_valid)
        self.assertEqual(len(errors), 2)

        # Test 5: Invalid leverage (not 1x for delta-neutral)
        is_valid, errors = DeltaNeutralLogic.validate_strategy_preconditions(
            spot_balance_usdt=30.0,
            perp_balance_usdt=30.0,
            current_leverage=5,
            min_capital_usd=50.0
        )
        self.assertFalse(is_valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid leverage setting: 5x", errors[0])
        self.assertIn("Delta-neutral strategy requires 1x leverage", errors[0])

    def test_delta_neutral_pair_discovery(self):
        """Test pair discovery functionality."""

        # Test 1: Find common pairs
        spot_symbols = ['BTCUSDT', 'ETHUSDT', 'ASTERUSDT', 'DOGEUSDT']
        perp_symbols = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT']

        common_pairs = DeltaNeutralLogic.find_delta_neutral_pairs(spot_symbols, perp_symbols)
        expected = ['BTCUSDT', 'ETHUSDT']
        self.assertEqual(common_pairs, expected)

        # Test 2: No common pairs
        spot_only = ['ADAUSDT', 'DOGEUSDT']
        perp_only = ['XRPUSDT', 'MATICUSDT']

        no_common = DeltaNeutralLogic.find_delta_neutral_pairs(spot_only, perp_only)
        self.assertEqual(no_common, [])

        # Test 3: Filter viable pairs by volume
        common_pairs = ['BTCUSDT', 'ETHUSDT', 'ASTERUSDT']
        spot_volumes = {'BTCUSDT': 100000, 'ETHUSDT': 50000, 'ASTERUSDT': 5000}
        perp_volumes = {'BTCUSDT': 80000, 'ETHUSDT': 60000, 'ASTERUSDT': 15000}

        viable = DeltaNeutralLogic.filter_viable_pairs(
            common_pairs, min_liquidity_usd=10000,
            spot_volumes_24h=spot_volumes, perp_volumes_24h=perp_volumes
        )
        # Only BTC and ETH meet both spot and perp volume requirements
        expected_viable = ['BTCUSDT', 'ETHUSDT']
        self.assertEqual(viable, expected_viable)

    def test_known_pairs_functionality(self):
        """Test known pairs and extraction functionality."""

        # Test known pairs structure
        known_pairs = DeltaNeutralLogic.get_aster_known_pairs()
        self.assertIsInstance(known_pairs, dict)
        self.assertIn('BTCUSDT', known_pairs)
        self.assertIn('ETHUSDT', known_pairs)
        self.assertIn('ASTERUSDT', known_pairs)

        # Verify structure of known pairs
        for symbol, markets in known_pairs.items():
            self.assertIn('spot', markets)
            self.assertIn('perp', markets)
            self.assertIsInstance(markets['spot'], bool)
            self.assertIsInstance(markets['perp'], bool)

        # Test extraction of delta-neutral candidates
        candidates = DeltaNeutralLogic.extract_delta_neutral_candidates(known_pairs)
        self.assertIsInstance(candidates, list)

        # Should include symbols that have both spot and perp = True
        expected_candidates = []
        for symbol, markets in known_pairs.items():
            if markets['spot'] and markets['perp']:
                expected_candidates.append(symbol)

        self.assertEqual(sorted(candidates), sorted(expected_candidates))
        # As of current implementation, should include BTC, ETH, ASTER, USD1
        self.assertIn('BTCUSDT', candidates)
        self.assertIn('ETHUSDT', candidates)
        self.assertIn('ASTERUSDT', candidates)
        self.assertIn('USD1USDT', candidates)

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""

        # Empty funding histories
        opportunities = DeltaNeutralLogic.analyze_funding_opportunities({}, {})
        self.assertEqual(len(opportunities), 0)

        # Zero capital position sizing
        result = DeltaNeutralLogic.calculate_position_size(0.0, 100.0)
        self.assertEqual(result['spot_quantity'], 0.0)
        self.assertEqual(result['perp_quantity'], 0.0)

        # Zero position size health check
        empty_position = {
            'positionAmt': '0.0',
            'liquidationPrice': '0.0',
            'markPrice': '100.0',
            'unrealizedProfit': '0.0'
        }
        health = DeltaNeutralLogic.check_position_health(empty_position, 0.0)
        self.assertEqual(health['imbalance_percentage'], 0.0)
        self.assertEqual(health['liquidation_risk_level'], 'NONE')


class TestStrategyConstants(unittest.TestCase):
    """Test that strategy constants are reasonable."""

    def test_constant_values(self):
        """Verify strategy constants are set to reasonable values."""
        from strategy_logic import (
            ANNUALIZED_APR_THRESHOLD, MIN_FUNDING_RATE_COUNT,
            MAX_VOLATILITY_THRESHOLD, LIQUIDATION_BUFFER_PCT,
            IMBALANCE_THRESHOLD_PCT, HIGH_RISK_LIQUIDATION_PCT
        )

        # APR threshold should be reasonable for DeFi
        self.assertGreaterEqual(ANNUALIZED_APR_THRESHOLD, 5.0)
        self.assertLessEqual(ANNUALIZED_APR_THRESHOLD, 50.0)

        # Should require meaningful amount of historical data
        self.assertGreaterEqual(MIN_FUNDING_RATE_COUNT, 5)

        # Volatility threshold should be reasonable.
        #
        # This is a coefficient of variation (stdev/mean). The old bound of < 1.0
        # encoded the old 0.05 setting, which demanded a funding series that barely
        # moved -- real series routinely exceed CV 1, so it filtered out
        # essentially every genuine opportunity.
        self.assertGreater(MAX_VOLATILITY_THRESHOLD, 0.0)
        self.assertLess(MAX_VOLATILITY_THRESHOLD, 5.0)

        # Risk thresholds should be conservative
        self.assertGreater(LIQUIDATION_BUFFER_PCT, 0.0)
        self.assertLess(LIQUIDATION_BUFFER_PCT, 0.2)  # Less than 20%

        self.assertGreater(IMBALANCE_THRESHOLD_PCT, 0.0)
        self.assertLess(IMBALANCE_THRESHOLD_PCT, 50.0)  # Less than 50%


if __name__ == '__main__':
    # Run all tests with verbose output
    unittest.main(verbosity=2)