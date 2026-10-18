"""Internal wiring for customer-bot identity and phone-access decisions.

These functions are not whitelisted and are not guest endpoints.
"""

from __future__ import annotations

from datetime import datetime

from almdina_erp.almdina_erp.application.customer_bot.phone_access_commands import (
    approve_phone_access_request,
    reject_phone_access_request,
    request_additional_phone_access,
    revoke_phone_access,
)
from almdina_erp.almdina_erp.application.customer_bot.resolve_customer_identity import (
    resolve_customer_identity,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import CustomerIdentity
from almdina_erp.almdina_erp.domain.customer_bot.phone_access import (
    PhoneDecisionResult,
    PhoneRequestResult,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_actor_policy import (
    FrappeCustomerBotActorPolicy,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_phone_repository import (
    FrappePhoneAccessStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)


def resolve_customer_phone(phone: str) -> CustomerIdentity:
    return resolve_customer_identity(
        FrappeCustomerPhoneDirectory(),
        FrappePhoneAccessStore(),
        phone,
    )


def submit_additional_phone_request(
    *,
    requested_phone: str,
    claimed_primary_phone: str,
    requester_ref_value: str,
    now: datetime,
) -> PhoneRequestResult:
    return request_additional_phone_access(
        FrappeCustomerPhoneDirectory(),
        FrappePhoneAccessStore(),
        requested_phone=requested_phone,
        claimed_primary_phone=claimed_primary_phone,
        requester_ref_value=requester_ref_value,
        now=now,
    )


def approve_additional_phone_request(
    *,
    actor_id: str,
    request_id: str,
    now: datetime,
    decision_note: str = "",
) -> PhoneDecisionResult:
    return approve_phone_access_request(
        FrappeCustomerPhoneDirectory(),
        FrappePhoneAccessStore(),
        FrappeCustomerBotActorPolicy(),
        actor_id=actor_id,
        request_id=request_id,
        now=now,
        decision_note=decision_note,
    )


def reject_additional_phone_request(
    *,
    actor_id: str,
    request_id: str,
    now: datetime,
    decision_note: str,
) -> PhoneDecisionResult:
    return reject_phone_access_request(
        FrappePhoneAccessStore(),
        FrappeCustomerBotActorPolicy(),
        actor_id=actor_id,
        request_id=request_id,
        now=now,
        decision_note=decision_note,
    )


def revoke_additional_phone(
    *,
    actor_id: str,
    phone: str,
    now: datetime,
    reason: str,
) -> PhoneDecisionResult:
    return revoke_phone_access(
        FrappePhoneAccessStore(),
        FrappeCustomerBotActorPolicy(),
        actor_id=actor_id,
        phone=phone,
        now=now,
        reason=reason,
    )


__all__ = [
    "approve_additional_phone_request",
    "reject_additional_phone_request",
    "resolve_customer_phone",
    "revoke_additional_phone",
    "submit_additional_phone_request",
]
