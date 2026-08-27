from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"


class TestNewOrderWorkspaceEventLoopRegression(unittest.TestCase):
    def test_unavailable_workspace_settlement_is_idempotent(self) -> None:
        state_files = (
            PUBLIC / "cutting_plan" / "door_cutting_order_plan_workspace_state.js",
            PUBLIC / "costing" / "door_cutting_order_cost_workspace_state.js",
        )

        for path in state_files:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("function settleUnavailable(frm, store, currentIdentity)", source)
                self.assertIn("frm[LOADED_IDENTITY_KEY] === currentIdentity", source)
                self.assertIn("current.identity === currentIdentity", source)
                self.assertIn('current.status === "idle"', source)
                self.assertIn("return current;", source)
                self.assertIn("frm[LOAD_PROMISE_KEY] = null;", source)
                self.assertIn(
                    "return settleUnavailable(frm, store, currentIdentity);",
                    source,
                )

    def test_workspace_event_rerender_path_cannot_restart_workspace_load(self) -> None:
        pairs = (
            (
                PUBLIC / "cutting_plan" / "door_cutting_order_plan_workspace_state.js",
                PUBLIC
                / "cutting_plan"
                / "door_cutting_order_plan_workspace_presenter_adapter.js",
                "almdina:plan-workspace-updated",
            ),
            (
                PUBLIC / "costing" / "door_cutting_order_cost_workspace_state.js",
                PUBLIC
                / "costing"
                / "door_cutting_order_cost_workspace_presenter_adapter.js",
                "almdina:cost-workspace-updated",
            ),
        )

        for state_path, presenter_path, event_name in pairs:
            with self.subTest(event=event_name):
                state = state_path.read_text(encoding="utf-8")
                presenter = presenter_path.read_text(encoding="utf-8")

                # Workspace-updated events are synchronous. Their presenter path
                # must therefore remain presentation-only; otherwise a loading
                # notification can recurse back into load() before the first
                # transport settles.
                self.assertIn(f'addEventListener("{event_name}"', presenter)
                pending = presenter.split("function renderPending(frm)", 1)[1].split(
                    "\n    function ",
                    1,
                )[0]
                self.assertNotIn("ensureLoad(frm);", pending)
                self.assertNotIn(".load(", pending)

                # The state owner installs its single-flight barrier before the
                # observable loading state and event are emitted, so any explicit
                # load re-entry elsewhere is coalesced onto the same flight.
                barrier = state.index("frm[LOAD_PROMISE_KEY] = promise;")
                begin_load = state.index("store.beginLoad(currentIdentity)", barrier)
                loading_dispatch = state.index(
                    "dispatch(frm, store.snapshot());",
                    begin_load,
                )
                self.assertLess(barrier, begin_load)
                self.assertLess(begin_load, loading_dispatch)
                self.assertIn("const pending = frm[LOAD_PROMISE_KEY];", state)
                self.assertIn("return pending;", state)


if __name__ == "__main__":
    unittest.main()
