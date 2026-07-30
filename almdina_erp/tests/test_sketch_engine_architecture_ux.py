from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
ENGINE = ROOT / "public" / "js" / "door_cutting_order_sketch_engine.js"
EDITOR = ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pure_sketch_engine_loads_before_the_dom_editor():
    hooks = _source(HOOKS)

    engine_position = hooks.index(
        '"public/js/door_cutting_order_sketch_engine.js"'
    )
    editor_position = hooks.index(
        '"public/js/door_cutting_order_special_shape_ux.js"'
    )

    assert engine_position < editor_position


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


def test_editor_stays_focused_on_interaction_and_orchestration():
    editor_lines = _source(EDITOR).splitlines()

    assert len(editor_lines) <= 1450
    assert "function open(" in "\n".join(editor_lines)
    assert "function bind(" in "\n".join(editor_lines)
