from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_STAGE_TYPES,
    can_dispatch_from_status,
    can_mark_delivered,
    can_return_to_draft,
    can_revert_department,
    first_stage_type,
    next_stage_type,
    order_status_for_stage_type,
    production_path_sequence,
    resolve_shop_floor_stage_type,
    stage_sequence,
    transition_stage,
)
from almdina_erp.almdina_erp.services import shop_floor_service as legacy


def _throw_transition(message: str) -> None:
    frappe.throw(_(message))


def _transition(current_status: str, event: str, message: str) -> str:
    try:
        return transition_stage(current_status, event)
    except ValueError:
        _throw_transition(message)
    raise AssertionError("frappe.throw must interrupt execution")


def _next_stage(path: str, stage_type: str) -> str | None:
    try:
        return next_stage_type(path, stage_type)
    except ValueError:
        frappe.throw(_("Stage {0} is not part of path {1}.").format(stage_type, path))
    raise AssertionError("frappe.throw must interrupt execution")


def _path(path: str) -> tuple[str, ...]:
    try:
        return production_path_sequence(path)
    except ValueError:
        frappe.throw(_("Invalid production path: {0}").format(path))
    raise AssertionError("frappe.throw must interrupt execution")


def assert_order_ready_for_dispatch(order: Any) -> None:
    if legacy.is_order_dispatched(
        production_path=order.production_path,
        current_stage=order.current_production_stage,
    ):
        frappe.throw(_("Order {0} is already dispatched.").format(order.name))
    if not can_dispatch_from_status(order.status):
        frappe.throw(_("Only draft or rejected orders can be sent to production."))
    if not order.cutting_plan_json:
        frappe.throw(_("Calculate a cutting plan before sending the order to production."))
    if cint(order.plan_needs_recalculation):
        frappe.throw(_("Recalculate the cutting plan before sending the order to production."))
    order.ensure_special_shapes_documented()


@frappe.whitelist()
def get_handoff_workers(stage_name: str) -> list[dict[str, str]]:
    stage = frappe.get_doc("Production Stage", stage_name)
    legacy._require_stage_assignee_or_admin(stage)
    order_path = frappe.db.get_value("Door Cutting Order", stage.door_cutting_order, "production_path")
    next_type = _next_stage(order_path, stage.stage_type)
    if not next_type:
        return []
    return legacy.get_users_for_role(legacy.STAGE_ROLE[next_type])


@frappe.whitelist()
def dispatch_order(order_name: str, path: str, assignee: str) -> dict[str, Any]:
    legacy.require_any_role(*legacy.DISPATCH_ROLES)
    order = frappe.get_doc("Door Cutting Order", order_name)
    assert_order_ready_for_dispatch(order)

    sequence = _path(path)
    first_type = first_stage_type(path)
    legacy._assert_user_has_role(assignee, legacy.STAGE_ROLE[first_type])

    legacy_stages = frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "status": ["in", ["Pending", "In Progress", "Paused"]],
        },
        fields=["name", "piece_label", "stage_type"],
    )
    for row in legacy_stages:
        if row.piece_label or row.stage_type in SHOP_FLOOR_STAGE_TYPES:
            continue
        frappe.db.set_value("Production Stage", row.name, "status", "Cancelled", update_modified=True)

    stage = legacy._create_stage(order_name, first_type, assignee, stage_sequence(path, first_type))
    legacy._set_order_tracking(order_name, path=path, stage=stage)
    legacy._log_event(stage, "Created", {"path": path, "assignee": assignee, "shop_floor_dispatch": True})

    return {
        "name": order_name,
        "production_path": path,
        "stage": stage.name,
        "status": order_status_for_stage_type(first_type),
        "current_assignee": assignee,
        "department_status": "بحاجة للعمل",
        "path_sequence": sequence,
    }


