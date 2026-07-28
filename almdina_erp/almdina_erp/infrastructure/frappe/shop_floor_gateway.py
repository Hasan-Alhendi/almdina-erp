from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_STAGE_TYPES,
    department_for_stage_type,
    department_status_for_stage_status,
    is_cutting_like_stage,
    order_status_for_stage_type,
)


STAGE_ROLE_BY_TYPE: dict[str, str] = {
    "Sharyoun": "عامل شريون",
    "Drawing": "عامل رسم",
    "CNC": "عامل CNC",
    "Sanding": "عامل تقشيط",
}

DISPATCH_ROLES = ("Order Entry", "Production Manager")
ADMIN_ROLES = ("Order Entry", "Production Manager", "System Manager")
STAGE_ADMIN_ROLES = frozenset({"Production Manager", "System Manager"})


def require_roles(*roles: str) -> None:
    user_roles = set(frappe.get_roles())
    if "System Manager" in user_roles:
        return
    if not user_roles.intersection(roles):
        frappe.throw(
            _("You do not have permission for this operation."),
            frappe.PermissionError,
        )


def get_order(order_name: str) -> Any:
    return frappe.get_doc("Door Cutting Order", order_name)


def get_stage(stage_name: str) -> Any:
    return frappe.get_doc("Production Stage", stage_name)


def get_order_path(order_name: str) -> str | None:
    return frappe.db.get_value("Door Cutting Order", order_name, "production_path")


def get_order_status(order_name: str) -> str | None:
    return frappe.db.get_value("Door Cutting Order", order_name, "status")


def stage_exists(stage_name: str | None) -> bool:
    return bool(stage_name and frappe.db.exists("Production Stage", stage_name))


def assert_enabled_user_has_stage_role(user: str, stage_type: str) -> None:
    role = STAGE_ROLE_BY_TYPE.get(stage_type)
    if not role:
        frappe.throw(_("Unsupported shop-floor stage: {0}").format(stage_type))
    if not user:
        frappe.throw(_("Select a worker."))
    if not frappe.db.exists("User", user) or not cint(
        frappe.db.get_value("User", user, "enabled")
    ):
        frappe.throw(_("User {0} is not an enabled system user.").format(user))
    user_roles = set(frappe.get_roles(user))
    if role not in user_roles and "System Manager" not in user_roles:
        frappe.throw(_("User {0} does not have role {1}.").format(user, role))


def require_stage_assignee_or_admin(stage: Any) -> None:
    roles = set(frappe.get_roles())
    if roles.intersection(STAGE_ADMIN_ROLES):
        return
    expected_role = STAGE_ROLE_BY_TYPE.get(stage.stage_type)
    if expected_role:
        require_roles(expected_role)
    if stage.assigned_to and stage.assigned_to != frappe.session.user:
        frappe.throw(_("This stage is assigned to another worker."))


def get_users_for_stage(stage_type: str) -> list[dict[str, str]]:
    role = STAGE_ROLE_BY_TYPE.get(stage_type)
    if not role:
        return []
    return get_users_for_role(role)


def get_users_for_role(role: str) -> list[dict[str, str]]:
    rows = frappe.db.sql(
        """
        select u.name, u.full_name
          from `tabUser` u
          inner join `tabHas Role` hr on hr.parent = u.name
         where hr.role = %s
           and u.enabled = 1
           and u.user_type = 'System User'
           and u.name not in ('Guest', 'Administrator')
         order by u.full_name asc
        """,
        (role,),
        as_dict=True,
    )
    return [
        {"name": row.name, "full_name": row.full_name or row.name}
        for row in rows
    ]


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
    log_event(
        stage,
        "Created",
        {"sequence": sequence, "assigned_to": assignee, "shop_floor": True},
    )
    return stage


def set_order_tracking(
    order_name: str,
    *,
    path: str | None = None,
    stage: Any | None = None,
    status: str | None = None,
    department: str | None = None,
    assignee: str | None = None,
    department_status: str | None = None,
    clear_stage: bool = False,
) -> None:
    values: dict[str, Any] = {}
    if path is not None:
        values["production_path"] = path
    if status is not None:
        values["status"] = status
    if department is not None:
        values["current_department"] = department
    if assignee is not None:
        values["current_assignee"] = assignee
    if department_status is not None:
        values["department_status"] = department_status
    if clear_stage:
        values["current_production_stage"] = None
    elif stage is not None:
        values["current_production_stage"] = stage.name
        values["current_department"] = department_for_stage_type(stage.stage_type)
        values["current_assignee"] = stage.assigned_to
        values["department_status"] = department_status_for_stage_status(
            stage.status
        )
        values["status"] = order_status_for_stage_type(stage.stage_type)
    if values:
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            values,
            update_modified=True,
        )


def log_event(
    stage: Any,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    event = frappe.new_doc("Production Stage Event")
    event.door_cutting_order = stage.door_cutting_order
    event.production_stage = stage.name
    event.stage_type = stage.stage_type
    event.event_type = event_type
    event.event_time = now_datetime()
    event.actor = frappe.session.user
    event.details_json = frappe.as_json(details or {})
    event.insert(ignore_permissions=True)


def required_piece_qty(order_name: str) -> int:
    rows = frappe.get_all(
        "Door Cutting Order Detail",
        filters={
            "parent": order_name,
            "parenttype": "Door Cutting Order",
        },
        fields=["qty"],
    )
    return sum(cint(row.qty) for row in rows)


def close_open_pause(stage: Any, resumed_by: str) -> None:
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
    stage.paused_seconds = sum(
        cint(row.duration_seconds) for row in (stage.pauses or [])
    )


def maybe_consume_stock(order_name: str, stage_type: str, trigger: str) -> None:
    if not is_cutting_like_stage(stage_type):
        return
    if not frappe.db.get_value("Door Cutting Order", order_name, "approved_plan"):
        return
    from almdina_erp.almdina_erp.services.stock_service import (
        consume_planned_material_if_due,
    )

    consume_planned_material_if_due(order_name, trigger=trigger)


def maybe_register_remnants(
    order_name: str,
    stage_type: str,
) -> dict[str, Any] | None:
    if not is_cutting_like_stage(stage_type):
        return None
    if not frappe.db.get_value("Door Cutting Order", order_name, "approved_plan"):
        return None
    from almdina_erp.almdina_erp.services.remnant_service import (
        register_plan_remnants,
    )

    return register_plan_remnants(order_name)


def get_revert_stage_candidates(
    order_name: str,
    stage_type: str,
) -> list[Any]:
    return frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "stage_type": stage_type,
        },
        fields=["name", "piece_label", "sequence"],
        order_by="sequence asc",
    )


def get_later_stages(order_name: str, sequence: int) -> list[Any]:
    return frappe.get_all(
        "Production Stage",
        filters={
            "door_cutting_order": order_name,
            "sequence": [">", sequence],
        },
        fields=["name", "piece_label"],
    )


__all__ = [
    "ADMIN_ROLES",
    "DISPATCH_ROLES",
    "STAGE_ROLE_BY_TYPE",
    "assert_enabled_user_has_stage_role",
    "cancel_non_shop_floor_active_stages",
    "close_open_pause",
    "create_stage",
    "get_later_stages",
    "get_order",
    "get_order_path",
    "get_order_status",
    "get_revert_stage_candidates",
    "get_stage",
    "get_users_for_role",
    "get_users_for_stage",
    "log_event",
    "maybe_consume_stock",
    "maybe_register_remnants",
    "require_roles",
    "require_stage_assignee_or_admin",
    "required_piece_qty",
    "set_order_tracking",
    "stage_exists",
]
