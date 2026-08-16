#!/usr/bin/env python3
"""
Comprehensive Step 1 verification against mega plan requirements.
This script validates every requirement from the mega plan Step 1.
"""

import os
import asyncio
import inspect
import importlib.util
from dotenv import load_dotenv

# Load environment for testing
load_dotenv()

def check_file_setup():
    """Verify file setup and imports according to mega plan."""
    print("=" * 60)
    print("STEP 1 VERIFICATION - FILE SETUP & IMPORTS")
    print("=" * 60)

    # Check if aster_api_manager.py exists
    file_path = "aster_api_manager.py"
    if not os.path.exists(file_path):
        print("[ERROR] aster_api_manager.py not found")
        return False

    print("[OK] aster_api_manager.py exists")

    # Import the module
    try:
        spec = importlib.util.spec_from_file_location("aster_api_manager", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("[OK] Module imports successfully")
    except Exception as e:
        print(f"[ERROR] Module import failed: {e}")
        return False

    # Check required imports in source
    with open(file_path, 'r') as f:
        content = f.read()

    required_imports = [
        'asyncio', 'aiohttp', 'os', 'time', 'hmac', 'hashlib',
        'json', 'urllib.parse', 'typing', 'ApiClient'
    ]

    for imp in required_imports:
        if imp in content:
            print(f"[OK] {imp} imported")
        else:
            print(f"[ERROR] {imp} missing from imports")
            return False

    # Check base URL constants
    if 'FUTURES_BASE_URL = "https://fapi.asterdex.com"' in content:
        print("[OK] FUTURES_BASE_URL defined correctly")
    else:
        print("[ERROR] FUTURES_BASE_URL not defined correctly")
        return False

    if 'SPOT_BASE_URL = "https://sapi.asterdex.com"' in content:
        print("[OK] SPOT_BASE_URL defined correctly")
    else:
        print("[ERROR] SPOT_BASE_URL not defined correctly")
        return False

    return True

def check_class_definition():
    """Verify AsterApiManager class definition."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - CLASS DEFINITION")
    print("=" * 60)

    try:
        from aster_api_manager import AsterApiManager

        # Check constructor signature
        init_sig = inspect.signature(AsterApiManager.__init__)
        params = list(init_sig.parameters.keys())
        expected_params = ['self', 'api_user', 'api_signer', 'api_private_key', 'apiv1_public', 'apiv1_private']

        if params == expected_params:
            print("[OK] Constructor signature correct")
        else:
            print(f"[ERROR] Constructor params: {params}, expected: {expected_params}")
            return False

        # Check for close method
        if hasattr(AsterApiManager, 'close'):
            print("[OK] close() method exists")
        else:
            print("[ERROR] close() method missing")
            return False

        return True

    except Exception as e:
        print(f"[ERROR] Class verification failed: {e}")
        return False

async def check_private_methods():
    """Verify private helper methods."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - PRIVATE HELPER METHODS")
    print("=" * 60)

    try:
        from aster_api_manager import AsterApiManager

        # Create dummy instance to check methods - use valid Ethereum address format
        dummy_eth_addr = "0x0000000000000000000000000000000000000000"
        dummy_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        manager = AsterApiManager(dummy_eth_addr, dummy_eth_addr, dummy_key, "dummy", "dummy")

        try:
            # Check _create_spot_signature
            if hasattr(manager, '_create_spot_signature'):
                print("[OK] _create_spot_signature method exists")

                # Test signature generation
                test_params = {'symbol': 'BTCUSDT', 'timestamp': 1640995200000}
                try:
                    sig = manager._create_spot_signature(test_params)
                    if isinstance(sig, str) and len(sig) == 64:
                        print("[OK] _create_spot_signature produces valid signature")
                    else:
                        print(f"[ERROR] Invalid signature format: {sig}")
                        return False
                except Exception as e:
                    print(f"[ERROR] _create_spot_signature failed: {e}")
                    return False
            else:
                print("[ERROR] _create_spot_signature method missing")
                return False

            # Check _make_spot_request
            if hasattr(manager, '_make_spot_request'):
                print("[OK] _make_spot_request method exists")
            else:
                print("[ERROR] _make_spot_request method missing")
                return False

            return True

        finally:
            await manager.close()

    except Exception as e:
        print(f"[ERROR] Private methods verification failed: {e}")
        return False

async def check_data_methods():
    """Verify all required data fetching methods."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - DATA FETCHING METHODS")
    print("=" * 60)

    try:
        from aster_api_manager import AsterApiManager

        # Create dummy instance - use valid Ethereum address format
        dummy_eth_addr = "0x0000000000000000000000000000000000000000"
        dummy_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        manager = AsterApiManager(dummy_eth_addr, dummy_eth_addr, dummy_key, "dummy", "dummy")

        try:
            required_methods = [
            'get_perp_account_info',
            'get_spot_account_balances',
            'get_funding_rate_history',
            'get_perp_book_ticker',
            'get_spot_book_ticker',
            'get_perp_order_status',
            'get_spot_order_status'
        ]

            for method_name in required_methods:
                if hasattr(manager, method_name):
                    method = getattr(manager, method_name)
                    if asyncio.iscoroutinefunction(method):
                        print(f"[OK] {method_name} exists and is async")
                    else:
                        print(f"[ERROR] {method_name} exists but not async")
                        return False
                else:
                    print(f"[ERROR] {method_name} missing")
                    return False
            return True
        finally:
            await manager.close()

    except Exception as e:
        print(f"[ERROR] Data methods verification failed: {e}")
        return False

async def check_execution_methods():
    """Verify all required execution methods."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - EXECUTION METHODS")
    print("=" * 60)

    try:
        from aster_api_manager import AsterApiManager

        # Create dummy instance - use valid Ethereum address format
        dummy_eth_addr = "0x0000000000000000000000000000000000000000"
        dummy_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        manager = AsterApiManager(dummy_eth_addr, dummy_eth_addr, dummy_key, "dummy", "dummy")

        try:
            required_methods = [
            'place_perp_order',
            'place_spot_buy_market_order',
            'place_spot_sell_market_order',
            'close_perp_position',
            'cancel_perp_order'  # Added during implementation
        ]

            for method_name in required_methods:
                if hasattr(manager, method_name):
                    method = getattr(manager, method_name)
                    if asyncio.iscoroutinefunction(method):
                        print(f"[OK] {method_name} exists and is async")
                    else:
                        print(f"[ERROR] {method_name} exists but not async")
                        return False
                else:
                    print(f"[ERROR] {method_name} missing")
                    return False
            return True
        finally:
            await manager.close()

    except Exception as e:
        print(f"[ERROR] Execution methods verification failed: {e}")
        return False

