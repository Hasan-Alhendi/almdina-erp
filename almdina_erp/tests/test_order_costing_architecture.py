from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "costing.py"
ACTIVE_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "costing_adapter.py"
)
CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
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

    def test_active_costing_adapter_delegates_all_decisions(self) -> None:
        source = ACTIVE_ADAPTER_PATH.read_text(encoding="utf-8")
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

    def test_active_controller_contains_no_costing_formulas(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(Document)", source)
        self.assertNotIn("calculate_piece_costs", source)
        self.assertNotIn("calculate_order_costs", source)
        self.assertNotIn("calculate_special_pricing", source)
        self.assertNotIn("mdf_cost_usd", source)

    def test_hooks_activate_the_direct_controller(self) -> None:
        source = HOOKS_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "door_cutting_order_controller.DoorCuttingOrderController",
            source,
        )
        self.assertNotIn(
            'door_cutting_order_plan.PlanDoorCuttingOrder",\n}',
            source,
        )


if __name__ == "__main__":
    unittest.main()
