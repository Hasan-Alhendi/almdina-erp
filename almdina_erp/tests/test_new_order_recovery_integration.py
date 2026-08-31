from __future__ import annotations

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

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        if self.tokens:
            frappe.db.delete(
                "Door Cutting Order",
                {"recovery_creation_token": ["in", self.tokens]},
            )
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
