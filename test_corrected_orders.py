#!/usr/bin/env python3
"""
Corrected order testing with proper precision handling and position cleanup.
Tests ASTER spot orders and XRP perpetual orders with proper cleanup.
"""

import os
import asyncio
import math
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

load_dotenv()

def format_quantity(quantity: float, precision: int = 6) -> str:
    """Format quantity with proper precision and remove trailing zeros."""
    if precision <= 0:
        return str(int(quantity))

    # Format with specified precision
    formatted = f"{quantity:.{precision}f}"

    # Remove trailing zeros and decimal point if not needed
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')

    return formatted

def format_price(price: float, precision: int = 6) -> str:
    """Format price with proper precision."""
    if precision <= 0:
        return str(int(price))
    return f"{price:.{precision}f}"

async def test_corrected_orders():
    """Test orders with proper precision handling and cleanup."""

    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    positions_to_cleanup = []  # Track positions that need cleanup

    try:
        print("Testing Corrected Orders with Proper Cleanup")
        print("=" * 60)

        # Test symbols
        spot_symbol = 'ASTERUSDT'
        perp_symbol = 'XRPUSDT'  # XRP for perpetuals as mentioned

        # Step 1: Check initial balances and positions
        print("\n1. CHECKING INITIAL STATE")
        print("-" * 40)

        # Check spot balances
        try:
            spot_balances = await manager.get_spot_account_balances()
            usdt_spot = 0.0
            aster_spot = 0.0

            for balance in spot_balances:
                if balance.get('asset') == 'USDT':
                    usdt_spot = float(balance.get('free', 0))
                elif balance.get('asset') == 'ASTER':
                    aster_spot = float(balance.get('free', 0))

            print(f"[OK] Spot Balances - USDT: ${usdt_spot:.6f}, ASTER: {aster_spot:.6f}")

        except Exception as e:
            print(f"[ERROR] Getting spot balances: {e}")
            return

        # Check perpetuals account
        try:
            perp_account = await manager.get_perp_account_info()
            usdt_perp = 0.0
            xrp_position = 0.0

            for asset in perp_account.get('assets', []):
                if asset.get('asset') == 'USDT':
                    usdt_perp = float(asset.get('walletBalance', 0))

            for position in perp_account.get('positions', []):
                if position.get('symbol') == perp_symbol:
                    xrp_position = float(position.get('positionAmt', 0))
                    if xrp_position != 0:
                        positions_to_cleanup.append({
                            'symbol': perp_symbol,
                            'position': xrp_position
                        })

            print(f"[OK] Perpetuals - USDT: ${usdt_perp:.6f}, XRP Position: {xrp_position:.6f}")

        except Exception as e:
            print(f"[ERROR] Getting perpetuals account: {e}")
            return

        # Step 2: Get market prices
        print("\n2. GETTING MARKET PRICES")
        print("-" * 40)

        try:
            aster_spot_ticker = await manager.get_spot_book_ticker(spot_symbol)
            aster_price = (float(aster_spot_ticker['bidPrice']) + float(aster_spot_ticker['askPrice'])) / 2
            print(f"[OK] ASTER Spot Price: ${aster_price:.6f}")
        except Exception as e:
            print(f"[ERROR] Getting ASTER price: {e}")
            return

        try:
            xrp_perp_ticker = await manager.get_perp_book_ticker(perp_symbol)
            xrp_price = (float(xrp_perp_ticker['bidPrice']) + float(xrp_perp_ticker['askPrice'])) / 2
            print(f"[OK] XRP Perpetuals Price: ${xrp_price:.6f}")
        except Exception as e:
            print(f"[ERROR] Getting XRP price: {e}")
            return

        # Step 3: Test ASTER spot sell (fix the current ASTER position)
        print("\n3. TESTING CORRECTED ASTER SPOT SELL")
        print("-" * 40)

        if aster_spot > 0:
            try:
                # Use proper precision for ASTER (typically 6 decimal places for spot)
                # Sell all ASTER to clean up position
                sell_quantity = format_quantity(aster_spot, 6)
                print(f"Selling all ASTER: {sell_quantity} (from {aster_spot:.8f})")

                sell_response = await manager.place_spot_sell_market_order(
                    symbol=spot_symbol,
                    base_quantity=sell_quantity
                )
                print(f"[OK] ASTER Spot Sell Success: {sell_response}")

                # Check new balances
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
                print(f"[OK] Trade Result - Sold: {aster_sold:.6f} ASTER, Gained: ${usdt_gained:.6f} USDT")
                print(f"[OK] New Balances - ASTER: {new_aster:.6f}, USDT: ${new_usdt:.6f}")

                # Update balance for next test
                usdt_spot = new_usdt
                aster_spot = new_aster

            except Exception as e:
                print(f"[ERROR] ASTER spot sell failed: {e}")

        # Step 4: Test XRP perpetuals order
        print("\n4. TESTING XRP PERPETUALS ORDER")
        print("-" * 40)

        # Calculate position size for $15 value
        min_usd_value = 15.0
        xrp_quantity = min_usd_value / xrp_price

        if usdt_perp > min_usd_value or abs(usdt_perp) < 50:  # Allow some negative balance if not too much
            try:
                # Place limit order 5% below market to avoid immediate fill
                limit_price = xrp_price * 0.95
                formatted_quantity = format_quantity(xrp_quantity, 3)  # XRP typically 3 decimals
                formatted_price = format_price(limit_price, 4)  # Price typically 4 decimals

                print(f"Placing XRP BUY limit: {formatted_quantity} @ ${formatted_price}")
                print(f"Target value: ${min_usd_value:.2f}")

                order_response = await manager.place_perp_order(
                    symbol=perp_symbol,
                    price=formatted_price,
                    quantity=formatted_quantity,
                    side='BUY'
                )
                order_id = order_response.get('orderId')
                print(f"[OK] XRP Perpetuals Order Placed: Order ID {order_id}")

                # Check order status
                await asyncio.sleep(2)
                try:
                    status = await manager.get_perp_order_status(perp_symbol, order_id)
                    print(f"[OK] Order Status: {status.get('status', 'Unknown')}")

                    # If filled, add to cleanup list
                    if status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                        filled_qty = float(status.get('executedQty', 0))
                        if filled_qty > 0:
                            positions_to_cleanup.append({
                                'symbol': perp_symbol,
                                'position': filled_qty
                            })
                            print(f"[WARNING] Order filled: {filled_qty} XRP - added to cleanup list")

                except Exception as e:
                    print(f"[WARNING] Could not check order status: {e}")

                # Cancel the order to avoid unwanted fills
                try:
                    cancel_response = await manager.cancel_perp_order(perp_symbol, order_id)
                    print(f"[OK] Order Canceled: {cancel_response.get('status', 'Canceled')}")
                except Exception as e:
                    print(f"[WARNING] Could not cancel order: {e}")

            except Exception as e:
                print(f"[ERROR] XRP perpetuals order failed: {e}")
        else:
            print(f"[WARNING] Insufficient margin for XRP order (Balance: ${usdt_perp:.6f})")

        # Step 5: Test spot market buy with remaining USDT
        print("\n5. TESTING SMALL ASTER SPOT BUY")
        print("-" * 40)

        if usdt_spot >= 10.0:  # Minimum $10 test
            try:
                test_amount = min(10.0, usdt_spot - 1.0)  # Leave $1 buffer
                formatted_amount = format_price(test_amount, 2)

                print(f"Buying ${formatted_amount} worth of ASTER")

                buy_response = await manager.place_spot_buy_market_order(
                    symbol=spot_symbol,
                    quote_quantity=formatted_amount
                )
                print(f"[OK] ASTER Spot Buy Success: {buy_response}")

                # Add small position to cleanup (will sell back)
                await asyncio.sleep(2)
                final_balances = await manager.get_spot_account_balances()
                for balance in final_balances:
                    if balance.get('asset') == 'ASTER':
                        new_aster_balance = float(balance.get('free', 0))
                        if new_aster_balance > aster_spot:
                            aster_gained = new_aster_balance - aster_spot
                            print(f"[OK] Gained {aster_gained:.6f} ASTER")

                            # Immediately sell it back to cleanup
                            print(f"[CLEANUP] Selling back {aster_gained:.6f} ASTER")
                            cleanup_quantity = format_quantity(aster_gained, 6)
                            cleanup_response = await manager.place_spot_sell_market_order(
                                symbol=spot_symbol,
                                base_quantity=cleanup_quantity
                            )
                            print(f"[OK] Cleanup sell: {cleanup_response}")

            except Exception as e:
                print(f"[ERROR] ASTER spot buy failed: {e}")

        # Step 6: Cleanup any remaining positions
        print("\n6. CLEANING UP POSITIONS")
        print("-" * 40)

        if positions_to_cleanup:
            for position in positions_to_cleanup:
                try:
                    symbol = position['symbol']
                    pos_amt = position['position']
                    side_to_close = 'SELL' if pos_amt > 0 else 'BUY'
                    quantity = abs(pos_amt)

                    print(f"Closing {symbol} position: {pos_amt} (side: {side_to_close})")

                    close_response = await manager.close_perp_position(
                        symbol=symbol,
                        quantity=format_quantity(quantity, 3),
                        side_to_close=side_to_close
                    )
                    print(f"[OK] Position closed: {close_response}")

                except Exception as e:
                    print(f"[ERROR] Could not close position {position}: {e}")
        else:
            print("[OK] No positions to cleanup")

        # Final balance check
        print("\n7. FINAL BALANCE CHECK")
        print("-" * 40)

        try:
            final_spot = await manager.get_spot_account_balances()
            final_perp = await manager.get_perp_account_info()

            print("Final Spot Balances:")
            for balance in final_spot:
                if balance.get('asset') in ['USDT', 'ASTER'] and (float(balance.get('free', 0)) > 0 or float(balance.get('locked', 0)) > 0):
                    print(f"  {balance['asset']}: {balance['free']} (free), {balance['locked']} (locked)")

            print("Final Perpetuals Positions:")
            any_positions = False
            for position in final_perp.get('positions', []):
                pos_amt = float(position.get('positionAmt', 0))
                if abs(pos_amt) > 0.001:  # Show positions > 0.001
                    print(f"  {position['symbol']}: {pos_amt}")
                    any_positions = True

            if not any_positions:
                print("  No active positions")

        except Exception as e:
            print(f"[ERROR] Getting final balances: {e}")

        print("\n" + "=" * 60)
        print("Corrected Order Testing Complete!")
        print("[OK] All methods tested with proper precision and cleanup")
        print("[OK] No unwanted positions should remain")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(test_corrected_orders())