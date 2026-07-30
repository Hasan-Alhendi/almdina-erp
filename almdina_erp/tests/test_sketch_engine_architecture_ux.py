from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
ENGINE = ROOT / "public" / "js" / "door_cutting_order_sketch_engine.js"
INTERACTION = ROOT / "public" / "js" / "door_cutting_order_sketch_interaction.js"
HISTORY = ROOT / "public" / "js" / "door_cutting_order_sketch_history.js"
RENDERER = ROOT / "public" / "js" / "door_cutting_order_sketch_renderer.js"
EDITOR = ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pure_sketch_layers_load_before_the_dom_editor():
    hooks = _source(HOOKS)

    engine_position = hooks.index(
        '"public/js/door_cutting_order_sketch_engine.js"'
    )
    interaction_position = hooks.index(
        '"public/js/door_cutting_order_sketch_interaction.js"'
    )
    history_position = hooks.index(
        '"public/js/door_cutting_order_sketch_history.js"'
    )
    renderer_position = hooks.index(
        '"public/js/door_cutting_order_sketch_renderer.js"'
    )
    editor_position = hooks.index(
        '"public/js/door_cutting_order_special_shape_ux.js"'
    )

    assert (
        engine_position
        < interaction_position
        < history_position
        < renderer_position
        < editor_position
    )


def test_sketch_engine_has_no_framework_or_dom_dependencies():
    engine = _source(ENGINE)

    forbidden_dependencies = (
        "frappe",
        "document",
        "querySelector",
        "addEventListener",
        "Dialog",
    )

    for dependency in forbidden_dependencies:
        assert dependency not in engine

    assert "window.AlmdinaSketchEngine = Object.freeze({" in engine


def test_sketch_interaction_has_no_framework_or_dom_dependencies():
    interaction = _source(INTERACTION)

    forbidden_dependencies = (
        "frappe",
        "document",
        "querySelector",
        "addEventListener",
        "PointerEvent",
        "setPointerCapture",
        "Dialog",
    )

    for dependency in forbidden_dependencies:
        assert dependency not in interaction

    assert "const sketchEngine = window.AlmdinaSketchEngine;" in interaction
    assert "window.AlmdinaSketchInteraction = Object.freeze({" in interaction
    assert "const DRAWING_TOOLS = Object.freeze([" in interaction


def test_sketch_history_has_no_framework_or_dom_dependencies():
    history = _source(HISTORY)

    forbidden_dependencies = (
        "frappe",
        "document",
        "querySelector",
        "addEventListener",
        "Dialog",
    )

    for dependency in forbidden_dependencies:
        assert dependency not in history

    assert "window.AlmdinaSketchHistory = Object.freeze({" in history
    assert "const DEFAULT_HISTORY_LIMIT = 80;" in history


def test_sketch_renderer_has_no_framework_or_dom_dependencies():
    renderer = _source(RENDERER)

    forbidden_dependencies = (
        "frappe",
        "document",
        "querySelector",
        "addEventListener",
        "Dialog",
    )

    for dependency in forbidden_dependencies:
        assert dependency not in renderer

    assert "window.AlmdinaSketchRenderer = Object.freeze({" in renderer
    assert "sketchEngine.elementBounds(" in renderer
    assert "sketchEngine.normalizePenStroke(" in renderer


def test_editor_delegates_geometry_instead_of_reimplementing_it():
    editor = _source(EDITOR)

    assert "const sketchEngine = window.AlmdinaSketchEngine;" in editor
    assert "sketchEngine.erasePenStroke(" in editor

    pure_functions = (
        "simplifyPolyline",
        "fitNearlyStraightLine",
        "smoothCorners",
        "normalizePenStroke",
        "elementAnchorPoints",
        "nearestAnchor",
        "snapLineEnd",
        "polylineLength",
        "snapPenEndpoints",
        "templatePoints",
        "translateElement",
        "elementBounds",
        "clampViewBox",
    )

    for function_name in pure_functions:
        assert f"function {function_name}(" not in editor


def test_editor_delegates_document_changes_and_history():
    editor = _source(EDITOR)

    assert "const sketchHistory = window.AlmdinaSketchHistory;" in editor
    assert "sketchHistory.createState(" in editor
    for operation in (
        "snapshot",
        "addElement",
        "selectElement",
        "deleteSelected",
        "clear",
        "undo",
        "redo",
    ):
        assert f"sketchHistory.{operation}(" in editor

    forbidden_ownership = (
        "state.undo.push(",
        "state.redo.push(",
        "state.undo.pop(",
        "state.redo.pop(",
        "state.elements.push(",
        "state.elements.splice(",
    )

    for mutation in forbidden_ownership:
        assert mutation not in editor


def test_editor_delegates_draft_interaction_transitions():
    editor = _source(EDITOR)

    assert "const sketchInteraction = window.AlmdinaSketchInteraction;" in editor
    for operation in ("beginDraft", "updateDraft", "finalizeDraft"):
        assert f"sketchInteraction.{operation}(" in editor

    forbidden_ownership = (
        'state.draft = { id: id("pen")',
        "state.draft.width =",
        "state.draft.rx =",
        "const tooSmall =",
        "element.points = snapPenEndpoints(",
    )

    for mutation in forbidden_ownership:
        assert mutation not in editor


def test_editor_delegates_svg_and_sidebar_presentation():
    editor = _source(EDITOR)

    assert "const sketchRenderer = window.AlmdinaSketchRenderer;" in editor
    assert "sketchRenderer.canvasView(state" in editor
    assert "sketchRenderer.sidebarView(state.elements)" in editor

    renderer_functions = (
        "pathData",
        "textPosition",
        "elementMarkup",
        "selectionMarkup",
        "snapIndicatorMarkup",
    )

    for function_name in renderer_functions:
        assert f"function {function_name}(" not in editor


def test_editor_stays_focused_on_interaction_and_orchestration():
    editor_lines = _source(EDITOR).splitlines()

    assert len(editor_lines) <= 1300
    assert "function open(" in "\n".join(editor_lines)
    assert "function bind(" in "\n".join(editor_lines)
