from __future__ import annotations

from collections.abc import Mapping

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.infrastructure.frappe.orders.document_access import (
    FrappeOrderDocumentAccess,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.piece_policy_adapter import (
    FrappeOrderPiecePolicyAdapter,
)


class TestGlassDoorPersistenceIntegration(FrappeTestCase):
    """Glass type and margin survive save, and old rows gain no hidden margin."""

    def setUp(self) -> None:
        super().setUp()
        token = frappe.generate_hash(length=8)
        self.order_name = f"TEST-DCO-GLASS-{token}"
        self.piece_name = f"TEST-DCO-GLASS-ROW-{token}"
        self.regular_name = f"TEST-DCO-GLASS-REGULAR-{token}"
        self._insert(
            "Door Cutting Order",
            {
                "name": self.order_name,
                **self._standard_columns(),
                "status": "Draft",
                "revision": 1,
                "board_description": "TEST MDF",
            },
        )
        self._insert(
            "Door Cutting Order Detail",
            {
                "name": self.piece_name,
                **self._standard_columns(),
                "parent": self.order_name,
                "parenttype": "Door Cutting Order",
                "parentfield": "pieces",
                "idx": 1,
                "piece_instance_id": f"piece:{token}",
                "piece_no": 1,
                "piece_type": "Glass",
                "width_cm": 52.1,
                "length_cm": 72.5,
                "qty": 2,
                "glass_margin_mm": 65,
                "edge_long_right": 1,
                "edge_width_top": 1,
            },
        )
        regular = {
            "name": self.regular_name,
            **self._standard_columns(),
            "parent": self.order_name,
            "parenttype": "Door Cutting Order",
            "parentfield": "pieces",
            "idx": 2,
            "piece_instance_id": f"piece-regular:{token}",
            "piece_no": 2,
            "piece_type": "Regular",
            "width_cm": 40,
            "length_cm": 60,
            "qty": 1,
        }
        self._insert("Door Cutting Order Detail", regular)

    def tearDown(self) -> None:
        frappe.db.delete("Door Cutting Order Detail", {"parent": self.order_name})
        frappe.db.delete("Door Cutting Order", {"name": self.order_name})
        super().tearDown()

    @staticmethod
    def _standard_columns() -> dict[str, object]:
        now = now_datetime()
        return {
            "owner": "Administrator",
            "creation": now,
            "modified": now,
            "modified_by": "Administrator",
            "docstatus": 0,
            "idx": 0,
        }

    @staticmethod
    def _insert(doctype: str, values: Mapping[str, object]) -> None:
        columns = list(values)
        quoted = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        frappe.db.sql(
            f"INSERT INTO `tab{doctype}` ({quoted}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )

    def _validate(self, **updates: object):
        order = frappe.get_doc("Door Cutting Order", self.order_name)
        row = next(piece for piece in order.pieces if piece.name == self.piece_name)
        for fieldname, value in updates.items():
            setattr(row, fieldname, value)
        FrappeOrderPiecePolicyAdapter(
            order,
            FrappeOrderDocumentAccess(order),
        ).validate_rows()
        row.db_update()
        return frappe.get_doc("Door Cutting Order", self.order_name)

    def test_glass_type_margin_and_edges_survive_validation_and_reload(self) -> None:
        order = self._validate()
        row = next(piece for piece in order.pieces if piece.name == self.piece_name)
        regular = next(piece for piece in order.pieces if piece.name == self.regular_name)

        self.assertEqual(row.piece_type, "Glass")
        self.assertEqual(flt(row.glass_margin_mm), 65)
        self.assertEqual(row.qty, 2)
        self.assertEqual((row.edge_long_right, row.edge_width_top), (1, 1))
        self.assertEqual(row.edge_break, 0)
        self.assertEqual(regular.piece_type, "Regular")
        self.assertIn(regular.glass_margin_mm, (None, 0))

    def test_server_rejects_non_positive_margin_and_opening(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            self._validate(glass_margin_mm=0)
        self.assertEqual(
            flt(frappe.db.get_value(
                "Door Cutting Order Detail",
                self.piece_name,
                "glass_margin_mm",
            )),
            65,
        )

        with self.assertRaises(frappe.ValidationError):
            self._validate(glass_margin_mm=260.5)
        self.assertEqual(
            flt(frappe.db.get_value(
                "Door Cutting Order Detail",
                self.piece_name,
                "glass_margin_mm",
            )),
            65,
        )

    def test_changing_margin_is_stored_and_regular_rows_are_not_backfilled(self) -> None:
        order = self._validate(glass_margin_mm=70)
        row = next(piece for piece in order.pieces if piece.name == self.piece_name)
        regular = next(piece for piece in order.pieces if piece.name == self.regular_name)

        self.assertEqual(row.piece_type, "Glass")
        self.assertEqual(flt(row.glass_margin_mm), 70)
        self.assertIn(regular.glass_margin_mm, (None, 0))
