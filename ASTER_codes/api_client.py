import time
import aiohttp
import hmac
import hashlib
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_abi import encode
import json
import math
import urllib.parse

class ApiClient:
    """
    An asynchronous client for interacting with the Aster Finance API,
    handling session management and request signing.
    """

    def __init__(self, api_user, api_signer, api_private_key, release_mode=True):
        if not api_user or not Web3.is_address(api_user):
            raise ValueError("API_USER is missing or not a valid Ethereum address.")
        if not api_signer or not Web3.is_address(api_signer):
            raise ValueError("API_SIGNER is missing or not a valid Ethereum address.")
        if not api_private_key:
            raise ValueError("API_PRIVATE_KEY is missing.")

        self.user = api_user
        self.signer = api_signer
        self.private_key = api_private_key
        self.release_mode = release_mode

        self.base_url = "https://fapi.asterdex.com"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _trim_dict(self, my_dict):
        """Recursively converts all values in a dictionary to strings, matching the API doc example."""
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

    def _sign(self, params):
        """Signs the request parameters using the exact logic from the API documentation."""
        nonce = math.trunc(time.time() * 1000000)
        my_dict = {k: v for k, v in params.items() if v is not None}
        my_dict["recvWindow"] = 50000
        my_dict["timestamp"] = int(round(time.time() * 1000))

        # Use the recursive trim function
        self._trim_dict(my_dict)

        # Create the JSON string exactly as in the documentation
        json_str = json.dumps(my_dict, sort_keys=True).replace(' ', '')

        # Encode and hash
        encoded = encode(['string', 'address', 'address', 'uint256'],
                         [json_str, self.user, self.signer, nonce])
        keccak_hex = Web3.keccak(encoded).hex()

        # Sign the message
        signable_msg = encode_defunct(hexstr=keccak_hex)
        signed_message = Account.sign_message(signable_message=signable_msg, private_key=self.private_key)

        # Append auth data to the dictionary
        my_dict['nonce'] = nonce
        my_dict['user'] = self.user
        my_dict['signer'] = self.signer
        my_dict['signature'] = '0x' + signed_message.signature.hex()

        return my_dict

    async def signed_request(self, method: str, endpoint: str, params: dict = None):
        """Generic method for making signed requests to the API."""
        if params is None:
            params = {}

        url = f"{self.base_url}{endpoint}"
        signed_params = self._sign(params)
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'PythonApp/1.0'}

        if method.upper() == 'GET':
            # For GET requests, parameters must be in the query string.
            # We manually build the URL to ensure correct encoding.
            query_string = urllib.parse.urlencode(signed_params)
            full_url = f"{url}?{query_string}"
            async with self.session.get(full_url, headers=headers) as response:
                if not response.ok:
                    error_body = await response.text()
                    if not self.release_mode:
                        print(f"API Error on {method} {endpoint}: Status={response.status}, Body={error_body}")
                response.raise_for_status()
                return await response.json()

        elif method.upper() == 'POST':
            # For POST, parameters are in the body. This logic was working.
            async with self.session.post(url, data=signed_params, headers=headers) as response:
                if not response.ok:
                    error_body = await response.text()
                    if not self.release_mode:
                        print(f"API Error on {method} {endpoint}: Status={response.status}, Body={error_body}")
                response.raise_for_status()
                return await response.json()

        elif method.upper() == 'DELETE':
             # For DELETE, parameters are in the body. This logic was working.
             async with self.session.delete(url, data=signed_params, headers=headers) as response:
                if not response.ok:
                    error_body = await response.text()
                    if not self.release_mode:
                        print(f"API Error on {method} {endpoint}: Status={response.status}, Body={error_body}")
                response.raise_for_status()
                return await response.json()
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    # --- Public Methods from original file ---

    async def get_exchange_info(self):
        """Gets exchange information. This is a public endpoint."""
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        async with self.session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def place_order(self, symbol, price, quantity, side, reduce_only=False):
        """Places a limit post-only order using Ethereum signature auth."""
        params = {
            "symbol": symbol, "side": side, "type": "LIMIT",
            "timeInForce": "GTX", "price": price, "quantity": quantity,
            "positionSide": "BOTH"
        }
        if reduce_only:
            params['reduceOnly'] = 'true'
        return await self.signed_request('POST', '/fapi/v3/order', params)
