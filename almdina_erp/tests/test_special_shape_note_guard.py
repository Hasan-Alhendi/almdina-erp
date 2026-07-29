from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "public" / "js" / "door_cutting_order_special_shape_note_guard.js"
HOOKS = ROOT / "hooks.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_note_guard_replaces_the_prompt_property_with_a_stable_accessor():
    guard = source(GUARD)
    assert 'Object.defineProperty(frappe, "prompt"' in guard
    assert "get()" in guard
    assert "return guardedPrompt" in guard
    assert "set(candidate)" in guard
    assert "fallbackPrompt = candidate.bind(frappe)" in guard


def test_note_guard_types_at_the_clicked_canvas_point_without_a_dialog():
    guard = source(GUARD)
    assert 'document.addEventListener("pointerdown"' in guard
    assert 'svg.dataset.tool !== "note"' in guard
    assert 'editor.contentEditable = "true"' in guard
    assert 'editor.className = EDITOR_CLASS' in guard
    assert 'callback({ text })' in guard
    assert 'frappe.prompt(' not in guard
    assert 'new frappe.ui.Dialog' not in guard


def test_note_guard_has_illustrator_like_text_only_presentation():
    guard = source(GUARD)
    assert "background:transparent!important" in guard
    assert "border:0!important" in guard
    assert "box-shadow:none!important" in guard
    assert "caret-color" in guard
    assert 'event.key === "Enter"' in guard
    assert 'event.key === "Escape"' in guard


def test_note_guard_loads_after_note_ux_and_before_close_handler():
    hooks = source(HOOKS)
    note_ux = '"public/js/door_cutting_order_special_shape_note_ux.js"'
    guard = '"public/js/door_cutting_order_special_shape_note_guard.js"'
    close = '"public/js/door_cutting_order_special_shape_close_ux.js"'
    assert note_ux in hooks
    assert guard in hooks
    assert close in hooks
    assert hooks.index(note_ux) < hooks.index(guard) < hooks.index(close)
