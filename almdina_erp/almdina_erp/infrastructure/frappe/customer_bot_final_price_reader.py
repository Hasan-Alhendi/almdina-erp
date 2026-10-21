"""Read-only, customer-owned final-price facts for the customer bot."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.customer_bot.final_price_service import (
    CustomerBotFinalPriceSnapshot,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    plan_read_requires_current_revision,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    fingerprint_final_price_basis,
    price_basis_token,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    active_approval_matches_basis,
    normalize_price_approval_status,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.frappe.final_price_approval_gateway import (
    FrappeFinalPriceApprovalGateway,
)
from almdina_erp.almdina_erp.services.cost_document_service import (
    customer_invoice_payload_for_order,
)


class FrappeCustomerBotFinalPriceReader:
    """Resolve the primary phone and constrain the order before financial reads."""

    def read(self, phone: str, order_name: str) -> CustomerBotFinalPriceSnapshot | None:
        identity = _identity(phone)
        if identity is None:
            return None
        name = _exact_order_name(order_name)
        if name is None:
            return None

        header = frappe.db.get_value(
            "Door Cutting Order",
            {"name": name, "customer": identity},
            ["name", "status", "revision_state"],
            as_dict=True,
        )
        if not header:
            return None
        status = str(header.get("status") or "").strip()
        if status == "Cancelled":
            return CustomerBotFinalPriceSnapshot(available=False, cancelled=True)
        if plan_read_requires_current_revision(status, str(header.get("revision_state") or "")):
            return None

        try:
            order = frappe.get_doc("Door Cutting Order", name)
            if str(getattr(order, "customer", None) or "") != identity:
                return None
            status = str(getattr(order, "status", None) or "").strip()
            if status == "Cancelled":
                return CustomerBotFinalPriceSnapshot(available=False, cancelled=True)
            if plan_read_requires_current_revision(
                status, str(getattr(order, "revision_state", None) or "")
            ):
                return None
            return _read_approved_invoice(order)
        except Exception:
            # A customer gets one safe result for missing, foreign, incomplete,
            # or internally inconsistent price facts.
            return None


def _identity(phone: str) -> str | None:
    from almdina_erp.almdina_erp.application.customer_bot.resolve_customer_identity import (
        resolve_customer_identity,
    )

    identity = resolve_customer_identity(FrappeCustomerPhoneDirectory(), phone)
    if identity.code != IdentityCode.ALLOWED:
        return None
    return identity.customer_id


def _read_approved_invoice(order: Any) -> CustomerBotFinalPriceSnapshot | None:
    if normalize_price_approval_status(getattr(order, "price_approval_status", None)) != PRICE_APPROVAL_STATUS_APPROVED:
        return None
    approval_name = str(getattr(order, "current_price_approval", None) or "").strip()
    if not approval_name:
        return None
    approval = frappe.get_doc("Door Cutting Price Approval", approval_name)
    if str(getattr(approval, "door_cutting_order", None) or "") != str(order.name):
        return None
    if str(getattr(approval, "validity_status", None) or "").strip() != PRICE_APPROVAL_VALIDITY_ACTIVE:
        return None

    gateway = FrappeFinalPriceApprovalGateway()
    plan = gateway.resolve_cost_plan(order)
    if plan is None or not gateway.plan_belongs_to_order(plan, order.name):
        return None
    if not gateway.plan_is_current(order, plan):
        return None
    basis = gateway.build_basis_payload(order, plan)
    fingerprint = fingerprint_final_price_basis(basis)
    formula_version = str(
        basis.get("formula_version") or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION
    )
    if not active_approval_matches_basis(
        validity_status=getattr(approval, "validity_status", None),
        stored_fingerprint=getattr(approval, "pricing_basis_fingerprint", None),
        current_fingerprint=fingerprint,
    ):
        return None
    if str(getattr(approval, "fingerprint_formula_version", None) or "") != formula_version:
        return None
    if not price_basis_token(fingerprint, formula_version=formula_version):
        return None

    invoice = customer_invoice_payload_for_order(order)
    amount = _invoice_total(invoice)
    approved = _decimal(getattr(approval, "approved_amount", None))
    basis_amount = _decimal(basis.get("approved_amount_usd"))
    currency = str(getattr(approval, "currency", None) or "").strip()
    basis_currency = str(basis.get("currency") or "").strip()
    if not currency or currency != basis_currency or currency != "USD":
        return None
    if amount is None or approved is None or basis_amount is None:
        return None
    if amount != approved or amount != basis_amount:
        return None

    consistency_key = ":".join(
        (
            str(order.name),
            str(getattr(order, "modified", "") or ""),
            str(getattr(order, "revision", "") or ""),
            approval_name,
            fingerprint,
            price_basis_token(fingerprint, formula_version=formula_version),
        )
    )
    return CustomerBotFinalPriceSnapshot(
        available=True,
        amount=amount,
        currency=currency,
        invoice_payload=invoice,
        consistency_key=consistency_key,
    )


def _invoice_total(payload: Any) -> Decimal | None:
    if not isinstance(payload, dict) or payload.get("kind") != "customer_invoice":
        return None
    lines = payload.get("lines")
    # Do not accept the customer-invoice builder's internal-cost fallback when
    # the commercial projection produced no customer price lines.
    if not isinstance(lines, (list, tuple)) or not lines:
        return None
    totals = payload.get("totals")
    if not isinstance(totals, (list, tuple)) or len(totals) != 1:
        return None
    row = totals[0]
    if not isinstance(row, dict) or row.get("value_usd") is None:
        return None
    return _decimal(row.get("value_usd"))


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _exact_order_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or any(character.isspace() for character in name):
        return None
    if any(character in name for character in "%_*?"):
        return None
    return name


__all__ = ["FrappeCustomerBotFinalPriceReader"]