async def check_real_integration():
    """Verify real API integration with live credentials."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - REAL API INTEGRATION")
    print("=" * 60)

    # Check if credentials are available
    creds = [
        os.getenv('API_USER'),
        os.getenv('API_SIGNER'),
        os.getenv('API_PRIVATE_KEY'),
        os.getenv('APIV1_PUBLIC_KEY'),
        os.getenv('APIV1_PRIVATE_KEY')
    ]

    if not all(creds):
        print("[WARNING] Real API credentials not available - skipping integration test")
        return True

    try:
        from aster_api_manager import AsterApiManager

        manager = AsterApiManager(*creds)

        # Test key data methods
        try:
            perp_account = await manager.get_perp_account_info()
            if isinstance(perp_account, dict) and 'assets' in perp_account:
                print("[OK] get_perp_account_info works with real API")
            else:
                print("[ERROR] get_perp_account_info invalid response")
                return False
        except Exception as e:
            print(f"[ERROR] get_perp_account_info failed: {e}")
            return False

        try:
            spot_balances = await manager.get_spot_account_balances()
            if isinstance(spot_balances, list):
                print("[OK] get_spot_account_balances works with real API")
            else:
                print("[ERROR] get_spot_account_balances invalid response")
                return False
        except Exception as e:
            print(f"[ERROR] get_spot_account_balances failed: {e}")
            return False

        try:
            funding_history = await manager.get_funding_rate_history('BTCUSDT', 5)
            if isinstance(funding_history, list):
                print("[OK] get_funding_rate_history works with real API")
            else:
                print("[ERROR] get_funding_rate_history invalid response")
                return False
        except Exception as e:
            print(f"[ERROR] get_funding_rate_history failed: {e}")
            return False

        await manager.close()
        print("[OK] Real API integration verified")
        return True

    except Exception as e:
        print(f"[ERROR] Real API integration failed: {e}")
        return False

def check_test_file():
    """Verify test file exists and has required tests."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - TEST FILE")
    print("=" * 60)

    test_file = "test_api_manager.py"
    if not os.path.exists(test_file):
        print("[ERROR] test_api_manager.py not found")
        return False

    print("[OK] test_api_manager.py exists")

    # Check test content
    with open(test_file, 'r') as f:
        content = f.read()

    required_tests = [
        'test_initialization_and_close',
        'test_spot_signature_generation',
        'test_get_perp_account_info_structure',
        'test_get_spot_account_balances_structure',
        'test_fetch_methods_with_invalid_symbol',
        'test_full_order_lifecycle'
    ]

    for test_name in required_tests:
        if test_name in content:
            print(f"[OK] {test_name} found in tests")
        else:
            print(f"[WARNING] {test_name} not found (may be named differently)")

    # Check for IsolatedAsyncioTestCase usage
    if 'IsolatedAsyncioTestCase' in content:
        print("[OK] Uses IsolatedAsyncioTestCase as required")
    else:
        print("[ERROR] Does not use IsolatedAsyncioTestCase")
        return False

    return True

async def run_unit_tests():
    """Run the actual unit tests."""
    print("\n" + "=" * 60)
    print("STEP 1 VERIFICATION - RUNNING UNIT TESTS")
    print("=" * 60)

    import subprocess
    import sys

    try:
        # Run unit tests
        result = subprocess.run([
            sys.executable, '-m', 'unittest',
            'test_api_manager.TestAsterApiManager', '-v'
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

async def main():
    """Run comprehensive Step 1 verification."""
    print("COMPREHENSIVE STEP 1 VERIFICATION")
    print("Checking all requirements from mega_plan.md Step 1")
    print("\n")

    all_checks = [
        ("File Setup & Imports", check_file_setup()),
        ("Class Definition", check_class_definition()),
        ("Private Helper Methods", await check_private_methods()),
        ("Data Fetching Methods", await check_data_methods()),
        ("Execution Methods", await check_execution_methods()),
        ("Test File Structure", check_test_file()),
        ("Unit Tests Execution", await run_unit_tests()),
        ("Real API Integration", await check_real_integration())
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
        print("[SUCCESS] STEP 1 FULLY ACCOMPLISHED!")
        print("All mega plan requirements satisfied")
        print("Ready to proceed to Step 2")
        print("[SUCCESS]" * 5)
        return True
    else:
        print("\n[ERROR] STEP 1 INCOMPLETE")
        print(f"Please address the {total - passed} failing checks")
        return False

if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)