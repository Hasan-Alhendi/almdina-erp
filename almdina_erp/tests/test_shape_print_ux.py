from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
RENDERER = ROOT / "public" / "js" / "door_cutting_order_shape_print.js"
CONTRACT = ROOT / "public" / "js" / "door_cutting_order_shape_output_contract.js"
MEASUREMENT_ACTIONS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_measurement_actions_ux.js"
)
PRINT_PRESENTER = ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
FINANCIAL = ROOT / "public" / "js" / "door_cutting_order_financial_documents_ux.js"
EDGE_COLOR = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "edge_banding"
    / "door_cutting_order_edge_color_ux.js"
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_shape_print_renderer_loads_before_every_active_print_surface():
    hooks = text(HOOKS)
    renderer = '"public/js/door_cutting_order_shape_print.js"'
    measurements = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js"'
    presenter = '"public/js/door_cutting_order_document_print_presenter.js"'
    financial = '"public/js/door_cutting_order_financial_documents_ux.js"'
    edge_color = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js"'
    for script in (renderer, measurements, presenter, financial, edge_color):
        assert script in hooks
    assert hooks.index(renderer) < hooks.index(measurements)
    assert hooks.index(renderer) < hooks.index(presenter) < hooks.index(financial) < hooks.index(edge_color)
    assert '"public/js/door_cutting_order_cost_invoice_ux.js"' not in hooks


def test_renderer_delegates_selection_to_the_shared_shape_output_contract():
    source = text(RENDERER)
    contract = text(CONTRACT)
    assert "const shapeOutput = window.AlmdinaShapeOutputContract;" in source
    assert "const selected = shapeOutput.visual(piece);" in source
    assert 'selected.kind === "drawing"' in source
    assert "const drawing = drawingFromPiece(piece);" in contract
    assert 'return Object.freeze({ kind: "drawing", payload: drawing });' in contract
    assert 'Object.freeze({ kind: "geometry", payload: polygon })' in contract
    for element_type in ("pen", "line", "rectangle", "ellipse", "dimension", "note"):
        assert f'element.type === "{element_type}"' in source
    assert "MAX_PRINT_POINTS" in source
    assert "safeColor" in source


def test_measurement_print_places_drawing_inside_notes_without_adding_a_column():
    actions = text(MEASUREMENT_ACTIONS)
    source = text(PRINT_PRESENTER)
    assert "window.AlmdinaOrderDocumentPrint" in actions
    assert "return Promise.resolve(documents.printMeasurements(frm))" in actions
    assert "...source" in source
    assert "renderer.notesCell(row, row.notes" in source
    assert "rowHasDrawing(row)" in source
    assert "notes-with-drawing" in source
    assert "shapePrintCss()" in source
    assert source.count("<th>ملاحظات</th>") == 1
    assert "<th>الرسم</th>" not in source


def test_customer_invoice_reuses_the_canonical_measurement_and_shape_renderer():
    presenter = text(PRINT_PRESENTER)
    financial = text(FINANCIAL)
    edge_color = text(EDGE_COLOR)

    assert "renderer.notesCell(row, row.notes" in presenter
    assert '${measurementDocumentBody(frm)}' in presenter
    assert '${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}' in presenter
    assert "shapePrintCss()" in presenter
    assert "async function printAuthorizedInvoice(frm, payload)" in presenter
    assert "frame.srcdoc = html" in presenter
    assert "presenter.printAuthorizedInvoice(frm, payload)" in financial

    # Edge color remains presentation-only and never forks print HTML.
    assert "patchMeasurementDrawings" not in edge_color
    assert "renderer.notesCell(" not in edge_color
    assert "removeLegacyColorDuplicates" in edge_color


def test_print_css_keeps_drawn_piece_row_together_and_preserves_long_notes():
    source = text(RENDERER)
    assert "page-break-inside:avoid" in source
    assert "break-inside:avoid" in source
    assert "overflow-wrap:anywhere" in source
    assert ".dco-piece-sketch svg" in source
    assert "height:68px" in source
