"""Additional-phone requests and grants.

A request does not authorize access. Approval re-checks the current customer
phones. One normalized phone has one grant row, including after revocation,
so a later approval keeps the revocation trace on that same row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .checks import required_token


class RequestStatus:
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


class AccessStatus:
    ACTIVE = "Active"
    REVOKED = "Revoked"


class RequestCode:
    REVIEW_REQUESTED = "review_requested"
    ALREADY_PENDING = "already_pending"
    PENDING_EXISTS = "pending_exists"
    SAME_AS_PRIMARY = "same_as_primary"
    INVALID_PHONE = "invalid_phone"
    PROVIDER_IDENTIFIER = "provider_identifier"


class DecisionCode:
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    ALREADY_APPLIED = "already_applied"
    ALREADY_DECIDED = "already_decided"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    CUSTOMER_CHANGED = "customer_changed"
    DECISION_NOTE_REQUIRED = "decision_note_required"
    INVALID_NOTE = "invalid_note"
    INVALID_PHONE = "invalid_phone"
    PROVIDER_IDENTIFIER = "provider_identifier"


_CLOSED_REQUESTS = frozenset({RequestStatus.REJECTED, RequestStatus.CANCELLED})
_NOTE_LIMIT = 500


class PhoneAccessDuplicate(Exception):
    """A store uniqueness constraint rejected a second row for the same phone."""


@dataclass(frozen=True, slots=True)
class AccessEvent:
    event_type: str
    actor_id: str
    occurred_on: datetime
    reason: str
    request_id: str | None


@dataclass(frozen=True, slots=True)
class StoredPhoneAccess:
    access_id: str
    customer_id: str
    normalized_phone: str
    status: str
    approved_by: str | None
    approved_on: datetime | None
    revoked_by: str | None
    revoked_on: datetime | None
    revoke_reason: str
    events: tuple[AccessEvent, ...]


@dataclass(frozen=True, slots=True)
class StoredPhoneRequest:
    request_id: str
    requested_phone: str
    claimed_primary_phone: str
    proposed_customer_id: str | None
    status: str
    requester_ref: str
    decided_by: str | None
    decided_on: datetime | None
    decision_note: str
    access_id: str | None


@dataclass(frozen=True, slots=True)
class PhoneRequestResult:
    code: str
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class PhoneDecisionResult:
    code: str
    request_id: str | None = None
    access_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovalPlan:
    code: str
    request: StoredPhoneRequest | None = None
    access: StoredPhoneAccess | None = None
    persist_request: bool = False
    persist_access: bool = False
    insert_access: bool = False


def proposed_customer_id(primary_customer_ids: tuple[str, ...] | list[str]) -> str | None:
    """Return the only current match. Zero or many matches stay unresolved."""

    distinct: list[str] = []
    for customer_id in primary_customer_ids:
        if customer_id not in distinct:
            distinct.append(customer_id)
    if len(distinct) != 1:
        return None
    return distinct[0]


def classify_pending_request(
    pending: StoredPhoneRequest | None,
    *,
    claimed_primary_phone: str,
) -> str | None:
    if pending is None:
        return None
    if pending.claimed_primary_phone == claimed_primary_phone:
        return RequestCode.ALREADY_PENDING
    return RequestCode.PENDING_EXISTS


def note_text(value: object, *, required: bool) -> tuple[str | None, str | None]:
    """Return ``(text, error_code)``. Empty is allowed only when not required."""

    if not isinstance(value, str):
        return None, DecisionCode.INVALID_NOTE
    text = value.strip()
    if required and not text:
        return None, DecisionCode.DECISION_NOTE_REQUIRED
    if len(text) > _NOTE_LIMIT:
        return None, DecisionCode.INVALID_NOTE
    return text, None


def requester_ref(value: object) -> str:
    token = required_token(value, "requester_ref")
    if len(token) > 140:
        raise ValueError("requester_ref is too long")
    return token


def plan_approval(
    request: StoredPhoneRequest,
    access: StoredPhoneAccess | None,
    primary_customer_ids: tuple[str, ...] | list[str],
    requested_phone_customer_ids: tuple[str, ...] | list[str],
    *,
    actor_id: str,
    now: datetime,
    decision_note: str,
) -> ApprovalPlan:
    """Decide approval from the phones as they are at execution time."""

    if request.status in _CLOSED_REQUESTS:
        return ApprovalPlan(DecisionCode.ALREADY_DECIDED)
    if request.status == RequestStatus.APPROVED:
        if (
            access is not None
            and access.status == AccessStatus.ACTIVE
            and access.customer_id == (request.proposed_customer_id or access.customer_id)
            and access.normalized_phone == request.requested_phone
        ):
            return ApprovalPlan(
                DecisionCode.ALREADY_APPLIED,
                request=request,
                access=access,
            )
        return ApprovalPlan(DecisionCode.ALREADY_DECIDED)

    customer_id = proposed_customer_id(primary_customer_ids)
    if customer_id is None:
        if _distinct(primary_customer_ids):
            return ApprovalPlan(DecisionCode.CONFLICT)
        return ApprovalPlan(DecisionCode.CUSTOMER_CHANGED)
    if request.proposed_customer_id and request.proposed_customer_id != customer_id:
        return ApprovalPlan(DecisionCode.CUSTOMER_CHANGED)
    if any(match_id != customer_id for match_id in _distinct(requested_phone_customer_ids)):
        return ApprovalPlan(DecisionCode.CONFLICT)
    if (
        access is not None
        and access.status == AccessStatus.ACTIVE
        and access.customer_id != customer_id
    ):
        return ApprovalPlan(DecisionCode.CONFLICT)
    if access is not None and access.status == AccessStatus.ACTIVE and access.customer_id == customer_id:
        linked = _decide_request(
            request,
            status=RequestStatus.APPROVED,
            actor_id=actor_id,
            now=now,
            decision_note=decision_note,
            access_id=access.access_id,
            proposed_customer_id=customer_id,
        )
        return ApprovalPlan(
            DecisionCode.ALREADY_APPLIED,
            request=linked,
            access=access,
            persist_request=linked != request,
        )

    event_type = "Approved" if access is None else "Reactivated"
    next_access = _activate_access(
        access,
        customer_id=customer_id,
        normalized_phone=request.requested_phone,
        actor_id=actor_id,
        now=now,
        request_id=request.request_id,
        event_type=event_type,
        reason=decision_note,
    )
    linked = _decide_request(
        request,
        status=RequestStatus.APPROVED,
        actor_id=actor_id,
        now=now,
        decision_note=decision_note,
        access_id=next_access.access_id,
        proposed_customer_id=customer_id,
    )
    return ApprovalPlan(
        DecisionCode.APPROVED,
        request=linked,
        access=next_access,
        persist_request=True,
        persist_access=True,
        insert_access=access is None,
    )


def plan_rejection(
    request: StoredPhoneRequest,
    *,
    actor_id: str,
    now: datetime,
    decision_note: str,
) -> ApprovalPlan:
    if request.status == RequestStatus.REJECTED:
        return ApprovalPlan(DecisionCode.ALREADY_APPLIED, request=request)
    if request.status != RequestStatus.PENDING:
        return ApprovalPlan(DecisionCode.ALREADY_DECIDED, request=request)
    rejected = _decide_request(
        request,
        status=RequestStatus.REJECTED,
        actor_id=actor_id,
        now=now,
        decision_note=decision_note,
        access_id=None,
        proposed_customer_id=request.proposed_customer_id,
    )
    return ApprovalPlan(
        DecisionCode.REJECTED,
        request=rejected,
        persist_request=True,
    )


def plan_revocation(
    access: StoredPhoneAccess,
    *,
    actor_id: str,
    now: datetime,
    reason: str,
) -> ApprovalPlan:
    if access.status == AccessStatus.REVOKED:
        return ApprovalPlan(DecisionCode.ALREADY_APPLIED, access=access)
    revoked = StoredPhoneAccess(
        access_id=access.access_id,
        customer_id=access.customer_id,
        normalized_phone=access.normalized_phone,
        status=AccessStatus.REVOKED,
        approved_by=access.approved_by,
        approved_on=access.approved_on,
        revoked_by=actor_id,
        revoked_on=now,
        revoke_reason=reason,
        events=access.events
        + (
            AccessEvent(
                event_type="Revoked",
                actor_id=actor_id,
                occurred_on=now,
                reason=reason,
                request_id=None,
            ),
        ),
    )
    return ApprovalPlan(
        DecisionCode.REVOKED,
        access=revoked,
        persist_access=True,
    )


def _activate_access(
    access: StoredPhoneAccess | None,
    *,
    customer_id: str,
    normalized_phone: str,
    actor_id: str,
    now: datetime,
    request_id: str,
    event_type: str,
    reason: str,
) -> StoredPhoneAccess:
    events = () if access is None else access.events
    return StoredPhoneAccess(
        access_id="" if access is None else access.access_id,
        customer_id=customer_id,
        normalized_phone=normalized_phone,
        status=AccessStatus.ACTIVE,
        approved_by=actor_id,
        approved_on=now,
        revoked_by=None if access is None else access.revoked_by,
        revoked_on=None if access is None else access.revoked_on,
        revoke_reason="" if access is None else access.revoke_reason,
        events=events
        + (
            AccessEvent(
                event_type=event_type,
                actor_id=actor_id,
                occurred_on=now,
                reason=reason,
                request_id=request_id,
            ),
        ),
    )


def _decide_request(
    request: StoredPhoneRequest,
    *,
    status: str,
    actor_id: str,
    now: datetime,
    decision_note: str,
    access_id: str | None,
    proposed_customer_id: str | None,
) -> StoredPhoneRequest:
    return StoredPhoneRequest(
        request_id=request.request_id,
        requested_phone=request.requested_phone,
        claimed_primary_phone=request.claimed_primary_phone,
        proposed_customer_id=proposed_customer_id,
        status=status,
        requester_ref=request.requester_ref,
        decided_by=actor_id,
        decided_on=now,
        decision_note=decision_note,
        access_id=access_id,
    )


def _distinct(customer_ids: tuple[str, ...] | list[str]) -> list[str]:
    distinct: list[str] = []
    for customer_id in customer_ids:
        if customer_id not in distinct:
            distinct.append(customer_id)
    return distinct


__all__ = [
    "AccessEvent",
    "AccessStatus",
    "ApprovalPlan",
    "DecisionCode",
    "PhoneAccessDuplicate",
    "PhoneDecisionResult",
    "PhoneRequestResult",
    "RequestCode",
    "RequestStatus",
    "StoredPhoneAccess",
    "StoredPhoneRequest",
    "classify_pending_request",
    "note_text",
    "plan_approval",
    "plan_rejection",
    "plan_revocation",
    "proposed_customer_id",
    "requester_ref",
]
