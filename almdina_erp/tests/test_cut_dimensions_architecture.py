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
PROFILE_REPOSITORY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "edge_profile_repository.py"
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
CUT_UX_PATH = ROOT / "public" / "js" / "door_cutting_order_cut_dimensions_ux.js"
SIDE_EDGE_UX_PATH = ROOT / "public" / "js" / "door_cutting_order_multi_edge_ux.js"
DOCUMENT_UX_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_multi_edge_documents_ux.js"
)
EDGE_UX_PATH = ROOT / "public" / "js" / "edge_banding_type_ux.js"
HOOKS_PATH = ROOT / "hooks.py"


class TestCutDimensionsArchitecture(unittest.TestCase):
    def test_domain_policy_has_no_framework_dependencies(self) -> None:
        source = DOMAIN_PATH.read_text(encoding="utf-8")
        self.assertIn("def calculate_cut_dimensions", source)
        for token in (
            "edge_long_right_thickness_mm",
            "edge_long_left_thickness_mm",
            "edge_width_top_thickness_mm",
            "edge_width_bottom_thickness_mm",
        ):
            self.assertIn(token, source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".infrastructure", source)
        self.assertNotIn(".services", source)

    def test_frappe_adapters_share_one_side_profile_repository(self) -> None:
        adapter = ADAPTER_PATH.read_text(encoding="utf-8")
        repository = PROFILE_REPOSITORY_PATH.read_text(encoding="utf-8")
        plan_adapter = PLAN_ADAPTER_PATH.read_text(encoding="utf-8")
        gateway = SAVE_GATEWAY_PATH.read_text(encoding="utf-8")

        self.assertIn("FrappeEdgeProfileRepository", adapter)
        self.assertIn("effective_profiles(row, index)", adapter)
        self.assertIn("_clear_inactive_overrides", adapter)
        self.assertNotIn("frappe.get_all", adapter)

        self.assertIn("class FrappeEdgeProfileRepository", repository)
        self.assertIn("EdgeSide = Literal", repository)
        self.assertIn("SIDE_CONFIG", repository)
        self.assertIn("profile_for_side", repository)
        self.assertIn('"thickness_mm"', repository)
        self.assertIn('"rate_usd_per_meter"', repository)
        self.assertIn("_order_edge_profiles_loaded", repository)

        self.assertIn("FrappeEdgeProfileRepository(document)", gateway)
        self.assertIn("self.edge_profiles", gateway)
        self.assertIn("FrappeOrderCutDimensionAdapter", gateway)
        self.assertIn("FrappeOrderCostingAdapter", gateway)

        self.assertIn('data["final_width_cm"]', plan_adapter)
        self.assertIn('"edge_long_right_type_override"', plan_adapter)
        self.assertIn('payload["version"] = 4', plan_adapter)
        self.assertIn('"per_side_edge_profile"', plan_adapter)
        self.assertNotIn("frappe.get_all", plan_adapter)

    def test_doctype_stores_only_optional_side_overrides_as_inputs(self) -> None:
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

        override_fields = (
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
        )
        for fieldname in override_fields:
            self.assertEqual(detail_fields[fieldname]["fieldtype"], "Link")
            self.assertEqual(detail_fields[fieldname]["options"], "Edge Banding Type")
            self.assertEqual(detail_fields[fieldname]["hidden"], 1)
            self.assertNotEqual(detail_fields[fieldname].get("read_only"), 1)

        for fieldname in ("edge_long_type", "edge_width_type"):
            self.assertEqual(detail_fields[fieldname]["hidden"], 1)
            self.assertEqual(detail_fields[fieldname]["read_only"], 1)

        for fieldname in (
            "edge_long_thickness_mm",
            "edge_width_thickness_mm",
            "edge_long_meters",
            "edge_width_meters",
            "edge_long_rate_usd",
            "edge_width_rate_usd",
            "edge_long_cost_usd",
            "edge_width_cost_usd",
            "edge_cost_usd",
            "cut_width_cm",
            "cut_length_cm",
            "cut_size_label",
        ):
            self.assertEqual(detail_fields[fieldname]["read_only"], 1)

    def test_live_ux_hides_profile_column_and_uses_side_indicators(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]
        performance_index = scripts.index(
            "public/js/door_cutting_order_table_performance_ux.js"
        )
        side_edge_index = scripts.index(
            "public/js/door_cutting_order_multi_edge_ux.js"
        )
        cut_index = scripts.index(
            "public/js/door_cutting_order_cut_dimensions_ux.js"
        )
        invoice_index = scripts.index(
            "public/js/door_cutting_order_cost_invoice_ux.js"
        )
        documents_index = scripts.index(
            "public/js/door_cutting_order_multi_edge_documents_ux.js"
        )

        self.assertGreater(side_edge_index, performance_index)
        self.assertGreater(cut_index, side_edge_index)
        self.assertGreater(documents_index, invoice_index)
        self.assertEqual(
            hooks["doctype_js"]["Edge Banding Type"],
            "public/js/edge_banding_type_ux.js",
        )

        side_source = SIDE_EDGE_UX_PATH.read_text(encoding="utf-8")
        cut_source = CUT_UX_PATH.read_text(encoding="utf-8")
        document_source = DOCUMENT_UX_PATH.read_text(encoding="utf-8")
        edge_source = EDGE_UX_PATH.read_text(encoding="utf-8")

        self.assertIn("dco-side-profile-trigger", side_source)
        self.assertIn("تخصيص نوع القشاط لهذا الضلع", side_source)
        self.assertIn("كل ضلع يأخذ الافتراضي", side_source)
        self.assertIn("استخدام الافتراضي", side_source)
        self.assertIn("th.dco-col-edge-type", side_source)
        self.assertIn("display:none!important", side_source)
        for fieldname in (
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
        ):
            self.assertIn(fieldname, side_source)

        self.assertIn("مقاس القص", cut_source)
        self.assertIn("الخصم حسب سماكة كل ضلع", cut_source)
        self.assertIn("قشاط الأطراف", document_source)
        self.assertIn("يتضمن أطرافًا مخصصة", document_source)
        self.assertIn("سطر مستقل لكل نوع قشاط", document_source)
        self.assertIn("سماكة القشاط (مم)", edge_source)


if __name__ == "__main__":
    unittest.main()
