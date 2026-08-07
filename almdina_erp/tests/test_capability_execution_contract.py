from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
PLAN_PERMISSION_SERVICE = (
    ROOT / "almdina_erp" / "services" / "order_plan_permission_service.py"
)
ACTION_GUARD = ROOT / "public" / "js" / "door_cutting_order_action_permission_guard.js"
DXF_VISIBILITY = ROOT / "public" / "js" / "shop_floor_dxf_visibility_ux.js"
DXF_SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_dxf_service.py"
DRAWING_POLICY = (
    ROOT / "almdina_erp" / "application" / "security" / "drawing_action_policy.py"
)


class TestCapabilityExecutionContract(unittest.TestCase):
    def test_catalog_contains_the_full_assignable_surface(self) -> None:
        declared = {
            value
            for name, value in vars(Capability).items()
            if name.isupper() and isinstance(value, str)
        }
        self.assertEqual(set(CAPABILITY_CATALOG), declared)
        self.assertIn(Capability.ASSIGN_USER_ROLES, CAPABILITY_CATALOG)
        for retired in (
            "assign_workforce_profile",
            "manage_users",
            "manage_factory_settings",
        ):
            self.assertNotIn(retired, CAPABILITY_CATALOG)

    def test_recalculation_is_overridden_by_explicit_capability_service(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        service = PLAN_PERMISSION_SERVICE.read_text(encoding="utf-8")

        self.assertIn(
            '"almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.recalculate_order"',
            hooks,
        )
        self.assertIn(
            '"almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order"',
            hooks,
        )
        self.assertIn("Capability.RECALCULATE_PLAN", service)
        self.assertIn("require_document_capability", service)
        self.assertIn("for update", service)
        self.assertIn("assert_order_editable", service)

    def test_optimizer_and_special_drawings_are_guarded_on_every_save(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        service = PLAN_PERMISSION_SERVICE.read_text(encoding="utf-8")

        self.assertIn('"Door Cutting Order": {', hooks)
        self.assertIn('"before_validate":', hooks)
        self.assertIn(
            '"almdina_erp.almdina_erp.services.order_plan_permission_service.enforce_plan_and_drawing_permissions"',
            hooks,
        )
        self.assertIn("Capability.EDIT_OPTIMIZER_SETTINGS", service)
        self.assertIn("Capability.EDIT_SPECIAL_DRAWING", service)
        self.assertIn("get_doc_before_save", service)
        self.assertIn('raw_status == "Documented"', service)

    def test_browser_actions_follow_the_same_capabilities(self) -> None:
        source = ACTION_GUARD.read_text(encoding="utf-8")

        for capability in (
            "recalculate_plan",
            "edit_optimizer_settings",
            "edit_special_drawing",
            "view_drawing_workspace",
            "print_measurements",
            "print_customer_invoice",
            "print_cutting_plan",
        ):
            with self.subTest(capability=capability):
                self.assertIn(f'"{capability}"', source)
        self.assertIn("orderEditable", source)
        self.assertIn("secureInvoicePrint", source)
        self.assertIn("AlmdinaCustomerInvoiceToolbarUX", source)
        self.assertIn("protectUnifiedPrintApi", source)
        self.assertIn("protectPlanPrintApis", source)
        self.assertIn("requestAnimationFrame", source)
        self.assertIn("MutationObserver(scheduleObserverApply)", source)

    def test_dxf_upload_and_replacement_are_separate_server_permissions(self) -> None:
        service = DXF_SERVICE.read_text(encoding="utf-8")
        policy = DRAWING_POLICY.read_text(encoding="utf-8")

        self.assertIn("required_upload_capability", service)
        self.assertIn("Capability.UPLOAD_DXF", policy)
        self.assertIn("Capability.REPLACE_DXF", policy)
        self.assertIn("_validate_and_attach_dxf_file", service)

    def test_shop_floor_dxf_link_uses_dxf_permissions_not_plan_permission(self) -> None:
        source = DXF_VISIBILITY.read_text(encoding="utf-8")
        self.assertIn('can("view_drawing_workspace")', source)
        self.assertIn('can("export_dxf")', source)
        self.assertNotIn('can("view_cutting_plan")', source)


if __name__ == "__main__":
    unittest.main()
