from __future__ import annotations

from collections.abc import Mapping

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.infrastructure.frappe.orders.document_access import (
    FrappeOrderDocumentAccess,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.piece_policy_adapter import (
    FrappeOrderPiecePolicyAdapter,
)


class TestCornerEdgePersistenceIntegration(FrappeTestCase):
    """Prove normalized corner flags survive an actual database reload."""

    def setUp(self) -> None:
        super().setUp()
        token = frappe.generate_hash(length=8)
        self.order_name = f"TEST-DCO-CORNER-{token}"
        self.piece_name = f"TEST-DCO-CORNER-ROW-{token}"
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
                "piece_type": "Clipped Corner",
                "width_cm": 100,
                "length_cm": 200,
                "qty": 1,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 20,
                "clipped_corner_length_cm": 40,
                "edge_break": 1,
                "edge_break_only": 0,
            },
        )

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

    def _normalize_store_reload(self, **updates: object):
        order = frappe.get_doc("Door Cutting Order", self.order_name)
        row = order.pieces[0]
        for fieldname, value in updates.items():
            setattr(row, fieldname, value)
        FrappeOrderPiecePolicyAdapter(
            order,
            FrappeOrderDocumentAccess(order),
        ).validate_rows()
        row.db_update()
        return frappe.get_doc("Door Cutting Order", self.order_name).pieces[0]

    def test_corner_edge_modes_survive_backend_normalization_and_reload(self) -> None:
        row = self._normalize_store_reload(edge_break=0, edge_break_only=0)
        self.assertEqual((row.edge_break, row.edge_break_only), (0, 0))

        row = self._normalize_store_reload(edge_break=0, edge_break_only=1)
        self.assertEqual((row.edge_break, row.edge_break_only), (0, 1))

        row = self._normalize_store_reload(edge_break=1, edge_break_only=0)
        self.assertEqual((row.edge_break, row.edge_break_only), (1, 0))

        row = self._normalize_store_reload(edge_break=0, edge_break_only=0)
        self.assertEqual(
            (row.edge_break, row.edge_break_only),
            (0, 0),
            "persisted zeroes must not reactivate a previous mode",
        )

    def test_conversion_l_corner_and_ordinary_sides_survive_reload(self) -> None:
        row = self._normalize_store_reload(
            edge_break=0,
            edge_break_only=1,
            edge_width_top=1,
            edge_long_right=1,
        )
        self.assertEqual((row.edge_break, row.edge_break_only), (1, 0))
        self.assertEqual((row.edge_width_top, row.edge_long_right), (0, 0))

        row = self._normalize_store_reload(
            piece_type="L-Shaped Corner",
            edge_break=1,
            edge_break_only=0,
            edge_width_top=1,
            edge_long_right=1,
        )
        self.assertEqual((row.edge_break, row.edge_break_only), (1, 0))
        self.assertEqual((row.edge_width_top, row.edge_long_right), (1, 1))

        row = self._normalize_store_reload(
            piece_type="Regular",
            edge_break=1,
            edge_break_only=0,
            edge_width_top=1,
            edge_long_right=1,
        )
        self.assertEqual((row.edge_break, row.edge_break_only), (0, 0))
        self.assertEqual((row.edge_width_top, row.edge_long_right), (1, 1))
