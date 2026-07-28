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
PROFILE_REPOSITORY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "edge_profile_repository.py"
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
        self.assertIn("edge_long_type", source)
        self.assertIn("edge_width_type", source)
        self.assertIn("edge_long_meters", source)
        self.assertIn("edge_width_meters", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".services", source)
        self.assertNotIn("DocType", source)

    def test_active_costing_adapter_delegates_formulas_and_reuses_profiles(self) -> None:
        source = ACTIVE_ADAPTER_PATH.read_text(encoding="utf-8")
        repository = PROFILE_REPOSITORY_PATH.read_text(encoding="utf-8")
        for token in (
            "calculate_piece_costs",
            "calculate_order_costs",
            "calculate_waste",
            "calculate_special_pricing",
        ):
            self.assertIn(token, source)
        self.assertIn("FrappeEdgeProfileRepository", source)
        self.assertIn("self.profiles.rate_map()", source)
        self.assertIn("row.edge_long_cost_usd", source)
        self.assertIn("row.edge_width_cost_usd", source)
        self.assertNotIn("width_cm * length_cm", source)
        self.assertNotIn("edge_meters * edge_rate", source)
        self.assertNotIn("board_and_cutting_cost * area_share", source)
        self.assertIn("rate_usd_per_meter", repository)
        self.assertIn("_order_edge_profiles_loaded", repository)

    def test_active_controller_contains_no_costing_formulas(self) -> None:
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(DoorCuttingOrder)", source)
        self.assertIn("from .door_cutting_order import DoorCuttingOrder", source)
        self.assertNotIn("frappe.model.document import Document", source)
        self.assertNotIn("calculate_piece_costs", source)
        self.assertNotIn("calculate_order_costs", source)
        self.assertNotIn("calculate_special_pricing", source)
        self.assertNotIn("mdf_cost_usd", source)

    def test_hooks_activate_the_thin_override_controller(self) -> None:
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
