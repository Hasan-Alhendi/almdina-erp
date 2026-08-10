from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_PATH = ROOT / "almdina_erp" / "application" / "shop_floor" / "queries.py"
DRAWING_POLICY_PATH = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "drawing_action_policy.py"
)
APPROVAL_POLICY_PATH = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "drawing_approval_policy.py"
)
PRESENTER_PATH = (
    ROOT
    / "almdina_erp"
    / "presentation"
    / "shop_floor"
    / "presenters.py"
)
REPOSITORY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "shop_floor_query_repository.py"
)
QUERY_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_query_service.py"
DXF_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_dxf_service.py"
APPROVAL_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "drawing_approval_service.py"
LEGACY_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
HOOKS_PATH = ROOT / "hooks.py"


class TestShopFloorQueryArchitecture(unittest.TestCase):
    def test_application_and_presenters_do_not_import_frappe(self) -> None:
        for path in (
            APPLICATION_PATH,
            DRAWING_POLICY_PATH,
            APPROVAL_POLICY_PATH,
            PRESENTER_PATH,
        ):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn("import frappe", source)
                self.assertNotIn("from frappe", source)
                self.assertNotIn("import erpnext", source)

    def test_frappe_reads_live_only_in_infrastructure_adapter(self) -> None:
        repository_source = REPOSITORY_PATH.read_text(encoding="utf-8")
        application_source = APPLICATION_PATH.read_text(encoding="utf-8")
        self.assertIn("import frappe", repository_source)
        self.assertIn("class FrappeShopFloorQueryRepository", repository_source)
        self.assertIn("class ShopFloorQueryPort", application_source)
        self.assertIn("def session_identity", application_source)
        self.assertIn("def global_capabilities", application_source)

    def test_query_service_composes_application_repository_and_presenter(self) -> None:
        source = QUERY_SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn("application.shop_floor import queries", source)
        self.assertIn("FrappeShopFloorQueryRepository", source)
        self.assertIn("present_order_detail", source)
        self.assertIn("def get_shop_floor_context", source)
        self.assertNotIn("frappe.get_roles", source)

    def test_legacy_service_is_only_a_small_lazy_compatibility_facade(self) -> None:
        source = LEGACY_PATH.read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 160)
        self.assertNotIn("frappe.db", source)
        self.assertNotIn("frappe.get_all", source)
        self.assertNotIn("dco-sheet-card", source)
        self.assertIn("from importlib import import_module", source)
        self.assertIn("services.shop_floor_query_service", source)
        self.assertIn("services.shop_floor_dxf_service", source)
        self.assertIn("services.shop_floor_commands", source)
        self.assertIn("get_shop_floor_context", source)
        self.assertNotIn(
            "from almdina_erp.almdina_erp.services.shop_floor_commands import",
            source,
        )

    def test_hooks_route_legacy_reads_and_drawing_actions_to_focused_services(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        overrides = hooks["override_whitelisted_methods"]
        query_methods = (
            "get_shop_floor_context",
            "get_dispatch_options",
            "get_revert_targets",
            "get_my_inbox",
            "get_my_archive",
            "get_order_shop_floor_detail",
        )
        for method in query_methods:
            old = f"almdina_erp.almdina_erp.services.shop_floor_service.{method}"
            new = f"almdina_erp.almdina_erp.services.shop_floor_query_service.{method}"
            self.assertEqual(overrides.get(old), new)

        for method in (
            "mark_dxf_exported",
            "upload_production_dxf",
            "recalculate_drawing_plan",
        ):
            old = f"almdina_erp.almdina_erp.services.shop_floor_service.{method}"
            new = f"almdina_erp.almdina_erp.services.shop_floor_dxf_service.{method}"
            self.assertEqual(overrides.get(old), new)

        self.assertEqual(
            overrides.get(
                "almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf"
            ),
            "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf",
        )

    def test_drawing_services_delegate_policies_and_stay_focused(self) -> None:
        dxf_source = DXF_SERVICE_PATH.read_text(encoding="utf-8")
        action_policy_source = DRAWING_POLICY_PATH.read_text(encoding="utf-8")
        approval_source = APPROVAL_SERVICE_PATH.read_text(encoding="utf-8")
        approval_policy_source = APPROVAL_POLICY_PATH.read_text(encoding="utf-8")

        self.assertNotIn("get_my_inbox", dxf_source)
        self.assertNotIn("get_order_shop_floor_detail", dxf_source)
        self.assertNotIn("dco-cutting-plan", dxf_source)
        self.assertIn("validate_assigned_drawing_action", dxf_source)
        self.assertIn("require_document_capability", dxf_source)
        self.assertIn("def validate_assigned_drawing_action", action_policy_source)
        self.assertIn("not_assigned_designer", action_policy_source)

        self.assertIn("require_stage_operational_access", approval_source)
        self.assertIn("Capability.APPROVE_DXF", approval_source)
        self.assertIn("def validate_drawing_approval", approval_policy_source)
        self.assertNotIn("current_assignee", approval_policy_source)


if __name__ == "__main__":
    unittest.main()
