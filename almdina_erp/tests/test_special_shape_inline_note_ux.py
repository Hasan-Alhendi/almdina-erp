from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INLINE_EDITOR = ROOT / "public" / "js" / "door_cutting_order_inline_note_editor.js"
EDITOR = ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js"
PRINT = ROOT / "public" / "js" / "door_cutting_order_shape_print.js"
HOOKS = ROOT / "hooks.py"
PUBLIC_JS = ROOT / "public" / "js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_note_addition_is_owned_by_the_editor_and_uses_point_based_inline_text():
    editor = source(EDITOR)
    inline = source(INLINE_EDITOR)

    assert "function openInlineNoteEditor(state, point, existing = null)" in editor
    assert "inlineNoteEditor.open({" in editor
    assert 'editor.className = "dco-canvas-text-editor"' in inline
    assert 'editor.contentEditable = "true"' in inline
    assert 'editor.setAttribute("aria-label", "اكتب الملاحظة مباشرة على الرسم")' in inline
    assert "openInlineNoteEditor(state, point)" in editor
    assert 'x: Number(point.x)' in editor
    assert 'y: Number(point.y)' in editor
    assert "transform:translate(-100%,-50%)" in inline
    assert "background:transparent!important" in inline


def test_note_editor_commits_on_enter_or_blur_and_cancels_on_escape():
    inline = source(INLINE_EDITOR)

    assert 'event.key === "Enter"' in inline
    assert 'event.key === "Escape"' in inline
    assert 'editor.addEventListener("blur", () => finish(true), { once: true })' in inline
    assert "insertPlainTextAtCaret" in inline
    assert "document.execCommand" not in inline


def test_note_font_size_and_text_anchor_are_canonical_element_fields():
    editor = source(EDITOR)
    inline = source(INLINE_EDITOR)

    assert "Object.freeze([12, 14, 16, 18, 20, 24, 28, 32])" in inline
    assert "function clampFontSize(value)" in inline
    assert 'class="dco-note-font-size"' in inline
    assert "const clampNoteFontSize = inlineNoteEditor.clampFontSize" in editor
    assert "selected.font_size = nextSize" in editor
    assert 'font_size: fontSize' in editor
    assert 'text_anchor: "end"' in editor
    assert 'existing.text_anchor = existing.text_anchor === "middle" ? "middle" : "end"' in editor


def test_note_rendering_is_text_only_in_editor_and_print():
    editor = source(EDITOR)
    inline = source(INLINE_EDITOR)
    printing = source(PRINT)

    assert 'dominant-baseline="middle"' in editor
    assert 'unicode-bidi="plaintext"' in editor
    assert "dco-sketch-note-bg" not in editor
    assert "dco-sketch-note-bg" not in inline
    assert 'data-dco-readable-note="1"' in printing
    assert 'paint-order="stroke"' in printing
    assert 'stroke="#fff"' in printing
    assert 'fill="#fff8c9"' not in printing


def test_print_renderer_directly_respects_note_formatting():
    printing = source(PRINT)

    assert "function clampPrintedNoteFontSize(value)" in printing
    assert "Math.max(24, Math.min(38, parsed))" in printing
    assert "element.font_size || element.fontSize || 24" in printing
    assert 'element.text_anchor === "middle" ? "middle" : "end"' in printing
    assert "window.AlmdinaShapePrint = Object.freeze" in printing


def test_no_global_prompt_or_renderer_monkey_patch_remains():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PUBLIC_JS.glob("*.js"))
    )

    assert 'Object.defineProperty(frappe, "prompt"' not in combined
    assert "frappe.prompt = promptBridge" not in combined
    assert "_dcoSpecialShapeBasePrompt" not in combined
    assert "_inlineNotePatched" not in combined
    assert "AlmdinaReadableShapePrintInstalled" not in combined


def test_only_canonical_editor_and_print_renderer_are_loaded():
    hooks = source(HOOKS)

    assert '"public/js/door_cutting_order_shape_print.js"' in hooks
    inline = '"public/js/door_cutting_order_inline_note_editor.js"'
    editor = '"public/js/door_cutting_order_special_shape_ux.js"'
    assert inline in hooks
    assert hooks.index(inline) < hooks.index(editor)
    assert '"public/js/door_cutting_order_special_shape_ux.js"' in hooks
    assert "door_cutting_order_shape_print_readability.js" not in hooks
    assert "door_cutting_order_special_shape_note_ux.js" not in hooks
    assert "door_cutting_order_special_shape_note_guard.js" not in hooks
