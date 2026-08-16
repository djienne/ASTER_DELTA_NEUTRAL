import unittest
import asyncio
import os
import hmac
import hashlib
import urllib.parse
from unittest.mock import AsyncMock, patch, MagicMock
from aster_api_manager import AsterApiManager


class TestAsterApiManager(unittest.IsolatedAsyncioTestCase):
    """
    Comprehensive test suite for AsterApiManager class.
    Tests both mocked functionality and live API integration.
    """

    def setUp(self):
        """Set up test fixtures with mock credentials."""
        # Mock credentials for testing
        self.api_user = "0x1234567890123456789012345678901234567890"
        self.api_signer = "0x0987654321098765432109876543210987654321"
        self.api_private_key = "0x" + "a" * 64  # Mock private key
        self.apiv1_public = "test_public_key"
        self.apiv1_private = "test_private_key"

        # Load real credentials from environment if available for integration tests
        self.real_api_user = os.getenv('API_USER')
        self.real_api_signer = os.getenv('API_SIGNER')
        self.real_api_private_key = os.getenv('API_PRIVATE_KEY')
        self.real_apiv1_public = os.getenv('APIV1_PUBLIC')
        self.real_apiv1_private = os.getenv('APIV1_PRIVATE')

    async def test_initialization_and_close(self):
        """Test 1: Initialization and Cleanup"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Assert initialization worked correctly
        self.assertIsNone(manager.session)  # Session is created lazily
        self.assertEqual(manager.api_user, self.api_user)
        self.assertEqual(manager.apiv1_public, self.apiv1_public)

        # Test cleanup (even when session is None)
        await manager.close()
        # Session is None initially, so no check for closed state

    def test_spot_signature_generation(self):
        """Test 2: Spot Authentication Signature"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Test with known parameters
        test_params = {
            'symbol': 'BTCUSDT',
            'timestamp': 1640995200000,
            'recvWindow': 5000
        }

        # Generate signature
        signature = manager._create_spot_signature(test_params)

        # Verify signature is a valid hex string
        self.assertIsInstance(signature, str)
        self.assertEqual(len(signature), 64)  # SHA256 hex digest length

        # Verify signature generation is deterministic
        signature2 = manager._create_spot_signature(test_params)
        self.assertEqual(signature, signature2)

        # Verify signature changes with different parameters
        test_params['symbol'] = 'ETHUSDT'
        signature3 = manager._create_spot_signature(test_params)
        self.assertNotEqual(signature, signature3)

    @patch('aiohttp.ClientSession.request')
    async def test_make_spot_request_unsigned(self, mock_request):
        """Test spot request without signature"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Mock response
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={'symbol': 'BTCUSDT'})
        mock_request.return_value.__aenter__.return_value = mock_response

        # Test unsigned request
        result = await manager._make_spot_request('GET', '/api/v1/ticker/bookTicker',
                                                {'symbol': 'BTCUSDT'}, signed=False)

        # Verify call was made correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], 'GET')  # method
        self.assertIn('/api/v1/ticker/bookTicker', call_args[0][1])  # URL

        # Verify headers contain API key
        headers = call_args[1]['headers']
        self.assertEqual(headers['X-MBX-APIKEY'], self.apiv1_public)

        # Verify response
        self.assertEqual(result, {'symbol': 'BTCUSDT'})

        await manager.close()

    @patch('aiohttp.ClientSession.request')
    async def test_make_spot_request_signed(self, mock_request):
        """Test spot request with signature"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Mock response
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={'balances': []})
        mock_request.return_value.__aenter__.return_value = mock_response

        # Test signed request
        result = await manager._make_spot_request('GET', '/api/v1/account', signed=True)

        # Verify call was made
        mock_request.assert_called_once()
        call_args = mock_request.call_args

        # Verify signature was added to params
        params = call_args[1]['params']
        self.assertIn('signature', params)
        self.assertIn('timestamp', params)
        self.assertIn('recvWindow', params)

        await manager.close()

    @patch('aster_api_manager.aiohttp.ClientSession')
    async def test_get_perp_leverage_mocked(self, mock_session_class):
        """Test 5: Get perpetual leverage (mocked)"""
        # Mock the session and response
        mock_session = AsyncMock()
        mock_session_class.return_value = mock_session

        # Mock position data response
        mock_positions = [
            {'symbol': 'BTCUSDT', 'leverage': '1.0'},
            {'symbol': 'ETHUSDT', 'leverage': '2.0'}
        ]

        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Mock the _signed_perp_request method
        manager._signed_perp_request = AsyncMock(return_value=mock_positions)

        # Test getting leverage for existing symbol
        leverage = await manager.get_perp_leverage('BTCUSDT')
        self.assertEqual(leverage, 1)

        # Test getting leverage for symbol with different leverage
        leverage = await manager.get_perp_leverage('ETHUSDT')
        self.assertEqual(leverage, 2)

        # Test getting leverage for non-existent symbol (should return default 1)
        leverage = await manager.get_perp_leverage('NONEXISTENT')
        self.assertEqual(leverage, 1)

        await manager.close()

    @patch('aster_api_manager.aiohttp.ClientSession')
    async def test_set_perp_leverage_mocked(self, mock_session_class):
        """Test 6: Set perpetual leverage (mocked)"""
        # Mock the session and response
        mock_session = AsyncMock()
        mock_session_class.return_value = mock_session

        # Mock leverage setting response
        mock_response = {'symbol': 'BTCUSDT', 'leverage': 1}

        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Mock the _make_spot_request method (leverage endpoint uses spot auth)
        manager._make_spot_request = AsyncMock(return_value=mock_response)

        # Test setting leverage to 1 (default for delta-neutral)
        response = await manager.set_perp_leverage('BTCUSDT')
        self.assertEqual(response['leverage'], 1)

        # Verify the correct parameters were sent
        manager._make_spot_request.assert_called_with(
            method='POST',
            path='/fapi/v1/leverage',
            params={'symbol': 'BTCUSDT', 'leverage': 1},
            signed=True,
            base_url='https://fapi.asterdex.com'
        )

        # Test setting custom leverage
        await manager.set_perp_leverage('BTCUSDT', 5)
        manager._make_spot_request.assert_called_with(
            method='POST',
            path='/fapi/v1/leverage',
            params={'symbol': 'BTCUSDT', 'leverage': 5},
            signed=True,
            base_url='https://fapi.asterdex.com'
        )

        await manager.close()

    @patch('aster_api_manager.aiohttp.ClientSession')
    async def test_analyze_current_positions_mocked(self, mock_session_class):
        """Test 7: Analyze current positions for delta-neutral detection"""
        # Mock the session and response
        mock_session = AsyncMock()
        mock_session_class.return_value = mock_session

        # Mock perpetual account info
        mock_perp_account = {
            'positions': [
                {
                    'symbol': 'BTCUSDT',
                    'positionAmt': '-1.0',  # Short 1 BTC
                    'markPrice': '50000.0'
                },
                {
                    'symbol': 'ETHUSDT',
                    'positionAmt': '-2.0',  # Short 2 ETH
                    'markPrice': '3000.0'
                }
            ]
        }

        # Mock spot balances
        mock_spot_balances = [
            {'asset': 'BTC', 'free': '1.0', 'locked': '0.0'},  # Long 1 BTC (balanced)
            {'asset': 'ETH', 'free': '1.95', 'locked': '0.0'},  # Long 1.95 ETH (2.5% imbalanced - above 2% threshold)
            {'asset': 'USDT', 'free': '1000.0', 'locked': '0.0'}
        ]

        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        # Mock exchange info
        mock_perp_info = {
            'symbols': [
                {
                    'symbol': 'BTCUSDT',
                    'baseAsset': 'BTC',
                    'quoteAsset': 'USDT'
                },
                {
                    'symbol': 'ETHUSDT',
                    'baseAsset': 'ETH',
                    'quoteAsset': 'USDT'
                }
            ]
        }

        # Mock all the required methods
        manager.get_perp_account_info = AsyncMock(return_value=mock_perp_account)
        manager.get_spot_account_balances = AsyncMock(return_value=mock_spot_balances)
        manager._get_perp_exchange_info = AsyncMock(return_value=mock_perp_info)
        manager._get_spot_exchange_info = AsyncMock(return_value=mock_perp_info)
        manager.get_perp_leverage = AsyncMock(return_value=1)

        # Test position analysis
        analysis = await manager.analyze_current_positions()

        # Verify BTCUSDT position (should be delta-neutral)
        btc_analysis = analysis['BTCUSDT']
        self.assertEqual(btc_analysis['spot_balance'], 1.0)
        self.assertEqual(btc_analysis['perp_position'], -1.0)
        self.assertEqual(btc_analysis['net_delta'], 0.0)  # 1.0 + (-1.0) = 0
        self.assertTrue(btc_analysis['is_delta_neutral'])
        self.assertAlmostEqual(btc_analysis['imbalance_pct'], 0.0, places=1)

        # Verify ETHUSDT position (should be imbalanced with 2% threshold)
        eth_analysis = analysis['ETHUSDT']
        self.assertEqual(eth_analysis['spot_balance'], 1.95)
        self.assertEqual(eth_analysis['perp_position'], -2.0)
        self.assertAlmostEqual(eth_analysis['net_delta'], -0.05, places=6)  # 1.95 + (-2.0) = -0.05
        self.assertFalse(eth_analysis['is_delta_neutral'])  # 2.5% > 2% threshold
        self.assertAlmostEqual(eth_analysis['imbalance_pct'], 2.5, places=1)  # 0.05/2.0 * 100

        await manager.close()


class TestAsterApiManagerIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Integration tests that require real API credentials.
    These tests will only run if environment variables are set.
    """

    def setUp(self):
        """Set up with real credentials from environment."""
        self.api_user = os.getenv('API_USER')
        self.api_signer = os.getenv('API_SIGNER')
        self.api_private_key = os.getenv('API_PRIVATE_KEY')
        self.apiv1_public = os.getenv('APIV1_PUBLIC')
        self.apiv1_private = os.getenv('APIV1_PRIVATE')

        # Skip tests if credentials not available
        self.skip_if_no_credentials()

    def skip_if_no_credentials(self):
        """Skip tests if real API credentials are not available."""
        if not all([self.api_user, self.api_signer, self.api_private_key,
                   self.apiv1_public, self.apiv1_private]):
            self.skipTest("Real API credentials not available in environment variables")

    async def test_get_perp_account_info_structure(self):
        """Test 3: Perpetuals Account Info Data Structure"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            response = await manager.get_perp_account_info()

            # Assert response structure
            self.assertIsInstance(response, dict)
            self.assertIn('assets', response)
            self.assertIn('positions', response)

            # Verify assets structure
            assets = response['assets']
            self.assertIsInstance(assets, list)
            if assets:  # If account has assets
                asset = assets[0]
                self.assertIn('asset', asset)
                self.assertIn('walletBalance', asset)

        finally:
            await manager.close()

    async def test_get_spot_account_balances_structure(self):
        """Test 3: Spot Account Balances Data Structure"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            balances = await manager.get_spot_account_balances()

            # Assert response structure
            self.assertIsInstance(balances, list)
            if balances:  # If account has balances
                balance = balances[0]
                self.assertIn('asset', balance)
                self.assertIn('free', balance)
                self.assertIn('locked', balance)

        finally:
            await manager.close()

    async def test_get_funding_rate_history_structure(self):
        """Test 3: Funding Rate History Data Structure"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            history = await manager.get_funding_rate_history('BTCUSDT', limit=10)

            # Assert response structure
            self.assertIsInstance(history, list)
            if history:  # If data available
                record = history[0]
                self.assertIn('symbol', record)
                self.assertIn('fundingRate', record)
                self.assertIn('fundingTime', record)

        finally:
            await manager.close()

    async def test_get_book_tickers_structure(self):
        """Test 3: Book Tickers Data Structure"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            # Test perpetuals book ticker
            perp_ticker = await manager.get_perp_book_ticker('BTCUSDT')
            self.assertIsInstance(perp_ticker, dict)
            self.assertIn('symbol', perp_ticker)
            self.assertIn('bidPrice', perp_ticker)
            self.assertIn('askPrice', perp_ticker)

            # Test spot book ticker
            spot_ticker = await manager.get_spot_book_ticker('BTCUSDT')
            self.assertIsInstance(spot_ticker, dict)
            self.assertIn('symbol', spot_ticker)
            self.assertIn('bidPrice', spot_ticker)
            self.assertIn('askPrice', spot_ticker)

        finally:
            await manager.close()

    async def test_fetch_methods_with_invalid_symbol(self):
        """Test 4: Edge Case - Invalid Symbol"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            # Test with invalid symbol - should raise an exception
            with self.assertRaises(Exception):
                await manager.get_perp_book_ticker('NOTASYMBOL')

            with self.assertRaises(Exception):
                await manager.get_spot_book_ticker('NOTASYMBOL')

        finally:
            await manager.close()

    async def test_transfer_methods_structure(self):
        """Test 6: Transfer Methods Structure and Validation"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            # Test invalid direction validation
            with self.assertRaises(ValueError):
                await manager.transfer_between_spot_and_perp('USDT', 10.0, 'INVALID_DIRECTION')

            # Test that rebalance method returns proper structure (without executing transfer)
            # We'll mock the balances to avoid real transfers
            original_get_spot = manager.get_spot_account_balances
            original_get_perp = manager.get_perp_account_info

            # Mock balanced accounts (no transfer needed)
            async def mock_spot_balances():
                return [{'asset': 'USDT', 'free': '100.0', 'locked': '0.0'}]

            async def mock_perp_account():
                return {
                    'assets': [{'asset': 'USDT', 'walletBalance': '100.0'}]
                }

            manager.get_spot_account_balances = mock_spot_balances
            manager.get_perp_account_info = mock_perp_account

            result = await manager.rebalance_usdt_50_50()

            # Verify structure
            self.assertIn('current_spot_usdt', result)
            self.assertIn('current_perp_usdt', result)
            self.assertIn('total_usdt', result)
            self.assertIn('target_each', result)
            self.assertIn('transfer_needed', result)
            self.assertIn('transfer_amount', result)

            # With balanced accounts, no transfer should be needed
            self.assertFalse(result['transfer_needed'])
            self.assertEqual(result['current_spot_usdt'], 100.0)
            self.assertEqual(result['current_perp_usdt'], 100.0)
            self.assertEqual(result['total_usdt'], 200.0)
            self.assertEqual(result['target_each'], 100.0)

            # Restore original methods
            manager.get_spot_account_balances = original_get_spot
            manager.get_perp_account_info = original_get_perp

        finally:
            await manager.close()

    async def test_rebalance_transfer_needed_calculation(self):
        """Test 7: Rebalance Transfer Calculation Logic"""
        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            original_get_spot = manager.get_spot_account_balances
            original_get_perp = manager.get_perp_account_info
            original_transfer = manager.transfer_between_spot_and_perp

            # Mock imbalanced accounts (spot has more)
            async def mock_spot_balances():
                return [{'asset': 'USDT', 'free': '150.0', 'locked': '0.0'}]

            async def mock_perp_account():
                return {
                    'assets': [{'asset': 'USDT', 'walletBalance': '50.0'}]
                }

            # Mock transfer to avoid real execution
            async def mock_transfer(asset, amount, direction):
                return {'tranId': 12345, 'status': 'SUCCESS'}

            manager.get_spot_account_balances = mock_spot_balances
            manager.get_perp_account_info = mock_perp_account
            manager.transfer_between_spot_and_perp = mock_transfer

            result = await manager.rebalance_usdt_50_50()

            # Should identify need for transfer from spot to perp
            self.assertTrue(result['transfer_needed'])
            self.assertEqual(result['current_spot_usdt'], 150.0)
            self.assertEqual(result['current_perp_usdt'], 50.0)
            self.assertEqual(result['total_usdt'], 200.0)
            self.assertEqual(result['target_each'], 100.0)
            self.assertEqual(result['transfer_amount'], 50.0)
            self.assertEqual(result['transfer_direction'], 'SPOT_TO_PERP')
            self.assertIsNotNone(result['transfer_result'])

            # Restore original methods
            manager.get_spot_account_balances = original_get_spot
            manager.get_perp_account_info = original_get_perp
            manager.transfer_between_spot_and_perp = original_transfer

        finally:
            await manager.close()

    async def test_transfer_execution_live(self):
        """
        Test 8: Live Transfer Execution (REQUIRES USER CONFIRMATION)
        WARNING: This test executes REAL transfers!
        """
        print("\n" + "="*80)
        print("**WARNING: This test will execute REAL transfers between accounts!**")
        print("This will move actual USDT between your spot and perpetual accounts.")
        print("Use a dedicated test account with minimal funds.")
        print("="*80)

        # Prompt for user confirmation
        try:
            response = input("\nPress 'y' and Enter to proceed with live transfer test (any other key to skip): ")
            if response.lower() != 'y':
                self.skipTest("Live transfer test skipped by user")
        except EOFError:
            self.skipTest("Live transfer test skipped - not running in interactive mode")

        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            # Get current balances
            print("Fetching current balances...")
            spot_balances = await manager.get_spot_account_balances()
            perp_account = await manager.get_perp_account_info()

            spot_usdt = next((float(b.get('free', 0)) for b in spot_balances if b.get('asset') == 'USDT'), 0.0)
            perp_assets = perp_account.get('assets', [])
            perp_usdt = next((float(a.get('walletBalance', 0)) for a in perp_assets if a.get('asset') == 'USDT'), 0.0)

            print(f"Current USDT balances - Spot: ${spot_usdt:.2f}, Perp: ${perp_usdt:.2f}")

            # Only proceed if we have sufficient balance for test transfer
            total_usdt = spot_usdt + perp_usdt
            if total_usdt < 10.0:
                self.skipTest(f"Insufficient USDT balance for test: ${total_usdt:.2f} (need at least $10)")

            # Test small transfer (1 USDT) from the account with more balance
            test_amount = 1.0
            if spot_usdt > perp_usdt:
                direction = 'SPOT_TO_PERP'
                print(f"Testing transfer of ${test_amount} from spot to perpetual...")
            else:
                direction = 'PERP_TO_SPOT'
                print(f"Testing transfer of ${test_amount} from perpetual to spot...")

            # Execute transfer
            transfer_result = await manager.transfer_between_spot_and_perp('USDT', test_amount, direction)

            # Verify transfer response
            self.assertIn('tranId', transfer_result)
            self.assertIn('status', transfer_result)
            print(f"Transfer completed - Transaction ID: {transfer_result['tranId']}, Status: {transfer_result['status']}")

            # Wait for transfer to process
            print("Waiting 3 seconds for transfer to process...")
            await asyncio.sleep(3)

            # Verify balances changed
            print("Verifying balance changes...")
            new_spot_balances = await manager.get_spot_account_balances()
            new_perp_account = await manager.get_perp_account_info()

            new_spot_usdt = next((float(b.get('free', 0)) for b in new_spot_balances if b.get('asset') == 'USDT'), 0.0)
            new_perp_assets = new_perp_account.get('assets', [])
            new_perp_usdt = next((float(a.get('walletBalance', 0)) for a in new_perp_assets if a.get('asset') == 'USDT'), 0.0)

            print(f"New USDT balances - Spot: ${new_spot_usdt:.2f}, Perp: ${new_perp_usdt:.2f}")

            # Check that total balance is preserved (allowing for small rounding differences)
            new_total = new_spot_usdt + new_perp_usdt
            self.assertAlmostEqual(total_usdt, new_total, places=1)
            print("✓ Total balance preserved")

            # Reverse the transfer to restore original state
            print(f"Reversing transfer to restore original state...")
            reverse_direction = 'PERP_TO_SPOT' if direction == 'SPOT_TO_PERP' else 'SPOT_TO_PERP'
            reverse_result = await manager.transfer_between_spot_and_perp('USDT', test_amount, reverse_direction)
            print(f"Reverse transfer completed - Transaction ID: {reverse_result['tranId']}")

        finally:
            await manager.close()

    async def test_full_order_lifecycle(self):
        """
        Test 5: Controlled Execution Workflow
        WARNING: This test executes REAL trades!
        """
        print("\n" + "="*80)
        print("**WARNING: This test will execute REAL trades on the exchange!**")
        print("Use a dedicated test account with minimal funds.")
        print("="*80)

        # Prompt for user confirmation (skip if not interactive)
        try:
            response = input("\nPress 'y' and Enter to proceed with live execution test (any other key to skip): ")
            if response.lower() != 'y':
                self.skipTest("Live execution test skipped by user")
        except EOFError:
            self.skipTest("Live execution test skipped - not running in interactive mode")

        manager = AsterApiManager(
            self.api_user, self.api_signer, self.api_private_key,
            self.apiv1_public, self.apiv1_private
        )

        try:
            # Get current market price for BTCUSDT
            ticker = await manager.get_perp_book_ticker('BTCUSDT')
            current_price = float(ticker['bidPrice'])

            # Place a far out-of-the-money limit order (should not fill)
            test_price = str(current_price * 0.5)  # 50% below market
            test_quantity = "0.001"  # Very small quantity

            print(f"Placing test order: {test_quantity} BTC at ${test_price}")
            order_response = await manager.place_perp_order(
                'BTCUSDT', test_price, test_quantity, 'BUY'
            )

            # Verify order was placed
            self.assertIn('orderId', order_response)
            order_id = order_response['orderId']
            print(f"Order placed successfully. Order ID: {order_id}")

            # Wait a moment
            await asyncio.sleep(2)

            # Check order status
            status_response = await manager.get_perp_order_status('BTCUSDT', order_id)
            self.assertEqual(status_response['status'], 'NEW')
            print(f"Order status confirmed: {status_response['status']}")

            # Cancel the order
            print("Canceling test order...")
            cancel_response = await manager.cancel_perp_order('BTCUSDT', order_id)
            print(f"Cancel response: {cancel_response}")

            # Wait a moment
            await asyncio.sleep(2)

            # Verify cancellation
            final_status = await manager.get_perp_order_status('BTCUSDT', order_id)
            self.assertEqual(final_status['status'], 'CANCELED')
            print(f"Order successfully canceled. Final status: {final_status['status']}")

        finally:
            await manager.close()


if __name__ == '__main__':
    # Instructions for running tests
    print("AsterApiManager Test Suite")
    print("=" * 50)
    print("Unit tests will run with mocked data.")
    print("Integration tests require real API credentials in environment variables:")
    print("  - API_USER")
    print("  - API_SIGNER")
    print("  - API_PRIVATE_KEY")
    print("  - APIV1_PUBLIC")
    print("  - APIV1_PRIVATE")
    print()
    print("To run integration tests, set these environment variables and run:")
    print("  python test_api_manager.py")
    print()

    unittest.main(verbosity=2)