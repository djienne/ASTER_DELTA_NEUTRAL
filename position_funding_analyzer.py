import asyncio
import os
import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from decimal import Decimal
from colorama import Fore, Style, init

from aster_api_manager import AsterApiManager

async def calculate_funding_for_position(manager: AsterApiManager, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Calculates the total funding fees paid/received for a specific open position.

    Args:
        manager: An initialized instance of AsterApiManager.
        symbol: The symbol of the open position to analyze (e.g., 'ASTERUSDT').

    Returns:
        A dictionary with the analysis details or None if no position is found.
    """
    print(f"\n{Fore.CYAN}Analyzing funding for current '{symbol}' position...{Style.RESET_ALL}")

    # 1. Get current open position and other account data
    try:
        # Fetch position, spot balances, and ticker price concurrently
        all_positions_task = manager.get_perp_account_info()
        spot_balances_task = manager.get_spot_account_balances()
        ticker_task = manager.get_perp_book_ticker(symbol)
        
        all_positions, spot_balances, ticker = await asyncio.gather(
            all_positions_task, spot_balances_task, ticker_task
        )

        position = next((p for p in all_positions.get('positions', []) if p.get('symbol') == symbol and Decimal(p.get('positionAmt', '0')) != 0), None)

        if not position:
            print(f"No open position found for {symbol}.")
            return None

        # Extract data from fetched results
        current_pos_amount = Decimal(position.get('positionAmt', '0'))
        position_notional = Decimal(position.get('notional', '0'))
        unrealized_pnl = Decimal(position.get('unrealizedProfit', '0'))
        mark_price = Decimal(ticker.get('bidPrice')) # Use bid price as a conservative current price

        base_asset = symbol.replace('USDT', '')
        spot_balance = next((Decimal(b.get('free', '0')) for b in spot_balances if b.get('asset') == base_asset), Decimal('0'))
        spot_value_usd = spot_balance * mark_price

        # Calculate the new "effective position value"
        effective_position_value = spot_value_usd + abs(position_notional) + unrealized_pnl

        print(f"Found open position: {current_pos_amount} {symbol} (Notional: {position_notional:.4f} USDT)")
        print(f"Spot Balance: {spot_balance} {base_asset} (Value: {spot_value_usd:.4f} USDT)")
        print(f"Unrealized PnL: {unrealized_pnl:.4f} USDT")
        print(f"Effective Position Value: {effective_position_value:.4f} USDT")


    except Exception as e:
        print(f"Error fetching account or market data: {e}")
        return None

    # 2. Fetch recent trades to find the position's opening time
    try:
        trades = await manager.get_user_trades(symbol=symbol, limit=1000)
        if not trades:
            print(f"No recent trades found for {symbol}.")
            return None

        # Sort trades from oldest to newest
        trades.sort(key=lambda x: int(x['time']))

        # Reconstruct the position from recent trades to find the opening trade
        position_start_time = None
        running_total = Decimal('0')
        
        # Iterate backwards from the most recent trade
        for trade in reversed(trades):
            trade_qty = Decimal(trade['qty'])
            # If the trade was a sell, the quantity is negative for our calculation
            if trade['side'].upper() == 'SELL':
                trade_qty *= -1
            
            running_total += trade_qty
            
            # Check if the running total matches the current position
            # We use a small tolerance for floating point comparisons
            if abs(running_total - current_pos_amount) < Decimal('0.000001'):
                position_start_time = int(trade['time'])
                break
        
        if not position_start_time:
            print("Could not determine the position start time from the last 1000 trades.")
            print("The position might be older, or this is a partial position.")
            return None

        start_datetime = datetime.datetime.fromtimestamp(position_start_time / 1000)
        print(f"Position start time identified: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"Error fetching user trades: {e}")
        return None

    # 3. Fetch funding payments since the position was opened
    try:
        funding_payments = await manager.get_income_history(
            symbol=symbol,
            income_type='FUNDING_FEE',
            start_time=position_start_time,
            limit=1000  # Max limit
        )

        total_funding = sum(Decimal(p['income']) for p in funding_payments)
        
        # Calculate funding as a percentage of the new effective value
        funding_percentage = Decimal('0')
        if effective_position_value != 0:
            funding_percentage = (total_funding / effective_position_value) * 100

        # Calculate progress towards covering entry/exit fees
        FEE_THRESHOLD_PERCENT = Decimal('0.135')
        fee_coverage_progress = Decimal('0')
        if funding_percentage > 0:
            fee_coverage_progress = (funding_percentage / FEE_THRESHOLD_PERCENT) * 100

        result = {
            "symbol": symbol,
            "position_amount": current_pos_amount,
            "position_notional": position_notional,
            "spot_balance": spot_balance,
            "effective_position_value": effective_position_value,
            "position_start_time": start_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            "funding_payments_count": len(funding_payments),
            "total_funding": total_funding,
            "funding_as_percentage_of_effective_value": funding_percentage,
            "fee_coverage_progress": fee_coverage_progress,
            "asset": funding_payments[0]['asset'] if funding_payments else 'USDT'
        }
        return result

    except Exception as e:
        print(f"Error fetching funding history: {e}")
        return None


async def main():
    """Main function to demonstrate the funding analysis."""
    init(autoreset=True) # Initialize colorama
    load_dotenv()

    api_user = os.getenv("API_USER")
    api_signer = os.getenv("API_SIGNER")
    api_private_key = os.getenv("API_PRIVATE_KEY")
    apiv1_public = os.getenv("APIV1_PUBLIC_KEY")
    apiv1_private = os.getenv("APIV1_PRIVATE_KEY")

    if not all([api_user, api_signer, api_private_key, apiv1_public, apiv1_private]):
        print("Please set all required API credentials in your .env file.")
        return

    manager = AsterApiManager(
        api_user=api_user,
        api_signer=api_signer,
        api_private_key=api_private_key,
        apiv1_public=apiv1_public,
        apiv1_private=apiv1_private
    )

    try:
        # --- Automatically detect and analyze delta-neutral positions ---
        print("Automatically detecting delta-neutral positions...")
        portfolio_data = await manager.get_comprehensive_portfolio_data()
        
        if not portfolio_data:
            print(f"{Fore.RED}Could not retrieve portfolio data.{Style.RESET_ALL}")
            return

        all_positions = portfolio_data.get('analyzed_positions', [])
        dn_positions = [p for p in all_positions if p.get('is_delta_neutral')]

        if not dn_positions:
            print(f"{Fore.YELLOW}No delta-neutral positions found to analyze.{Style.RESET_ALL}")
            return
            
        print(f"{Fore.GREEN}Found {len(dn_positions)} delta-neutral position(s): "
              f"{[p['symbol'] for p in dn_positions]}{Style.RESET_ALL}")

        for position in dn_positions:
            symbol_to_analyze = position['symbol']
            analysis_result = await calculate_funding_for_position(manager, symbol_to_analyze)

            if analysis_result:
                print(f"\n{Fore.YELLOW}--- Funding Analysis Result for {analysis_result['symbol']} ---")
                print(f"Perp Position: {analysis_result['position_amount']} (Notional: {analysis_result['position_notional']:.4f} USDT)")
                print(f"Spot Balance: {analysis_result['spot_balance']} {analysis_result['symbol'].replace('USDT','')}")
                print(f"Effective Position Value: {Fore.CYAN}{analysis_result['effective_position_value']:.4f} USDT")
                print(f"Position Start Time: {analysis_result['position_start_time']}")
                print("-" * 33)
                print(f"Funding Payments Found: {analysis_result['funding_payments_count']}")
                
                funding_color = Fore.GREEN if analysis_result['total_funding'] > 0 else Fore.RED
                print(f"Total Funding Fees Paid: {funding_color}{analysis_result['total_funding']:.8f} {analysis_result['asset']}{Style.RESET_ALL}")
                print(f"Funding as % of Effective Value: {analysis_result['funding_as_percentage_of_effective_value']:.4f}%")
                
                # Visual progress bar for fee coverage
                progress = min(Decimal('100'), analysis_result['fee_coverage_progress']) # Cap at 100%
                bar_length = 25
                filled_length = int(bar_length * progress / 100)
                bar = (Fore.GREEN + '#' * filled_length) + (Style.DIM + '-' * (bar_length - filled_length))
                print(f"Fee Coverage Progress: [{bar}{Style.RESET_ALL}] {analysis_result['fee_coverage_progress']:.2f}% of 0.135%")
                
                print(f"\n{Style.DIM}Notes:")
                print(f"{Style.DIM}- Effective Position Value = Spot Value + Abs(Perp Notional) + PnL.")
                print(f"{Style.DIM}- Fee Coverage Progress shows how close the funding has come to paying")
                print(f"{Style.DIM}  for the estimated 0.135% in total entry/exit trading fees.")
                print(f"{Style.DIM}- This analysis does not account for price spreads.")
                print(f"{Fore.YELLOW}-------------------------------------------")

    finally:
        await manager.close()

if __name__ == "__main__":
    asyncio.run(main())
