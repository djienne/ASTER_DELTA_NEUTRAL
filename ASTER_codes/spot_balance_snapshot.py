#!/usr/bin/env python3
"""Simple helper to retrieve Aster spot account balances with USD valuation."""

from __future__ import annotations

import os
import sys
import time
import json
import hmac
import hashlib
from decimal import Decimal, InvalidOperation, getcontext
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

BASE_URL = "https://sapi.asterdex.com"
DEFAULT_TIMEOUT = 10
PRICE_STABLE_QUOTES = ("USDT", "BUSD", "USDC", "USDD", "USD")

# Basic configuration – edit these constants if you need different behaviour.
BASE_ASSET = "USDT"
USD_RATE = Decimal("1")
MIN_TOTAL = Decimal("0")
SHOW_ZERO = False
OUTPUT_JSON = False


def decimal_from(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("0")


def sign_params(params: Dict[str, str], secret: str) -> Dict[str, str]:
    query_string = urlencode(params, doseq=True)
    signature = hmac.new(secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
    signed = dict(params)
    signed["signature"] = signature
    return signed


class SpotClient:
    def __init__(self, api_key: str, api_secret: str, timeout: int = DEFAULT_TIMEOUT):
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": api_key, "User-Agent": "AsterSpotBalance/1.0"})
        self.api_secret = api_secret
        self.timeout = timeout
        self.price_cache: Dict[str, Decimal] = {}

    def _request(self, method: str, path: str, params: Optional[Dict[str, str]] = None,
                 signed: bool = False) -> requests.Response:
        params = params.copy() if params else {}
        url = f"{BASE_URL}{path}"

        if signed:
            params.setdefault("recvWindow", "5000")
            params["timestamp"] = str(int(time.time() * 1000))
            signed_params = sign_params(params, self.api_secret)
        else:
            signed_params = params

        response = self.session.request(method, url, params=signed_params if method.upper() == "GET" else None,
                                        data=signed_params if method.upper() != "GET" else None,
                                        timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_account_balances(self) -> List[Dict[str, str]]:
        response = self._request("GET", "/api/v1/account", signed=True)
        payload = response.json()
        return payload.get("balances", [])

    def get_price(self, symbol: str) -> Decimal:
        symbol = symbol.upper()
        if symbol in self.price_cache:
            return self.price_cache[symbol]

        response = self._request("GET", "/api/v1/ticker/price", params={"symbol": symbol})
        data = response.json()
        if isinstance(data, dict) and "price" in data:
            price = Decimal(str(data["price"]))
            self.price_cache[symbol] = price
            return price
        raise RuntimeError(f"Unexpected price payload for {symbol}: {data}")

    def find_conversion_rate(self, asset: str, base_asset: str) -> Optional[Decimal]:
        asset = asset.upper()
        base_asset = base_asset.upper()

        if asset == base_asset:
            return Decimal("1")

        # Direct pair
        direct_symbol = f"{asset}{base_asset}"
        try:
            return self.get_price(direct_symbol)
        except Exception:
            pass

        # Inverse pair
        inverse_symbol = f"{base_asset}{asset}"
        try:
            inverse_price = self.get_price(inverse_symbol)
            if inverse_price and inverse_price != 0:
                return Decimal("1") / inverse_price
        except Exception:
            pass

        # Bridge using stable quotes
        bridge_priority = [base_asset] + [q for q in PRICE_STABLE_QUOTES if q not in {asset, base_asset}]

        for intermediate in bridge_priority:
            if intermediate == asset:
                continue

            asset_to_intermediate = self._pair_price(asset, intermediate)
            if asset_to_intermediate is None:
                continue

            if intermediate == base_asset:
                return asset_to_intermediate

            intermediate_to_base = self._pair_price(intermediate, base_asset)
            if intermediate_to_base is None:
                continue

            return asset_to_intermediate * intermediate_to_base

        return None

    def _pair_price(self, base: str, quote: str) -> Optional[Decimal]:
        if base == quote:
            return Decimal("1")

        symbol = f"{base}{quote}"
        try:
            return self.get_price(symbol)
        except Exception:
            pass

        inverse_symbol = f"{quote}{base}"
        try:
            inverse_price = self.get_price(inverse_symbol)
            if inverse_price and inverse_price != 0:
                return Decimal("1") / inverse_price
        except Exception:
            pass
        return None


def load_credentials() -> Tuple[str, str]:
    load_dotenv()
    api_key = os.getenv("APIV1_PUBLIC_KEY")
    api_secret = os.getenv("APIV1_PRIVATE_KEY")

    if not api_key or not api_secret:
        print("Missing APIV1_PUBLIC_KEY or APIV1_PRIVATE_KEY in the environment.", file=sys.stderr)
        sys.exit(1)

    return api_key, api_secret


def format_table(rows: Iterable[Dict[str, object]], base_asset: str, total_base: Decimal, total_usd: Decimal) -> str:
    base_label = f"Value ({base_asset.upper()})"
    header = ["Asset", "Free", "Locked", "Total", f"Price ({base_asset.upper()})", base_label, "Value (USD)"]
    table_data = [header]

    def fmt(value: Optional[Decimal], precision: int = 8) -> str:
        if value is None:
            return "-"
        return f"{value:.{precision}f}".rstrip("0").rstrip(".") if value != 0 else "0"

    for row in rows:
        table_data.append([
            row["asset"],
            fmt(row["free"]),
            fmt(row["locked"]),
            fmt(row["total"]),
            fmt(row.get("price"), precision=8),
            fmt(row.get("base_value"), precision=8),
            fmt(row.get("usd_value"), precision=8),
        ])

    footer = ["TOTAL", "", "", "", "", fmt(total_base, precision=8), fmt(total_usd, precision=8)]
    table_data.append(footer)

    col_widths = [max(len(str(row[idx])) for row in table_data) for idx in range(len(header))]

    formatted_lines = []
    for row in table_data:
        formatted_row = "  ".join(str(value).ljust(col_widths[idx]) if idx == 0 else str(value).rjust(col_widths[idx])
                                   for idx, value in enumerate(row))
        formatted_lines.append(formatted_row)

    return "\n".join(formatted_lines)


def main() -> None:
    api_key, api_secret = load_credentials()
    client = SpotClient(api_key, api_secret, timeout=DEFAULT_TIMEOUT)

    try:
        balances = client.get_account_balances()
    except requests.HTTPError as exc:
        print(f"Failed to fetch account balances: {exc}", file=sys.stderr)
        if exc.response is not None:
            print(exc.response.text, file=sys.stderr)
        sys.exit(1)

    usd_rate = USD_RATE
    base_asset = BASE_ASSET.upper()

    rows = []
    total_base_value = Decimal("0")
    total_usd_value = Decimal("0")

    for balance in balances:
        asset = balance.get("asset", "").upper()
        free_amt = decimal_from(balance.get("free", "0"))
        locked_amt = decimal_from(balance.get("locked", "0"))
        total_amt = free_amt + locked_amt

        if not SHOW_ZERO and total_amt <= MIN_TOTAL:
            continue

        row = {
            "asset": asset,
            "free": free_amt,
            "locked": locked_amt,
            "total": total_amt
        }

        if total_amt > 0:
            conversion = client.find_conversion_rate(asset, base_asset)
            if conversion is not None:
                base_value = total_amt * conversion
                usd_value = base_value * usd_rate
                row["price"] = conversion
                row["base_value"] = base_value
                row["usd_value"] = usd_value
                total_base_value += base_value
                total_usd_value += usd_value
            else:
                row["price"] = None
                row["base_value"] = None
                row["usd_value"] = None
        else:
            row["price"] = Decimal("0")
            row["base_value"] = Decimal("0")
            row["usd_value"] = Decimal("0")

        rows.append(row)

    rows.sort(key=lambda item: item["asset"])

    if OUTPUT_JSON:
        output = {
            "base_asset": base_asset,
            "usd_rate": float(usd_rate),
            "assets": [
                {
                    "asset": row["asset"],
                    "free": float(row["free"]),
                    "locked": float(row["locked"]),
                    "total": float(row["total"]),
                    "price_in_base": float(row["price"]) if isinstance(row.get("price"), Decimal) else None,
                    "value_in_base": float(row["base_value"]) if isinstance(row.get("base_value"), Decimal) else None,
                    "value_in_usd": float(row["usd_value"]) if isinstance(row.get("usd_value"), Decimal) else None,
                }
                for row in rows
            ],
            "totals": {
                "value_in_base": float(total_base_value),
                "value_in_usd": float(total_usd_value)
            }
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_table(rows, base_asset, total_base_value, total_usd_value))


if __name__ == "__main__":
    getcontext().prec = 28
    main()
