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

from delta_neutral_bot import check_available_pairs, check_funding_rates, check_current_positions, check_spot_assets, check_perpetual_positions, main
from aster_api_manager import AsterApiManager


def sample_portfolio_payload():
    """The shape get_comprehensive_portfolio_data() returns.

    `is_delta_neutral` is the STRUCTURAL flag (both legs present); `is_balanced`
    is the separate health question. They used to be one flag, which made a
    drifted position vanish from both the health check and the closeable list.
    """
    return {
        'perp_account_info': {
            'assets': [
                {'asset': 'USDT', 'walletBalance': '5000.0'},
                {'asset': 'USDC', 'walletBalance': '0.0'},
                {'asset': 'USDF', 'walletBalance': '0.0'},
            ]
        },
        'raw_perp_positions': [
            {'symbol': 'BTCUSDT', 'positionAmt': '-0.5', 'markPrice': '30000.0',
             'unrealizedProfit': '12.5', 'liquidationPrice': '0', 'leverage': '1'},
        ],
        'spot_balances': [
            {'asset': 'USDT', 'free': '1000.0', 'locked': '0.0'},
            {'asset': 'BTC', 'free': '0.5', 'locked': '0.0'},
        ],
        'analyzed_positions': [
            {'symbol': 'BTCUSDT', 'spot_balance': 0.5, 'perp_position': -0.5,
             'is_delta_neutral': True, 'is_balanced': True, 'imbalance_pct': 0.0,
             'net_delta': 0.0, 'position_value_usd': 15000.0, 'leverage': 1},
        ],
    }


