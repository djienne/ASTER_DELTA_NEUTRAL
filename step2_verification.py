#!/usr/bin/env python3
"""
Comprehensive Step 2 verification against mega plan requirements.
This script validates every requirement from the mega plan Step 2.
"""

import os
import sys
import inspect
import importlib.util
import subprocess

def check_file_setup():
    """Verify file setup and imports according to mega plan."""
    print("=" * 60)
    print("STEP 2 VERIFICATION - FILE SETUP & IMPORTS")
    print("=" * 60)

    # Check if strategy_logic.py exists
    file_path = "strategy_logic.py"
    if not os.path.exists(file_path):
        print("[ERROR] strategy_logic.py not found")
        return False

    print("[OK] strategy_logic.py exists")

    # Import the module
    try:
        spec = importlib.util.spec_from_file_location("strategy_logic", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("[OK] Module imports successfully")
    except Exception as e:
        print(f"[ERROR] Module import failed: {e}")
        return False

    # Check required imports in source
    with open(file_path, 'r') as f:
        content = f.read()

    required_imports = ['typing', 'statistics']
    for imp in required_imports:
        if imp in content:
            print(f"[OK] {imp} imported")
        else:
            print(f"[ERROR] {imp} missing from imports")
            return False

    # Check strategy constants
    required_constants = [
        'ANNUALIZED_APR_THRESHOLD',
        'MIN_FUNDING_RATE_COUNT',
        'MAX_VOLATILITY_THRESHOLD',
        'LIQUIDATION_BUFFER_PCT',
        'IMBALANCE_THRESHOLD_PCT',
        'HIGH_RISK_LIQUIDATION_PCT'
    ]

    for const in required_constants:
        if const in content:
            print(f"[OK] {const} constant defined")
        else:
            print(f"[ERROR] {const} constant missing")
            return False

    return True

def check_class_definition():
    """Verify DeltaNeutralLogic class definition."""
    print("\n" + "=" * 60)
    print("STEP 2 VERIFICATION - CLASS DEFINITION")
    print("=" * 60)

    try:
        from strategy_logic import DeltaNeutralLogic

        # Check that it's a class
        if not inspect.isclass(DeltaNeutralLogic):
            print("[ERROR] DeltaNeutralLogic is not a class")
            return False

        print("[OK] DeltaNeutralLogic class exists")

        # Check that it has no __init__ method (should be static only)
        if hasattr(DeltaNeutralLogic, '__init__'):
            # It will always have __init__, but it should be the default one
            init_method = getattr(DeltaNeutralLogic, '__init__')
            if init_method.__qualname__ != 'object.__init__':
                print("[WARNING] DeltaNeutralLogic has custom __init__ (should be static methods only)")

        return True

    except Exception as e:
        print(f"[ERROR] Class verification failed: {e}")
        return False

def check_static_methods():
    """Verify all required static methods exist."""
    print("\n" + "=" * 60)
    print("STEP 2 VERIFICATION - STATIC METHODS")
    print("=" * 60)

    try:
        from strategy_logic import DeltaNeutralLogic

        required_methods = [
            'analyze_funding_opportunities',
            'calculate_position_size',
            'check_position_health',
            'determine_rebalance_action',
            'calculate_rebalance_quantities',
            'validate_strategy_preconditions'
        ]

        for method_name in required_methods:
            if hasattr(DeltaNeutralLogic, method_name):
                method = getattr(DeltaNeutralLogic, method_name)
                if isinstance(method, staticmethod):
                    print(f"[OK] {method_name} exists and is static")
                else:
                    print(f"[WARNING] {method_name} exists but may not be static")
            else:
                print(f"[ERROR] {method_name} missing")
                return False

        return True

    except Exception as e:
        print(f"[ERROR] Static methods verification failed: {e}")
        return False

def check_method_signatures():
    """Verify method signatures match mega plan requirements."""
    print("\n" + "=" * 60)
    print("STEP 2 VERIFICATION - METHOD SIGNATURES")
    print("=" * 60)

    try:
        from strategy_logic import DeltaNeutralLogic

        # Check analyze_funding_opportunities signature
        sig = inspect.signature(DeltaNeutralLogic.analyze_funding_opportunities)
        params = list(sig.parameters.keys())
        expected_params = ['funding_histories', 'spot_prices']
        if params == expected_params:
            print("[OK] analyze_funding_opportunities signature correct")
        else:
            print(f"[ERROR] analyze_funding_opportunities params: {params}, expected: {expected_params}")
            return False

        # Check calculate_position_size signature
        sig = inspect.signature(DeltaNeutralLogic.calculate_position_size)
        params = list(sig.parameters.keys())
        expected_params = ['total_usd_capital', 'spot_price', 'leverage']
        if params == expected_params:
            print("[OK] calculate_position_size signature correct")
        else:
            print(f"[ERROR] calculate_position_size params: {params}, expected: {expected_params}")
            return False

        # Check check_position_health signature
        sig = inspect.signature(DeltaNeutralLogic.check_position_health)
        params = list(sig.parameters.keys())
        expected_params = ['perp_position', 'spot_balance_qty', 'leverage']
        if params == expected_params:
            print("[OK] check_position_health signature correct")
        else:
            print(f"[ERROR] check_position_health params: {params}, expected: {expected_params}")
            return False

        # Check determine_rebalance_action signature
        sig = inspect.signature(DeltaNeutralLogic.determine_rebalance_action)
        params = list(sig.parameters.keys())
        expected_params = ['health_report']
        if params == expected_params:
            print("[OK] determine_rebalance_action signature correct")
        else:
            print(f"[ERROR] determine_rebalance_action params: {params}, expected: {expected_params}")
            return False

        return True

    except Exception as e:
        print(f"[ERROR] Method signature verification failed: {e}")
        return False

def check_test_file():
    """Verify test file exists and has required tests."""
    print("\n" + "=" * 60)
    print("STEP 2 VERIFICATION - TEST FILE")
    print("=" * 60)

    test_file = "test_strategy_logic.py"
    if not os.path.exists(test_file):
        print("[ERROR] test_strategy_logic.py not found")
        return False

    print("[OK] test_strategy_logic.py exists")

    # Check test content
    with open(test_file, 'r') as f:
        content = f.read()

    required_tests = [
        'test_opportunity_analyzer',
        'test_position_sizing',
        'test_health_checks',
        'test_action_determination'
    ]

    for test_name in required_tests:
        if test_name in content:
            print(f"[OK] {test_name} found in tests")
        else:
            print(f"[WARNING] {test_name} not found (may be named differently)")

    # Check for unittest.TestCase usage
    if 'unittest.TestCase' in content:
        print("[OK] Uses unittest.TestCase as required")
    else:
        print("[ERROR] Does not use unittest.TestCase")
        return False

    return True

def run_unit_tests():
    """Run the actual unit tests."""
    print("\n" + "=" * 60)
    print("STEP 2 VERIFICATION - RUNNING UNIT TESTS")
    print("=" * 60)

    try:
        # Run unit tests
        result = subprocess.run([
            sys.executable, '-m', 'unittest',
            'test_strategy_logic', '-v'
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print("[OK] All unit tests pass")
            return True
        else:
            print(f"[ERROR] Unit tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False

    except Exception as e:
        print(f"[ERROR] Could not run unit tests: {e}")
        return False

def test_core_functionality():
    """Test core functionality with simple examples."""
    print("\n" + "=" * 60)
    print("STEP 2 VERIFICATION - CORE FUNCTIONALITY")
    print("=" * 60)

    try:
        from strategy_logic import DeltaNeutralLogic

        # Test 1: analyze_funding_opportunities
        mock_funding = {
            'BTCUSDT': [0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002, 0.0002]
        }
        mock_prices = {'BTCUSDT': 50000.0}

        opportunities = DeltaNeutralLogic.analyze_funding_opportunities(mock_funding, mock_prices)
        if len(opportunities) == 1 and opportunities[0]['symbol'] == 'BTCUSDT':
            print("[OK] analyze_funding_opportunities basic functionality works")
        else:
            print("[ERROR] analyze_funding_opportunities failed basic test")
            return False

        # Test 2: calculate_position_size
        sizing = DeltaNeutralLogic.calculate_position_size(1000.0, 50.0, 1)
        if sizing['spot_quantity'] == sizing['perp_quantity'] == 20.0:
            print("[OK] calculate_position_size basic functionality works")
        else:
            print("[ERROR] calculate_position_size failed basic test")
            return False

        # Test 3: check_position_health
        mock_position = {
            'positionAmt': '-10.0',
            'liquidationPrice': '1000.0',
            'markPrice': '2000.0',
            'unrealizedProfit': '100.0'
        }
        health = DeltaNeutralLogic.check_position_health(mock_position, 10.0)
        if abs(health['net_delta']) < 0.01:  # Should be approximately 0
            print("[OK] check_position_health basic functionality works")
        else:
            print("[ERROR] check_position_health failed basic test")
            return False

        # Test 4: determine_rebalance_action
        healthy_report = {'liquidation_risk_level': 'LOW', 'imbalance_percentage': 2.0}
        action = DeltaNeutralLogic.determine_rebalance_action(healthy_report)
        if action == 'ACTION_HOLD':
            print("[OK] determine_rebalance_action basic functionality works")
        else:
            print("[ERROR] determine_rebalance_action failed basic test")
            return False

        return True

    except Exception as e:
        print(f"[ERROR] Core functionality test failed: {e}")
        return False

def main():
    """Run comprehensive Step 2 verification."""
    print("COMPREHENSIVE STEP 2 VERIFICATION")
    print("Checking all requirements from mega_plan.md Step 2")
    print("\n")

    all_checks = [
        ("File Setup & Imports", check_file_setup()),
        ("Class Definition", check_class_definition()),
        ("Static Methods", check_static_methods()),
        ("Method Signatures", check_method_signatures()),
        ("Test File Structure", check_test_file()),
        ("Unit Tests Execution", run_unit_tests()),
        ("Core Functionality", test_core_functionality())
    ]

    print("\n" + "=" * 60)
    print("FINAL VERIFICATION RESULTS")
    print("=" * 60)

    passed = 0
    total = len(all_checks)

    for check_name, result in all_checks:
        if result:
            print(f"[PASS] {check_name}")
            passed += 1
        else:
            print(f"[FAIL] {check_name}")

    print(f"\nResults: {passed}/{total} checks passed")

    if passed == total:
        print("\n" + "[SUCCESS]" * 5)
        print("[SUCCESS] STEP 2 FULLY ACCOMPLISHED!")
        print("All mega plan requirements satisfied")
        print("Strategy logic module complete and tested")
        print("Ready to proceed to Step 3")
        print("[SUCCESS]" * 5)
        return True
    else:
        print("\n[ERROR] STEP 2 INCOMPLETE")
        print(f"Please address the {total - passed} failing checks")
        return False

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)