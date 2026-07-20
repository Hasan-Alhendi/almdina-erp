from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


DEFAULT_ROUTING = (
    (10, "Review / Preparation"),
    (20, "Cutting"),
    (30, "Edge Banding"),
)


def ensure_default_stages(order_name: str, approved_by: str | None = None) -> list[str]:
    existing = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name, "piece_label": ["in", ["", None]]},
        order_by="sequence asc",
        pluck="name",
    )
    if existing:
        return existing

    created: list[str] = []
    now = now_datetime()
    actor = approved_by or frappe.session.user

    for sequence, stage_type in DEFAULT_ROUTING:
        stage = frappe.new_doc("Production Stage")
        stage.door_cutting_order = order_name
        stage.sequence = sequence
        stage.stage_type = stage_type

        if stage_type == "Review / Preparation":
            stage.status = "Completed"
            stage.assigned_to = actor
            stage.started_by = actor
            stage.start_time = now
            stage.finished_by = actor
            stage.finish_time = now
            stage.actual_working_seconds = 0
        else:
            stage.status = "Pending"

        stage.insert(ignore_permissions=True)
        created.append(stage.name)

    return created


def _require_stage_role(stage: Any) -> None:
    if stage.stage_type == "Cutting":
        require_any_role("Cutting Operator", "Production Manager")
    elif stage.stage_type == "Edge Banding":
        require_any_role("Edge Operator", "Production Manager")
    else:
        require_any_role("Production Manager")


def _assert_previous_stages_completed(stage: Any) -> None:
    incomplete = frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": stage.door_cutting_order,
            "sequence": ["<", stage.sequence],
            "status": ["not in", ["Completed", "Cancelled"]],
            "piece_label": ["in", ["", None]],
        },
        fields=["name", "stage_type", "status"],
        order_by="sequence asc",
        limit=1,
    )
    if incomplete:
        row = incomplete[0]
        frappe.throw(
            _("Previous stage {0} ({1}) must be completed before starting this stage.").format(
                row.stage_type, row.status
            )
        )


def _close_open_pause(stage: Any, resumed_by: str) -> None:
    open_pause = None
    for row in reversed(stage.pauses or []):
        if row.pause_start and not row.pause_end:
            open_pause = row
            break

    if not open_pause:
        return

    open_pause.pause_end = now_datetime()
    open_pause.resumed_by = resumed_by
    open_pause.duration_seconds = max(
        0,
        cint(time_diff_in_seconds(open_pause.pause_end, open_pause.pause_start)),
    )
    stage.paused_seconds = sum(cint(row.duration_seconds) for row in (stage.pauses or []))


def _sync_order_status(order_name: str) -> str:
    stages = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name, "piece_label": ["in", ["", None]]},
        fields=["stage_type", "status", "sequence"],
        order_by="sequence asc",
    )
    if not stages:
        return frappe.db.get_value("Door Cutting Order", order_name, "status") or "Draft"

    if all(row.status in {"Completed", "Cancelled"} for row in stages):
        status = "Completed"
    else:
        active = next((row for row in stages if row.status in {"In Progress", "Paused"}), None)
        if active:
            if active.stage_type == "Cutting":
                status = "Cutting In Progress"
            elif active.stage_type == "Edge Banding":
                status = "Edge Banding In Progress"
            else:
                status = "Production In Progress"
        else:
            cutting = next((row for row in stages if row.stage_type == "Cutting"), None)
            edge = next((row for row in stages if row.stage_type == "Edge Banding"), None)
            if cutting and cutting.status == "Completed" and edge and edge.status == "Pending":
                status = "Cut Completed"
            else:
                status = "Approved"

    frappe.db.set_value("Door Cutting Order", order_name, "status", status, update_modified=True)
    return status


@frappe.whitelist()
def start_stage(stage_name: str, assigned_to: str | None = None) -> dict[str, Any]:
    stage = frappe.get_doc("Production Stage", stage_name)
    _require_stage_role(stage)
    if stage.status != "Pending":
        frappe.throw(_("Only a Pending stage can be started."))

    _assert_previous_stages_completed(stage)
    worker = assigned_to or stage.assigned_to or frappe.session.user
    stage.assigned_to = worker
    stage.started_by = frappe.session.user
    stage.start_time = now_datetime()
    stage.status = "In Progress"
    stage.save(ignore_permissions=True)
    order_status = _sync_order_status(stage.door_cutting_order)
    return {"stage": stage.name, "status": stage.status, "order_status": order_status}


@frappe.whitelist()
def pause_stage(stage_name: str, reason: str | None = None) -> dict[str, Any]:
    stage = frappe.get_doc("Production Stage", stage_name)
    _require_stage_role(stage)
    if stage.status != "In Progress":
        frappe.throw(_("Only an In Progress stage can be paused."))

    stage.append(
        "pauses",
        {
            "pause_start": now_datetime(),
            "reason": reason or "",
            "paused_by": frappe.session.user,
        },
    )
    stage.status = "Paused"
    stage.save(ignore_permissions=True)
    order_status = _sync_order_status(stage.door_cutting_order)
    return {"stage": stage.name, "status": stage.status, "order_status": order_status}


@frappe.whitelist()
def resume_stage(stage_name: str) -> dict[str, Any]:
    stage = frappe.get_doc("Production Stage", stage_name)
    _require_stage_role(stage)
    if stage.status != "Paused":
        frappe.throw(_("Only a Paused stage can be resumed."))

    _close_open_pause(stage, frappe.session.user)
    stage.status = "In Progress"
    stage.save(ignore_permissions=True)
    order_status = _sync_order_status(stage.door_cutting_order)
    return {"stage": stage.name, "status": stage.status, "order_status": order_status}


@frappe.whitelist()
def finish_stage(
    stage_name: str,
    completed_qty: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    stage = frappe.get_doc("Production Stage", stage_name)
    _require_stage_role(stage)
    if stage.status not in {"In Progress", "Paused"}:
        frappe.throw(_("Only an active stage can be finished."))

    if stage.status == "Paused":
        _close_open_pause(stage, frappe.session.user)

    finish_time = now_datetime()
    stage.finish_time = finish_time
    stage.finished_by = frappe.session.user
    stage.status = "Completed"
    if completed_qty is not None:
        stage.completed_qty = cint(completed_qty)
    if notes:
        stage.notes = notes

    total_seconds = max(0, cint(time_diff_in_seconds(finish_time, stage.start_time)))
    stage.actual_working_seconds = max(0, total_seconds - cint(stage.paused_seconds))
    stage.save(ignore_permissions=True)

    order_status = _sync_order_status(stage.door_cutting_order)
    return {
        "stage": stage.name,
        "status": stage.status,
        "order_status": order_status,
        "paused_seconds": stage.paused_seconds,
        "actual_working_seconds": stage.actual_working_seconds,
    }
