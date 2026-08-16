"""Tests for funding-interval resolution and the fee-aware entry gate.

Two defects motivated this module, and both are asserted here:

1. Hardcoded funding intervals. Aster runs 1h, 4h and 8h simultaneously, so
   `rate * 3 * 365` understated a 4h symbol by 2x and a 1h symbol by 8x.
2. Gross-APR entry gates with no fee term, which selected trades that could not
   cover their own four taker fills.
"""
import unittest
from unittest.mock import AsyncMock

from funding_economics import (
    HOURS_PER_YEAR,
    VERIFIED_TAKER_BPS,
    FundingInterval,
    FundingIntervalResolver,
    IntervalResolutionError,
    TradeCostModel,
    VenueCosts,
    annualize,
    break_even_apr_pct,
    evaluate_entry,
    recommended_hold_hours,
)


def hours_to_ms(hours):
    return int(hours * 3_600_000)


class AnnualizeTests(unittest.TestCase):

    def test_eight_hour_matches_the_legacy_constant(self):
        iv = FundingInterval(8.0, "api_field", 0.0)
        self.assertAlmostEqual(annualize(0.0001, iv), 0.0001 * 3 * 365 * 100, places=9)

    def test_four_hour_is_double_eight_hour(self):
        four = annualize(0.0001, FundingInterval(4.0, "api_field", 0.0))
        eight = annualize(0.0001, FundingInterval(8.0, "api_field", 0.0))
        self.assertAlmostEqual(four, eight * 2, places=9)

    def test_one_hour_is_eight_times_eight_hour(self):
        one = annualize(0.0001, FundingInterval(1.0, "api_field", 0.0))
        eight = annualize(0.0001, FundingInterval(8.0, "api_field", 0.0))
        self.assertAlmostEqual(one, eight * 8, places=9)

    def test_periods_per_year(self):
        self.assertAlmostEqual(
            FundingInterval(4.0, "api_field", 0.0).periods_per_year, HOURS_PER_YEAR / 4)


class IntervalResolutionTests(unittest.IsolatedAsyncioTestCase):

    async def test_api_field_is_preferred(self):
        resolver = FundingIntervalResolver()
        iv = await resolver.resolve_from_api_field(
            "aster", "ASTERUSDT", AsyncMock(return_value=4.0))
        self.assertEqual(iv.hours, 4.0)
        self.assertEqual(iv.source, "api_field")

    async def test_missing_api_field_raises_rather_than_defaulting(self):
        resolver = FundingIntervalResolver()
        with self.assertRaises(IntervalResolutionError):
            await resolver.resolve_from_api_field(
                "aster", "NEWUSDT", AsyncMock(return_value=None))

    async def test_api_failure_is_not_cached(self):
        """A transient error must not pin a symbol at a wrong interval forever."""
        resolver = FundingIntervalResolver()
        with self.assertRaises(IntervalResolutionError):
            await resolver.resolve_from_api_field(
                "aster", "BTCUSDT", AsyncMock(side_effect=RuntimeError("boom")))
        iv = await resolver.resolve_from_api_field(
            "aster", "BTCUSDT", AsyncMock(return_value=8.0))
        self.assertEqual(iv.hours, 8.0)

    async def test_successful_resolution_is_cached(self):
        resolver = FundingIntervalResolver()
        fetch = AsyncMock(return_value=8.0)
        await resolver.resolve_from_api_field("aster", "BTCUSDT", fetch)
        await resolver.resolve_from_api_field("aster", "BTCUSDT", fetch)
        self.assertEqual(fetch.await_count, 1)

    async def test_empirical_resolution_from_settlement_times(self):
        times = [hours_to_ms(4 * i) for i in range(12)]
        resolver = FundingIntervalResolver()
        iv = await resolver.resolve_empirically(
            "aster", "ASTERUSDT", AsyncMock(return_value=times))
        self.assertEqual(iv.hours, 4.0)
        self.assertEqual(iv.source, "empirical")

    async def test_too_few_samples_refuses_to_guess(self):
        times = [hours_to_ms(4 * i) for i in range(3)]
        resolver = FundingIntervalResolver()
        with self.assertRaises(IntervalResolutionError):
            await resolver.resolve_empirically(
                "aster", "X", AsyncMock(return_value=times))

    async def test_disagreeing_gaps_refuse_to_guess(self):
        times = [0, hours_to_ms(1), hours_to_ms(5), hours_to_ms(6), hours_to_ms(14),
                 hours_to_ms(15), hours_to_ms(23), hours_to_ms(40), hours_to_ms(70)]
        resolver = FundingIntervalResolver()
        with self.assertRaises(IntervalResolutionError):
            await resolver.resolve_empirically(
                "aster", "X", AsyncMock(return_value=times))


