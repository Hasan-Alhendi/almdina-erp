"""Persist customer-bot phone requests and grants.

Writes run only after a use case has decided, and only while the service flag
is set. ``ignore_permissions`` skips the closed DocPerm write bit; the
controller still rejects a save that did not come through this repository.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import frappe
from frappe.utils import get_datetime

from almdina_erp.almdina_erp.domain.customer_bot.phone_access import (
    AccessEvent,
    PhoneAccessDuplicate,
    StoredPhoneAccess,
    StoredPhoneRequest,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_records import (
    PHONE_ACCESS_DOCTYPE,
    PHONE_REQUEST_DOCTYPE,
    SERVICE_WRITE_FLAG,
)


class FrappePhoneAccessStore:
    @contextmanager
    def exclusive(self) -> Iterator[None]:
        frappe.db.savepoint("customer_bot_phone_access")
        try:
            yield
        except Exception:
            try:
                frappe.db.rollback(save_point="customer_bot_phone_access")
            except Exception:
                frappe.db.rollback()
            raise

    def lock_request(self, request_id: str) -> StoredPhoneRequest | None:
        if not _lock(PHONE_REQUEST_DOCTYPE, {"name": request_id}):
            return None
        return _request_snapshot(frappe.get_doc(PHONE_REQUEST_DOCTYPE, request_id))

    def lock_access_by_phone(self, normalized_phone: str) -> StoredPhoneAccess | None:
        name = _lock(
            PHONE_ACCESS_DOCTYPE,
            {"normalized_phone": normalized_phone},
        )
        if not name:
            return None
        return _access_snapshot(frappe.get_doc(PHONE_ACCESS_DOCTYPE, name))

    def pending_for_phone(self, normalized_phone: str) -> StoredPhoneRequest | None:
        name = _lock(
            PHONE_REQUEST_DOCTYPE,
            {"pending_phone_key": normalized_phone, "status": "Pending"},
        )
        if not name:
            return None
        return _request_snapshot(frappe.get_doc(PHONE_REQUEST_DOCTYPE, name))

    def get_access_by_phone(self, normalized_phone: str) -> StoredPhoneAccess | None:
        name = frappe.db.get_value(
            PHONE_ACCESS_DOCTYPE,
            {"normalized_phone": normalized_phone},
            "name",
        )
        if not name:
            return None
        return _access_snapshot(frappe.get_doc(PHONE_ACCESS_DOCTYPE, name))

    def insert_request(self, request: StoredPhoneRequest) -> StoredPhoneRequest:
        document = frappe.get_doc(
            {
                "doctype": PHONE_REQUEST_DOCTYPE,
                "requested_phone": request.requested_phone,
                "claimed_primary_phone": request.claimed_primary_phone,
                "proposed_customer": request.proposed_customer_id,
                "status": request.status,
                "requester_ref": request.requester_ref,
                "decision_note": request.decision_note,
                "pending_phone_key": request.requested_phone
                if request.status == "Pending"
                else None,
            }
        )
        _save_new(document)
        return _request_snapshot(document)

    def save_request(self, request: StoredPhoneRequest) -> StoredPhoneRequest:
        document = frappe.get_doc(PHONE_REQUEST_DOCTYPE, request.request_id)
        document.proposed_customer = request.proposed_customer_id
        document.status = request.status
        document.decided_by = request.decided_by
        document.decided_on = _persist_datetime(request.decided_on)
        document.decision_note = request.decision_note
        document.phone_access = request.access_id
        document.pending_phone_key = (
            request.requested_phone if request.status == "Pending" else None
        )
        _save_existing(document)
        return _request_snapshot(document)

    def insert_access(self, access: StoredPhoneAccess) -> StoredPhoneAccess:
        document = frappe.get_doc(
            {
                "doctype": PHONE_ACCESS_DOCTYPE,
                "customer": access.customer_id,
                "normalized_phone": access.normalized_phone,
                "status": access.status,
                "approved_by": access.approved_by,
                "approved_on": _persist_datetime(access.approved_on),
                "revoked_by": access.revoked_by,
                "revoked_on": _persist_datetime(access.revoked_on),
                "revoke_reason": access.revoke_reason,
                "events": [_event_row(event) for event in access.events],
            }
        )
        _save_new(document)
        return _access_snapshot(document)

    def save_access(self, access: StoredPhoneAccess) -> StoredPhoneAccess:
        document = frappe.get_doc(PHONE_ACCESS_DOCTYPE, access.access_id)
        document.customer = access.customer_id
        document.status = access.status
        document.approved_by = access.approved_by
        document.approved_on = _persist_datetime(access.approved_on)
        document.revoked_by = access.revoked_by
        document.revoked_on = _persist_datetime(access.revoked_on)
        document.revoke_reason = access.revoke_reason
        document.events = []
        for event in access.events:
            document.append("events", _event_row(event))
        _save_existing(document)
        return _access_snapshot(document)


def _lock(doctype: str, filters: dict[str, str]) -> str:
    clauses = []
    values: list[str] = []
    for field, value in filters.items():
        clauses.append(f"`{field}`=%s")
        values.append(value)
    table = f"tab{doctype}"
    rows = frappe.db.sql(
        f"select name from `{table}` where {' and '.join(clauses)} for update",
        values,
    )
    if not rows:
        return ""
    return str(rows[0][0])


def _save_new(document: frappe.model.document.Document) -> None:
    try:
        with _service_write(document):
            document.insert(ignore_permissions=True)
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError, frappe.QueryDeadlockError) as error:
        raise PhoneAccessDuplicate() from error


def _save_existing(document: frappe.model.document.Document) -> None:
    try:
        with _service_write(document):
            document.save(ignore_permissions=True)
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError, frappe.QueryDeadlockError) as error:
        raise PhoneAccessDuplicate() from error


@contextmanager
def _service_write(document: frappe.model.document.Document) -> Iterator[None]:
    previous = bool(getattr(frappe.flags, SERVICE_WRITE_FLAG, False))
    frappe.flags.customer_bot_service_write = True
    document.flags.customer_bot_service_write = True
    try:
        yield
    finally:
        frappe.flags.customer_bot_service_write = previous


def _request_snapshot(document: frappe.model.document.Document) -> StoredPhoneRequest:
    return StoredPhoneRequest(
        request_id=str(document.name),
        requested_phone=str(document.requested_phone),
        claimed_primary_phone=str(document.claimed_primary_phone),
        proposed_customer_id=str(document.proposed_customer or "") or None,
        status=str(document.status),
        requester_ref=str(document.requester_ref),
        decided_by=str(document.decided_by or "") or None,
        decided_on=_aware(document.decided_on),
        decision_note=str(document.decision_note or ""),
        access_id=str(document.phone_access or "") or None,
    )


def _access_snapshot(document: frappe.model.document.Document) -> StoredPhoneAccess:
    events = tuple(
        AccessEvent(
            event_type=str(row.event_type),
            actor_id=str(row.actor),
            occurred_on=_aware(row.occurred_on) or datetime.now(timezone.utc),
            reason=str(row.reason or ""),
            request_id=str(row.request or "") or None,
        )
        for row in document.events or []
    )
    return StoredPhoneAccess(
        access_id=str(document.name),
        customer_id=str(document.customer),
        normalized_phone=str(document.normalized_phone),
        status=str(document.status),
        approved_by=str(document.approved_by or "") or None,
        approved_on=_aware(document.approved_on),
        revoked_by=str(document.revoked_by or "") or None,
        revoked_on=_aware(document.revoked_on),
        revoke_reason=str(document.revoke_reason or ""),
        events=events,
    )


def _event_row(event: AccessEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "actor": event.actor_id,
        "occurred_on": _persist_datetime(event.occurred_on),
        "reason": event.reason,
        "request": event.request_id,
    }


def _aware(value: object) -> datetime | None:
    if not value:
        return None
    parsed = value if isinstance(value, datetime) else get_datetime(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _persist_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


__all__ = ["FrappePhoneAccessStore"]
