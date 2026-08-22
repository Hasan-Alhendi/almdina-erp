from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "public" / "js" / "frontend_foundation.js"
MODULAR_PAGES = (
    ROOT / "almdina_erp" / "page" / "factory_workforce" / "factory_workforce.js",
    ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js",
    ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js",
)


class FrontendAssetLoadingContractTest(unittest.TestCase):
    def test_foundation_owns_batched_asset_loading(self) -> None:
        source = FOUNDATION.read_text(encoding="utf-8")
        self.assertIn("function requireAssets(items)", source)
        self.assertIn("runtime.require(assets)", source)
        self.assertIn("pendingAssetGroups", source)

    def test_modular_pages_never_require_dependencies_serially(self) -> None:
        for page in MODULAR_PAGES:
            with self.subTest(page=page.name):
                source = page.read_text(encoding="utf-8")
                self.assertIn("frontend.requireAssets(MODULES)", source)
                self.assertNotIn("MODULES.reduce", source)
                self.assertNotIn("frappe.require(", source)


if __name__ == "__main__":
    unittest.main()
