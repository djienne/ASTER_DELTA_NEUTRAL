#!/usr/bin/env python3
"""
Terminal-based UI and orchestrator for the delta-neutral funding rate farming bot.
"""

import asyncio
import os
import sys
import argparse
from datetime import datetime
from collections import deque
from dotenv import load_dotenv
from colorama import init, Fore, Style
import math
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple

# Platform-specific imports for non-blocking input
try:
    import msvcrt
except ImportError:
    import termios
    import tty

from aster_api_manager import AsterApiManager
from strategy_logic import DeltaNeutralLogic
from utils import truncate

# Import rendering functions from ui_renderers
from ui_renderers import (
    render_funding_rates_table,
    render_perpetual_positions_table,
    render_portfolio_summary,
    render_delta_neutral_positions,
    render_spot_balances,
    render_other_positions,
    render_opportunities,
    render_funding_analysis_results
)

# Import CLI command functions from cli_commands
from cli_commands import (
    check_available_pairs,
    check_current_positions,
    check_spot_assets,
    check_perpetual_positions,
    check_funding_rates,
    check_portfolio_health,
    rebalance_usdt_cli,
    open_position_cli,
    close_position_cli,
    analyze_fundings_cli
)

# Load environment variables from .env file
load_dotenv()

# Initialize colorama for cross-platform colored text
init()

