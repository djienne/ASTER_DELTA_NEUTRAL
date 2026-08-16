#!/usr/bin/env python3
"""
CLI command functions for the delta-neutral funding rate farming bot.
Contains standalone command-line interface functions.
"""

import os
import asyncio
from colorama import Fore, Style
from aster_api_manager import AsterApiManager
from ui_renderers import (
    render_funding_rates_table,
    render_perpetual_positions_table,
    render_portfolio_summary,
    render_delta_neutral_positions,
    render_other_positions,
    render_spot_balances,
    render_funding_analysis_results
)


async def check_available_pairs():
    """CLI function to check available pairs that have both spot and perp markets."""
    print(Fore.CYAN + "Checking available delta-neutral pairs..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        available_pairs = await api_manager.discover_delta_neutral_pairs()

        if not available_pairs:
            print(Fore.YELLOW + "No symbols are currently available in both spot and perpetual markets." + Style.RESET_ALL)
            return

        print(Fore.GREEN + f"\nFound {len(available_pairs)} pairs available for delta-neutral trading:\n" + Style.RESET_ALL)

        # Display in columns for better readability
        pairs_per_row = 4
        for i in range(0, len(available_pairs), pairs_per_row):
            row_pairs = available_pairs[i:i+pairs_per_row]
            formatted_pairs = [f"{pair:<12}" for pair in row_pairs]
            print("  " + "".join(formatted_pairs))

        print(f"\n{Fore.CYAN}Total: {len(available_pairs)} pairs{Style.RESET_ALL}")

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to check available pairs: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def check_current_positions():
    """CLI function to show current delta-neutral positions."""
    print(Fore.CYAN + "Analyzing current positions..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Fetching comprehensive portfolio data from Aster DEX...")
        portfolio_data = await api_manager.get_comprehensive_portfolio_data()

        if not portfolio_data:
            print(Fore.YELLOW + "No portfolio data available." + Style.RESET_ALL)
            return

        # Extract data from the comprehensive payload
        all_positions = portfolio_data.get('analyzed_positions', [])
        spot_balances = portfolio_data.get('spot_balances', [])
        perp_account_info = portfolio_data.get('perp_account_info', {})
        raw_perp_positions = portfolio_data.get('raw_perp_positions', [])
        delta_neutral_positions = [p for p in all_positions if p.get('is_delta_neutral')]
        other_positions = [p for p in all_positions if not p.get('is_delta_neutral')]

        # Calculate portfolio totals
        spot_usdt_balance = next((float(b.get('free', 0)) for b in spot_balances if b.get('asset') == 'USDT'), 0.0)
        assets = perp_account_info.get('assets', [])
        perp_usdt = next((float(a.get('walletBalance', 0)) for a in assets if a.get('asset') == 'USDT'), 0.0)
        perp_usdc = next((float(a.get('walletBalance', 0)) for a in assets if a.get('asset') == 'USDC'), 0.0)
        perp_usdf = next((float(a.get('walletBalance', 0)) for a in assets if a.get('asset') == 'USDF'), 0.0)

        # Display portfolio summary
        print(Fore.GREEN + f"\n{'='*70}")
        print("PORTFOLIO SUMMARY")
        print(f"{'='*70}" + Style.RESET_ALL)
        render_portfolio_summary(perp_usdt, perp_usdc, perp_usdf, spot_usdt_balance, title="", indent="")

        # Display delta-neutral positions
        render_delta_neutral_positions(all_positions, raw_perp_positions, title=f"DELTA-NEUTRAL POSITIONS ({len(delta_neutral_positions)} found)")

        # Display other positions
        if other_positions:
            render_other_positions(all_positions, title=f"OTHER HOLDINGS ({len(other_positions)} found)")

        # Summary
        print(Fore.GREEN + f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}" + Style.RESET_ALL)
        print(f"Delta-Neutral Positions: {len(delta_neutral_positions)}")
        print(f"Other Holdings:          {len(other_positions)}")
        print(f"Total Positions:         {len(all_positions)}")

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to analyze positions: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def check_spot_assets():
    """CLI function to show current spot asset balances."""
    print(Fore.CYAN + "Fetching spot asset balances..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Fetching comprehensive portfolio data from Aster DEX...")
        portfolio_data = await api_manager.get_comprehensive_portfolio_data()

        if not portfolio_data or 'spot_balances' not in portfolio_data:
            print(Fore.YELLOW + "No spot balance data available." + Style.RESET_ALL)
            return

        spot_balances = portfolio_data['spot_balances']
        render_spot_balances(spot_balances, title="Spot Balances (Excluding Stables)")

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to fetch spot assets: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def check_perpetual_positions():
    """CLI function to show current perpetual positions with detailed PnL analysis."""
    print(Fore.CYAN + "Fetching perpetual positions..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Fetching comprehensive portfolio data from Aster DEX...")
        portfolio_data = await api_manager.get_comprehensive_portfolio_data()

        if not portfolio_data or 'raw_perp_positions' not in portfolio_data:
            print(Fore.YELLOW + "No perpetual position data available." + Style.RESET_ALL)
            return

        active_positions = portfolio_data['raw_perp_positions']
        perp_account_info = portfolio_data['perp_account_info']

        if not active_positions:
            print(Fore.YELLOW + "No active perpetual positions found." + Style.RESET_ALL)
            return

        # Get account balance information
        assets = perp_account_info.get('assets', [])
        total_wallet_balance = sum(float(a.get('walletBalance', 0)) for a in assets)
        total_unrealized_pnl = sum(float(p.get('unrealizedProfit', 0)) for p in active_positions)
        total_margin_balance = total_wallet_balance + total_unrealized_pnl

        # Display results
        print(Fore.GREEN + f"\n{'='*95}")
        print("PERPETUAL POSITIONS")
        print(f"{'='*95}" + Style.RESET_ALL)

        # Account summary
        print(Fore.GREEN + f"\nACCOUNT SUMMARY" + Style.RESET_ALL)
        print(f"Total Wallet Balance:    ${total_wallet_balance:>12,.2f}")
        print(f"Total Unrealized PnL:    ${total_unrealized_pnl:>12,.2f}")
        print(f"Total Margin Balance:    ${total_margin_balance:>12,.2f}")
        print(f"Active Positions:        {len(active_positions):>12}")

        # Use common function to render the positions table
        render_perpetual_positions_table(active_positions, title="\nPOSITION DETAILS", show_summary=True)

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to fetch perpetual positions: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def check_funding_rates():
    """CLI function to check funding rates for all available pairs."""
    print(Fore.CYAN + "Fetching funding rates for delta-neutral pairs..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        funding_data = await api_manager.get_all_funding_rates()

        if not funding_data:
            print(Fore.YELLOW + "No funding rate data available or no delta-neutral pairs found." + Style.RESET_ALL)
            return

        # Use common function to render the table
        render_funding_rates_table(funding_data)

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to fetch funding rates: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def check_portfolio_health():
    """CLI function to perform portfolio health check."""
    print(Fore.CYAN + "Performing portfolio health check..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Fetching current position data...")

        # Use API manager's health check method
        health_issues, critical_issues, dn_positions_count, position_pnl_data = await api_manager.perform_health_check_analysis()

        if dn_positions_count == 0:
            print(Fore.YELLOW + "No delta-neutral positions found to check." + Style.RESET_ALL)
            return

        # Display results
        print(Fore.GREEN + f"\n{'='*70}")
        print("PORTFOLIO HEALTH CHECK RESULTS")
        print(f"{'='*70}" + Style.RESET_ALL)

        print(Fore.CYAN + "\nHealth Check Criteria:" + Style.RESET_ALL)
        print(f"  {Fore.GREEN}Spot USD > $10{Style.RESET_ALL}: Healthy")
        print(f"  {Fore.YELLOW}Spot USD < $10{Style.RESET_ALL}: Warning (rebalancing advised)")
        print(f"  {Fore.RED}Spot USD < $5{Style.RESET_ALL}: Critical (impossible to close)")
        print(f"  {Fore.YELLOW}Short PnL < -25%{Style.RESET_ALL}: Warning")
        print(f"  {Fore.RED}Short PnL < -50%{Style.RESET_ALL}: Critical")

        if critical_issues:
            print(Fore.RED + "\nCRITICAL ISSUES:" + Style.RESET_ALL)
            for issue in critical_issues:
                print(Fore.RED + f"  {issue}" + Style.RESET_ALL)

        if health_issues:
            print(Fore.YELLOW + "\nWARNINGS:" + Style.RESET_ALL)
            for issue in health_issues:
                print(Fore.YELLOW + f"  {issue}" + Style.RESET_ALL)

        # Display position PnL summary
        if position_pnl_data:
            print(Fore.CYAN + "\nPOSITION PnL SUMMARY:" + Style.RESET_ALL)
            header = f"{'Symbol':<12} {'Value':<12} {'Imbalance':<10} {'PnL %':<10}"
            print(header)
            print("-" * len(header))

            for pos_data in position_pnl_data:
                symbol = pos_data['symbol']
                value_usd = pos_data['position_value_usd']
                spot_value_usd = pos_data['spot_value_usd']
                imbalance_pct = pos_data['imbalance_pct']
                pnl_pct = pos_data['pnl_pct']

                # Color code based on spot value thresholds
                if spot_value_usd < 5:
                    row_color = Fore.RED  # Critical
                elif spot_value_usd < 10:
                    row_color = Fore.YELLOW  # Warning
                else:
                    row_color = Fore.GREEN  # Healthy

                # Color code PnL based on performance
                if pnl_pct is not None:
                    if pnl_pct >= -25:  # Good PnL (above -25%)
                        pnl_color = Fore.GREEN
                        pnl_str = f"{pnl_pct:+.2f}%"
                    else:  # Bad PnL (below -25%, already in warnings/critical)
                        pnl_color = Fore.RED
                        pnl_str = f"{pnl_pct:+.2f}%"
                else:
                    pnl_color = Fore.YELLOW
                    pnl_str = "N/A"

                print(f"{row_color}{symbol:<12} ${value_usd:<11.2f} {imbalance_pct:<9.2f}% {pnl_color}{pnl_str:<10}{Style.RESET_ALL}")

        if not critical_issues and not health_issues:
            print(Fore.GREEN + "\nALL CLEAR: No health issues detected with your positions." + Style.RESET_ALL)
        else:
            print(f"\n{Fore.CYAN}RECOMMENDATION:{Style.RESET_ALL}")
            if critical_issues:
                print(f"{Fore.RED}  URGENT: Critical issues detected. Consider immediate rebalancing or position closure.{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}  Consider rebalancing your positions to address the warnings above.{Style.RESET_ALL}")
            print(f"{Fore.CYAN}  Run: python delta_neutral_bot.py --rebalance{Style.RESET_ALL}")

        # Summary
        print(f"\n{Fore.CYAN}SUMMARY:")
        print(f"  Delta-Neutral Positions Checked: {dn_positions_count}")
        print(f"  Critical Issues Found:           {len(critical_issues)}")
        print(f"  Warnings Found:                  {len(health_issues)}")
        print(f"  Health Status:                   {'CRITICAL' if critical_issues else 'WARNING' if health_issues else 'HEALTHY'}{Style.RESET_ALL}")

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to perform health check: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def rebalance_usdt_cli():
    """CLI function to rebalance USDT between spot and perpetual accounts 50/50."""
    print(Fore.CYAN + "Rebalancing USDT between spot and perpetual accounts..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        print("Analyzing current USDT distribution...")
        result = await api_manager.rebalance_usdt_50_50()

        # Display current state
        print("\n" + Fore.CYAN + "=== USDT BALANCE ANALYSIS ===" + Style.RESET_ALL)
        print(f"Current Spot USDT:     ${result['current_spot_usdt']:>10.2f}")
        print(f"Current Perp USDT:     ${result['current_perp_usdt']:>10.2f}")
        print(f"Total Available USDT:  ${result['total_usdt']:>10.2f}")
        print(f"Target Each (50/50):   ${result['target_each']:>10.2f}")

        if not result['transfer_needed']:
            print(Fore.GREEN + "\nALREADY BALANCED: Your USDT is already distributed 50/50 (within $1)" + Style.RESET_ALL)
            return

        # Show transfer details and ask for confirmation
        print(f"\nTransfer Required:")
        print(f"  Amount:     ${result['transfer_amount']:.2f}")
        print(f"  Direction:  {result['transfer_direction'].replace('_', ' -> ')}")

        print(Fore.YELLOW + f"\nConfirm transfer of ${result['transfer_amount']:.2f} USDT?" + Style.RESET_ALL)
        confirmation = input("Type 'yes' to proceed: ").strip().lower()

        if confirmation != 'yes':
            print("Transfer cancelled.")
            return

        # Execute the transfer
        print("Executing transfer...")
        transfer_result = await api_manager.transfer_between_spot_and_perp(
            'USDT', result['transfer_amount'], result['transfer_direction']
        )

        if transfer_result and transfer_result.get('status') == 'SUCCESS':
            print(Fore.GREEN + f"[SUCCESS] Transfer completed successfully!" + Style.RESET_ALL)
            print(f"Transaction ID: {transfer_result.get('tranId', 'N/A')}")
        else:
            print(Fore.RED + f"Transfer failed: {transfer_result}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to rebalance USDT: {e}" + Style.RESET_ALL)
    finally:
        await api_manager.close()


async def open_position_cli(symbol: str, capital: float, auto_confirm: bool = False):
    """CLI function to open a new delta-neutral position."""
    print(Fore.CYAN + f"Attempting to open a ${capital:.2f} USD position for {symbol}..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        # 1. Perform Dry Run to get trade details
        print("Calculating trade details (dry run)...")
        trade_plan = await api_manager.prepare_and_execute_dn_position(symbol, capital, dry_run=True)

        if not trade_plan.get('success'):
            error_message = trade_plan.get('message', 'No error message provided.')
            print(f"{Fore.RED}Error: {error_message}{Style.RESET_ALL}")
            return

        # 2. Show Confirmation
        details = trade_plan['details']
        base_asset = symbol.replace('USDT', '')
        print("\n" + Fore.YELLOW + "--- TRADE PLAN (ADJUSTED FOR LOT SIZE) ---" + Style.RESET_ALL)
        print(f"Symbol: {details['symbol']}, Initial Capital: ${details['capital_to_deploy']:.2f}")
        print(f"Action: Open delta-neutral position via MARKET orders at 1x leverage.")
        print(Fore.MAGENTA + f"Perp Lot Size Filter (stepSize): {details['lot_size_filter'].get('stepSize') if details['lot_size_filter'] else 'N/A'}" + Style.RESET_ALL)
        print(f"Final Perp Qty:   {details['final_perp_qty']:.8f}")
        print("-"*40)
        if (details['existing_spot_quantity'] * details['spot_price']) > 0:
            print(Fore.CYAN + f"Utilizing Existing Spot: {details['existing_spot_quantity']:.8f} {base_asset} (${(details['existing_spot_quantity'] * details['spot_price']):.2f})" + Style.RESET_ALL)
        print(f"Spot BUY Qty: {details['spot_qty_to_buy']:.8f} (${details['spot_capital_to_buy']:.2f})")
        print(f"Perp SELL Qty: {details['final_perp_qty']:.8f} (${details['final_perp_qty'] * details['spot_price']:.2f})")

        # 3. Confirm and Execute
        if not auto_confirm:
            confirm = input("\nPress Enter to confirm (or enter 'x' to cancel): ")
            if confirm.strip().lower() == 'x' or confirm.strip() != '':
                print("Trade execution cancelled by user.")
                return

        print("\nExecuting trades...")
        exec_result = await api_manager.prepare_and_execute_dn_position(symbol, capital, dry_run=False)

        if exec_result.get('success'):
            print(f"{Fore.GREEN}{exec_result.get('message')}{Style.RESET_ALL}")
            print(f"Spot Order: {exec_result.get('spot_order')}")
            print(f"Perp Order: {exec_result.get('perp_order')}")
        else:
            print(f"{Fore.RED}Execution failed: {exec_result.get('message')}{Style.RESET_ALL}")

    finally:
        await api_manager.close()


async def close_position_cli(symbol: str, auto_confirm: bool = False):
    """CLI function to close a delta-neutral position."""
    print(Fore.CYAN + f"Attempting to close position for {symbol}..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        if not auto_confirm:
            confirm = input(f"Are you sure you want to close the position for {symbol}? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("Operation cancelled.")
                return

        print(f"Executing closing trades for {symbol}...")
        close_result = await api_manager.execute_dn_position_close(symbol)

        if close_result.get('success'):
            print(f"{Fore.GREEN}{close_result.get('message')}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Failed to close position: {close_result.get('message')}{Style.RESET_ALL}")

    finally:
        await api_manager.close()


async def analyze_fundings_cli(symbol: str):
    """CLI function for non-interactive funding analysis."""
    print(Fore.CYAN + f"Analyzing paid fundings for {symbol}..." + Style.RESET_ALL)

    api_manager = AsterApiManager(
        api_user=os.getenv('API_USER'),
        api_signer=os.getenv('API_SIGNER'),
        api_private_key=os.getenv('API_PRIVATE_KEY'),
        apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
        apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
    )

    try:
        analysis_result = await api_manager.perform_funding_analysis(symbol)
        if analysis_result:
            render_funding_analysis_results(analysis_result)
        else:
            print(f"{Fore.RED}Could not perform analysis for {symbol}.{Style.RESET_ALL}")
    finally:
        await api_manager.close()