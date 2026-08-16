#!/usr/bin/env python3
"""
UI rendering functions for the delta-neutral funding rate farming bot.
Contains all terminal output formatting and display functions.
"""

from colorama import Fore, Style
from decimal import Decimal
from typing import Dict, Any, List


def render_funding_rates_table(funding_data, title="Funding Rates (sorted by APR, highest first)", show_summary=True, indent=""):
    """Common function to render funding rates table with effective APR column.

    Args:
        funding_data: List of funding rate dictionaries with 'symbol', 'rate', 'apr' keys
        title: Title to display above the table
        show_summary: Whether to show summary statistics
        indent: String to prepend to each line for indentation
    """
    if not funding_data:
        print(Fore.YELLOW + f"{indent}No funding rate data available." + Style.RESET_ALL)
        return

    print(Fore.GREEN + f"{indent}{title}:\n" + Style.RESET_ALL)

    # Display header
    header = f"{'Symbol':<12} {'Current Rate':>15} {'APR (%)':>20} {'Effective APR (%)':>18}"
    print(f"{indent}{header}")
    print(f"{indent}" + "-" * len(header))

    # Display funding rates
    for item in funding_data:
        rate = item['rate']
        apr = item['apr']
        effective_apr = apr / 2  # Divide by 2 since leverage is 1x for delta-neutral
        apr_color = Fore.GREEN if apr > 0 else Fore.RED
        effective_color = Fore.GREEN if effective_apr > 0 else Fore.RED
        print(f"{indent}{item['symbol']:<12} {rate:>15.6f} {apr_color}{apr:>20.2f}{Style.RESET_ALL} {effective_color}{effective_apr:>18.2f}{Style.RESET_ALL}")

    if show_summary:
        # Summary statistics
        positive_rates = [item for item in funding_data if item['apr'] > 0]
        negative_rates = [item for item in funding_data if item['apr'] < 0]

        print(f"\n{indent}{Fore.CYAN}Summary:")
        print(f"{indent}  Positive APR pairs: {len(positive_rates)}")
        print(f"{indent}  Negative APR pairs: {len(negative_rates)}")
        if positive_rates:
            highest_apr = max(positive_rates, key=lambda x: x['apr'])
            highest_effective_apr = highest_apr['apr'] / 2
            print(f"{indent}  Highest APR: {highest_apr['symbol']} ({highest_apr['apr']:.2f}% -> {highest_effective_apr:.2f}% effective)")
        print(f"{indent}  Total pairs scanned: {len(funding_data)}{Style.RESET_ALL}")


