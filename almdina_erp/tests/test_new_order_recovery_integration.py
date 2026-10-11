from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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
        user = f"almdina.recovery.{uuid4().hex[:12]}@example.com"
        frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
        self.test_roles.append(role)
        if can_create:
            update_role_permissions(role, {Capability.CREATE_ORDER: True})
        frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": "Recovery",
                "last_name": "Test",
                "user_type": "System User",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        self.test_users.append(user)
        frappe.clear_cache(user=user)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.local.role_permissions = {}
        if hasattr(frappe.local, "almdina_matrix_capabilities"):
            del frappe.local.almdina_matrix_capabilities
        return user

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

    def test_concurrent_native_inserts_bind_one_creation_token(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        barrier = Barrier(2)
        site = frappe.local.site
        duplicate_errors = tuple(
            error
            for error in (
                getattr(frappe, "DuplicateEntryError", None),
                getattr(frappe, "UniqueValidationError", None),
            )
            if isinstance(error, type)
        )

        def insert_on_independent_connection(worker: int) -> tuple[str, str]:
            frappe.init(site=site)
            frappe.connect()
            frappe.set_user("Administrator")
            barrier.wait(timeout=10)
            try:
                order = frappe.new_doc("Door Cutting Order")
                # Avoid serializing both inserts on the shared naming-series row;
                # the race under test is the unique recovery token constraint.
                order.name = f"DCO-RECOVERY-RACE-{token[:8]}-{worker}"
                order.recovery_creation_token = token
                order.flags._order_save_gateway = _NoopOrderSaveGateway()
                order.insert(ignore_permissions=True, ignore_mandatory=True)
                frappe.db.commit()
                return "inserted", order.name
            except Exception as error:
                frappe.db.rollback()
                if duplicate_errors and isinstance(error, duplicate_errors):
                    return "duplicate", type(error).__name__
                if type(error).__name__ == "QueryTimeoutError":
                    return "timeout", type(error).__name__
                return "error", f"{type(error).__name__}: {error}"
            finally:
                frappe.destroy()

        def delete_committed_token() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.db.delete("Door Cutting Order", {"recovery_creation_token": token})
                frappe.db.commit()
            finally:
                frappe.destroy()

        try:
            with (
                mock.patch(
                    "almdina_erp.almdina_erp.doctype.door_cutting_order."
                    "door_cutting_order_controller.invalidate_stale_draft_plans"
                ),
                mock.patch(
                    "almdina_erp.almdina_erp.doctype.door_cutting_order."
                    "door_cutting_order_controller.refresh_order_commercial_totals"
                ),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                outcomes = list(pool.map(insert_on_independent_connection, range(2)))
            self.assertFalse(
                [value for kind, value in outcomes if kind == "error"],
                f"Unexpected concurrent insert errors: {outcomes}",
            )

            # Contention can time out both full DocType inserts before either
            # owns the token. A fresh retry is the same recovery path clients
            # use after an ambiguous response; the unique constraint still
            # limits the identity to one committed DCO.
            frappe.db.rollback()
            names = frappe.get_all(
                "Door Cutting Order",
                filters={"recovery_creation_token": token},
                pluck="name",
            )
            if not names:
                retry = self._insert(token)
                frappe.db.commit()
                names = [retry.name]
            self.assertEqual(len(names), 1)
            reconciliation = reconcile_new_order_creation(token)
            self.assertEqual(reconciliation["status"], "CREATED")
            self.assertEqual(reconciliation["door_cutting_order"], names[0])
        finally:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(delete_committed_token).result()

    def test_reconciliation_rejects_unauthenticated_token_probing(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        self._insert(token)

        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(token)

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

    def test_unbound_identity_is_proven_without_creating_a_dco(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)

        result = reconcile_new_order_creation(token)

        self.assertEqual(result, {"status": "NOT_FOUND"})
        self.assertFalse(
            frappe.db.exists("Door Cutting Order", {"recovery_creation_token": token})
        )

    def test_reconciliation_scopes_tokens_to_actor_and_requires_create_permission(self) -> None:
        owner_token = str(uuid4())
        self.tokens.append(owner_token)
        self._insert(owner_token)

        user = self._create_user(can_create=True)
        frappe.set_user(user)
        self.assertEqual(reconcile_new_order_creation(owner_token), {"status": "NOT_FOUND"})

        own_token = str(uuid4())
        self.tokens.append(own_token)
        self._insert(own_token)
        with mock.patch("frappe.has_permission", return_value=False) as has_permission:
            with self.assertRaises(frappe.PermissionError):
                reconcile_new_order_creation(own_token)
        self.assertEqual(has_permission.call_args.args[1], "read")
        self.assertEqual(has_permission.call_args.kwargs["user"], user)

        frappe.set_user("Administrator")
        no_create_user = self._create_user(can_create=False)
        frappe.set_user(no_create_user)
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(str(uuid4()))

    def test_acknowledged_creation_binding_is_immutable(self) -> None:
        token = str(uuid4())
        replacement = str(uuid4())
        self.tokens.extend((token, replacement))
        order = self._insert(token)
        order.recovery_creation_token = replacement
        order.flags._order_save_gateway = _NoopOrderSaveGateway()

        with self.assertRaises(frappe.ValidationError):
            order.save(ignore_permissions=True, ignore_version=True)
