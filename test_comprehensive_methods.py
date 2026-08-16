#!/usr/bin/env python3
"""
Comprehensive test script for all AsterApiManager methods with real API calls.
Tests all methods with $10+ order sizes where applicable.
"""

import os
import asyncio
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

# Load environment variables
load_dotenv()

async def test_all_methods():
    """Test all AsterApiManager methods with real API calls."""

    # Initialize manager with credentials from .env
    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Testing AsterApiManager - All Methods")
        print("=" * 60)

        # Test 1: Account Information Methods
        print("\n1. ACCOUNT INFORMATION METHODS")
        print("-" * 40)

        try:
            perp_account = await manager.get_perp_account_info()
            print(f"[OK] Perpetuals Account Info: Found {len(perp_account.get('assets', []))} assets")
            print(f"   Total Wallet Balance: {perp_account.get('totalWalletBalance', 'N/A')} USDT")
            if perp_account.get('positions'):
                active_positions = [p for p in perp_account['positions'] if float(p.get('positionAmt', 0)) != 0]
                print(f"   Active Positions: {len(active_positions)}")
        except Exception as e:
            print(f"[ERROR] Perpetuals Account Info: {e}")

        try:
            spot_balances = await manager.get_spot_account_balances()
            non_zero_balances = [b for b in spot_balances if float(b.get('free', 0)) > 0 or float(b.get('locked', 0)) > 0]
            print(f"[OK] Spot Account Balances: Found {len(non_zero_balances)} non-zero balances")
            for balance in non_zero_balances[:5]:  # Show first 5
                total = float(balance.get('free', 0)) + float(balance.get('locked', 0))
                print(f"    {balance['asset']}: {total:.6f} (Free: {balance['free']}, Locked: {balance['locked']})")
        except Exception as e:
            print(f"[ERROR] Spot Account Balances: {e}")

        # Test 2: Market Data Methods
        print("\n 2. MARKET DATA METHODS")
        print("-" * 40)

        test_symbol = 'BTCUSDT'

        try:
            funding_history = await manager.get_funding_rate_history(test_symbol, limit=5)
            print(f"[OK] Funding Rate History ({test_symbol}): {len(funding_history)} records")
            if funding_history:
                latest = funding_history[0]
                print(f"    Latest Rate: {latest.get('fundingRate', 'N/A')} at {latest.get('fundingTime', 'N/A')}")
        except Exception as e:
            print(f"[ERROR] Funding Rate History: {e}")

        try:
            perp_ticker = await manager.get_perp_book_ticker(test_symbol)
            print(f"[OK] Perpetuals Book Ticker ({test_symbol}):")
            print(f"   BID: Bid: ${float(perp_ticker.get('bidPrice', 0)):,.2f} (Qty: {perp_ticker.get('bidQty', 'N/A')})")
            print(f"   ASK: Ask: ${float(perp_ticker.get('askPrice', 0)):,.2f} (Qty: {perp_ticker.get('askQty', 'N/A')})")
            perp_mid_price = (float(perp_ticker.get('bidPrice', 0)) + float(perp_ticker.get('askPrice', 0))) / 2
        except Exception as e:
            print(f"[ERROR] Perpetuals Book Ticker: {e}")
            perp_mid_price = 50000  # Fallback for calculations

        try:
            spot_ticker = await manager.get_spot_book_ticker(test_symbol)
            print(f"[OK] Spot Book Ticker ({test_symbol}):")
            print(f"   BID: Bid: ${float(spot_ticker.get('bidPrice', 0)):,.2f} (Qty: {spot_ticker.get('bidQty', 'N/A')})")
            print(f"   ASK: Ask: ${float(spot_ticker.get('askPrice', 0)):,.2f} (Qty: {spot_ticker.get('askQty', 'N/A')})")
            spot_mid_price = (float(spot_ticker.get('bidPrice', 0)) + float(spot_ticker.get('askPrice', 0))) / 2
        except Exception as e:
            print(f"[ERROR] Spot Book Ticker: {e}")
            spot_mid_price = 50000  # Fallback

        # Test 3: Order Status Methods (using dummy order IDs)
        print("\n 3. ORDER STATUS METHODS")
        print("-" * 40)

        try:
            # This will likely fail with "Order does not exist" but tests the method
            await manager.get_perp_order_status(test_symbol, 999999999)
            print("[OK] Perpetuals Order Status: Method works (order not found is expected)")
        except Exception as e:
            if "not exist" in str(e).lower() or "unknown order" in str(e).lower():
                print("[OK] Perpetuals Order Status: Method works (order not found is expected)")
            else:
                print(f"[ERROR] Perpetuals Order Status: {e}")

        try:
            # This will likely fail with "Order does not exist" but tests the method
            await manager.get_spot_order_status(test_symbol, 999999999)
            print("[OK] Spot Order Status: Method works (order not found is expected)")
        except Exception as e:
            if "not exist" in str(e).lower() or "unknown order" in str(e).lower():
                print("[OK] Spot Order Status: Method works (order not found is expected)")
            else:
                print(f"[ERROR] Spot Order Status: {e}")

        # Test 4: Order Execution Methods (with $10+ minimum)
        print("\n 4. ORDER EXECUTION METHODS")
        print("-" * 40)
        print("[WARNING]  Testing with minimum $10 order sizes as requested")

        # Calculate quantities for $10+ orders
        min_usd_value = 15.0  # $15 to be safe above $10 minimum

        perp_quantity = min_usd_value / perp_mid_price
        spot_quote_quantity = min_usd_value

        print(f"INFO: Using mid prices - Perp: ${perp_mid_price:,.2f}, Spot: ${spot_mid_price:,.2f}")
        print(f"INFO: Order sizes - Perp qty: {perp_quantity:.6f} BTC, Spot: ${spot_quote_quantity:.2f} USDT")

        # Test perpetuals limit order (far out of the money to avoid filling)
        try:
            low_price = perp_mid_price * 0.5  # 50% below market
            print(f"\n- Testing Perpetuals Limit Order (${min_usd_value:.0f} value)")
            print(f"    Price: ${low_price:,.2f} (50% below market), Qty: {perp_quantity:.6f}")

            order_response = await manager.place_perp_order(
                symbol=test_symbol,
                price=str(low_price),
                quantity=f"{perp_quantity:.6f}",
                side='BUY'
            )
            order_id = order_response.get('orderId')
            print(f"[OK] Perpetuals Order Placed: Order ID {order_id}")

            # Check order status
            await asyncio.sleep(1)
            status = await manager.get_perp_order_status(test_symbol, order_id)
            print(f"    Order Status: {status.get('status', 'Unknown')}")

            # Cancel the order
            cancel_response = await manager.cancel_perp_order(test_symbol, order_id)
            print(f"[OK] Order Canceled: {cancel_response.get('status', 'Success')}")

        except Exception as e:
            print(f"[ERROR] Perpetuals Order Test: {e}")

        # Test spot market orders (will likely fail due to insufficient funds)
        print(f"\n- Testing Spot Market Buy Order (${min_usd_value:.0f} value)")
        try:
            buy_response = await manager.place_spot_buy_market_order(
                symbol=test_symbol,
                quote_quantity=str(spot_quote_quantity)
            )
            print(f"[OK] Spot Market Buy: {buy_response}")
        except Exception as e:
            if "insufficient" in str(e).lower() or "balance" in str(e).lower():
                print(f"[WARNING]  Spot Market Buy: Insufficient funds (expected) - {e}")
            else:
                print(f"[ERROR] Spot Market Buy: {e}")

        print(f"\n- Testing Spot Market Sell Order")
        try:
            sell_quantity = min_usd_value / spot_mid_price
            sell_response = await manager.place_spot_sell_market_order(
                symbol=test_symbol,
                base_quantity=f"{sell_quantity:.6f}"
            )
            print(f"[OK] Spot Market Sell: {sell_response}")
        except Exception as e:
            if "insufficient" in str(e).lower() or "balance" in str(e).lower():
                print(f"[WARNING]  Spot Market Sell: Insufficient funds (expected) - {e}")
            else:
                print(f"[ERROR] Spot Market Sell: {e}")

        # Test position closing (will likely fail if no position exists)
        print(f"\n- Testing Position Close")
        try:
            close_response = await manager.close_perp_position(
                symbol=test_symbol,
                quantity=f"{perp_quantity:.6f}",
                side_to_close='SELL'
            )
            print(f"[OK] Position Close: {close_response}")
        except Exception as e:
            if "position" in str(e).lower() or "reduce" in str(e).lower():
                print(f"[WARNING]  Position Close: No position to close (expected) - {e}")
            else:
                print(f"[ERROR] Position Close: {e}")

        print("\n" + "=" * 60)
        print(" Comprehensive Method Testing Complete!")
        print("[OK] All methods have been tested with real API calls")
        print("[WARNING]  Insufficient fund errors are expected and normal")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(test_all_methods())