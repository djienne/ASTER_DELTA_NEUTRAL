#!/usr/bin/env python3
"""
Demonstration of dynamic delta-neutral pair discovery functionality.
Shows how to find trading pairs suitable for delta-neutral strategies.
"""

import asyncio
import os
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager
from strategy_logic import DeltaNeutralLogic

load_dotenv()

async def demonstrate_pair_discovery():
    """Demonstrate the pair discovery functionality."""

    print("=" * 80)
    print("DELTA-NEUTRAL PAIR DISCOVERY DEMONSTRATION")
    print("Finding trading pairs with both spot and perpetual markets")
    print("=" * 80)

    # Method 1: Use known pairs (offline, always works)
    print("\n[METHOD 1] Using Known Pairs Database:")
    print("-" * 50)

    known_pairs = DeltaNeutralLogic.get_aster_known_pairs()

    print("All known trading pairs on Aster DEX:")
    for symbol, markets in known_pairs.items():
        spot_status = "[SPOT]" if markets['spot'] else "[----]"
        perp_status = "[PERP]" if markets['perp'] else "[----]"
        delta_neutral = "[DELTA-NEUTRAL]" if markets['spot'] and markets['perp'] else ""

        print(f"  {symbol:<12} {spot_status} {perp_status} {delta_neutral}")

    # Extract delta-neutral candidates
    candidates = DeltaNeutralLogic.extract_delta_neutral_candidates(known_pairs)
    print(f"\nDelta-neutral candidates: {candidates}")
    print(f"Total pairs suitable for strategy: {len(candidates)}")

    # Method 2: Dynamic discovery via API (requires credentials)
    print(f"\n[METHOD 2] Dynamic API Discovery:")
    print("-" * 50)

    # Check if credentials are available
    creds = [
        os.getenv('API_USER'),
        os.getenv('API_SIGNER'),
        os.getenv('API_PRIVATE_KEY'),
        os.getenv('APIV1_PUBLIC_KEY'),
        os.getenv('APIV1_PRIVATE_KEY')
    ]

    if not all(creds):
        print("API credentials not available - skipping dynamic discovery")
        print("Using fallback to known pairs...")
        dynamic_pairs = candidates
    else:
        try:
            # Create API manager
            manager = AsterApiManager(*creds)

            try:
                print("Fetching available trading pairs from Aster DEX APIs...")

                # Discover pairs dynamically
                dynamic_pairs = await manager.discover_delta_neutral_pairs()

                print(f"Dynamically discovered pairs: {dynamic_pairs}")

                # Get detailed information about each pair
                if dynamic_pairs:
                    print(f"\nDetailed analysis of discovered pairs:")
                    volumes = await manager.get_market_volumes_24h(dynamic_pairs)

                    for symbol in dynamic_pairs:
                        volume_info = volumes.get(symbol, {'spot_volume': 0, 'perp_volume': 0})
                        spot_vol = volume_info['spot_volume']
                        perp_vol = volume_info['perp_volume']

                        print(f"  {symbol}:")
                        print(f"    Spot 24h volume: ${spot_vol:,.2f}")
                        print(f"    Perp 24h volume: ${perp_vol:,.2f}")

                        # Assess liquidity
                        min_volume = 10000  # $10k minimum
                        if spot_vol >= min_volume and perp_vol >= min_volume:
                            print(f"    Liquidity: GOOD (both markets > ${min_volume:,})")
                        else:
                            print(f"    Liquidity: LOW (one or both markets < ${min_volume:,})")

            finally:
                await manager.close()

        except Exception as e:
            print(f"Dynamic discovery failed: {e}")
            print("Falling back to known pairs...")
            dynamic_pairs = candidates

    # Method 3: Filter by liquidity requirements
    print(f"\n[METHOD 3] Liquidity Filtering:")
    print("-" * 50)

    # Example: Filter pairs that meet minimum volume requirements
    mock_spot_volumes = {
        'BTCUSDT': 2500000,    # High liquidity
        'ETHUSDT': 1200000,    # High liquidity
        'ASTERUSDT': 45000,    # Medium liquidity
        'USD1USDT': 8000       # Low liquidity
    }

    mock_perp_volumes = {
        'BTCUSDT': 3200000,    # High liquidity
        'ETHUSDT': 1800000,    # High liquidity
        'ASTERUSDT': 38000,    # Medium liquidity
        'USD1USDT': 12000      # Low liquidity
    }

    print("Volume analysis (example data):")
    for symbol in dynamic_pairs:
        spot_vol = mock_spot_volumes.get(symbol, 0)
        perp_vol = mock_perp_volumes.get(symbol, 0)
        print(f"  {symbol}: Spot ${spot_vol:,}, Perp ${perp_vol:,}")

    # Filter by different liquidity thresholds
    liquidity_thresholds = [5000, 10000, 50000, 100000]

    for threshold in liquidity_thresholds:
        viable_pairs = DeltaNeutralLogic.filter_viable_pairs(
            dynamic_pairs,
            min_liquidity_usd=threshold,
            spot_volumes_24h=mock_spot_volumes,
            perp_volumes_24h=mock_perp_volumes
        )

        print(f"\nPairs with >${threshold:,} daily volume: {viable_pairs}")

    # Method 4: Practical usage recommendations
    print(f"\n[PRACTICAL RECOMMENDATIONS]")
    print("=" * 50)

    # High liquidity pairs (safest for large positions)
    high_liquidity = DeltaNeutralLogic.filter_viable_pairs(
        dynamic_pairs,
        min_liquidity_usd=100000,
        spot_volumes_24h=mock_spot_volumes,
        perp_volumes_24h=mock_perp_volumes
    )

    # Medium liquidity pairs (good for smaller positions)
    medium_liquidity = DeltaNeutralLogic.filter_viable_pairs(
        dynamic_pairs,
        min_liquidity_usd=10000,
        spot_volumes_24h=mock_spot_volumes,
        perp_volumes_24h=mock_perp_volumes
    )

    print(f"Recommended for large positions (>$10k): {high_liquidity}")
    print(f"Recommended for small-medium positions: {medium_liquidity}")

    print(f"\nCurrent delta-neutral opportunities available:")
    for symbol in medium_liquidity:
        if symbol in ['BTCUSDT', 'ETHUSDT']:
            print(f"  {symbol}: EXCELLENT (major cryptocurrency, high liquidity)")
        elif symbol in ['ASTERUSDT']:
            print(f"  {symbol}: GOOD (native token, medium liquidity)")
        elif symbol in ['USD1USDT']:
            print(f"  {symbol}: STABLE (stablecoin pair, lower liquidity)")

    print(f"\n[INTEGRATION NOTES]")
    print("-" * 30)
    print("This functionality can be integrated into the main bot to:")
    print("1. Automatically discover new trading pairs as Aster adds them")
    print("2. Filter pairs by liquidity requirements for position sizing")
    print("3. Provide fallback to known pairs when API is unavailable")
    print("4. Update the strategy to focus on the most liquid pairs")
    print("\nThe delta-neutral strategy can now adapt to market changes!")

