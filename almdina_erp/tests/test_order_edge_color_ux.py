from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_defaults.js"
)
EDGE_COLOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "edge_banding"
    / "door_cutting_order_edge_color_ux.js"
)
EDGE_CONTROLS_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "edge_banding"
    / "door_cutting_order_edge_profile_controls_ux.js"
)
EDGE_DOUBLE_CLICK_GUARD = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "edge_banding"
    / "door_cutting_order_edge_profile_double_click_guard.js"
)
MEASUREMENT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_measurement_actions_ux.js"
)
HOOKS = ROOT / "frontend_assets.py"
REGISTRY = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_registry.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_has_editable_text_edge_color_below_default_edge_type():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["edge_color"]["fieldtype"] == "Data"
    assert fields["edge_color"]["reqd"] == 1
    assert not fields["edge_color"].get("read_only")
    assert doc["field_order"].index("default_edge_type") < doc["field_order"].index("edge_color")
    assert doc["field_order"].index("edge_color") < doc["field_order"].index("pieces_section")


def test_edge_color_is_manual_and_never_defaulted_from_edge_profile():
    source = _source(DEFAULTS)
    assert "edge_banding_lookup_service.get_order_edge_banding_options" in source
    assert "loadSafeEdgeOptions(frm);" in source
    assert "أدخل لون القشاط يدويًا لهذا الطلب." in source
    assert 'frappe.db.get_value("Edge Banding Type"' not in source
    assert 'frm.set_value("edge_color"' not in source
    assert "apply_edge_color_default" not in source
    assert "default_edge_type(frm)" not in source


def test_edge_color_stays_in_cost_kpi_and_fast_entry_context_without_table_duplicates():
    source = _source(EDGE_COLOR_UX)
    assert "updateColorKpi(frm, root)" in source
    assert "patchFastEntryContext(frm)" in source
    assert "لون القشاط:" in source
    assert "removeLegacyColorDuplicates(root)" in source
    assert "patchMeasurementTable" not in source
    assert "patchInvoiceLines" not in source
    assert "patchInvoiceMeta" not in source


def test_financial_documents_use_server_payload_and_shared_customer_presenter():
    financial = _source(ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js")
    presenter = _source(ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_presenter.js")
    edge = _source(EDGE_COLOR_UX)
    assert "get_customer_invoice_document" in financial
    assert "get_internal_cost_report_document" in financial
    assert "window.AlmdinaFinancialDocuments = Object.freeze" in financial
    assert "resolvePrintIdentity()" in financial
    assert "AlmdinaFactoryPrintIdentity" in financial
    assert "printHtml(documentHtml(payload, printIdentity))" in financial
    assert "presenter.printAuthorizedInvoice(frm, payload)" in financial
    assert "function printAuthorizedInvoice(frm, payload)" in presenter
    assert 'documentHtml(frm, "invoice", printIdentity, payload)' in presenter
    assert 'documentHtml(frm, "measurements", printIdentity)' in presenter
    assert "function printHtml(frm)" not in edge
    assert "event.stopImmediatePropagation()" not in edge


def test_measurement_entry_print_delegates_to_unified_document_presenter():
    source = _source(MEASUREMENT_UX)
    assert "function orderEdgeColor(frm)" in source
    assert "لون القشاط:" in source
    assert "window.AlmdinaOrderDocumentPrint" in source
    assert 'typeof documents.printMeasurements !== "function"' in source
    assert "return Promise.resolve(documents.printMeasurements(frm))" in source
    assert "function printDocumentHtml" not in source
    assert "dco-measurements-print-frame" not in source
    assert "dco-measurement-print-table" not in source


def test_edge_profiles_use_compact_double_click_popover_without_extra_row():
    controls = _source(EDGE_CONTROLS_UX)
    guard = _source(EDGE_DOUBLE_CLICK_GUARD)
    hooks = _source(HOOKS)

    assert "removeSideDropdownRows" in controls
    assert 'root.addEventListener("dblclick"' in controls
    assert "openSidePopover" in controls
    assert "dco-edge-profile-popover" in controls
    assert "is-edge-custom" in controls
    assert "tbody td{vertical-align:middle!important;" in controls
    assert "function ensureSideGrid" not in controls
    assert 'select.className = "dco-side-profile-select"' not in controls
    assert "new frappe.ui.Dialog" not in controls

    assert "const CLICK_DELAY_MS = 260" in guard
    assert 'document.addEventListener("click"' in guard
    assert 'document.addEventListener("dblclick"' in guard
    assert "replayingSingleClick" in guard
    assert "toggle.click()" in guard
    assert "controls.openSidePopover" in guard

    controls_script = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js"'
    guard_script = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js"'
    cut_script = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js"'
    assert controls_script in hooks
    assert guard_script in hooks
    assert cut_script in hooks
    assert hooks.index(controls_script) < hooks.index(guard_script) < hooks.index(cut_script)


def test_edge_profile_lists_are_custom_and_scrollable():
    controls = _source(EDGE_CONTROLS_UX)

    assert "dco-all-sides-profile-button" in controls
    assert "ensureBulkButton" in controls
    assert "openBulkPopover" in controls
    assert "bulkPopoverOptionsHtml" in controls
    assert "overflow-y:auto" in controls
    assert "scrollbar-gutter:stable" in controls
    assert "touch-action:pan-y" in controls
    assert 'popover.addEventListener("wheel"' in controls
    assert "activePopover.element.contains(event.target)" in controls
    assert 'select = document.createElement("select")' not in controls


def test_edge_color_eager_layer_is_independent_from_lazy_financial_presenters():
    hooks = HOOKS.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    legacy = "door_cutting_order_cost_invoice_ux.js"
    presenter = "door_cutting_order_document_print_presenter.js"
    financial = "door_cutting_order_financial_documents_ux.js"
    edge_color = "door_cutting_order_edge_color_ux.js"

    assert legacy not in hooks
    assert legacy not in registry
    assert presenter in hooks
    assert edge_color in hooks
    assert hooks.index(presenter) < hooks.index(edge_color)

    # Financial documents are Cost-only and activate later. Edge-color entry and
    # measurement UX must not pull that bundle onto the initial Order path.
    assert financial not in hooks
    cost = registry.split("cost: Object.freeze({", 1)[1].split(
        "});\n\n    function descriptor", 1
    )[0]
    assert financial in cost