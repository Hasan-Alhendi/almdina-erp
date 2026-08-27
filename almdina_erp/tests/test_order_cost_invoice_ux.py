from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
COST_PRESENTER = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_cost_presenter.js"
MULTI_EDGE_DOCUMENTS = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_multi_edge_documents_ux.js"
PRINT_PRESENTER = ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_presenter.js"
PRINT_THEME = ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_theme.js"
INVOICE_TOOLBAR = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_customer_invoice_toolbar_ux.js"
FINANCIAL_DOCUMENTS = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js"
HEADER_UX = ROOT / "public" / "js" / "door_cutting_order" / "responsive" / "door_cutting_order_header_ux.js"
HOOKS = ROOT / "frontend_assets.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_primary_tabs_are_order_cutting_plan_then_order_cost():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    order = doc["field_order"].index("order_tab")
    plan = doc["field_order"].index("results_tab")
    cost = doc["field_order"].index("cost_tab")
    assert order < plan < cost
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["cost_tab"]["fieldtype"] == "Tab Break"
    assert fields["order_cost_invoice_html"]["fieldtype"] == "HTML"
    assert doc["field_order"].index("board_rate_usd") > cost
    assert doc["field_order"].index("cutting_cost_per_board_usd") > cost
    assert doc["field_order"].index("board_rate_usd") < doc["field_order"].index("order_cost_invoice_html")


def test_primary_tab_bar_is_fixed_on_scroll_and_labels_are_arabic():
    src = HEADER_UX.read_text(encoding="utf-8")
    assert ".dco-sticky-tabs" in src
    assert ".dco-sticky-tabs.dco-tabs-is-fixed" in src
    assert "position: fixed !important" in src
    assert 'order_tab: "الطلب"' in src
    assert 'results_tab: "خطة القص"' in src
    assert 'cost_tab: "تكلفة الطلب"' in src
    assert 'frm.set_df_property(fieldname, "label", label)' in src


def test_cost_measurements_are_compact_and_custom_edge_details_have_one_owner():
    cost = _source(COST_PRESENTER)
    edges = _source(MULTI_EDGE_DOCUMENTS)

    assert "جدول قياسات الطلب" in cost
    assert "<th>طول القشاط (م)</th>" not in cost
    assert "<th>طول القشاط م</th>" not in cost
    assert "<th>نوع القشاط</th>" in cost
    assert '<th class="text-start">ملاحظات</th>' in cost

    # The focused edge-document presenter decorates only exceptional/custom
    # per-side edge choices; the cost presenter remains the table owner.
    assert 'headerCells[5].textContent = "القشاط المخصص"' in edges
    assert "customEdgeSummaryHtml(data[index].details)" in edges
    assert "dco-notes-col" in edges


def test_printed_width_and_length_keep_visual_edge_direction_marks():
    presenter = _source(PRINT_PRESENTER)
    theme = _source(PRINT_THEME)

    assert "function dimensionMark(value, count)" in presenter
    assert "row.source.edge_width_top" in presenter
    assert "row.source.edge_width_bottom" in presenter
    assert "row.source.edge_long_right" in presenter
    assert "row.source.edge_long_left" in presenter
    assert "dimensionMark(row.width, widthCount)" in presenter
    assert "dimensionMark(row.length, longCount)" in presenter
    assert "Array.from(" in presenter
    assert 'class="dimension-edge-line"' in presenter
    assert ".dimension-edge-line" in theme
    assert ".dimension-lines-0{visibility:hidden}" in theme


def test_edge_color_is_order_owned_and_customer_documents_show_it_once():
    order_doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in order_doc["fields"]}
    assert fields["edge_color"]["fieldtype"] == "Data"
    assert fields["edge_color"]["reqd"] == 1

    presenter = _source(PRINT_PRESENTER)
    cost = _source(COST_PRESENTER)
    assert '<div><b>لون القشاط</b>${esc(frm.doc.edge_color || "غير محدد")}</div>' in presenter
    assert '<span class="label">إجمالي القشاط</span>' not in cost
    assert '<div><b>إجمالي القشاط</b>' not in cost


def test_customer_invoice_breaks_down_boards_cutting_and_edge_banding():
    src = _source(COST_PRESENTER)
    assert "ألواح MDF" in src
    assert "أجور قص وتجهيز الألواح" in src
    assert "قشاط —" in src
    assert "function invoiceLines(frm)" in src
    assert "function invoiceTotal(frm)" in src
    assert "boardCount * boardRate" in src
    assert "boardCount * cuttingRate" in src
    assert 'unit: "لوح"' in src
    assert "regularAreaRatio" not in src
    assert "حصة خام MDF" not in src
    assert "حصة قص وتجهيز" not in src
    assert "frm.doc.edge_cost_usd" in src


def test_invoice_has_secure_customer_action_and_shared_a4_print_layout():
    toolbar = _source(INVOICE_TOOLBAR)
    presenter = _source(PRINT_PRESENTER)
    theme = _source(PRINT_THEME)

    assert "طباعة فاتورة الزبون" in toolbar
    assert 'can(frm, "print_customer_invoice")' in toolbar
    assert "@page{size:A4 portrait" in theme
    assert 'const invoice = mode === "invoice";' in presenter
    assert "measurementDocumentBodyWithPayload(frm, quotePayload)" in presenter
    assert '${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}' in presenter
    assert "renderer.notesCell(row, notes" in presenter
    assert '<th>ملاحظات</th>' in presenter


def test_invoice_printing_uses_isolated_iframe_not_popup_window():
    presenter = _source(PRINT_PRESENTER)
    assert 'document.createElement("iframe")' in presenter
    assert "frame.srcdoc = html" in presenter
    assert "win.print()" in presenter
    assert 'win.addEventListener("afterprint", cleanup' in presenter
    assert "window.open(" not in presenter
    assert "اسمح بالنوافذ المنبثقة" not in presenter


def test_legacy_cost_invoice_is_deleted_and_secure_financial_layers_are_loaded():
    hooks = HOOKS.read_text(encoding="utf-8")
    legacy_path = ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"
    assert not legacy_path.exists()

    legacy = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    presenter = '"public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js"'
    cost_permissions = '"public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js"'
    financial = '"public/js/door_cutting_order/costing/door_cutting_order_financial_documents_ux.js"'
    toolbar = '"public/js/door_cutting_order/costing/door_cutting_order_customer_invoice_toolbar_ux.js"'
    assert legacy not in hooks
    for script in (presenter, cost_permissions, financial, toolbar):
        assert script in hooks
    assert hooks.index(presenter) < hooks.index(cost_permissions) < hooks.index(financial) < hooks.index(toolbar)

    # The financial layer delegates customer invoices to the canonical unified
    # document presenter instead of maintaining a second print renderer.
    financial_source = _source(FINANCIAL_DOCUMENTS)
    assert "presenter.printAuthorizedInvoice(frm, payload)" in financial_source
