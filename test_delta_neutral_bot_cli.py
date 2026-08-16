#!/usr/bin/env python3
"""
Test suite for CLI functionality in delta_neutral_bot.py
"""

import unittest
import unittest.mock
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from io import StringIO
import argparse

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from delta_neutral_bot import check_available_pairs, check_funding_rates, check_current_positions, check_spot_assets, check_futures_positions, main
from aster_api_manager import AsterApiManager


class TestDeltaNeutralBotCLI(unittest.TestCase):
    """Test CLI functionality of the delta-neutral bot."""

    def setUp(self):
        """Set up test environment with mocked API manager."""
        self.mock_api_manager = AsyncMock(spec=AsterApiManager)

        # Mock environment variables
        self.env_vars = {
            'API_USER': 'test_user',
            'API_SIGNER': 'test_signer',
            'API_PRIVATE_KEY': 'test_private_key',
            'APIV1_PUBLIC_KEY': 'test_public_key',
            'APIV1_PRIVATE_KEY': 'test_private_key'
        }

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_available_pairs_success(self, mock_getenv, mock_api_manager_class):
        """Test successful pair discovery via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock API responses
        mock_api_instance.get_available_spot_symbols.return_value = ['BTCUSDT', 'ETHUSDT', 'ASTERUSDT']
        mock_api_instance.get_available_perp_symbols.return_value = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_available_pairs()

        # Verify API calls
        mock_api_instance.get_available_spot_symbols.assert_called_once()
        mock_api_instance.get_available_perp_symbols.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains expected pairs (intersection: BTCUSDT, ETHUSDT)
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('BTCUSDT', output_text)
        self.assertIn('ETHUSDT', output_text)
        self.assertNotIn('ASTERUSDT', output_text)  # Only in spot
        self.assertNotIn('SOLUSDT', output_text)    # Only in perp

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_available_pairs_empty_intersection(self, mock_getenv, mock_api_manager_class):
        """Test pair discovery when no pairs are available in both markets."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock API responses with no intersection
        mock_api_instance.get_available_spot_symbols.return_value = ['BTCUSDT', 'ETHUSDT']
        mock_api_instance.get_available_perp_symbols.return_value = ['SOLUSDT', 'ADAUSDT']
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_available_pairs()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('No symbols are currently available', output_text)

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_funding_rates_success(self, mock_getenv, mock_api_manager_class):
        """Test successful funding rate fetching via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock API responses
        mock_api_instance.get_available_spot_symbols.return_value = ['BTCUSDT', 'ETHUSDT']
        mock_api_instance.get_available_perp_symbols.return_value = ['BTCUSDT', 'ETHUSDT']

        # Mock funding rate responses
        mock_api_instance.get_funding_rate_history.side_effect = [
            [{'fundingRate': '0.0001'}],  # BTC: 0.01% = ~10.95% APR
            [{'fundingRate': '-0.0002'}]  # ETH: -0.02% = ~-21.9% APR
        ]
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_funding_rates()

        # Verify API calls
        mock_api_instance.get_available_spot_symbols.assert_called_once()
        mock_api_instance.get_available_perp_symbols.assert_called_once()
        self.assertEqual(mock_api_instance.get_funding_rate_history.call_count, 2)
        mock_api_instance.close.assert_called_once()

        # Verify output contains funding rate data
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('BTCUSDT', output_text)
        self.assertIn('ETHUSDT', output_text)
        self.assertIn('Summary', output_text)

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_funding_rates_api_error(self, mock_getenv, mock_api_manager_class):
        """Test funding rate fetching when API calls fail."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock API to return None (failure)
        mock_api_instance.get_available_spot_symbols.return_value = None
        mock_api_instance.get_available_perp_symbols.return_value = ['BTCUSDT']
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_funding_rates()

        # Verify error message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('ERROR: Could not retrieve symbol lists', output_text)

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--pairs'])
    @patch('delta_neutral_bot.check_available_pairs')
    def test_main_pairs_argument(self, mock_check_pairs, mock_getenv):
        """Test main function with --pairs argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_check_pairs.return_value = asyncio.Future()
        mock_check_pairs.return_value.set_result(None)

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--funding-rates'])
    @patch('delta_neutral_bot.check_funding_rates')
    def test_main_funding_rates_argument(self, mock_check_funding, mock_getenv):
        """Test main function with --funding-rates argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_check_funding.return_value = asyncio.Future()
        mock_check_funding.return_value.set_result(None)

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_current_positions_success(self, mock_getenv, mock_api_manager_class):
        """Test successful position analysis via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock API responses
        mock_api_instance.analyze_current_positions.return_value = {
            'BTCUSDT': {
                'symbol': 'BTCUSDT',
                'spot_balance': 0.5,
                'perp_position': -0.5,
                'is_delta_neutral': True,
                'imbalance_pct': 2.0,
                'net_delta': 0.0,
                'position_value_usd': 15000.0
            }
        }

        mock_api_instance.get_spot_account_balances.return_value = [
            {'asset': 'USDT', 'free': '1000.0', 'locked': '0.0'},
            {'asset': 'BTC', 'free': '0.5', 'locked': '0.0'}
        ]

        mock_api_instance.get_perp_account_info.return_value = {
            'assets': [
                {'asset': 'USDT', 'walletBalance': '5000.0'},
                {'asset': 'USDC', 'walletBalance': '0.0'},
                {'asset': 'USDF', 'walletBalance': '0.0'}
            ]
        }

        mock_api_instance.get_funding_rate_history.return_value = [{'fundingRate': '0.0001'}]
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_current_positions()

        # Verify API calls
        mock_api_instance.analyze_current_positions.assert_called_once()
        mock_api_instance.get_spot_account_balances.assert_called_once()
        mock_api_instance.get_perp_account_info.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains position data
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('PORTFOLIO SUMMARY', output_text)
        self.assertIn('DELTA-NEUTRAL POSITIONS', output_text)
        self.assertIn('BTCUSDT', output_text)

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_current_positions_no_positions(self, mock_getenv, mock_api_manager_class):
        """Test position analysis when no positions exist."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock empty analysis results
        mock_api_instance.analyze_current_positions.return_value = {}
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_current_positions()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('No position analysis data available', output_text)

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--positions'])
    @patch('delta_neutral_bot.check_current_positions')
    def test_main_positions_argument(self, mock_check_positions, mock_getenv):
        """Test main function with --positions argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_check_positions.return_value = asyncio.Future()
        mock_check_positions.return_value.set_result(None)

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_spot_assets_success(self, mock_getenv, mock_api_manager_class):
        """Test successful spot assets fetching via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock spot balances response
        mock_api_instance.get_spot_account_balances.return_value = [
            {'asset': 'USDT', 'free': '1000.0', 'locked': '0.0'},
            {'asset': 'BTC', 'free': '0.5', 'locked': '0.0'},
            {'asset': 'ETH', 'free': '0.0', 'locked': '2.0'}
        ]

        # Mock price responses for non-stablecoins
        mock_api_instance.get_spot_book_ticker.side_effect = [
            {'bidPrice': '30000.0'},  # BTCUSDT
            Exception("No market"),   # BTCUSDC
            Exception("No market"),   # BTCBUSD
            {'bidPrice': '2000.0'},   # ETHUSDT
            Exception("No market"),   # ETHUSDC
            Exception("No market")    # ETHBUSD
        ]

        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_spot_assets()

        # Verify API calls
        mock_api_instance.get_spot_account_balances.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains asset data
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('SPOT ASSET BALANCES', output_text)
        self.assertIn('USDT', output_text)
        self.assertIn('BTC', output_text)
        self.assertIn('ETH', output_text)

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_spot_assets_no_balances(self, mock_getenv, mock_api_manager_class):
        """Test spot assets when no balances exist."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock empty balances
        mock_api_instance.get_spot_account_balances.return_value = []
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_spot_assets()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('No spot balance data available', output_text)

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--spot-assets'])
    @patch('delta_neutral_bot.check_spot_assets')
    def test_main_spot_assets_argument(self, mock_check_spot_assets, mock_getenv):
        """Test main function with --spot-assets argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_check_spot_assets.return_value = asyncio.Future()
        mock_check_spot_assets.return_value.set_result(None)

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_futures_positions_success(self, mock_getenv, mock_api_manager_class):
        """Test successful futures positions fetching via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock perpetual account info with positions
        mock_api_instance.get_perp_account_info.return_value = {
            'assets': [
                {'asset': 'USDT', 'walletBalance': '1000.0'},
                {'asset': 'USDC', 'walletBalance': '0.0'}
            ],
            'positions': [
                {
                    'symbol': 'BTCUSDT',
                    'positionAmt': '0.5',
                    'entryPrice': '30000.0',
                    'unrealizedProfit': '500.0',
                    'leverage': '2'
                },
                {
                    'symbol': 'ETHUSDT',
                    'positionAmt': '-1.0',
                    'entryPrice': '2000.0',
                    'unrealizedProfit': '-100.0',
                    'leverage': '3'
                }
            ]
        }

        # Mock price responses
        mock_api_instance.get_perp_book_ticker.side_effect = [
            {'bidPrice': '31000.0', 'askPrice': '31000.0'},  # BTCUSDT
            {'bidPrice': '1900.0', 'askPrice': '1900.0'}     # ETHUSDT
        ]

        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_futures_positions()

        # Verify API calls
        mock_api_instance.get_perp_account_info.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains futures data
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('FUTURES/PERPETUAL POSITIONS', output_text)
        self.assertIn('BTCUSDT', output_text)
        self.assertIn('ETHUSDT', output_text)
        self.assertIn('PnL %', output_text)

    @patch('delta_neutral_bot.AsterApiManager')
    @patch('os.getenv')
    async def test_check_futures_positions_no_positions(self, mock_getenv, mock_api_manager_class):
        """Test futures positions when no active positions exist."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Mock empty positions
        mock_api_instance.get_perp_account_info.return_value = {
            'assets': [{'asset': 'USDT', 'walletBalance': '1000.0'}],
            'positions': []
        }
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_futures_positions()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        output_text = ' '.join(print_calls)
        self.assertIn('No active futures positions found', output_text)

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--futures'])
    @patch('delta_neutral_bot.check_futures_positions')
    def test_main_futures_argument(self, mock_check_futures, mock_getenv):
        """Test main function with --futures argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_check_futures.return_value = asyncio.Future()
        mock_check_futures.return_value.set_result(None)

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--help'])
    def test_main_help_argument(self, mock_getenv):
        """Test main function with --help argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)

        # --help should cause SystemExit
        with self.assertRaises(SystemExit):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                main()
                help_output = mock_stdout.getvalue()
                self.assertIn('--pairs', help_output)
                self.assertIn('--funding-rates', help_output)
                self.assertIn('--positions', help_output)
                self.assertIn('--spot-assets', help_output)
                self.assertIn('--futures', help_output)

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py'])
    def test_main_missing_env_vars(self, mock_getenv):
        """Test main function with missing environment variables."""
        # Return None for all environment variables
        mock_getenv.return_value = None

        # Should exit with error
        with self.assertRaises(SystemExit):
            with patch('builtins.print') as mock_print:
                main()
                print_calls = [call[0][0] for call in mock_print.call_args_list]
                output_text = ' '.join(print_calls)
                self.assertIn('ERROR: Not all required environment variables', output_text)


