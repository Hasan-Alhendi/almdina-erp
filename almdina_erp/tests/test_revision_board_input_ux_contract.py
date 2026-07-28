from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION_UX = ROOT / "public" / "js" / "door_cutting_order_revision_ux.js"
BOARD_TEXT_UX = ROOT / "public" / "js" / "door_cutting_order_board_text_ux.js"
FAST_SAVE_UX = ROOT / "public" / "js" / "door_cutting_order_fast_save_ux.js"
TEXT_BOARD_PLAN_UX = ROOT / "public" / "js" / "door_cutting_order_text_board_plan_ux.js"
DOCTYPE_JSON = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)


class TestRevisionReasonUxContract(unittest.TestCase):
    def test_revision_dialog_requires_and_forwards_reason(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        self.assertIn('fieldname: "reason"', source)
        self.assertIn("reqd: 1", source)
        self.assertIn('const reason = String(values.reason || "").trim()', source)
        self.assertIn(
            "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
            source,
        )
        self.assertIn("args: { order_name: frm.doc.name, reason }", source)

    def test_legacy_return_to_draft_button_is_intercepted(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        self.assertIn("function installLegacyReturnButtonGuard", source)
        self.assertIn('label.includes(__("إعادة للمسودة"))', source)
        self.assertIn("event.stopImmediatePropagation()", source)
        self.assertIn("openRevision(frm)", source)


class TestBoardInputSyncContract(unittest.TestCase):
    def test_visible_board_controls_are_the_source_of_truth(self) -> None:
        source = BOARD_TEXT_UX.read_text(encoding="utf-8")
        self.assertIn("function controlValue", source)
        self.assertIn("field.$input.val()", source)
        self.assertIn("async function syncInputs", source)
        self.assertIn("await frm.set_value(updates)", source)
        self.assertIn("before_save(frm) { return syncInputs(frm); }", source)
        self.assertIn("syncInputs,", source)

    def test_plan_actions_flush_board_controls_before_validation(self) -> None:
        cases = (
            (FAST_SAVE_UX, "if (!boardUX || !boardUX.canCalculatePlan(frm))"),
            (TEXT_BOARD_PLAN_UX, "if (!validatePlanInputs(frm)"),
        )
        for path, validation_token in cases:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                sync_index = source.index("await boardUX.syncInputs(frm)")
                validation_index = source.index(validation_token)
                self.assertLess(sync_index, validation_index)

    def test_doctype_uses_free_text_board_field_not_hidden_stock_item(self) -> None:
        payload = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in payload["fields"]}

        self.assertEqual(fields["board_description"]["fieldtype"], "Data")
        self.assertEqual(fields["board_description"].get("reqd"), 1)
        self.assertEqual(fields["board_item"].get("hidden"), 1)
        self.assertFalse(fields["board_item"].get("reqd", 0))


if __name__ == "__main__":
    unittest.main()
