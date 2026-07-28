from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "cut_dimensions.py"
ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "cut_dimension_adapter.py"
)
PLAN_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "cut_dimension_plan_adapter.py"
)
SAVE_GATEWAY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "save_gateway.py"
)
EDGE_DOCTYPE_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "edge_banding_type"
    / "edge_banding_type.json"
)
EDGE_CONTROLLER_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "edge_banding_type"
    / "edge_banding_type.py"
)
DETAIL_DOCTYPE_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order_detail"
    / "door_cutting_order_detail.json"
)
UX_PATH = ROOT / "public" / "js" / "door_cutting_order_cut_dimensions_ux.js"
EDGE_UX_PATH = ROOT / "public" / "js" / "edge_banding_type_ux.js"
HOOKS_PATH = ROOT / "hooks.py"


class TestCutDimensionsArchitecture(unittest.TestCase):
    def test_domain_policy_has_no_framework_dependencies(self) -> None:
        source = DOMAIN_PATH.read_text(encoding="utf-8")
        self.assertIn("def calculate_cut_dimensions", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".infrastructure", source)
        self.assertNotIn(".services", source)

    def test_frappe_adapters_keep_framework_and_plan_concerns_separate(self) -> None:
        adapter = ADAPTER_PATH.read_text(encoding="utf-8")
        plan_adapter = PLAN_ADAPTER_PATH.read_text(encoding="utf-8")
        gateway = SAVE_GATEWAY_PATH.read_text(encoding="utf-8")

        self.assertIn("calculate_cut_dimensions", adapter)
        self.assertIn("def _resolve_thickness", adapter)
        self.assertIn("Select an Edge Type before choosing edge sides", adapter)
        self.assertIn("must have a thickness greater than zero", adapter)
        self.assertIn("FrappeOrderCutDimensionAdapter", gateway)
        self.assertIn("FrappeCutDimensionPlanAdapter", gateway)
        self.assertIn('data["final_width_cm"]', plan_adapter)
        self.assertIn('data["width_cm"]', plan_adapter)
        self.assertIn('payload["version"] = 2', plan_adapter)
        self.assertNotIn("frappe.get_all", plan_adapter)

    def test_doctypes_store_and_validate_thickness_and_cut_size(self) -> None:
        edge = json.loads(EDGE_DOCTYPE_PATH.read_text(encoding="utf-8"))
        detail = json.loads(DETAIL_DOCTYPE_PATH.read_text(encoding="utf-8"))
        edge_fields = {field["fieldname"]: field for field in edge["fields"]}
        detail_fields = {
            field["fieldname"]: field for field in detail["fields"]
        }
        edge_controller = EDGE_CONTROLLER_PATH.read_text(encoding="utf-8")

        self.assertEqual(edge_fields["thickness_mm"]["default"], "1")
        self.assertEqual(edge_fields["thickness_mm"]["reqd"], 1)
        self.assertIn("def _validate_thickness", edge_controller)
        self.assertIn("thickness_mm <= 0", edge_controller)
        for fieldname in (
            "edge_thickness_mm",
            "cut_width_cm",
            "cut_length_cm",
            "cut_size_label",
        ):
            self.assertEqual(detail_fields[fieldname]["read_only"], 1)

    def test_live_ux_is_loaded_after_table_stabilization(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]
        operator_index = scripts.index(
            "public/js/door_cutting_order_operator_ux.js"
        )
        performance_index = scripts.index(
            "public/js/door_cutting_order_table_performance_ux.js"
        )
        cut_index = scripts.index(
            "public/js/door_cutting_order_cut_dimensions_ux.js"
        )
        self.assertGreater(cut_index, operator_index)
        self.assertGreater(cut_index, performance_index)
        self.assertEqual(
            hooks["doctype_js"]["Edge Banding Type"],
            "public/js/edge_banding_type_ux.js",
        )

        source = UX_PATH.read_text(encoding="utf-8")
        edge_source = EDGE_UX_PATH.read_text(encoding="utf-8")
        self.assertIn("مقاس القص", source)
        self.assertIn("المدخل نهائي", source)
        self.assertIn("thickness_mm", source)
        self.assertIn("سماكة القشاط (مم)", edge_source)
        self.assertIn("طرفان متقابلان", edge_source)


if __name__ == "__main__":
    unittest.main()
