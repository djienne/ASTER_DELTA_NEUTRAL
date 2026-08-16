#!/usr/bin/env python3
"""
Sells all available ASTER on the spot market.
"""

import os
import asyncio
import math
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

# Load environment variables
load_dotenv()

async def sell_all_aster():
    """Sells all available ASTER on the spot market."""

    # Initialize manager with credentials from .env
    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Selling all ASTER...")
        print("=" * 60)

        # Get current ASTER balance
        spot_balances = await manager.get_spot_account_balances()
        aster_balance = 0.0
        for balance in spot_balances:
            if balance.get('asset') == 'ASTER':
                aster_balance = float(balance.get('free', 0))
                break

        if aster_balance > 0:
            print(f"Found {aster_balance} ASTER to sell.")

            # Get the current price of ASTER
            ticker = await manager.get_spot_book_ticker('ASTERUSDT')
            price = float(ticker.get('bidPrice', 0))

            # Check if the total value is greater than 5 USDT
            total_value = aster_balance * price
            if total_value > 5 * 1.01:
                # Get symbol info to find the step size for the quantity
                symbol_info = await manager.get_spot_symbol_info('ASTERUSDT')
                step_size = 0.0
                for f in symbol_info.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        break

                if step_size > 0:
                    # Calculate precision
                    precision = int(round(-math.log(step_size, 10), 0))
                    # Round down to the nearest step size
                    rounded_quantity = math.floor(aster_balance / step_size) * step_size
                    print(f"Rounding quantity to {precision} decimal places: {rounded_quantity}")

                    # Place a market sell order for the rounded balance
                    sell_response = await manager.place_spot_sell_market_order(
                        symbol='ASTERUSDT',
                        base_quantity=f"{rounded_quantity:.{precision}f}"
                    )
                    print(f"[SUCCESS] ASTER Sell Order Response: {sell_response}")
                else:
                    print("[ERROR] Could not determine step size for ASTERUSDT.")
            else:
                print(f"Total value of ASTER is {total_value:.2f} USDT, which is not enough to sell.")

        else:
            print("No ASTER balance to sell.")

    except Exception as e:
        print(f"[ERROR] Failed to sell ASTER: {e}")
    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(sell_all_aster())