from __future__ import annotations

from typing import Any

import frappe
from frappe import _


DRAFT_LIKE_STATUSES = {"Draft", "Pending Review", "Rejected"}
LOCKED_ORDER_STATUSES = {"Delivered", "Cancelled"}
ORDER_EDITOR_ROLES = {"Order Entry", "Production Manager", "System Manager"}
DRAWING_OPERATOR_ROLES = {"عامل رسم", "Production Manager", "System Manager"}


def order_display_name(order: Any) -> str:
    if isinstance(order, dict):
        return str(order.get("name") or "")
    return str(getattr(order, "name", None) or "")


def order_status(order: Any) -> str:
    if isinstance(order, dict):
        return order.get("status") or "Draft"
    return getattr(order, "status", None) or "Draft"


def user_has_drawing_operator_role(user: str | None = None) -> bool:
    roles = set(frappe.get_roles(user)) if user else set(frappe.get_roles())
    return bool(roles.intersection(DRAWING_OPERATOR_ROLES))


def is_order_at_drawing_stage(order: Any) -> bool:
    production_path = (
        getattr(order, "production_path", None)
        if not isinstance(order, dict)
        else order.get("production_path")
    )
    if production_path != "Drawing":
        return False
    status = order_status(order)
    if status == "At Drawing":
        return True
    stage_name = (
        getattr(order, "current_production_stage", None)
        if not isinstance(order, dict)
        else order.get("current_production_stage")
    )
    if not stage_name:
        return False
    stage_type = frappe.db.get_value("Production Stage", stage_name, "stage_type")
    return stage_type == "Drawing"


def user_can_recalculate_drawing_system_plan(order: Any, user: str | None = None) -> bool:
    if not user_has_drawing_operator_role(user):
        return False
    if getattr(order, "approved_plan", None) or (
        isinstance(order, dict) and order.get("approved_plan")
    ):
        return False
    return is_order_at_drawing_stage(order)


def user_has_order_editor_role(user: str | None = None) -> bool:
    roles = set(frappe.get_roles(user)) if user else set(frappe.get_roles())
    return bool(roles.intersection(ORDER_EDITOR_ROLES))


def is_draft_like(status: str | None) -> bool:
    return (status or "Draft") in DRAFT_LIKE_STATUSES


def is_locked_status(status: str | None) -> bool:
    return (status or "") in LOCKED_ORDER_STATUSES


def user_can_edit_order(status: str | None = None, user: str | None = None) -> bool:
    """Order Entry / Production Manager may keep editing after dispatch."""
    if is_locked_status(status):
        return False
    if is_draft_like(status):
        return True
    return user_has_order_editor_role(user)


def assert_order_editable(order: Any) -> None:
    status = order_status(order)
    if user_can_edit_order(status):
        return
    frappe.throw(
        _(
            "Order {0} is already approved or in production and cannot be edited/recalculated in place. "
            "Create a controlled revision instead."
        ).format(order_display_name(order)),
    )


def enforce_order_immutability_on_save(order: Any, old: Any) -> None:
    if getattr(order, "is_new", lambda: False)() or order.flags.get("allow_approved_edit"):
        return
    if not old:
        return

    if user_can_edit_order(order_status(old)):
        unlock_frozen_plan_for_editor(order)
        return

    if order.flags.get("force_cutting_plan_recalculation") and user_can_recalculate_drawing_system_plan(order):
        return

    assert_order_editable(order)


def unlock_frozen_plan_for_editor(order: Any) -> None:
    """Clear the immutable plan link so Order Entry edits remain the live source."""
    if not getattr(order, "approved_plan", None):
        return
    if is_draft_like(getattr(order, "status", None)):
        return
    if not user_has_order_editor_role():
        return
    order.approved_plan = None
