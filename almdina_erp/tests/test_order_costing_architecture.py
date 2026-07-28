from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "costing.py"
CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_costing.py"
)
PLAN_CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_plan.py"
)
HOOKS_PATH = ROOT / "hooks.py"


class TestOrderCostingArchitecture(unittest.TestCase):
    def test_costing_domain_is_framework_independent(self) -> None:
        source = DOMAIN_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".services", source)
        self.assertNotIn("DocType", source)

    def test_costing_controller_delegates_all_costing_decisions(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        for token in (
            "calculate_piece_costs",
            "calculate_order_costs",
            "calculate_waste",
            "calculate_special_pricing",
        ):
            self.assertIn(token, source)
        self.assertNotIn("width_cm * length_cm", source)
        self.assertNotIn("edge_meters * edge_rate", source)
        self.assertNotIn("board_and_cutting_cost * area_share", source)

    def test_active_controller_composes_plan_and_costing_layers(self) -> None:
        source = HOOKS_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "door_cutting_order_plan.PlanDoorCuttingOrder",
            source,
        )
        plan_source = PLAN_CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "class PlanDoorCuttingOrder(CostingDoorCuttingOrder)",
            plan_source,
        )

    def test_costing_controller_preserves_compatibility_inheritance(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class CostingDoorCuttingOrder(DomainDoorCuttingOrder)", source)
        self.assertIn("super()._calculate_cutting_plan", source)
        self.assertIn("self._refresh_costs_from_plan", source)


if __name__ == "__main__":
    unittest.main()
