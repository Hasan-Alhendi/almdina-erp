from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.application.orders.lifecycle_permissions import (
    OrderLifecycleAction,
)
from almdina_erp.almdina_erp.domain.orders.cancellation_resume import (
    CancelledStageSnapshot,
    StageResumeFact,
    build_cancellation_snapshot,
    restore_cancelled_stage,
    select_resume_plan,
    snapshot_from_mapping,
    snapshot_to_mapping,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import normalize_order_status
from almdina_erp.almdina_erp.services.order_lifecycle_permission_service import (
    lifecycle_context_for_order,
    require_lifecycle_action,
)


def _cutting_stage(order_name: str) -> Any | None:
    name = frappe.db.get_value(
        "Production Stage",
        {
            "door_cutting_order": order_name,
            "stage_type": "Cutting",
            "piece_label": ["in", ["", None]],
        },
        "name",
    )
    return frappe.get_doc("Production Stage", name) if name else None


def _plan_status(plan_name: str | None) -> str | None:
    if not str(plan_name or "").strip():
        return None
    return frappe.db.get_value("Cutting Plan", plan_name, "status")


def _parse_snapshot(raw: Any):
    if not raw:
        return None
    if isinstance(raw, str):
        raw = frappe.parse_json(raw)
    return snapshot_from_mapping(raw)


def _cancel_stages(order_name: str, reason: str) -> list[str]:
    from almdina_erp.almdina_erp.infrastructure.frappe.production_event_repository import (
        log_event as _log_event,
    )

    stages = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name},
        pluck="name",
    )
    cancelled: list[str] = []
    for name in stages:
        stage = frappe.get_doc("Production Stage", name)
        if stage.status in {"Completed", "Cancelled"}:
            continue
        previous_status = stage.status
        stage.status = "Cancelled"
        stage.notes = (
            (stage.notes or "")
            + "\n"
            + _("Cancelled with order: {0}").format(reason)
        ).strip()
        stage.save(ignore_permissions=True)
        _log_event(
            stage,
            "Cancel",
            {"reason": reason, "previous_status": previous_status},
        )
        cancelled.append(name)
    return cancelled


def _cancel_unstarted_replacements(order_name: str, reason: str) -> list[str]:
    replacements = frappe.get_all(
        "Replacement Piece",
        filters={
            "door_cutting_order": order_name,
            "status": ["!=", "Cancelled"],
        },
        fields=["name", "status"],
    )

    physically_started = [
        row
        for row in replacements
        if row.status in {"In Progress", "Completed"}
    ]
    if physically_started:
        frappe.throw(
            _(
                "Order has replacement work already in progress or completed ({0}). "
                "Resolve that replacement before cancelling the order."
            ).format(", ".join(row.name for row in physically_started))
        )

    from almdina_erp.almdina_erp.services.replacement_execution import (
        cancel_replacement_for_order_cancellation,
    )

    cancelled: list[str] = []
    for row in replacements:
        if row.status in {"Pending Approval", "Approved"}:
            cancel_replacement_for_order_cancellation(
                row.name,
                reason=_("Order cancelled: {0}").format(reason),
            )
            cancelled.append(row.name)
    return cancelled


def _cancellation_snapshot_for(order: Any):
    rows = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order.name},
        fields=["name", "status", "stage_type", "department_label"],
    )
    return build_cancellation_snapshot(
        order_status=order.status,
        department_status=getattr(order, "department_status", None),
        current_production_stage=getattr(order, "current_production_stage", None),
        current_assignee=getattr(order, "current_assignee", None),
        current_department=getattr(order, "current_department", None),
        production_path=getattr(order, "production_path", None),
        approved_plan=getattr(order, "approved_plan", None),
        approved_plan_status=_plan_status(getattr(order, "approved_plan", None)),
        cancellable_stages=[
            CancelledStageSnapshot(
                name=row.name,
                previous_status=row.status,
                stage_type=row.stage_type,
                department_label=row.department_label,
            )
            for row in rows
            if row.status not in {"Completed", "Cancelled"}
        ],
    )


def _restore_cancelled_stages(plan) -> list[str]:
    from almdina_erp.almdina_erp.infrastructure.frappe.production_event_repository import (
        log_event as _log_event,
    )

    restored: list[str] = []
    for target in plan.stages:
        if not frappe.db.exists("Production Stage", target.name):
            continue
        stage = frappe.get_doc("Production Stage", target.name)
        if stage.status != "Cancelled":
            continue
        stage.status = restore_cancelled_stage(stage.status, target.target_status)
        stage.save(ignore_permissions=True)
        _log_event(
            stage,
            "Override",
            {"resumed": True, "target_status": stage.status},
        )
        restored.append(stage.name)
    return restored


def _restore_cancelled_plan(plan) -> None:
    if not plan.restore_plan or not plan.approved_plan:
        return
    cutting_plan = frappe.get_doc("Cutting Plan", plan.approved_plan)
    if cutting_plan.status != "Cancelled":
        return
    cutting_plan.flags.allow_status_transition = True
    cutting_plan.status = "Approved"
    cutting_plan.save(ignore_permissions=True)


