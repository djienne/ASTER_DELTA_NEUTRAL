#!/usr/bin/env python3
"""
Script to run integration tests with credentials from .env file
"""

import os
import sys
import unittest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import test module after loading environment
from test_api_manager import TestAsterApiManagerIntegration

if __name__ == '__main__':
    # Check if credentials are loaded
    credentials = [
        'API_USER', 'API_SIGNER', 'API_PRIVATE_KEY',
        'APIV1_PUBLIC_KEY', 'APIV1_PRIVATE_KEY'
    ]

    print("Checking credentials from .env file:")
    for cred in credentials:
        value = os.getenv(cred)
        if value:
            print(f"[OK] {cred}: {value[:10]}..." if len(value) > 10 else f"[OK] {cred}: {value}")
        else:
            print(f"[MISSING] {cred}: Not found")

    print("\nRunning integration tests...")

    # Fix the environment variable names to match what the test expects
    if os.getenv('APIV1_PUBLIC_KEY'):
        os.environ['APIV1_PUBLIC'] = os.getenv('APIV1_PUBLIC_KEY')
    if os.getenv('APIV1_PRIVATE_KEY'):
        os.environ['APIV1_PRIVATE'] = os.getenv('APIV1_PRIVATE_KEY')

    # Run the integration tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestAsterApiManagerIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with error code if tests failed
    sys.exit(0 if result.wasSuccessful() else 1)