"""Loads ar.csv with Frappe's own CSV parser. Site test only."""

from __future__ import annotations

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.translate import get_translation_dict_from_file


CATALOG = Path(__file__).resolve().parents[1] / "translations" / "ar.csv"


class TestTranslationCatalogParser(FrappeTestCase):
    def test_frappe_parser_loads_the_arabic_catalog(self) -> None:
        parsed = get_translation_dict_from_file(str(CATALOG), "ar", "almdina_erp", throw=True)
        self.assertIn("The selected user language is not supported.", parsed)
        self.assertTrue(parsed["The selected user language is not supported."])
        self.assertGreater(len(parsed), 100)
        frappe.logger().debug("arabic catalog keys=%s", len(parsed))
