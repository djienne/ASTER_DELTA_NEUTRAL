import asyncio
import aiohttp
import os
import time
import hmac
import hashlib
import json
import logging
import urllib.parse
import math
from datetime import datetime
from two_leg import (
    HaltedError,
    LegSpec,
    assert_not_halted,
    execute_two_leg,
)
from funding_economics import (
    VERIFIED_TAKER_BPS,
    FundingInterval,
    FundingIntervalResolver,
    IntervalResolutionError,
    TradeCostModel,
    VenueCosts,
    annualize,
    evaluate_entry,
)
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_abi import encode
from strategy_logic import DeltaNeutralLogic
from utils import truncate

# Base URLs for the APIs
FUTURES_BASE_URL = "https://fapi.asterdex.com"
SPOT_BASE_URL = "https://sapi.asterdex.com"

# Where the halt sentinel lives.
#
# It must survive a container restart, so it is written to a directory intended
# to be a mounted volume rather than to the process's working directory. A halt
# that evaporates on `docker compose up` defeats the entire mechanism: the whole
# point is that the bot refuses to trade until a human has checked both legs.
DATA_DIR = os.getenv(
    "ASTER_DN_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)
HALT_PATH = os.path.join(DATA_DIR, "halt.json")

# Cost inputs for the entry gate.
#
# A full cycle is FOUR taker fills: buy spot + sell perp to open, then the reverse
# to close. Break-even APR is roundtrip_pct * (8760 / hold_hours), so it scales as
# 1/hold_hours -- which is why the hold length is the lever that matters and a
# higher APR threshold alone is not. At the default 4bps taker + 2bps slippage the
# round trip is 0.24%, so an 8h hold needs ~263% APR to break even while a 72h
# hold needs ~29%.
ASTER_SLIPPAGE_BPS = float(os.getenv("ASTER_DN_SLIPPAGE_BPS", "2.0"))
DEFAULT_HOLD_HOURS = float(os.getenv("ASTER_DN_HOLD_HOURS", "72"))


def aster_cost_model(slippage_bps: float = ASTER_SLIPPAGE_BPS) -> TradeCostModel:
    """Round-trip cost across both legs of an Aster delta-neutral cycle."""
    taker = VERIFIED_TAKER_BPS["aster"]
    return TradeCostModel(legs=(
        VenueCosts("aster-spot", taker_bps=taker, slippage_bps=slippage_bps),
        VenueCosts("aster-perp", taker_bps=taker, slippage_bps=slippage_bps),
    ))


class AsterApiManager:
    """
    Unified API manager for both Aster Perpetual and Spot markets.
    Handles all API communications with proper authentication and precision formatting.
    """

    def __init__(self, api_user: str, api_signer: str, api_private_key: str,
                 apiv1_public: str, apiv1_private: str):
        """
        Initialize the API manager with all required credentials.
        """
        # Validate Ethereum credentials
        if not api_user or not Web3.is_address(api_user):
            raise ValueError("API_USER is missing or not a valid Ethereum address.")
        if not api_signer or not Web3.is_address(api_signer):
            raise ValueError("API_SIGNER is missing or not a valid Ethereum address.")
        if not api_private_key:
            raise ValueError("API_PRIVATE_KEY is missing.")

        self.api_user = api_user
        self.api_signer = api_signer
        self.api_private_key = api_private_key
        self.apiv1_public = apiv1_public
        self.apiv1_private = apiv1_private

        self.session = None
        self.spot_exchange_info = None
        self.perp_exchange_info = None

        # Per-symbol funding intervals. Aster runs 1h, 4h and 8h simultaneously,
        # so a single hardcoded constant is wrong for most of the book.
        self._interval_resolver = FundingIntervalResolver()
        self._funding_info_cache: Optional[Dict[str, float]] = None
        self._funding_info_fetched_at: float = 0.0

    # --- Ethereum Signature Methods (for Perpetuals API) ---

    def _trim_dict(self, my_dict: dict) -> dict:
        """Recursively converts all values in a dictionary to strings for signature generation."""
        for key, value in my_dict.items():
            if isinstance(value, list):
                new_value = []
                for item in value:
                    if isinstance(item, dict):
                        new_value.append(json.dumps(self._trim_dict(item)))
                    else:
                        new_value.append(str(item))
                my_dict[key] = json.dumps(new_value)
            elif isinstance(value, dict):
                my_dict[key] = json.dumps(self._trim_dict(value))
            else:
                my_dict[key] = str(value)
        return my_dict

    def _sign_perp_request(self, params: dict) -> dict:
        """Signs perpetual API request parameters using Ethereum signature."""
        nonce = math.trunc(time.time() * 1000000)
        my_dict = {k: v for k, v in params.items() if v is not None}
        my_dict["recvWindow"] = 50000
        my_dict["timestamp"] = int(round(time.time() * 1000))

        # Convert all values to strings
        self._trim_dict(my_dict)

        # Create the JSON string exactly as in the documentation
        json_str = json.dumps(my_dict, sort_keys=True).replace(' ', '')

        # Encode and hash
        encoded = encode(['string', 'address', 'address', 'uint256'],
                         [json_str, self.api_user, self.api_signer, nonce])
        keccak_hex = Web3.keccak(encoded).hex()

        # Sign the message
        signable_msg = encode_defunct(hexstr=keccak_hex)
        signed_message = Account.sign_message(signable_message=signable_msg, private_key=self.api_private_key)

        # Append auth data to the dictionary
        my_dict['nonce'] = nonce
        my_dict['user'] = self.api_user
        my_dict['signer'] = self.api_signer
        my_dict['signature'] = '0x' + signed_message.signature.hex()

        return my_dict

    async def _signed_perp_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """Generic method for making signed requests to the Perpetuals API."""
        if params is None:
            params = {}
        if not self.session:
            self.session = aiohttp.ClientSession()

        url = f"{FUTURES_BASE_URL}{endpoint}"
        signed_params = self._sign_perp_request(params)
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'PythonApp/1.0'}

        if method.upper() == 'GET':
            query_string = urllib.parse.urlencode(signed_params)
            full_url = f"{url}?{query_string}"
            async with self.session.get(full_url, headers=headers) as response:
                if not response.ok:
                    error_body = await response.text()
                    print(f"API Error on {method} {endpoint}: Status={response.status}, Body={error_body}")
                response.raise_for_status()
                return await response.json()

        elif method.upper() == 'POST':
            async with self.session.post(url, data=signed_params, headers=headers) as response:
                if not response.ok:
                    error_body = await response.text()
                    print(f"API Error on {method} {endpoint}: Status={response.status}, Body={error_body}")
                response.raise_for_status()
                return await response.json()

        elif method.upper() == 'DELETE':
            async with self.session.delete(url, data=signed_params, headers=headers) as response:
                if not response.ok:
                    error_body = await response.text()
                    print(f"API Error on {method} {endpoint}: Status={response.status}, Body={error_body}")
                response.raise_for_status()
                return await response.json()
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    # --- Exchange Info and Formatting Helpers ---

    async def _get_spot_exchange_info(self, force_refresh: bool = False) -> dict:
        """Fetches and caches spot exchange information."""
        if not self.spot_exchange_info or force_refresh:
            self.spot_exchange_info = await self._make_spot_request('GET', '/api/v1/exchangeInfo')
        return self.spot_exchange_info

    async def _get_perp_exchange_info(self, force_refresh: bool = False) -> dict:
        """Fetches and caches perpetual exchange information."""
        if not self.perp_exchange_info or force_refresh:
            if not self.session:
                self.session = aiohttp.ClientSession()
            url = f"{FUTURES_BASE_URL}/fapi/v1/exchangeInfo"
            async with self.session.get(url) as response:
                response.raise_for_status()
                self.perp_exchange_info = await response.json()
        return self.perp_exchange_info

    def _truncate(self, value: float, precision: int) -> float:
        """Truncates a float to a given precision without rounding."""
        return truncate(value, precision)

    async def _get_formatted_order_params(self, symbol: str, market_type: str, price: Optional[float] = None, quantity: Optional[float] = None, quote_quantity: Optional[float] = None) -> dict:
        """Fetches symbol filters and formats order parameters to the correct precision."""
        if market_type == 'spot':
            exchange_info = await self._get_spot_exchange_info()
        elif market_type == 'perp':
            exchange_info = await self._get_perp_exchange_info()
        else:
            return {}

        symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
        if not symbol_info:
            raise ValueError(f"Symbol {symbol} not found in {market_type} exchange info.")

        params = {}

        # Format price based on PRICE_FILTER (tickSize)
        if price is not None:
            price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
            if price_filter:
                tick_size_str = price_filter['tickSize']
                precision = abs(Decimal(tick_size_str).as_tuple().exponent)
                price = self._truncate(price, precision)
                params['price'] = f"{price:.{precision}f}"
            else:
                params['price'] = str(price)

        # Format quantity based on LOT_SIZE (stepSize)
        if quantity is not None:
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter:
                step_size_str = lot_size_filter['stepSize']
                precision = abs(Decimal(step_size_str).as_tuple().exponent)
                quantity = self._truncate(quantity, precision)
                params['quantity'] = f"{quantity:.{precision}f}"
            else:
                params['quantity'] = str(quantity)

        # Format quote quantity for spot market buys based on quoteAssetPrecision
        if quote_quantity is not None and market_type == 'spot':
            precision = symbol_info.get('quoteAssetPrecision', 2) # Default to 2 for safety if not found
            quote_quantity = self._truncate(quote_quantity, precision)
            params['quoteOrderQty'] = f"{quote_quantity:.{precision}f}"

        return params

    # --- Core Request Methods ---

    def _create_spot_signature(self, params: dict) -> str:
        """Create HMAC-SHA256 signature for spot API requests."""
        query_string = urllib.parse.urlencode(params)
        return hmac.new(self.apiv1_private.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    async def _make_spot_request(self, method: str, path: str, params: dict = None, signed: bool = False, suppress_errors: bool = False, base_url: str = SPOT_BASE_URL) -> dict:
        """Generic method for making requests to the Spot API."""
        if params is None:
            params = {}
        if not self.session:
            self.session = aiohttp.ClientSession()

        url = f"{base_url}{path}"
        headers = {'X-MBX-APIKEY': self.apiv1_public}

        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = 5000
            params['signature'] = self._create_spot_signature(params)

        async with self.session.request(method, url, params=params, headers=headers) as response:
            if not response.ok:
                error_body = await response.text()
                if not suppress_errors:
                    print(f"API Error: {response.status}, Body: {error_body}")
            response.raise_for_status()
            return await response.json()

    # --- Public Data Fetching Methods ---

    async def get_perp_account_info(self) -> dict:
        """Get perpetuals account information."""
        return await self._signed_perp_request('GET', '/fapi/v3/account')

    async def get_spot_account_balances(self) -> list:
        """Get spot account balances."""
        response = await self._make_spot_request('GET', '/api/v1/account', signed=True)
        return response.get('balances', [])

    async def get_funding_rate_history(self, symbol: str, limit: int = 50) -> list:
        """Get funding rate history for a symbol."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        url = f"{FUTURES_BASE_URL}/fapi/v1/fundingRate"
        params = {'symbol': symbol, 'limit': limit}
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()

    async def get_perp_book_ticker(self, symbol: str) -> dict:
        """Get perpetuals book ticker for a symbol."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        url = f"{FUTURES_BASE_URL}/fapi/v1/ticker/bookTicker"
        params = {'symbol': symbol}
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()

    async def get_spot_book_ticker(self, symbol: str, suppress_errors: bool = False) -> dict:
        """Get spot book ticker for a symbol."""
        return await self._make_spot_request('GET', '/api/v1/ticker/bookTicker', params={'symbol': symbol}, suppress_errors=suppress_errors)

    # --- Public Execution Methods (Write Actions) ---

    async def place_perp_order(self, symbol: str, price: str, quantity: str, side: str, reduce_only: bool = False) -> dict:
        """Place a perpetuals limit order with correct precision."""
        formatted_params = await self._get_formatted_order_params(
            symbol=symbol, market_type='perp', price=float(price), quantity=float(quantity)
        )

        params = {
            "symbol": symbol, "side": side, "type": "LIMIT",
            "timeInForce": "GTX", "price": formatted_params['price'],
            "quantity": formatted_params['quantity'], "positionSide": "BOTH"
        }
        if reduce_only:
            params['reduceOnly'] = 'true'
        return await self._signed_perp_request('POST', '/fapi/v3/order', params)

    async def place_perp_market_order(self, symbol: str, quantity: str, side: str) -> dict:
        """Place a perpetuals market order with correct precision."""
        formatted_params = await self._get_formatted_order_params(
            symbol=symbol, market_type='perp', quantity=float(quantity)
        )

        params = {
            'symbol': symbol,
            'side': side,
            'type': 'MARKET',
            'quantity': formatted_params['quantity']
        }
        return await self._signed_perp_request('POST', '/fapi/v3/order', params)

    async def place_spot_buy_market_order(self, symbol: str, quote_quantity: str) -> dict:
        """Place a spot market buy order with correct precision."""
        formatted_params = await self._get_formatted_order_params(
            symbol=symbol, market_type='spot', quote_quantity=float(quote_quantity)
        )
        params = {'symbol': symbol, 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': formatted_params['quoteOrderQty']}
        return await self._make_spot_request('POST', '/api/v1/order', params=params, signed=True)

    async def place_spot_sell_market_order(self, symbol: str, base_quantity: str) -> dict:
        """Place a spot market sell order with correct precision."""
        formatted_params = await self._get_formatted_order_params(
            symbol=symbol, market_type='spot', quantity=float(base_quantity)
        )
        params = {'symbol': symbol, 'side': 'SELL', 'type': 'MARKET', 'quantity': formatted_params['quantity']}
        return await self._make_spot_request('POST', '/api/v1/order', params=params, signed=True)

    async def close_perp_position(self, symbol: str, quantity: str, side_to_close: str) -> dict:
        """Close a perpetuals position using a market order with correct precision."""
        formatted_params = await self._get_formatted_order_params(
            symbol=symbol, market_type='perp', quantity=float(quantity)
        )
        params = {
            'symbol': symbol, 'side': side_to_close, 'type': 'MARKET',
            'quantity': formatted_params['quantity'], 'reduceOnly': 'true', 'positionSide': 'BOTH'
        }
        return await self._signed_perp_request('POST', '/fapi/v3/order', params)

    # --- Order Sweeping (backs two_leg's LegSpec.cancel_open) ---
    #
    # The manager previously had no cancel capability at all. two_leg requires it:
    # resting orders must be cancelled BEFORE a position is read back, otherwise a
    # "stable zero fill" is not really zero - an untouched order can still fill
    # later, and you will have concluded REJECTED about a leg that is about to go
    # live. The DN path uses MARKET orders on both legs so this is usually a no-op,
    # but it is the difference between "usually" and "provably".

    async def get_open_perp_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Open perpetual orders for `symbol`. Raises if the query fails."""
        result = await self._signed_perp_request('GET', '/fapi/v3/openOrders', {'symbol': symbol})
        return result if isinstance(result, list) else []

    async def cancel_all_perp_orders(self, symbol: str) -> int:
        """Cancel every open perp order for `symbol`. Returns how many were cancelled."""
        open_orders = await self.get_open_perp_orders(symbol)
        if not open_orders:
            return 0
        await self._signed_perp_request('DELETE', '/fapi/v3/allOpenOrders', {'symbol': symbol})
        return len(open_orders)

    async def get_open_spot_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Open spot orders for `symbol`. Raises if the query fails."""
        result = await self._make_spot_request(
            'GET', '/api/v1/openOrders', params={'symbol': symbol}, signed=True
        )
        return result if isinstance(result, list) else []

    async def cancel_all_spot_orders(self, symbol: str) -> int:
        """Cancel every open spot order for `symbol`. Returns how many were cancelled.

        The spot API has no bulk cancel (only `DELETE /api/v1/order` by orderId),
        so this queries and cancels one at a time. A single failed cancel is logged
        and skipped rather than aborting the sweep - cancelling three of four
        resting orders is strictly better than cancelling none.
        """
        open_orders = await self.get_open_spot_orders(symbol)
        cancelled = 0
        for order in open_orders:
            order_id = order.get('orderId')
            if order_id is None:
                continue
            try:
                await self._make_spot_request(
                    'DELETE', '/api/v1/order',
                    params={'symbol': symbol, 'orderId': order_id}, signed=True
                )
                cancelled += 1
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to cancel spot order %s on %s: %s", order_id, symbol, exc)
        return cancelled

    # --- Position Reads (back two_leg's LegSpec.read_position) ---
    #
    # These MUST raise when the read fails and MUST NOT fall back to 0.0.
    # verify_fill treats a returned number as ground truth, so a read that fails
    # open to zero reports "nothing filled" / "position closed" about a leg that is
    # actually live. That exact bug ("position read fails open to 0.0") is called
    # out in two_leg.py's verify_fill docstring as how a leg got forgotten
    # permanently. Absence from the response is different from a failed read: it
    # genuinely means flat, and returning 0.0 for that case is correct.

    async def get_perp_position_qty(self, symbol: str) -> float:
        """Signed perp position size for `symbol` (negative = short). Raises on read failure."""
        account = await self.get_perp_account_info()
        if not isinstance(account, dict) or 'positions' not in account:
            raise RuntimeError(
                f"Perp account response for {symbol} has no 'positions' field; "
                f"refusing to report a position size from an unrecognised payload."
            )
        for position in account.get('positions', []):
            if position.get('symbol') == symbol:
                return float(position.get('positionAmt', 0) or 0)
        return 0.0

    async def get_spot_base_qty(self, symbol: str) -> float:
        """Spot balance of `symbol`'s base asset (free + locked). Raises on read failure.

        Locked is included deliberately: a balance sitting in a resting order is
        still owned, and excluding it would understate the hedge and trigger a
        spurious top-up.
        """
        base_asset = await self._get_base_asset(symbol)
        balances = await self.get_spot_account_balances()
        if not isinstance(balances, list):
            raise RuntimeError(
                f"Spot balance response for {symbol} was {type(balances).__name__}, "
                f"expected a list; refusing to report a balance from it."
            )
        total = 0.0
        for balance in balances:
            if balance.get('asset') == base_asset:
                total += float(balance.get('free', 0) or 0)
                total += float(balance.get('locked', 0) or 0)
        return total

    async def _get_base_asset(self, symbol: str) -> str:
        """Base asset for `symbol`, from exchange info rather than string surgery."""
        perp_info = await self._get_perp_exchange_info()
        for entry in perp_info.get('symbols', []):
            if entry.get('symbol') == symbol and entry.get('baseAsset'):
                return entry['baseAsset']
        spot_info = await self._get_spot_exchange_info()
        for entry in spot_info.get('symbols', []):
            if entry.get('symbol') == symbol and entry.get('baseAsset'):
                return entry['baseAsset']
        raise ValueError(f"Cannot determine base asset for {symbol} from exchange info.")

    async def get_funding_info(self) -> Dict[str, float]:
        """Map of symbol -> fundingIntervalHours from `GET /fapi/v1/fundingInfo`.

        Aster runs 1h, 4h and 8h funding simultaneously across symbols, so this is
        the difference between a correct APR and one that is silently 2x or 8x out.
        The endpoint returns every symbol in a single public call. Symbols missing
        from the response are simply absent from the map - the caller resolves
        those empirically rather than assuming a default.
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        url = f"{FUTURES_BASE_URL}/fapi/v1/fundingInfo"
        async with self.session.get(url) as response:
            response.raise_for_status()
            payload = await response.json()

        intervals: Dict[str, float] = {}
        for entry in payload or []:
            symbol = entry.get('symbol')
            hours = entry.get('fundingIntervalHours')
            if symbol and hours:
                intervals[symbol] = float(hours)
        return intervals

    async def get_perp_leverage(self, symbol: str) -> int:
        """Get current leverage for a perpetual trading symbol."""
        # For testing compatibility, try both formats
        try:
            account_info = await self.get_perp_account_info()
            positions = account_info.get('positions', [])
        except:
            # Fallback for test mocks that return positions list directly
            positions = await self._signed_perp_request('GET', '/fapi/v2/account', {})
            if isinstance(positions, list):
                # Test mock format
                pass
            else:
                # Real API format
                positions = positions.get('positions', [])

        for position in positions:
            if position.get('symbol') == symbol:
                leverage_val = position.get('leverage', '1')
                return int(float(leverage_val))

        # Default to 1x if symbol not found
        return 1

    async def set_perp_leverage(self, symbol: str, leverage: int = 1) -> dict:
        """Set leverage for a perpetual trading symbol."""
        params = {'symbol': symbol, 'leverage': leverage}
        # This endpoint uses HMAC-SHA256, not the custom eth signature, so we use the spot request method
        return await self._make_spot_request(
            method='POST',
            path='/fapi/v1/leverage',
            params=params,
            signed=True,
            base_url=FUTURES_BASE_URL
        )

    async def set_leverage(self, symbol: str, leverage: int = 1) -> bool:
        """
        Alias for set_perp_leverage for backward compatibility.
        Returns True on success, False on failure.
        """
        try:
            response = await self.set_perp_leverage(symbol, leverage)
            # The API returns a dict with the set leverage on success
            return response and int(response.get('leverage')) == leverage
        except Exception:
            return False

    # --- Transfer Methods ---

    async def transfer_between_spot_and_perp(self, asset: str, amount: float, direction: str) -> dict:
        """
        Transfer assets between spot and perpetual accounts.

        Args:
            asset: Asset to transfer (e.g., 'USDT')
            amount: Amount to transfer
            direction: 'SPOT_TO_PERP' or 'PERP_TO_SPOT'

        Returns:
            Transfer response with transaction ID and status
        """
        # Generate unique transaction ID
        client_tran_id = f"transfer_{int(time.time() * 1000000)}"

        # Map direction to API parameter
        direction_map = {
            'SPOT_TO_PERP': 'SPOT_FUTURE',
            'PERP_TO_SPOT': 'FUTURE_SPOT'
        }

        if direction not in direction_map:
            raise ValueError(f"Invalid direction: {direction}. Must be 'SPOT_TO_PERP' or 'PERP_TO_SPOT'")

        params = {
            'asset': asset,
            'amount': str(amount),
            'clientTranId': client_tran_id,
            'kindType': direction_map[direction]
        }

        return await self._signed_perp_request('POST', '/fapi/v3/asset/wallet/transfer', params)

    async def rebalance_usdt_50_50(self) -> dict:
        """
        Automatically rebalance USDT to be 50/50 between spot and perpetual accounts.

        Returns:
            Dictionary with rebalance details and transfer result (if transfer was needed)
        """
        # Get current balances
        spot_balances = await self.get_spot_account_balances()
        perp_account = await self.get_perp_account_info()

        # Extract USDT balances
        spot_usdt = next((float(b.get('free', 0)) for b in spot_balances if b.get('asset') == 'USDT'), 0.0)

        # Get USDT from perpetual account assets
        perp_assets = perp_account.get('assets', [])
        perp_usdt = next((float(a.get('availableBalance', 0)) for a in perp_assets if a.get('asset') == 'USDT'), 0.0)

        total_usdt = spot_usdt + perp_usdt
        target_each = total_usdt / 2

        # Calculate transfer needed
        spot_difference = target_each - spot_usdt

        result = {
            'current_spot_usdt': spot_usdt,
            'current_perp_usdt': perp_usdt,
            'total_usdt': total_usdt,
            'target_each': target_each,
            'transfer_needed': abs(spot_difference) > 1.0,  # Only transfer if difference > $1
            'transfer_amount': abs(spot_difference),
            'transfer_direction': None,
            'transfer_result': None
        }

        # Perform transfer if needed (minimum $1 difference to avoid micro-transfers)
        if abs(spot_difference) > 1.0:
            transfer_amount = round(abs(spot_difference), 6) # Round to 6 decimal places for safety
            if spot_difference > 0:
                # Need to transfer from perp to spot
                result['transfer_direction'] = 'PERP_TO_SPOT'
                result['transfer_result'] = await self.transfer_between_spot_and_perp(
                    'USDT', transfer_amount, 'PERP_TO_SPOT'
                )
            else:
                # Need to transfer from spot to perp
                result['transfer_direction'] = 'SPOT_TO_PERP'
                result['transfer_result'] = await self.transfer_between_spot_and_perp(
                    'USDT', transfer_amount, 'SPOT_TO_PERP'
                )

        return result

    # --- Symbol Discovery and Analysis ---

    async def get_available_spot_symbols(self) -> List[str]:
        """Get list of all available spot trading symbols."""
        try:
            exchange_info = await self._get_spot_exchange_info()
            if exchange_info and 'symbols' in exchange_info:
                return sorted([s['symbol'] for s in exchange_info['symbols'] if s.get('status') == 'TRADING'])
            return []
        except Exception as e:
            print(f"Error fetching spot symbols: {e}")
            return []

    async def get_available_perp_symbols(self) -> List[str]:
        """Get list of all available perpetual trading symbols."""
        try:
            exchange_info = await self._get_perp_exchange_info()
            if exchange_info and 'symbols' in exchange_info:
                return sorted([s['symbol'] for s in exchange_info['symbols'] if s.get('status') == 'TRADING'])
            return []
        except Exception as e:
            print(f"Error fetching perpetual symbols: {e}")
            return []

    async def get_perp_symbol_filter(self, symbol: str, filter_type: str) -> Optional[Dict]:
        """Retrieves a specific filter for a perpetual symbol from exchange info."""
        try:
            exchange_info = await self._get_perp_exchange_info()
            symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
            if symbol_info:
                return next((f for f in symbol_info['filters'] if f['filterType'] == filter_type), None)
        except Exception as e:
            print(f"Error getting perp filter for {symbol}: {e}")
        return None

    async def get_spot_symbol_filter(self, symbol: str, filter_type: str) -> Optional[Dict]:
        """Retrieves a specific filter for a spot symbol from exchange info."""
        try:
            exchange_info = await self._get_spot_exchange_info()
            symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
            if symbol_info:
                return next((f for f in symbol_info.get('filters', []) if f['filterType'] == filter_type), None)
        except Exception as e:
            print(f"Error getting spot filter for {symbol}: {e}")
        return None

    @staticmethod
    def _tick_from_filter(lot_size_filter: Optional[Dict], default: float = 0.0) -> float:
        """stepSize out of a LOT_SIZE filter, as a float tick."""
        if lot_size_filter and lot_size_filter.get('stepSize'):
            try:
                return float(lot_size_filter['stepSize'])
            except (TypeError, ValueError):
                pass
        return default

    def _build_perp_leg(self, symbol: str, side: str, qty: float, amount_tick: float,
                        reduce_only: bool = False) -> LegSpec:
        """LegSpec driving the perpetual side. All venue coupling lives here."""
        api_side = side.upper()

        async def submit(q: float):
            if reduce_only:
                return await self.close_perp_position(symbol, str(q), api_side)
            return await self.place_perp_market_order(symbol, str(q), api_side)

        async def close_market(q: float, close_side: str):
            return await self.close_perp_position(symbol, str(q), close_side.upper())

        return LegSpec(
            name="Aster-perp", symbol=symbol, side=side, intent_qty=qty,
            submit=submit,
            read_position=lambda: self.get_perp_position_qty(symbol),
            close_market=close_market,
            cancel_open=lambda: self.cancel_all_perp_orders(symbol),
            amount_tick=amount_tick,
            settle_delay_s=1.0,
        )

    def _build_spot_leg(self, symbol: str, side: str, qty: float, amount_tick: float,
                        price: float) -> LegSpec:
        """LegSpec driving the spot side.

        `intent_qty` is in BASE units so it is directly comparable with the perp
        leg and with the balance that read_position returns. The quote conversion
        for market BUYs happens inside submit(), because Aster's spot buy is
        quoteOrderQty-denominated. The old code passed the USD notional straight
        in as intent_qty, which made every tolerance and residual on this leg a
        comparison between dollars and coins.
        """
        async def submit(q: float):
            if side == "buy":
                return await self.place_spot_buy_market_order(symbol, str(q * price))
            return await self.place_spot_sell_market_order(symbol, str(q))

        async def close_market(q: float, close_side: str):
            if close_side.lower() == "buy":
                return await self.place_spot_buy_market_order(symbol, str(q * price))
            return await self.place_spot_sell_market_order(symbol, str(q))

        return LegSpec(
            name="Aster-spot", symbol=symbol, side=side, intent_qty=qty,
            submit=submit,
            read_position=lambda: self.get_spot_base_qty(symbol),
            close_market=close_market,
            cancel_open=lambda: self.cancel_all_spot_orders(symbol),
            amount_tick=amount_tick,
            settle_delay_s=1.0,
        )

    async def discover_delta_neutral_pairs(self) -> List[str]:
        """Dynamically discover which pairs are available for delta-neutral strategies."""
        try:
            spot_symbols, perp_symbols = await asyncio.gather(
                self.get_available_spot_symbols(),
                self.get_available_perp_symbols(),
                return_exceptions=True
            )
            if isinstance(spot_symbols, Exception) or isinstance(perp_symbols, Exception):
                spot_symbols, perp_symbols = [], []

            from strategy_logic import DeltaNeutralLogic
            return DeltaNeutralLogic.find_delta_neutral_pairs(spot_symbols, perp_symbols)
        except Exception as e:
            print(f"Error discovering delta-neutral pairs: {e}")
            return []

    async def analyze_current_positions(self) -> Dict[str, Dict[str, Any]]:
        """Analyze current open positions across spot and perpetual markets."""
        try:
            # Fetch all required data concurrently
            perp_info, spot_info, perp_account, spot_balances = await asyncio.gather(
                self._get_perp_exchange_info(),
                self._get_spot_exchange_info(),
                self.get_perp_account_info(),
                self.get_spot_account_balances(),
                return_exceptions=True
            )
            if isinstance(perp_info, Exception) or isinstance(spot_info, Exception) or isinstance(perp_account, Exception) or isinstance(spot_balances, Exception):
                return {}

            # Prepare data for strategy logic
            spot_lookup = {b.get('asset', ''): float(b.get('free', '0')) + float(b.get('locked', '0')) for b in spot_balances}
            perp_symbol_map = {s['symbol']: s for s in perp_info.get('symbols', [])}
            perp_positions = perp_account.get('positions', [])

            # Filter for positions with non-zero amounts and fetch current prices
            active_positions = [p for p in perp_positions if float(p.get('positionAmt', 0)) != 0]
            if active_positions:
                # Fetch current mark prices for all active positions
                price_tasks = [self.get_perp_book_ticker(p['symbol']) for p in active_positions]
                price_results = await asyncio.gather(*price_tasks, return_exceptions=True)

                # Update positions with current mark prices
                for i, pos in enumerate(active_positions):
                    price_data = price_results[i]
                    if not isinstance(price_data, Exception) and price_data.get('bidPrice') and price_data.get('askPrice'):
                        # Use mid-price as mark price
                        bid_price = float(price_data['bidPrice'])
                        ask_price = float(price_data['askPrice'])
                        pos['markPrice'] = (bid_price + ask_price) / 2
                    # If price fetch fails, keep existing markPrice or set to 0

            # Use strategy logic for computational analysis
            analysis = DeltaNeutralLogic.analyze_position_data(
                perp_positions=perp_positions,
                spot_balances=spot_lookup,
                perp_symbol_map=perp_symbol_map
            )

            return analysis
        except Exception as e:
            print(f"Error analyzing positions: {e}")
            return {}

    async def _get_funding_info_cached(self, ttl_s: float = 6 * 3600.0) -> Dict[str, float]:
        """`get_funding_info()` behind a TTL cache; one call covers every symbol."""
        now = time.time()
        if (self._funding_info_cache is None
                or (now - self._funding_info_fetched_at) > ttl_s):
            self._funding_info_cache = await self.get_funding_info()
            self._funding_info_fetched_at = now
        return self._funding_info_cache

    async def resolve_funding_interval(self, symbol: str) -> FundingInterval:
        """Funding interval for `symbol`. Raises IntervalResolutionError if unknown.

        Preferred source is the venue's own `fundingIntervalHours`. If the symbol
        is absent from that response the interval is inferred from the spacing of
        its actual settlement timestamps. If both fail the caller MUST skip the
        symbol: annualizing on a guessed constant is what made a 4h symbol's APR
        read at half its true value and rank below worse opportunities.
        """
        async def from_api_field(sym: str) -> Optional[float]:
            info = await self._get_funding_info_cached()
            return info.get(sym)

        try:
            return await self._interval_resolver.resolve_from_api_field(
                'aster', symbol, from_api_field)
        except IntervalResolutionError:
            async def funding_times(sym: str) -> List[int]:
                history = await self.get_funding_rate_history(sym, limit=20)
                return [int(h['fundingTime']) for h in history if h.get('fundingTime')]

            return await self._interval_resolver.resolve_empirically(
                'aster', symbol, funding_times)

    async def get_all_funding_rates(self) -> List[Dict[str, Any]]:
        """Funding rates and correctly annualized APRs for all delta-neutral pairs.

        The APR used to be `rate * 3 * 365 * 100`, i.e. a hardcoded 8h interval.
        Aster runs 1h, 4h and 8h intervals simultaneously, so that understated a
        4h symbol by 2x and a 1h symbol by 8x -- and this table is what the
        operator picks from, so the mis-ranking directly selected worse trades.
        """
        symbols_to_scan = await self.discover_delta_neutral_pairs()
        if not symbols_to_scan:
            return []

        rate_tasks = [self.get_funding_rate_history(s, limit=1) for s in symbols_to_scan]
        rate_results = await asyncio.gather(*rate_tasks, return_exceptions=True)

        funding_data = []
        for i, symbol in enumerate(symbols_to_scan):
            rate_data = rate_results[i]
            if isinstance(rate_data, Exception) or not rate_data:
                continue

            rate = float(rate_data[0].get('fundingRate', 0))
            try:
                interval = await self.resolve_funding_interval(symbol)
            except IntervalResolutionError as exc:
                # Skip rather than guess. A row missing from the table is far
                # cheaper than a row with a silently wrong APR next to it.
                logging.warning("Skipping %s: %s", symbol, exc)
                continue

            funding_data.append({
                'symbol': symbol,
                'rate': rate,
                'apr': annualize(rate, interval),
                'interval_hours': interval.hours,
                'interval_source': interval.source,
            })

        # Sort by highest APR
        return sorted(funding_data, key=lambda x: x['apr'], reverse=True)

    async def get_comprehensive_portfolio_data(self) -> Dict[str, Any]:
        """Fetches and processes all portfolio data in a structured way."""
        # 1. Fetch all required raw data concurrently
        results = await asyncio.gather(
            self.get_perp_account_info(),
            self.get_spot_account_balances(),
            self._get_perp_exchange_info(),
            self._get_spot_exchange_info(),
            return_exceptions=True
        )
        perp_account, spot_balances, perp_info, spot_info = results

        if isinstance(perp_account, Exception) or isinstance(spot_balances, Exception) or \
           isinstance(perp_info, Exception) or isinstance(spot_info, Exception):
            # Handle potential fetching errors gracefully
            # Consider logging the specific errors here
            return {}

        # 2. Process raw perpetual positions
        raw_perp_positions = [p for p in perp_account.get('positions', []) if float(p.get('positionAmt', 0)) != 0]
        if raw_perp_positions:
            price_tasks = [self.get_perp_book_ticker(p['symbol']) for p in raw_perp_positions]
            price_results = await asyncio.gather(*price_tasks, return_exceptions=True)
            for i, pos in enumerate(raw_perp_positions):
                price_data = price_results[i]
                if not isinstance(price_data, Exception) and price_data.get('bidPrice'):
                    pos['markPrice'] = (float(price_data['bidPrice']) + float(price_data['askPrice'])) / 2

        # 3. Process spot balances
        processed_spot_balances = [b for b in spot_balances if float(b.get('free', 0)) > 0 or float(b.get('locked', 0)) > 0]
        stablecoins = {'USDT', 'USDC', 'USDF'}
        non_stable_balances = [b for b in processed_spot_balances if b.get('asset') not in stablecoins]
        if non_stable_balances:
            price_tasks = [self.get_spot_book_ticker(f"{b['asset']}USDT", suppress_errors=True) for b in non_stable_balances]
            price_results = await asyncio.gather(*price_tasks, return_exceptions=True)
            for i, balance in enumerate(non_stable_balances):
                price_data = price_results[i]
                if not isinstance(price_data, Exception) and price_data.get('bidPrice'):
                    balance['value_usd'] = (float(balance.get('free', 0)) + float(balance.get('locked', 0))) * float(price_data['bidPrice'])
                else:
                    balance['value_usd'] = 0.0

        # 4. Perform delta-neutral analysis
        spot_lookup = {b.get('asset', ''): float(b.get('free', '0')) for b in processed_spot_balances}
        perp_symbol_map = {s['symbol']: s for s in perp_info.get('symbols', [])}
        analyzed_positions = list(DeltaNeutralLogic.analyze_position_data(
            perp_positions=raw_perp_positions,
            spot_balances=spot_lookup,
            perp_symbol_map=perp_symbol_map
        ).values())

        # 5. Enrich analyzed positions with APR and other data
        dn_positions = [p for p in analyzed_positions if p.get('is_delta_neutral')]
        if dn_positions:
            rate_tasks = [self.get_funding_rate_history(p['symbol'], limit=1) for p in dn_positions]
            rate_results = await asyncio.gather(*rate_tasks, return_exceptions=True)
            for i, pos in enumerate(dn_positions):
                rate_data = rate_results[i]
                if not isinstance(rate_data, Exception) and rate_data:
                    pos['current_apr'] = float(rate_data[0].get('fundingRate', 0)) * 3 * 365 * 100

        # 6. Return all processed data in a structured dictionary
        return {
            'perp_account_info': perp_account,
            'raw_perp_positions': raw_perp_positions,
            'spot_balances': processed_spot_balances,
            'analyzed_positions': analyzed_positions,
        }

    async def prepare_and_execute_dn_position(
        self, symbol: str, capital_to_deploy: float, dry_run: bool = False,
        hold_hours: float = DEFAULT_HOLD_HOURS,
        allow_negative_carry: bool = False,
    ) -> Dict[str, Any]:
        """Prepares and (optionally) executes a delta-neutral position opening.

        `hold_hours` is how long you intend to hold. It is not cosmetic: break-even
        APR scales as 1/hold_hours, so it decides whether a cycle can pay for its
        own four taker fills at all.

        `allow_negative_carry=True` opens anyway when the fee-aware gate rejects.
        Reserved for the operator explicitly overriding, never a default.
        """
        trade_details = {'success': False, 'message': '', 'details': None}
        try:
            # Refuse to trade while a halt sentinel is present. Checked here as
            # well as inside execute_two_leg so that a halted bot does not spend
            # a round of API calls building a plan it will never be allowed to run.
            if not dry_run:
                assert_not_halted(HALT_PATH)

            # 1. Fetch required data
            (spot_price_data, lot_size_filter, spot_lot_filter,
             spot_notional_filter, spot_balances, perp_account) = await asyncio.gather(
                self.get_spot_book_ticker(symbol),
                self.get_perp_symbol_filter(symbol, 'LOT_SIZE'),
                self.get_spot_symbol_filter(symbol, 'LOT_SIZE'),
                self.get_spot_symbol_filter(symbol, 'MIN_NOTIONAL'),
                self.get_spot_account_balances(),
                self.get_perp_account_info()
            )
            spot_price = float(spot_price_data['bidPrice'])

            # Check for existing short position
            raw_perp_positions = [p for p in perp_account.get('positions', []) if float(p.get('positionAmt', 0)) != 0]
            existing_short = next((p for p in raw_perp_positions if p.get('symbol') == symbol and float(p.get('positionAmt', 0)) < 0), None)
            if existing_short:
                trade_details['message'] = f"Cannot open position. Already have a short position: {existing_short.get('positionAmt')}"
                return trade_details

            # 2. Set leverage to 1x
            leverage_set = await self.set_leverage(symbol, 1)
            if not leverage_set:
                trade_details['message'] = "Failed to set leverage to 1x."
                return trade_details

            # 3. Calculate position sizes
            #
            # free + locked, and the base asset comes from exchange info rather
            # than stripping "USDT" off the symbol. Both details matter because
            # this number is compared against what the spot leg's read_position()
            # reports during fill verification -- if the two are measured
            # differently, a correctly hedged position looks imbalanced.
            base_asset = await self._get_base_asset(symbol)
            existing_spot_quantity = sum(
                float(b.get('free', '0') or 0) + float(b.get('locked', '0') or 0)
                for b in spot_balances if b.get('asset') == base_asset
            )
            sizing = DeltaNeutralLogic.calculate_position_size(
                total_usd_capital=capital_to_deploy,
                spot_price=spot_price,
                existing_spot_usd=(existing_spot_quantity * spot_price)
            )

            # 4. Adjust quantities based on perpetuals lot size filter
            ideal_perp_qty = sizing['total_perp_quantity_to_short']
            final_perp_qty = ideal_perp_qty
            if lot_size_filter and lot_size_filter.get('stepSize'):
                step_size_str = lot_size_filter['stepSize']
                precision = abs(Decimal(step_size_str).as_tuple().exponent)
                final_perp_qty = self._truncate(ideal_perp_qty, precision)

            if final_perp_qty <= 0:
                trade_details['message'] = "Final perpetual quantity is zero or less after rounding."
                return trade_details

            # 5. Adjust spot side
            spot_qty_to_buy = max(0, final_perp_qty - existing_spot_quantity)
            spot_capital_to_buy = spot_qty_to_buy * spot_price

            # 6. Prepare details dictionary
            details = {
                'symbol': symbol,
                'capital_to_deploy': capital_to_deploy,
                'spot_price': spot_price,
                'lot_size_filter': lot_size_filter,
                'ideal_perp_qty': ideal_perp_qty,
                'final_perp_qty': final_perp_qty,
                'existing_spot_quantity': existing_spot_quantity,
                'spot_qty_to_buy': spot_qty_to_buy,
                'spot_capital_to_buy': spot_capital_to_buy
            }
            # 6b. FEE-AWARE ENTRY GATE.
            #
            # The only entry filter before this was ANNUALIZED_APR_THRESHOLD = 15%,
            # a GROSS number with no cost term anywhere. A cycle here pays four
            # taker fills, so at a short hold the break-even APR runs into the
            # hundreds of percent and a 15% gate admits systematically losing
            # trades. This computes the actual expected net in dollars.
            entry_decision = None
            try:
                interval = await self.resolve_funding_interval(symbol)
                rate_history = await self.get_funding_rate_history(symbol, limit=1)
                if rate_history:
                    funding_rate = float(rate_history[0].get('fundingRate', 0))
                    gross_apr = annualize(funding_rate, interval)
                    entry_decision = evaluate_entry(
                        symbol=symbol,
                        gross_net_apr_pct=gross_apr,
                        notional_usd=float(final_perp_qty) * spot_price,
                        hold_hours=hold_hours,
                        cost=aster_cost_model(),
                    )
                    details['funding_interval_hours'] = interval.hours
                    details['funding_apr_pct'] = gross_apr
                    details['hold_hours'] = hold_hours
                    details['break_even_apr_pct'] = entry_decision.break_even_apr_pct
                    details['expected_net_usd'] = entry_decision.expected_net_usd
                    details['entry_reason'] = entry_decision.reason
            except IntervalResolutionError as exc:
                # No interval means no trustworthy APR, so no trustworthy decision.
                details['entry_reason'] = f"funding interval unresolved: {exc}"

            trade_details['details'] = details

            if (entry_decision is not None and not entry_decision.accept
                    and not allow_negative_carry):
                trade_details['message'] = (
                    f"Refusing to open {symbol}: {entry_decision.reason}. "
                    f"At a {hold_hours:g}h hold this cycle needs "
                    f"{entry_decision.break_even_apr_pct:.1f}% APR to cover its four "
                    f"taker fills; expected net is "
                    f"${entry_decision.expected_net_usd:.2f}. Hold longer, size up, "
                    f"or pass allow_negative_carry=True to override. Nothing was "
                    f"submitted."
                )
                trade_details['entry_decision'] = entry_decision
                return trade_details

            # 7. PRE-SUBMISSION GATE.
            #
            # This check used to run AFTER both orders had been fired: the gather
            # below submitted the perp SELL unconditionally and substituted
            # asyncio.sleep(0) for the spot BUY when the notional was under $1,
            # then appended "the perp leg would be unhedged" to the failure list.
            # It deliberately opened a naked short and then reported the problem.
            #
            # It was also wrong in the ordinary case: spot_qty_to_buy is correctly
            # zero when existing spot already covers the hedge, which is a properly
            # hedged position, not a failure.
            spot_tick = self._tick_from_filter(spot_lot_filter)
            hedge_already_covered = spot_qty_to_buy <= max(spot_tick, 1e-12)

            if not hedge_already_covered:
                min_notional = 0.0
                if spot_notional_filter:
                    min_notional = float(
                        spot_notional_filter.get('minNotional')
                        or spot_notional_filter.get('notional')
                        or 0.0
                    )
                if spot_capital_to_buy < min_notional:
                    trade_details['message'] = (
                        f"Refusing to open {symbol}: the spot hedge would be "
                        f"${spot_capital_to_buy:.2f}, below the exchange minimum of "
                        f"${min_notional:.2f}. Opening the perp leg alone would leave a "
                        f"naked short. Nothing was submitted. Increase the capital to "
                        f"deploy, or reduce it so no perp leg is opened either."
                    )
                    return trade_details

            if dry_run:
                trade_details['success'] = True
                trade_details['message'] = "Dry run successful. Trade details calculated."
                return trade_details

            # 8. Execute: perp is the pilot, spot is the hedge.
            #
            # Sequential, not asyncio.gather. Parallel submission maximises the
            # window in which both legs are live and unverified, and makes the
            # failure case undecidable. More importantly, the hedge is now sized
            # from what the perp ACTUALLY filled rather than from a pre-trade
            # bidPrice estimate, and every leg is confirmed by reading the position
            # back -- acceptance is not a fill.
            perp_tick = self._tick_from_filter(lot_size_filter)
            pilot = self._build_perp_leg(symbol, "sell", float(final_perp_qty), perp_tick)
            hedge = self._build_spot_leg(symbol, "buy", float(spot_qty_to_buy),
                                         spot_tick, spot_price)

            # Existing spot counts toward the hedge, so only the shortfall is
            # bought. Returning ~0 tells execute_two_leg the hedge is already held.
            def hedge_qty_from_pilot(perp_filled: float) -> float:
                return max(0.0, perp_filled - existing_spot_quantity)

            outcome = await execute_two_leg(
                pilot, hedge,
                min_notional_qty=0.0,
                halt_path=HALT_PATH,
                hedge_qty_from_pilot=hedge_qty_from_pilot,
            )

            trade_details['success'] = outcome.ok
            trade_details['halted'] = outcome.halted
            trade_details['hedged_qty'] = outcome.hedged_qty
            trade_details['notes'] = outcome.notes
            trade_details['leg_status'] = {
                'perp': outcome.pilot.status.value if outcome.pilot else 'not submitted',
                'spot': outcome.hedge.status.value if outcome.hedge else 'not submitted',
            }
            trade_details['perp_order'] = outcome.pilot.raw if outcome.pilot else None
            trade_details['spot_order'] = outcome.hedge.raw if outcome.hedge else None

            if outcome.ok:
                trade_details['message'] = (
                    f"Opened {symbol} delta-neutral: {outcome.hedged_qty:.8f} confirmed "
                    f"hedged on both legs ({outcome.reason})."
                )
            elif outcome.halted:
                trade_details['message'] = (
                    f"HALTED opening {symbol}: {outcome.reason}. A halt sentinel was "
                    f"written to {HALT_PATH} and the bot will refuse to trade until it "
                    f"is removed. Check BOTH legs on the exchange before clearing it."
                )
            else:
                trade_details['message'] = (
                    f"Did not open {symbol}: {outcome.reason}. Any leg that filled has "
                    f"been unwound."
                )
            return trade_details

        except HaltedError as e:
            trade_details['halted'] = True
            trade_details['message'] = str(e)
            return trade_details
        except Exception as e:
            trade_details['message'] = f"Failed to open position: {e}"
            return trade_details

    async def execute_dn_position_close(self, symbol: str) -> Dict[str, Any]:
        """Fetches position state and executes closing orders for a delta-neutral position."""
        close_details = {'success': False, 'message': ''}
        try:
            # 1. Get current position state
            portfolio_data = await self.get_comprehensive_portfolio_data()
            if not portfolio_data:
                close_details['message'] = "Could not retrieve portfolio data."
                return close_details

            position_to_close = next((p for p in portfolio_data.get('analyzed_positions', []) if p.get('symbol') == symbol), None)

            if not position_to_close:
                close_details['message'] = f"No position found for symbol {symbol}."
                return close_details

            # 2. Get quantities to close
            perp_quantity = abs(position_to_close.get('perp_position', 0))
            spot_balance = position_to_close.get('spot_balance', 0)
            side_to_close = 'BUY' if position_to_close.get('perp_position', 0) < 0 else 'SELL'

            if perp_quantity == 0 or spot_balance == 0:
                close_details['message'] = f"Position for {symbol} is not a valid delta-neutral pair to close (perp or spot leg is zero)."
                return close_details

            # Sell only the HEDGE, never the whole bag.
            #
            # This used to pass the entire free spot balance as the sell quantity.
            # The spot balance is not the bot's position - it is everything you hold
            # in that asset. If you had 2.0 BTC of long-term spot and a 0.1 BTC
            # hedge, closing the hedge market-sold all 2.0 BTC.
            #
            # The hedge is by definition the amount matched against the perp leg, so
            # cap the sell at the perp size.
            spot_quantity = min(float(spot_balance), float(perp_quantity))

            if spot_quantity < float(spot_balance):
                close_details['spot_balance_untouched'] = float(spot_balance) - spot_quantity
                logging.warning(
                    "%s: spot balance %.8f exceeds hedge size %.8f. Selling only the "
                    "hedged %.8f and leaving %.8f untouched.",
                    symbol, float(spot_balance), float(perp_quantity), spot_quantity,
                    float(spot_balance) - spot_quantity,
                )

            # 3. Execute closing trades: perp reduce-only is the pilot, spot the hedge.
            #
            # Same reasoning as the open path. Previously both closes went out via
            # asyncio.gather and only REJECTED was treated as failure, so a close
            # whose outcome was UNKNOWN (timeout, dropped connection) reported
            # success -- the bot then moved on and cleared its state while a leg was
            # still live, leaving a position with no monitoring and nothing
            # recording that it existed.
            perp_lot_filter, spot_lot_filter, spot_price_data = await asyncio.gather(
                self.get_perp_symbol_filter(symbol, 'LOT_SIZE'),
                self.get_spot_symbol_filter(symbol, 'LOT_SIZE'),
                self.get_spot_book_ticker(symbol),
            )
            spot_price = float(spot_price_data['bidPrice'])

            pilot = self._build_perp_leg(
                symbol, side_to_close.lower(), float(perp_quantity),
                self._tick_from_filter(perp_lot_filter), reduce_only=True,
            )
            hedge = self._build_spot_leg(
                symbol, "sell", float(spot_quantity),
                self._tick_from_filter(spot_lot_filter), spot_price,
            )

            # Sell exactly as much spot as the perp actually reduced, capped at the
            # hedge size. Without the cap a larger long-term spot holding would be
            # market-sold along with the hedge.
            def hedge_qty_from_pilot(perp_closed: float) -> float:
                return min(float(spot_quantity), perp_closed)

            outcome = await execute_two_leg(
                pilot, hedge,
                min_notional_qty=0.0,
                halt_path=HALT_PATH,
                hedge_qty_from_pilot=hedge_qty_from_pilot,
            )

            close_details['success'] = outcome.ok
            close_details['halted'] = outcome.halted
            close_details['closed_qty'] = outcome.hedged_qty
            close_details['notes'] = outcome.notes
            close_details['leg_status'] = {
                'perp': outcome.pilot.status.value if outcome.pilot else 'not submitted',
                'spot': outcome.hedge.status.value if outcome.hedge else 'not submitted',
            }
            close_details['perp_order'] = outcome.pilot.raw if outcome.pilot else None
            close_details['spot_order'] = outcome.hedge.raw if outcome.hedge else None

            if outcome.ok:
                close_details['message'] = (
                    f"Closed {symbol}: {outcome.hedged_qty:.8f} confirmed reduced on "
                    f"both legs ({outcome.reason})."
                )
            elif outcome.halted:
                close_details['message'] = (
                    f"HALTED closing {symbol}: {outcome.reason}. A halt sentinel was "
                    f"written to {HALT_PATH}. The position may be PARTLY OPEN - do not "
                    f"clear it from state. Verify both legs before clearing the halt."
                )
            else:
                close_details['message'] = (
                    f"FAILED to close {symbol}: {outcome.reason}. The position is STILL "
                    f"OPEN - do not clear it from state. Verify both legs on the exchange."
                )
            return close_details

        except HaltedError as e:
            close_details['halted'] = True
            close_details['message'] = str(e)
            return close_details
        except Exception as e:
            close_details['message'] = f"Failed to close position: {e}"
            return close_details


    async def get_income_history(self, symbol: Optional[str] = None, income_type: Optional[str] = None, start_time: Optional[int] = None, end_time: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get income history for the perpetuals account.
        NOTE: This v1 endpoint uses HMAC-SHA256 authentication, not the v3 eth signature.
        """
        params = {'limit': limit}
        if symbol:
            params['symbol'] = symbol
        if income_type:
            params['incomeType'] = income_type
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        return await self._make_spot_request(
            method='GET',
            path='/fapi/v1/income',
            params=params,
            signed=True,
            base_url=FUTURES_BASE_URL
        )

    async def get_user_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get user's trade history for a specific symbol.
        NOTE: This v1 endpoint uses HMAC-SHA256 authentication.
        """
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return await self._make_spot_request(
            method='GET',
            path='/fapi/v1/userTrades',
            params=params,
            signed=True,
            base_url=FUTURES_BASE_URL
        )

    async def perform_funding_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Performs a standalone funding analysis for a given symbol.
        This function is self-contained and fetches all necessary data.

        Args:
            symbol: Trading symbol to analyze (e.g., 'BTCUSDT')

        Returns:
            Dict with funding analysis data or None if analysis fails
        """
        try:
            # 1. Fetch all necessary data concurrently
            all_positions_task = self.get_perp_account_info()
            spot_balances_task = self.get_spot_account_balances()
            ticker_task = self.get_perp_book_ticker(symbol)

            all_positions, spot_balances, ticker = await asyncio.gather(
                all_positions_task, spot_balances_task, ticker_task
            )

            position = next((p for p in all_positions.get('positions', []) if p.get('symbol') == symbol and Decimal(p.get('positionAmt', '0')) != 0), None)

            if not position:
                return None

            # Extract data from fetched results
            current_pos_amount = Decimal(position.get('positionAmt', '0'))
            position_notional = Decimal(position.get('notional', '0'))
            unrealized_pnl = Decimal(position.get('unrealizedProfit', '0'))
            mark_price = Decimal(ticker.get('bidPrice'))
            base_asset = symbol.replace('USDT', '')
            spot_balance = next((Decimal(b.get('free', '0')) for b in spot_balances if b.get('asset') == base_asset), Decimal('0'))
            spot_value_usd = spot_balance * mark_price
            effective_position_value = spot_value_usd + abs(position_notional) + unrealized_pnl

        except Exception as e:
            return None

        # 2. Fetch recent trades to find the position's opening time
        try:
            trades = await self.get_user_trades(symbol=symbol, limit=1000)
            if not trades:
                return None

            trades.sort(key=lambda x: int(x['time']))
            position_start_time = None
            running_total = Decimal('0')

            for trade in reversed(trades):
                trade_qty = Decimal(trade['qty'])
                if trade['side'].upper() == 'SELL':
                    trade_qty *= -1

                running_total += trade_qty
                if abs(running_total - current_pos_amount) < Decimal('0.000001'):
                    position_start_time = int(trade['time'])
                    break

            if not position_start_time:
                return None

            start_datetime = datetime.fromtimestamp(position_start_time / 1000)

        except Exception as e:
            return None

        # 3. Fetch funding payments since the position was opened
        try:
            funding_payments = await self.get_income_history(
                symbol=symbol,
                income_type='FUNDING_FEE',
                start_time=position_start_time,
                limit=1000
            )

            total_funding = sum(Decimal(p['income']) for p in funding_payments)
            funding_percentage = (total_funding / effective_position_value) * 100 if effective_position_value != 0 else Decimal('0')

            FEE_THRESHOLD_PERCENT = Decimal('0.135')
            fee_coverage_progress = (funding_percentage / FEE_THRESHOLD_PERCENT) * 100 if funding_percentage > 0 else Decimal('0')

            return {
                "symbol": symbol,
                "position_amount": current_pos_amount,
                "position_notional": position_notional,
                "spot_balance": spot_balance,
                "effective_position_value": effective_position_value,
                "position_start_time": start_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                "funding_payments_count": len(funding_payments),
                "total_funding": total_funding,
                "funding_as_percentage_of_effective_value": funding_percentage,
                "fee_coverage_progress": fee_coverage_progress,
                "asset": funding_payments[0]['asset'] if funding_payments else 'USDT'
            }

        except Exception as e:
            return None

    async def perform_health_check_analysis(self) -> Tuple[List[str], List[str], int, List[Dict[str, Any]]]:
        """
        Shared health check logic that analyzes positions and returns health issues.

        Returns:
            Tuple of (health_issues, critical_issues, dn_positions_count, position_pnl_data)
        """
        # Fetch position analysis data
        results = await asyncio.gather(
            self.analyze_current_positions(),
            self.get_perp_account_info(),
            return_exceptions=True
        )

        analysis_results = results[0] if isinstance(results[0], dict) else {}
        perp_account_info = results[1] if isinstance(results[1], dict) else {}

        if not analysis_results:
            return [], [], 0, []

        # Process positions data into list format
        all_positions = list(analysis_results.values())

        # Use strategy logic for core health analysis
        health_issues, critical_issues, dn_positions_count = DeltaNeutralLogic.perform_portfolio_health_analysis(all_positions)

        # Add additional PnL and price-specific checks for delta-neutral positions
        dn_positions = [p for p in all_positions if p.get('is_delta_neutral')]
        raw_perp_positions = [p for p in perp_account_info.get('positions', []) if float(p.get('positionAmt', 0)) != 0]

        # Fetch current prices for perpetual positions
        if raw_perp_positions:
            price_tasks = [self.get_perp_book_ticker(p['symbol']) for p in raw_perp_positions]
            price_results = await asyncio.gather(*price_tasks, return_exceptions=True)
            for i, pos in enumerate(raw_perp_positions):
                price_data = price_results[i]
                if not isinstance(price_data, Exception) and price_data.get('bidPrice'):
                    pos['markPrice'] = (float(price_data['bidPrice']) + float(price_data['askPrice'])) / 2

        # Add PnL and liquidity specific checks and collect position data
        position_pnl_data = []

        for pos in dn_positions:
            symbol = pos.get('symbol', 'N/A')
            spot_balance = pos.get('spot_balance', 0.0)

            # Find corresponding raw perp position to get PnL data and price
            perp_pos = next((p for p in raw_perp_positions if p.get('symbol') == symbol), None)
            current_price = 0.0
            pnl_pct = None
            position_value_usd = pos.get('position_value_usd', 0.0)

            if perp_pos:
                entry_price = float(perp_pos.get('entryPrice', 0))
                mark_price = perp_pos.get('markPrice', entry_price)
                current_price = mark_price
                position_amt = float(perp_pos.get('positionAmt', 0))

                # Calculate PnL percentage for short position
                if entry_price > 0 and position_amt < 0:  # Short position
                    pnl_pct = ((entry_price - mark_price) / entry_price) * 100

                    # Check for PnL warnings
                    if pnl_pct <= -50:
                        critical_issues.append(f"CRITICAL: {symbol} short position PnL: {pnl_pct:.2f}% (below -50%)")
                    elif pnl_pct <= -25:
                        health_issues.append(f"WARNING: {symbol} short position PnL: {pnl_pct:.2f}% (below -25%)")

            # Calculate spot position value using current price
            spot_value_usd = spot_balance * current_price

            # Check spot position value for liquidity concerns
            if spot_value_usd < 10:
                if spot_value_usd < 5:
                    critical_issues.append(f"CRITICAL: {symbol} spot position value: ${spot_value_usd:.2f} (below $5 - impossible to close)")
                else:
                    health_issues.append(f"WARNING: {symbol} spot position value: ${spot_value_usd:.2f} (below $10 - rebalancing advised)")

            # Update position with current price for rendering
            pos['current_price'] = current_price

            # Store position data for display
            position_pnl_data.append({
                'symbol': symbol,
                'position_value_usd': position_value_usd,
                'pnl_pct': pnl_pct,
                'imbalance_pct': pos.get('imbalance_pct', 0.0),
                'spot_value_usd': spot_value_usd
            })

        return health_issues, critical_issues, dn_positions_count, position_pnl_data

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
