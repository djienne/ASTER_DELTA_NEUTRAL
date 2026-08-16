#!/usr/bin/env python3
"""
Final corrected order testing with exact exchange precision requirements.
ASTER: Step size 0.01, XRP: Step size 0.1
"""

import os
import asyncio
import math
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

load_dotenv()

def round_to_step(quantity: float, step_size: float) -> float:
    """Round quantity to the nearest valid step size."""
    if step_size == 0:
        return quantity
    return math.floor(quantity / step_size) * step_size

def format_to_precision(value: float, step_size: float) -> str:
    """Format value according to step size precision."""
    if step_size >= 1:
        return f"{round_to_step(value, step_size):.0f}"
    elif step_size >= 0.1:
        return f"{round_to_step(value, step_size):.1f}"
    elif step_size >= 0.01:
        return f"{round_to_step(value, step_size):.2f}"
    elif step_size >= 0.001:
        return f"{round_to_step(value, step_size):.3f}"
    else:
        return f"{round_to_step(value, step_size):.6f}"

async def test_final_corrected():
    """Final test with exact precision requirements."""

    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Final Corrected Order Testing with Exact Precision")
        print("=" * 60)

        # Exchange-specific precision settings
        ASTER_STEP = 0.01  # From exchange info
        XRP_STEP = 0.1     # From exchange info
        ASTER_PRICE_TICK = 0.00001
        XRP_PRICE_TICK = 0.0001

        # Test symbols
        spot_symbol = 'ASTERUSDT'
        perp_symbol = 'XRPUSDT'

        # Step 1: Get current state
        print("\n1. CURRENT STATE")
        print("-" * 30)

        spot_balances = await manager.get_spot_account_balances()
        usdt_spot = 0.0
        aster_spot = 0.0

        for balance in spot_balances:
            if balance.get('asset') == 'USDT':
                usdt_spot = float(balance.get('free', 0))
            elif balance.get('asset') == 'ASTER':
                aster_spot = float(balance.get('free', 0))

        print(f"Spot: USDT=${usdt_spot:.6f}, ASTER={aster_spot:.6f}")

        # Step 2: Fix ASTER position - sell all with correct precision
        print("\n2. SELLING ASTER WITH CORRECT PRECISION")
        print("-" * 40)

        if aster_spot > 0.01:  # Only if we have more than minimum
            # Round down to valid step size
            sell_quantity = round_to_step(aster_spot, ASTER_STEP)
            formatted_quantity = format_to_precision(sell_quantity, ASTER_STEP)

            print(f"Original ASTER: {aster_spot:.8f}")
            print(f"Rounded to step: {sell_quantity:.8f}")
            print(f"Formatted: {formatted_quantity}")

            if sell_quantity >= 0.01:  # Check minimum
                try:
                    print(f"Executing sell order: {formatted_quantity} ASTER")

                    sell_response = await manager.place_spot_sell_market_order(
                        symbol=spot_symbol,
                        base_quantity=formatted_quantity
                    )
                    print(f"[SUCCESS] ASTER Sell: {sell_response}")

                    # Check results
                    await asyncio.sleep(3)
                    new_balances = await manager.get_spot_account_balances()
                    new_aster = 0.0
                    new_usdt = 0.0

                    for balance in new_balances:
                        if balance.get('asset') == 'ASTER':
                            new_aster = float(balance.get('free', 0))
                        elif balance.get('asset') == 'USDT':
                            new_usdt = float(balance.get('free', 0))

                    aster_sold = aster_spot - new_aster
                    usdt_gained = new_usdt - usdt_spot
                    avg_price = usdt_gained / aster_sold if aster_sold > 0 else 0

                    print(f"[RESULT] Sold: {aster_sold:.6f} ASTER")
                    print(f"[RESULT] Gained: ${usdt_gained:.6f} USDT")
                    print(f"[RESULT] Avg Price: ${avg_price:.6f}")
                    print(f"[RESULT] Remaining ASTER: {new_aster:.6f}")

                    usdt_spot = new_usdt
                    aster_spot = new_aster

                except Exception as e:
                    print(f"[ERROR] ASTER sell failed: {e}")
            else:
                print(f"[SKIP] Quantity {sell_quantity:.8f} below minimum 0.01")
        else:
            print("[SKIP] Insufficient ASTER to sell")

        # Step 3: Test XRP perpetuals with correct precision
        print("\n3. TESTING XRP PERPETUALS")
        print("-" * 30)

        try:
            # Get XRP price
            xrp_ticker = await manager.get_perp_book_ticker(perp_symbol)
            xrp_price = (float(xrp_ticker['bidPrice']) + float(xrp_ticker['askPrice'])) / 2

            # Calculate quantity for $15 order, rounded to step
            target_usd = 15.0
            raw_quantity = target_usd / xrp_price
            xrp_quantity = round_to_step(raw_quantity, XRP_STEP)
            formatted_xrp_qty = format_to_precision(xrp_quantity, XRP_STEP)

            # Price 5% below market
            limit_price = round_to_step(xrp_price * 0.95, XRP_PRICE_TICK)
            formatted_price = format_to_precision(limit_price, XRP_PRICE_TICK)

            print(f"XRP Price: ${xrp_price:.4f}")
            print(f"Target: ${target_usd:.2f} → {raw_quantity:.3f} XRP")
            print(f"Rounded: {formatted_xrp_qty} XRP @ ${formatted_price}")

            if xrp_quantity >= 0.1:  # Check minimum
                order_response = await manager.place_perp_order(
                    symbol=perp_symbol,
                    price=formatted_price,
                    quantity=formatted_xrp_qty,
                    side='BUY'
                )
                order_id = order_response.get('orderId')
                print(f"[SUCCESS] XRP Order Placed: ID {order_id}")

                # Wait and check status
                await asyncio.sleep(2)
                try:
                    status = await manager.get_perp_order_status(perp_symbol, order_id)
                    print(f"[STATUS] {status.get('status', 'Unknown')}")
                except Exception as e:
                    print(f"[WARNING] Status check failed: {e}")

                # Cancel to avoid unwanted fill
                try:
                    await asyncio.sleep(1)
                    cancel_response = await manager.cancel_perp_order(perp_symbol, order_id)
                    print(f"[CANCELED] {cancel_response.get('status', 'Success')}")
                except Exception as e:
                    print(f"[WARNING] Cancel failed: {e}")

            else:
                print(f"[SKIP] Quantity {xrp_quantity:.3f} below minimum 0.1")

        except Exception as e:
            print(f"[ERROR] XRP test failed: {e}")

        # Step 4: Small buy test with remaining USDT
        print("\n4. SMALL BUY TEST")
        print("-" * 20)

        if usdt_spot >= 5.0:  # If we have at least $5
            try:
                # Buy $5 worth of ASTER
                buy_amount = 5.0
                aster_price = (float((await manager.get_spot_book_ticker(spot_symbol))['bidPrice']) +
                              float((await manager.get_spot_book_ticker(spot_symbol))['askPrice'])) / 2

                expected_aster = buy_amount / aster_price
                print(f"Buying ${buy_amount:.2f} USDT worth of ASTER")
                print(f"Expected: ~{expected_aster:.6f} ASTER @ ${aster_price:.6f}")

                buy_response = await manager.place_spot_buy_market_order(
                    symbol=spot_symbol,
                    quote_quantity=f"{buy_amount:.2f}"
                )
                print(f"[SUCCESS] Buy: {buy_response}")

                # Immediately sell it back to clean up
                await asyncio.sleep(3)
                check_balances = await manager.get_spot_account_balances()
                current_aster = 0.0

                for balance in check_balances:
                    if balance.get('asset') == 'ASTER':
                        current_aster = float(balance.get('free', 0))

                if current_aster >= 0.01:
                    cleanup_qty = round_to_step(current_aster, ASTER_STEP)
                    cleanup_formatted = format_to_precision(cleanup_qty, ASTER_STEP)

                    if cleanup_qty >= 0.01:
                        print(f"[CLEANUP] Selling back {cleanup_formatted} ASTER")
                        cleanup_response = await manager.place_spot_sell_market_order(
                            symbol=spot_symbol,
                            base_quantity=cleanup_formatted
                        )
                        print(f"[CLEANUP] Success: {cleanup_response}")

            except Exception as e:
                print(f"[ERROR] Buy test failed: {e}")

        # Final status
        print("\n5. FINAL STATUS")
        print("-" * 20)

        final_spot = await manager.get_spot_account_balances()
        final_perp = await manager.get_perp_account_info()

        print("Final Spot Balances:")
        for balance in final_spot:
            if balance.get('asset') in ['USDT', 'ASTER']:
                free_amt = float(balance.get('free', 0))
                locked_amt = float(balance.get('locked', 0))
                if free_amt > 0.001 or locked_amt > 0.001:
                    print(f"  {balance['asset']}: {free_amt:.6f} (free)")

        print("Active Perpetuals Positions:")
        has_positions = False
        for position in final_perp.get('positions', []):
            pos_amt = float(position.get('positionAmt', 0))
            if abs(pos_amt) > 0.001:
                print(f"  {position['symbol']}: {pos_amt:.6f}")
                has_positions = True

        if not has_positions:
            print("  None")

        print("\n" + "=" * 60)
        print("Final Corrected Testing Complete!")
        print("All order methods tested with proper exchange precision")
        print("Positions cleaned up to avoid unwanted exposure")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(test_final_corrected())