@frappe.whitelist()
def start_my_stage(stage_name: str) -> dict[str, Any]:
    stage = frappe.get_doc("Production Stage", stage_name)
    legacy._require_stage_assignee_or_admin(stage)
    target_status = _transition(
        stage.status,
        "start",
        "Only a stage that needs work can be started.",
    )

    legacy._maybe_consume_stock(stage.door_cutting_order, stage.stage_type, "Cutting Start")

    stage.started_by = frappe.session.user
    stage.start_time = now_datetime()
    stage.status = target_status
    if not stage.assigned_to:
        stage.assigned_to = frappe.session.user
    stage.save(ignore_permissions=True)
    legacy._log_event(stage, "Start", {"assigned_to": stage.assigned_to, "shop_floor": True})
    legacy._set_order_tracking(stage.door_cutting_order, stage=stage)
    return {
        "stage": stage.name,
        "status": stage.status,
        "order_status": frappe.db.get_value("Door Cutting Order", stage.door_cutting_order, "status"),
        "department_status": "قيد العمل",
    }


@frappe.whitelist()
def handoff_to_next(stage_name: str, next_assignee: str | None = None) -> dict[str, Any]:
    stage = frappe.get_doc("Production Stage", stage_name)
    legacy._require_stage_assignee_or_admin(stage)
    target_status = _transition(
        stage.status,
        "finish",
        "Start the stage before sending it to the next department.",
    )

    order = frappe.get_doc("Door Cutting Order", stage.door_cutting_order)
    path = order.production_path
    if not path:
        frappe.throw(_("Order has no production path."))

    if stage.stage_type == "Drawing" and (order.drawing_dxf_status or "None") != "Approved by Drawing":
        frappe.throw(_("Approve the production DXF before sending the order to CNC."))

    next_type = _next_stage(path, stage.stage_type)

    if stage.status == "Paused":
        from almdina_erp.almdina_erp.services.production_service import _close_open_pause

        _close_open_pause(stage, frappe.session.user)

    finish_time = now_datetime()
    stage.finish_time = finish_time
    stage.finished_by = frappe.session.user
    stage.status = target_status
    stage.completed_qty = legacy._required_piece_qty(stage.door_cutting_order)
    if stage.start_time:
        total_seconds = max(0, cint(time_diff_in_seconds(finish_time, stage.start_time)))
        stage.actual_working_seconds = max(0, total_seconds - cint(stage.paused_seconds))
    stage.save(ignore_permissions=True)

    remnants = legacy._maybe_register_remnants(stage.door_cutting_order, stage.stage_type)
    legacy._maybe_consume_stock(stage.door_cutting_order, stage.stage_type, "Cutting Finish")
    legacy._log_event(
        stage,
        "Finish",
        {"shop_floor": True, "handoff": True, "next_stage_type": next_type, "remnants": remnants or {}},
    )

    if not next_type:
        legacy._set_order_tracking(
            stage.door_cutting_order,
            status="Ready for Delivery",
            department="جاهز للتسليم",
            assignee="",
            department_status="مكتمل",
            clear_stage=True,
        )
        return {
            "stage": stage.name,
            "status": target_status,
            "order_status": "Ready for Delivery",
            "ready_for_delivery": True,
        }

    if not next_assignee:
        frappe.throw(_("Select the next worker."))
    legacy._assert_user_has_role(next_assignee, legacy.STAGE_ROLE[next_type])

    next_stage = legacy._create_stage(
        stage.door_cutting_order,
        next_type,
        next_assignee,
        stage_sequence(path, next_type),
    )
    legacy._set_order_tracking(stage.door_cutting_order, stage=next_stage)
    legacy._log_event(
        next_stage,
        "Created",
        {"from_stage": stage.name, "assignee": next_assignee, "shop_floor_handoff": True},
    )

    return {
        "stage": stage.name,
        "status": target_status,
        "next_stage": next_stage.name,
        "next_stage_type": next_type,
        "order_status": order_status_for_stage_type(next_type),
        "ready_for_delivery": False,
    }


@frappe.whitelist()
def mark_delivered(order_name: str) -> dict[str, Any]:
    legacy.require_any_role(*legacy.ADMIN_ROLES)
    status = frappe.db.get_value("Door Cutting Order", order_name, "status")
    if not can_mark_delivered(status):
        frappe.throw(_("Only orders ready for delivery can be marked as delivered."))
    legacy._set_order_tracking(
        order_name,
        status="Delivered",
        department="تم التسليم",
        assignee="",
        department_status="مكتمل",
        clear_stage=True,
    )
    return {"name": order_name, "status": "Delivered"}


