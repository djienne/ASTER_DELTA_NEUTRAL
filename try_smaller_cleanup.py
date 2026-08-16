#!/usr/bin/env python3
"""
Try smaller ASTER cleanup amounts to identify the issue.
"""

import os
import asyncio
import math
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

load_dotenv()

async def try_smaller_cleanup():
    """Try different ASTER sell amounts to identify the issue."""

    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Trying Different ASTER Cleanup Amounts")
        print("=" * 40)

        # Get current state
        spot_balances = await manager.get_spot_account_balances()
        aster_balance = 0.0
        usdt_balance = 0.0

        for balance in spot_balances:
            if balance.get('asset') == 'ASTER':
                aster_balance = float(balance.get('free', 0))
            elif balance.get('asset') == 'USDT':
                usdt_balance = float(balance.get('free', 0))

        print(f"Current: ASTER={aster_balance:.8f}, USDT=${usdt_balance:.6f}")

        # Get current ASTER price
        aster_ticker = await manager.get_spot_book_ticker('ASTERUSDT')
        aster_price = (float(aster_ticker['bidPrice']) + float(aster_ticker['askPrice'])) / 2
        position_value = aster_balance * aster_price

        print(f"ASTER Price: ${aster_price:.6f}")
        print(f"Position Value: ${position_value:.6f}")

        # Try different amounts
        test_amounts = [
            0.01,  # Minimum
            0.50,  # Small
            1.00,  # Medium
            2.00,  # Most of position
            2.56,  # Exactly 2.56 (step aligned)
        ]

        for amount in test_amounts:
            if amount <= aster_balance:
                value = amount * aster_price
                print(f"\nTrying {amount:.2f} ASTER (${value:.2f} value)")

                try:
                    # Just test without executing
                    print(f"  Would sell: quantity={amount:.2f}")

                    if value >= 5.0:  # If above $5 minimum notional
                        print(f"  [TEST] This should work (value ${value:.2f} >= $5 min notional)")
                    else:
                        print(f"  [WARNING] Below min notional (${value:.2f} < $5)")

                except Exception as e:
                    print(f"  [ERROR] {e}")

        # Try a manual calculation for valid amount
        print(f"\nCalculating valid sell amount:")
        min_notional = 5.0  # Typical minimum
        min_quantity_for_notional = min_notional / aster_price

        print(f"Min notional: ${min_notional}")
        print(f"ASTER price: ${aster_price:.6f}")
        print(f"Min quantity needed: {min_quantity_for_notional:.6f}")

        # Round up to next step
        step_size = 0.01
        min_quantity_stepped = math.ceil(min_quantity_for_notional / step_size) * step_size
        print(f"Min quantity (stepped): {min_quantity_stepped:.2f}")

        if min_quantity_stepped <= aster_balance:
            expected_value = min_quantity_stepped * aster_price
            print(f"Expected value: ${expected_value:.2f}")

            if expected_value >= min_notional:
                print(f"\n[RECOMMENDATION] Try selling {min_quantity_stepped:.2f} ASTER")

                # Actually try this amount
                try:
                    sell_response = await manager.place_spot_sell_market_order(
                        symbol='ASTERUSDT',
                        base_quantity=f"{min_quantity_stepped:.2f}"
                    )
                    print(f"[SUCCESS] Sold {min_quantity_stepped:.2f} ASTER: {sell_response}")

                except Exception as e:
                    print(f"[ERROR] Still failed: {e}")
        else:
            print(f"[ERROR] Need {min_quantity_stepped:.2f} but only have {aster_balance:.6f}")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(try_smaller_cleanup())