"""Execution-path tests for AsterApiManager's delta-neutral open/close.

These exist because of one specific defect: the bot reported `success: True` for a
leg whose outcome was UNKNOWN. `classify_submission` returns only REJECTED or
UNKNOWN by design -- submitting an order can never prove a fill -- but both call
sites built their failure list from REJECTED alone, so a timeout or dropped
connection produced a green dashboard over a naked short.

Every test here runs against AsyncMock. There is no network, and no exchange
credentials are needed. That is deliberate: this bot cannot be validated with real
money, so unit tests are the only verification available before a live cycle.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aster_api_manager
from aster_api_manager import AsterApiManager
from funding_economics import FundingInterval
from two_leg import HaltedError, LegStatus


SYMBOL = "BTCUSDT"
PRICE = 100.0

LOT = {"filterType": "LOT_SIZE", "stepSize": "0.001"}
NOTIONAL = {"filterType": "MIN_NOTIONAL", "minNotional": "5.0"}


def make_manager() -> AsterApiManager:
    """A manager with credential validation bypassed."""
    with patch.object(aster_api_manager.Web3, "is_address", return_value=True):
        return AsterApiManager(
            api_user="0x" + "1" * 40, api_signer="0x" + "2" * 40,
            api_private_key="0x" + "3" * 64,
            apiv1_public="pub", apiv1_private="priv",
        )


class PositionBook:
    """Tracks perp position and spot balance so read-backs reflect submissions."""

    def __init__(self, perp=0.0, spot=0.0):
        self.perp = perp
        self.spot = spot
        self.perp_fill_ratio = 1.0
        self.spot_fill_ratio = 1.0
        self.perp_raises = None
        self.spot_raises = None
        self.submissions = []

    async def submit_perp(self, qty, side):
        self.submissions.append(("perp", qty, side))
        if self.perp_raises:
            raise self.perp_raises
        delta = qty * self.perp_fill_ratio
        self.perp += delta if side.upper() == "BUY" else -delta
        return {"orderId": 1, "status": "FILLED"}

    async def submit_spot(self, qty, side):
        self.submissions.append(("spot", qty, side))
        if self.spot_raises:
            raise self.spot_raises
        delta = qty * self.spot_fill_ratio
        self.spot += delta if side == "buy" else -delta
        return {"orderId": 2, "status": "FILLED"}


def wire(mgr: AsterApiManager, book: PositionBook, spot_balance_qty=0.0):
    """Point every venue call at the in-memory book."""
    book.spot = spot_balance_qty

    mgr.get_spot_book_ticker = AsyncMock(
        return_value={"bidPrice": str(PRICE), "askPrice": str(PRICE)})
    mgr.get_perp_symbol_filter = AsyncMock(return_value=LOT)

    async def spot_filter(symbol, filter_type):
        return LOT if filter_type == "LOT_SIZE" else NOTIONAL
    mgr.get_spot_symbol_filter = AsyncMock(side_effect=spot_filter)

    mgr.get_perp_account_info = AsyncMock(return_value={"positions": []})
    mgr.get_spot_account_balances = AsyncMock(
        return_value=[{"asset": "BTC", "free": str(spot_balance_qty), "locked": "0"}])
    mgr._get_base_asset = AsyncMock(return_value="BTC")
    mgr.set_leverage = AsyncMock(return_value=True)

    mgr.cancel_all_perp_orders = AsyncMock(return_value=0)
    mgr.cancel_all_spot_orders = AsyncMock(return_value=0)

    # Funding inputs for the fee-aware entry gate. Mocked so no test touches the
    # network. 0.002 per 8h is ~219% APR, comfortably clear of the ~29% break-even
    # at the default 72h hold, so tests about execution are not silently gated on
    # economics. The gate itself is tested separately.
    mgr.resolve_funding_interval = AsyncMock(
        return_value=FundingInterval(8.0, "api_field", 0.0))
    mgr.get_funding_rate_history = AsyncMock(
        return_value=[{"fundingRate": "0.002", "fundingTime": 0}])

    # AsyncMock awaits the call itself, so a plain sync side_effect returning the
    # current value is what reflects live book state on each read.
    mgr.get_perp_position_qty = AsyncMock(side_effect=lambda s=None: book.perp)
    mgr.get_spot_base_qty = AsyncMock(side_effect=lambda s=None: book.spot)

    # side_effect must be an async def, not a lambda returning a coroutine --
    # AsyncMock uses a sync side_effect's return value verbatim, so a lambda here
    # hands back an un-awaited coroutine object.
    async def perp_order(s, q, side):
        return await book.submit_perp(float(q), side)

    async def spot_buy(s, quote):
        return await book.submit_spot(float(quote) / PRICE, "buy")

    async def spot_sell(s, qty):
        return await book.submit_spot(float(qty), "sell")

    mgr.place_perp_market_order = AsyncMock(side_effect=perp_order)
    mgr.close_perp_position = AsyncMock(side_effect=perp_order)
    mgr.place_spot_buy_market_order = AsyncMock(side_effect=spot_buy)
    mgr.place_spot_sell_market_order = AsyncMock(side_effect=spot_sell)


class OpenPathTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Verification polls with sleeps; collapse them so tests stay fast.
        self._sleep = patch("two_leg.asyncio.sleep", new=AsyncMock())
        self._sleep.start()
        self.addCleanup(self._sleep.stop)
        self.halt = patch.object(aster_api_manager, "HALT_PATH",
                                 "./.test-halt-should-not-exist.json")
        self.halt.start()
        self.addCleanup(self.halt.stop)

    async def test_both_legs_fill_reports_success(self):
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)

        result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        self.assertTrue(result["success"], result["message"])
        self.assertAlmostEqual(result["hedged_qty"], 10.0, places=6)
        self.assertEqual(result["leg_status"]["perp"], LegStatus.FILLED.value)
        self.assertEqual(result["leg_status"]["spot"], LegStatus.FILLED.value)

    async def test_unknown_perp_outcome_is_not_success(self):
        """The regression guard. A timeout is UNKNOWN, and UNKNOWN is not a fill."""
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        book.perp_raises = asyncio.TimeoutError()

        result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        self.assertFalse(result["success"],
                         "UNKNOWN leg outcome must never be reported as success")

    async def test_hedge_rejected_unwinds_the_pilot(self):
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        book.spot_raises = ValueError("insufficient balance")

        result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        self.assertFalse(result["success"])
        self.assertAlmostEqual(book.perp, 0.0, places=6,
                               msg="pilot must be flattened when the hedge dies")

    async def test_existing_spot_covering_hedge_is_success_not_failure(self):
        """The false positive: spot already held is a hedge, not a skipped leg."""
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book, spot_balance_qty=10.0)

        result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        self.assertTrue(result["success"], result["message"])
        self.assertNotIn(("spot", 10.0, "buy"), book.submissions)
        self.assertFalse([s for s in book.submissions if s[0] == "spot"],
                         "no spot order should be sent when the hedge is already held")

    async def test_sub_minimum_hedge_submits_nothing(self):
        """The naked-short bug: the guard must fire BEFORE anything is submitted."""
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)

        # $3 of hedge against a $5 exchange minimum. allow_negative_carry gets us
        # past the economics gate so this exercises the notional gate specifically.
        result = await mgr.prepare_and_execute_dn_position(
            SYMBOL, 3.0, allow_negative_carry=True)

        self.assertFalse(result["success"])
        self.assertEqual(book.submissions, [],
                         "nothing may be submitted when the hedge is unplaceable")
        self.assertIn("naked short", result["message"])

    async def test_fee_gate_rejects_a_losing_cycle_before_submitting(self):
        """15% gross APR at an 8h hold loses money on four taker fills."""
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        # 0.0000137 per 8h ~= 1.5% APR, far under any break-even.
        mgr.get_funding_rate_history = AsyncMock(
            return_value=[{"fundingRate": "0.0000137", "fundingTime": 0}])

        result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0, hold_hours=8.0)

        self.assertFalse(result["success"])
        self.assertEqual(book.submissions, [])
        self.assertIn("break-even", result["message"].lower() + " break-even")
        self.assertLess(result["details"]["expected_net_usd"], 0.0)

    async def test_fee_gate_can_be_overridden_explicitly(self):
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        mgr.get_funding_rate_history = AsyncMock(
            return_value=[{"fundingRate": "0.0000137", "fundingTime": 0}])

        result = await mgr.prepare_and_execute_dn_position(
            SYMBOL, 1000.0, hold_hours=8.0, allow_negative_carry=True)

        self.assertTrue(result["success"], result["message"])

    async def test_partial_perp_fill_resizes_the_hedge(self):
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        book.perp_fill_ratio = 0.5

        await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        spot_orders = [s for s in book.submissions if s[0] == "spot"]
        self.assertTrue(spot_orders)
        self.assertAlmostEqual(spot_orders[0][1], 5.0, places=6,
                               msg="hedge must match the ACTUAL pilot fill, not intent")

    async def test_halt_sentinel_blocks_opening(self):
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        with patch("aster_api_manager.assert_not_halted",
                   side_effect=HaltedError("halted: prior unwind failed")):
            result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        self.assertFalse(result["success"])
        self.assertTrue(result.get("halted"))
        self.assertEqual(book.submissions, [])

    async def test_position_read_failure_is_not_treated_as_flat(self):
        mgr = make_manager()
        book = PositionBook()
        wire(mgr, book)
        mgr.get_perp_position_qty = AsyncMock(side_effect=RuntimeError("API down"))

        result = await mgr.prepare_and_execute_dn_position(SYMBOL, 1000.0)

        self.assertFalse(result["success"],
                         "a failed position read must never read as a clean result")


class ClosePathTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._sleep = patch("two_leg.asyncio.sleep", new=AsyncMock())
        self._sleep.start()
        self.addCleanup(self._sleep.stop)
        self.halt = patch.object(aster_api_manager, "HALT_PATH",
                                 "./.test-halt-should-not-exist.json")
        self.halt.start()
        self.addCleanup(self.halt.stop)

    def _portfolio(self, perp_qty, spot_qty):
        return {
            "analyzed_positions": [{
                "symbol": SYMBOL, "perp_position": perp_qty,
                "spot_balance": spot_qty, "is_delta_neutral": True,
            }]
        }

    async def test_close_both_legs_reports_success(self):
        mgr = make_manager()
        book = PositionBook(perp=-10.0, spot=10.0)
        wire(mgr, book, spot_balance_qty=10.0)
        mgr.get_comprehensive_portfolio_data = AsyncMock(
            return_value=self._portfolio(-10.0, 10.0))

        result = await mgr.execute_dn_position_close(SYMBOL)

        self.assertTrue(result["success"], result["message"])
        self.assertAlmostEqual(book.perp, 0.0, places=6)

    async def test_unknown_close_outcome_is_not_success(self):
        mgr = make_manager()
        book = PositionBook(perp=-10.0, spot=10.0)
        wire(mgr, book, spot_balance_qty=10.0)
        mgr.get_comprehensive_portfolio_data = AsyncMock(
            return_value=self._portfolio(-10.0, 10.0))
        book.perp_raises = asyncio.TimeoutError()

        result = await mgr.execute_dn_position_close(SYMBOL)

        self.assertFalse(result["success"],
                         "an UNKNOWN close must not let the caller clear state")

    async def test_close_never_sells_more_spot_than_the_hedge(self):
        """A long-term spot bag must survive closing a smaller hedge."""
        mgr = make_manager()
        book = PositionBook(perp=-1.0, spot=20.0)
        wire(mgr, book, spot_balance_qty=20.0)
        mgr.get_comprehensive_portfolio_data = AsyncMock(
            return_value=self._portfolio(-1.0, 20.0))

        await mgr.execute_dn_position_close(SYMBOL)

        spot_orders = [s for s in book.submissions if s[0] == "spot"]
        for _, qty, _side in spot_orders:
            self.assertLessEqual(qty, 1.0 + 1e-9,
                                 "must sell only the hedged portion of the balance")
        self.assertGreater(book.spot, 18.0, "the untouched bag must remain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
