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
        "if (canShowStartAction(frm, stage)) {",
        "if (!canShowHandoffAction(frm, stage)) return;",
    )
    handoff = section(
        worker,
        "if (!canShowHandoffAction(frm, stage)) return;",
        "}).catch((error)",
    )

    assert 'frm.add_custom_button(__("بدء العمل")' in start
    assert "PRODUCTION_ACTION_GROUP" not in start
    assert 'frm.add_custom_button(__("إنهاء وإرسال")' in handoff
    assert "PRODUCTION_ACTION_GROUP" not in handoff


def test_direct_stage_actions_keep_existing_authorization_and_state_gates() -> None:
    text = source()
    start_helper = section(
        text,
        "function canShowStartAction(frm, stage) {",
        "function canShowHandoffAction(frm, stage) {",
    )
    handoff_condition = section(
        section(
            text,
            "function canShowHandoffAction(frm, stage) {",
            "function isShopFloorProfile(frm) {",
        ),
        "return Boolean(",
        ");",
    )
    worker = section(
        text,
        "function addWorkerStageButtons(frm) {",
        "function removeProductionButtons(frm) {",
    )
    expected = section(
        text,
        "function expectedProductionActionLabels(frm) {",
        "function productionActionsReady(frm) {",
    )

    assert "assignedToCurrentUser(stage)" in start_helper
    assert 'stage.active_stage_status === "Pending"' in start_helper
    assert 'can(frm, "start_assigned_stage")' in start_helper
    assert "stage.can_start_stage" in start_helper

    assert "assignedToCurrentUser(stage)" in handoff_condition
    assert "stage.can_handoff_stage" in handoff_condition
    assert 'can(frm, "handoff_assigned_stage")' in handoff_condition
    assert "active_stage_status" not in handoff_condition
    assert "In Progress" not in handoff_condition
    assert "Paused" not in handoff_condition
    assert "Pending" not in handoff_condition

    assert "if (!assignedToCurrentUser(stage)) return;" in worker
    assert "if (canShowStartAction(frm, stage))" in worker
    assert "if (!canShowHandoffAction(frm, stage)) return;" in worker
    assert "if (canShowStartAction(frm, stage))" in expected
    assert "if (canShowHandoffAction(frm, stage))" in expected
    assert '["In Progress", "Paused"].includes(stageStatus)' not in worker
    assert '["In Progress", "Paused"].includes(stageStatus)' not in expected

    reassign = section(
        worker,
        "if (stage.can_reassign_worker",
        "if (!assignedToCurrentUser(stage)) return;",
    )
    assert "PRODUCTION_ACTION_GROUP" in reassign


def test_handoff_visibility_trusts_server_flag_without_local_status_whitelist() -> None:
    text = source()
    condition = section(
        section(
            text,
            "function canShowHandoffAction(frm, stage) {",
            "function isShopFloorProfile(frm) {",
        ),
        "return Boolean(",
        ");",
    )

    assert "stage.can_handoff_stage" in condition
    assert 'can(frm, "handoff_assigned_stage")' in condition
    assert "assignedToCurrentUser(stage)" in condition
    assert "active_stage_status" not in condition
    assert "In Progress" not in condition
    assert "Paused" not in condition
    assert "Pending" not in condition


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
