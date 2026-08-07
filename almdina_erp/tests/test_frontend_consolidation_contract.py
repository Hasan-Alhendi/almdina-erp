from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
CANONICAL_FORM = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.js"
)
PLAN_RENDERER = ROOT / "public" / "js" / "door_cutting_order_cutting_plan_renderer.js"
INPUT_STABILITY = ROOT / "public" / "js" / "input_stability.js"
FAST_SAVE = ROOT / "public" / "js" / "door_cutting_order_fast_save_ux.js"
MEASUREMENT_ACTIONS = (
    ROOT / "public" / "js" / "door_cutting_order_measurement_actions_ux.js"
)
DOCUMENT_PRINT = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
)
SECURE_DXF = ROOT / "public" / "js" / "secure_dxf_export.js"


class TestFrontendConsolidationContract(unittest.TestCase):
    def test_canonical_frappe_entry_point_is_side_effect_free(self) -> None:
        source = CANONICAL_FORM.read_text(encoding="utf-8")

        self.assertLessEqual(len(source.splitlines()), 12)
        self.assertNotIn("frappe.ui.form.on", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("add_custom_button", source)
        self.assertNotIn("set_query", source)
        self.assertNotIn("preview_door_cutting_order", source)
        self.assertNotIn("board_item", source)

    def test_focused_renderer_loads_before_every_active_plan_consumer(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        renderer = '"public/js/door_cutting_order_cutting_plan_renderer.js"'

        self.assertIn(renderer, hooks)
        for consumer in (
            '"public/js/door_cutting_order_plan_tabs_ux.js"',
            '"public/js/door_cutting_order_drawing_plan_ux.js"',
            '"public/js/shop_floor_order_ux.js"',
        ):
            self.assertLess(hooks.index(renderer), hooks.index(consumer))

    def test_protected_surfaces_have_deterministic_form_load_order(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        cost_presenter = '"public/js/door_cutting_order_cost_presenter.js"'
        cost_permissions = '"public/js/door_cutting_order_cost_permissions_ux.js"'
        plan_tabs = '"public/js/door_cutting_order_plan_tabs_ux.js"'
        permission_refresh = '"public/js/door_cutting_order_permission_refresh_ux.js"'

        self.assertIn('"route": "/desk"', hooks)
        self.assertNotIn('"route": "/desk/almdina-erp"', hooks)
        self.assertLess(hooks.index(cost_presenter), hooks.index(cost_permissions))
        self.assertLess(hooks.index(plan_tabs), hooks.index(permission_refresh))

    def test_duplicate_legacy_form_controllers_are_not_loaded(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        for legacy in (
            '"public/js/door_cutting_order_workflow.js"',
            '"public/js/door_cutting_order_cost_invoice_ux.js"',
            '"public/js/production_stage.js"',
        ):
            self.assertNotIn(legacy, hooks)

    def test_renderer_owns_drawing_only(self) -> None:
        source = PLAN_RENDERER.read_text(encoding="utf-8")

        self.assertIn("window.AlmdinaCuttingPlanRender", source)
        self.assertIn("build: build_cutting_plan_html", source)
        self.assertIn("parse: parse_plan", source)
        self.assertIn("print: print_cutting_plan", source)
        self.assertIn("frm.doc.board_description", source)
        self.assertNotIn("frm.doc.board_item", source)
        self.assertNotIn("frappe.ui.form.on", source)
        self.assertNotIn("preview_door_cutting_order", source)
        self.assertNotIn("print_measurements_table", source)
        self.assertNotIn("export_cutting_plan_dxf", source)
        self.assertNotIn("setup_pieces_excel_ux", source)
        # Single A4 print: screen header + all sheet boards scaled to one page.
        self.assertIn("size: A4 portrait", source)
        self.assertIn("planRootFromVisibleDom", source)
        self.assertIn("dco-print-plan-single", source)
        self.assertIn("layoutPlanForSingleA4", source)
        self.assertIn("dco-summary-grid", source)
        self.assertIn("render_plan_header_cards", source)
        self.assertIn("dco-plan-header-cards", source)
        self.assertIn("رقم الطلب", source)
        self.assertIn("اسم الزبون", source)
        self.assertIn("تاريخ الطلب", source)
        self.assertIn("نوع اللوح", source)
        self.assertIn("لون القشاط", source)
        self.assertIn('round(piece.original_w, 1)}*${round(piece.original_h, 1)}</span>', source)
        self.assertNotIn("piece.label)}</b>", source)
        self.assertNotIn(" سم</span>", source)
        self.assertNotIn("page-break-after: always", source)
        self.assertNotIn("print-header", source)
        self.assertNotIn("ERPNext Cutting Plan", source)

    def test_modern_modules_own_recalculation_printing_and_dxf(self) -> None:
        fast_save = FAST_SAVE.read_text(encoding="utf-8")
        measurements = MEASUREMENT_ACTIONS.read_text(encoding="utf-8")
        document_print = DOCUMENT_PRINT.read_text(encoding="utf-8")
        secure_dxf = SECURE_DXF.read_text(encoding="utf-8")

        self.assertIn("door_cutting_order.recalculate_order", fast_save)
        self.assertIn("dco-print-measurements", measurements)
        self.assertIn("window.AlmdinaOrderDocumentPrint", document_print)
        self.assertIn("printInvoice(frm)", document_print)
        self.assertIn('event.target.closest(".dco-print-customer-invoice")', document_print)
        self.assertIn("validatedExport(frm)", secure_dxf)
        self.assertIn('permissions.canDocument(frm, "export_dxf")', secure_dxf)
        self.assertIn("__almdinaSecureDxfExportLoaded", secure_dxf)
        self.assertNotIn("DXF_EXPORT_ROLES", secure_dxf)
        self.assertNotIn("frappe.user_roles", secure_dxf)

    def test_input_policy_uses_public_form_surface_only(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertIn("prototype.refresh_field = function inputSafeRefreshField", source)
        self.assertNotIn("frappe.ui.form.handlers", source)
        self.assertNotIn("frappe.call =", source)
        self.assertNotIn("Function.prototype.toString", source)
        self.assertNotIn("preview_door_cutting_order", source)


if __name__ == "__main__":
    unittest.main()
