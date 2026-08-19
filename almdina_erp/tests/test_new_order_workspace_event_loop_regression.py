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

    def test_new_order_presenter_reload_path_cannot_re_dispatch_forever(self) -> None:
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

                # The presenters intentionally request a load while showing a
                # pending surface. On unsaved DCOs that call re-enters load()
                # synchronously through the workspace-updated event, so load()
                # must settle the same unavailable identity without dispatching
                # a second event.
                self.assertIn("ensureLoad(frm);", presenter)
                self.assertIn(f'addEventListener("{event_name}"', presenter)
                self.assertIn("function settleUnavailable", state)
                self.assertIn("store.snapshot()", state)
                self.assertIn("return current;", state)


if __name__ == "__main__":
    unittest.main()
