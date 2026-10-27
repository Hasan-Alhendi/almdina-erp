"""Normalized phone index rules that do not need a site."""

from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_index import (
    NORMALIZED_MOBILE_FIELD,
    normalized_mobile_for_storage,
)


ROOT = Path(__file__).resolve().parents[1]


class CustomerPhoneIndexUnitTests(unittest.TestCase):
    def test_storage_uses_the_existing_normalizer(self) -> None:
        expected = "+963988100101"
        for raw in ("0988100101", "988100101", "963988100101", "+963988100101", "00963988100101"):
            self.assertEqual(normalized_mobile_for_storage(raw), expected)
        self.assertEqual(
            normalized_mobile_for_storage(" 00963 988-100-101 "),
            expected,
        )

    def test_empty_and_invalid_numbers_are_not_indexed(self) -> None:
        for raw in (None, "", "   ", "abc", "12345", "customer@c.us", "+963111"):
            self.assertIsNone(normalized_mobile_for_storage(raw))

    def test_lookup_source_is_an_equality_on_the_index(self) -> None:
        source = (ROOT / "almdina_erp" / "infrastructure" / "frappe" / "customer_phone_directory.py").read_text(
            encoding="utf-8"
        )
        index = (ROOT / "almdina_erp" / "infrastructure" / "frappe" / "customer_phone_index.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(NORMALIZED_MOBILE_FIELD, index)
        self.assertNotIn("limit_page_length", source)
        self.assertNotIn("limit_page_length", index)
        self.assertNotIn("frappe.cache", index)
        self.assertNotIn('filters={"mobile_no"', index)
        self.assertIn('"unique": 0', index)
        self.assertIn("search_index", index)
        lookup = index.split("def customer_ids_for_indexed_phone", 1)[1].split("\n__all__", 1)[0]
        sql = lookup.split("frappe.db.sql(", 1)[1]
        self.assertNotIn("mobile_no", sql)
        self.assertIn("Unsupported", index)
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("sync_customer_normalized_mobile_after_value_change", hooks)


if __name__ == "__main__":
    unittest.main()