class TestAsyncRunner(unittest.TestCase):
    """Helper class to run async tests."""

    def run_async_test(self, coro):
        """Run an async test."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_check_available_pairs_async(self):
        """Run the async test for check_available_pairs."""
        test_instance = TestDeltaNeutralBotCLI()
        test_instance.setUp()
        self.run_async_test(test_instance.test_check_available_pairs_success())

    def test_check_funding_rates_async(self):
        """Run the async test for check_funding_rates."""
        test_instance = TestDeltaNeutralBotCLI()
        test_instance.setUp()
        self.run_async_test(test_instance.test_check_funding_rates_success())

    def test_check_current_positions_async(self):
        """Run the async test for check_current_positions."""
        test_instance = TestDeltaNeutralBotCLI()
        test_instance.setUp()
        self.run_async_test(test_instance.test_check_current_positions_success())

    def test_check_spot_assets_async(self):
        """Run the async test for check_spot_assets."""
        test_instance = TestDeltaNeutralBotCLI()
        test_instance.setUp()
        self.run_async_test(test_instance.test_check_spot_assets_success())

    def test_check_futures_positions_async(self):
        """Run the async test for check_futures_positions."""
        test_instance = TestDeltaNeutralBotCLI()
        test_instance.setUp()
        self.run_async_test(test_instance.test_check_futures_positions_success())


if __name__ == '__main__':
    # Run both sync and async tests
    unittest.main(verbosity=2)