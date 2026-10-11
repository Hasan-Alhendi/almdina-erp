from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.editability import (
    DRAFT_LIKE_STATUSES,
    LOCKED_ORDER_STATUSES,
    can_recalculate_drawing_system_plan,
    is_pre_dispatch_draft,
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

    return can_recalculate_drawing_system_plan(
        has_recalculate_permission=True,
        approved_plan=_value(order, "approved_plan"),
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
    current_production_stage: str | None = None,
) -> bool:
    """In-place edits are allowed only while the order is still a Draft.

    Superseded revisions stay read-only. Leaving Draft requires return-to-draft
    or a controlled revision — ``edit_order`` never unlocks production states.
    """

    del user
    if str(revision_state or "Current") == "Superseded":
        return False
    return is_pre_dispatch_draft(
        status=status,
        current_production_stage=current_production_stage,
    )


def assert_order_editable(order: Any) -> None:
    status = order_status(order)
    if user_can_edit_order(
        status,
        revision_state=_revision_state(order),
        current_production_stage=_value(order, "current_production_stage"),
    ):
        return
    frappe.throw(
        _(
            "يمكن تعديل الطلب {0} فقط وهو في حالة المسودة."
        ).format(order_display_name(order))
    )


def _is_return_to_draft_save(order: Any, old: Any) -> bool:
    """Accept only the cleared shape produced by the controlled reset action."""

    if not order.flags.get("allow_approved_edit"):
        return False
    cleared_fields = (
        "production_path",
        "current_department",
        "current_assignee",
        "department_status",
        "current_production_stage",
        "approved_plan",
    )
    return bool(
        order_status(order) == "Draft"
        and all(not _value(order, fieldname) for fieldname in cleared_fields)
        and user_can_edit_order(
            order_status(order),
            revision_state=_revision_state(order),
            current_production_stage=_value(order, "current_production_stage"),
        )
        and not user_can_edit_order(
            order_status(old),
            revision_state=_revision_state(old),
            current_production_stage=_value(old, "current_production_stage"),
        )
    )


def enforce_order_immutability_on_save(order: Any, old: Any) -> None:
    if getattr(order, "is_new", lambda: False)():
        return
    if not old:
        return

    old_is_editable = user_can_edit_order(
        order_status(old),
        revision_state=_revision_state(old),
        current_production_stage=_value(old, "current_production_stage"),
    )
    proposed_is_editable = user_can_edit_order(
        order_status(order),
        revision_state=_revision_state(order),
        current_production_stage=_value(order, "current_production_stage"),
    )

    if _is_return_to_draft_save(order, old):
        return

    if old_is_editable and proposed_is_editable:
        return

    if order.flags.get("force_cutting_plan_recalculation") and user_can_recalculate_drawing_system_plan(order):
        return

    if not proposed_is_editable:
        assert_order_editable(order)
    assert_order_editable(old)
