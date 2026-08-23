from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "public" / "js" / "frontend_foundation.js"
PAGE_ROOT = ROOT / "almdina_erp" / "page"
MODULAR_PAGES = (
    PAGE_ROOT / "factory_workforce" / "factory_workforce.js",
    PAGE_ROOT / "factory_permissions" / "factory_permissions.js",
    PAGE_ROOT / "factory_production_settings" / "factory_production_settings.js",
)


class FrontendAssetLoadingContractTest(unittest.TestCase):
    def test_foundation_owns_batched_asset_loading(self) -> None:
        source = FOUNDATION.read_text(encoding="utf-8")
        self.assertIn("function requireAssets(items)", source)
        self.assertIn("runtime.require(assets)", source)
        self.assertIn("pendingAssetGroups", source)

    def test_known_modular_pages_keep_a_single_batch_compatibility_path(self) -> None:
        for page in MODULAR_PAGES:
            with self.subTest(page=page.name):
                source = page.read_text(encoding="utf-8")
                self.assertIn('typeof frontend.requireAssets === "function"', source)
                self.assertIn("frontend.requireAssets(MODULES)", source)
                self.assertIn("Promise.resolve(frappe.require(MODULES))", source)
                self.assertNotIn('typeof frontend.requireAssets !== "function"', source)
                self.assertNotIn(".reduce(", source)

    def test_no_page_reintroduces_serial_frappe_asset_loading(self) -> None:
        for page in PAGE_ROOT.rglob("*.js"):
            source = page.read_text(encoding="utf-8")
            if "frappe.require(" not in source:
                continue
            with self.subTest(page=str(page.relative_to(ROOT))):
                self.assertNotIn(
                    ".reduce(",
                    source,
                    "Page assets must be loaded as one Frappe batch, never serially with reduce().",
                )


if __name__ == "__main__":
    unittest.main()
