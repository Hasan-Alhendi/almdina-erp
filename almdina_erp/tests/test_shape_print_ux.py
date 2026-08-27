from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "frontend_assets.py"
REGISTRY = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_registry.js"
RENDERER = ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_shape_print.js"
CONTRACT = ROOT / "public" / "js" / "door_cutting_order" / "drawing" / "door_cutting_order_shape_output_contract.js"
MEASUREMENT_ACTIONS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_measurement_actions_ux.js"
)
PRINT_PRESENTER = ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_presenter.js"
FINANCIAL = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js"
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
    registry = text(REGISTRY)
    renderer = "door_cutting_order_shape_print.js"
    measurements = "door_cutting_order_measurement_actions_ux.js"
    presenter = "door_cutting_order_document_print_presenter.js"
    financial = "door_cutting_order_financial_documents_ux.js"
    edge_color = "door_cutting_order_edge_color_ux.js"

    # Measurement/customer print primitives remain eager and ordered because the
    # Order workspace needs them without activating Cost.
    for script in (renderer, measurements, presenter, edge_color):
        assert script in hooks
    assert hooks.index(renderer) < hooks.index(measurements)
    assert hooks.index(renderer) < hooks.index(presenter)
    assert hooks.index(renderer) < hooks.index(edge_color)

    # Financial printing is Cost-only, but consumes the already initialized
    # shared presenter/shape renderer after Cost bundle activation.
    assert financial not in hooks
    cost = registry.split("cost: Object.freeze({", 1)[1].split(
        "});\n\n    function descriptor", 1
    )[0]
    assert financial in cost
    assert "door_cutting_order_cost_permissions_ux.js" in cost
    assert cost.index("door_cutting_order_cost_permissions_ux.js") < cost.index(financial)
    assert '"public/js/door_cutting_order_cost_invoice_ux.js"' not in hooks


def test_renderer_delegates_selection_to_the_shared_shape_output_contract():
    source = text(RENDERER)
    contract = text(CONTRACT)
    assert "const shapeOutput = window.AlmdinaShapeOutputContract;" in source
    assert "const selected = shapeOutput.visual(piece);" in source
    assert 'selected.kind === "documentation"' in source
    assert "const drawing = drawingFromPiece(piece);" in contract
    assert 'return Object.freeze({ kind: "documentation", payload: drawing });' in contract
    assert 'Object.freeze({ kind: "geometry", payload: polygon })' in contract
    assert 'element.type === "stroke"' in source
    assert '["line", "arrow", "dimension"].includes(element.type)' in source
    assert '["rect", "ellipse"].includes(element.type)' in source
    assert 'element.type === "text"' in source
    assert "documentationElement" in source
    assert "function color" in source


def test_measurement_print_places_drawing_inside_notes_without_adding_a_column():
    actions = text(MEASUREMENT_ACTIONS)
    source = text(PRINT_PRESENTER)
    assert "window.AlmdinaOrderDocumentPrint" in actions
    assert "return Promise.resolve(documents.printMeasurements(frm))" in actions
    assert "...source" in source
    assert "renderer.notesCell(row, notes" in source
    assert "rowHasDrawing(row)" in source
    assert "notes-with-drawing" in source
    assert "shapePrintCss()" in source
    assert source.count("<th>ملاحظات</th>") == 1
    assert "<th>الرسم</th>" not in source


def test_customer_invoice_reuses_the_canonical_measurement_and_shape_renderer():
    presenter = text(PRINT_PRESENTER)
    financial = text(FINANCIAL)
    edge_color = text(EDGE_COLOR)

    assert "renderer.notesCell(row, notes" in presenter
    assert "measurementDocumentBodyWithPayload(frm, quotePayload)" in presenter
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
    assert ".dco-piece-sketch>svg" in source
    assert ".dco-piece-sketch .dco-reference-crop{overflow:hidden}" in source
    assert "height:68px" in source