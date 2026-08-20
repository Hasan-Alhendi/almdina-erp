from __future__ import annotations

import unittest

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.order_cost_surface_metadata import (
    DOCTYPE,
    order_cost_surface_metadata_state,
    sync_order_cost_surface_metadata,
)


FIELDNAME = "cutting_cost_per_board_usd"


class TestOrderCostSurfaceMetadataIntegration(unittest.TestCase):
    def _delete_required_setters(self) -> None:
        for name in frappe.get_all(
            "Property Setter",
            filters={
                "doc_type": DOCTYPE,
                "field_name": FIELDNAME,
                "property": "reqd",
            },
            pluck="name",
        ):
            frappe.delete_doc(
                "Property Setter",
                name,
                ignore_permissions=True,
                force=True,
            )

    def _set_standard_required_flag(self, required: int) -> None:
        frappe.db.sql(
            """
            update `tabDocField`
               set reqd = %s
             where parent = %s
               and fieldname = %s
            """,
            (required, DOCTYPE, FIELDNAME),
        )

    def _install_legacy_required_override(self) -> None:
        self._delete_required_setters()
        frappe.get_doc(
            {
                "doctype": "Property Setter",
                "doc_type": DOCTYPE,
                "doctype_or_field": "DocField",
                "field_name": FIELDNAME,
                "property": "reqd",
                "property_type": "Check",
                "value": "1",
            }
        ).insert(ignore_permissions=True)
        self._set_standard_required_flag(1)
        frappe.clear_cache(doctype=DOCTYPE)

    def tearDown(self) -> None:
        self._delete_required_setters()
        self._set_standard_required_flag(0)
        frappe.clear_cache(doctype=DOCTYPE)

    def test_sync_repairs_cached_legacy_required_metadata_idempotently(self) -> None:
        self._install_legacy_required_override()

        self.assertEqual(frappe.get_meta(DOCTYPE).get_field(FIELDNAME).reqd, 1)

        sync_order_cost_surface_metadata()
        sync_order_cost_surface_metadata()

        state = order_cost_surface_metadata_state()
        self.assertEqual(state["fields"][FIELDNAME], 0)
        self.assertEqual(state["property_setters"], [])
        self.assertEqual(
            frappe.db.get_value(
                "DocField",
                {"parent": DOCTYPE, "fieldname": FIELDNAME},
                "reqd",
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
