from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_DIR = ROOT / "almdina_erp" / "application" / "cutting"
ENGINE_ADAPTER_PATH = (
    ROOT / "almdina_erp" / "infrastructure" / "cutting" / "domain_engine.py"
)
PLAN_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "plan_adapter.py"
)
CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
)
SERVICES = ROOT / "almdina_erp" / "services"
SNAPSHOT_SERVICE_PATH = SERVICES / "cutting_plan_snapshot_service.py"
COMPATIBILITY_SERVICE_PATH = SERVICES / "cutting_plan_service.py"
DRAWING_APPROVAL_PATH = SERVICES / "drawing_approval_service.py"
HOOKS_PATH = ROOT / "hooks.py"


class TestCuttingPlanArchitecture(unittest.TestCase):
    def test_application_cutting_layer_is_framework_and_service_independent(self) -> None:
        for path in sorted(APPLICATION_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("import frappe", source)
                self.assertNotIn("from frappe", source)
                self.assertNotIn("import erpnext", source)
                self.assertNotIn(".services", source)
                self.assertNotIn(".infrastructure", source)

    def test_engine_adapter_points_to_the_pure_cutting_domain(self) -> None:
        source = ENGINE_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("domain.cutting", source)
        self.assertNotIn("services.advanced_cutting_optimizer", source)
        self.assertNotIn("services.cutting_engine", source)
        self.assertIn("class DomainCuttingEngineAdapter", source)
        self.assertIn("def expand_pieces", source)
        self.assertIn("def optimize", source)
        self.assertIn("def validate", source)

    def test_active_plan_adapter_delegates_orchestration(self) -> None:
        source = PLAN_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("class FrappeOrderPlanAdapter", source)
        self.assertIn("optimize_order_plan", source)
        self.assertIn("decide_plan_reuse", source)
        self.assertIn("refresh_plan_metadata", source)
        self.assertIn("plan_invalidation_state", source)
        self.assertIn("domain_cutting_engine", source)
        self.assertNotIn("advanced_cutting_optimizer", source)
        self.assertNotIn("services.cutting_engine", source)
        self.assertNotIn("validate_plan(", source)
        self.assertNotIn("expand_piece_groups(", source)
        self.assertNotIn('"industrial_metrics": metrics', source)
        self.assertNotIn('"special_shape_raw_summary":', source)

    def test_snapshot_persistence_has_one_focused_owner(self) -> None:
        snapshot = SNAPSHOT_SERVICE_PATH.read_text(encoding="utf-8")
        facade = COMPATIBILITY_SERVICE_PATH.read_text(encoding="utf-8")
        drawing = DRAWING_APPROVAL_PATH.read_text(encoding="utf-8")

        for symbol in (
            "def create_plan_from_order",
            "def approve_plan",
            "def lock_order_for_production",
            'frappe.new_doc("Cutting Plan")',
            "plan.insert(ignore_permissions=True)",
            '"status": "Approved"',
        ):
            self.assertIn(symbol, snapshot)

        self.assertIn("Backward-compatible Cutting Plan lifecycle facade", facade)
        self.assertIn("cutting_plan_snapshot_service as _snapshot", facade)
        self.assertIn("def create_plan_from_order", facade)
        self.assertIn("return _snapshot.create_plan_from_order", facade)
        self.assertIn("return _snapshot.approve_plan", facade)
        self.assertIn("return _snapshot.lock_order_for_production", facade)
        self.assertNotIn('frappe.new_doc("Cutting Plan")', facade)
        self.assertNotIn("frappe.db.set_value", facade)
        self.assertNotIn("plan.insert(ignore_permissions=True)", facade)

        self.assertIn("services.cutting_plan_snapshot_service", drawing)
        self.assertIn("lock_order_for_production(", drawing)
        self.assertNotIn("services.cutting_plan_service import", drawing)
        self.assertNotIn("_lock_order_for_production(", drawing)

    def test_active_controller_contains_no_plan_algorithm(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(DoorCuttingOrder)", source)
        self.assertIn("from .door_cutting_order import DoorCuttingOrder", source)
        self.assertNotIn("frappe.model.document import Document", source)
        self.assertNotIn("optimize_order_plan", source)
        self.assertNotIn("decide_plan_reuse", source)
        self.assertNotIn("refresh_plan_metadata", source)

    def test_hooks_activate_application_backed_override_controller(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_controller.DoorCuttingOrderController",
        )


if __name__ == "__main__":
    unittest.main()
