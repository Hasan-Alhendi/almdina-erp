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
PLAN_CONTROLS = ROOT / "public" / "js" / "door_cutting_order_plan_controls_ux.js"
APPROVAL_SERVICE = ROOT / "almdina_erp" / "services" / "drawing_approval_service.py"
ACTION_GUARD = ROOT / "public" / "js" / "door_cutting_order_action_permission_guard.js"
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
        self.assertIn("Capability.EDIT_OPTIMIZER_SETTINGS", service)
        self.assertIn("require_document_capability", service)
        self.assertIn("for update", service)
        self.assertIn("assert_order_editable", service)

    def test_recalculation_response_never_exposes_internal_costs(self) -> None:
        service = PLAN_PERMISSION_SERVICE.read_text(encoding="utf-8")
        self.assertIn("def _recalculation_result", service)
        for financial_field in (
            "mdf_cost_usd",
            "cutting_cost_usd",
            "edge_cost_usd",
            "total_cost_usd",
            "special_shape_cost_usd",
            "customer_quote_total_usd",
        ):
            with self.subTest(financial_field=financial_field):
                self.assertNotIn(financial_field, service)

    def test_algorithm_preview_is_capability_only_and_never_persists(self) -> None:
        service = PLAN_PERMISSION_SERVICE.read_text(encoding="utf-8")
        preview = service.split("def simulate_optimizer_plan", 1)[1].split(
            "\n__all__", 1
        )[0]

        self.assertIn('check_permission("read")', preview)
        self.assertIn("Capability.EDIT_OPTIMIZER_SETTINGS", preview)
        self.assertIn("frappe.copy_doc(stored)", preview)
        self.assertIn("_calculate_cutting_plan", preview)
        # Inspection only: no persistence, no stage gate, no lifecycle unlock.
        self.assertNotIn("save(", preview)
        self.assertNotIn("db_set", preview)
        self.assertNotIn("require_stage_operational_access", preview)
        self.assertNotIn("assert_order_editable", preview)
        self.assertNotIn("approved_plan =", preview)

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

    def test_browser_plan_actions_do_not_depend_on_full_order_editability(self) -> None:
        source = ACTION_GUARD.read_text(encoding="utf-8")
        controls = PLAN_CONTROLS.read_text(encoding="utf-8")

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
        self.assertNotIn("orderEditable", source)
        self.assertIn("planIsLocked", source)
        self.assertIn(
            "!locked && mayMutate && mayRecalculate && (!modeButton || mayEditOptimizer)",
            source,
        )
        self.assertIn("RECALCULATE_METHOD", controls)
        self.assertIn(
            '"almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order"',
            controls,
        )
        self.assertNotIn(
            '"almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.recalculate_order"',
            controls,
        )
        self.assertIn("__almdinaPlanCommandBound", controls)
        self.assertIn("scheduleSimplify", controls)
        self.assertIn("setTextIfChanged", controls)
        self.assertIn('.off("click")', controls)
        self.assertNotIn("frm.save", controls)
        self.assertIn("secureInvoicePrint", source)
        self.assertIn("AlmdinaCustomerInvoiceToolbarUX", source)
        self.assertIn("protectUnifiedPrintApi", source)
        self.assertIn("protectPlanPrintApis", source)
        self.assertIn("requestAnimationFrame", source)
        self.assertIn("MutationObserver(scheduleObserverApply)", source)

    def test_plan_approval_locks_and_rejects_stale_system_plan(self) -> None:
        service = APPROVAL_SERVICE.read_text(encoding="utf-8")
        controls = PLAN_CONTROLS.read_text(encoding="utf-8")

        self.assertIn("Capability.APPROVE_DXF", service)
        self.assertIn("for update", service)
        self.assertIn("_assert_reviewed_system_plan", service)
        self.assertIn("plan_needs_recalculation", service)
        self.assertNotIn("force_cutting_plan_recalculation", service)
        self.assertIn('"اعتماد خطة القص"', controls)
        self.assertIn('can(frm, "approve_dxf")', controls)
        self.assertIn("plan_needs_recalculation", controls)
        self.assertIn(
            '"almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf"',
            controls,
        )

    def test_dxf_upload_and_replacement_are_separate_server_permissions(self) -> None:
        service = DXF_SERVICE.read_text(encoding="utf-8")
        policy = DRAWING_POLICY.read_text(encoding="utf-8")

        self.assertIn("required_upload_capability", service)
        self.assertIn("Capability.UPLOAD_DXF", policy)
        self.assertIn("Capability.REPLACE_DXF", policy)
        self.assertIn("_attach_validated_dxf_file", service)

if __name__ == "__main__":
    unittest.main()
