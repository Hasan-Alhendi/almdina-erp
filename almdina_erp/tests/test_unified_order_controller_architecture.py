from __future__ import annotations

import ast
import runpy
import unittest
from pathlib import Path

try:
    from frappe.model.base_document import get_controller
except ImportError:  # Static checks intentionally run without Frappe installed.
    get_controller = None


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
)
SAVE_USE_CASE_PATH = (
    ROOT / "almdina_erp" / "application" / "orders" / "process_order_save.py"
)
ORDER_ADAPTER_DIR = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders"
)
HOOKS_PATH = ROOT / "hooks.py"


class TestUnifiedOrderControllerArchitecture(unittest.TestCase):
    def test_active_controller_subclasses_canonical_doctype_controller(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        controller = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "DoorCuttingOrderController"
        )

        self.assertEqual(
            [ast.unparse(base) for base in controller.bases],
            ["DoorCuttingOrder"],
        )
        self.assertIn("from .door_cutting_order import DoorCuttingOrder", source)
        self.assertIn("process_order_save(self._gateway())", source)
        self.assertIn("invalidate_stale_draft_plans(self)", source)
        self.assertNotIn("frappe.model.document import Document", source)
        self.assertNotIn("PlanDoorCuttingOrder", source)
        self.assertNotIn("CostingDoorCuttingOrder", source)
        self.assertNotIn("DomainDoorCuttingOrder", source)
        self.assertNotIn("FastDoorCuttingOrder", source)
        self.assertLess(len(source.splitlines()), 45)

    def test_hooks_activate_only_the_thin_override_controller(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_controller.DoorCuttingOrderController",
        )

    @unittest.skipIf(
        get_controller is None,
        "Frappe is not installed in the static-check environment.",
    )
    def test_frappe_accepts_the_override_subclass_contract(self) -> None:
        from almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order import (
            DoorCuttingOrder,
        )

        active_controller = get_controller("Door Cutting Order")

        self.assertTrue(issubclass(active_controller, DoorCuttingOrder))
        self.assertEqual(active_controller.__name__, "DoorCuttingOrderController")

    def test_order_save_use_case_is_framework_independent(self) -> None:
        source = SAVE_USE_CASE_PATH.read_text(encoding="utf-8")
        self.assertIn("class OrderSaveGateway(Protocol)", source)
        self.assertIn("def process_order_save", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn(".services", source)
        self.assertNotIn(".infrastructure", source)
        self.assertNotIn("plan_input_fingerprint", source)
        self.assertNotIn("calculate_cutting_plan", source)

    def test_frappe_order_adapters_are_split_by_responsibility(self) -> None:
        expected = {
            "document_access.py",
            "piece_policy_adapter.py",
            "edge_profile_repository.py",
            "cut_dimension_adapter.py",
            "costing_adapter.py",
            "plan_adapter.py",
            "cut_dimension_plan_adapter.py",
            "save_gateway.py",
        }
        existing = {path.name for path in ORDER_ADAPTER_DIR.glob("*.py")}
        self.assertTrue(expected.issubset(existing))

        gateway = (ORDER_ADAPTER_DIR / "save_gateway.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FrappeOrderDocumentAccess", gateway)
        self.assertIn("FrappeOrderPiecePolicyAdapter", gateway)
        self.assertIn("FrappeEdgeProfileRepository", gateway)
        self.assertIn("FrappeOrderCutDimensionAdapter", gateway)
        self.assertIn("FrappeOrderCostingAdapter", gateway)
        self.assertNotIn("FrappeCutDimensionPlanAdapter", gateway)
        self.assertNotIn("sanitize_plan_snapshot_json", gateway)
        self.assertNotIn("domain.orders.costing", gateway)
        self.assertNotIn("domain.orders.cut_dimensions", gateway)
        self.assertNotIn("optimize_order_plan", gateway)
        self.assertNotIn("frappe.db", gateway)


if __name__ == "__main__":
    unittest.main()
