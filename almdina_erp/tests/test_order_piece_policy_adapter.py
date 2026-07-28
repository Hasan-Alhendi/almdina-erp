from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "piece_policy.py"
ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_domain.py"
)
COSTING_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_costing.py"
)
PLAN_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_plan.py"
)
FAST_CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_fast.py"
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

    def test_domain_controller_adapts_rows_to_piece_policy(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DomainDoorCuttingOrder", source)
        self.assertIn("TextBoardDoorCuttingOrder", source)
        self.assertIn("evaluate_special_shape", source)
        self.assertIn("resolve_clipped_corner", source)
        self.assertIn("def _validate_special_shape_rows", source)
        self.assertIn("def _validate_clipped_corner", source)
        self.assertNotIn("math.isclose", source)

    def test_active_controller_composes_piece_costing_and_plan_layers(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_plan.PlanDoorCuttingOrder",
        )
        costing_source = COSTING_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "class CostingDoorCuttingOrder(DomainDoorCuttingOrder)",
            costing_source,
        )
        plan_source = PLAN_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "class PlanDoorCuttingOrder(CostingDoorCuttingOrder)",
            plan_source,
        )

    def test_legacy_fast_controller_remains_a_compatibility_base(self) -> None:
        source = FAST_CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class FastDoorCuttingOrder", source)
        self.assertIn("def _plan_metadata_fingerprint", source)
        self.assertNotEqual(FAST_CONTROLLER_PATH, ADAPTER_PATH)


if __name__ == "__main__":
    unittest.main()