async def test_integration_example():
    """Show how this integrates with the full strategy."""

    print(f"\n[INTEGRATION EXAMPLE]")
    print("=" * 50)
    print("Complete workflow: Discovery -> Analysis -> Opportunity")

    # Step 1: Discover pairs
    known_pairs = DeltaNeutralLogic.get_aster_known_pairs()
    viable_pairs = DeltaNeutralLogic.extract_delta_neutral_candidates(known_pairs)

    print(f"Step 1: Found {len(viable_pairs)} viable pairs: {viable_pairs}")

    # Step 2: Mock funding data for analysis
    funding_data = [0.0002] * 20  # Stable 0.02% funding
    mock_funding_histories = {symbol: funding_data for symbol in viable_pairs}

    mock_prices = {
        'BTCUSDT': 67500.0,
        'ETHUSDT': 3200.0,
        'ASTERUSDT': 0.45,
        'USD1USDT': 1.0
    }

    # Step 3: Analyze opportunities
    opportunities = DeltaNeutralLogic.analyze_funding_opportunities(
        mock_funding_histories, mock_prices
    )

    print(f"Step 2: Found {len(opportunities)} profitable opportunities")

    # Step 4: Show results
    if opportunities:
        print("Step 3: Opportunity analysis:")
        for opp in opportunities:
            symbol = opp['symbol']
            apr = opp['annualized_apr']
            price = opp['spot_price']
            print(f"  {symbol}: {apr:.1f}% APR @ ${price:,.2f}")

        print(f"\nReady to execute delta-neutral strategy on {len(opportunities)} pairs!")
    else:
        print("No opportunities meet current criteria")

if __name__ == '__main__':
    asyncio.run(demonstrate_pair_discovery())
    asyncio.run(test_integration_example())