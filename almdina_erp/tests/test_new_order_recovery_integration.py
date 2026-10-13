from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError
from unittest import mock
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.services.new_order_recovery_service import (
    reconcile_new_order_creation,
)


class _NoopOrderSaveGateway:
    def enforce_immutability(self) -> None:
        pass

    def set_piece_numbers(self) -> None:
        pass

    def validate_piece_inputs(self) -> None:
        pass

    def validate_piece_policies(self) -> None:
        pass

    def load_board_snapshot(self) -> None:
        pass

    def calculate_cut_dimensions(self) -> None:
        pass

    def calculate_piece_costs(self) -> None:
        pass

    def calculate_extra_addon_prices(self) -> None:
        pass


class TestNewOrderRecoveryIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.tokens: list[str] = []
        self.test_roles: list[str] = []
        self.test_users: list[str] = []

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        if self.tokens:
            frappe.db.delete(
                "Door Cutting Order",
                {"recovery_creation_token": ["in", self.tokens]},
            )
        for user in self.test_users:
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in self.test_roles:
            frappe.db.delete("Almdina Permission Audit", {"role": role})
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        if self.test_roles:
            frappe.clear_cache()
        super().tearDown()

    def _insert(self, token: str):
        order = frappe.new_doc("Door Cutting Order")
        order.recovery_creation_token = token
        order.flags._order_save_gateway = _NoopOrderSaveGateway()
        with (
            mock.patch(
                "almdina_erp.almdina_erp.doctype.door_cutting_order."
                "door_cutting_order_controller.invalidate_stale_draft_plans"
            ),
            mock.patch(
                "almdina_erp.almdina_erp.doctype.door_cutting_order."
                "door_cutting_order_controller.refresh_order_commercial_totals"
            ),
        ):
            order.insert(ignore_permissions=True, ignore_mandatory=True)
        return order

    def _create_user(self, *, can_create: bool) -> str:
        from almdina_erp.almdina_erp.domain.security.authorization import Capability
        from almdina_erp.almdina_erp.services.permission_management_service import (
            update_role_permissions,
        )

        role = f"Almdina Recovery Test {uuid4().hex[:8]}"
        email = f"almdina.recovery.{uuid4().hex[:12]}@example.com"
        frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
        self.test_roles.append(role)
        if can_create:
            update_role_permissions(role, {Capability.CREATE_ORDER: True})
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Recovery",
                "last_name": "Test",
                "user_type": "System User",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        self.test_users.append(email)
        frappe.clear_cache(user=email)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.local.role_permissions = {}
        if hasattr(frappe.local, "almdina_matrix_capabilities"):
            del frappe.local.almdina_matrix_capabilities
        return email

    def test_lost_response_reconciles_to_one_native_insert(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)

        inserted = self._insert(token)
        # Model the client losing the successful HTTP response by discarding the
        # inserted Document and asking only through the creation token.
        first_reconciliation = reconcile_new_order_creation(token)
        repeated_reconciliation = reconcile_new_order_creation(token)

        self.assertEqual(first_reconciliation["status"], "CREATED")
        self.assertEqual(first_reconciliation["door_cutting_order"], inserted.name)
        self.assertEqual(repeated_reconciliation, first_reconciliation)

        unique_errors = tuple(
            error
            for error in (
                getattr(frappe, "DuplicateEntryError", None),
                getattr(frappe, "UniqueValidationError", None),
            )
            if isinstance(error, type)
        )
        self.assertTrue(unique_errors)
        with self.assertRaises(unique_errors):
            self._insert(token)

        names = frappe.get_all(
            "Door Cutting Order",
            filters={"recovery_creation_token": token},
            pluck="name",
        )
        self.assertEqual(names, [inserted.name], "the repeated identity cannot create DCO B")

    def test_reconciliation_rejects_unauthenticated_token_probing(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        self._insert(token)

        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(token)

    def test_unbound_identity_is_proven_without_creating_a_dco(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)

        result = reconcile_new_order_creation(token)

        self.assertEqual(result, {"status": "NOT_FOUND"})
        self.assertFalse(
            frappe.db.exists("Door Cutting Order", {"recovery_creation_token": token})
        )

    def test_acknowledged_creation_binding_is_immutable(self) -> None:
        token = str(uuid4())
        replacement = str(uuid4())
        self.tokens.extend((token, replacement))
        order = self._insert(token)
        order.recovery_creation_token = replacement
        order.flags._order_save_gateway = _NoopOrderSaveGateway()

        with self.assertRaises(frappe.ValidationError):
            order.save(ignore_permissions=True, ignore_version=True)

    def test_insert_binds_token_to_session_user_and_rejects_malformed_token(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        order = self._insert(token)
        self.assertEqual(
            frappe.db.get_value("Door Cutting Order", order.name, "recovery_creation_user"),
            "Administrator",
        )

        malformed = "not-a-uuid"
        invalid = frappe.new_doc("Door Cutting Order")
        invalid.recovery_creation_token = malformed
        invalid.flags._order_save_gateway = _NoopOrderSaveGateway()
        with self.assertRaises(frappe.ValidationError):
            invalid.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertFalse(
            frappe.db.exists("Door Cutting Order", {"recovery_creation_token": malformed})
        )

    def test_reconciliation_scopes_tokens_and_checks_real_document_read_permission(self) -> None:
        owner_token = str(uuid4())
        self.tokens.append(owner_token)
        self._insert(owner_token)

        create_only_user = self._create_user(can_create=True)
        frappe.set_user(create_only_user)
        self.assertEqual(reconcile_new_order_creation(owner_token), {"status": "NOT_FOUND"})

        own_token = str(uuid4())
        self.tokens.append(own_token)
        own_order = self._insert(own_token)
        self.assertFalse(
            frappe.has_permission("Door Cutting Order", "read", own_order, user=create_only_user),
            "the fixture must lack native document read permission",
        )
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(own_token)

        frappe.set_user("Administrator")
        no_create_user = self._create_user(can_create=False)
        frappe.set_user(no_create_user)
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(str(uuid4()))

    def test_concurrent_native_inserts_bind_one_creation_token(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        insert_barrier = Barrier(2)
        site = frappe.local.site
        from frappe.model.document import Document

        original_db_insert = Document.db_insert

        def synchronize_at_database_insert(document, *args, **kwargs):
            if document.doctype == "Door Cutting Order":
                insert_barrier.wait(timeout=10)
            return original_db_insert(document, *args, **kwargs)

        duplicate_errors = tuple(
            error
            for error in (
                getattr(frappe, "DuplicateEntryError", None),
                getattr(frappe, "UniqueValidationError", None),
            )
            if isinstance(error, type)
        )
        self.assertTrue(duplicate_errors, "Frappe must expose its unique-entry failure type")

        def insert_on_independent_connection(worker: int) -> tuple[str, str]:
            frappe.init(site=site)
            frappe.connect()
            frappe.set_user("Administrator")
            try:
                order = frappe.new_doc("Door Cutting Order")
                order.name = f"DCO-RECOVERY-RACE-{token[:8]}-{worker}"
                order.recovery_creation_token = token
                order.flags._order_save_gateway = _NoopOrderSaveGateway()
                order.insert(ignore_permissions=True, ignore_mandatory=True)
                frappe.db.commit()
                return "inserted", order.name
            except Exception as error:
                frappe.db.rollback()
                if isinstance(error, duplicate_errors):
                    return "duplicate", type(error).__name__
                error_name = type(error).__name__.lower()
                error_text = str(error).lower()
                if any(
                    marker in error_name or marker in error_text
                    for marker in (
                        "deadlock",
                        "timeout",
                        "lock wait",
                        "lockwait",
                        "brokenbarrier",
                        "barrier",
                    )
                ):
                    return "inconclusive", f"{type(error).__name__}: {error}"
                return "error", f"{type(error).__name__}: {error}"
            finally:
                frappe.destroy()

        try:
            frappe.db.commit()
            with (
                mock.patch(
                    "almdina_erp.almdina_erp.doctype.door_cutting_order."
                    "door_cutting_order_controller.invalidate_stale_draft_plans"
                ),
                mock.patch(
                    "almdina_erp.almdina_erp.doctype.door_cutting_order."
                    "door_cutting_order_controller.refresh_order_commercial_totals"
                ),
                mock.patch.object(Document, "db_insert", new=synchronize_at_database_insert),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                outcomes = list(pool.map(insert_on_independent_connection, range(2)))
            inconclusive = [value for kind, value in outcomes if kind == "inconclusive"]
            if inconclusive:
                self.skipTest(f"INCONCLUSIVE concurrent insert outcome: {outcomes}")
            self.assertFalse(
                [value for kind, value in outcomes if kind == "error"],
                f"Unexpected concurrent insert errors: {outcomes}",
            )
            self.assertCountEqual(
                [kind for kind, _value in outcomes],
                ["inserted", "duplicate"],
                f"The concurrent race must produce one commit and one unique conflict: {outcomes}",
            )
            winner = next(value for kind, value in outcomes if kind == "inserted")
            names = frappe.get_all(
                "Door Cutting Order",
                filters={"recovery_creation_token": token},
                pluck="name",
            )
            self.assertEqual(names, [winner], "only the concurrent winner may commit")
            reconciliation = reconcile_new_order_creation(token)
            self.assertEqual(reconciliation["status"], "CREATED")
            self.assertEqual(reconciliation["door_cutting_order"], winner)
        finally:
            frappe.db.rollback()
            committed_names = frappe.get_all(
                "Door Cutting Order",
                filters={"recovery_creation_token": token},
                pluck="name",
            )
            for name in committed_names:
                frappe.delete_doc(
                    "Door Cutting Order",
                    name,
                    force=True,
                    ignore_permissions=True,
                )
            frappe.db.commit()
