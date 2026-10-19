"""Database proof for customer-bot phone access.

These tests use synthetic customers and users only. They commit only the
concurrency fixtures, then delete those rows. They do not read or print
existing customer names.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone
from uuid import uuid4

import frappe
from frappe.client import set_value
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    normalize_customer_phone,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_access_gateway import (
    approve_additional_phone_request,
    reject_additional_phone_request,
    resolve_customer_phone,
    revoke_additional_phone,
    submit_additional_phone_request,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_phone_repository import (
    FrappePhoneAccessStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_records import (
    PHONE_ACCESS_DOCTYPE,
    PHONE_REQUEST_DOCTYPE,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


NOW = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
ACCESS_TABLE = "tabCustomer Bot Phone Access"
REQUEST_TABLE = "tabCustomer Bot Phone Request"


class TestCustomerBotPhoneAccessIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        sync_permission_types()
        self.committed = False
        self.customers: list[str] = []
        self.phones: list[str] = []
        self.users: list[str] = []
        self.roles: list[str] = []
        self.suffix = uuid4().hex[:8]

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        self._purge()
        if self.committed:
            frappe.db.commit()
        super().tearDown()

    def test_unique_indexes_are_database_constraints(self) -> None:
        access_indexes = frappe.db.sql(
            f"show index from `{ACCESS_TABLE}` where Column_name='normalized_phone' and Non_unique=0"
        )
        pending_indexes = frappe.db.sql(
            f"show index from `{REQUEST_TABLE}` where Column_name='pending_phone_key' and Non_unique=0"
        )
        self.assertTrue(access_indexes)
        self.assertTrue(pending_indexes)

    def test_savepoint_rolls_back_a_failed_request_insert(self) -> None:
        requested = self._unused_phone()
        claimed = self._unused_phone()
        store = FrappePhoneAccessStore()
        try:
            with store.exclusive():
                store.insert_request(self._memory_request(requested, claimed))
                raise RuntimeError("force savepoint rollback")
        except RuntimeError:
            pass
        self.assertFalse(
            frappe.db.exists(PHONE_REQUEST_DOCTYPE, {"requested_phone": normalize_customer_phone(requested)})
        )

    def test_direct_crud_import_and_set_value_are_rejected(self) -> None:
        from almdina_erp.almdina_erp.domain.customer_bot.phone_access import StoredPhoneAccess

        customer = self._customer(self._unused_phone())
        requested = normalize_customer_phone(self._unused_phone())
        self.phones.append(requested)
        access = FrappePhoneAccessStore().insert_access(
            StoredPhoneAccess(
                access_id="",
                customer_id=customer,
                normalized_phone=requested,
                status="Active",
                approved_by="Administrator",
                approved_on=NOW,
                revoked_by=None,
                revoked_on=None,
                revoke_reason="",
                events=(),
            )
        )
        access_id = access.access_id
        self.assertTrue(access_id)

        document = frappe.get_doc(PHONE_ACCESS_DOCTYPE, access_id)
        document.status = "Revoked"
        with self.assertRaises(frappe.PermissionError):
            document.save()
        self.assertEqual(frappe.db.get_value(PHONE_ACCESS_DOCTYPE, access_id, "status"), "Active")

        with self.assertRaises(frappe.PermissionError):
            set_value(PHONE_ACCESS_DOCTYPE, access_id, "status", "Revoked")
        self.assertEqual(frappe.db.get_value(PHONE_ACCESS_DOCTYPE, access_id, "status"), "Active")

        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc(PHONE_ACCESS_DOCTYPE, access_id, force=True)

        self.assertEqual(frappe.get_meta(PHONE_REQUEST_DOCTYPE).allow_import, 0)
        frappe.flags.in_import = True
        try:
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc(
                    {
                        "doctype": PHONE_REQUEST_DOCTYPE,
                        "requested_phone": self._unused_phone(),
                        "claimed_primary_phone": frappe.db.get_value("Customer", customer, "mobile_no"),
                        "status": "Pending",
                        "requester_ref": "import",
                    }
                ).insert(ignore_permissions=True)
        finally:
            frappe.flags.in_import = False

        holder = self._user_with(
            {Capability.MANAGE_CUSTOMER_BOT_ACCESS: True, Capability.VIEW_CUSTOMERS: True}
        )
        frappe.set_user(holder)
        self.assertFalse(frappe.has_permission(PHONE_ACCESS_DOCTYPE, ptype="read", user=holder))
        self.assertFalse(frappe.has_permission(PHONE_ACCESS_DOCTYPE, ptype="write", user=holder))
        with self.assertRaises(frappe.PermissionError):
            frappe.get_list(PHONE_ACCESS_DOCTYPE, filters={"name": access_id}, pluck="name")
        frappe.set_user("Administrator")
        self.assertTrue(frappe.db.exists(PHONE_ACCESS_DOCTYPE, access_id))

    def test_retired_commands_do_not_write_and_grants_do_not_identify(self) -> None:
        from almdina_erp.almdina_erp.application.customer_bot.phone_access_commands import (
            PhoneAccessRetired,
        )
        from almdina_erp.almdina_erp.domain.customer_bot.phone_access import StoredPhoneAccess

        customer = self._customer(self._unused_phone())
        primary = frappe.db.get_value("Customer", customer, "mobile_no")
        additional = self._unused_phone()
        normalized_additional = normalize_customer_phone(additional)
        for call in (
            lambda: submit_additional_phone_request(
                requested_phone=additional,
                claimed_primary_phone=primary,
                requester_ref_value=f"cbot-{self.suffix}",
                now=NOW,
            ),
            lambda: approve_additional_phone_request(
                actor_id="Administrator",
                request_id="CBPR-00050",
                now=NOW,
                decision_note="retired",
            ),
            lambda: reject_additional_phone_request(
                actor_id="Administrator",
                request_id="CBPR-00050",
                now=NOW,
                decision_note="retired",
            ),
            lambda: revoke_additional_phone(
                actor_id="Administrator",
                phone=additional,
                now=NOW,
                reason="retired",
            ),
        ):
            with self.assertRaises(PhoneAccessRetired):
                call()
        self.assertFalse(
            frappe.db.exists(PHONE_REQUEST_DOCTYPE, {"requester_ref": f"cbot-{self.suffix}"})
        )

        FrappePhoneAccessStore().insert_access(
            StoredPhoneAccess(
                access_id="",
                customer_id=customer,
                normalized_phone=normalized_additional,
                status="Active",
                approved_by="Administrator",
                approved_on=NOW,
                revoked_by=None,
                revoked_on=None,
                revoke_reason="",
                events=(),
            )
        )
        granted = resolve_customer_phone(additional)
        self.assertEqual(granted.code, "unknown")
        self.assertIsNone(granted.customer_id)
        primary_identity = resolve_customer_phone(primary)
        self.assertEqual(primary_identity.code, "allowed")
        self.assertEqual(primary_identity.customer_id, customer)
        self.assertEqual(primary_identity.access_basis, "primary")
        frappe.db.set_value("Customer", customer, "mobile_no", self._unused_phone(), update_modified=False)
        moved = resolve_customer_phone(primary)
        self.assertEqual(moved.code, "unknown")
        self.assertIsNone(moved.customer_id)

    def test_directory_matches_stored_variants_and_reports_conflict(self) -> None:
        first = self._unused_phone()
        normalized = normalize_customer_phone(first)
        customer = self._customer(f"00{normalized[1:]}")
        identity = resolve_customer_phone(first)
        self.assertEqual(identity.code, "allowed")
        self.assertEqual(identity.customer_id, customer)
        self.assertEqual(identity.access_basis, "primary")

        other = self._customer(f"+{normalized[1:]}")
        conflict = resolve_customer_phone(normalized)
        self.assertEqual(conflict.code, "conflict")
        self.assertIsNone(conflict.customer_id)
        self.assertNotEqual(customer, other)

        frappe.db.set_value("Customer", customer, "mobile_no", self._unused_phone(), update_modified=False)
        frappe.db.set_value("Customer", other, "mobile_no", self._unused_phone(), update_modified=False)
        unknown = resolve_customer_phone(normalized)
        self.assertEqual(unknown.code, "unknown")
        self.assertIsNone(unknown.customer_id)

    def test_gateway_functions_are_not_guest_endpoints(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe import customer_bot_access_gateway as gateway

        for name in (
            "resolve_customer_phone",
            "submit_additional_phone_request",
            "approve_additional_phone_request",
            "reject_additional_phone_request",
            "revoke_additional_phone",
        ):
            function = getattr(gateway, name)
            self.assertFalse(getattr(function, "allow_guest", False))
            self.assertNotIn(function, frappe.whitelisted)

    def _race(self, operation) -> list[object]:
        site = frappe.local.site
        sites_path = frappe.local.sites_path
        barrier = threading.Barrier(2)
        results: list[object] = [None, None]

        def worker(index: int) -> None:
            frappe.init(site, sites_path=sites_path, force=True)
            frappe.connect()
            frappe.flags.mute_emails = True
            try:
                barrier.wait(timeout=15)
                results[index] = operation()
                frappe.db.commit()
            except Exception as error:  # pragma: no cover - reported as the result
                frappe.db.rollback()
                results[index] = error
            finally:
                frappe.destroy()

        threads = [threading.Thread(target=worker, args=(index,)) for index in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(40)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        return results

    def _unused_phone(self) -> str:
        directory = FrappeCustomerPhoneDirectory()
        for _ in range(30):
            local = f"09{secrets.randbelow(90_000_000) + 10_000_000}"
            normalized = normalize_customer_phone(local)
            if directory.find_by_normalized_phone(normalized):
                continue
            self.phones.append(normalized)
            return local
        self.fail("no unused synthetic phone was available")

    def _customer(self, mobile: str) -> str:
        suffix = uuid4().hex[:10]
        group = frappe.db.get_single_value("Selling Settings", "customer_group") or "Individual"
        if frappe.db.get_value("Customer Group", group, "is_group"):
            group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
        territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
        if frappe.db.get_value("Territory", territory, "is_group"):
            territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
        document = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"CBOT Fixture {suffix}",
                "customer_type": "Individual",
                "customer_group": group,
                "territory": territory,
                "mobile_no": mobile,
            }
        ).insert(ignore_permissions=True)
        self.customers.append(document.name)
        return document.name

    def _user_with(self, capabilities: dict[str, bool]) -> str:
        role = f"CBOT Role {uuid4().hex[:8]}"
        self._ensure_role(role)
        self.roles.append(role)
        FrappePermissionMatrixRepository().save_role_state(role, capabilities)
        return self._user_with_roles([role])

    def _user_with_roles(self, roles: list[str]) -> str:
        email = f"cbot.{uuid4().hex[:8]}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "CBOT",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
            }
        ).insert(ignore_permissions=True)
        for role in roles:
            if role == "System Manager":
                self._ensure_role(role)
            user.append("roles", {"role": role})
        user.save(ignore_permissions=True)
        self.users.append(email)
        frappe.clear_cache(user=email)
        return email

    def _ensure_role(self, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

    def _memory_request(self, requested: str, claimed: str):
        from almdina_erp.almdina_erp.domain.customer_bot.phone_access import StoredPhoneRequest

        return StoredPhoneRequest(
            request_id="",
            requested_phone=normalize_customer_phone(requested),
            claimed_primary_phone=normalize_customer_phone(claimed),
            proposed_customer_id=None,
            status="Pending",
            requester_ref=f"cbot-{self.suffix}",
            decided_by=None,
            decided_on=None,
            decision_note="",
            access_id=None,
        )

    def _purge(self) -> None:
        frappe.set_user("Administrator")
        if self.committed:
            frappe.db.rollback()
        if self.phones:
            access_names = frappe.db.sql(
                f"select name from `{ACCESS_TABLE}` where normalized_phone in %s",
                [self.phones],
            )
            for (name,) in access_names:
                frappe.db.sql("delete from `tabCustomer Bot Phone Access Event` where parent=%s", name)
                frappe.db.sql(f"delete from `{ACCESS_TABLE}` where name=%s", name)
            frappe.db.sql(
                f"delete from `{REQUEST_TABLE}` where requested_phone in %s",
                [self.phones],
            )
        for customer in self.customers:
            if frappe.db.exists("Customer", customer):
                frappe.delete_doc("Customer", customer, force=True, ignore_permissions=True)
        for email in self.users:
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        for role in self.roles:
            frappe.db.delete("Custom DocPerm", {"role": role})
            if role != "System Manager" and frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        if self.committed:
            frappe.db.commit()
