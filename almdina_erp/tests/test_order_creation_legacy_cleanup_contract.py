from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "almdina_erp"
LEGACY_MODULE = RUNTIME_ROOT / "services" / "order_creation_service.py"
HOOKS_PATH = ROOT / "hooks.py"
RETIRED_TARGET = (
    "almdina_erp.almdina_erp.services.legacy_endpoint_service."
    "retired_product_endpoint"
)
LEGACY_ENDPOINTS = (
    "almdina_erp.almdina_erp.services.order_creation_service."
    "create_door_cutting_order",
    "almdina_erp.almdina_erp.services.order_creation_service."
    "get_new_order_defaults",
)


class TestOrderCreationLegacyCleanupContract(unittest.TestCase):
    def test_legacy_module_is_a_business_logic_free_tombstone(self) -> None:
        source = LEGACY_MODULE.read_text(encoding="utf-8")
        self.assertIn("Retired historical order-creation module", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("def apply_factory_defaults", source)
        self.assertNotIn("def create_door_cutting_order", source)
        self.assertNotIn("def get_new_order_defaults", source)
        self.assertNotIn("frappe.get_doc", source)
        self.assertNotIn("frappe.get_single", source)

    def test_runtime_has_zero_python_imports_of_legacy_module(self) -> None:
        forbidden = (
            "services.order_creation_service import",
            "services import order_creation_service",
            "import almdina_erp.almdina_erp.services.order_creation_service",
            "apply_factory_defaults",
        )
        offenders: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            if path == LEGACY_MODULE:
                continue
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    offenders.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_historical_rpc_names_remain_fail_closed(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        overrides = hooks["override_whitelisted_methods"]
        for endpoint in LEGACY_ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(overrides.get(endpoint), RETIRED_TARGET)


if __name__ == "__main__":
    unittest.main()