@frappe.whitelist()
def revert_department(
    order_name: str,
    target_stage: str | None = None,
    target_stage_type: str | None = None,
) -> dict[str, Any]:
    legacy.require_any_role("Production Manager", "System Manager", "Order Entry")
    order = frappe.get_doc("Door Cutting Order", order_name)
    if order.status == "Delivered":
        frappe.throw(_("Delivered orders cannot be reverted."))
    if not can_revert_department(order.status, production_path=order.production_path):
        frappe.throw(_("Order is not on the shop-floor path."))

    raw_target = target_stage_type or target_stage
    try:
        stage_type = resolve_shop_floor_stage_type(raw_target)
    except ValueError:
        frappe.throw(_("Select a stage to revert to."))

    candidates = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name, "stage_type": stage_type},
        fields=["name", "piece_label", "sequence"],
        order_by="sequence asc",
    )
    stage_name = next((row.name for row in candidates if not row.piece_label), None)
    if not stage_name and target_stage and frappe.db.exists("Production Stage", target_stage):
        stage_name = target_stage
    if not stage_name:
        frappe.throw(_("No shop-floor stage found for {0}.").format(_(stage_type or target_stage or "")))

    stage = frappe.get_doc("Production Stage", stage_name)
    if stage.door_cutting_order != order_name:
        frappe.throw(_("Stage does not belong to this order."))
    if stage.stage_type not in SHOP_FLOOR_STAGE_TYPES:
        frappe.throw(_("Only shop-floor stages can be reverted to."))

    later = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name, "sequence": [">", stage.sequence]},
        fields=["name", "piece_label"],
    )
    for row in later:
        if row.piece_label:
            continue
        doc = frappe.get_doc("Production Stage", row.name)
        doc.status = transition_stage(doc.status, "cancel")
        doc.save(ignore_permissions=True)
        legacy._log_event(doc, "Cancel", {"reason": "Reverted to earlier stage", "target": stage.stage_type})

    stage.status = transition_stage(stage.status, "reopen")
    stage.started_by = None
    stage.start_time = None
    stage.finished_by = None
    stage.finish_time = None
    stage.actual_working_seconds = 0
    stage.paused_seconds = 0
    stage.completed_qty = 0
    stage.pauses = []
    stage.save(ignore_permissions=True)
    legacy._log_event(stage, "Override", {"reopened": True, "shop_floor_revert": True})
    legacy._set_order_tracking(order_name, stage=stage)

    return {
        "name": order_name,
        "stage": stage.name,
        "stage_type": stage.stage_type,
        "status": order_status_for_stage_type(stage.stage_type),
        "department_status": "بحاجة للعمل",
    }


@frappe.whitelist()
def return_order_to_draft(order_name: str) -> dict[str, Any]:
    legacy.require_any_role(*legacy.DISPATCH_ROLES)
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("write")
    if order.status in {"Draft", "Rejected"}:
        frappe.throw(_("Order is already editable as a draft."))
    if not can_return_to_draft(order.status):
        frappe.throw(_("Delivered or cancelled orders cannot return to draft."))

    stages = frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "status": ["in", ["Pending", "In Progress", "Paused", "Completed"]],
            "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
        },
        fields=["name", "piece_label"],
    )
    for row in stages:
        if row.piece_label:
            continue
        doc = frappe.get_doc("Production Stage", row.name)
        doc.status = transition_stage(doc.status, "cancel")
        doc.save(ignore_permissions=True)
        legacy._log_event(doc, "Cancel", {"reason": "Returned to draft", "shop_floor": True})

    frappe.db.set_value(
        "Door Cutting Order",
        order_name,
        {
            "status": "Draft",
            "approved_plan": None,
            "production_path": None,
            "current_department": None,
            "current_assignee": None,
            "department_status": None,
            "current_production_stage": None,
            "drawing_dxf_status": "None",
            "production_dxf": None,
        },
        update_modified=True,
    )
    return {"name": order_name, "status": "Draft"}
