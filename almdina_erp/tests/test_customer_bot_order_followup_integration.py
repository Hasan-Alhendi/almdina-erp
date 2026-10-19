"""MariaDB proof for customer-bot order reading.

Synthetic customers and orders are created inside the test transaction and
removed afterward. Existing site customers, including earlier bot fixtures,
are not selected for cleanup.
"""

from __future__ import annotations

import secrets
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.customer_bot.read_customer_orders import (
    list_current_customer_orders,
    select_customer_order_by_name,
)
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    CurrentOrderListOutcome,
    OrderSelectionOutcome,
    PublicOrderStatus,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    normalize_customer_phone,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_order_gateway import (
    list_current_orders_for_phone,
    select_order_for_phone,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_order_reader import (
    FrappeCustomerOrderReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)


class TestCustomerBotOrderFollowupIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.suffix = uuid4().hex[:8]
        self.customers: list[str] = []
        self.orders: list[str] = []
        self.stages: list[str] = []
        self.routes: list[str] = []
        self.definitions: list[str] = []
        self.edges: list[str] = []
        self.roles: list[str] = []
        self.grants: list[str] = []
        self.phones: list[str] = []

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for name in self.stages:
            frappe.delete_doc("Production Stage", name, force=1, ignore_permissions=True)
        for name in self.orders:
            frappe.delete_doc("Door Cutting Order", name, force=1, ignore_permissions=True)
        for name in self.routes:
            frappe.delete_doc("Production Routing", name, force=1, ignore_permissions=True)
        for name in self.definitions:
            frappe.delete_doc(
                "Production Stage Definition", name, force=1, ignore_permissions=True
            )
        for name in self.edges:
            frappe.delete_doc("Edge Banding Type", name, force=1, ignore_permissions=True)
        for name in self.grants:
            frappe.db.sql(
                "DELETE FROM `tabCustomer Bot Phone Access` WHERE name = %s",
                (name,),
            )
        for name in self.customers:
            frappe.delete_doc("Customer", name, force=1, ignore_permissions=True)
        for name in self.roles:
            frappe.delete_doc("Role", name, force=1, ignore_permissions=True)
        super().tearDown()

    def test_database_list_is_customer_scoped_paged_and_sorted(self) -> None:
        phone = self._unused_phone()
        customer = self._customer(phone)
        other_phone = self._unused_phone()
        other = self._customer(other_phone)
        current = [
            self._order(customer, order_date="2026-10-01")
            for _index in range(25)
        ]
        self._order(other, order_date="2026-10-18")
        delivered = self._order(customer, order_date="2026-10-18")
        cancelled = self._order(customer, order_date="2026-10-18")
        superseded = self._order(customer, order_date="2026-10-18")
        pending = self._order(customer, order_date="2026-10-18")
        frappe.db.set_value("Door Cutting Order", delivered, "status", "Delivered")
        frappe.db.set_value("Door Cutting Order", cancelled, "status", "Cancelled")
        frappe.db.set_value(
            "Door Cutting Order", superseded, "revision_state", "Superseded"
        )
        frappe.db.set_value(
            "Door Cutting Order", pending, "revision_state", "Pending Activation"
        )
        marker = f"SECRET-NOTE-{self.suffix}"
        frappe.db.set_value("Door Cutting Order", current[0], "order_notes", marker)
        frappe.db.set_value("Door Cutting Order", current[0], "mdf_cost_usd", 98765.43)
        before = {
            name: frappe.db.get_value("Door Cutting Order", name, "modified")
            for name in self.orders
        }
        reader = FrappeCustomerOrderReader(page_size=10)
        captured: list[tuple[object, object]] = []
        original = frappe.db.sql

        def wrapped(query, *args, **kwargs):
            captured.append((query, args))
            return original(query, *args, **kwargs)

        frappe.db.sql = wrapped
        try:
            listed = list_current_customer_orders(
                FrappeCustomerPhoneDirectory(),
                reader,
                reader,
                reader,
                phone,
            )
        finally:
            frappe.db.sql = original

        self.assertEqual(listed.outcome, CurrentOrderListOutcome.MANY)
        self.assertEqual(len(listed.orders), 25)
        self.assertEqual(
            tuple(item.order_name for item in listed.orders),
            tuple(sorted(current, reverse=True)),
        )
        self.assertNotIn(marker, repr(listed))
        self.assertNotIn("98765.43", repr(listed))
        after = {
            name: frappe.db.get_value("Door Cutting Order", name, "modified")
            for name in self.orders
        }
        self.assertEqual(before, after)
        list_queries = [
            (str(query), args)
            for query, args in captured
            if "tabDoor Cutting Order" in str(query) and "customer = %s" in str(query)
        ]
        self.assertEqual(len(list_queries), 3)
        for query, args in list_queries:
            self.assertIn(customer, args[0] if args else ())
            self.assertNotIn("LIKE", str(query).upper())
            self.assertNotIn(other, str(args))
        self.assertTrue(
            all("UPDATE" not in str(query).upper() for query, _args in captured)
        )

    def test_status_selection_ownership_and_phone_change_use_the_database(self) -> None:
        phone = self._unused_phone()
        customer = self._customer(phone)
        other = self._customer(self._unused_phone())
        route, middle_code, last_code = self._route()
        draft = self._order(customer)
        middle = self._order(customer)
        ready = self._order(customer)
        delivered = self._order(customer)
        cancelled = self._order(customer)
        superseded = self._order(customer)
        pending = self._order(customer)
        foreign = self._order(other)
        self._point_stage(middle, route, middle_code, "Completed")
        self._point_stage(ready, route, last_code, "Completed")
        frappe.db.set_value("Door Cutting Order", delivered, "status", "Delivered")
        frappe.db.set_value("Door Cutting Order", cancelled, "status", "Cancelled")
        frappe.db.set_value(
            "Door Cutting Order", superseded, "revision_state", "Superseded"
        )
        frappe.db.set_value(
            "Door Cutting Order", pending, "revision_state", "Pending Activation"
        )
        frappe.db.set_value(
            "Door Cutting Order", draft, "current_assignee", "staff-hidden@example.com"
        )
        frappe.db.set_value(
            "Production Stage",
            frappe.db.get_value("Door Cutting Order", middle, "current_production_stage"),
            "notes",
            f"STAFF-NOTE-{self.suffix}",
        )
        directory = FrappeCustomerPhoneDirectory()
        reader = FrappeCustomerOrderReader()
        listed = list_current_customer_orders(directory, reader, reader, reader, phone)
        names = {item.order_name for item in listed.orders}
        self.assertEqual(
            names, {draft, middle, ready}
        )
        by_name = {item.order_name: item.public_status for item in listed.orders}
        self.assertEqual(by_name[draft], PublicOrderStatus.AWAITING_START)
        self.assertEqual(by_name[middle], PublicOrderStatus.IN_PROGRESS)
        self.assertEqual(by_name[ready], PublicOrderStatus.READY_FOR_PICKUP)
        self.assertNotIn(f"STAFF-NOTE-{self.suffix}", repr(listed))
        self.assertNotIn("staff-hidden@example.com", repr(listed))

        delivered_selection = select_order_for_phone(phone, delivered)
        self.assertEqual(delivered_selection.outcome, OrderSelectionOutcome.SELECTED)
        self.assertEqual(delivered_selection.public_status, PublicOrderStatus.DELIVERED)
        cancelled_selection = select_customer_order_by_name(
            directory, reader, reader, reader, phone, cancelled
        )
        self.assertEqual(cancelled_selection.outcome, OrderSelectionOutcome.CANCELLED)
        self.assertNotIn("98765", repr(cancelled_selection))
        missing = select_order_for_phone(phone, f"CBOT-ABSENT-{self.suffix}")
        foreign_selection = select_order_for_phone(phone, foreign)
        self.assertEqual(missing, foreign_selection)
        self.assertEqual(missing.outcome, OrderSelectionOutcome.NOT_FOUND)
        partial = select_order_for_phone(phone, delivered[:-1])
        self.assertEqual(partial, missing)
        old_copy = select_order_for_phone(phone, superseded)
        self.assertEqual(old_copy.outcome, OrderSelectionOutcome.NOT_CURRENT)
        self.assertEqual(old_copy.order_name, superseded)
        self.assertIsNone(old_copy.public_status)
        self.assertEqual(
            select_order_for_phone(phone, pending).outcome,
            OrderSelectionOutcome.NOT_CURRENT,
        )

        grant_phone = self._unused_phone()
        self._grant(customer, normalize_customer_phone(grant_phone))
        refused = list_current_orders_for_phone(grant_phone)
        self.assertEqual(refused.outcome, CurrentOrderListOutcome.IDENTITY_UNAVAILABLE)

        moved = self._unused_phone()
        frappe.db.set_value("Customer", customer, "mobile_no", moved)
        stale = list_current_orders_for_phone(phone)
        current = list_current_orders_for_phone(moved)
        self.assertEqual(stale.outcome, CurrentOrderListOutcome.IDENTITY_UNAVAILABLE)
        self.assertEqual(current.outcome, CurrentOrderListOutcome.MANY)
        self.assertEqual({item.order_name for item in current.orders}, names)

    def _unused_phone(self) -> str:
        directory = FrappeCustomerPhoneDirectory()
        for _attempt in range(30):
            local = f"0988{secrets.randbelow(1_000_000):06d}"
            if directory.find_by_normalized_phone(normalize_customer_phone(local)):
                continue
            self.phones.append(local)
            return local
        self.fail("no unused synthetic phone was available")

    def _customer(self, mobile: str) -> str:
        group = frappe.db.get_single_value("Selling Settings", "customer_group") or "Individual"
        if frappe.db.get_value("Customer Group", group, "is_group"):
            group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
        territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
        if frappe.db.get_value("Territory", territory, "is_group"):
            territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
        document = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"CBOT Read {self.suffix} {mobile[-4:]}",
                "customer_type": "Individual",
                "customer_group": group,
                "territory": territory,
                "mobile_no": mobile,
            }
        ).insert(ignore_permissions=True)
        self.customers.append(document.name)
        return document.name

    def _order(self, customer: str, order_date: str | None = None) -> str:
        document = frappe.get_doc(
            {
                "doctype": "Door Cutting Order",
                "customer": customer,
                "order_date": order_date or "2026-10-01",
                "board_description": f"CBOT read board {self.suffix}",
                "board_length_cm": 244,
                "board_width_cm": 122,
                "default_edge_type": self._edge(),
                "edge_color": "White",
                "pieces": [
                    {"piece_type": "Regular", "width_cm": 40, "length_cm": 80, "qty": 1}
                ],
            }
        ).insert(ignore_permissions=True)
        self.orders.append(document.name)
        if order_date:
            frappe.db.set_value(
                "Door Cutting Order", document.name, "order_date", order_date
            )
        return document.name

    def _edge(self) -> str:
        if self.edges:
            return self.edges[0]
        document = frappe.get_doc(
            {
                "doctype": "Edge Banding Type",
                "edge_type_name": f"CBOT Read Edge {self.suffix}",
                "english_name": f"CBOT Read Edge {self.suffix}",
                "width_cm": 2,
                "thickness_mm": 1,
                "rate_usd_per_meter": 1,
            }
        ).insert(ignore_permissions=True)
        self.edges.append(document.name)
        return document.name

    def _route(self) -> tuple[str, str, str]:
        role = frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": f"CBOT Read Role {self.suffix}",
                "desk_access": 0,
            }
        ).insert(ignore_permissions=True)
        self.roles.append(role.name)
        middle = self._definition("middle")
        last = self._definition("last")
        document = frappe.get_doc(
            {
                "doctype": "Production Routing",
                "routing_name": f"CBOT Read Route {self.suffix}",
                "stages": [
                    {
                        "sequence": 10,
                        "stage_definition": middle,
                        "operational_role": role.name,
                        "required": 1,
                    },
                    {
                        "sequence": 20,
                        "stage_definition": last,
                        "operational_role": role.name,
                        "required": 1,
                    },
                ],
            }
        ).insert(ignore_permissions=True)
        self.routes.append(document.name)
        return document.name, middle, last

    def _definition(self, label: str) -> str:
        document = frappe.get_doc(
            {
                "doctype": "Production Stage Definition",
                "stage_code": f"cbot-{label}-{self.suffix}",
                "stage_label": f"CBOT {label} {self.suffix}",
            }
        ).insert(ignore_permissions=True)
        self.definitions.append(document.name)
        return document.name

    def _point_stage(self, order: str, route: str, stage_code: str, status: str) -> None:
        stage = frappe.get_doc(
            {
                "doctype": "Production Stage",
                "door_cutting_order": order,
                "sequence": 10,
                "stage_type": stage_code,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True)
        self.stages.append(stage.name)
        frappe.db.set_value("Production Stage", stage.name, "status", status)
        frappe.db.set_value(
            "Door Cutting Order",
            order,
            {
                "production_path": route,
                "current_production_stage": stage.name,
            },
        )

    def _grant(self, customer: str, normalized_phone: str) -> None:
        name = f"CBPA-READ-{self.suffix}"
        frappe.db.sql(
            """
            INSERT INTO `tabCustomer Bot Phone Access`
                (name, creation, modified, modified_by, owner, docstatus, idx,
                 customer, normalized_phone, status)
            VALUES (%s, NOW(), NOW(), 'Administrator', 'Administrator', 0, 0,
                    %s, %s, 'Active')
            """,
            (name, customer, normalized_phone),
        )
        self.grants.append(name)
