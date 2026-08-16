#!/usr/bin/env python3
"""
Test script to analyze real positions on Aster account.
This will check if the analyze_current_positions method can detect
delta-neutral setups in the actual account.
"""

import asyncio
import os
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

async def test_real_position_analysis():
    """Test position analysis on real Aster account."""

    # Load environment variables
    load_dotenv()

    # Get API credentials
    api_user = os.getenv('API_USER')
    api_signer = os.getenv('API_SIGNER')
    api_private_key = os.getenv('API_PRIVATE_KEY')
    apiv1_public = os.getenv('APIV1_PUBLIC_KEY')
    apiv1_private = os.getenv('APIV1_PRIVATE_KEY')

    if not all([api_user, api_signer, api_private_key, apiv1_public, apiv1_private]):
        print("ERROR: Missing API credentials in environment variables")
        print("Required: API_USER, API_SIGNER, API_PRIVATE_KEY, APIV1_PUBLIC_KEY, APIV1_PRIVATE_KEY")
        return

    # Initialize API manager
    manager = AsterApiManager(
        api_user=api_user,
        api_signer=api_signer,
        api_private_key=api_private_key,
        apiv1_public=apiv1_public,
        apiv1_private=apiv1_private
    )

    try:
        print("[SEARCH] Analyzing current positions on Aster account...")
        print("=" * 60)

        # Analyze current positions
        analysis = await manager.analyze_current_positions()

        if not analysis:
            print("No open positions found or unable to fetch position data.")
            return

        print(f"Found {len(analysis)} positions with perpetual exposure:")
        print()

        for symbol, data in analysis.items():
            print(f"[ANALYSIS] {symbol} Position Analysis:")
            print(f"   Spot Balance:     {data['spot_balance']:.6f} {data['base_asset']}")
            print(f"   Perp Position:    {data['perp_position']:.6f} {data['base_asset']}")
            print(f"   Net Delta:        {data['net_delta']:.6f} {data['base_asset']}")
            print(f"   Imbalance:        {data['imbalance_pct']:.2f}%")
            print(f"   Delta Neutral:    {'[YES]' if data['is_delta_neutral'] else '[NO]'}")
            print(f"   Position Value:   ${data['position_value_usd']:.2f}")
            print(f"   Leverage:         {data['leverage']}x")
            print(f"   Mark Price:       ${data['mark_price']:.2f}")

            if data['is_delta_neutral']:
                print(f"   [SUCCESS] Perfect! This is a delta-neutral position.")
            else:
                print(f"   [WARNING] This position is imbalanced by {data['imbalance_pct']:.2f}%")
                if data['net_delta'] > 0:
                    print(f"   [INFO] Too much spot exposure (long bias)")
                else:
                    print(f"   [INFO] Too much perp exposure (short bias)")

            print("-" * 50)

        # Summary
        delta_neutral_positions = [s for s, d in analysis.items() if d['is_delta_neutral']]
        imbalanced_positions = [s for s, d in analysis.items() if not d['is_delta_neutral']]

        print(f"\n[SUMMARY] Position Summary:")
        print(f"   Delta-Neutral Positions: {len(delta_neutral_positions)}")
        if delta_neutral_positions:
            print(f"   [OK] {', '.join(delta_neutral_positions)}")

        print(f"   Imbalanced Positions: {len(imbalanced_positions)}")
        if imbalanced_positions:
            print(f"   [WARNING] {', '.join(imbalanced_positions)}")

        # Specific check for ETH
        if 'ETHUSDT' in analysis:
            eth_data = analysis['ETHUSDT']
            print(f"\n[ETH CHECK] ETH Delta-Neutral Analysis:")
            print(f"   Status: {'[DELTA-NEUTRAL]' if eth_data['is_delta_neutral'] else '[IMBALANCED]'}")
            print(f"   Details: {eth_data['spot_balance']:.6f} ETH spot + {eth_data['perp_position']:.6f} ETH perp = {eth_data['net_delta']:.6f} net delta")
            print(f"   Imbalance: {eth_data['imbalance_pct']:.2f}% (threshold: 2.0%)")

    except Exception as e:
        print(f"[ERROR] Error analyzing positions: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await manager.close()
        # Give a moment for cleanup
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    print("Real Position Analysis Test")
    print("Testing analyze_current_positions() on live Aster account")
    print()

    # Use asyncio.Runner for better cleanup (Python 3.11+) or fallback to run()
    try:
        # For Python 3.11+
        async def main():
            await test_real_position_analysis()

        with asyncio.Runner() as runner:
            runner.run(main())
    except AttributeError:
        # Fallback for older Python versions
        asyncio.run(test_real_position_analysis())