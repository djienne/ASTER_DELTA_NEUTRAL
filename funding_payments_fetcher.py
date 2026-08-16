import asyncio
import os
import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# Assuming aster_api_manager is in the same directory or accessible
from aster_api_manager import AsterApiManager

async def get_funding_payments(
    manager: AsterApiManager,
    symbol: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetches and lists all funding fee payments from the perpetuals account.

    Args:
        manager: An initialized instance of AsterApiManager.
        symbol: Optional symbol to filter payments for (e.g., 'BTCUSDT').
        limit: The maximum number of payments to retrieve.

    Returns:
        A list of dictionaries, where each dictionary represents a funding payment.
    """
    print(f"Fetching last {limit} funding payments for symbol: {symbol or 'ALL'}...")
    try:
        # Use the new method to get only funding fees
        payments = await manager.get_income_history(
            income_type='FUNDING_FEE',
            symbol=symbol,
            limit=limit
        )
        return payments
    except Exception as e:
        print(f"An error occurred while fetching funding payments: {e}")
        return []

async def main():
    """Main function to demonstrate fetching funding payments."""
    load_dotenv()

    # Load credentials from environment variables
    api_user = os.getenv("API_USER")
    api_signer = os.getenv("API_SIGNER")
    api_private_key = os.getenv("API_PRIVATE_KEY")
    apiv1_public = os.getenv("APIV1_PUBLIC_KEY")
    apiv1_private = os.getenv("APIV1_PRIVATE_KEY")

    if not all([api_user, api_signer, api_private_key, apiv1_public, apiv1_private]):
        print("Please set all required API credentials in your .env file.")
        return

    # Initialize the API manager
    manager = AsterApiManager(
        api_user=api_user,
        api_signer=api_signer,
        api_private_key=api_private_key,
        apiv1_public=apiv1_public,
        apiv1_private=apiv1_private
    )

    try:
        # Fetch and print funding payments
        funding_payments = await get_funding_payments(manager, limit=50)

        if funding_payments:
            print(f"Successfully fetched {len(funding_payments)} funding payments:")
            for payment in funding_payments:
                income = float(payment.get('income', 0))
                asset = payment.get('asset', '')
                symbol = payment.get('symbol', 'N/A')
                time_ms = int(payment.get('time', 0))
                payment_time = datetime.datetime.fromtimestamp(time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  - Time: {payment_time}, Symbol: {symbol}, Amount: {income:.8f} {asset}")
        else:
            print("No funding payments found or an error occurred.")

    finally:
        # Cleanly close the session
        await manager.close()

if __name__ == "__main__":
    # This script can be run directly to test the functionality.
    # Ensure your .env file is correctly configured with API keys.
    asyncio.run(main())
