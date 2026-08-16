#!/usr/bin/env python3
"""
Example demonstrating profitable opportunity analysis using strategy_logic.py
Shows realistic funding rate scenarios and how the algorithm identifies opportunities.
"""

from strategy_logic import DeltaNeutralLogic

def demonstrate_opportunity_analysis():
    """Show realistic examples of opportunity analysis."""

    print("=" * 70)
    print("DELTA-NEUTRAL FUNDING RATE OPPORTUNITY ANALYSIS")
    print("=" * 70)

    # Example 1: Highly profitable opportunity (realistic DeFi scenario)
    print("\n[EXAMPLE 1] High-yield stable opportunity:")
    print("-" * 50)

    # Simulate funding rates that meet our criteria:
    # - Consistent positive funding (0.02% per 8 hours)
    # - Low volatility (coefficient of variation < 0.05)
    # - Sufficient data points (>10)
    # This represents consistent bull market with people paying to stay long
    high_yield_funding = [
        0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002,
        0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002
    ]

    funding_histories = {
        'BTCUSDT': high_yield_funding
    }

    spot_prices = {
        'BTCUSDT': 45000.0  # Bitcoin at $45,000
    }

    opportunities = DeltaNeutralLogic.analyze_funding_opportunities(funding_histories, spot_prices)

    if opportunities:
        opp = opportunities[0]
        print(f"Symbol: {opp['symbol']}")
        print(f"Mean Funding Rate: {opp['mean_funding']:.6f} ({opp['mean_funding']*100:.4f}%)")
        print(f"Standard Deviation: {opp['stdev_funding']:.6f}")
        print(f"Coefficient of Variation: {opp['coefficient_of_variation']:.4f}")
        print(f"Annualized APR: {opp['annualized_apr']:.2f}%")
        print(f"Data Points: {opp['data_points_count']}")
        print(f"Current Price: ${opp['spot_price']:,.2f}")

        # Calculate potential profit
        daily_rate = opp['mean_funding'] * 3  # 3 funding periods per day
        monthly_rate = daily_rate * 30
        print(f"\nProfit Potential:")
        print(f"  Daily funding: {daily_rate*100:.4f}%")
        print(f"  Monthly funding: {monthly_rate*100:.2f}%")
        print(f"  On $1000 position: ${monthly_rate*1000:.2f}/month")
    else:
        print("No opportunities found (requirements not met)")

    # Example 2: Calculate position sizing for this opportunity
    print("\n[EXAMPLE 2] Position sizing for $5000 capital:")
    print("-" * 50)

    capital = 5000.0
    btc_price = 45000.0

    position_sizes = DeltaNeutralLogic.calculate_position_size(capital, btc_price)

    print(f"Total Capital: ${capital:,.2f}")
    print(f"BTC Price: ${btc_price:,.2f}")
    print(f"Spot BTC to buy: {position_sizes['spot_quantity']:.6f} BTC")
    print(f"Perp BTC to short: {position_sizes['perp_quantity']:.6f} BTC")
    print(f"Spot investment: ${position_sizes['spot_quantity'] * btc_price:,.2f}")
    print(f"Perp margin needed: ~${position_sizes['perp_quantity'] * btc_price * 0.1:,.2f} (10% margin)")

    # Example 3: Monitor position health
    print("\n[EXAMPLE 3] Position health monitoring:")
    print("-" * 50)

    # Simulate position after some time
    mock_perp_position = {
        'positionAmt': f"-{position_sizes['perp_quantity']:.6f}",  # Short position
        'liquidationPrice': '35000.0',  # Liquidation at $35k (safe distance)
        'markPrice': '46000.0',  # Price moved up to $46k
        'unrealizedProfit': '55.67'  # Small profit from funding
    }

    current_spot_balance = position_sizes['spot_quantity']  # Still holding same amount

    health = DeltaNeutralLogic.check_position_health(mock_perp_position, current_spot_balance)

    print(f"Position Health Report:")
    print(f"  Net Delta: {health['net_delta']:.6f} BTC")
    print(f"  Imbalance: {health['imbalance_percentage']:.2f}%")
    print(f"  Liquidation Risk: {health['liquidation_risk_pct']:.2f}% ({health['liquidation_risk_level']})")
    print(f"  Position Value: ${health['position_value_usd']:,.2f}")
    print(f"  Unrealized PnL: ${health['unrealized_pnl']:.2f}")

    # Example 4: Determine action needed
    action = DeltaNeutralLogic.determine_rebalance_action(health)
    print(f"  Recommended Action: {action}")

    # Example 5: Compare different scenarios
    print("\n[EXAMPLE 4] Comparing different funding scenarios:")
    print("-" * 50)

    scenarios = {
        'High Yield Stable': [0.0002] * 20,  # Consistent 0.02% - meets criteria
        'Medium Yield': [0.0001] * 20,       # Consistent 0.01% - too low APR
        'Volatile High': [0.001, 0.0001, 0.005, 0.0002, 0.008] * 4,  # High but volatile
        'Negative Funding': [-0.0001] * 20,   # Bears paying bulls
        'Low Yield': [0.00003] * 20          # Very low funding
    }

    all_prices = {name: 45000.0 for name in scenarios.keys()}

    print(f"{'Scenario':<20} {'APR':<8} {'Status'}")
    print("-" * 40)

    for name, funding_rates in scenarios.items():
        test_funding = {name: funding_rates}
        test_prices = {name: 45000.0}

        opps = DeltaNeutralLogic.analyze_funding_opportunities(test_funding, test_prices)

        if opps:
            apr = opps[0]['annualized_apr']
            status = "PROFITABLE"
            print(f"{name:<20} {apr:>6.1f}% {status}")
        else:
            print(f"{name:<20} {'N/A':<8} FILTERED OUT")

    # Example 6: Real-world profit calculation
    print("\n[EXAMPLE 5] Real-world profit example (30 days):")
    print("-" * 50)

    if opportunities:
        opp = opportunities[0]
        position_value = 5000.0  # $5k position
        daily_funding_rate = opp['mean_funding'] * 3  # 3 times per day

        print(f"Position Size: ${position_value:,.2f}")
        print(f"Daily Funding Rate: {daily_funding_rate*100:.4f}%")

        daily_profit = position_value * daily_funding_rate
        monthly_profit = daily_profit * 30

        print(f"Daily Funding Profit: ${daily_profit:.2f}")
        print(f"Monthly Funding Profit: ${monthly_profit:.2f}")
        print(f"Monthly ROI: {(monthly_profit/position_value)*100:.2f}%")

        # Account for trading fees (rough estimate)
        estimated_fees = position_value * 0.002  # 0.2% total fees for opening position
        net_monthly_profit = monthly_profit - estimated_fees

        print(f"Less Trading Fees: -${estimated_fees:.2f}")
        print(f"Net Monthly Profit: ${net_monthly_profit:.2f}")
        print(f"Net Monthly ROI: {(net_monthly_profit/position_value)*100:.2f}%")

if __name__ == '__main__':
    demonstrate_opportunity_analysis()