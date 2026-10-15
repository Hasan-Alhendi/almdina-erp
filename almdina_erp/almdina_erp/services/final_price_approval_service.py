"""Thin RPC boundary for commercial final-price approval."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    FinalPriceApprovalTokenError,
    approve_order_final_price as run_approve_order_final_price,
    invalidate_order_final_price_approval,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    FinalPriceApprovalEligibilityError,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
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
        "reused_existing": result.reused_existing,
        "price_basis_token": result.price_basis_token,
    }


@frappe.whitelist()
def approve_order_final_price(
    order_name: str,
    expected_price_basis_token: str | None = None,
) -> dict[str, Any]:
    """Approve the current commercial invoice total for one Door Cutting Order.

    Requires ``approve_final_price`` on the order plus ``view_costs`` within
    parent-order scope, plus complete/fresh commercial pricing. Allowed at any
    production stage (including post-Drawing). Does not require edit_order,
    edit_cost_settings, or approve_special_price, and does not use draft-only
    order-edit or special-leaf pricing policies. Mutates price-approval fields
    only; never order status, stage, assignee, or Cutting Plan approval.
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
        )
    except FinalPriceApprovalTokenError as exc:
        frappe.throw(str(exc), frappe.ValidationError)
    except FinalPriceApprovalEligibilityError as exc:
        frappe.throw(str(exc), frappe.ValidationError)

    return _result_payload(result)


def maybe_invalidate_final_price_approval(
    order_name: str,
    *,
    reason: str,
    only_if_basis_changed: bool = False,
) -> dict[str, Any] | None:
    """Central mutation-path hook: invalidate Approved price inside the same txn.

    Callers must already be authorized for the commercial/plan mutation itself.
    This does not grant view_costs or approve_final_price, and never runs from
    read/snapshot paths.

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
    return {
        "order_name": result.order_name,
        "invalidated": True,
        "previous_approval": result.previous_approval,
        "reason": result.reason,
    }


def maybe_invalidate_final_price_after_order_save(order: Any) -> dict[str, Any] | None:
    """Invalidate when a DCO save changed commercial pricing inputs.

    Invoked from ``on_update`` so it shares the parent ``Document.save``
    transaction. Do not wrap callers in ``try/except`` that continues the save.
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
    )


__all__ = [
    "approve_order_final_price",
    "maybe_invalidate_final_price_after_order_save",
    "maybe_invalidate_final_price_approval",
]
