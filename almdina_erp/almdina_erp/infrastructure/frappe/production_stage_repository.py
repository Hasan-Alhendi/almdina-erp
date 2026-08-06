from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_write_guard import (
    authorize_internal_stage_write,
)
from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
    eligible_roles_display,
    encode_eligible_roles,
)


def get_stage(stage_name: str) -> Any:
    return frappe.get_doc("Production Stage", stage_name)


def stage_exists(stage_name: str | None) -> bool:
    return bool(stage_name and frappe.db.exists("Production Stage", stage_name))


def _lock_stage(stage_name: str) -> None:
    frappe.db.sql(
        "select name from `tabProduction Stage` where name = %s for update",
        (stage_name,),
    )


def _save_stage(stage: Any) -> Any:
    authorize_internal_stage_write(stage)
    stage.save(ignore_permissions=True)
    return stage


def _insert_stage(stage: Any) -> Any:
    authorize_internal_stage_write(stage)
    stage.insert(ignore_permissions=True)
    return stage


def cancel_active_order_stages(order_name: str) -> None:
    """Cancel stale order-wide stages before a fresh route is dispatched.

    Exceptional-piece stages are independent work items and must survive the
    order dispatch. Every other active stage is route work; no stage code is
    privileged here because routes are administrator-configurable.
    """

    rows = frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "status": ["in", ["Pending", "In Progress", "Paused"]],
        },
        fields=["name", "piece_label"],
        order_by="name asc",
    )
    for row in rows:
        if row.piece_label:
            continue
        _lock_stage(str(row.name))
        stage = get_stage(str(row.name))
        stage.status = "Cancelled"
        _save_stage(stage)


def create_stage(
    order_name: str,
    stage_type: str,
    assignee: str,
    sequence: int,
    *,
    department_label: str | None = None,
    operational_role: str | None = None,
    eligible_roles: Iterable[str] | str = (),
) -> Any:
    roles = decode_eligible_roles(
        eligible_roles,
        legacy_role=operational_role,
    )
    stage = frappe.new_doc("Production Stage")
    stage.door_cutting_order = order_name
    stage.sequence = sequence
    stage.stage_type = stage_type
    stage.department_label = department_label or stage_type
    stage.eligible_roles_json = encode_eligible_roles(roles)
    stage.eligible_roles_display = eligible_roles_display(roles)
    # The legacy Link is a compatibility snapshot only. Derive it from the
    # canonical role set so the three persisted fields can never disagree.
    stage.operational_role = roles[0] if roles else ""
    stage.status = "Pending"
    stage.assigned_to = assignee
    return _insert_stage(stage)


def reassign_stage(stage_name: str, *, assignee: str) -> Any:
    _lock_stage(stage_name)
    stage = get_stage(stage_name)
    stage.assigned_to = assignee
    return _save_stage(stage)


def close_open_pause(
    stage_or_name: Any,
    resumed_by: str,
    *,
    save: bool = True,
) -> Any:
    stage_name = (
        str(stage_or_name)
        if isinstance(stage_or_name, str)
        else str(stage_or_name.name)
    )
    _lock_stage(stage_name)
    stage = get_stage(stage_name)
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
        if save:
            _save_stage(stage)
    return stage


def start_stage(
    stage_name: str,
    *,
    actor: str,
    target_status: str,
) -> Any:
    _lock_stage(stage_name)
    stage = get_stage(stage_name)
    stage.started_by = actor
    stage.start_time = now_datetime()
    stage.status = target_status
    if not stage.assigned_to:
        stage.assigned_to = actor
    return _save_stage(stage)


def complete_stage(
    stage_name: str,
    *,
    actor: str,
    target_status: str,
    completed_qty: int,
) -> Any:
    _lock_stage(stage_name)
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
    return _save_stage(stage)


def list_revert_stage_candidates(order_name: str, stage_type: str) -> list[Any]:
    return frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "stage_type": stage_type,
        },
        fields=["name", "piece_label", "sequence"],
        order_by="sequence asc, name asc",
    )


def list_later_stages(order_name: str, sequence: int) -> list[Any]:
    return frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "sequence": [">", sequence],
        },
        fields=["name", "piece_label", "sequence"],
        order_by="sequence asc, name asc",
    )


def cancel_stage(stage_name: str, *, target_status: str) -> Any:
    _lock_stage(stage_name)
    stage = get_stage(stage_name)
    stage.status = target_status
    return _save_stage(stage)


def reopen_stage(stage_name: str, *, target_status: str) -> Any:
    _lock_stage(stage_name)
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
    return _save_stage(stage)


__all__ = [
    "cancel_active_order_stages",
    "cancel_stage",
    "close_open_pause",
    "complete_stage",
    "create_stage",
    "get_stage",
    "list_later_stages",
    "list_revert_stage_candidates",
    "reassign_stage",
    "reopen_stage",
    "stage_exists",
    "start_stage",
]
