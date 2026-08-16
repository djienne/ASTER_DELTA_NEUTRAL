#!/usr/bin/env python3
"""
Realistic example of delta-neutral funding rate arbitrage opportunity.
Based on actual market conditions that could occur on Aster DEX.
"""

from strategy_logic import DeltaNeutralLogic

def realistic_market_example():
    """Demonstrate with realistic market scenarios."""

    print("=" * 80)
    print("REALISTIC DELTA-NEUTRAL ARBITRAGE OPPORTUNITY")
    print("Example: Bull market with consistent funding payments")
    print("=" * 80)

    # Scenario: Strong bull market where longs consistently pay shorts
    # This happens when there's high demand for leveraged long positions
    # Funding rate is 0.01-0.03% every 8 hours (typical in DeFi bull markets)

    print("\n[MARKET CONTEXT]")
    print("- Bull market with high long leverage demand")
    print("- Perpetual traders paying premium to stay long")
    print("- Funding rate: 0.01-0.03% every 8 hours")
    print("- We profit by being short perp + long spot (delta neutral)")

    # Realistic funding history - stable bull market conditions
    # Consistent 0.02% funding rate with minimal variation (meets criteria)
    funding_data = [
        0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002,
        0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002,
        0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002
    ]

    # Current market prices
    current_prices = {
        'BTCUSDT': 67500.0,    # BTC at $67.5k
        'ETHUSDT': 3200.0,     # ETH at $3.2k
        'ASTER': 0.45          # ASTER at $0.45
    }

    # Check each asset for opportunities
    for symbol in ['BTCUSDT', 'ETHUSDT', 'ASTER']:
        print(f"\n[ANALYSIS: {symbol}]")
        print("-" * 50)

        funding_histories = {symbol: funding_data}
        asset_prices = {symbol: current_prices[symbol]}

        opportunities = DeltaNeutralLogic.analyze_funding_opportunities(
            funding_histories, asset_prices
        )

        if opportunities:
            opp = opportunities[0]

            print(f"[OK] PROFITABLE OPPORTUNITY FOUND")
            print(f"  Asset: {symbol}")
            print(f"  Current Price: ${opp['spot_price']:,.2f}")
            print(f"  Avg Funding Rate: {opp['mean_funding']*100:.4f}% per 8h")
            print(f"  Volatility (CV): {opp['coefficient_of_variation']:.4f}")
            print(f"  Annualized APR: {opp['annualized_apr']:.1f}%")

            # Calculate position details for different capital amounts
            for capital in [1000, 5000, 10000]:
                print(f"\n  Position with ${capital:,} capital:")

                sizing = DeltaNeutralLogic.calculate_position_size(capital, opp['spot_price'])

                daily_rate = opp['mean_funding'] * 3  # 3 funding periods per day
                monthly_profit = capital * daily_rate * 30

                print(f"    - Buy {sizing['spot_quantity']:.6f} {symbol.replace('USDT','')} spot")
                print(f"    - Short {sizing['perp_quantity']:.6f} {symbol.replace('USDT','')} perp")
                print(f"    - Expected profit: ${monthly_profit:.2f}/month ({monthly_profit/capital*100:.1f}%)")

        else:
            print(f"[SKIP] No opportunity (filtered out)")

    # Detailed walkthrough of a specific trade
    print(f"\n[DETAILED TRADE WALKTHROUGH]")
    print("=" * 50)
    print("Let's walk through opening a $5000 BTC position:")

    btc_funding = {'BTCUSDT': funding_data}
    btc_price = {'BTCUSDT': 67500.0}

    opportunities = DeltaNeutralLogic.analyze_funding_opportunities(btc_funding, btc_price)

    if opportunities:
        opp = opportunities[0]
        capital = 5000.0

        # Step 1: Validate preconditions
        print(f"\n1. VALIDATE ACCOUNT BALANCES")
        spot_usdt = 3000.0  # Available in spot account
        perp_usdt = 2500.0  # Available in perp account

        is_valid, errors = DeltaNeutralLogic.validate_strategy_preconditions(
            spot_usdt, perp_usdt, capital
        )

        if is_valid:
            print(f"   [OK] Sufficient balances for ${capital:,} position")
        else:
            print(f"   [ERROR] Insufficient balances:")
            for error in errors:
                print(f"     - {error}")
            return

        # Step 2: Calculate position sizes
        print(f"\n2. CALCULATE POSITION SIZES")
        sizing = DeltaNeutralLogic.calculate_position_size(capital, opp['spot_price'])

        btc_amount = sizing['spot_quantity']
        spot_cost = btc_amount * opp['spot_price']
        margin_needed = spot_cost * 0.1  # Assume 10x leverage available

        print(f"   - Spot trade: Buy {btc_amount:.6f} BTC for ${spot_cost:,.2f}")
        print(f"   - Perp trade: Short {btc_amount:.6f} BTC (${margin_needed:,.2f} margin)")

        # Step 3: Project profits
        print(f"\n3. PROFIT PROJECTIONS")
        daily_funding_rate = opp['mean_funding'] * 3

        profits = {
            'Daily': capital * daily_funding_rate,
            'Weekly': capital * daily_funding_rate * 7,
            'Monthly': capital * daily_funding_rate * 30,
            'Yearly': capital * daily_funding_rate * 365
        }

        for period, profit in profits.items():
            roi = (profit / capital) * 100
            print(f"   - {period:<8}: ${profit:>7.2f} ({roi:>5.2f}% ROI)")

        # Step 4: Risk analysis
        print(f"\n4. RISK ANALYSIS")

        # Simulate position after price movement
        new_btc_price = 70000.0  # BTC goes up $2500
        mock_position = {
            'positionAmt': f"-{btc_amount:.6f}",
            'liquidationPrice': '85000.0',  # Safe liquidation level
            'markPrice': str(new_btc_price),
            'unrealizedProfit': str((67500 - new_btc_price) * btc_amount)  # Loss from short
        }

        health = DeltaNeutralLogic.check_position_health(mock_position, btc_amount)

        print(f"   - After BTC moves to ${new_btc_price:,}:")
        print(f"     - Net delta: {health['net_delta']:.6f} BTC (perfect hedge)")
        print(f"     - Liquidation risk: {health['liquidation_risk_level']}")
        print(f"     - Perp loss: ${abs(float(mock_position['unrealizedProfit'])):,.2f}")
        print(f"     - Spot gain: ${(new_btc_price - 67500) * btc_amount:,.2f}")
        print(f"     - Net P&L: ~$0.00 (delta neutral!)")

        # Step 5: When to close
        print(f"\n5. EXIT STRATEGY")
        print(f"   - Close when funding turns negative")
        print(f"   - Close if position becomes imbalanced (>5%)")
        print(f"   - Close if liquidation risk becomes HIGH")
        print(f"   - Target: Hold for 30-90 days in bull market")

    print(f"\n[SUMMARY]")
    print("=" * 50)
    print("Delta-neutral funding arbitrage works by:")
    print("1. Buying spot asset (going long)")
    print("2. Shorting equal amount on perpetuals")
    print("3. Collecting funding payments from long traders")
    print("4. Remaining market-neutral (no price exposure)")
    print(f"\nRisk: Low (market neutral)")
    print(f"Reward: Steady funding income (15-25% APR in bull markets)")
    print(f"Best conditions: High leverage demand, positive funding rates")

if __name__ == '__main__':
    realistic_market_example()