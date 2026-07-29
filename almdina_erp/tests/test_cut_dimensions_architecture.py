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
EDGE_CONTROLS_UX_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_edge_profile_controls_ux.js"
)
DOCUMENT_PRINT_PRESENTER_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
)
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

    def test_live_ux_aligns_edge_controls_and_uses_one_print_presenter(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]
        performance_index = scripts.index(
            "public/js/door_cutting_order_table_performance_ux.js"
        )
        side_edge_index = scripts.index(
            "public/js/door_cutting_order_multi_edge_ux.js"
        )
        controls_index = scripts.index(
            "public/js/door_cutting_order_edge_profile_controls_ux.js"
        )
        cut_index = scripts.index(
            "public/js/door_cutting_order_cut_dimensions_ux.js"
        )
        invoice_index = scripts.index(
            "public/js/door_cutting_order_cost_invoice_ux.js"
        )
        print_index = scripts.index(
            "public/js/door_cutting_order_document_print_presenter.js"
        )
        documents_index = scripts.index(
            "public/js/door_cutting_order_multi_edge_documents_ux.js"
        )

        self.assertGreater(side_edge_index, performance_index)
        self.assertGreater(controls_index, side_edge_index)
        self.assertGreater(cut_index, controls_index)
        self.assertGreater(print_index, invoice_index)
        self.assertGreater(documents_index, print_index)
        self.assertNotIn(
            "public/js/door_cutting_order_measurement_print_presenter.js",
            scripts,
        )
        self.assertNotIn(
            "public/js/door_cutting_order_compact_invoice_print_presenter.js",
            scripts,
        )
        self.assertEqual(
            hooks["doctype_js"]["Edge Banding Type"],
            "public/js/edge_banding_type_ux.js",
        )

        side_source = SIDE_EDGE_UX_PATH.read_text(encoding="utf-8")
        controls_source = EDGE_CONTROLS_UX_PATH.read_text(encoding="utf-8")
        print_source = DOCUMENT_PRINT_PRESENTER_PATH.read_text(encoding="utf-8")
        cut_source = CUT_UX_PATH.read_text(encoding="utf-8")
        document_source = DOCUMENT_UX_PATH.read_text(encoding="utf-8")
        edge_source = EDGE_UX_PATH.read_text(encoding="utf-8")

        self.assertIn("th.dco-col-edge-type", side_source)
        self.assertIn("display:none!important", side_source)
        for fieldname in (
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
        ):
            self.assertIn(fieldname, side_source)
            self.assertIn(fieldname, controls_source)

        self.assertIn("removeSideDropdownRows", controls_source)
        self.assertIn(':scope > .dco-edge-profile-grid', controls_source)
        self.assertNotIn("function ensureSideGrid", controls_source)
        self.assertNotIn('select.className = "dco-side-profile-select"', controls_source)
        self.assertIn("dco-all-sides-profile-select", controls_source)
        self.assertIn("dco-col-edge-bulk", controls_source)
        self.assertIn("ensureBulkHeader", controls_source)
        self.assertIn('edgeTypeHeader.insertAdjacentElement("afterend", header)', controls_source)
        self.assertIn("tbody td{vertical-align:middle!important}", controls_source)
        self.assertIn('root.addEventListener("dblclick"', controls_source)
        self.assertIn("openSidePopover", controls_source)
        self.assertIn("dco-edge-profile-popover", controls_source)
        self.assertIn("dco-edge-profile-option", controls_source)
        self.assertIn("is-edge-custom", controls_source)
        self.assertIn("نقرة للتفعيل والتعطيل", controls_source)
        self.assertIn("document.addEventListener(\"pointerdown\"", controls_source)
        self.assertIn("document.addEventListener(\"keydown\"", controls_source)
        self.assertIn("الافتراضي", controls_source)
        self.assertIn("تطبيق على الأربعة", controls_source)
        self.assertIn("الأربعة بالافتراضي", controls_source)
        self.assertIn("applySideSelection", controls_source)
        self.assertIn("applyAllSides", controls_source)
        self.assertIn('row[config.selectedField] = 1', controls_source)
        self.assertNotIn("new frappe.ui.Dialog", controls_source)
        self.assertNotIn("frappe.prompt", controls_source)
        self.assertNotIn("width_cm *", controls_source)
        self.assertNotIn("rate_usd_per_meter *", controls_source)

        self.assertIn("removeCutSizeColumn", cut_source)
        self.assertIn('.forEach(element => element.remove())', cut_source)
        self.assertIn("display:none!important", cut_source)
        self.assertNotIn("dco-cut-size-card", cut_source)
        self.assertNotIn("function renderCell", cut_source)
        self.assertNotIn('header.textContent = isArabic() ? "مقاس القص"', cut_source)
        self.assertIn("الخصم حسب سماكة كل ضلع", cut_source)

        self.assertIn("module.details(frm, source)", print_source)
        self.assertIn("await Promise.resolve(module.ensureProfiles(frm))", print_source)
        self.assertIn(".dco-print-measurements,.dco-entry-window-print", print_source)
        self.assertIn(".dco-print-customer-invoice", print_source)
        self.assertIn("event.stopImmediatePropagation()", print_source)
        self.assertIn("القشاط المخصص", print_source)
        self.assertIn(".filter(detail => Boolean(detail.custom))", print_source)
        self.assertIn("notesCellHtml", print_source)
        self.assertIn("shapePrintCss", print_source)
        self.assertNotIn("row.edge_type || frm.doc.default_edge_type", print_source)
        self.assertNotIn("rate_usd_per_meter *", print_source)

        self.assertIn("قشاط الأطراف", document_source)
        self.assertIn("يتضمن أطرافًا مخصصة", document_source)
        self.assertIn("سطر مستقل لكل نوع قشاط", document_source)
        self.assertIn("سماكة القشاط (مم)", edge_source)


if __name__ == "__main__":
    unittest.main()
