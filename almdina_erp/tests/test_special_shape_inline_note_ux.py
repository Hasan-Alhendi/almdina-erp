from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "public" / "js" / "door_cutting_order_special_shape_note_ux.js"
EDITOR = ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js"
HOOKS = ROOT / "hooks.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_note_addition_uses_inline_canvas_editor_instead_of_a_frappe_dialog():
    patch = source(PATCH)
    assert 'NOTE_TITLES = new Set(["إضافة ملاحظة", "تعديل الملاحظة"])' in patch
    assert "frappe._dcoSpecialShapeOriginalPrompt" in patch
    assert "openInlineEditor(session, defaultValue, callback, editingExisting)" in patch
    assert 'input.className = "dco-inline-note-editor"' in patch
    assert 'input.placeholder = "اكتب الملاحظة هنا"' in patch
    assert 'event.key === "Enter"' in patch
    assert 'event.key === "Escape"' in patch
    assert "session.lastPointer = { clientX: event.clientX, clientY: event.clientY }" in patch


def test_notes_are_rendered_as_text_only_without_background_rectangles():
    patch = source(PATCH)
    assert ".dco-sketch-note-bg{display:none!important" in patch
    assert 'group.querySelectorAll(".dco-sketch-note-bg,rect").forEach(rect => rect.remove())' in patch
    assert 'text.setAttribute("text-anchor", "middle")' in patch
    assert 'text.setAttribute("dominant-baseline", "middle")' in patch
    assert 'text.setAttribute("fill", note.color || "#172033")' in patch


def test_note_font_size_is_selectable_and_persisted_in_drawing_json():
    patch = source(PATCH)
    assert "const FONT_SIZES = [12, 14, 16, 18, 20, 24, 28, 32]" in patch
    assert "حجم خط الملاحظة" in patch
    assert 'class="dco-note-font-size"' in patch
    assert "element.font_size = size" in patch
    assert "session.row.special_shape_drawing_json = JSON.stringify(payload)" in patch
    assert "session.frm.dirty()" in patch


def test_existing_notes_keep_backward_compatible_default_font_size():
    patch = source(PATCH)
    assert "element.font_size || element.fontSize || 16" in patch
    assert "clampFontSize(note.font_size || 16)" in patch


def test_measurement_and_invoice_prints_remove_note_background_and_respect_font_size():
    patch = source(PATCH)
    assert "function patchPrintedSvg(piece, markup)" in patch
    assert "group.querySelectorAll(\"rect\").forEach(rect => rect.remove())" in patch
    assert 'text.setAttribute("font-size", String(clampFontSize(note.font_size || 16)))' in patch
    assert "window.AlmdinaShapePrint = Object.freeze" in patch
    assert "notesCell: patchedNotesCell" in patch


def test_inline_note_layer_loads_after_editor_and_before_close_fix():
    hooks = source(HOOKS)
    editor = '"public/js/door_cutting_order_special_shape_ux.js"'
    notes = '"public/js/door_cutting_order_special_shape_note_ux.js"'
    close = '"public/js/door_cutting_order_special_shape_close_ux.js"'
    assert editor in hooks
    assert notes in hooks
    assert close in hooks
    assert hooks.index(editor) < hooks.index(notes) < hooks.index(close)


def test_canonical_editor_still_exposes_note_tool_for_the_inline_layer():
    editor = source(EDITOR)
    assert '{ key: "note", group: "explain"' in editor
    assert 'if (state.tool === "note")' in editor
    assert "window.AlmdinaSpecialShapeEditor" in editor
