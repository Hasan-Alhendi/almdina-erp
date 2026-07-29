from __future__ import annotations

import json
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
FORM_PATH = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
HOOKS_PATH = APP_ROOT / "hooks.py"
EDIT_POLICY_PATH = APP_ROOT / "almdina_erp" / "services" / "order_edit_policy.py"
REVISION_SERVICE_PATH = APP_ROOT / "almdina_erp" / "services" / "order_revision_service.py"
REVISION_UX_PATH = APP_ROOT / "public" / "js" / "door_cutting_order_revision_ux.js"


class TestOrderRevisionContract(unittest.TestCase):
    def test_doctype_contains_revision_chain_metadata(self) -> None:
        payload = json.loads(FORM_PATH.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in payload["fields"]}
        for fieldname in ("revision_of", "revision_root", "superseded_by", "revision_reason"):
            self.assertIn(fieldname, fields)
            self.assertEqual(fields[fieldname].get("read_only"), 1)
        for fieldname in ("revision_of", "revision_root", "superseded_by"):
            self.assertEqual(fields[fieldname].get("options"), "Door Cutting Order")

    def test_edit_policy_never_unlinks_an_approved_plan(self) -> None:
        source = EDIT_POLICY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("unlock_frozen_plan_for_editor", source)
        self.assertNotIn("order.approved_plan = None", source)
        self.assertIn("Create a controlled revision instead", source)

    def test_legacy_return_to_draft_routes_to_revision_use_case(self) -> None:
        hooks = HOOKS_PATH.read_text(encoding="utf-8")
        target = "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision"
        self.assertGreaterEqual(hooks.count(target), 2)
        self.assertIn('"public/js/door_cutting_order_revision_ux.js"', hooks)

    def test_revision_service_resets_new_copy_without_mutating_source_plan(self) -> None:
        source = REVISION_SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn('"approved_plan": None', source)
        self.assertIn('frappe.copy_doc(source)', source)
        self.assertIn('"superseded_by", revised.name', source)
        self.assertNotIn('frappe.db.set_value("Door Cutting Order", source.name, "approved_plan"', source)

    def test_revision_ui_replaces_direct_draft_rollback(self) -> None:
        source = REVISION_UX_PATH.read_text(encoding="utf-8")
        self.assertIn('frm.remove_custom_button(__("إعادة للمسودة")', source)
        self.assertIn('__("إنشاء نسخة تعديل")', source)
        self.assertIn("order_revision_service.create_order_revision", source)
        self.assertIn("DRAFT_LIKE.has(frm.doc.status", source)


if __name__ == "__main__":
    unittest.main()
