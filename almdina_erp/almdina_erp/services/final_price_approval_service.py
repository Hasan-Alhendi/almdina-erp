"""Thin RPC boundary for commercial final-price approval and manual cancel."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    FinalPriceApprovalTokenError,
    approve_order_final_price as run_approve_order_final_price,
    cancel_order_final_price_approval as run_cancel_order_final_price_approval,
    decide_final_price_approval_actions,
    invalidate_order_final_price_approval,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    ApprovalNoteError,
    FinalPriceApprovalEligibilityError,
    FinalPriceCancellationError,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.final_price_approval_gateway import (
    FrappeFinalPriceApprovalGateway,
    order_commercial_inputs_changed,
)


def _result_payload(result: Any) -> dict[str, Any]:
    return {
        "order_name": result.order_name,
        "price_approval_status": result.price_approval_status,
        "current_price_approval": result.current_price_approval,
        "approved_amount_usd": result.approved_amount_usd,
        "currency": result.currency,
        "cutting_plan": result.cutting_plan,
        "pricing_basis_fingerprint": result.pricing_basis_fingerprint,
        "fingerprint_formula_version": result.fingerprint_formula_version,
        "approved_by": result.approved_by,
        "approved_on": result.approved_on,
        "approval_note": result.approval_note,
        "reused_existing": result.reused_existing,
        "price_basis_token": result.price_basis_token,
    }


def _cancellation_payload(result: Any, *, order: Any) -> dict[str, Any]:
    # Refresh action decisions with the caller's real capabilities after cancel.
    decision = decide_final_price_approval_actions(
        has_approve_final_price=document_has_capability(
            order, Capability.APPROVE_FINAL_PRICE
        ),
        has_view_costs=cutting_plan_capability_allowed(order, Capability.VIEW_COSTS),
        has_edit_cost_settings=cutting_plan_capability_allowed(
            order, Capability.EDIT_COST_SETTINGS
        ),
        has_cancel_final_price_approval=document_has_capability(
            order, Capability.CANCEL_FINAL_PRICE_APPROVAL
        ),
        price_approval_status=result.price_approval_status,
        current_price_approval=result.current_price_approval,
        price_basis_token_value=None,
        order_status=getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
        docstatus=int(getattr(order, "docstatus", 0) or 0),
    )
    return {
        "order_name": result.order_name,
        "price_approval_status": result.price_approval_status,
        "current_price_approval": result.current_price_approval,
        "cancelled_approval": result.cancelled_approval,
        "cancelled_now": result.cancelled_now,
        "reason": result.reason,
        "can_approve_final_price": decision.can_approve_final_price,
        "can_cancel_final_price_approval": decision.can_cancel_final_price_approval,
        "final_price_approval_blocker": (
            {
                "code": decision.reason_code,
                "message": decision.reason_message,
            }
            if decision.reason_code
            else None
        ),
        "final_price_cancellation_blocker": (
            {
                "code": decision.cancel_reason_code,
                "message": decision.cancel_reason_message,
            }
            if decision.cancel_reason_code
            else None
        ),
        # Manual cancel must not set the auto-invalidation toast signal.
        "final_price_approval_invalidated": False,
    }


def mark_final_price_approval_invalidated(*, order: Any | None = None) -> None:
    """Record that the current request actually cleared an Approved final price.

    Sets a response/snapshot flag consumed by the Cost/order UI. Toast visibility
    is decided on the client from capabilities + document generation. Does not
    create Notifications or broadcast to other users.
    """

    frappe.flags.final_price_approval_invalidated = True
    response = getattr(frappe.local, "response", None)
    order_name = str(getattr(order, "name", None) or "").strip() or None
    if isinstance(response, dict):
        response["final_price_approval_invalidated"] = True
        if order_name:
            response["final_price_approval_order"] = order_name
    if order is not None:
        order.price_approval_status = PRICE_APPROVAL_STATUS_UNAPPROVED
        order.current_price_approval = None
        order.flags.final_price_approval_invalidated = True


def final_price_approval_was_invalidated() -> bool:
    return bool(getattr(frappe.flags, "final_price_approval_invalidated", False))


@frappe.whitelist()
def approve_order_final_price(
    order_name: str,
    expected_price_basis_token: str | None = None,
    approval_note: str | None = None,
) -> dict[str, Any]:
    """Approve the current commercial invoice total for one Door Cutting Order.

    Requires ``approve_final_price`` on the order plus ``view_costs`` within
    parent-order scope, plus complete/fresh commercial pricing. Allowed at any
    production stage (including post-Drawing). Does not require edit_order,
    edit_cost_settings, or approve_special_price, and does not use draft-only
    order-edit or special-leaf pricing policies. Mutates price-approval fields
    only; never order status, stage, assignee, or Cutting Plan approval.

    ``approval_note`` is optional plain text (max 500). Absent/blank store no note.
    """

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_document_capability(
        order,
        Capability.APPROVE_FINAL_PRICE,
        message=_("لا تملك صلاحية اعتماد السعر النهائي لهذا الطلب."),
    )
    require_cutting_plan_capability(
        order,
        Capability.VIEW_COSTS,
        message=_("اعتماد السعر النهائي يتطلب صلاحية عرض التكلفة لهذا الطلب."),
    )

    gateway = FrappeFinalPriceApprovalGateway()
    try:
        # Alias required: this whitelist shares the application use-case name.
        # Calling the unaliased import would recurse into this endpoint and raise
        # "got multiple values for argument 'order_name'" (gateway + keyword).
        result = run_approve_order_final_price(
            gateway,
            order_name=name,
            expected_price_basis_token=expected_price_basis_token,
            approval_note=approval_note,
        )
    except ApprovalNoteError as exc:
        frappe.throw(_(str(exc)), frappe.ValidationError)
    except FinalPriceApprovalTokenError as exc:
        frappe.throw(str(exc), frappe.ValidationError)
    except FinalPriceApprovalEligibilityError as exc:
        frappe.throw(str(exc), frappe.ValidationError)

    return _result_payload(result)


@frappe.whitelist()
def cancel_order_final_price_approval(
    order_name: str,
    expected_current_price_approval: str | None = None,
) -> dict[str, Any]:
    """Manually cancel the Active final-price approval the client reviewed.

    Requires ``cancel_final_price_approval`` plus ``view_costs`` within parent-order
    scope. Does not require ``approve_final_price``, edit capabilities, a fresh
    plan, or complete pricing. Does not mutate commercial inputs, operational
    status, stage, assignee, or Cutting Plan approval. Does not raise the
    auto-invalidation toast signal used after basis-affecting saves.
    """

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_document_capability(
        order,
        Capability.CANCEL_FINAL_PRICE_APPROVAL,
        message=_("لا تملك صلاحية إلغاء اعتماد السعر النهائي لهذا الطلب."),
    )
    require_cutting_plan_capability(
        order,
        Capability.VIEW_COSTS,
        message=_("إلغاء اعتماد السعر النهائي يتطلب صلاحية عرض التكلفة لهذا الطلب."),
    )

    gateway = FrappeFinalPriceApprovalGateway()
    try:
        result = run_cancel_order_final_price_approval(
            gateway,
            order_name=name,
            expected_current_price_approval=expected_current_price_approval,
        )
    except FinalPriceCancellationError as exc:
        frappe.throw(_(str(exc)), frappe.ValidationError)

    # Reload focused order fields after command-owned db.set_value writes.
    order.reload()
    return _cancellation_payload(result, order=order)


def maybe_invalidate_final_price_approval(
    order_name: str,
    *,
    reason: str,
    only_if_basis_changed: bool = False,
    order: Any | None = None,
) -> dict[str, Any] | None:
    """Central mutation-path hook: invalidate Approved price inside the same txn.

    Callers must already be authorized for the commercial/plan mutation itself.
    This does not grant view_costs, approve_final_price, or
    cancel_final_price_approval, and never runs from read/snapshot paths.

    Exceptions propagate intentionally. Callers must not swallow them: the
    surrounding request/document transaction must roll back the original
    pricing-basis mutation together with the failed invalidation.
    """

    name = str(order_name or "").strip()
    if not name:
        return None
    result = invalidate_order_final_price_approval(
        FrappeFinalPriceApprovalGateway(),
        order_name=name,
        reason=reason,
        only_if_basis_changed=only_if_basis_changed,
    )
    if not result.invalidated:
        return None
    mark_final_price_approval_invalidated(order=order)
    return {
        "order_name": result.order_name,
        "invalidated": True,
        "previous_approval": result.previous_approval,
        "reason": result.reason,
        "final_price_approval_invalidated": True,
    }


def maybe_invalidate_final_price_after_order_save(order: Any) -> dict[str, Any] | None:
    """Invalidate when a DCO save changed commercial pricing inputs.

    Invoked from ``on_update`` so it shares the parent ``Document.save``
    transaction. Do not wrap callers in ``try/except`` that continues the save.
    Syncs the in-memory document so the save response reflects Unapproved.
    """

    if not order_commercial_inputs_changed(order):
        return None
    name = str(getattr(order, "name", None) or "").strip()
    if not name:
        return None
    return maybe_invalidate_final_price_approval(
        name,
        reason="order_pricing_inputs_changed",
        only_if_basis_changed=False,
        order=order,
    )


__all__ = [
    "approve_order_final_price",
    "cancel_order_final_price_approval",
    "final_price_approval_was_invalidated",
    "mark_final_price_approval_invalidated",
    "maybe_invalidate_final_price_after_order_save",
    "maybe_invalidate_final_price_approval",
]
