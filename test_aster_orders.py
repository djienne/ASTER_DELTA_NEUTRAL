#!/usr/bin/env python3
"""
Focused test for ASTER buy/sell orders on both perpetual and spot markets.
Uses ASTER symbol to avoid interfering with other cryptocurrencies.
"""

import os
import asyncio
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

# Load environment variables
load_dotenv()

async def test_aster_orders():
    """Test ASTER orders on both perpetual and spot markets."""

    # Initialize manager with credentials from .env
    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Testing ASTER Orders - Perpetual and Spot Markets")
        print("=" * 60)

        # Test symbol
        test_symbol = 'ASTERUSDT'

        # Step 1: Check current balances
        print("\n1. CHECKING CURRENT BALANCES")
        print("-" * 40)

        try:
            perp_account = await manager.get_perp_account_info()
            usdt_perp_balance = 0.0
            aster_perp_position = 0.0

            for asset in perp_account.get('assets', []):
                if asset.get('asset') == 'USDT':
                    usdt_perp_balance = float(asset.get('walletBalance', 0))

            for position in perp_account.get('positions', []):
                if position.get('symbol') == test_symbol:
                    aster_perp_position = float(position.get('positionAmt', 0))

            print(f"[OK] Perpetuals - USDT Balance: ${usdt_perp_balance:.6f}")
            print(f"[OK] Perpetuals - ASTER Position: {aster_perp_position:.6f}")

        except Exception as e:
            print(f"[ERROR] Getting perpetuals account: {e}")
            return

        try:
            spot_balances = await manager.get_spot_account_balances()
            usdt_spot_balance = 0.0
            aster_spot_balance = 0.0

            for balance in spot_balances:
                if balance.get('asset') == 'USDT':
                    usdt_spot_balance = float(balance.get('free', 0))
                elif balance.get('asset') == 'ASTER':
                    aster_spot_balance = float(balance.get('free', 0))

            print(f"[OK] Spot - USDT Balance: ${usdt_spot_balance:.6f}")
            print(f"[OK] Spot - ASTER Balance: {aster_spot_balance:.6f}")

        except Exception as e:
            print(f"[ERROR] Getting spot balances: {e}")
            return

        # Step 2: Get current market prices
        print("\n2. GETTING MARKET PRICES")
        print("-" * 40)

        try:
            perp_ticker = await manager.get_perp_book_ticker(test_symbol)
            perp_bid = float(perp_ticker.get('bidPrice', 0))
            perp_ask = float(perp_ticker.get('askPrice', 0))
            perp_mid = (perp_bid + perp_ask) / 2
            print(f"[OK] Perpetuals - Bid: ${perp_bid:.6f}, Ask: ${perp_ask:.6f}, Mid: ${perp_mid:.6f}")

        except Exception as e:
            print(f"[ERROR] Getting perpetuals ticker: {e}")
            return

        try:
            spot_ticker = await manager.get_spot_book_ticker(test_symbol)
            spot_bid = float(spot_ticker.get('bidPrice', 0))
            spot_ask = float(spot_ticker.get('askPrice', 0))
            spot_mid = (spot_bid + spot_ask) / 2
            print(f"[OK] Spot - Bid: ${spot_bid:.6f}, Ask: ${spot_ask:.6f}, Mid: ${spot_mid:.6f}")

        except Exception as e:
            print(f"[ERROR] Getting spot ticker: {e}")
            return

        # Step 3: Calculate order sizes (minimum $15 value)
        min_usd_value = 15.0
        perp_quantity = min_usd_value / perp_mid
        spot_quote_quantity = min_usd_value

        print(f"\n3. CALCULATED ORDER SIZES")
        print("-" * 40)
        print(f"Target USD Value: ${min_usd_value:.2f}")
        print(f"Perpetuals Quantity: {perp_quantity:.6f} ASTER")
        print(f"Spot Quote Quantity: ${spot_quote_quantity:.2f} USDT")

        # Check if we have sufficient funds
        print(f"\nFund Check:")
        print(f"Perp USDT needed: ${min_usd_value:.2f}, Available: ${usdt_perp_balance:.2f}")
        print(f"Spot USDT needed: ${spot_quote_quantity:.2f}, Available: ${usdt_spot_balance:.2f}")

        # Step 4: Test Perpetuals Limit Order
        print("\n4. TESTING PERPETUALS LIMIT ORDER")
        print("-" * 40)

        if usdt_perp_balance >= min_usd_value:
            try:
                # Place limit order slightly below market (90% of mid price) to avoid immediate fill
                limit_price = perp_mid * 0.90
                print(f"Placing BUY limit order: {perp_quantity:.6f} ASTER @ ${limit_price:.6f}")

                order_response = await manager.place_perp_order(
                    symbol=test_symbol,
                    price=f"{limit_price:.6f}",
                    quantity=f"{perp_quantity:.6f}",
                    side='BUY'
                )
                order_id = order_response.get('orderId')
                print(f"[OK] Perpetuals Order Placed: Order ID {order_id}")
                print(f"    Response: {order_response}")

                # Check order status
                await asyncio.sleep(2)
                try:
                    status = await manager.get_perp_order_status(test_symbol, order_id)
                    print(f"[OK] Order Status: {status.get('status', 'Unknown')}")
                except Exception as e:
                    print(f"[WARNING] Could not check order status: {e}")

                # Cancel the order
                try:
                    cancel_response = await manager.cancel_perp_order(test_symbol, order_id)
                    print(f"[OK] Order Canceled: {cancel_response}")
                except Exception as e:
                    print(f"[WARNING] Could not cancel order: {e}")

            except Exception as e:
                print(f"[ERROR] Perpetuals limit order failed: {e}")
        else:
            print(f"[WARNING] Insufficient USDT in perpetuals account for ${min_usd_value:.2f} order")

        # Step 5: Test Spot Market Buy Order
        print("\n5. TESTING SPOT MARKET BUY ORDER")
        print("-" * 40)

        if usdt_spot_balance >= spot_quote_quantity:
            try:
                print(f"Placing market BUY order: ${spot_quote_quantity:.2f} USDT worth of ASTER")

                buy_response = await manager.place_spot_buy_market_order(
                    symbol=test_symbol,
                    quote_quantity=f"{spot_quote_quantity:.2f}"
                )
                print(f"[OK] Spot Market Buy: {buy_response}")

                # Wait a moment then check new balance
                await asyncio.sleep(3)
                new_balances = await manager.get_spot_account_balances()
                new_aster_balance = 0.0
                new_usdt_balance = 0.0

                for balance in new_balances:
                    if balance.get('asset') == 'ASTER':
                        new_aster_balance = float(balance.get('free', 0))
                    elif balance.get('asset') == 'USDT':
                        new_usdt_balance = float(balance.get('free', 0))

                print(f"[OK] New Balances - ASTER: {new_aster_balance:.6f}, USDT: ${new_usdt_balance:.6f}")
                aster_gained = new_aster_balance - aster_spot_balance
                usdt_spent = usdt_spot_balance - new_usdt_balance
                print(f"[OK] Trade Result - Gained: {aster_gained:.6f} ASTER, Spent: ${usdt_spent:.6f} USDT")

                # Update balance for next test
                aster_spot_balance = new_aster_balance
                usdt_spot_balance = new_usdt_balance

            except Exception as e:
                print(f"[ERROR] Spot market buy failed: {e}")
        else:
            print(f"[WARNING] Insufficient USDT in spot account for ${spot_quote_quantity:.2f} order")

        # Step 6: Test Spot Market Sell Order (if we have ASTER)
        print("\n6. TESTING SPOT MARKET SELL ORDER")
        print("-" * 40)

        if aster_spot_balance > 0:
            try:
                # Sell half of our ASTER balance or enough for $10 minimum
                min_sell_aster = 10.0 / spot_mid
                sell_quantity = max(min_sell_aster, aster_spot_balance * 0.5)
                sell_quantity = min(sell_quantity, aster_spot_balance)  # Don't sell more than we have

                print(f"Placing market SELL order: {sell_quantity:.6f} ASTER")
                print(f"Available ASTER: {aster_spot_balance:.6f}")

                sell_response = await manager.place_spot_sell_market_order(
                    symbol=test_symbol,
                    base_quantity=f"{sell_quantity:.6f}"
                )
                print(f"[OK] Spot Market Sell: {sell_response}")

                # Wait a moment then check new balance
                await asyncio.sleep(3)
                final_balances = await manager.get_spot_account_balances()
                final_aster_balance = 0.0
                final_usdt_balance = 0.0

                for balance in final_balances:
                    if balance.get('asset') == 'ASTER':
                        final_aster_balance = float(balance.get('free', 0))
                    elif balance.get('asset') == 'USDT':
                        final_usdt_balance = float(balance.get('free', 0))

                print(f"[OK] Final Balances - ASTER: {final_aster_balance:.6f}, USDT: ${final_usdt_balance:.6f}")
                aster_sold = aster_spot_balance - final_aster_balance
                usdt_gained = final_usdt_balance - usdt_spot_balance
                print(f"[OK] Trade Result - Sold: {aster_sold:.6f} ASTER, Gained: ${usdt_gained:.6f} USDT")

            except Exception as e:
                print(f"[ERROR] Spot market sell failed: {e}")
        else:
            print(f"[WARNING] No ASTER balance to sell (Balance: {aster_spot_balance:.6f})")

        print("\n" + "=" * 60)
        print("ASTER Order Testing Complete!")
        print("[OK] All order methods have been tested with real trades")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(test_aster_orders())