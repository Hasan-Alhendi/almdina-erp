"""Request, approve, reject, and revoke additional phone access.

Approval and revocation run inside the store transaction. A repeated call
does not insert another grant. Closed requests stay closed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from almdina_erp.almdina_erp.domain.customer_bot.phone_access import (
    DecisionCode,
    PhoneAccessDuplicate,
    PhoneDecisionResult,
    PhoneRequestResult,
    RequestCode,
    RequestStatus,
    StoredPhoneRequest,
    classify_pending_request,
    note_text,
    plan_approval,
    plan_rejection,
    plan_revocation,
    proposed_customer_id,
    requester_ref,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
)

from .phone_access_ports import (
    CustomerBotActorPolicy,
    CustomerPhoneDirectory,
    PhoneAccessStore,
)


def request_additional_phone_access(
    directory: CustomerPhoneDirectory,
    store: PhoneAccessStore,
    *,
    requested_phone: str,
    claimed_primary_phone: str,
    requester_ref_value: str,
    now: datetime,
) -> PhoneRequestResult:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        return PhoneRequestResult(RequestCode.INVALID_PHONE)
    try:
        requested = normalize_customer_phone(requested_phone)
        claimed = normalize_customer_phone(claimed_primary_phone)
    except CustomerPhoneError as error:
        return PhoneRequestResult(error.code)
    if requested == claimed:
        return PhoneRequestResult(RequestCode.SAME_AS_PRIMARY)
    try:
        source = requester_ref(requester_ref_value)
    except ValueError:
        return PhoneRequestResult(RequestCode.INVALID_PHONE)

    try:
        with store.exclusive():
            pending = store.pending_for_phone(requested)
            pending_code = classify_pending_request(
                pending,
                claimed_primary_phone=claimed,
            )
            if pending_code == RequestCode.ALREADY_PENDING and pending is not None:
                return PhoneRequestResult(pending_code, pending.request_id)
            if pending_code is not None:
                return PhoneRequestResult(pending_code)
            created = store.insert_request(
                StoredPhoneRequest(
                    request_id="",
                    requested_phone=requested,
                    claimed_primary_phone=claimed,
                    proposed_customer_id=proposed_customer_id(
                        directory.find_by_normalized_phone(claimed)
                    ),
                    status=RequestStatus.PENDING,
                    requester_ref=source,
                    decided_by=None,
                    decided_on=None,
                    decision_note="",
                    access_id=None,
                )
            )
    except PhoneAccessDuplicate:
        return PhoneRequestResult(RequestCode.PENDING_EXISTS)
    return PhoneRequestResult(RequestCode.REVIEW_REQUESTED, created.request_id)


def approve_phone_access_request(
    directory: CustomerPhoneDirectory,
    store: PhoneAccessStore,
    policy: CustomerBotActorPolicy,
    *,
    actor_id: str,
    request_id: str,
    now: datetime,
    decision_note: str = "",
) -> PhoneDecisionResult:
    actor = _actor(actor_id)
    if actor is None or not _aware(now):
        return PhoneDecisionResult(DecisionCode.FORBIDDEN)
    note, note_error = note_text(decision_note, required=False)
    if note_error:
        return PhoneDecisionResult(note_error)
    assert note is not None
    try:
        with store.exclusive():
            request = store.lock_request(request_id)
            if request is None:
                return PhoneDecisionResult(DecisionCode.NOT_FOUND)
            if not policy.has_manage_access(actor):
                return PhoneDecisionResult(DecisionCode.FORBIDDEN)
            if request.proposed_customer_id and not policy.can_access_customer(
                actor,
                request.proposed_customer_id,
            ):
                return PhoneDecisionResult(DecisionCode.FORBIDDEN)
            access = store.lock_access_by_phone(request.requested_phone)
            primary_ids = directory.find_by_normalized_phone(request.claimed_primary_phone)
            requested_ids = directory.find_by_normalized_phone(request.requested_phone)
            plan = plan_approval(
                request,
                access,
                primary_ids,
                requested_ids,
                actor_id=actor,
                now=now,
                decision_note=note,
            )
            customer_id = plan.access.customer_id if plan.access is not None else proposed_customer_id(primary_ids)
            if plan.code in {DecisionCode.APPROVED, DecisionCode.ALREADY_APPLIED} or plan.persist_request:
                if customer_id and not policy.can_access_customer(actor, customer_id):
                    return PhoneDecisionResult(DecisionCode.FORBIDDEN)
            if not plan.persist_request and not plan.persist_access:
                return PhoneDecisionResult(plan.code, request.request_id, None if plan.access is None else plan.access.access_id)
            stored_access = plan.access
            if plan.insert_access and plan.access is not None:
                stored_access = store.insert_access(plan.access)
            elif plan.persist_access and plan.access is not None:
                stored_access = store.save_access(plan.access)
            if plan.persist_request and plan.request is not None:
                access_id = stored_access.access_id if stored_access is not None else plan.request.access_id
                store.save_request(replace(plan.request, access_id=access_id))
            return PhoneDecisionResult(
                plan.code,
                request.request_id,
                None if stored_access is None else stored_access.access_id,
            )
    except PhoneAccessDuplicate:
        return PhoneDecisionResult(DecisionCode.CONFLICT)


def reject_phone_access_request(
    store: PhoneAccessStore,
    policy: CustomerBotActorPolicy,
    *,
    actor_id: str,
    request_id: str,
    now: datetime,
    decision_note: str,
) -> PhoneDecisionResult:
    actor = _actor(actor_id)
    if actor is None or not _aware(now):
        return PhoneDecisionResult(DecisionCode.FORBIDDEN)
    note, note_error = note_text(decision_note, required=True)
    if note_error:
        return PhoneDecisionResult(note_error)
    assert note is not None
    with store.exclusive():
        request = store.lock_request(request_id)
        if request is None:
            return PhoneDecisionResult(DecisionCode.NOT_FOUND)
        if not policy.has_manage_access(actor):
            return PhoneDecisionResult(DecisionCode.FORBIDDEN)
        if request.proposed_customer_id and not policy.can_access_customer(actor, request.proposed_customer_id):
            return PhoneDecisionResult(DecisionCode.FORBIDDEN)
        plan = plan_rejection(request, actor_id=actor, now=now, decision_note=note)
        if plan.persist_request and plan.request is not None:
            store.save_request(plan.request)
        return PhoneDecisionResult(plan.code, request.request_id)


def revoke_phone_access(
    store: PhoneAccessStore,
    policy: CustomerBotActorPolicy,
    *,
    actor_id: str,
    phone: str,
    now: datetime,
    reason: str,
) -> PhoneDecisionResult:
    actor = _actor(actor_id)
    if actor is None or not _aware(now):
        return PhoneDecisionResult(DecisionCode.FORBIDDEN)
    note, note_error = note_text(reason, required=True)
    if note_error:
        return PhoneDecisionResult(note_error)
    assert note is not None
    try:
        normalized = normalize_customer_phone(phone)
    except CustomerPhoneError as error:
        return PhoneDecisionResult(error.code)
    with store.exclusive():
        access = store.lock_access_by_phone(normalized)
        if access is None:
            return PhoneDecisionResult(DecisionCode.NOT_FOUND)
        if not policy.has_manage_access(actor) or not policy.can_access_customer(actor, access.customer_id):
            return PhoneDecisionResult(DecisionCode.FORBIDDEN)
        plan = plan_revocation(access, actor_id=actor, now=now, reason=note)
        if plan.persist_access and plan.access is not None:
            stored = store.save_access(plan.access)
            return PhoneDecisionResult(plan.code, None, stored.access_id)
        return PhoneDecisionResult(plan.code, None, access.access_id)


def _actor(actor_id: object) -> str | None:
    if not isinstance(actor_id, str):
        return None
    actor = actor_id.strip()
    if not actor or actor == "Guest":
        return None
    return actor


def _aware(now: datetime) -> bool:
    return isinstance(now, datetime) and now.utcoffset() is not None


__all__ = [
    "approve_phone_access_request",
    "reject_phone_access_request",
    "request_additional_phone_access",
    "revoke_phone_access",
]