class TestDeltaNeutralBotCLI(unittest.IsolatedAsyncioTestCase):
    """Test CLI functionality of the delta-neutral bot.

    IsolatedAsyncioTestCase, not TestCase. As a plain TestCase the `async def`
    tests below were collected, called, and handed back a coroutine that was never
    awaited -- so they reported PASS without executing a single assertion. The
    separate TestAsyncRunner class existed to work around that by driving five of
    them by hand; it is gone now that the async tests run properly here.
    """

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

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_available_pairs_success(self, mock_getenv, mock_api_manager_class):
        """Test successful pair discovery via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # The intersection is computed inside discover_delta_neutral_pairs(); this
        # test used to mock get_available_spot_symbols/get_available_perp_symbols,
        # which check_available_pairs has not called since the CLI refactor.
        mock_api_instance.discover_delta_neutral_pairs.return_value = ['BTCUSDT', 'ETHUSDT']
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_available_pairs()

        # Verify API calls
        mock_api_instance.discover_delta_neutral_pairs.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains the discovered pairs
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('BTCUSDT', output_text)
        self.assertIn('ETHUSDT', output_text)

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_available_pairs_empty_intersection(self, mock_getenv, mock_api_manager_class):
        """Test pair discovery when no pairs are available in both markets."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # No pairs available in both markets.
        mock_api_instance.discover_delta_neutral_pairs.return_value = []
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_available_pairs()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('No symbols are currently available', output_text)

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_funding_rates_success(self, mock_getenv, mock_api_manager_class):
        """Test successful funding rate fetching via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Discovery, rate fetching and annualization all happen inside
        # get_all_funding_rates(). Each row now also carries the funding interval,
        # because Aster runs 1h/4h/8h simultaneously and the APR depends on it.
        mock_api_instance.get_all_funding_rates.return_value = [
            {'symbol': 'BTCUSDT', 'rate': 0.0001, 'apr': 10.95,
             'interval_hours': 8.0, 'interval_source': 'api_field'},
            {'symbol': 'ETHUSDT', 'rate': -0.0002, 'apr': -21.9,
             'interval_hours': 4.0, 'interval_source': 'api_field'},
        ]
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_funding_rates()

        # Verify API calls
        mock_api_instance.get_all_funding_rates.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains funding rate data, including the cadence
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('BTCUSDT', output_text)
        self.assertIn('ETHUSDT', output_text)
        self.assertIn('8h', output_text)
        self.assertIn('4h', output_text)

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_funding_rates_api_error(self, mock_getenv, mock_api_manager_class):
        """Test funding rate fetching when API calls fail."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # No rows come back at all (discovery failed, or every symbol was skipped
        # because its funding interval could not be resolved).
        mock_api_instance.get_all_funding_rates.return_value = []
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_funding_rates()

        # Verify the user is told, rather than shown an empty table
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertTrue(
            'No funding rate data' in output_text or 'ERROR' in output_text,
            f"expected an explicit empty/error message, got: {output_text!r}")

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--pairs'])
    @patch('delta_neutral_bot.check_available_pairs')
    def test_main_pairs_argument(self, mock_check_pairs, mock_getenv):
        """Test main function with --pairs argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        # No real coroutine needed: asyncio.run is patched below, so nothing awaits this.
        # A bare asyncio.Future() here required an ambient event loop, which fails once
        # any IsolatedAsyncioTestCase in the suite has closed its loop.
        mock_check_pairs.return_value = None

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
        # No real coroutine needed: asyncio.run is patched below, so nothing awaits this.
        # A bare asyncio.Future() here required an ambient event loop, which fails once
        # any IsolatedAsyncioTestCase in the suite has closed its loop.
        mock_check_funding.return_value = None

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_current_positions_success(self, mock_getenv, mock_api_manager_class):
        """Test successful position analysis via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # One call now returns the whole payload; the CLI stopped assembling it
        # from analyze_current_positions + get_spot_account_balances +
        # get_perp_account_info during the refactor.
        mock_api_instance.get_comprehensive_portfolio_data.return_value = \
            sample_portfolio_payload()
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_current_positions()

        # Verify API calls
        mock_api_instance.get_comprehensive_portfolio_data.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains position data
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('PORTFOLIO SUMMARY', output_text)
        self.assertIn('DELTA-NEUTRAL POSITIONS', output_text)
        self.assertIn('BTCUSDT', output_text)

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_current_positions_no_positions(self, mock_getenv, mock_api_manager_class):
        """Test position analysis when no positions exist."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Portfolio fetch returns nothing at all.
        mock_api_instance.get_comprehensive_portfolio_data.return_value = {}
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_current_positions()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('No portfolio data available', output_text)

    @patch('os.getenv')
    @patch('sys.argv', ['delta_neutral_bot.py', '--positions'])
    @patch('delta_neutral_bot.check_current_positions')
    def test_main_positions_argument(self, mock_check_positions, mock_getenv):
        """Test main function with --positions argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        # No real coroutine needed: asyncio.run is patched below, so nothing awaits this.
        # A bare asyncio.Future() here required an ambient event loop, which fails once
        # any IsolatedAsyncioTestCase in the suite has closed its loop.
        mock_check_positions.return_value = None

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_spot_assets_success(self, mock_getenv, mock_api_manager_class):
        """Test successful spot assets fetching via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Balances and prices arrive together in the comprehensive payload.
        payload = sample_portfolio_payload()
        payload['spot_balances'] = [
            {'asset': 'USDT', 'free': '1000.0', 'locked': '0.0', 'usd_value': 1000.0},
            {'asset': 'BTC', 'free': '0.5', 'locked': '0.0', 'usd_value': 15000.0},
            {'asset': 'ETH', 'free': '0.0', 'locked': '2.0', 'usd_value': 4000.0},
        ]
        mock_api_instance.get_comprehensive_portfolio_data.return_value = payload
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_spot_assets()

        # Verify API calls
        mock_api_instance.get_comprehensive_portfolio_data.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains asset data. The table lists non-stable holdings;
        # USDT is deliberately excluded from it, so asserting on USDT here was
        # asserting the opposite of the intended behaviour.
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('Spot Balances', output_text)
        self.assertIn('BTC', output_text)
        self.assertIn('ETH', output_text)

    @patch('cli_commands.AsterApiManager')
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
        # No real coroutine needed: asyncio.run is patched below, so nothing awaits this.
        # A bare asyncio.Future() here required an ambient event loop, which fails once
        # any IsolatedAsyncioTestCase in the suite has closed its loop.
        mock_check_spot_assets.return_value = None

        # Mock asyncio.run to avoid actually running async code
        with patch('asyncio.run') as mock_asyncio_run:
            main()
            mock_asyncio_run.assert_called_once()

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_perpetual_positions_success(self, mock_getenv, mock_api_manager_class):
        """Test successful futures positions fetching via CLI."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Positions and marks arrive together in the comprehensive payload.
        payload = sample_portfolio_payload()
        # Numeric fields are numbers, matching what get_comprehensive_portfolio_data
        # stores after resolving book tickers. The renderer formats mark price and
        # leverage with %f, so strings raise "Unknown format code 'f'".
        payload['raw_perp_positions'] = [
            {'symbol': 'BTCUSDT', 'positionAmt': '0.5', 'entryPrice': '30000.0',
             'markPrice': 31000.0, 'unrealizedProfit': '500.0', 'leverage': 2,
             'liquidationPrice': '0'},
            {'symbol': 'ETHUSDT', 'positionAmt': '-1.0', 'entryPrice': '2000.0',
             'markPrice': 1900.0, 'unrealizedProfit': '-100.0', 'leverage': 3,
             'liquidationPrice': '0'},
        ]
        mock_api_instance.get_comprehensive_portfolio_data.return_value = payload
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_perpetual_positions()

        # Verify API calls
        mock_api_instance.get_comprehensive_portfolio_data.assert_called_once()
        mock_api_instance.close.assert_called_once()

        # Verify output contains futures data
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('BTCUSDT', output_text)
        self.assertIn('ETHUSDT', output_text)

    @patch('cli_commands.AsterApiManager')
    @patch('os.getenv')
    async def test_check_perpetual_positions_no_positions(self, mock_getenv, mock_api_manager_class):
        """Test futures positions when no active positions exist."""
        # Setup mocks
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        mock_api_instance = AsyncMock()
        mock_api_manager_class.return_value = mock_api_instance

        # Account funded, but no open perp positions.
        payload = sample_portfolio_payload()
        payload['raw_perp_positions'] = []
        payload['analyzed_positions'] = []
        mock_api_instance.get_comprehensive_portfolio_data.return_value = payload
        mock_api_instance.close = AsyncMock()

        # Capture output
        with patch('builtins.print') as mock_print:
            await check_perpetual_positions()

        # Verify warning message
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        output_text = ' '.join(str(c) for c in print_calls)
        self.assertIn('No active perpetual positions', output_text)

    @patch('os.getenv')
    # The flag is --perpetual; --futures was never a valid argument, so argparse
    # exited with code 2 before main() could dispatch anything.
    @patch('sys.argv', ['delta_neutral_bot.py', '--perpetual'])
    @patch('delta_neutral_bot.check_perpetual_positions')
    def test_main_futures_argument(self, mock_check_futures, mock_getenv):
        """Test main function with --perpetual argument."""
        # Setup environment variables
        mock_getenv.side_effect = lambda key: self.env_vars.get(key)
        # No real coroutine needed: asyncio.run is patched below, so nothing awaits this.
        # A bare asyncio.Future() here required an ambient event loop, which fails once
        # any IsolatedAsyncioTestCase in the suite has closed its loop.
        mock_check_futures.return_value = None

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


# TestAsyncRunner used to live here: five sync wrappers that hand-built an event
# loop and drove the async tests above, because as a plain TestCase they never ran
# on their own. TestDeltaNeutralBotCLI is now an IsolatedAsyncioTestCase, so they
# run directly and the wrappers were duplicate coverage that also left a closed
# event loop behind for later tests in the suite.


if __name__ == '__main__':
    unittest.main(verbosity=2)
