from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
RENDERER = ROOT / "public" / "js" / "door_cutting_order_shape_print.js"
MEASUREMENTS = ROOT / "public" / "js" / "door_cutting_order_measurement_actions_ux.js"
INVOICE = ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"
EDGE_COLOR = ROOT / "public" / "js" / "door_cutting_order_edge_color_ux.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_shape_print_renderer_loads_before_every_print_surface():
    hooks = text(HOOKS)
    renderer = '"public/js/door_cutting_order_shape_print.js"'
    measurements = '"public/js/door_cutting_order_measurement_actions_ux.js"'
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    edge_color = '"public/js/door_cutting_order_edge_color_ux.js"'
    for script in (renderer, measurements, invoice, edge_color):
        assert script in hooks
    assert hooks.index(renderer) < hooks.index(measurements)
    assert hooks.index(renderer) < hooks.index(invoice) < hooks.index(edge_color)


def test_renderer_prefers_classic_drawing_and_falls_back_to_exact_geometry():
    source = text(RENDERER)
    assert "special_shape_drawing_json" in source
    assert "special_shape_geometry_json" in source
    assert "if (drawing) return drawingSvg(drawing, label)" in source
    assert "return geometry ? geometrySvg(geometry, label) : \"\"" in source
    for element_type in ("pen", "line", "rectangle", "ellipse", "dimension", "note"):
        assert f'element.type === "{element_type}"' in source
    assert "MAX_PRINT_POINTS" in source
    assert "safeColor" in source


def test_measurement_print_places_drawing_inside_notes_without_adding_a_column():
    source = text(MEASUREMENTS)
    assert "renderer.notesCell(row, row.notes" in source
    assert "row.special_shape_drawing_json" in source
    assert "row.special_shape_geometry_json" in source
    assert "dco-notes-has-sketch" in source
    assert "${shapePrintCss()}" in source
    assert source.count("<th class=\"notes\">ملاحظات</th>") == 1
    assert "<th>الرسم</th>" not in source


def test_customer_invoice_print_includes_drawing_in_the_canonical_print_path():
    invoice = text(INVOICE)
    edge_color = text(EDGE_COLOR)
    assert "renderer.notesCell(row, row.notes" in invoice
    assert "${printNotesCell(row)}" in invoice
    assert "${shapePrintCss()}" in invoice
    assert "dco-row-with-sketch" in invoice
    assert "function buildPrintHtml(frm)" in invoice
    assert "frame.srcdoc = buildPrintHtml(frm)" in invoice

    # Edge color is now a presentation-only patch. It must not rebuild or fork
    # the invoice print HTML, which keeps a single authoritative print path.
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
