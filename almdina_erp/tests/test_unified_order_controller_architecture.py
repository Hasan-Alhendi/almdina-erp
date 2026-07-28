from __future__ import annotations

import runpy
import unittest
from pathlib import Path


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
    def test_active_controller_inherits_directly_from_frappe_document(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(Document)", source)
        self.assertIn("process_order_save(self._gateway())", source)
        self.assertNotIn("PlanDoorCuttingOrder", source)
        self.assertNotIn("CostingDoorCuttingOrder", source)
        self.assertNotIn("DomainDoorCuttingOrder", source)
        self.assertNotIn("FastDoorCuttingOrder", source)
        self.assertLess(len(source.splitlines()), 45)

    def test_hooks_activate_only_the_direct_controller(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_controller.DoorCuttingOrderController",
        )

    def test_order_save_use_case_is_framework_independent(self) -> None:
        source = SAVE_USE_CASE_PATH.read_text(encoding="utf-8")
        self.assertIn("class OrderSaveGateway(Protocol)", source)
        self.assertIn("def process_order_save", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn(".services", source)
        self.assertNotIn(".infrastructure", source)

    def test_frappe_order_adapters_are_split_by_responsibility(self) -> None:
        expected = {
            "document_access.py",
            "piece_policy_adapter.py",
            "costing_adapter.py",
            "plan_adapter.py",
            "save_gateway.py",
        }
        existing = {path.name for path in ORDER_ADAPTER_DIR.glob("*.py")}
        self.assertTrue(expected.issubset(existing))

        gateway = (ORDER_ADAPTER_DIR / "save_gateway.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FrappeOrderDocumentAccess", gateway)
        self.assertIn("FrappeOrderPiecePolicyAdapter", gateway)
        self.assertIn("FrappeOrderCostingAdapter", gateway)
        self.assertIn("FrappeOrderPlanAdapter", gateway)
        self.assertNotIn("domain.orders.costing", gateway)
        self.assertNotIn("optimize_order_plan", gateway)
        self.assertNotIn("frappe.db", gateway)


if __name__ == "__main__":
    unittest.main()
