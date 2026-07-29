from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.editability import (
    DRAFT_LIKE_STATUSES,
    DRAWING_OPERATOR_ROLES,
    LOCKED_ORDER_STATUSES,
    ORDER_EDITOR_ROLES,
    can_edit_order,
    can_recalculate_drawing_system_plan,
    has_any_role,
    is_draft_like as domain_is_draft_like,
    is_drawing_stage,
    is_locked_status as domain_is_locked_status,
)


def order_display_name(order: Any) -> str:
    if isinstance(order, dict):
        return str(order.get("name") or "")
    return str(getattr(order, "name", None) or "")


def order_status(order: Any) -> str:
    if isinstance(order, dict):
        return order.get("status") or "Draft"
    return getattr(order, "status", None) or "Draft"


def _roles_for_user(user: str | None = None) -> set[str]:
    return set(frappe.get_roles(user)) if user else set(frappe.get_roles())


def _value(order: Any, fieldname: str) -> Any:
    if isinstance(order, dict):
        return order.get(fieldname)
    return getattr(order, fieldname, None)


def _current_stage_type(order: Any) -> str | None:
    production_path = _value(order, "production_path")
    status = order_status(order)
    if production_path != "Drawing" or status == "At Drawing":
        return None

    stage_name = _value(order, "current_production_stage")
    if not stage_name:
        return None
    return frappe.db.get_value("Production Stage", stage_name, "stage_type")


def user_has_drawing_operator_role(user: str | None = None) -> bool:
    return has_any_role(_roles_for_user(user), DRAWING_OPERATOR_ROLES)


def is_order_at_drawing_stage(order: Any) -> bool:
    return is_drawing_stage(
        production_path=_value(order, "production_path"),
        status=order_status(order),
        current_stage_type=_current_stage_type(order),
    )


def user_can_recalculate_drawing_system_plan(order: Any, user: str | None = None) -> bool:
    roles = _roles_for_user(user)
    if not has_any_role(roles, DRAWING_OPERATOR_ROLES):
        return False

    approved_plan = _value(order, "approved_plan")
    if approved_plan:
        return False

    return can_recalculate_drawing_system_plan(
        roles=roles,
        approved_plan=approved_plan,
        production_path=_value(order, "production_path"),
        status=order_status(order),
        current_stage_type=_current_stage_type(order),
    )


def user_has_order_editor_role(user: str | None = None) -> bool:
    return has_any_role(_roles_for_user(user), ORDER_EDITOR_ROLES)


def is_draft_like(status: str | None) -> bool:
    return domain_is_draft_like(status)


def is_locked_status(status: str | None) -> bool:
    return domain_is_locked_status(status)


def user_can_edit_order(status: str | None = None, user: str | None = None) -> bool:
    """Only draft-like orders are editable; roles do not unlock approved history."""

    del user
    return can_edit_order(status)


def assert_order_editable(order: Any) -> None:
    status = order_status(order)
    if user_can_edit_order(status):
        return
    frappe.throw(
        _(
            "Order {0} is already approved or in production and cannot be edited/recalculated in place. "
            "Create a controlled revision instead."
        ).format(order_display_name(order))
    )


def enforce_order_immutability_on_save(order: Any, old: Any) -> None:
    if getattr(order, "is_new", lambda: False)() or order.flags.get("allow_approved_edit"):
        return
    if not old:
        return

    if user_can_edit_order(order_status(old)):
        return

    if order.flags.get("force_cutting_plan_recalculation") and user_can_recalculate_drawing_system_plan(order):
        return

    assert_order_editable(order)
