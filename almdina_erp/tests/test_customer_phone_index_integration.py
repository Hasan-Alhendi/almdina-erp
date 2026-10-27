"""Indexed phone lookup against the current site database.

These tests create synthetic customers and delete them. They do not print
existing customer names. Adopted writes are the Customer document, Data
Import, ``Document.db_set``, ``frappe.client.set_value``, and
``assign_customer_primary_mobile``. Raw SQL is asserted to stay stale.
"""

from __future__ import annotations

import secrets
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.customer_bot.resolve_customer_identity import (
    resolve_customer_identity,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import normalize_customer_phone
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_index import (
    NORMALIZED_MOBILE_FIELD,
    assign_customer_primary_mobile,
    sync_customer_normalized_mobile_index,
)


class TestCustomerPhoneIndexIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        sync_customer_normalized_mobile_index()
        sync_customer_normalized_mobile_index()
        self.customers: list[str] = []
        self.suffix = uuid4().hex[:8]

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for name in self.customers:
            if frappe.db.exists("Customer", name):
                frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
        super().tearDown()

    def test_index_is_non_unique_and_lookup_does_not_scan_every_mobile(self) -> None:
        indexes = frappe.db.sql(
            f"show index from `tabCustomer` where Column_name=%s",
            (NORMALIZED_MOBILE_FIELD,),
            as_dict=True,
        )
        self.assertTrue(indexes)
        self.assertTrue(all(int(row.Non_unique) == 1 for row in indexes))

        phone = self._customer_phone()
        normalized = normalize_customer_phone(phone)
        queries: list[str] = []
        original = frappe.db.sql

        def spy(*args, **kwargs):
            if args:
                queries.append(str(args[0]))
            return original(*args, **kwargs)

        frappe.db.sql = spy
        try:
            found = FrappeCustomerPhoneDirectory().find_by_normalized_phone(normalized)
        finally:
            frappe.db.sql = original
        self.assertEqual(found, (self.customers[-1],))
        customer_queries = [query for query in queries if "tabCustomer" in query]
        self.assertTrue(customer_queries)
        for query in customer_queries:
            self.assertIn(NORMALIZED_MOBILE_FIELD, query)
            self.assertNotIn("mobile_no", query)

    def test_phone_change_duplicate_formats_invalid_values_and_delete(self) -> None:
        directory = FrappeCustomerPhoneDirectory()
        local = self._unused_local()
        normalized = normalize_customer_phone(local)
        owner = self._customer(local)
        self.assertEqual(
            frappe.db.get_value("Customer", owner, NORMALIZED_MOBILE_FIELD),
            normalized,
        )
        self.assertEqual(directory.find_by_normalized_phone(normalized), (owner,))

        moved = self._unused_local()
        moved_normalized = normalize_customer_phone(moved)
        assign_customer_primary_mobile(owner, moved, update_modified=False)
        self.assertEqual(directory.find_by_normalized_phone(normalized), ())
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), (owner,))
        identity = resolve_customer_identity(directory, moved)
        self.assertEqual(identity.code, IdentityCode.ALLOWED)
        self.assertEqual(identity.customer_id, owner)

        other = self._customer(f"00{moved_normalized[1:]}")
        conflict = resolve_customer_identity(directory, f"+{moved_normalized[1:]}")
        self.assertEqual(conflict.code, IdentityCode.CONFLICT)
        self.assertIsNone(conflict.customer_id)
        self.assertCountEqual(
            directory.find_by_normalized_phone(moved_normalized),
            (owner, other),
        )

        invalid = self._customer(self._unused_local())
        invalid_normalized = normalize_customer_phone(
            frappe.db.get_value("Customer", invalid, "mobile_no")
        )
        frappe.get_doc("Customer", invalid).db_set("mobile_no", "not-a-phone")
        self.assertEqual(frappe.db.get_value("Customer", invalid, "mobile_no"), "not-a-phone")
        self.assertEqual(frappe.db.get_value("Customer", invalid, NORMALIZED_MOBILE_FIELD) or "", "")
        self.assertEqual(directory.find_by_normalized_phone(invalid_normalized), ())
        self.assertNotIn(invalid, directory.find_by_normalized_phone(moved_normalized))

        stranger = self._customer(self._unused_local())
        self.assertNotIn(stranger, directory.find_by_normalized_phone(moved_normalized))

        frappe.delete_doc("Customer", other, force=True, ignore_permissions=True)
        self.customers.remove(other)
        restored = resolve_customer_identity(directory, moved_normalized)
        self.assertEqual(restored.code, IdentityCode.ALLOWED)
        self.assertEqual(restored.customer_id, owner)

        assign_customer_primary_mobile(owner, "", update_modified=False)
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), ())
        cleared = resolve_customer_identity(directory, moved_normalized)
        self.assertEqual(cleared.code, IdentityCode.UNKNOWN)
        self.assertIsNone(cleared.customer_id)

    def test_contact_save_releases_the_old_number_and_collides_immediately(self) -> None:
        directory = FrappeCustomerPhoneDirectory()
        first = self._unused_local()
        second = self._unused_local()
        first_normalized = normalize_customer_phone(first)
        second_normalized = normalize_customer_phone(second)
        owner = self._customer(first)
        other = self._customer(second)

        self._save_customer_phone(owner, f"00{second_normalized[1:]}")

        rows = self._stored_phones(owner, other)
        self.assertEqual(
            {normalize_customer_phone(row.mobile_no) for row in rows},
            {second_normalized},
        )
        self.assertEqual({row.normalized for row in rows}, {second_normalized})
        self.assertEqual(directory.find_by_normalized_phone(first_normalized), ())
        identity = resolve_customer_identity(directory, second)
        self.assertEqual(identity.code, IdentityCode.CONFLICT)
        self.assertIsNone(identity.customer_id)
        self.assertCountEqual(
            directory.find_by_normalized_phone(second_normalized),
            (owner, other),
        )

    def test_db_set_client_set_value_and_data_import_update_the_index(self) -> None:
        from frappe.core.doctype.data_import.importer import Importer

        directory = FrappeCustomerPhoneDirectory()
        original = self._unused_local()
        original_normalized = normalize_customer_phone(original)
        owner = self._customer(original)
        commits: list[int] = []
        real_commit = frappe.db.commit

        def spy_commit(*args, **kwargs):
            commits.append(1)
            return real_commit(*args, **kwargs)

        moved = self._unused_local()
        moved_normalized = normalize_customer_phone(moved)
        frappe.db.commit = spy_commit
        try:
            frappe.get_doc("Customer", owner).db_set("mobile_no", moved)
        finally:
            frappe.db.commit = real_commit
        self.assertEqual(commits, [])
        self.assertEqual(
            normalize_customer_phone(frappe.db.get_value("Customer", owner, "mobile_no")),
            moved_normalized,
        )
        self.assertEqual(directory.find_by_normalized_phone(original_normalized), ())
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), (owner,))

        via_client = self._unused_local()
        via_client_normalized = normalize_customer_phone(via_client)
        self._align_primary_contact(owner, via_client)
        frappe.client.set_value("Customer", owner, "mobile_no", via_client)
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), ())
        self.assertEqual(directory.find_by_normalized_phone(via_client_normalized), (owner,))
        self.assertEqual(
            normalize_customer_phone(frappe.db.get_value("Customer", owner, "mobile_no")),
            via_client_normalized,
        )

        imported_phone = self._unused_local()
        imported_normalized = normalize_customer_phone(imported_phone)
        imported = Importer.insert_record(
            self._import_host(),
            frappe._dict(
                doctype="Customer",
                customer_name=f"CBOT Import {self.suffix} {uuid4().hex[:6]}",
                customer_type="Individual",
                customer_group=self._customer_group(),
                territory=self._territory(),
                mobile_no=imported_phone,
            ),
        )
        self.customers.append(imported.name)
        self.assertEqual(directory.find_by_normalized_phone(imported_normalized), (imported.name,))

        replacement = self._unused_local()
        replacement_normalized = normalize_customer_phone(replacement)
        self._align_primary_contact(imported.name, replacement)
        Importer.update_record(
            self._import_host(),
            frappe._dict(name=imported.name, mobile_no=replacement),
        )
        self.assertEqual(directory.find_by_normalized_phone(imported_normalized), ())
        self.assertEqual(directory.find_by_normalized_phone(replacement_normalized), (imported.name,))
        self.assertEqual(
            normalize_customer_phone(frappe.db.get_value("Customer", imported.name, "mobile_no")),
            replacement_normalized,
        )

    def test_raw_sql_and_lone_set_value_stay_outside_lookup(self) -> None:
        directory = FrappeCustomerPhoneDirectory()
        original = self._unused_local()
        original_normalized = normalize_customer_phone(original)
        owner = self._customer(original)
        moved = self._unused_local()
        moved_normalized = normalize_customer_phone(moved)

        frappe.db.sql(
            "update `tabCustomer` set mobile_no=%s where name=%s",
            (moved, owner),
        )
        self.assertEqual(directory.find_by_normalized_phone(original_normalized), (owner,))
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), ())
        queries: list[str] = []
        original_sql = frappe.db.sql

        def spy(*args, **kwargs):
            if args:
                queries.append(str(args[0]))
            return original_sql(*args, **kwargs)

        frappe.db.sql = spy
        try:
            directory.find_by_normalized_phone(moved_normalized)
        finally:
            frappe.db.sql = original_sql
        customer_queries = [query for query in queries if "tabCustomer" in query]
        self.assertTrue(customer_queries)
        for query in customer_queries:
            self.assertNotIn("mobile_no", query)

        frappe.get_doc("Customer", owner).db_set("mobile_no", moved)
        self.assertEqual(directory.find_by_normalized_phone(original_normalized), ())
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), (owner,))

        lone = self._unused_local()
        lone_normalized = normalize_customer_phone(lone)
        frappe.db.set_value("Customer", owner, "mobile_no", lone, update_modified=False)
        self.assertEqual(directory.find_by_normalized_phone(moved_normalized), (owner,))
        self.assertEqual(directory.find_by_normalized_phone(lone_normalized), ())

    def _align_primary_contact(self, customer: str, raw_phone: str) -> None:
        contact_name = frappe.db.get_value("Customer", customer, "customer_primary_contact")
        contact = frappe.get_doc("Contact", contact_name)
        primary = [row for row in contact.phone_nos if row.is_primary_mobile_no]
        if primary:
            primary[0].phone = raw_phone
        else:
            contact.append("phone_nos", {"phone": raw_phone, "is_primary_mobile_no": 1})
        contact.save(ignore_permissions=True)

    def _save_customer_phone(self, customer: str, raw_phone: str) -> None:
        """Follow the Desk path: edit the primary contact, then save the customer."""

        self._align_primary_contact(customer, raw_phone)
        document = frappe.get_doc("Customer", customer)
        document.save(ignore_permissions=True)

    def _stored_phones(self, *names: str):
        placeholders = ", ".join(["%s"] * len(names))
        return frappe.db.sql(
            f"""select name, mobile_no, `{NORMALIZED_MOBILE_FIELD}` as normalized
                from `tabCustomer`
                where name in ({placeholders})""",
            names,
            as_dict=True,
        )

    def _import_host(self):
        return frappe._dict(doctype="Customer", data_import=frappe._dict(doctype="Data Import", name="DI-PHASE1"))

    def _customer_group(self) -> str:
        return self._leaf(
            "Customer Group",
            "customer_group_name",
            "parent_customer_group",
            "All Customer Groups",
        )

    def _territory(self) -> str:
        return self._leaf("Territory", "territory_name", "parent_territory", "All Territories")

    def _leaf(self, doctype: str, name_field: str, parent_field: str, root_name: str) -> str:
        existing = frappe.db.get_value(doctype, {"is_group": 0}, "name")
        if existing:
            return existing
        if not frappe.db.exists(doctype, root_name):
            frappe.get_doc(
                {"doctype": doctype, name_field: root_name, "is_group": 1}
            ).insert(ignore_permissions=True)
        leaf_name = f"CBOT {doctype} {self.suffix}"
        frappe.get_doc(
            {
                "doctype": doctype,
                name_field: leaf_name,
                parent_field: root_name,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
        return leaf_name

    def _customer_phone(self) -> str:
        phone = self._unused_local()
        self._customer(phone)
        return phone

    def _unused_local(self) -> str:
        directory = FrappeCustomerPhoneDirectory()
        for _ in range(40):
            local = f"0988{secrets.randbelow(1_000_000):06d}"
            if directory.find_by_normalized_phone(normalize_customer_phone(local)):
                continue
            return local
        self.fail("no unused synthetic phone was available")

    def _customer(self, mobile: str) -> str:
        document = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"CBOT Index {self.suffix} {uuid4().hex[:6]}",
                "customer_type": "Individual",
                "customer_group": self._customer_group(),
                "territory": self._territory(),
                "mobile_no": mobile,
            }
        ).insert(ignore_permissions=True)
        self.customers.append(document.name)
        return document.name


__all__ = ["TestCustomerPhoneIndexIntegration"]
