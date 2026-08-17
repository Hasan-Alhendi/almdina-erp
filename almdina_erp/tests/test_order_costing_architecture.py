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
PLAN_SCHEMA_PATH = (
    ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.json"
)
PLAN_COMMAND_CONTEXT_PATH = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cutting_plan_command_context.py"
)
PLAN_COST_WORKSPACE_PATH = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cutting_plan_costing_workspace.py"
)
PLAN_COST_COMMAND_PATH = (
    ROOT / "almdina_erp" / "services" / "cutting_plan_cost_command_service.py"
)
PLAN_COMMAND_PATH = ROOT / "almdina_erp" / "services" / "cutting_plan_command_service.py"
COST_PERMISSION_PATH = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
COST_DOCUMENT_PATH = ROOT / "almdina_erp" / "services" / "cost_document_service.py"
HOOKS_PATH = ROOT / "hooks.py"


class TestOrderCostingArchitecture(unittest.TestCase):
    def test_costing_domain_is_framework_independent(self) -> None:
        source = DOMAIN_PATH.read_text(encoding="utf-8")
        for token in (
            "edge_long_right_type",
            "edge_long_left_type",
            "edge_width_top_type",
            "edge_width_bottom_type",
            "edge_long_right_meters",
            "edge_width_bottom_cost_usd",
        ):
            self.assertIn(token, source)
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
        for fieldname in (
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
        ):
            self.assertIn(fieldname, source)
        self.assertIn("row.edge_long_cost_usd", source)
        self.assertIn("row.edge_width_cost_usd", source)
        self.assertNotIn("width_cm * length_cm", source)
        self.assertNotIn("edge_meters * edge_rate", source)
        self.assertNotIn("board_and_cutting_cost * area_share", source)
        self.assertIn("rate_usd_per_meter", repository)
        self.assertIn("_order_edge_profiles_loaded", repository)

    def test_a3_cutting_plan_is_the_canonical_plan_cost_owner(self) -> None:
        schema = PLAN_SCHEMA_PATH.read_text(encoding="utf-8")
        context = PLAN_COMMAND_CONTEXT_PATH.read_text(encoding="utf-8")
        workspace = PLAN_COST_WORKSPACE_PATH.read_text(encoding="utf-8")
        command = PLAN_COST_COMMAND_PATH.read_text(encoding="utf-8")

        self.assertIn('"fieldname":"cost_snapshot_version"', schema)
        self.assertIn('"label":"Plan Cost Snapshot"', schema)
        self.assertNotIn('"label":"Legacy Cost Snapshot"', schema)
        self.assertIn("Capability.EDIT_COST_SETTINGS", context)
        self.assertIn("COST_SNAPSHOT_VERSION = 1", workspace)
        self.assertIn("calculate_order_costs", workspace)
        self.assertIn("initial_plan_cost_values", workspace)
        self.assertIn("initialize_draft_plan_cost_snapshot", workspace)
        self.assertIn("project_plan_costs_to_order", workspace)
        self.assertIn("FrappeCuttingPlanCommandRepository", command)
        self.assertIn("Capability.EDIT_COST_SETTINGS", command)
        self.assertIn("apply_plan_costs(plan)", command)
        self.assertIn("repository.save_document(plan)", command)
        self.assertNotIn("order.save(", command)
        self.assertNotIn("ignore_permissions", command)
        self.assertNotIn("plan_needs_recalculation =", command)
        self.assertNotIn("snapshot_json =", command)
        self.assertNotIn("input_fingerprint =", command)

    def test_focused_cost_settings_no_longer_trigger_geometry_recalculation(self) -> None:
        source = COST_PERMISSION_PATH.read_text(encoding="utf-8")
        focused = source.split("def update_order_cost_settings", 1)[1].split(
            "\n\n@frappe.whitelist()\ndef approve_special_piece_price", 1
        )[0]

        self.assertIn("update_plan_cost_settings", focused)
        self.assertIn("Capability.EDIT_COST_SETTINGS", focused)
        self.assertIn("_require_cost_visibility(order)", focused)
        self.assertNotIn("force_cutting_plan_recalculation", focused)
        self.assertNotIn("order.save(", focused)
        self.assertNotIn("ignore_permissions", focused)
        self.assertNotIn("plan_needs_recalculation", focused)

    def test_geometry_refreshes_plan_cost_before_canonical_plan_save(self) -> None:
        source = PLAN_COMMAND_PATH.read_text(encoding="utf-8")
        system = source.split("def recalculate_system_plan", 1)[1].split(
            "\n\n@frappe.whitelist()\ndef recalculate_order_plan", 1
        )[0]
        dxf = source.split("def save_uploaded_dxf_plan", 1)[1].split(
            "\n\ndef mirror_uploaded_dxf_projection", 1
        )[0]

        for segment in (system, dxf):
            self.assertIn("initialize_draft_plan_cost_snapshot(order, plan)", segment)
            self.assertIn("apply_plan_costs(plan", segment)
            self.assertLess(segment.index("apply_plan_costs(plan"), segment.index("repository.save_document(plan)"))

    def test_approval_never_pulls_cost_back_from_dco(self) -> None:
        source = PLAN_COMMAND_PATH.read_text(encoding="utf-8")
        approval = source.split("def approve_order_plan", 1)[1].split(
            "\n\ndef save_system_plan_settings", 1
        )[0]

        self.assertNotIn("_copy_compatibility_costs_to_plan", source)
        self.assertIn("cost_snapshot_version", source)
        self.assertIn("COST_SNAPSHOT_VERSION", source)
        self.assertNotIn("apply_plan_costs", approval)
        self.assertNotIn("board_rate_usd =", approval)
        self.assertNotIn("cutting_cost_per_board_usd =", approval)
        self.assertIn("project_plan_costs_to_order(order, plan)", approval)

    def test_cost_reads_and_financial_documents_prefer_plan_snapshot(self) -> None:
        cost_service = COST_PERMISSION_PATH.read_text(encoding="utf-8")
        document_service = COST_DOCUMENT_PATH.read_text(encoding="utf-8")
        workspace = PLAN_COST_WORKSPACE_PATH.read_text(encoding="utf-8")

        self.assertIn("overlay_authoritative_costs(order, order_snapshot)", cost_service)
        self.assertIn("overlay_authoritative_costs(", document_service)
        self.assertIn("def current_cost_plan", workspace)
        self.assertIn("def authoritative_cost_values", workspace)
        self.assertIn("def overlay_authoritative_costs", workspace)
        self.assertIn("update_modified=False", workspace)
        self.assertNotIn("save(ignore_permissions=True)", document_service)

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
