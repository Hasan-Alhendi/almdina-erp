from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "piece_policy.py"
ACTIVE_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "piece_policy_adapter.py"
)
CONTROLLER_DIR = ROOT / "almdina_erp" / "doctype" / "door_cutting_order"
CONTROLLER_PATH = CONTROLLER_DIR / "door_cutting_order_controller.py"
RETIRED_CONTROLLER_PATHS = (
    CONTROLLER_DIR / "door_cutting_order_fast.py",
    CONTROLLER_DIR / "door_cutting_order_text_board.py",
    CONTROLLER_DIR / "door_cutting_order_domain.py",
    CONTROLLER_DIR / "door_cutting_order_costing.py",
    CONTROLLER_DIR / "door_cutting_order_plan.py",
)
HOOKS_PATH = ROOT / "hooks.py"


class TestOrderPiecePolicyAdapter(unittest.TestCase):
    def test_piece_policy_domain_has_no_framework_dependencies(self) -> None:
        source = DOMAIN_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".services", source)
        self.assertNotIn(".doctype", source)
        self.assertIn("class SpecialShapeDecision", source)

    def test_active_frappe_adapter_delegates_piece_decisions(self) -> None:
        source = ACTIVE_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("class FrappeOrderPiecePolicyAdapter", source)
        self.assertIn("evaluate_special_shape", source)
        self.assertIn("resolve_clipped_corner", source)
        self.assertIn("def validate_rows", source)
        self.assertIn("def _validate_clipped_corner", source)
        self.assertNotIn("math.isclose", source)

    def test_active_special_price_policy_uses_configurable_capabilities(self) -> None:
        source = ACTIVE_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("document_has_capability", source)
        self.assertIn("Capability.APPROVE_SPECIAL_PRICE", source)
        self.assertIn("Capability.EDIT_SPECIAL_PRICE", source)
        self.assertNotIn("has_special_price_approval_role", source)
        self.assertNotIn("Accounts Management", source)
        self.assertNotIn("System Manager", source)

    def test_active_controller_is_framework_compatible_and_thin(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_controller.DoorCuttingOrderController",
        )
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(DoorCuttingOrder)", source)
        self.assertIn("from .door_cutting_order import DoorCuttingOrder", source)
        self.assertIn("FrappeDoorCuttingOrderSaveGateway", source)
        self.assertNotIn("frappe.model.document import Document", source)

    def test_retired_alternate_controller_chain_is_absent(self) -> None:
        for path in RETIRED_CONTROLLER_PATHS:
            with self.subTest(path=path.name):
                self.assertFalse(path.exists(), path)


if __name__ == "__main__":
    unittest.main()
