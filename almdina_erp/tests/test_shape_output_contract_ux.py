from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
CONTRACT = ROOT / "public" / "js" / "door_cutting_order_shape_output_contract.js"
SHAPE_PRINT = ROOT / "public" / "js" / "door_cutting_order_shape_print.js"
EDITOR = ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js"
PLAN_RENDERER = ROOT / "public" / "js" / "door_cutting_order_cutting_plan_renderer.js"
WORKFLOW = ROOT / "public" / "js" / "door_cutting_order_workflow.js"
SECURE_DXF = ROOT / "public" / "js" / "secure_dxf_export.js"
OPERATOR = ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
TABLE = ROOT / "public" / "js" / "door_cutting_order_table_performance_ux.js"
MEASUREMENTS = ROOT / "public" / "js" / "door_cutting_order_measurement_actions_ux.js"
INVOICE = ROOT / "public" / "js" / "door_cutting_order_cost_invoice_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shape_output_contract_is_pure_immutable_and_version_aware():
    source = _source(CONTRACT)

    for dependency in (
        "frappe",
        "document",
        "querySelector",
        "addEventListener",
    ):
        assert dependency not in source

    assert "const DRAWING_VERSION = 1;" in source
    assert "window.AlmdinaShapeOutputContract = Object.freeze({" in source
    assert "drawingFromPiece" in source
    assert "geometryFromPiece" in source
    assert "hasExactCutPath" in source
    assert "dxfPoints" in source


def test_contract_loads_before_all_shape_output_consumers():
    hooks = _source(HOOKS)
    geometry = '"/assets/almdina_erp/js/door_cutting_order_special_shape_geometry.js"'
    contract = '"/assets/almdina_erp/js/door_cutting_order_shape_output_contract.js"'
    secure_dxf = '"/assets/almdina_erp/js/secure_dxf_export.js"'

    assert hooks.index(geometry) < hooks.index(contract) < hooks.index(secure_dxf)
    for consumer in (
        '"public/js/door_cutting_order_cutting_plan_renderer.js"',
        '"public/js/door_cutting_order_workflow.js"',
        '"public/js/door_cutting_order_shape_print.js"',
        '"public/js/door_cutting_order_operator_ux.js"',
        '"public/js/door_cutting_order_special_shape_ux.js"',
        '"public/js/door_cutting_order_table_performance_ux.js"',
        '"public/js/door_cutting_order_measurement_actions_ux.js"',
        '"public/js/door_cutting_order_cost_invoice_ux.js"',
    ):
        assert hooks.index(contract) < hooks.index(consumer)


def test_customer_documents_keep_drawing_first_and_share_one_renderer():
    shape_print = _source(SHAPE_PRINT)
    editor = _source(EDITOR)
    measurements = _source(MEASUREMENTS)
    invoice = _source(INVOICE)

    assert "const shapeOutput = window.AlmdinaShapeOutputContract;" in shape_print
    assert "const selected = shapeOutput.visual(piece);" in shape_print
    assert 'selected.kind === "drawing"' in shape_print
    assert "shapeOutput.parseDrawing(raw)" in editor
    assert "renderer.notesCell(row, row.notes" in measurements
    assert "renderer.notesCell(row, row.notes" in invoice


def test_plan_dxf_and_status_surfaces_do_not_reimplement_exact_shape_policy():
    consumers = (PLAN_RENDERER, WORKFLOW, SECURE_DXF, OPERATOR, TABLE)

    for path in consumers:
        source = _source(path)
        assert "AlmdinaShapeOutputContract" in source, path
        assert "AlmdinaSpecialShapeGeometry" not in source, path
        assert ".isExact(" not in source, path

    assert "shapeOutput.pointsAttribute(piece, 100, 100)" in _source(PLAN_RENDERER)
    assert "shapeOutput.pointsAttribute(piece, 100, 100)" in _source(WORKFLOW)
    assert "shapeOutput.dxfPoints(piece" in _source(WORKFLOW)
    assert "shapeOutput.dxfPoints(piece" in _source(SECURE_DXF)
