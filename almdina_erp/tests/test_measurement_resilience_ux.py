from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_measurement_resilience_ux.js"
)
HOOKS = ROOT / "frontend_assets.py"


def _source() -> str:
    return UX.read_text(encoding="utf-8")


def test_horizontal_scroll_is_available_on_small_screens_without_crushing_the_table():
    source = _source()
    assert "overflow-x:auto !important" in source
    assert "@media (max-width:980px)" in source
    assert "min-width:1180px !important" in source
    assert "min-width:300px !important" in source
    assert "scrollbar-width:thin" in source
    assert "overscroll-behavior:contain" in source


def test_small_screens_keep_sketch_and_delete_actions_reachable_by_scrolling():
    source = _source()
    assert "@media (max-width:720px)" in source
    assert ".dco-fast-table .dco-col-sketch" in source
    assert ".dco-fast-table .dco-col-delete" in source
    assert "display:table-cell !important" in source
    assert "position:sticky" in source
    assert "right:32px" in source


def test_long_notes_have_ellipsis_full_text_hint_and_large_editor():
    source = _source()
    assert "text-overflow:ellipsis" in source
    assert "dco-notes-expand" in source
    assert "has-long-note" in source
    assert "Small Text" in source
    assert "min-height:240px" in source
    assert "فتح الملاحظة كاملة" in source
    assert "row.notes = value" in source
    assert 'frm.script_manager.trigger("notes", row.doctype, row.name)' in source


def test_piece_type_change_preserves_table_and_page_scroll_position():
    source = _source()
    assert "select.dco-fast-select[data-field='piece_type']" in source
    assert "capturePosition(root, control)" in source
    assert "restorePosition(frm, state, token)" in source
    assert "scroller.scrollTop = state.tableTop" in source
    assert "scroller.scrollLeft = state.tableLeft" in source
    assert "control.focus({ preventScroll: true })" in source
    assert "document.scrollingElement.scrollTop = state.documentTop" in source


def test_resilience_layer_loads_after_compact_and_special_shape_ux():
    hooks = HOOKS.read_text(encoding="utf-8")
    compact = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_compact_measurements_ux.js"'
    special = '"public/js/door_cutting_order/drawing/special_shape_facade.js"'
    resilience = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_resilience_ux.js"'
    assert compact in hooks
    assert special in hooks
    assert resilience in hooks
    assert hooks.index(compact) < hooks.index(resilience)
    assert hooks.index(special) < hooks.index(resilience)