class DashboardApp:
    """
    The main application class that orchestrates the API manager, strategy logic,
    and terminal-based user interface.
    """

    def __init__(self, is_test_run=False):
        """Initialize the application, API manager, and initial state."""
        self.api_manager = AsterApiManager(
            api_user=os.getenv('API_USER'),
            api_signer=os.getenv('API_SIGNER'),
            api_private_key=os.getenv('API_PRIVATE_KEY'),
            apiv1_public=os.getenv('APIV1_PUBLIC_KEY'),
            apiv1_private=os.getenv('APIV1_PRIVATE_KEY')
        )
        self.logic = DeltaNeutralLogic()
        self.running = True
        self.refresh_interval = 30  # seconds
        self.is_test_run = is_test_run
        self.interactive_mode = False  # Flag to pause auto-refresh during user interactions
        self.is_standalone_workflow = False

        # State variables to hold dashboard data
        self.last_updated = "Never"
        self.portfolio_value = 0.0
        self.positions = []
        self.spot_balances = []
        self.opportunities = []
        self.log_messages = deque(maxlen=5)  # Store last 5 log messages
        self.perp_margin_balance = 0.0
        self.perp_usdt_balance = 0.0
        self.perp_usdc_balance = 0.0
        self.perp_usdf_balance = 0.0
        self.spot_usdt_balance = 0.0
        self.raw_perp_positions = []
        self.funding_rate_cache = None  # To hold on-demand funding rate scan results

    async def run(self):
        """Main entry point to start the application."""
        self._add_log("Application started. Initializing and performing first data fetch...")

        try:
            # Perform an initial fetch to populate caches before the user can interact
            await self._fetch_and_update_data()
            self._render_dashboard()
        except Exception as e:
            self._add_log(f"{Fore.RED}Initial data fetch failed: {e}{Style.RESET_ALL}")
            self.running = False # Stop if the initial fetch fails

        # Now start the main loop and input handler if the initial fetch was successful
        if self.running:
            main_loop_task = asyncio.create_task(self._main_loop())

            if not self.is_test_run:
                input_handler_task = asyncio.create_task(self._handle_user_input())
                tasks = [main_loop_task, input_handler_task]
            else:
                # For test run, we don't need the main loop, just the initial fetch
                tasks = [main_loop_task]

            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                self._add_log("Shutdown signal received.")
            finally:
                self._add_log("Closing API connections...")
                await self.api_manager.close()
                if not self.is_test_run:
                    self._add_log("Shutdown complete.")
                    print(Fore.YELLOW + "Application has been shut down." + Style.RESET_ALL)

    async def _main_loop(self):
        """The core loop that periodically fetches data and refreshes the dashboard."""
        # The first fetch is already done by run(), so we start with a sleep.
        while self.running:
            await asyncio.sleep(self.refresh_interval)

            # Skip refresh if in interactive mode (user is in a workflow)
            if self.interactive_mode:
                continue

            try:
                await self._fetch_and_update_data()
                self._render_dashboard()

                if self.is_test_run:
                    self._add_log("Test run complete. Exiting.")
                    print("\n" + Fore.GREEN + "Test run successful. Dashboard rendered once." + Style.RESET_ALL)
                    self.running = False
                    await asyncio.sleep(1)
                    continue

            except Exception as e:
                self._add_log(f"{Fore.RED}ERROR in main loop: {e}{Style.RESET_ALL}")
                if self.is_test_run:
                    self.running = False # Exit on error in test mode


    async def _fetch_and_update_data(self):
        """Fetch all necessary data from the API manager and update state."""
        self._add_log("Fetching latest portfolio data from Aster DEX...")

        portfolio_data = await self.api_manager.get_comprehensive_portfolio_data()

        if not portfolio_data:
            self._add_log(f"{Fore.RED}Failed to fetch comprehensive portfolio data.{Style.RESET_ALL}")
            return

        # Assign data from the comprehensive payload to the dashboard state
        self.positions = portfolio_data.get('analyzed_positions', [])
        self.spot_balances = portfolio_data.get('spot_balances', [])
        self.raw_perp_positions = portfolio_data.get('raw_perp_positions', [])
        perp_account_info = portfolio_data.get('perp_account_info', {})

        # Extract summary values from the fetched data
        self.spot_usdt_balance = next((float(b.get('free', 0)) for b in self.spot_balances if b.get('asset') == 'USDT'), 0.0)

        assets = perp_account_info.get('assets', [])
        self.perp_usdt_balance = next((float(a.get('walletBalance', 0)) for a in assets if a.get('asset') == 'USDT'), 0.0)
        self.perp_usdc_balance = next((float(a.get('walletBalance', 0)) for a in assets if a.get('asset') == 'USDC'), 0.0)
        self.perp_usdf_balance = next((float(a.get('walletBalance', 0)) for a in assets if a.get('asset') == 'USDF'), 0.0)
        self.perp_margin_balance = self.perp_usdt_balance + self.perp_usdc_balance + self.perp_usdf_balance

        # Fetch available opportunities for new positions
        try:
            all_opportunities = await self.api_manager.discover_delta_neutral_pairs()
            existing_dn_symbols = {p.get('symbol') for p in self.positions if p.get('is_delta_neutral')}
            self.opportunities = [opp for opp in all_opportunities if opp not in existing_dn_symbols]
        except Exception as e:
            self._add_log(f"Could not fetch opportunities: {e}")
            self.opportunities = []

        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._add_log("Data refresh complete.")

    def _render_dashboard(self):
        """Clears the screen and renders the entire dashboard UI."""
        # Skip rendering if in interactive mode to avoid clearing user prompts
        if self.interactive_mode:
            return

        os.system('cls' if os.name == 'nt' else 'clear')
        print(Style.BRIGHT + Fore.CYAN + "=" * 80)
        print(" ASTER DELTA-NEUTRAL FUNDING RATE FARMING BOT ".center(80))
        print(f" Last Updated: {self.last_updated} ".center(80))
        print("=" * 80 + Style.RESET_ALL)

        # --- Render sections here ---
        self._render_portfolio_summary()
        self._render_all_perp_positions()
        self._render_delta_neutral_positions()
        self._render_other_positions()
        self._render_spot_balances()
        self._render_opportunities()
        self._render_funding_rate_scan() # Render the on-demand scan if data is present
        self._render_logs()
        self._render_menu()

    def _get_char(self):
        """Gets a single character from standard input."""
        try: # Windows
            return msvcrt.getch().decode()
        except NameError: # Not Windows
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch

    async def _handle_user_input(self):
        """Handles user input in a non-blocking way."""
        loop = asyncio.get_event_loop()
        while self.running:
            command = ''
            try:
                command = await loop.run_in_executor(None, self._get_char)
            except (KeyboardInterrupt, asyncio.CancelledError):
                # On Windows, Ctrl+C raises KeyboardInterrupt here.
                # Treat it as a 'q' command for graceful shutdown.
                command = 'q'
            except Exception as e:
                self._add_log(f"{Fore.RED}Input Error: {e}{Style.RESET_ALL}")
                continue

            # On non-Windows, Ctrl+C is read as the '\x03' character.
            if command == '\x03':
                command = 'q'

            command = command.strip().lower()

            if command == 'q':
                if self.running: # Ensure shutdown logic runs only once
                    self._add_log("Shutdown key pressed. Exiting...")
                    self.running = False
                    # Cancel all running tasks to allow for graceful shutdown
                    for task in asyncio.all_tasks():
                        task.cancel()
            elif command == 'r':
                self._add_log("Manual refresh requested.")
                await self._fetch_and_update_data()
                self._render_dashboard()
            elif command == 'o':
                self.interactive_mode = True
                await self._open_position_workflow()
                self.interactive_mode = False
                self._render_dashboard()
            elif command == 'c':
                self.interactive_mode = True
                await self._close_position_workflow()
                self.interactive_mode = False
                self._render_dashboard()
            elif command == 'f':
                self.interactive_mode = True
                await self._show_funding_rates_workflow()
                self.interactive_mode = False
                self._render_dashboard()
            elif command == 'h':
                self.interactive_mode = True
                await self._perform_health_check()
                self.interactive_mode = False
                self._render_dashboard()
            elif command == 'b':
                self.interactive_mode = True
                await self._rebalance_usdt_workflow()
                self.interactive_mode = False
                self._render_dashboard()
            elif command == 'a':
                self.interactive_mode = True
                await self._analyze_funding_workflow()
                self.interactive_mode = False
                self._render_dashboard()

    def _add_log(self, message: str):
        """Adds a timestamped message to the log queue."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_messages.append(f"[{timestamp}] {message}")

    async def _get_user_input(self, prompt: str) -> str:
        """Gets user input in a non-blocking way."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt)

    async def _open_position_workflow(self):
        """Guides the user through opening a new delta-neutral position."""
        self._add_log("Starting 'Open Position' workflow...")
        try:
            # 1. Select Symbol
            available_opportunities = self.opportunities
            if not available_opportunities:
                self._add_log(f"{Fore.YELLOW}No new opportunities available to open a position.{Style.RESET_ALL}")
                return

            print("\n" + Fore.CYAN + "Please select a symbol to open a position (or enter 'x' to cancel):" + Style.RESET_ALL)
            for i, opp in enumerate(available_opportunities):
                print(f"[{i+1}] {opp}")

            selection = await self._get_user_input("Enter the number of the symbol: ")
            if selection.strip().lower() == 'x': raise KeyboardInterrupt
            selected_symbol = available_opportunities[int(selection) - 1]

            # 2. Get Capital Input & Calculate Minimums
            perp_balance = self.perp_margin_balance
            spot_balance = self.spot_usdt_balance
            max_capital = min(spot_balance, perp_balance)

            # Fetch filters to calculate true minimum notional
            min_notional_filter, lot_size_filter, spot_price_data = await asyncio.gather(
                self.api_manager.get_perp_symbol_filter(selected_symbol, 'MIN_NOTIONAL'),
                self.api_manager.get_perp_symbol_filter(selected_symbol, 'LOT_SIZE'),
                self.api_manager.get_spot_book_ticker(selected_symbol)
            )
            spot_price = float(spot_price_data['bidPrice'])

            min_notional_from_filter = float(min_notional_filter.get('notional', 0)) if min_notional_filter else 0.0
            min_qty_from_filter = float(lot_size_filter.get('minQty', 0)) if lot_size_filter else 0.0
            min_notional_from_qty = min_qty_from_filter * spot_price
            true_min_notional = max(min_notional_from_filter, min_notional_from_qty)

            # Add a small buffer and round up for a clean user prompt
            display_min_notional = math.ceil(true_min_notional + 1.0)

            prompt = f"Enter USD capital for {selected_symbol} (min: ${display_min_notional:.2f}, max: ${max_capital:.2f}, or 'x' to cancel): "
            capital_str = await self._get_user_input(prompt)
            if capital_str.strip().lower() == 'x': raise KeyboardInterrupt
            capital_to_deploy = float(capital_str)

            if capital_to_deploy > max_capital or capital_to_deploy < true_min_notional:
                self._add_log(f"{Fore.RED}Error: Invalid amount. Please enter a value between ${true_min_notional:.2f} and ${max_capital:.2f}.{Style.RESET_ALL}")
                return

            # 3. Perform Dry Run to get trade details
            self._add_log("Calculating trade details (dry run)...")
            trade_plan = await self.api_manager.prepare_and_execute_dn_position(selected_symbol, capital_to_deploy, dry_run=True)

            if not trade_plan.get('success'):
                error_message = f"{Fore.RED}Could not create trade plan: {trade_plan.get('message')}{Style.RESET_ALL}"
                self._add_log(error_message)
                if self.is_standalone_workflow:
                    print(error_message)
                return

            # 4. Show Confirmation
            details = trade_plan['details']
            base_asset = selected_symbol.replace('USDT', '')
            print("\n" + Fore.YELLOW + "--- CONFIRMATION (ADJUSTED FOR LOT SIZE) ---" + Style.RESET_ALL)
            print(f"Symbol: {details['symbol']}, Initial Capital: ${details['capital_to_deploy']:.2f}")
            print(f"Action: Open delta-neutral position via MARKET orders at 1x leverage.")
            print(Fore.MAGENTA + f"Perp Lot Size Filter (stepSize): {details['lot_size_filter'].get('stepSize') if details['lot_size_filter'] else 'N/A'}" + Style.RESET_ALL)
            print(f"Ideal Perp Qty:   {details['ideal_perp_qty']:.8f}")
            print(f"Final Perp Qty:   {details['final_perp_qty']:.8f}")
            print("-"*40)
            if (details['existing_spot_quantity'] * details['spot_price']) > 0:
                print(Fore.CYAN + f"Utilizing Existing Spot: {details['existing_spot_quantity']:.8f} {base_asset} (${(details['existing_spot_quantity'] * details['spot_price']):.2f})" + Style.RESET_ALL)
            print(f"Spot BUY Qty: {details['spot_qty_to_buy']:.8f} (${details['spot_capital_to_buy']:.2f})")
            print(f"Perp SELL Qty: {details['final_perp_qty']:.8f} (${details['final_perp_qty'] * details['spot_price']:.2f})")

            confirm = await self._get_user_input("Press Enter to confirm (or enter 'x' to cancel): ")
            if confirm.strip().lower() == 'x' or confirm.strip() != '':
                self._add_log("Trade execution cancelled by user.")
                return

            # 5. Execute Trade
            self._add_log("Executing trades...")
            exec_result = await self.api_manager.prepare_and_execute_dn_position(selected_symbol, capital_to_deploy, dry_run=False)

            if exec_result.get('success'):
                success_message = f"{Fore.GREEN}{exec_result.get('message')}{Style.RESET_ALL}"
                self._add_log(success_message)
                if self.is_standalone_workflow:
                    print(success_message)
            else:
                error_message = f"{Fore.RED}Execution failed: {exec_result.get('message')}{Style.RESET_ALL}"
                self._add_log(error_message)
                if self.is_standalone_workflow:
                    print(error_message)

            # Wait and refresh data
            self._add_log("Refreshing data to show new position...")
            await asyncio.sleep(1)
            await self._fetch_and_update_data()

        except (ValueError, IndexError):
            self._add_log(f"{Fore.RED}Invalid selection.{Style.RESET_ALL}")
        except KeyboardInterrupt:
            self._add_log("Operation cancelled by user.")

    async def _close_position_workflow(self):
        """Guides the user through closing an existing delta-neutral position."""
        self._add_log("Starting 'Close Position' workflow...")
        dn_positions = [p for p in self.positions if p.get('is_delta_neutral')]

        if not dn_positions:
            message = f"{Fore.YELLOW}No delta-neutral positions available to close.{Style.RESET_ALL}"
            self._add_log(message)
            if self.is_standalone_workflow:
                print(message)
            return

        try:
            # 1. Ask user to select a position
            print("\n" + Fore.CYAN + "Select a delta-neutral position to close (or 'x' to cancel):" + Style.RESET_ALL)
            for i, pos in enumerate(dn_positions):
                print(f"[{i+1}] {pos.get('symbol', 'N/A')}")

            selection = await self._get_user_input("Enter the number of the position: ")
            if selection.strip().lower() == 'x': raise KeyboardInterrupt

            selected_position = dn_positions[int(selection) - 1]
            symbol_to_close = selected_position.get('symbol')

            # 2. Show confirmation
            print("\n" + Fore.YELLOW + "--- CONFIRMATION ---" + Style.RESET_ALL)
            print(f"Symbol: {symbol_to_close}")
            print(f"Spot Balance: {selected_position.get('spot_balance', 0):.6f}")
            print(f"Perp Position: {selected_position.get('perp_position', 0):.6f}")

            confirm = await self._get_user_input(f"Press Enter to confirm closing the {symbol_to_close} position (or 'x' to cancel): ")
            if confirm.strip().lower() == 'x' or confirm.strip() != '':
                self._add_log("Close position cancelled by user.")
                return

            # 3. Execute closing trades via the centralized method
            self._add_log(f"Closing position for {symbol_to_close}...")
            close_result = await self.api_manager.execute_dn_position_close(symbol_to_close)

            if close_result.get('success'):
                success_message = f"{Fore.GREEN}{close_result.get('message')}{Style.RESET_ALL}"
                self._add_log(success_message)
                if self.is_standalone_workflow:
                    print(success_message)
            else:
                error_message = f"{Fore.RED}Failed to close position: {close_result.get('message')}{Style.RESET_ALL}"
                self._add_log(error_message)
                if self.is_standalone_workflow:
                    print(error_message)

            # Wait 1 second then refresh data to show the closed position
            self._add_log("Refreshing data to show position closure...")
            await asyncio.sleep(1)
            await self._fetch_and_update_data()

        except (ValueError, IndexError):
            self._add_log(f"{Fore.RED}Invalid selection.{Style.RESET_ALL}")
        except KeyboardInterrupt:
            self._add_log("Operation cancelled by user.")

    async def _show_funding_rates_workflow(self):
        """Fetches and displays funding rates for top perpetual contracts."""
        self._add_log("Fetching top funding rates for delta-neutral pairs...")
        try:
            self.funding_rate_cache = await self.api_manager.get_all_funding_rates()
            self._add_log("Funding rate scan complete.")

            # Display the results to the user
            if self.funding_rate_cache:
                print(f"\n{Fore.GREEN}=== FUNDING RATES SCAN RESULTS ==={Style.RESET_ALL}")
                render_funding_rates_table(self.funding_rate_cache)
                print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
                await self._get_user_input("")
            else:
                print(f"\n{Fore.YELLOW}No funding rate data available.{Style.RESET_ALL}")
                print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
                await self._get_user_input("")

        except Exception as e:
            self._add_log(f"{Fore.RED}Error during funding rate scan: {e}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
            await self._get_user_input("")

    async def _rebalance_usdt_workflow(self):
        """Guides the user through rebalancing USDT between spot and perpetual accounts."""
        self._add_log("Starting USDT rebalance workflow...")

        try:
            # Get current balances and calculate rebalance need
            self._add_log("Analyzing current USDT distribution...")
            result = await self.api_manager.rebalance_usdt_50_50()

            # Display current state
            print("\n" + Fore.CYAN + "=== USDT BALANCE ANALYSIS ===" + Style.RESET_ALL)
            print(f"Current Spot USDT:     ${result['current_spot_usdt']:>10.2f}")
            print(f"Current Perp USDT:     ${result['current_perp_usdt']:>10.2f}")
            print(f"Total Available USDT:  ${result['total_usdt']:>10.2f}")
            print(f"Target Each (50/50):   ${result['target_each']:>10.2f}")

            if not result['transfer_needed']:
                print(Fore.GREEN + "\n✓ ALREADY BALANCED: Your USDT is already distributed 50/50 (within $1)" + Style.RESET_ALL)
                print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
                await self._get_user_input("")
                return

            # Show transfer details
            print(f"\nTransfer Required:")
            print(f"  Amount:     ${result['transfer_amount']:.2f}")
            print(f"  Direction:  {result['transfer_direction'].replace('_', ' → ')}")

            if result['transfer_direction'] == 'SPOT_TO_PERP':
                print(f"  Action:     Move ${result['transfer_amount']:.2f} from Spot to Perpetual")
            else:
                print(f"  Action:     Move ${result['transfer_amount']:.2f} from Perpetual to Spot")

            # Ask for confirmation
            print("\n" + Fore.YELLOW + "--- CONFIRMATION ---" + Style.RESET_ALL)
            print(f"Execute USDT rebalance transfer?")
            print(f"This will move ${result['transfer_amount']:.2f} USDT between your accounts.")

            confirm = await self._get_user_input("Press Enter to confirm transfer (or 'x' to cancel): ")
            if confirm.strip().lower() == 'x' or confirm.strip() != '':
                self._add_log("USDT rebalance cancelled by user.")
                return

            # Execute the rebalance (which includes the transfer)
            self._add_log("Executing USDT rebalance transfer...")
            final_result = await self.api_manager.rebalance_usdt_50_50()

            if final_result.get('transfer_result'):
                transfer_result = final_result['transfer_result']
                if transfer_result.get('status') == 'SUCCESS':
                    self._add_log(f"{Fore.GREEN}USDT rebalance completed successfully!{Style.RESET_ALL}")
                    print(f"\n{Fore.GREEN}✓ TRANSFER SUCCESSFUL{Style.RESET_ALL}")
                    print(f"Transaction ID: {transfer_result.get('tranId')}")
                    print(f"Status: {transfer_result.get('status')}")
                else:
                    self._add_log(f"{Fore.RED}Transfer failed: {transfer_result}{Style.RESET_ALL}")
            else:
                self._add_log(f"{Fore.RED}No transfer result received{Style.RESET_ALL}")

            # Wait 1 second then refresh data to show the new balances
            self._add_log("Refreshing data to show updated balances...")
            await asyncio.sleep(1)
            await self._fetch_and_update_data()

            print(f"\n{Fore.CYAN}Rebalance complete. Press Enter to return to dashboard...{Style.RESET_ALL}")
            await self._get_user_input("")

        except (ValueError, KeyError) as e:
            self._add_log(f"{Fore.RED}Rebalance error: {e}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
            await self._get_user_input("")
        except KeyboardInterrupt:
            self._add_log("USDT rebalance cancelled by user.")
            print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
            await self._get_user_input("")
        except Exception as e:
            self._add_log(f"{Fore.RED}Unexpected error during rebalance: {e}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}Press Enter to return to dashboard...{Style.RESET_ALL}")
            await self._get_user_input("")

    async def _perform_health_check(self):
        """Performs a health check on all positions and displays warnings."""
        self._add_log("Performing portfolio health check...")

        try:
            # Use shared health check logic from api_manager
            health_issues, critical_issues, dn_positions_count, position_pnl_data = await self.api_manager.perform_health_check_analysis()

            if dn_positions_count == 0:
                self._add_log(f"{Fore.YELLOW}No delta-neutral positions found to check.{Style.RESET_ALL}")
                return

            # Display health check results
            print("\n" + Fore.CYAN + "=== PORTFOLIO HEALTH CHECK ===" + Style.RESET_ALL)
            print(Fore.CYAN + "Health Check Criteria:" + Style.RESET_ALL)
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
                print(f"{Fore.CYAN}  Use 'r' in the dashboard or run: python delta_neutral_bot.py --rebalance{Style.RESET_ALL}")

            print(f"\n{Fore.CYAN}Health check complete. Press Enter to return to dashboard...{Style.RESET_ALL}")
            await self._get_user_input("")

        except Exception as e:
            self._add_log(f"{Fore.RED}Error during health check: {e}{Style.RESET_ALL}")

    async def _analyze_funding_workflow(self):
        """Guides the user through analyzing funding for a specific position."""
        self._add_log("Starting 'Analyze Paid Fundings' workflow...")
        dn_positions = [p for p in self.positions if p.get('is_delta_neutral')]

        if not dn_positions:
            self._add_log(f"{Fore.YELLOW}No delta-neutral positions available to analyze.{Style.RESET_ALL}")
            if self.is_standalone_workflow:
                print(f"{Fore.YELLOW}No delta-neutral positions available to analyze.{Style.RESET_ALL}")
            return

        try:
            # 1. Ask user to select a position
            print("\n" + Fore.CYAN + "Select a delta-neutral position to analyze paid fundings (or 'x' to cancel):" + Style.RESET_ALL)
            for i, pos in enumerate(dn_positions):
                print(f"[{i+1}] {pos.get('symbol', 'N/A')}")

            selection = await self._get_user_input("Enter the number of the position: ")
            if selection.strip().lower() == 'x': raise KeyboardInterrupt

            selected_position = dn_positions[int(selection) - 1]
            symbol_to_analyze = selected_position.get('symbol')

            # 2. Perform analysis using the refactored function from api_manager
            self._add_log(f"Analyzing paid fundings for {symbol_to_analyze}...")
            analysis_result = await self._calculate_funding_for_position(symbol_to_analyze)

            # 3. Display results using the rendering function
            if analysis_result:
                render_funding_analysis_results(analysis_result)
            else:
                self._add_log(f"{Fore.RED}Could not complete funding analysis for {symbol_to_analyze}.{Style.RESET_ALL}")

            if self.is_standalone_workflow:
                print(f"\n{Fore.CYAN}Analysis complete.{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.CYAN}Analysis complete. Press Enter to return to dashboard...{Style.RESET_ALL}")
                await self._get_user_input("")

        except (ValueError, IndexError):
            self._add_log(f"{Fore.RED}Invalid selection.{Style.RESET_ALL}")
        except KeyboardInterrupt:
            self._add_log("Operation cancelled by user.")

    async def _calculate_funding_for_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Calculates funding fees for a specific position using the api_manager function."""
        # This method now serves as a wrapper around the api_manager function
        return await self.api_manager.perform_funding_analysis(symbol)

    def _render_portfolio_summary(self):
        """Renders the summary of portfolio balances."""
        print()  # Single line break before section
        render_portfolio_summary(
            self.perp_usdt_balance,
            self.perp_usdc_balance,
            self.perp_usdf_balance,
            self.spot_usdt_balance,
            title="Portfolio Summary",
            indent=""
        )

    def _render_all_perp_positions(self):
        """Renders a detailed view of all raw perpetual positions."""
        if not self.raw_perp_positions:
            print(Fore.GREEN + "\n--- All Perpetual Positions (Raw) ---" + Style.RESET_ALL)
            print("  No open perpetual positions.")
            return

        # Enhance position data with calculated fields for the common function
        enhanced_positions = []
        for pos in self.raw_perp_positions:
            position_amt = float(pos.get('positionAmt', 0))
            entry_price = float(pos.get('entryPrice', 0))
            mark_price = float(pos.get('markPrice', entry_price))
            leverage = float(pos.get('leverage', 1))

            # Calculate PnL percentage
            if entry_price > 0:
                if position_amt > 0:  # Long position
                    pnl_pct = ((mark_price - entry_price) / entry_price) * 100
                else:  # Short position
                    pnl_pct = ((entry_price - mark_price) / entry_price) * 100
            else:
                pnl_pct = 0.0

            # Calculate notional value and unrealized PnL
            notional_value = abs(position_amt) * mark_price
            unrealized_pnl = float(pos.get('unrealizedProfit', 0))

            # If unrealizedProfit is not available, calculate it
            if unrealized_pnl == 0 and position_amt != 0:
                unrealized_pnl = (mark_price - entry_price) * position_amt

            # Create enhanced position with calculated fields
            enhanced_pos = pos.copy()
            enhanced_pos.update({
                'mark_price': mark_price,
                'pnl_pct': pnl_pct,
                'notional_value': notional_value,
                'leverage': leverage,
                'unrealizedProfit': unrealized_pnl
            })
            enhanced_positions.append(enhanced_pos)

        # Use common function to render the table
        render_perpetual_positions_table(
            enhanced_positions,
            title="--- All Perpetual Positions (Raw) ---",
            show_summary=False,  # Don't show summary in dashboard to save space
            indent=""
        )

    def _render_delta_neutral_positions(self):
        """Renders the analyzed delta-neutral positions."""
        render_delta_neutral_positions(
            self.positions,
            self.raw_perp_positions,
            title="Delta-Neutral Positions",
            indent=""
        )

    def _render_other_positions(self):
        """Renders non-delta-neutral positions, like spot-only holdings or imbalanced pairs."""
        render_other_positions(
            self.positions,
            title="Other Holdings (Non-Delta-Neutral)",
            indent=""
        )

    def _render_spot_balances(self):
        """Renders non-stablecoin spot balances including their USD value."""
        render_spot_balances(
            self.spot_balances,
            title="Spot Balances (Excluding Stables)",
            indent=""
        )

    def _render_opportunities(self):
        """Renders potential opportunities for new positions."""
        render_opportunities(
            self.opportunities,
            title="Potential Opportunities",
            indent=""
        )

    def _render_funding_rate_scan(self):
        """Renders the results of an on-demand funding rate scan."""
        if not self.funding_rate_cache:
            return # Don't render if no scan has been run

        # Use common function to render the table
        render_funding_rates_table(
            self.funding_rate_cache,
            title="--- Top Funding Rate APRs (On-Demand Scan) ---",
            show_summary=False,
            indent=""
        )

    def _render_logs(self):
        """Renders the most recent log messages in reverse order (newest first)."""
        print(Fore.GREEN + "\n--- Logs ---" + Style.RESET_ALL)

        num_messages = len(self.log_messages)
        max_logs = self.log_messages.maxlen

        # Print the actual log messages in reverse order
        for msg in reversed(self.log_messages):
            print(f"{msg}")

        # Print placeholder lines for the remaining space
        for _ in range(max_logs - num_messages):
            print("[--:--:--]")

    def _render_menu(self):
        """Renders the main menu of available actions."""
        print(Fore.CYAN + "\n--- Menu ---" + Style.RESET_ALL)
        print("[R] Refresh Data   [O] Open Position   [C] Close Position   [F] Scan Funding Rates   [Q] Quit")
        print("[H] Health Check   [B] Balance USDT (Perp/Spot)   [A] Analyze Paid Fundings")


# Helper functions for standalone CLI workflows
async def run_interactive_open_workflow():
    """Helper to run the interactive open position workflow from the CLI."""
    app = DashboardApp()
    app.is_standalone_workflow = True
    # Manually initialize the app state before running the workflow
    print("Initializing app and fetching market data...")
    await app._fetch_and_update_data()
    app.interactive_mode = True # Ensure it behaves like the interactive command
    await app._open_position_workflow()
    await app.api_manager.close()

async def run_interactive_close_workflow():
    """Helper to run the interactive close position workflow from the CLI."""
    app = DashboardApp()
    # Manually initialize the app state before running the workflow
    print("Initializing app and fetching market data...")
    await app._fetch_and_update_data()
    app.interactive_mode = True # Ensure it behaves like the interactive command
    app.is_standalone_workflow = True # Ensure messages are printed to console
    await app._close_position_workflow()
    await app.api_manager.close()

async def run_interactive_funding_analysis_workflow():
    """Helper to run the interactive funding analysis workflow from the CLI."""
    app = DashboardApp()
    print("Initializing app and fetching market data...")
    await app._fetch_and_update_data()
    app.interactive_mode = True
    app.is_standalone_workflow = True
    await app._analyze_funding_workflow()
    await app.api_manager.close()


def main():
    """The main function to run the bot."""
    parser = argparse.ArgumentParser(description="Delta-Neutral Funding Rate Farming Bot")
    parser.add_argument('--test', action='store_true', help="Run in test mode (fetch, render once, then exit)")
    parser.add_argument('--pairs', action='store_true', help="Check available pairs for delta-neutral trading")
    parser.add_argument('--funding-rates', action='store_true', help="Check current funding rates for all available pairs")
    parser.add_argument('--positions', action='store_true', help="Show current delta-neutral positions and portfolio summary")
    parser.add_argument('--spot-assets', action='store_true', help="Show current spot asset balances with USD values")
    parser.add_argument('--perpetual', action='store_true', help="Show current perpetual positions with PnL analysis")
    parser.add_argument('--health-check', action='store_true', help="Perform portfolio health check for position risks")
    parser.add_argument('--rebalance', action='store_true', help="Rebalance USDT between spot and perpetual accounts 50/50")
    parser.add_argument('--open', nargs='*', help="Open a new delta-neutral position. Runs interactively if no symbol/capital is provided.")
    parser.add_argument('--close', nargs='?', const=True, default=None, help="Close a delta-neutral position. Runs interactively if no symbol is provided.")
    parser.add_argument('--analyze-fundings', nargs='?', const=True, default=None, help="Analyze paid fundings for a delta-neutral position. Runs interactively if no symbol is provided.")
    parser.add_argument('--yes', action='store_true', help="Bypass confirmation for non-interactive commands like --open.")
    args = parser.parse_args()

    # Check for required environment variables
    required_vars = ['API_USER', 'API_SIGNER', 'API_PRIVATE_KEY', 'APIV1_PUBLIC_KEY', 'APIV1_PRIVATE_KEY']
    if not all(os.getenv(var) for var in required_vars):
        print(Fore.RED + "ERROR: Not all required environment variables are set in your .env file." + Style.RESET_ALL)
        print("Please ensure API_USER, API_SIGNER, API_PRIVATE_KEY, APIV1_PUBLIC_KEY, and APIV1_PRIVATE_KEY are configured.")
        sys.exit(1)

    # Handle CLI-only operations
    if args.pairs:
        try:
            asyncio.run(check_available_pairs())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if args.funding_rates:
        try:
            asyncio.run(check_funding_rates())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if args.positions:
        try:
            asyncio.run(check_current_positions())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if args.spot_assets:
        try:
            asyncio.run(check_spot_assets())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if args.perpetual:
        try:
            asyncio.run(check_perpetual_positions())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if getattr(args, 'health_check', False):
        try:
            asyncio.run(check_portfolio_health())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if args.open is not None:
        if len(args.open) == 0:
            # Interactive mode
            try:
                asyncio.run(run_interactive_open_workflow())
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            return
        elif len(args.open) == 2:
            # Non-interactive CLI mode
            try:
                symbol, capital = args.open
                asyncio.run(open_position_cli(symbol, float(capital), args.yes))
            except (ValueError, IndexError):
                print(f"{Fore.RED}Error: --open requires SYMBOL and CAPITAL arguments.{Style.RESET_ALL}")
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            return
        else:
            print(f"{Fore.RED}Error: --open takes either 0 or 2 arguments (symbol and capital).{Style.RESET_ALL}")
            return

    if args.close is not None:
        if args.close is True:
            # Interactive mode
            try:
                asyncio.run(run_interactive_close_workflow())
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            return
        else:
            # Non-interactive CLI mode
            try:
                asyncio.run(close_position_cli(args.close, args.yes))
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            return

    if args.rebalance:
        try:
            asyncio.run(rebalance_usdt_cli())
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        return

    if args.analyze_fundings is not None:
        if args.analyze_fundings is True:
            # Interactive mode
            try:
                asyncio.run(run_interactive_funding_analysis_workflow())
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            return
        else:
            # Non-interactive CLI mode
            try:
                asyncio.run(analyze_fundings_cli(args.analyze_fundings))
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            return

    # Default behavior: run the dashboard
    app = DashboardApp(is_test_run=args.test)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nCaught KeyboardInterrupt, shutting down...")

if __name__ == '__main__':
    main()