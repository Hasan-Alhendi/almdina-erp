from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.order_identity import (
    ORDER_NAME_SERIES,
    compact_legacy_order_name,
    compact_order_sequence,
)


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
MIGRATION = ROOT / "patches" / "v1_0" / "migrate_door_cutting_order_names.py"
PATCHES = ROOT / "patches.txt"


class TestDcoOrderIdentity(unittest.TestCase):
    def test_canonical_series_is_two_digit_year_plus_five_digit_sequence(self) -> None:
        self.assertEqual(ORDER_NAME_SERIES, "YY.-.#####")
        self.assertEqual(compact_legacy_order_name("DCO-2026-00001"), "26-00001")
        self.assertEqual(compact_legacy_order_name("DCO-2026-00055"), "26-00055")
        self.assertEqual(compact_legacy_order_name("DCO-2026-000023"), "26-000023")
        self.assertIsNone(compact_legacy_order_name("26-00001"))
        self.assertIsNone(compact_legacy_order_name("DCO-26-00001"))

    def test_compact_sequence_parser_supports_counter_synchronization(self) -> None:
        self.assertEqual(compact_order_sequence("26-00055"), ("26", 55))
        self.assertEqual(compact_order_sequence("26-000023"), ("26", 23))
        self.assertEqual(compact_order_sequence("27-00001"), ("27", 1))
        self.assertIsNone(compact_order_sequence("DCO-2026-00055"))

    def test_controller_owns_real_document_name_instead_of_list_formatting(self) -> None:
        source = CONTROLLER.read_text(encoding="utf-8")

        self.assertIn("from frappe.model.naming import make_autoname", source)
        self.assertIn("def autoname(self) -> None:", source)
        self.assertIn("self.name = make_autoname(ORDER_NAME_SERIES, doc=self)", source)

    def test_migration_renames_existing_documents_and_advances_series_counter(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")
        patches = PATCHES.read_text(encoding="utf-8")

        self.assertIn("if not frappe.db.table_exists(DOCTYPE):", source)
        self.assertIn("rename_doc(", source)
        self.assertIn("force=True", source)
        self.assertIn("ignore_permissions=True", source)
        self.assertIn('NamingSeries(f"{year}-.#####").update_counter(sequence)', source)
        self.assertIn("almdina_erp.patches.v1_0.migrate_door_cutting_order_names", patches)


if __name__ == "__main__":
    unittest.main()
