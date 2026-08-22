from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_revision_ux.js"
)
SAVE_INTENT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_edit_save_intent_ux.js"
)
FRONTEND_ASSETS = ROOT / "frontend_assets.py"


class TestOrderEditSaveIntentUx(unittest.TestCase):
    def test_explicit_save_clears_checkpoint_preserve_without_saving_itself(self) -> None:
        source = SAVE_INTENT_UX.read_text(encoding="utf-8")

        self.assertIn("function prepareExplicitSave(frm)", source)
        self.assertIn("if (!frm.__almdina_lock_after_save) return false;", source)
        self.assertIn("frm.__almdina_preserve_edit_session_after_save = false;", source)
        self.assertIn('frappe.ui.form.on("Door Cutting Order", {', source)
        self.assertIn("before_save(frm)", source)
        self.assertIn("prepareExplicitSave(frm);", source)

        # This module owns only the state invariant. Native persistence remains in
        # the revision owner, so it must never introduce a second save/RPC path.
        self.assertNotIn("frm.save(", source)
        self.assertNotIn("frappe.call(", source)

    def test_checkpoint_and_explicit_save_intents_remain_distinct(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        explicit = source.split("async function commitEditSession", 1)[1].split(
            "async function persistOrderEditCheckpoint", 1
        )[0]
        checkpoint = source.split("async function persistOrderEditCheckpoint", 1)[1].split(
            "function confirmEditSession", 1
        )[0]

        self.assertIn("frm.__almdina_lock_after_save = true;", explicit)
        self.assertIn("return frm.save();", explicit)
        self.assertIn("markEditSessionSticky(frm);", checkpoint)
        self.assertIn("frm.__almdina_preserve_edit_session_after_save = true;", checkpoint)
        self.assertIn("await frm.save();", checkpoint)

    def test_save_intent_guard_loads_after_revision_owner_before_page_actions(self) -> None:
        manifest = FRONTEND_ASSETS.read_text(encoding="utf-8")
        revision = manifest.index(
            '"public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"'
        )
        guard = manifest.index(
            '"public/js/door_cutting_order/core/door_cutting_order_edit_save_intent_ux.js"'
        )
        page_actions = manifest.index(
            '"public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"'
        )

        self.assertLess(revision, guard)
        self.assertLess(guard, page_actions)


if __name__ == "__main__":
    unittest.main()