class BreakEvenTests(unittest.TestCase):

    def setUp(self):
        # Aster's real taker fee on both legs, no slippage.
        taker = VERIFIED_TAKER_BPS["aster"]
        self.cost = TradeCostModel(legs=(
            VenueCosts("aster-spot", taker_bps=taker),
            VenueCosts("aster-perp", taker_bps=taker),
        ))

    def test_round_trip_is_four_fills(self):
        # 2 legs x 2 sides x 4bps = 16bps = 0.16%
        self.assertAlmostEqual(self.cost.roundtrip_bps(), 16.0)
        self.assertAlmostEqual(self.cost.roundtrip_pct(), 0.16)

    def test_break_even_scales_inversely_with_hold(self):
        short = break_even_apr_pct(self.cost, 8.0)
        long = break_even_apr_pct(self.cost, 72.0)
        self.assertAlmostEqual(short / long, 9.0, places=6)

    def test_eight_hour_hold_break_even_is_enormous(self):
        """The number that makes a 15% gross threshold indefensible."""
        self.assertGreater(break_even_apr_pct(self.cost, 8.0), 150.0)

    def test_recommended_hold_inverts_break_even(self):
        hours = recommended_hold_hours(self.cost, 20.0)
        self.assertAlmostEqual(break_even_apr_pct(self.cost, hours), 20.0, places=6)

    def test_zero_hold_is_rejected(self):
        with self.assertRaises(ValueError):
            break_even_apr_pct(self.cost, 0.0)


class EvaluateEntryTests(unittest.TestCase):

    def setUp(self):
        taker = VERIFIED_TAKER_BPS["aster"]
        self.cost = TradeCostModel(legs=(
            VenueCosts("aster-spot", taker_bps=taker),
            VenueCosts("aster-perp", taker_bps=taker),
        ))

    def test_fifteen_percent_at_eight_hours_is_rejected(self):
        """Exactly the trade the old gross ANNUALIZED_APR_THRESHOLD admitted."""
        decision = evaluate_entry(
            symbol="BTCUSDT", gross_net_apr_pct=15.0, notional_usd=1000.0,
            hold_hours=8.0, cost=self.cost)
        self.assertFalse(decision.accept)
        self.assertLess(decision.expected_net_usd, 0.0)

    def test_same_rate_over_a_long_hold_can_pass(self):
        decision = evaluate_entry(
            symbol="BTCUSDT", gross_net_apr_pct=60.0, notional_usd=10_000.0,
            hold_hours=336.0, cost=self.cost)
        self.assertTrue(decision.accept, decision.reason)
        self.assertGreater(decision.expected_net_usd, 0.0)

    def test_haircut_is_applied_to_the_observed_rate(self):
        decision = evaluate_entry(
            symbol="BTCUSDT", gross_net_apr_pct=100.0, notional_usd=1000.0,
            hold_hours=72.0, cost=self.cost, apr_haircut_pct=0.30)
        self.assertAlmostEqual(decision.expected_apr_pct, 70.0, places=6)

    def test_margin_requirement_is_enforced(self):
        """Clears break-even but not the safety multiple."""
        be = break_even_apr_pct(self.cost, 72.0)
        marginal = be * 1.2 / 0.7   # expected_apr ends up 1.2x break-even
        decision = evaluate_entry(
            symbol="BTCUSDT", gross_net_apr_pct=marginal, notional_usd=1_000_000.0,
            hold_hours=72.0, cost=self.cost, min_margin_ratio=2.0)
        self.assertFalse(decision.accept)
        self.assertIn("margin", decision.reason)

    def test_rejection_still_reports_the_numbers(self):
        """So the opportunity table can show break-even per row, not a bare gross."""
        decision = evaluate_entry(
            symbol="BTCUSDT", gross_net_apr_pct=1.0, notional_usd=1000.0,
            hold_hours=8.0, cost=self.cost)
        self.assertFalse(decision.accept)
        self.assertGreater(decision.break_even_apr_pct, 0.0)
        self.assertGreater(decision.expected_cost_usd, 0.0)

    def test_slippage_raises_break_even(self):
        with_slip = TradeCostModel(legs=(
            VenueCosts("aster-spot", taker_bps=4.0, slippage_bps=5.0),
            VenueCosts("aster-perp", taker_bps=4.0, slippage_bps=5.0),
        ))
        self.assertGreater(break_even_apr_pct(with_slip, 72.0),
                           break_even_apr_pct(self.cost, 72.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
