import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "frontend_assets.py"
REGISTRY = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_registry.js"
CONTRACT = ROOT / "public" / "js" / "door_cutting_order" / "drawing" / "door_cutting_order_shape_output_contract.js"
SHAPE_PRINT = ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_shape_print.js"
EDITOR = ROOT / "public" / "js" / "door_cutting_order" / "drawing" / "special_shape_facade.js"
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
PLAN_RENDERER = CUTTING_PLAN / "door_cutting_order_cutting_plan_renderer.js"
SECURE_DXF = CUTTING_PLAN / "secure_dxf_export.js"
OPERATOR = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_operator_ux.js"
)
TABLE = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_table_performance_ux.js"
)
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
FINANCIAL_DOCUMENTS = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shape_output_contract_is_pure_immutable_and_version_aware():
    source = _source(CONTRACT)
    for dependency in ("frappe.call", "document.querySelector", "querySelector", "addEventListener"):
        assert dependency not in source
    assert 'const DOCUMENTATION_SCHEMA = "almdina.special-shape-documentation";' in source
    assert "const DRAWING_VERSION = 1;" in source
    assert "window.AlmdinaShapeOutputContract = Object.freeze({" in source
    assert "drawingFromPiece" in source
    assert "geometryFromPiece" in source
    assert "hasExactCutPath" in source
    assert "dxfPoints" in source


def test_contract_loads_before_active_shape_output_consumers():
    hooks = _source(HOOKS)
    registry = _source(REGISTRY)
    geometry = '"/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"'
    contract = '"/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"'
    assert hooks.index(geometry) < hooks.index(contract)

    eager_consumers = (
        '"public/js/door_cutting_order/printing/door_cutting_order_shape_print.js"',
        '"public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"',
        '"public/js/door_cutting_order/drawing/special_shape_facade.js"',
        '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js"',
        '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js"',
        '"public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js"',
    )
    for consumer in eager_consumers:
        assert consumer in hooks
        assert hooks.index(contract) < hooks.index(consumer)

    # Plan renderer and DXF export consume the same already-loaded global shape
    # contract, but are intentionally withheld until the Plan tab activates.
    plan = registry.split("plan: Object.freeze({", 1)[1].split(
        "cost: Object.freeze({", 1
    )[0]
    for lazy_consumer in (
        "door_cutting_order_cutting_plan_renderer.js",
        "secure_dxf_export.js",
    ):
        assert lazy_consumer not in hooks
        assert lazy_consumer in plan

    assert '"public/js/door_cutting_order_workflow.js"' not in hooks
    assert '"public/js/door_cutting_order_cost_invoice_ux.js"' not in hooks


def test_order_form_uses_global_shape_dependencies_without_re_evaluating_them():
    hooks = runpy.run_path(str(HOOKS))
    registry = _source(REGISTRY)
    global_scripts = hooks["app_include_js"]
    form_scripts = hooks["doctype_js"]["Door Cutting Order"]
    geometry_global = "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"
    contract_global = "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"
    geometry_form = "public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"
    contract_form = "public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"
    eager_consumers = (
        "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js",
        "public/js/door_cutting_order/drawing/special_shape_facade.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
    )
    assert geometry_global in global_scripts
    assert contract_global in global_scripts
    assert global_scripts.index(geometry_global) < global_scripts.index(contract_global)
    assert geometry_form not in form_scripts
    assert contract_form not in form_scripts
    for consumer in eager_consumers:
        assert consumer in form_scripts

    plan = registry.split("plan: Object.freeze({", 1)[1].split(
        "cost: Object.freeze({", 1
    )[0]
    assert "door_cutting_order_cutting_plan_renderer.js" in plan
    assert "door_cutting_order_cutting_plan_renderer.js" not in "\n".join(form_scripts)


def test_special_shape_button_resolves_documentation_workspace_at_click_time():
    operator = _source(OPERATOR)
    editor = _source(EDITOR)
    assert 'event.target.closest(".dco-special-sketch-button")' in operator
    assert "if (!row || !requirePieceDimensions(row, tr)) return" in operator
    assert "window.AlmdinaSpecialShapeEditor.open(currentFrm, row)" in operator
    assert "window.AlmdinaSpecialShapeEditor = Object.freeze(facade);" in editor
    assert "__documentationOnly: true" in editor
    assert "__manufacturingGeometrySeparated: true" in editor
    assert "door_drawing_v4" not in editor
    assert "function open(frm, row" in editor


def test_customer_documents_keep_drawing_first_and_share_one_renderer():
    shape_print = _source(SHAPE_PRINT)
    measurement_actions = _source(MEASUREMENT_ACTIONS)
    presenter = _source(PRINT_PRESENTER)
    financial = _source(FINANCIAL_DOCUMENTS)
    assert "const shapeOutput = window.AlmdinaShapeOutputContract;" in shape_print
    assert "shapeOutput.visual(piece)" in shape_print
    assert 'selected.kind === "documentation"' in shape_print
    assert "هذا توثيق لطلب العميل وليس ملف تصنيع" in shape_print
    assert "renderer.notesCell(row, notes" in presenter
    assert "window.AlmdinaOrderDocumentPrint" in measurement_actions
    assert "measurementDocumentBodyWithPayload(frm, quotePayload)" in presenter
    assert '${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}' in presenter
    assert "presenter.printAuthorizedInvoice(frm, payload)" in financial


def test_plan_dxf_and_browser_surfaces_do_not_reimplement_exact_shape_policy():
    consumers = (PLAN_RENDERER, SECURE_DXF, OPERATOR, TABLE)
    for path in consumers:
        source = _source(path)
        assert "AlmdinaShapeOutputContract" in source, path
        assert "AlmdinaSpecialShapeGeometry" not in source, path
        assert ".isExact(" not in source, path
    assert "shapeOutput.pointsAttribute(piece, 100, 100)" in _source(PLAN_RENDERER)
    assert "shapeOutput.dxfPoints(piece" in _source(SECURE_DXF)
    assert not (ROOT / "public" / "js" / "door_cutting_order_workflow.js").exists()