@frappe.whitelist()
def cancel_order(
    order_name: str,
    reason: str,
    reverse_stock: int | bool = 0,
) -> dict[str, Any]:
    del reverse_stock

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_lifecycle_action(order, OrderLifecycleAction.CANCEL)

    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("Cancellation reason is required."))

    cutting = _cutting_stage(order.name)
    if cutting and cutting.status == "Completed":
        frappe.throw(
            _(
                "Cutting is already completed. A completed cutting operation "
                "cannot be cancelled automatically."
            )
        )

    snapshot = _cancellation_snapshot_for(order)
    cancelled_replacements = _cancel_unstarted_replacements(order.name, reason)
    cancelled_stages = _cancel_stages(order.name, reason)

    if order.approved_plan:
        plan = frappe.get_doc("Cutting Plan", order.approved_plan)
        if plan.status == "Approved":
            plan.flags.allow_status_transition = True
            plan.status = "Cancelled"
            plan.save(ignore_permissions=True)

    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        {
            "status": "Cancelled",
            "cancellation_snapshot": frappe.as_json(snapshot_to_mapping(snapshot)),
        },
        update_modified=True,
    )
    order.reload()
    order.add_comment(
        "Comment",
        text=_("Order cancelled by {0} on {1}. Reason: {2}").format(
            frappe.session.user,
            now_datetime(),
            reason,
        ),
    )

    return {
        "name": order.name,
        "status": "Cancelled",
        "cancelled_stages": cancelled_stages,
        "cancelled_replacements": cancelled_replacements,
        "lifecycle": lifecycle_context_for_order(order),
    }


@frappe.whitelist()
def resume_cancelled_order(
    order_name: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Restore a cancelled order to the production stage it was cancelled from."""

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_lifecycle_action(order, OrderLifecycleAction.RESUME_CANCELLED)
    del reason

    snapshot = _parse_snapshot(getattr(order, "cancellation_snapshot", None))
    rows = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order.name},
        fields=["name", "status", "sequence", "stage_type", "department_label"],
    )
    try:
        plan = select_resume_plan(
            snapshot,
            current_production_stage=getattr(order, "current_production_stage", None),
            stages=[
                StageResumeFact(
                    name=row.name,
                    status=row.status,
                    sequence=int(row.sequence or 0),
                    stage_type=row.stage_type,
                    department_label=row.department_label,
                )
                for row in rows
            ],
            approved_plan=getattr(order, "approved_plan", None),
            approved_plan_status=_plan_status(getattr(order, "approved_plan", None)),
        )
    except ValueError as exc:
        frappe.throw(_(str(exc)))
    restored_stages = _restore_cancelled_stages(plan)
    _restore_cancelled_plan(plan)

    updates: dict[str, Any] = {
        "status": plan.order_status,
        "cancellation_snapshot": None,
    }
    if plan.department_status is not None:
        updates["department_status"] = plan.department_status
    if snapshot is not None:
        if snapshot.current_production_stage:
            updates["current_production_stage"] = snapshot.current_production_stage
        if snapshot.current_assignee:
            updates["current_assignee"] = snapshot.current_assignee
        if snapshot.current_department:
            updates["current_department"] = snapshot.current_department
        if snapshot.production_path:
            updates["production_path"] = snapshot.production_path
        if snapshot.approved_plan and plan.restore_plan:
            updates["approved_plan"] = snapshot.approved_plan

    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        updates,
        update_modified=True,
    )
    order.reload()
    order.add_comment(
        "Comment",
        text=_("Order resumed by {0} on {1}.").format(
            frappe.session.user,
            now_datetime(),
        ),
    )
    return {
        "name": order.name,
        "status": plan.order_status,
        "restored_stages": restored_stages,
        "restored_plan": bool(plan.restore_plan and plan.approved_plan),
        "lifecycle": lifecycle_context_for_order(order),
    }


_IN_PLACE_DRAFT_FIELDS: dict[str, Any] = {
    "status": "Draft",
    "production_path": None,
    "current_department": None,
    "current_assignee": None,
    "department_status": None,
    "current_production_stage": None,
    "approved_plan": None,
    "approved_plan_source": "System",
    "production_dxf": None,
    "drawing_dxf_status": "None",
    "plan_needs_recalculation": 1,
    "cancellation_snapshot": None,
}


@frappe.whitelist()
def return_order_to_draft(
    order_name: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Reset the same order to Draft so it can be edited again.

    Cancels active production stages and clears the production route. Does not
    create a revision copy — the original document is the editable draft.
    """

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_lifecycle_action(order, OrderLifecycleAction.RETURN_TO_DRAFT)

    reason = str(reason or "").strip() or _(
        "Returned to draft for editing by {0}."
    ).format(frappe.session.user)

    # Already draft: capability was checked; nothing else to reset.
    if normalize_order_status(order.status) == "Draft" and not (
        order.production_path or order.current_production_stage
    ):
        return {
            "name": order.name,
            "status": order.status,
            "cancelled_stages": 0,
            "cancelled_replacements": 0,
            "in_place": True,
            "noop": True,
        }

    cancelled_replacements = _cancel_unstarted_replacements(order.name, reason)
    cancelled_stages = _cancel_stages(order.name, reason)

    if order.approved_plan:
        plan = frappe.get_doc("Cutting Plan", order.approved_plan)
        if plan.status == "Approved":
            plan.flags.allow_status_transition = True
            plan.status = "Cancelled"
            plan.save(ignore_permissions=True)

    for fieldname, value in _IN_PLACE_DRAFT_FIELDS.items():
        order.set(fieldname, value)
    order.flags.allow_status_transition = True
    order.flags.allow_approved_edit = True
    order.save(ignore_permissions=True)
    order.add_comment(
        "Comment",
        text=_("Order returned to draft by {0} on {1}. Reason: {2}").format(
            frappe.session.user,
            now_datetime(),
            reason,
        ),
    )

    return {
        "name": order.name,
        "status": order.status,
        "cancelled_stages": cancelled_stages,
        "cancelled_replacements": cancelled_replacements,
        "in_place": True,
    }