def render_perpetual_positions_table(positions_data, title="POSITION DETAILS", show_summary=True, indent=""):
    """Common function to render perpetual positions table with % gain column.
    Args:
        positions_data: List of position dictionaries with calculated fields
        title: Title to display above the table
        show_summary: Whether to show summary statistics
        indent: String to prepend to each line for indentation
    """
    if not positions_data:
        print(Fore.YELLOW + f"{indent}No active perpetual positions found." + Style.RESET_ALL)
        return

    print(Fore.GREEN + f"{indent}{title}" + Style.RESET_ALL)

    # Header with % gain column
    header = f"{'Symbol':<12} {'Side':<5} {'Size':>12} {'Entry':>12} {'Mark':>12} {'Leverage':>8} {'Notional':>12} {'PnL USD':>12} {'PnL %':>8}"
    print(f"{indent}{header}")
    print(f"{indent}" + "-" * len(header))

    # Sort positions by unrealized PnL (highest first)
    sorted_positions = sorted(positions_data, key=lambda x: float(x.get('unrealizedProfit', 0)), reverse=True)

    total_notional = 0
    total_pnl = 0
    profitable_positions = 0
    losing_positions = 0

    for pos in sorted_positions:
        symbol = pos.get('symbol', 'N/A')
        position_amt = float(pos.get('positionAmt', 0))
        entry_price = float(pos.get('entryPrice', 0))
        mark_price = pos.get('mark_price', entry_price)
        leverage = pos.get('leverage', 1)
        notional_value = pos.get('notional_value', 0)
        unrealized_pnl = float(pos.get('unrealizedProfit', 0))
        pnl_pct = pos.get('pnl_pct', 0)

        total_notional += notional_value
        total_pnl += unrealized_pnl

        if unrealized_pnl > 0:
            profitable_positions += 1
        elif unrealized_pnl < 0:
            losing_positions += 1

        # Determine side and colors
        if position_amt > 0:
            side = "LONG"
            side_color = Fore.GREEN
        else:
            side = "SHORT"
            side_color = Fore.RED

        size = abs(position_amt)

        # Color coding based on PnL for the row
        if unrealized_pnl > 0:
            row_color = Fore.GREEN
        elif unrealized_pnl < 0:
            row_color = Fore.RED
        else:
            row_color = Fore.YELLOW

        # Format the row with colored side text
        print(f"{indent}{symbol:<12} {side_color}{side:<5}{Style.RESET_ALL} {row_color}{size:>12.6f} {entry_price:>12.4f} {mark_price:>12.4f} {leverage:>8.1f}x {notional_value:>12,.2f} {unrealized_pnl:>12.2f} {pnl_pct:>7.2f}%{Style.RESET_ALL}")

    if show_summary:
        # Summary statistics
        print(f"\n{indent}{Fore.CYAN}Portfolio Summary:")
        print(f"{indent}  Total Notional Value: ${total_notional:>12,.2f}")
        print(f"{indent}  Total Unrealized PnL: ${total_pnl:>12,.2f}")
        print(f"{indent}  Profitable Positions: {profitable_positions:>2}")
        print(f"{indent}  Losing Positions:     {losing_positions:>2}")

        if sorted_positions:
            best_position = sorted_positions[0]
            worst_position = sorted_positions[-1]
            print(f"{indent}  Best Performer:  {best_position.get('symbol', 'N/A')} ({best_position.get('pnl_pct', 0):.2f}%)")
            print(f"{indent}  Worst Performer: {worst_position.get('symbol', 'N/A')} ({worst_position.get('pnl_pct', 0):.2f}%)")
        print(f"{indent}  Total Positions: {len(sorted_positions)}{Style.RESET_ALL}")


def render_portfolio_summary(perp_usdt_balance, perp_usdc_balance, perp_usdf_balance, spot_usdt_balance, title="Portfolio Summary", indent=""):
    """Common function to render portfolio summary section.
    Args:
        perp_usdt_balance: Perpetual USDT balance
        perp_usdc_balance: Perpetual USDC balance
        perp_usdf_balance: Perpetual USDF balance
        spot_usdt_balance: Spot USDT balance
        title: Title to display above the summary
        indent: String to prepend to each line for indentation
    """
    print(Fore.GREEN + f"{indent}--- {title} ---" + Style.RESET_ALL)

    perp_margin_balance = perp_usdt_balance + perp_usdc_balance + perp_usdf_balance
    total_portfolio_value = perp_margin_balance + spot_usdt_balance

    print(f"{indent}Perp Margin Balance: ${perp_margin_balance:,.2f} (USDT: {perp_usdt_balance:.2f}, USDC: {perp_usdc_balance:.2f}, USDF: {perp_usdf_balance:.2f})")
    print(f"{indent}Spot USDT Balance:   ${spot_usdt_balance:,.2f}")
    print(f"{indent}Total Portfolio USD: ${total_portfolio_value:,.2f}")


