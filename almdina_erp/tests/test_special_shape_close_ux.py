from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOSE_UX = ROOT / "public" / "js" / "door_cutting_order_special_shape_close_ux.js"
HOOKS = ROOT / "hooks.py"


def _source() -> str:
    return CLOSE_UX.read_text(encoding="utf-8")


def test_special_shape_close_button_is_captured_and_routes_through_modal_hide():
    source = _source()
    assert ".btn-modal-close" in source
    assert ".btn-close" in source
    assert 'document.addEventListener("click", handleCloseClick, true)' in source
    assert 'event.stopImmediatePropagation()' in source
    assert '$modal.modal("hide")' in source
    assert 'window.bootstrap.Modal' in source


def test_close_fix_keeps_unsaved_changes_guard_authoritative():
    source = _source()
    assert 'hide.bs.modal' in source
    assert 'isDefaultPrevented()' in source
    assert 'modal.classList.remove("show")' in source
    assert 'hidden.bs.modal' in source


def test_close_fix_is_loaded_immediately_after_special_shape_editor():
    hooks = HOOKS.read_text(encoding="utf-8")
    editor = '"public/js/door_cutting_order_special_shape_ux.js"'
    close_fix = '"public/js/door_cutting_order_special_shape_close_ux.js"'
    assert editor in hooks
    assert close_fix in hooks
    assert hooks.index(editor) < hooks.index(close_fix)


def test_special_shape_editor_keeps_a_single_active_dialog():
    source = (ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js").read_text(
        encoding="utf-8"
    )
    assert "let activeDialog = null" in source
    assert "if (activeDialog)" in source
    assert "activeDialog.hide()" in source
    assert 'hidden.bs.modal.dco-special-shape-active' in source
    assert "activeDialog = dialog" in source
    assert "Duplicate open calls" in source
