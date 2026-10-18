"""Behavior of customer identity and additional-phone decisions.

The store here is in memory. It shows the decision rules and that a repeated
call does not invent a second grant. Database uniqueness, row locks, and the
Frappe permission hooks are covered by the integration module.
"""

from __future__ import annotations

import inspect
import socket
import unittest
import urllib.request
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from threading import RLock
from typing import Iterator
from unittest.mock import patch

from almdina_erp.almdina_erp.application.customer_bot.phone_access_commands import (
    approve_phone_access_request,
    reject_phone_access_request,
    request_additional_phone_access,
    revoke_phone_access,
)
from almdina_erp.almdina_erp.application.customer_bot.resolve_customer_identity import (
    resolve_customer_identity,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import (
    AccessBasis,
    IdentityCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_access import (
    AccessStatus,
    DecisionCode,
    PhoneAccessDuplicate,
    RequestCode,
    RequestStatus,
    StoredPhoneAccess,
    StoredPhoneRequest,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    normalize_customer_phone,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CUSTOMER_BOT_PHONE_ACCESS_DOCTYPE,
    CUSTOMER_BOT_PHONE_REQUEST_DOCTYPE,
    FACTORY_SETTINGS_CAPABILITIES,
    Capability,
)


NOW = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
PRIMARY = "+963944111111"
ADDITIONAL = "+963955222222"
LATER = datetime(2026, 10, 18, 11, 0, tzinfo=timezone.utc)


def _forbid_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("customer-bot phone tests must not open a network connection")


class MemoryDirectory:
    def __init__(self, phones: dict[str, tuple[str, ...]], existing: set[str] | None = None) -> None:
        self.phones = phones
        self.existing = existing

    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        return self.phones.get(normalized_phone, ())

    def customer_exists(self, customer_id: str) -> bool:
        if self.existing is None:
            return True
        return customer_id in self.existing


class MemoryPolicy:
    def __init__(self, managers: set[str], customers: dict[str, set[str]]) -> None:
        self.managers = managers
        self.customers = customers

    def has_manage_access(self, actor_id: str) -> bool:
        return actor_id in self.managers

    def can_access_customer(self, actor_id: str, customer_id: str) -> bool:
        allowed = self.customers.get(actor_id, set())
        return "*" in allowed or customer_id in allowed


class MemoryStore:
    """Single-process stand-in. Its lock is not a database transaction."""

    def __init__(self) -> None:
        self.requests: dict[str, StoredPhoneRequest] = {}
        self.access_rows: dict[str, StoredPhoneAccess] = {}
        self._sequence = 0
        self._guard = RLock()
        self.fail_next_request_insert = False

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        with self._guard:
            yield

    def lock_request(self, request_id: str) -> StoredPhoneRequest | None:
        return self.requests.get(request_id)

    def lock_access_by_phone(self, normalized_phone: str) -> StoredPhoneAccess | None:
        return self.get_access_by_phone(normalized_phone)

    def pending_for_phone(self, normalized_phone: str) -> StoredPhoneRequest | None:
        for request in self.requests.values():
            if request.status == RequestStatus.PENDING and request.requested_phone == normalized_phone:
                return request
        return None

    def get_access_by_phone(self, normalized_phone: str) -> StoredPhoneAccess | None:
        for access in self.access_rows.values():
            if access.normalized_phone == normalized_phone:
                return access
        return None

    def insert_request(self, request: StoredPhoneRequest) -> StoredPhoneRequest:
        if self.fail_next_request_insert:
            self.fail_next_request_insert = False
            raise PhoneAccessDuplicate()
        if self.pending_for_phone(request.requested_phone) is not None:
            raise PhoneAccessDuplicate()
        self._sequence += 1
        stored = StoredPhoneRequest(
            request_id=f"CBPR-{self._sequence:05d}",
            requested_phone=request.requested_phone,
            claimed_primary_phone=request.claimed_primary_phone,
            proposed_customer_id=request.proposed_customer_id,
            status=request.status,
            requester_ref=request.requester_ref,
            decided_by=request.decided_by,
            decided_on=request.decided_on,
            decision_note=request.decision_note,
            access_id=request.access_id,
        )
        self.requests[stored.request_id] = stored
        return stored

    def save_request(self, request: StoredPhoneRequest) -> StoredPhoneRequest:
        self.requests[request.request_id] = request
        return request

    def insert_access(self, access: StoredPhoneAccess) -> StoredPhoneAccess:
        if self.get_access_by_phone(access.normalized_phone) is not None:
            raise PhoneAccessDuplicate()
        self._sequence += 1
        stored = StoredPhoneAccess(
            access_id=f"CBPA-{self._sequence:05d}",
            customer_id=access.customer_id,
            normalized_phone=access.normalized_phone,
            status=access.status,
            approved_by=access.approved_by,
            approved_on=access.approved_on,
            revoked_by=access.revoked_by,
            revoked_on=access.revoked_on,
            revoke_reason=access.revoke_reason,
            events=access.events,
        )
        self.access_rows[stored.access_id] = stored
        return stored

    def save_access(self, access: StoredPhoneAccess) -> StoredPhoneAccess:
        self.access_rows[access.access_id] = access
        return access


class CustomerBotPhoneAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._socket = patch("socket.create_connection", _forbid_network)
        self._url = patch("urllib.request.urlopen", _forbid_network)
        self._socket.start()
        self._url.start()
        self.addCleanup(self._socket.stop)
        self.addCleanup(self._url.stop)

    def test_syrian_forms_share_one_e164_value(self) -> None:
        expected = "+963944111111"
        for raw in (
            "0944111111",
            "944111111",
            "963944111111",
            "+963944111111",
            "00963944111111",
            "00963 944-111-111",
            "+963 (944) 111.111",
            "0944 111 111",
        ):
            self.assertEqual(normalize_customer_phone(raw), expected)

    def test_explicit_international_is_not_rewritten_as_syrian(self) -> None:
        self.assertEqual(normalize_customer_phone("+1 202 555 0123"), "+12025550123")
        self.assertEqual(normalize_customer_phone("00442079460958"), "+442079460958")
        with self.assertRaises(Exception) as bare:
            normalize_customer_phone("12025550123")
        self.assertEqual(bare.exception.code, "invalid_phone")

    def test_invalid_phones_and_provider_ids_are_refused(self) -> None:
        for raw in ("", "   ", "abc", "09", "+963123", 944111111, None):
            with self.assertRaises(Exception) as caught:
                normalize_customer_phone(raw)
            self.assertEqual(caught.exception.code, "invalid_phone")
        for raw in ("963944111111@c.us", "foo@lid", "@c.us"):
            with self.assertRaises(Exception) as caught:
                normalize_customer_phone(raw)
            self.assertEqual(caught.exception.code, "provider_identifier")

    def test_resolve_signature_has_no_verified_flag(self) -> None:
        parameters = inspect.signature(resolve_customer_identity).parameters
        self.assertNotIn("verified", parameters)
        self.assertEqual(tuple(parameters), ("directory", "store", "phone"))

    def test_one_primary_match_is_allowed_without_orders_or_costs(self) -> None:
        identity = resolve_customer_identity(
            MemoryDirectory({PRIMARY: ("CUST-1",)}),
            MemoryStore(),
            "0944 111 111",
        )
        self.assertEqual(identity.code, IdentityCode.ALLOWED)
        self.assertEqual(identity.customer_id, "CUST-1")
        self.assertEqual(identity.access_basis, AccessBasis.PRIMARY)
        names = {item.name for item in fields(identity)}
        self.assertEqual(names, {"code", "customer_id", "access_basis"})

    def test_unknown_and_duplicate_primary_reveal_no_customer(self) -> None:
        unknown = resolve_customer_identity(MemoryDirectory({}), MemoryStore(), "0944111111")
        conflict = resolve_customer_identity(
            MemoryDirectory({PRIMARY: ("CUST-1", "CUST-2")}),
            MemoryStore(),
            PRIMARY,
        )
        self.assertEqual(unknown.code, IdentityCode.UNKNOWN)
        self.assertIsNone(unknown.customer_id)
        self.assertEqual(conflict.code, IdentityCode.CONFLICT)
        self.assertIsNone(conflict.customer_id)
        self.assertIsNone(conflict.access_basis)

    def test_request_does_not_grant_access_until_approval(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        created = request_additional_phone_access(
            directory,
            store,
            requested_phone="0955 222 222",
            claimed_primary_phone="0944111111",
            requester_ref_value="gateway-event-1",
            now=NOW,
        )
        self.assertEqual(created.code, RequestCode.REVIEW_REQUESTED)
        self.assertIsNotNone(created.request_id)
        self.assertIsNone(getattr(created, "customer_id", None))
        self.assertEqual(store.requests[created.request_id].status, RequestStatus.PENDING)
        self.assertEqual(store.requests[created.request_id].proposed_customer_id, "CUST-1")
        self.assertEqual(store.access_rows, {})
        before = resolve_customer_identity(directory, store, ADDITIONAL)
        self.assertEqual(before.code, IdentityCode.UNKNOWN)
        self.assertIsNone(before.customer_id)

    def test_approve_reject_and_revoke(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        policy = MemoryPolicy({"employee-1"}, {"employee-1": {"CUST-1"}})
        created = self._request(directory, store)
        rejected = reject_phone_access_request(
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=NOW,
            decision_note="لم يتطابق الاسم",
        )
        self.assertEqual(rejected.code, DecisionCode.REJECTED)
        self.assertEqual(store.access_rows, {})
        again = reject_phone_access_request(
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=LATER,
            decision_note="مرة ثانية",
        )
        self.assertEqual(again.code, DecisionCode.ALREADY_APPLIED)

        second = self._request(directory, store, source="gateway-event-2")
        approved = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=second.request_id or "",
            now=NOW,
            decision_note="تم التحقق هاتفيًا",
        )
        self.assertEqual(approved.code, DecisionCode.APPROVED)
        self.assertEqual(len(store.access_rows), 1)
        access = store.get_access_by_phone(ADDITIONAL)
        assert access is not None
        self.assertEqual(access.status, AccessStatus.ACTIVE)
        self.assertEqual(access.customer_id, "CUST-1")
        allowed = resolve_customer_identity(directory, store, "00963 955 222 222")
        self.assertEqual(allowed.code, IdentityCode.ALLOWED)
        self.assertEqual(allowed.access_basis, AccessBasis.ADDITIONAL)
        self.assertEqual(allowed.customer_id, "CUST-1")

        revoked = revoke_phone_access(
            store,
            policy,
            actor_id="employee-1",
            phone=ADDITIONAL,
            now=LATER,
            reason="الزبون طلب الإيقاف",
        )
        self.assertEqual(revoked.code, DecisionCode.REVOKED)
        access = store.get_access_by_phone(ADDITIONAL)
        assert access is not None
        self.assertEqual(access.status, AccessStatus.REVOKED)
        self.assertEqual(access.revoked_by, "employee-1")
        after = resolve_customer_identity(directory, store, ADDITIONAL)
        self.assertEqual(after.code, IdentityCode.UNKNOWN)
        self.assertIsNone(after.customer_id)
        repeated = revoke_phone_access(
            store,
            policy,
            actor_id="employee-1",
            phone=ADDITIONAL,
            now=LATER,
            reason="محاولة ثانية",
        )
        self.assertEqual(repeated.code, DecisionCode.ALREADY_APPLIED)
        self.assertEqual(len(store.get_access_by_phone(ADDITIONAL).events), 2)

    def test_repeat_request_and_repeat_approval_do_not_duplicate_rows(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        policy = MemoryPolicy({"employee-1"}, {"employee-1": {"*"}})
        first = self._request(directory, store)
        second = self._request(directory, store, source="gateway-event-2")
        self.assertEqual(second.code, RequestCode.ALREADY_PENDING)
        self.assertEqual(second.request_id, first.request_id)
        self.assertEqual(len(store.requests), 1)
        different_claim = request_additional_phone_access(
            directory,
            store,
            requested_phone=ADDITIONAL,
            claimed_primary_phone="+963944333333",
            requester_ref_value="gateway-event-3",
            now=NOW,
        )
        self.assertEqual(different_claim.code, RequestCode.PENDING_EXISTS)
        self.assertEqual(len(store.requests), 1)

        approved = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=first.request_id or "",
            now=NOW,
        )
        repeated = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=first.request_id or "",
            now=LATER,
        )
        self.assertEqual(approved.code, DecisionCode.APPROVED)
        self.assertEqual(repeated.code, DecisionCode.ALREADY_APPLIED)
        self.assertEqual(len(store.access_rows), 1)
        self.assertEqual(repeated.access_id, approved.access_id)

    def test_additional_phone_conflicts_with_another_customers_primary(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",), ADDITIONAL: ("CUST-2",)})
        store = MemoryStore()
        policy = MemoryPolicy({"employee-1"}, {"employee-1": {"*"}})
        created = self._request(directory, store)
        decision = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=NOW,
        )
        self.assertEqual(decision.code, DecisionCode.CONFLICT)
        self.assertIsNone(decision.access_id)
        self.assertEqual(store.access_rows, {})
        self.assertEqual(store.requests[created.request_id].status, RequestStatus.PENDING)
        identity = resolve_customer_identity(directory, store, ADDITIONAL)
        self.assertEqual(identity.code, IdentityCode.ALLOWED)
        self.assertEqual(identity.customer_id, "CUST-2")
        self.assertEqual(identity.access_basis, AccessBasis.PRIMARY)

    def test_customer_data_is_rechecked_at_approval(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        policy = MemoryPolicy({"employee-1"}, {"employee-1": {"*"}})
        created = self._request(directory, store)
        directory.phones[PRIMARY] = ("CUST-9",)
        changed = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=NOW,
        )
        self.assertEqual(changed.code, DecisionCode.CUSTOMER_CHANGED)
        self.assertEqual(store.access_rows, {})
        self.assertEqual(store.requests[created.request_id].status, RequestStatus.PENDING)

        directory.phones[PRIMARY] = ()
        missing = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=LATER,
        )
        self.assertEqual(missing.code, DecisionCode.CUSTOMER_CHANGED)

    def test_primary_change_invalidates_an_earlier_match(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        before = resolve_customer_identity(directory, store, "0944111111")
        self.assertEqual(before.customer_id, "CUST-1")
        directory.phones = {"+963944999999": ("CUST-1",)}
        after = resolve_customer_identity(directory, store, PRIMARY)
        self.assertEqual(after.code, IdentityCode.UNKNOWN)
        self.assertIsNone(after.customer_id)

    def test_revoked_grant_stays_revoked_until_a_new_approval(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        policy = MemoryPolicy({"employee-1"}, {"employee-1": {"CUST-1"}})
        created = self._request(directory, store)
        approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=NOW,
        )
        revoke_phone_access(
            store,
            policy,
            actor_id="employee-1",
            phone=ADDITIONAL,
            now=LATER,
            reason="إيقاف",
        )
        stale = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=created.request_id or "",
            now=LATER,
        )
        self.assertEqual(stale.code, DecisionCode.ALREADY_DECIDED)
        self.assertEqual(store.get_access_by_phone(ADDITIONAL).status, AccessStatus.REVOKED)

        renewed = self._request(directory, store, source="gateway-event-9")
        decision = approve_phone_access_request(
            directory,
            store,
            policy,
            actor_id="employee-1",
            request_id=renewed.request_id or "",
            now=LATER,
            decision_note="تحقق جديد",
        )
        self.assertEqual(decision.code, DecisionCode.APPROVED)
        self.assertEqual(len(store.access_rows), 1)
        access = store.get_access_by_phone(ADDITIONAL)
        assert access is not None
        self.assertEqual(access.status, AccessStatus.ACTIVE)
        self.assertEqual(access.approved_by, "employee-1")
        self.assertEqual(access.revoked_by, "employee-1")
        self.assertEqual(access.revoke_reason, "إيقاف")
        self.assertEqual([event.event_type for event in access.events], ["Approved", "Revoked", "Reactivated"])

    def test_manage_capability_is_not_implied_by_role_or_whatsapp_settings(self) -> None:
        self.assertNotIn(Capability.MANAGE_CUSTOMER_BOT_ACCESS, FACTORY_SETTINGS_CAPABILITIES)
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        created = self._request(directory, store)
        system_manager = MemoryPolicy(set(), {})
        whatsapp_only = MemoryPolicy(set(), {"whatsapp-user": {"CUST-1"}})
        for policy, actor in (
            (system_manager, "System Manager"),
            (whatsapp_only, "whatsapp-user"),
            (MemoryPolicy({"employee-1"}, {}), "employee-1"),
        ):
            decision = approve_phone_access_request(
                directory,
                store,
                policy,
                actor_id=actor,
                request_id=created.request_id or "",
                now=NOW,
            )
            self.assertEqual(decision.code, DecisionCode.FORBIDDEN)
            self.assertEqual(store.access_rows, {})
        guest = approve_phone_access_request(
            directory,
            store,
            MemoryPolicy({"Guest"}, {"Guest": {"*"}}),
            actor_id="Guest",
            request_id=created.request_id or "",
            now=NOW,
        )
        self.assertEqual(guest.code, DecisionCode.FORBIDDEN)

    def test_projection_keeps_bot_records_read_only(self) -> None:
        for doctype in (CUSTOMER_BOT_PHONE_ACCESS_DOCTYPE, CUSTOMER_BOT_PHONE_REQUEST_DOCTYPE):
            granted = standard_permission_projection(doctype, {Capability.MANAGE_CUSTOMER_BOT_ACCESS: True})
            denied = standard_permission_projection(doctype, {})
            self.assertEqual(granted, {"read": True, "select": True, "create": False, "write": False, "delete": False})
            self.assertEqual(denied["read"], False)
            self.assertEqual(denied["write"], False)

    def test_duplicate_constraint_signal_does_not_create_a_second_request(self) -> None:
        directory = MemoryDirectory({PRIMARY: ("CUST-1",)})
        store = MemoryStore()
        store.fail_next_request_insert = True
        result = self._request(directory, store)
        self.assertEqual(result.code, RequestCode.PENDING_EXISTS)
        self.assertEqual(store.requests, {})

    def test_same_number_as_primary_is_not_a_request(self) -> None:
        result = request_additional_phone_access(
            MemoryDirectory({PRIMARY: ("CUST-1",)}),
            MemoryStore(),
            requested_phone="0944111111",
            claimed_primary_phone="+963944111111",
            requester_ref_value="gateway-event-1",
            now=NOW,
        )
        self.assertEqual(result.code, RequestCode.SAME_AS_PRIMARY)
        self.assertIsNone(result.request_id)

    def test_socket_module_is_not_used_by_the_decision(self) -> None:
        self.assertIs(socket.create_connection, _forbid_network)
        self.assertIs(urllib.request.urlopen, _forbid_network)
        resolve_customer_identity(MemoryDirectory({}), MemoryStore(), "not a phone")

    def _request(self, directory: MemoryDirectory, store: MemoryStore, source: str = "gateway-event-1") -> object:
        return request_additional_phone_access(
            directory,
            store,
            requested_phone=ADDITIONAL,
            claimed_primary_phone=PRIMARY,
            requester_ref_value=source,
            now=NOW,
        )


if __name__ == "__main__":
    unittest.main()
