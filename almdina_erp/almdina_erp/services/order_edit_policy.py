from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.editability import (
    DRAFT_LIKE_STATUSES,
    LOCKED_ORDER_STATUSES,
    can_edit_order,
    can_recalculate_drawing_system_plan,
    is_before_cutting,
    is_draft_like as domain_is_draft_like,
    is_drawing_stage,
    is_locked_status as domain_is_locked_status,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)


def order_display_name(order: Any) -> str:
    if isinstance(order, dict):
        return str(order.get("name") or "")
    return str(getattr(order, "name", None) or "")


def order_status(order: Any) -> str:
    if isinstance(order, dict):
        return order.get("status") or "Draft"
    return getattr(order, "status", None) or "Draft"


def _value(order: Any, fieldname: str) -> Any:
    if isinstance(order, dict):
        return order.get(fieldname)
    return getattr(order, fieldname, None)


def _current_stage_type(order: Any) -> str | None:
    status = order_status(order)
    if status == "At Drawing":
        return "Drawing"

    stage_name = _value(order, "current_production_stage")
    if not stage_name:
        return None
    return frappe.db.get_value("Production Stage", stage_name, "stage_type")


def is_order_at_drawing_stage(order: Any) -> bool:
    return is_drawing_stage(
        production_path=_value(order, "production_path"),
        status=order_status(order),
        current_stage_type=_current_stage_type(order),
    )


def user_can_recalculate_drawing_system_plan(order: Any, user: str | None = None) -> bool:
    if not doctype_has_capability(Capability.RECALCULATE_PLAN, user=user):
        return False

    approved_plan = _value(order, "approved_plan")
    if approved_plan:
        return False

    return can_recalculate_drawing_system_plan(
        has_recalculate_permission=True,
        approved_plan=approved_plan,
        production_path=_value(order, "production_path"),
        status=order_status(order),
        current_stage_type=_current_stage_type(order),
    )


def is_draft_like(status: str | None) -> bool:
    return domain_is_draft_like(status)


def is_locked_status(status: str | None) -> bool:
    return domain_is_locked_status(status)


def _revision_state(order: Any) -> str:
    value = _value(order, "revision_state") or "Current"
    return str(value)


def user_can_edit_order(
    status: str | None = None,
    user: str | None = None,
    *,
    revision_state: str | None = None,
) -> bool:
    """Editors with ``edit_order`` may change the same document before cutting.

    Superseded revisions and orders that reached Sharyoun/CNC (or later) stay
    read-only. Draft-like statuses remain editable under normal write access.
    """

    if str(revision_state or "Current") == "Superseded":
        return False
    if not is_before_cutting(status):
        return False
    if is_draft_like(status):
        return can_edit_order(status, privileged=False)
    return can_edit_order(
        status,
        privileged=doctype_has_capability(Capability.EDIT_ORDER, user=user),
    )


def assert_order_editable(order: Any) -> None:
    status = order_status(order)
    if user_can_edit_order(status, revision_state=_revision_state(order)):
        return
    frappe.throw(
        _(
            "Order {0} cannot be edited after cutting has started, or in its current state."
        ).format(order_display_name(order))
    )


def enforce_order_immutability_on_save(order: Any, old: Any) -> None:
    if getattr(order, "is_new", lambda: False)() or order.flags.get("allow_approved_edit"):
        return
    if not old:
        return

    if user_can_edit_order(order_status(old), revision_state=_revision_state(old)):
        return

    if order.flags.get("force_cutting_plan_recalculation") and user_can_recalculate_drawing_system_plan(order):
        return

    assert_order_editable(old)
