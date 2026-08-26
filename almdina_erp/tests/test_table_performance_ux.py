from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_table_performance_ux.js"
)
OPERATOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_operator_ux.js"
)
HOOKS = ROOT / "frontend_assets.py"


def _source() -> str:
    return PERFORMANCE_UX.read_text(encoding="utf-8")


def test_piece_type_change_is_intercepted_before_legacy_full_table_render():
    source = _source()
    assert "handlePieceTypeChange(frm, root, control, event)" in source
    assert "event.stopImmediatePropagation()" in source
    assert 'setPieceType(frm, tr, control.value || "Regular"' in source
    assert "function setPieceType(frm, tr, pieceType" in source
    assert "window.AlmdinaTablePerformanceUX = Object.freeze" in source
    assert "updatePieceTypeVisual(frm, tr, row)" in source
    assert "options.focusTarget.focus({ preventScroll: true })" in source
    assert "extraAddons.reconcilePieceType(frm, row)" in source
    assert "extraAddons.syncRowPresentation(frm, tr, row" in source
    assert "renderFastMeasurements(frm)" not in source


def test_row_selector_is_preserved_or_recreated_after_piece_type_change():
    source = _source()
    assert "ensureRowSelector(frm, tr)" in source
    assert 'cell.className = "dco-select-col"' in source
    assert 'checkbox.className = "dco-row-selector"' in source
    assert "checkbox.dataset.rowName = name" in source
    assert "selectedRows(frm).has(name)" in source
    assert "ensureAllSelectors(frm, root)" in source


def test_virtual_piece_type_change_materializes_one_row_without_rebuilding_table():
    source = _source()
    assert 'frappe.model.add_child(frm.doc, CHILD_DOCTYPE, "pieces")' in source
    assert "materializeVirtualRow(frm, tr)" in source
    assert "resetVirtualClone(frm, clone)" in source
    assert 'tbody.appendChild(clone)' in source
    assert 'frm.script_manager.trigger("pieces_add", row.doctype, row.name)' in source
    assert 'extraAddons.renderTypePicker(' in source
    assert 'clone.classList.remove("dco-special-row", "dco-clipped-corner-row", "dco-extra-row"' in source


def test_expensive_class_mutation_observer_is_replaced_by_direct_child_list_observer():
    source = _source()
    assert "root._dcoKeyboardColumnsObserver.disconnect()" in source
    assert 'observer.observe(tbody, { childList: true, subtree: false })' in source
    assert "attributes: true" not in source
    assert "refreshColumnHeaderStates(frm, root)" in source


def test_table_performance_layer_loads_after_all_table_enhancement_layers():
    hooks = HOOKS.read_text(encoding="utf-8")
    performance = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js"'
    for dependency in (
        '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_bulk_rows_ux.js"',
        '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_keyboard_columns_ux.js"',
        '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_compact_measurements_ux.js"',
        '"public/js/door_cutting_order/drawing/special_shape_facade.js"',
        '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_resilience_ux.js"',
    ):
        assert dependency in hooks
        assert hooks.index(dependency) < hooks.index(performance)
    assert performance in hooks


def test_legacy_operator_is_the_only_source_with_full_table_renderer():
    # The performance layer deliberately avoids invoking the legacy renderer for
    # ordinary piece-type changes; the original renderer remains for initial load.
    assert "function renderFastMeasurements(frm)" in OPERATOR_UX.read_text(encoding="utf-8")
    assert "function renderFastMeasurements(frm)" not in _source()
