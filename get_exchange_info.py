#!/usr/bin/env python3
"""
Get exchange info to understand exact precision requirements.
"""

import os
import asyncio
import json
import aiohttp
from dotenv import load_dotenv
from aster_api_manager import AsterApiManager

load_dotenv()

async def get_exchange_info():
    """Get exchange info for both spot and perpetuals."""

    manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Getting Exchange Information")
        print("=" * 40)

        # Get perpetuals exchange info
        try:
            if not manager.perp_client.session:
                manager.perp_client.session = aiohttp.ClientSession()

            perp_info = await manager.perp_client.get_exchange_info()

            print("Perpetuals Symbols (XRPUSDT, ASTERUSDT):")
            for symbol_info in perp_info.get('symbols', []):
                if symbol_info.get('symbol') in ['XRPUSDT', 'ASTERUSDT']:
                    print(f"\n{symbol_info['symbol']}:")
                    print(f"  Status: {symbol_info.get('status', 'N/A')}")

                    for filter_info in symbol_info.get('filters', []):
                        if filter_info.get('filterType') == 'LOT_SIZE':
                            print(f"  Quantity - Min: {filter_info.get('minQty')}, Max: {filter_info.get('maxQty')}, Step: {filter_info.get('stepSize')}")
                        elif filter_info.get('filterType') == 'PRICE_FILTER':
                            print(f"  Price - Min: {filter_info.get('minPrice')}, Max: {filter_info.get('maxPrice')}, Tick: {filter_info.get('tickSize')}")
                        elif filter_info.get('filterType') == 'MIN_NOTIONAL':
                            print(f"  Min Notional: {filter_info.get('notional')}")

        except Exception as e:
            print(f"Error getting perpetuals info: {e}")

        # Try to get spot exchange info
        try:
            # Make a direct request to spot exchange info endpoint
            if not manager.session:
                manager.session = aiohttp.ClientSession()

            spot_info_url = "https://sapi.asterdex.com/api/v1/exchangeInfo"
            async with manager.session.get(spot_info_url) as response:
                if response.status == 200:
                    spot_info = await response.json()

                    print("\nSpot Symbols (ASTERUSDT):")
                    for symbol_info in spot_info.get('symbols', []):
                        if symbol_info.get('symbol') == 'ASTERUSDT':
                            print(f"\n{symbol_info['symbol']}:")
                            print(f"  Status: {symbol_info.get('status', 'N/A')}")

                            for filter_info in symbol_info.get('filters', []):
                                if filter_info.get('filterType') == 'LOT_SIZE':
                                    print(f"  Quantity - Min: {filter_info.get('minQty')}, Max: {filter_info.get('maxQty')}, Step: {filter_info.get('stepSize')}")
                                elif filter_info.get('filterType') == 'PRICE_FILTER':
                                    print(f"  Price - Min: {filter_info.get('minPrice')}, Max: {filter_info.get('maxPrice')}, Tick: {filter_info.get('tickSize')}")
                                elif filter_info.get('filterType') == 'MIN_NOTIONAL':
                                    print(f"  Min Notional: {filter_info.get('notional')}")
                else:
                    print(f"Spot exchange info request failed: {response.status}")

        except Exception as e:
            print(f"Error getting spot info: {e}")

    finally:
        await manager.close()

if __name__ == '__main__':
    asyncio.run(get_exchange_info())