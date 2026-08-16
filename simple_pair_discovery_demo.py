#!/usr/bin/env python3
"""
Simple demonstration of delta-neutral pair discovery.
Shows the core functionality without complex API calls.
"""

from strategy_logic import DeltaNeutralLogic

def simple_pair_discovery_demo():
    """Simple demo of finding suitable trading pairs."""

    print("DELTA-NEUTRAL PAIR DISCOVERY")
    print("=" * 40)

    # Get current known pairs on Aster DEX
    known_pairs = DeltaNeutralLogic.get_aster_known_pairs()

    print("Available trading pairs on Aster DEX:")
    print("Symbol       Spot    Perp    Delta-Neutral")
    print("-" * 45)

    delta_neutral_pairs = []

    for symbol, markets in known_pairs.items():
        spot = "YES" if markets['spot'] else "NO "
        perp = "YES" if markets['perp'] else "NO "
        suitable = "YES" if markets['spot'] and markets['perp'] else "NO "

        print(f"{symbol:<12} {spot}     {perp}     {suitable}")

        if markets['spot'] and markets['perp']:
            delta_neutral_pairs.append(symbol)

    print("\n" + "=" * 45)
    print(f"SUITABLE PAIRS FOR DELTA-NEUTRAL STRATEGY:")
    print(f"Total: {len(delta_neutral_pairs)} pairs")

    for i, symbol in enumerate(delta_neutral_pairs, 1):
        base_asset = symbol.replace('USDT', '')
        print(f"{i}. {symbol} ({base_asset} against USDT)")

    print(f"\nThese pairs allow you to:")
    print(f"- Buy {base_asset} on spot market")
    print(f"- Short {base_asset} on perpetual market")
    print(f"- Collect funding payments while staying market-neutral")

    # Example: Simulate market expansion
    print(f"\n" + "=" * 45)
    print("SIMULATING MARKET EXPANSION:")

    # Example of how new pairs would be added
    future_pairs = {
        'SOLUSDT': {'spot': True, 'perp': True},   # New pair added
        'AVAXUSDT': {'spot': True, 'perp': False}, # Spot only initially
        'DOTUSDT': {'spot': False, 'perp': True},  # Perp only initially
    }

    print("Future pairs that might be added:")
    for symbol, markets in future_pairs.items():
        status = "READY" if markets['spot'] and markets['perp'] else "WAITING"
        reason = ""
        if not markets['spot']:
            reason = "(waiting for spot market)"
        elif not markets['perp']:
            reason = "(waiting for perp market)"

        print(f"  {symbol}: {status} {reason}")

    # Show how the discovery would work
    all_pairs = {**known_pairs, **future_pairs}
    all_suitable = DeltaNeutralLogic.extract_delta_neutral_candidates(all_pairs)

    print(f"\nAfter expansion: {len(all_suitable)} total pairs suitable")
    print(f"New additions: {[p for p in all_suitable if p not in delta_neutral_pairs]}")

    return delta_neutral_pairs

if __name__ == '__main__':
    pairs = simple_pair_discovery_demo()
    print(f"\nCurrent strategy can work with: {pairs}")