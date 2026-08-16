#!/usr/bin/env python3
"""
Final cleanup - sell remaining ASTER with exact precision.
"""

import os
import asyncio
import math
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

load_dotenv()

def round_to_step(quantity: float, step_size: float) -> float:
    """Round quantity DOWN to the nearest valid step size."""
    if step_size == 0:
        return quantity
    return math.floor(quantity / step_size) * step_size

async def cleanup_aster():
    """Clean up remaining ASTER position."""

    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Cleaning Up Remaining ASTER Position")
        print("=" * 40)

        # Get current ASTER balance
        spot_balances = await manager.get_spot_account_balances()
        aster_balance = 0.0

        for balance in spot_balances:
            if balance.get('asset') == 'ASTER':
                aster_balance = float(balance.get('free', 0))

        print(f"Current ASTER Balance: {aster_balance:.8f}")

        if aster_balance >= 0.01:  # Minimum step size
            # Round DOWN to valid step (0.01)
            ASTER_STEP = 0.01
            sell_quantity = round_to_step(aster_balance, ASTER_STEP)

            print(f"Rounded to valid step: {sell_quantity:.2f}")

            if sell_quantity >= 0.01:
                try:
                    print(f"Selling {sell_quantity:.2f} ASTER...")

                    sell_response = await manager.place_spot_sell_market_order(
                        symbol='ASTERUSDT',
                        base_quantity=f"{sell_quantity:.2f}"
                    )

                    print(f"[SUCCESS] Cleanup Complete: {sell_response}")

                    # Check final balance
                    await asyncio.sleep(3)
                    final_balances = await manager.get_spot_account_balances()
                    final_aster = 0.0
                    final_usdt = 0.0

                    for balance in final_balances:
                        if balance.get('asset') == 'ASTER':
                            final_aster = float(balance.get('free', 0))
                        elif balance.get('asset') == 'USDT':
                            final_usdt = float(balance.get('free', 0))

                    print(f"Final ASTER: {final_aster:.8f}")
                    print(f"Final USDT: ${final_usdt:.6f}")

                    if final_aster < 0.01:
                        print("[SUCCESS] Position cleaned up successfully!")
                    else:
                        print(f"[WARNING] Still have {final_aster:.8f} ASTER remaining")

                except Exception as e:
                    print(f"[ERROR] Cleanup failed: {e}")
            else:
                print("[INFO] Quantity too small to sell")
        else:
            print("[INFO] No significant ASTER position to clean up")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(cleanup_aster())