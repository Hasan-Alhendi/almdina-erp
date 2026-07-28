from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.revisions import (
    RevisionNotAllowed,
    RevisionState,
    assert_revision_allowed,
    next_revision,
    revision_root,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability, has_capability


RESET_FIELDS: dict[str, Any] = {
    "status": "Draft",
    "revision_state": RevisionState.PENDING_ACTIVATION,
    "revision_activated_by": None,
    "revision_activated_on": None,
    "approved_plan": None,
    "approved_plan_source": "System",
    "production_path": None,
    "current_department": None,
    "current_assignee": None,
    "department_status": None,
    "current_production_stage": None,
    "production_dxf": None,
    "drawing_dxf_status": "None",
    "packing_method": None,
    "packing_score": None,
    "engine_version": None,
    "cutting_plan_json": None,
    "system_plan_json": None,
    "custom_plan_json": None,
    "calculated_plan_input_hash": None,
    "calculated_plan_metadata_hash": None,
    "plan_needs_recalculation": 1,
    "material_variance_cost_usd": 0,
    "internal_loss_cost_usd": 0,
    "actual_cost_usd": 0,
}


def _require_revision_capability() -> None:
    if has_capability(frappe.get_roles(), Capability.CREATE_ORDER_REVISION):
        return
    frappe.throw(_("You do not have permission to create an order revision."), frappe.PermissionError)


def _reset_special_price_approvals(order: Any) -> None:
    for row in order.pieces or []:
        row.special_shape_custom_unit_price_usd = 0
        row.special_shape_price_status = "Estimated" if (row.piece_type or "Regular") == "Special" else "Not Applicable"
        row.special_shape_price_note = ""
        row.special_shape_price_approved_by = ""
        row.special_shape_price_approved_on = None


def _add_revision_comment(source: Any, revised_name: str, reason: str) -> None:
    if reason:
        text = _("Controlled revision {0} created. Reason: {1}").format(revised_name, reason)
    else:
        text = _("Controlled revision {0} created.").format(revised_name)
    source.add_comment("Comment", text=text)


@frappe.whitelist()
def create_order_revision(order_name: str, reason: str | None = None) -> dict[str, Any]:
    """Create one editable successor while preserving the source order and plan.

    The reason is optional by design. Older buttons and external callers that do
    not send it must still be able to create a controlled draft revision.
    """

    _require_revision_capability()
    reason = str(reason or "").strip()

    frappe.db.sql("select name from `tabDoor Cutting Order` where name = %s for update", (order_name,))
    source = frappe.get_doc("Door Cutting Order", order_name)
    source.check_permission("read")

    try:
        assert_revision_allowed(source.status)
    except RevisionNotAllowed as exc:
        frappe.throw(_(str(exc)))

    if source.superseded_by:
        return {
            "name": source.superseded_by,
            "status": frappe.db.get_value("Door Cutting Order", source.superseded_by, "status") or "Draft",
            "revision": frappe.db.get_value("Door Cutting Order", source.superseded_by, "revision"),
            "revision_state": frappe.db.get_value(
                "Door Cutting Order", source.superseded_by, "revision_state"
            )
            or RevisionState.PENDING_ACTIVATION,
            "revision_of": source.name,
            "already_exists": True,
        }

    revised = frappe.copy_doc(source)
    revised.name = None
    revised.revision = next_revision(source.revision)
    revised.revision_of = source.name
    revised.revision_root = revision_root(order_name=source.name, current_root=source.revision_root)
    revised.superseded_by = None
    revised.revision_reason = reason
    for fieldname, value in RESET_FIELDS.items():
        revised.set(fieldname, value)
    _reset_special_price_approvals(revised)
    revised.insert(ignore_permissions=True)

    if not getattr(source, "revision_state", None):
        frappe.db.set_value(
            "Door Cutting Order",
            source.name,
            "revision_state",
            RevisionState.CURRENT,
            update_modified=False,
        )
    frappe.db.set_value("Door Cutting Order", source.name, "superseded_by", revised.name, update_modified=True)
    _add_revision_comment(source, revised.name, reason)

    return {
        "name": revised.name,
        "status": revised.status,
        "revision": revised.revision,
        "revision_state": revised.revision_state,
        "revision_of": source.name,
        "revision_root": revised.revision_root,
        "already_exists": False,
    }
