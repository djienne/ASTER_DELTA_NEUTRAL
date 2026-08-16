#!/usr/bin/env python3
"""
Check ASTER symbol filters to understand precision requirements.
"""

import os
import asyncio
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

load_dotenv()

async def check_aster_filters():
    """Check ASTER symbol filters for both spot and perpetuals."""

    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Checking ASTER Symbol Filters")
        print("=" * 40)

        # Check perpetuals symbol filters using the existing api_client method
        try:
            perp_filters = await manager.perp_client.get_symbol_filters('ASTERUSDT')
            print(f"Perpetuals ASTERUSDT Filters:")
            print(f"  Price Precision: {perp_filters.get('price_precision', 'N/A')}")
            print(f"  Tick Size: {perp_filters.get('tick_size', 'N/A')}")
            print(f"  Quantity Precision: {perp_filters.get('quantity_precision', 'N/A')}")
            print(f"  Step Size: {perp_filters.get('step_size', 'N/A')}")
            print(f"  Min Notional: {perp_filters.get('min_notional', 'N/A')}")
        except Exception as e:
            print(f"Error getting perpetuals filters: {e}")

        # Check current spot balances for exact available amounts
        try:
            print(f"\nCurrent Spot Balances:")
            spot_balances = await manager.get_spot_account_balances()
            for balance in spot_balances:
                if balance.get('asset') in ['ASTER', 'USDT']:
                    free = balance.get('free', '0')
                    locked = balance.get('locked', '0')
                    print(f"  {balance['asset']}: Free={free}, Locked={locked}")
        except Exception as e:
            print(f"Error getting balances: {e}")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(check_aster_filters())