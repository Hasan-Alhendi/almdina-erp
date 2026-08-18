from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_FLOOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_order_ux.js"
)


def source() -> str:
    return SHOP_FLOOR_UX.read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_worker_start_and_handoff_are_direct_toolbar_actions() -> None:
    text = source()
    worker = section(
        text,
        "function addWorkerStageButtons(frm) {",
        "function removeProductionButtons(frm) {",
    )
    start = section(
        worker,
        'if (stage.can_start_stage && stageStatus === "Pending"',
        'if (!stage.can_handoff_stage',
    )
    handoff = section(
        worker,
        'if (!stage.can_handoff_stage',
        '}).catch((error)',
    )

    assert 'frm.add_custom_button(__("بدء العمل")' in start
    assert "PRODUCTION_ACTION_GROUP" not in start
    assert 'frm.add_custom_button(__("إنهاء وإرسال")' in handoff
    assert "PRODUCTION_ACTION_GROUP" not in handoff


def test_direct_stage_actions_keep_existing_authorization_and_state_gates() -> None:
    text = source()
    worker = section(
        text,
        "function addWorkerStageButtons(frm) {",
        "function removeProductionButtons(frm) {",
    )

    for expected in (
        "if (!assignedToMe) return;",
        'stage.can_start_stage && stageStatus === "Pending"',
        'can(frm, "start_assigned_stage")',
        "stage.can_handoff_stage",
        '["In Progress", "Paused"].includes(stageStatus)',
        'can(frm, "handoff_assigned_stage")',
    ):
        assert expected in worker

    reassign = section(
        worker,
        "if (stage.can_reassign_worker",
        "if (!assignedToMe) return;",
    )
    assert "PRODUCTION_ACTION_GROUP" in reassign


def test_reconciliation_removes_direct_and_legacy_grouped_stage_actions() -> None:
    text = source()
    cleanup = section(
        text,
        "function removeProductionButtons(frm) {",
        "function reconcileProductionActions(frm) {",
    )

    assert 'frm.remove_custom_button(__("بدء العمل"));' in cleanup
    assert 'frm.remove_custom_button(__("إنهاء وإرسال"));' in cleanup
    assert 'frm.remove_custom_button(__(label), PRODUCTION_ACTION_GROUP)' in cleanup
