#!/usr/bin/env python3
"""
Demo script to showcase the CLI functionality of delta_neutral_bot.py
This script demonstrates the new --pairs and --funding-rates commands.
"""

import subprocess
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_env_vars():
    """Check if required environment variables are set."""
    required_vars = ['API_USER', 'API_SIGNER', 'API_PRIVATE_KEY', 'APIV1_PUBLIC_KEY', 'APIV1_PRIVATE_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"[X] Missing environment variables: {', '.join(missing_vars)}")
        print("[!] Please configure your .env file with API credentials to run live demos.")
        return False

    print("[OK] All required environment variables are set.")
    return True

def demo_help():
    """Demo the help command."""
    print("\n" + "="*60)
    print("[HELP] DEMO: Help Command")
    print("="*60)
    print("Command: python delta_neutral_bot.py --help\n")

    try:
        result = subprocess.run([sys.executable, 'delta_neutral_bot.py', '--help'],
                              capture_output=True, text=True, timeout=10)
        print(result.stdout)
    except subprocess.TimeoutExpired:
        print("[X] Command timed out")
    except Exception as e:
        print(f"[X] Error running command: {e}")

def demo_pairs_dry_run():
    """Demo the pairs command structure (without API calls)."""
    print("\n" + "="*60)
    print("[PAIRS] DEMO: Available Pairs Command Structure")
    print("="*60)
    print("Command: python delta_neutral_bot.py --pairs")
    print("\nThis command will:")
    print("  1. Connect to both Aster spot and perpetual markets")
    print("  2. Fetch available trading symbols from both markets")
    print("  3. Find the intersection (pairs available in both)")
    print("  4. Display results in a formatted table")
    print("  5. Show total count and exit cleanly")

    if check_env_vars():
        print("\n[!] To run live: python delta_neutral_bot.py --pairs")
    else:
        print("\n[X] Cannot run live demo - missing API credentials")

def demo_funding_rates_dry_run():
    """Demo the funding rates command structure (without API calls)."""
    print("\n" + "="*60)
    print("[RATES] DEMO: Funding Rates Command Structure")
    print("="*60)
    print("Command: python delta_neutral_bot.py --funding-rates")
    print("\nThis command will:")
    print("  1. Discover all delta-neutral tradeable pairs")
    print("  2. Fetch current funding rates for each pair")
    print("  3. Calculate annualized APR (rate * 3 * 365 * 100)")
    print("  4. Calculate effective APR (APR / 2) for 1x leverage delta-neutral trading")
    print("  5. Sort by highest APR first")
    print("  6. Display formatted table with summary statistics")
    print("  7. Show positive/negative rate counts and highest APR pair")

    if check_env_vars():
        print("\n[!] To run live: python delta_neutral_bot.py --funding-rates")
    else:
        print("\n[X] Cannot run live demo - missing API credentials")

def demo_positions_dry_run():
    """Demo the positions command structure (without API calls)."""
    print("\n" + "="*60)
    print("[POSITIONS] DEMO: Current Positions Command Structure")
    print("="*60)
    print("Command: python delta_neutral_bot.py --positions")
    print("\nThis command will:")
    print("  1. Analyze current positions across both spot and perpetual markets")
    print("  2. Calculate portfolio summary with total balances")
    print("  3. Display delta-neutral positions with imbalance analysis")
    print("  4. Show other holdings (spot-only or imbalanced positions)")
    print("  5. Fetch current funding rates for delta-neutral positions")
    print("  6. Provide summary statistics and balance quality metrics")

    if check_env_vars():
        print("\n[!] To run live: python delta_neutral_bot.py --positions")
    else:
        print("\n[X] Cannot run live demo - missing API credentials")

def demo_spot_assets_dry_run():
    """Demo the spot assets command structure (without API calls)."""
    print("\n" + "="*60)
    print("[ASSETS] DEMO: Spot Assets Command Structure")
    print("="*60)
    print("Command: python delta_neutral_bot.py --spot-assets")
    print("\nThis command will:")
    print("  1. Fetch all spot account balances from Aster DEX")
    print("  2. Separate stablecoins from other assets automatically")
    print("  3. Fetch current USD prices for non-stablecoin assets")
    print("  4. Try multiple quote currencies (USDT, USDC, BUSD) for price discovery")
    print("  5. Suppress expected API errors during price discovery for cleaner output")
    print("  6. Display detailed breakdown with free, locked, and total amounts")
    print("  7. Calculate and show total portfolio value in USD")
    print("  8. Highlight assets without available price data")

    if check_env_vars():
        print("\n[!] To run live: python delta_neutral_bot.py --spot-assets")
    else:
        print("\n[X] Cannot run live demo - missing API credentials")

def demo_perpetual_dry_run():
    """Demo the perpetual command structure (without API calls)."""
    print("\n" + "="*60)
    print("[PERPETUAL] DEMO: Perpetual Positions Command Structure")
    print("="*60)
    print("Command: python delta_neutral_bot.py --perpetual")
    print("\nThis command will:")
    print("  1. Fetch perpetual account information and active positions")
    print("  2. Calculate real-time PnL in both USD and percentage")
    print("  3. Display position details with entry price, mark price, and leverage")
    print("  4. Show account summary with wallet balance and margin details")
    print("  5. Provide portfolio metrics including effective leverage")
    print("  6. Analyze risk with profitable vs. losing position breakdown")
    print("  7. Highlight best and worst performing positions")

    if check_env_vars():
        print("\n[!] To run live: python delta_neutral_bot.py --perpetual")
    else:
        print("\n[X] Cannot run live demo - missing API credentials")

def demo_test_mode():
    """Demo the test mode functionality."""
    print("\n" + "="*60)
    print("[TEST] DEMO: Test Mode")
    print("="*60)
    print("Command: python delta_neutral_bot.py --test")
    print("\nTest mode will:")
    print("  1. Initialize the full dashboard application")
    print("  2. Fetch data once from the API")
    print("  3. Render the dashboard once")
    print("  4. Exit immediately (no user interaction)")
    print("  5. Perfect for CI/CD validation")

def main():
    """Run all demonstrations."""
    print("Delta-Neutral Bot CLI Functionality Demo")
    print("This demo showcases the new command-line interface features.")

    # Demo help (always works)
    demo_help()

    # Demo other commands (structure explanation)
    demo_pairs_dry_run()
    demo_funding_rates_dry_run()
    demo_positions_dry_run()
    demo_spot_assets_dry_run()
    demo_perpetual_dry_run()
    demo_test_mode()

    print("\n" + "="*60)
    print("[SUMMARY] Available CLI Commands:")
    print("="*60)
    print("  --help          : Show help message and available options")
    print("  --pairs         : List available delta-neutral trading pairs")
    print("  --funding-rates : Show current funding rates and APRs")
    print("  --positions     : Show current delta-neutral positions and portfolio")
    print("  --spot-assets   : Show current spot asset balances with USD values")
    print("  --perpetual     : Show perpetual positions with PnL analysis")
    print("  --test          : Run dashboard in test mode (fetch once, exit)")
    print("  (no args)       : Run full interactive dashboard")

    print("\n[FEATURES] All CLI commands include:")
    print("  * Proper error handling and timeout management")
    print("  * Colorized output for better readability")
    print("  * Concurrent API calls for optimal performance")
    print("  * Clean session management with proper cleanup")
    print("  * Cross-platform compatibility (Windows/Linux/Mac)")

if __name__ == '__main__':
    main()