from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.domain.orders.lifecycle import SHOP_FLOOR_STAGE_TYPES


def get_stage(stage_name: str) -> Any:
    return frappe.get_doc("Production Stage", stage_name)


def stage_exists(stage_name: str | None) -> bool:
    return bool(stage_name and frappe.db.exists("Production Stage", stage_name))


def cancel_non_shop_floor_active_stages(order_name: str) -> None:
    rows = frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "status": ["in", ["Pending", "In Progress", "Paused"]],
        },
        fields=["name", "piece_label", "stage_type"],
    )
    for row in rows:
        if row.piece_label or row.stage_type in SHOP_FLOOR_STAGE_TYPES:
            continue
        frappe.db.set_value(
            "Production Stage",
            row.name,
            "status",
            "Cancelled",
            update_modified=True,
        )


def create_stage(
    order_name: str,
    stage_type: str,
    assignee: str,
    sequence: int,
) -> Any:
    stage = frappe.new_doc("Production Stage")
    stage.door_cutting_order = order_name
    stage.sequence = sequence
    stage.stage_type = stage_type
    stage.status = "Pending"
    stage.assigned_to = assignee
    stage.insert(ignore_permissions=True)
    return stage


def close_open_pause(stage_or_name: Any, resumed_by: str) -> Any:
    stage = (
        get_stage(stage_or_name)
        if isinstance(stage_or_name, str)
        else stage_or_name
    )
    open_pause = None
    for row in reversed(stage.pauses or []):
        if row.pause_start and not row.pause_end:
            open_pause = row
            break
    if open_pause:
        open_pause.pause_end = now_datetime()
        open_pause.resumed_by = resumed_by
        open_pause.duration_seconds = max(
            0,
            cint(time_diff_in_seconds(open_pause.pause_end, open_pause.pause_start)),
        )
        stage.paused_seconds = sum(
            cint(row.duration_seconds) for row in (stage.pauses or [])
        )
        stage.save(ignore_permissions=True)
    return stage


def start_stage(
    stage_name: str,
    *,
    actor: str,
    target_status: str,
) -> Any:
    stage = get_stage(stage_name)
    stage.started_by = actor
    stage.start_time = now_datetime()
    stage.status = target_status
    if not stage.assigned_to:
        stage.assigned_to = actor
    stage.save(ignore_permissions=True)
    return stage


def complete_stage(
    stage_name: str,
    *,
    actor: str,
    target_status: str,
    completed_qty: int,
) -> Any:
    stage = get_stage(stage_name)
    finish_time = now_datetime()
    stage.finish_time = finish_time
    stage.finished_by = actor
    stage.status = target_status
    stage.completed_qty = completed_qty
    if stage.start_time:
        total_seconds = max(
            0,
            cint(time_diff_in_seconds(finish_time, stage.start_time)),
        )
        stage.actual_working_seconds = max(
            0,
            total_seconds - cint(stage.paused_seconds),
        )
    stage.save(ignore_permissions=True)
    return stage


def list_revert_stage_candidates(order_name: str, stage_type: str) -> list[Any]:
    return frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "stage_type": stage_type,
        },
        fields=["name", "piece_label", "sequence"],
        order_by="sequence asc",
    )


def list_later_stages(order_name: str, sequence: int) -> list[Any]:
    return frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "sequence": [">", sequence],
        },
        fields=["name", "piece_label"],
    )


def cancel_stage(stage_name: str, *, target_status: str) -> Any:
    stage = get_stage(stage_name)
    stage.status = target_status
    stage.save(ignore_permissions=True)
    return stage


def reopen_stage(stage_name: str, *, target_status: str) -> Any:
    stage = get_stage(stage_name)
    stage.status = target_status
    stage.started_by = None
    stage.start_time = None
    stage.finished_by = None
    stage.finish_time = None
    stage.actual_working_seconds = 0
    stage.paused_seconds = 0
    stage.completed_qty = 0
    stage.pauses = []
    stage.save(ignore_permissions=True)
    return stage


__all__ = [
    "cancel_non_shop_floor_active_stages",
    "cancel_stage",
    "close_open_pause",
    "complete_stage",
    "create_stage",
    "get_stage",
    "list_later_stages",
    "list_revert_stage_candidates",
    "reopen_stage",
    "stage_exists",
    "start_stage",
]