def render_delta_neutral_positions(positions_data, raw_perp_positions, title="Delta-Neutral Positions", indent=""):
    """Common function to render delta-neutral positions table.
    Args:
        positions_data: List of position dictionaries with delta-neutral analysis
        raw_perp_positions: List of raw perpetual position data for PnL lookup
        title: Title to display above the table
        indent: String to prepend to each line for indentation
    """
    print(Fore.GREEN + f"{indent}--- {title} ---" + Style.RESET_ALL)

    dn_positions = [p for p in positions_data if p.get('is_delta_neutral')]

    if not dn_positions:
        print(f"{indent}No delta-neutral positions found.")
        return

    header = f"{'Symbol':<12} {'Spot Balance':>15} {'Perp Position':>15} {'Net Delta':>12} {'Value (spot+perp+pnl)':>25} {'Imbalance':>12} {' Eff. APR (%)':>12}"
    print(f"{indent}{header}")
    print(f"{indent}" + "-" * len(header))

    total_dn_value = 0
    for pos in dn_positions:
        symbol = pos.get('symbol', 'N/A')
        spot_balance = pos.get('spot_balance', 0.0)
        perp_position = pos.get('perp_position', 0.0)
        net_delta = pos.get('net_delta', 0.0)
        imbalance = pos.get('imbalance_pct', 0.0)
        apr = pos.get('current_apr', 'N/A')
        apr_str = f"{apr/2.0:.2f}" if isinstance(apr, (int, float)) else str(apr)

        # Find the corresponding raw perp position to get PnL and price
        raw_pos = next((p for p in raw_perp_positions if p.get('symbol') == symbol), None)
        pnl = float(raw_pos.get('unrealizedProfit', 0)) if raw_pos else 0.0
        current_price = float(raw_pos.get('markPrice', 0)) if raw_pos else pos.get('current_price', 0.0)

        # Calculate different components of value
        spot_value_usd = spot_balance * current_price
        short_value_usd = abs(perp_position) * current_price

        # User-defined formula for "Value"
        final_value = spot_value_usd + short_value_usd + pnl

        total_dn_value += final_value

        # Color coding based on spot value warning levels
        if spot_value_usd < 5:
            row_color = Fore.RED  # Critical - below $5
        elif spot_value_usd < 10:
            row_color = Fore.YELLOW  # Warning - below $10
        else:
            row_color = Fore.GREEN  # Healthy - above $10

        print(row_color + f"{indent}{symbol:<12} {spot_balance:>15.6f} {perp_position:>15.6f} {net_delta:>12.6f} {f'${final_value:,.2f}':>25} {f'{imbalance:.2f}%':>12} {apr_str:>12}" + Style.RESET_ALL)

    print(f"{indent}{Fore.CYAN}Total Delta-Neutral Value: ${total_dn_value:,.2f}{Style.RESET_ALL}")


def render_spot_balances(spot_balances, title="Spot Balances (Excluding Stables)", indent=""):
    """Common function to render spot balances table.
    Args:
        spot_balances: List of spot balance dictionaries
        title: Title to display above the table
        indent: String to prepend to each line for indentation
    """
    print(Fore.GREEN + f"{indent}--- {title} ---" + Style.RESET_ALL)

    non_stable_balances = [b for b in spot_balances if b.get('asset') not in ['USDT', 'USDC', 'USDF'] and float(b.get('free', 0)) + float(b.get('locked', 0)) > 0]

    if not non_stable_balances:
        print(f"{indent}No significant non-stablecoin spot balances found.")
        return

    header = f"{'Asset':<10} {'Free':>15} {'Locked':>15} {'Value (USD)':>18}"
    print(f"{indent}{header}")
    print(f"{indent}" + "-" * (len(header) + 4))

    total_spot_value = 0
    for balance in non_stable_balances:
        asset = balance.get('asset', 'N/A')
        free = float(balance.get('free', 0))
        locked = float(balance.get('locked', 0))
        value_usd = balance.get('value_usd', 0.0)
        total_spot_value += value_usd
        print(f"{indent}{asset:<10} {free:>15.6f} {locked:>15.6f} {value_usd:>18,.2f}")

    print(f"{indent}{Fore.CYAN}Total Non-Stable Value: ${total_spot_value:,.2f}{Style.RESET_ALL}")


