from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "public" / "js" / "frontend_foundation.js"
ASSETS = ROOT / "frontend_assets.py"
STATIC_WORKFLOW = ROOT.parent / ".github" / "workflows" / "static-checks.yml"
DCO_CONTEXT = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_document_context.js"
PAGE_ENTRIES = (
    ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js",
    ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js",
    ROOT / "almdina_erp" / "page" / "factory_workforce" / "factory_workforce.js",
    ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js",
)


class TestFrontendFoundationContract(unittest.TestCase):
    def test_foundation_is_small_explicit_and_framework_neutral(self) -> None:
        source = FOUNDATION.read_text(encoding="utf-8")

        for exported in (
            "rpc",
            "errorMessage",
            "createLatestRequestGate",
            "createLifecycleScope",
            "ensureStylesheet",
        ):
            self.assertIn(exported, source)

        self.assertIn("window.AlmdinaFrontend", source)
        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("System Manager", source)
        self.assertNotIn("almdina_erp.almdina_erp.services.", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("MutationObserver", source)

    def test_foundation_is_loaded_once_before_legacy_shared_shell(self) -> None:
        source = ASSETS.read_text(encoding="utf-8")
        foundation_asset = '"/assets/almdina_erp/js/frontend_foundation.js"'
        shell_asset = '"/assets/almdina_erp/js/shared_shell.js"'

        self.assertEqual(source.count(foundation_asset), 1)
        self.assertLess(source.index(foundation_asset), source.index(shell_asset))

    def test_modular_pages_self_bootstrap_when_global_foundation_is_late(self) -> None:
        for page_entry in PAGE_ENTRIES:
            with self.subTest(page=page_entry.name):
                source = page_entry.read_text(encoding="utf-8")

                self.assertIn(
                    'const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";',
                    source,
                )
                self.assertIn(
                    'const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";',
                    source,
                )
                self.assertIn("frappe.ui.make_app_page", source)
                self.assertLess(source.index("frappe.ui.make_app_page"), source.index("function ensureCore()"))
                self.assertIn("function ensureCore()", source)
                self.assertIn("frappe.require(assets)", source)
                self.assertIn("bindActivationLifecycle", source)
                self.assertIn("return ensureCore()", source)
                self.assertIn(
                    'if (!frontend || typeof frontend.ensureStylesheet !== "function")',
                    source,
                )

    def test_dco_keeps_its_specialized_document_context(self) -> None:
        source = DCO_CONTEXT.read_text(encoding="utf-8")

        self.assertIn("window.AlmdinaDocumentContext", source)
        self.assertIn("function isCurrent", source)
        self.assertIn("function schedule", source)
        self.assertIn("function registerObserver", source)
        self.assertNotIn("AlmdinaFrontend.createLatestRequestGate", source)

    def test_foundation_runtime_test_is_a_permanent_static_gate(self) -> None:
        workflow = STATIC_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("almdina_erp.tests.test_frontend_foundation_contract", workflow)
        self.assertIn("node almdina_erp/tests/js/frontend_foundation.test.js", workflow)


if __name__ == "__main__":
    unittest.main()
