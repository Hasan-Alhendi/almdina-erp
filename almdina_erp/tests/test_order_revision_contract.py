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
LIFECYCLE_UX_PATH = APP_ROOT / "public" / "js" / "order_lifecycle.js"


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
        self.assertIn("يمكن تعديل الطلب", source)

    def test_legacy_return_to_draft_routes_to_in_place_lifecycle_reset(self) -> None:
        hooks = HOOKS_PATH.read_text(encoding="utf-8")
        target = "almdina_erp.almdina_erp.services.order_revision_service.return_order_to_draft"
        self.assertGreaterEqual(hooks.count(target), 2)
        self.assertIn('"public/js/door_cutting_order_revision_ux.js"', hooks)
        self.assertIn('"public/js/order_lifecycle.js"', hooks)

        revision = REVISION_SERVICE_PATH.read_text(encoding="utf-8")
        return_fn = revision.split("def return_order_to_draft", 1)[1]
        self.assertIn("order_lifecycle_service", return_fn)
        self.assertIn("reset_same_order", return_fn)
        self.assertNotIn("_create_revision", return_fn)

        lifecycle = (
            APP_ROOT
            / "almdina_erp"
            / "services"
            / "order_lifecycle_service.py"
        ).read_text(encoding="utf-8")
        in_place = lifecycle.split("def return_order_to_draft", 1)[1]
        self.assertIn("_IN_PLACE_DRAFT_FIELDS", lifecycle)
        self.assertIn('"status": "Draft"', lifecycle)
        self.assertIn('"in_place": True', in_place)
        self.assertIn("_cancel_stages", in_place)
        self.assertIn("OrderLifecycleAction.RETURN_TO_DRAFT", in_place)
        self.assertNotIn("frappe.copy_doc", in_place)

    def test_revision_service_resets_new_copy_without_mutating_source_plan(self) -> None:
        source = REVISION_SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn('"approved_plan": None', source)
        self.assertIn("frappe.copy_doc(source)", source)
        self.assertIn('"superseded_by"', source)
        self.assertIn("revised.name", source)
        self.assertNotIn(
            'frappe.db.set_value("Door Cutting Order", source.name, "approved_plan"',
            source,
        )

    def test_revision_and_return_actions_are_separate_and_capability_driven(self) -> None:
        revision_source = REVISION_UX_PATH.read_text(encoding="utf-8")
        lifecycle_source = LIFECYCLE_UX_PATH.read_text(encoding="utf-8")
        self.assertIn('can(frm, "create_order_revision")', revision_source)
        self.assertIn('can(frm, "edit_order")', revision_source)
        self.assertIn("canOfferEditSession", revision_source)
        self.assertIn('__("تعديل")', revision_source)
        self.assertIn('__("حفظ")', revision_source)
        self.assertIn("commitEditSession", revision_source)
        self.assertIn("lockEditSession", revision_source)
        self.assertIn("after_save(frm)", revision_source)
        self.assertIn("__almdina_lock_after_save", revision_source)
        self.assertNotIn("frm.add_custom_button(CONFIRM_EDIT_LABEL", revision_source)
        self.assertIn("__almdina_edit_session", revision_source)
        self.assertIn("syncPrimaryAction", revision_source)
        self.assertIn("schedulePrimaryActionSync", revision_source)
        self.assertIn("setPrimaryActionMode", revision_source)
        self.assertIn('"edit", EDIT_LABEL', revision_source)
        self.assertIn('"save", SAVE_LABEL', revision_source)
        self.assertIn("editSessionRecalculated", revision_source)
        self.assertIn("markEditSessionRecalculated", revision_source)
        self.assertIn('=== "Draft"', revision_source)
        self.assertIn('(frm.doc.status || "Draft") !== "Draft"', revision_source)
        self.assertIn("installEditSessionAbandonGuard", revision_source)
        self.assertIn("form-unload", revision_source)
        self.assertIn("page-change", revision_source)
        self.assertIn("abandonStoredEditSession", revision_source)
        self.assertIn("hydrateEditSession", revision_source)
        self.assertIn("__almdina_edit_session_abandoned", revision_source)
        self.assertIn("markEditSessionSticky", revision_source)
        self.assertIn("restorePrimaryAfterPlanEngine", revision_source)
        self.assertIn("ensureLockedPrimaryAction", revision_source)
        self.assertIn("activateEditSessionQuietly", revision_source)
        self.assertIn("flushPendingCostPriceEdits", revision_source)
        self.assertIn("Price-only edits are persisted by the pricing APIs", revision_source)
        self.assertIn("disable_save()", revision_source)
        self.assertIn("No changes in document", revision_source)
        self.assertIn("order_revision_service.create_order_revision", revision_source)
        self.assertIn('LABELS.return_to_draft', lifecycle_source)
        self.assertIn("order_revision_service.return_order_to_draft", lifecycle_source)
        self.assertIn("removeLifecycleButtons(frm)", lifecycle_source)
        self.assertIn("إعادة نفس الطلب إلى المسودة", lifecycle_source)


if __name__ == "__main__":
    unittest.main()