def render_other_positions(positions_data, title="Other Holdings (Non-Delta-Neutral)", indent=""):
    """Common function to render non-delta-neutral positions table.
    Args:
        positions_data: List of position dictionaries with delta-neutral analysis
        title: Title to display above the table
        indent: String to prepend to each line for indentation
    """
    other_positions = [p for p in positions_data if not p.get('is_delta_neutral')]

    if not other_positions:
        return  # Don't render if no other positions

    print(Fore.GREEN + f"{indent}--- {title} ---" + Style.RESET_ALL)

    header = f"{'Symbol':<12} {'Spot Balance':>15} {'Perp Position':>15} {'Net Delta':>12} {'Value':>15} {'Imbalance':>12}"
    print(f"{indent}{header}")
    print(f"{indent}" + "-" * len(header))

    for pos in other_positions:
        symbol = pos.get('symbol', 'N/A')
        spot_balance = pos.get('spot_balance', 0.0)
        perp_position = pos.get('perp_position', 0.0)
        net_delta = pos.get('net_delta', 0.0)
        value_usd = pos.get('position_value_usd', 0.0)
        imbalance = pos.get('imbalance_pct', 0.0)

        print(Fore.YELLOW + f"{indent}{symbol:<12} {spot_balance:>15.6f} {perp_position:>15.6f} {net_delta:>12.6f} ${value_usd:>14,.2f} {imbalance:>11.2f}%" + Style.RESET_ALL)


def render_opportunities(opportunities_data, title="Potential Opportunities", indent=""):
    """Common function to render opportunities section.
    Args:
        opportunities_data: List of opportunity strings
        title: Title to display above the opportunities
        indent: String to prepend to each line for indentation
    """
    if not opportunities_data:
        return  # Do not render the section if there are no opportunities

    print(Fore.GREEN + f"{indent}--- {title} ---" + Style.RESET_ALL)
    for opp in opportunities_data:
        print(f"{indent}- {opp}")


def render_funding_analysis_results(analysis_result: Dict[str, Any]):
    """Renders the results of a funding analysis to the console."""
    if not analysis_result:
        return

    print(f"\n{Fore.YELLOW}--- Paid Fundings Analysis Result for {analysis_result['symbol']} ---{Style.RESET_ALL}")
    print(f"Perp Position: {analysis_result['position_amount']} (Notional: {analysis_result['position_notional']:.4f} USDT)")
    print(f"Spot Balance: {analysis_result['spot_balance']} {analysis_result['symbol'].replace('USDT','')}")
    print(f"Effective Position Value: {Fore.CYAN}{analysis_result['effective_position_value']:.4f} USDT{Style.RESET_ALL}")
    print(f"Position Start Time: {analysis_result['position_start_time']}")
    print("-" * 33)
    print(f"Funding Payments Found: {analysis_result['funding_payments_count']}")

    funding_color = Fore.GREEN if analysis_result['total_funding'] > 0 else Fore.RED
    print(f"Total Funding Fees Paid: {funding_color}{analysis_result['total_funding']:.8f} {analysis_result['asset']}{Style.RESET_ALL}")
    print(f"Funding as % of Effective Value: {analysis_result['funding_as_percentage_of_effective_value']:.4f}%")

    # Visual progress bar for fee coverage
    progress = min(Decimal('100'), analysis_result['fee_coverage_progress'])  # Cap at 100%
    bar_length = 25
    filled_length = int(bar_length * progress / 100)
    bar = (Fore.GREEN + '#' * filled_length) + (Style.DIM + '-' * (bar_length - filled_length))
    print(f"Fee Coverage Progress: [{bar}{Style.RESET_ALL}] {analysis_result['fee_coverage_progress']:.2f}% of 0.135%")

    print(f"\n{Style.DIM}Notes:")
    print(f"{Style.DIM}- Funding is paid every 8 hours at 00:00, 08:00, and 16:00 UTC.")
    print(f"{Style.DIM}- Effective Position Value = Spot Value + Abs(Perp Notional) + PnL.")
    print(f"{Style.DIM}- Fee Coverage Progress shows how close the funding has come to paying")
    print(f"{Style.DIM}  for the estimated 0.135% in total entry+exit trading fees: ([0.1% spot market]/2 + [0.035% perp market]/2) X 2.")
    print(f"{Style.DIM}- This analysis does not account for price spreads.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}-------------------------------------------{Style.RESET_ALL}")