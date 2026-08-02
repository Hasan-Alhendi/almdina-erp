from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIR = ROOT / "almdina_erp" / "domain" / "inventory"
APPLICATION_DIR = ROOT / "almdina_erp" / "application" / "inventory"
REPOSITORY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "inventory"
    / "stock_availability_repository.py"
)
SERVICE_PATH = ROOT / "almdina_erp" / "services" / "stock_availability_service.py"
HOOKS_PATH = ROOT / "hooks.py"
LEGACY_STOCK_ENDPOINT = (
    "almdina_erp.almdina_erp.services.stock_service.check_order_stock"
)
RETIRED_PRODUCT_ENDPOINT = (
    "almdina_erp.almdina_erp.services.legacy_endpoint_service."
    "retired_product_endpoint"
)


class TestStockAvailabilityArchitecture(unittest.TestCase):
    def test_inventory_domain_is_framework_independent(self) -> None:
        for path in sorted(DOMAIN_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("import frappe", source)
                self.assertNotIn("from frappe", source)
                self.assertNotIn("import erpnext", source)
                self.assertNotIn(".services", source)
                self.assertNotIn(".infrastructure", source)

    def test_inventory_application_depends_only_inward(self) -> None:
        for path in sorted(APPLICATION_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("import frappe", source)
                self.assertNotIn("from frappe", source)
                self.assertNotIn("import erpnext", source)
                self.assertNotIn(".services", source)
                self.assertNotIn(".infrastructure", source)
        use_case = (APPLICATION_DIR / "check_order_stock.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class StockAvailabilityRepository(Protocol)", use_case)
        self.assertIn("evaluate_stock_availability", use_case)

    def test_frappe_queries_live_in_inventory_repository(self) -> None:
        repository = REPOSITORY_PATH.read_text(encoding="utf-8")
        self.assertIn("class FrappeStockAvailabilityRepository", repository)
        self.assertIn("tabMaterial Reservation Item", repository)
        self.assertIn("def get_stock_position", repository)
        service = SERVICE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("frappe.db.", service)
        self.assertNotIn("actual_qty - reserved_qty", service)

    def test_legacy_public_endpoint_is_fail_closed(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        overrides = hooks["override_whitelisted_methods"]
        self.assertEqual(
            overrides.get(LEGACY_STOCK_ENDPOINT),
            RETIRED_PRODUCT_ENDPOINT,
        )


if __name__ == "__main__":
    unittest.main()
