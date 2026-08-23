from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_ENTRY = ROOT / "public" / "js" / "door_cutting_order" / "order_entry"
MEASUREMENTS = ORDER_ENTRY / "measurements"
EDGE = ORDER_ENTRY / "edge_banding"
ASSETS = ROOT / "frontend_assets.py"

OPERATOR = ORDER_ENTRY / "door_cutting_order_operator_ux.js"
PATCH = ORDER_ENTRY / "door_cutting_order_operator_ux_patch.js"
FAST_KEYBOARD = MEASUREMENTS / "door_cutting_order_fast_entry_keyboard_ux.js"
EDGE_OWNER = EDGE / "door_cutting_order_edge_render_owner.js"
DOUBLE_CLICK_GUARD = EDGE / "door_cutting_order_edge_profile_double_click_guard.js"


def test_legacy_operator_patch_is_removed_from_runtime_and_repository():
    assets = ASSETS.read_text(encoding="utf-8")
    assert "door_cutting_order_operator_ux_patch.js" not in assets
    assert not PATCH.exists()


def test_fast_entry_keyboard_is_a_focused_qty_enter_owner():
    source = FAST_KEYBOARD.read_text(encoding="utf-8")
    assert 'input[data-field=\'qty\']' in source
    assert 'event.key !== "Enter"' in source
    assert "Math.max(1, Math.trunc" in source
    assert 'new Event("input", { bubbles: true })' in source
    assert 'frm.script_manager.trigger("qty"' in source
    assert "focusNextWidth(tr)" in source
    assert "MutationObserver" not in source
    assert "dco-special-edge-visual-guard-css" not in source


def test_operator_remains_the_single_click_toggle_owner():
    source = OPERATOR.read_text(encoding="utf-8")
    assert 'root.addEventListener("click"' in source
    assert '.dco-check-toggle[data-check-field]' in source
    assert "toggleCheck(currentFrm, check)" in source
    assert "function toggleCheck(frm, button)" in source


def test_double_click_guard_still_replays_single_click_to_operator():
    source = DOUBLE_CLICK_GUARD.read_text(encoding="utf-8")
    assert "const CLICK_DELAY_MS = 260" in source
    assert "replayingSingleClick = true" in source
    assert "toggle.click()" in source
    assert "scheduleSingleClick(target.toggle)" in source
    assert "controls.openSidePopover" in source


def test_edge_render_owner_owns_structural_refresh_and_disconnects_legacy_observers():
    source = EDGE_OWNER.read_text(encoding="utf-8")
    assert "const LEGACY_OBSERVER_KEYS = Object.freeze" in source
    assert '"_dcoSideEdgeObserver"' in source
    assert '"_dcoCompactEdgeProfileControlsObserver"' in source
    assert "observer.disconnect()" in source
    assert "function structuralMeasurementMutation(mutation)" in source
    assert "new MutationObserver" in source
    assert "mutations.some(structuralMeasurementMutation)" in source
    assert "AlmdinaMeasurementLifecycle" in source
    assert "AlmdinaDocumentContext" in source
    assert "toggleButtonImmediately" not in source
    assert "CHECK_FIELDS" not in source


def test_asset_order_keeps_dependencies_and_owners_explicit():
    source = ASSETS.read_text(encoding="utf-8")
    operator = '"public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"'
    keyboard = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js"'
    lifecycle = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js"'
    multi_edge = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"'
    controls = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js"'
    guard = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js"'
    owner = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js"'
    cut_dimensions = '"public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js"'

    for asset in (operator, keyboard, lifecycle, multi_edge, controls, guard, owner, cut_dimensions):
        assert asset in source
    assert source.index(operator) < source.index(keyboard) < source.index(lifecycle)
    assert source.index(multi_edge) < source.index(controls) < source.index(guard) < source.index(owner)
    assert source.index(owner) < source.index(cut_dimensions)
