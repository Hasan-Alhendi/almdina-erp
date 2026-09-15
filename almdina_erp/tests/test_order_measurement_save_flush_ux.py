from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
OPERATOR = PUBLIC / "order_entry" / "door_cutting_order_operator_ux.js"
REVISION = PUBLIC / "core" / "door_cutting_order_revision_ux.js"
PAGE_EDIT = PUBLIC / "core" / "door_cutting_order_page_edit_action_ux.js"
MEASUREMENT_ACTIONS = (
    PUBLIC / "order_entry" / "measurements" / "door_cutting_order_measurement_actions_ux.js"
)
FAST_SAVE = PUBLIC / "cutting_plan" / "door_cutting_order_fast_save_ux.js"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_explicit_save_flushes_open_measurement_cells_before_dirty_check() -> None:
    revision = _text(REVISION)
    operator = _text(OPERATOR)
    fast_save = _text(FAST_SAVE)

    assert "function flushMeasurementInputs(frm)" in operator
    assert "flush: flushMeasurementInputs" in operator
    assert "function flushPendingMeasurements(frm)" in revision
    assert "owner.flush(frm)" in revision

    explicit = revision.split("async function commitEditSession", 1)[1].split(
        "async function persistOrderEditCheckpoint", 1
    )[0]
    assert explicit.index("flushPendingMeasurements(frm);") < explicit.index(
        "if (documentIsDirty(frm))"
    )
    assert "Boolean(await commitEditSession(frm))" in revision
    assert "return !captureEditSessionPresence(frm);" in explicit
    assert "Frappe resolves frm.save() before after_save finishes" in explicit

    checkpoint = revision.split("async function persistOrderEditCheckpoint", 1)[1].split(
        "function confirmEditSession", 1
    )[0]
    assert checkpoint.index("flushPendingMeasurements(frm);") < checkpoint.index(
        "if (!documentIsDirty(frm)) return true;"
    )

    persist = fast_save.split("async function persistPendingOrderInputs", 1)[1].split(
        "function backgroundJob", 1
    )[0]
    assert "fastEntry.flush(frm)" in persist
    assert persist.index("fastEntry.flush(frm)") < persist.index("frm.is_dirty()")


def test_save_toolbar_keeps_the_same_button_node_while_saving() -> None:
    source = _text(PAGE_EDIT)

    assert "function bindToolbarActions(toolbar)" in source
    assert "function patchToolbarButtons(" in source
    assert 'toolbar.addEventListener("pointerdown"' in source
    assert 'toolbar.addEventListener("click"' in source
    assert "data-almdina-action-mode" in source
    assert "flushOrderSurfaces(frm)" in source
    assert "owner.flush(frm)" in source
    assert 'save.addEventListener("click"' not in source


def test_measurement_window_does_not_rebuild_save_on_every_keystroke() -> None:
    source = _text(MEASUREMENT_ACTIONS)

    assert "function inlineActionSignature(frm)" in source
    assert "host.dataset.almdinaInlineEdit === signature" in source
    assert 'overlay.addEventListener("pointerdown"' in source
    assert "flushOrderMeasurements(frm)" in source
    assert "state.saving = true" in source
    assert 'if (snapshot && snapshot.phase === "saving") return' in source


def test_measurement_table_is_not_replaced_while_order_save_is_in_flight() -> None:
    source = _text(OPERATOR)

    changed = source.split("almdina_edit_session_changed(frm)", 1)[1]
    assert 'editSessionPhase(frm) === "saving"' in changed
    assert "refreshOperatorUI(frm)" in changed
