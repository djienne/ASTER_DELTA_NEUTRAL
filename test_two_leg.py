"""Tests for the two-leg execution safety primitive.

two_leg.py's own docstring notes that these bots cannot be validated with real
money, so unit tests are the only verification available. It nonetheless had no
test file at all.

The rule under test throughout: SUBMITTING AN ORDER NEVER YIELDS "FILLED".
Submission distinguishes only *definitely dead* from *maybe live*; only reading the
position back can promote a leg to FILLED.
"""
import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from two_leg import (
    HaltedError,
    LegSpec,
    LegStatus,
    assert_not_halted,
    classify_submission,
    execute_two_leg,
    read_halt,
    unwind_leg,
    verify_fill,
    write_halt,
)


class ClassifySubmissionTests(unittest.TestCase):
    """Each venue client signals failure differently; all must normalise."""

    def _classify(self, raw):
        return classify_submission("v", raw, intent_qty=1.0, symbol="BTC", side="buy")

    def test_none_is_rejected(self):
        self.assertIs(self._classify(None).status, LegStatus.REJECTED)

    def test_false_is_rejected(self):
        self.assertIs(self._classify(False).status, LegStatus.REJECTED)

    def test_error_code_is_rejected(self):
        res = self._classify({"code": -1013, "msg": "min notional"})
        self.assertIs(res.status, LegStatus.REJECTED)
        self.assertIn("-1013", res.error)

    def test_success_false_is_rejected(self):
        self.assertIs(self._classify({"success": False}).status, LegStatus.REJECTED)

    def test_ordinary_exception_is_rejected(self):
        self.assertIs(self._classify(ValueError("bad symbol")).status, LegStatus.REJECTED)

    def test_timeout_is_unknown_not_rejected(self):
        """The distinction the whole module exists for."""
        res = self._classify(asyncio.TimeoutError())
        self.assertIs(res.status, LegStatus.UNKNOWN)

    def test_connection_error_is_unknown(self):
        self.assertIs(self._classify(ConnectionError("reset")).status, LegStatus.UNKNOWN)

    def test_accepted_order_is_unknown_never_filled(self):
        res = self._classify({"orderId": 42, "status": "NEW"})
        self.assertIs(res.status, LegStatus.UNKNOWN)
        self.assertEqual(res.order_ref, "42")

    def test_bare_true_is_unknown_not_filled(self):
        self.assertIs(self._classify(True).status, LegStatus.UNKNOWN)

    def test_success_code_is_unknown_not_filled(self):
        res = self._classify({"code": "SUCCESS", "data": {"order_id": "7"}})
        self.assertIs(res.status, LegStatus.UNKNOWN,
                      "a SUCCESS submission is still not a proven fill")


class VerifyFillTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._sleep = patch("two_leg.asyncio.sleep", new=AsyncMock())
        self._sleep.start()
        self.addCleanup(self._sleep.stop)

    async def test_stable_full_fill(self):
        status, delta = await verify_fill(
            AsyncMock(return_value=-5.0), baseline_signed_qty=0.0,
            intent_signed_delta=-5.0, amount_tick=0.001, settle_delay_s=0.0)
        self.assertIs(status, LegStatus.FILLED)
        self.assertAlmostEqual(delta, -5.0)

    async def test_no_movement_is_rejected(self):
        status, _ = await verify_fill(
            AsyncMock(return_value=0.0), baseline_signed_qty=0.0,
            intent_signed_delta=-5.0, amount_tick=0.001, settle_delay_s=0.0)
        self.assertIs(status, LegStatus.REJECTED)

    async def test_partial_fill(self):
        status, _ = await verify_fill(
            AsyncMock(return_value=-2.0), baseline_signed_qty=0.0,
            intent_signed_delta=-5.0, amount_tick=0.001, settle_delay_s=0.0)
        self.assertIs(status, LegStatus.PARTIAL)

    async def test_baseline_is_respected(self):
        """A pre-existing position must not be mistaken for our own fill."""
        status, delta = await verify_fill(
            AsyncMock(return_value=-15.0), baseline_signed_qty=-10.0,
            intent_signed_delta=-5.0, amount_tick=0.001, settle_delay_s=0.0)
        self.assertIs(status, LegStatus.FILLED)
        self.assertAlmostEqual(delta, -5.0)

    async def test_read_failure_never_reports_flat(self):
        """The 'fails open to 0.0' bug: a failed read is not evidence of anything."""
        status, _ = await verify_fill(
            AsyncMock(side_effect=RuntimeError("api down")), baseline_signed_qty=0.0,
            intent_signed_delta=-5.0, amount_tick=0.001, settle_delay_s=0.0,
            timeout_s=0.0)
        self.assertIs(status, LegStatus.UNKNOWN)
        self.assertIsNot(status, LegStatus.REJECTED)

    async def test_movement_in_the_wrong_direction_is_not_a_fill(self):
        status, _ = await verify_fill(
            AsyncMock(return_value=5.0), baseline_signed_qty=0.0,
            intent_signed_delta=-5.0, amount_tick=0.001, settle_delay_s=0.0)
        self.assertIs(status, LegStatus.UNKNOWN)


class HaltSentinelTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "halt.json")

    def test_write_then_assert_raises(self):
        write_halt("unwind failed", symbol="BTCUSDT", venue="Aster-perp",
                   residual_qty=0.5, path=self.path)
        self.assertTrue(os.path.exists(self.path))
        with self.assertRaises(HaltedError):
            assert_not_halted(self.path)

    def test_absent_sentinel_does_not_raise(self):
        assert_not_halted(self.path)  # must not raise

    def test_unreadable_sentinel_still_counts_as_halted(self):
        """Failing open here would defeat the entire mechanism."""
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        self.assertIsNotNone(read_halt(self.path))
        with self.assertRaises(HaltedError):
            assert_not_halted(self.path)

    def test_payload_records_the_residual(self):
        write_halt("boom", symbol="ETHUSDT", venue="Aster-spot",
                   residual_qty=1.25, path=self.path)
        with open(self.path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["symbol"], "ETHUSDT")
        self.assertEqual(payload["residual_qty"], 1.25)


def make_leg(name, side, qty, *, submit, read_position,
             close_market=None, cancel_open=None, tick=0.001):
    return LegSpec(
        name=name, symbol="BTCUSDT", side=side, intent_qty=qty,
        submit=submit, read_position=read_position,
        close_market=close_market or AsyncMock(return_value={"code": "SUCCESS"}),
        cancel_open=cancel_open or AsyncMock(return_value=0),
        amount_tick=tick, settle_delay_s=0.0,
    )


class ExecuteTwoLegTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._sleep = patch("two_leg.asyncio.sleep", new=AsyncMock())
        self._sleep.start()
        self.addCleanup(self._sleep.stop)
        self.dir = tempfile.mkdtemp()
        self.halt = os.path.join(self.dir, "halt.json")

    async def test_happy_path(self):
        perp, spot = {"q": 0.0}, {"q": 0.0}

        async def perp_submit(q):
            perp["q"] -= q
            return {"orderId": 1}

        async def spot_submit(q):
            spot["q"] += q
            return {"orderId": 2}

        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=perp_submit,
                     read_position=AsyncMock(side_effect=lambda: perp["q"])),
            make_leg("spot", "buy", 5.0, submit=spot_submit,
                     read_position=AsyncMock(side_effect=lambda: spot["q"])),
            halt_path=self.halt,
        )
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertAlmostEqual(outcome.hedged_qty, 5.0)

    async def test_rejected_pilot_leaves_nothing_live(self):
        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=AsyncMock(return_value=None),
                     read_position=AsyncMock(return_value=0.0)),
            make_leg("spot", "buy", 5.0, submit=AsyncMock(return_value={"orderId": 2}),
                     read_position=AsyncMock(return_value=0.0)),
            halt_path=self.halt,
        )
        self.assertFalse(outcome.ok)
        self.assertIn("pilot rejected", outcome.reason)

    async def test_hedge_rejected_unwinds_the_pilot(self):
        perp = {"q": 0.0}

        async def perp_submit(q):
            perp["q"] -= q
            return {"orderId": 1}

        async def perp_close(q, side):
            perp["q"] += q
            return {"code": "SUCCESS"}

        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=perp_submit,
                     read_position=AsyncMock(side_effect=lambda: perp["q"]),
                     close_market=perp_close),
            make_leg("spot", "buy", 5.0, submit=AsyncMock(return_value=None),
                     read_position=AsyncMock(return_value=0.0)),
            halt_path=self.halt,
        )
        self.assertFalse(outcome.ok)
        self.assertAlmostEqual(perp["q"], 0.0, places=6, msg="pilot must be flattened")
        self.assertFalse(os.path.exists(self.halt), "a clean unwind must not halt")

    async def test_failed_unwind_writes_halt_and_blocks_next_call(self):
        perp = {"q": 0.0}

        async def perp_submit(q):
            perp["q"] -= q
            return {"orderId": 1}

        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=perp_submit,
                     read_position=AsyncMock(side_effect=lambda: perp["q"]),
                     close_market=AsyncMock(side_effect=RuntimeError("cannot close"))),
            make_leg("spot", "buy", 5.0, submit=AsyncMock(return_value=None),
                     read_position=AsyncMock(return_value=0.0)),
            halt_path=self.halt, unwind_attempts=2,
        )
        self.assertFalse(outcome.ok)
        self.assertTrue(outcome.halted)
        self.assertTrue(os.path.exists(self.halt))
        with self.assertRaises(HaltedError):
            await execute_two_leg(
                make_leg("perp", "sell", 1.0, submit=AsyncMock(return_value={"orderId": 1}),
                         read_position=AsyncMock(return_value=0.0)),
                make_leg("spot", "buy", 1.0, submit=AsyncMock(return_value={"orderId": 2}),
                         read_position=AsyncMock(return_value=0.0)),
                halt_path=self.halt,
            )

    async def test_hedge_is_sized_from_actual_pilot_fill(self):
        perp, spot = {"q": 0.0}, {"q": 0.0}
        submitted = []

        async def perp_submit(q):
            perp["q"] -= q * 0.6          # venue only fills 60%
            return {"orderId": 1}

        async def spot_submit(q):
            submitted.append(q)
            spot["q"] += q
            return {"orderId": 2}

        await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=perp_submit,
                     read_position=AsyncMock(side_effect=lambda: perp["q"])),
            make_leg("spot", "buy", 5.0, submit=spot_submit,
                     read_position=AsyncMock(side_effect=lambda: spot["q"])),
            halt_path=self.halt,
        )
        self.assertTrue(submitted)
        self.assertAlmostEqual(submitted[0], 3.0, places=6,
                               msg="hedge must follow the fill, not the intent")

    async def test_sizing_hook_skips_the_order_when_hedge_already_held(self):
        """The Aster case: spot already owned counts toward the hedge."""
        perp, spot = {"q": 0.0}, {"q": 5.0}
        spot_submit = AsyncMock(return_value={"orderId": 2})

        async def perp_submit(q):
            perp["q"] -= q
            return {"orderId": 1}

        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=perp_submit,
                     read_position=AsyncMock(side_effect=lambda: perp["q"])),
            make_leg("spot", "buy", 0.0, submit=spot_submit,
                     read_position=AsyncMock(side_effect=lambda: spot["q"])),
            halt_path=self.halt,
            hedge_qty_from_pilot=lambda filled: max(0.0, filled - 5.0),
        )
        self.assertTrue(outcome.ok, outcome.reason)
        spot_submit.assert_not_awaited()
        self.assertAlmostEqual(outcome.hedged_qty, 5.0)

    async def test_sizing_hook_buys_only_the_shortfall(self):
        perp, spot = {"q": 0.0}, {"q": 2.0}
        submitted = []

        async def perp_submit(q):
            perp["q"] -= q
            return {"orderId": 1}

        async def spot_submit(q):
            submitted.append(q)
            spot["q"] += q
            return {"orderId": 2}

        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=perp_submit,
                     read_position=AsyncMock(side_effect=lambda: perp["q"])),
            make_leg("spot", "buy", 3.0, submit=spot_submit,
                     read_position=AsyncMock(side_effect=lambda: spot["q"])),
            halt_path=self.halt,
            hedge_qty_from_pilot=lambda filled: max(0.0, filled - 2.0),
        )
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertAlmostEqual(submitted[0], 3.0, places=6)
        self.assertAlmostEqual(outcome.hedged_qty, 5.0, places=6,
                               msg="coverage is existing spot plus what was bought")

    async def test_baseline_read_failure_aborts_before_submitting(self):
        submit = AsyncMock(return_value={"orderId": 1})
        outcome = await execute_two_leg(
            make_leg("perp", "sell", 5.0, submit=submit,
                     read_position=AsyncMock(side_effect=RuntimeError("down"))),
            make_leg("spot", "buy", 5.0, submit=AsyncMock(return_value={"orderId": 2}),
                     read_position=AsyncMock(return_value=0.0)),
            halt_path=self.halt,
        )
        self.assertFalse(outcome.ok)
        submit.assert_not_awaited()
        self.assertIn("baseline", outcome.reason)


class UnwindLegTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._sleep = patch("two_leg.asyncio.sleep", new=AsyncMock())
        self._sleep.start()
        self.addCleanup(self._sleep.stop)
        self.halt = os.path.join(tempfile.mkdtemp(), "halt.json")

    async def test_already_flat_is_success(self):
        ok = await unwind_leg(
            make_leg("perp", "sell", 5.0, submit=AsyncMock(),
                     read_position=AsyncMock(return_value=0.0)),
            baseline_signed_qty=0.0, halt_path=self.halt)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(self.halt))

    async def test_exhausted_attempts_writes_halt(self):
        ok = await unwind_leg(
            make_leg("perp", "sell", 5.0, submit=AsyncMock(),
                     read_position=AsyncMock(return_value=-5.0),
                     close_market=AsyncMock(side_effect=RuntimeError("nope"))),
            baseline_signed_qty=0.0, attempts=2, halt_path=self.halt)
        self.assertFalse(ok)
        self.assertTrue(os.path.exists(self.halt))


if __name__ == "__main__":
    unittest.main(verbosity=2)
