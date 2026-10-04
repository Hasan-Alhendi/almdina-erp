from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "almdina_erp"
CUTTING_DOMAIN = ROOT / "almdina_erp" / "domain" / "cutting"
CUTTING_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_engine.py"
OPTIMIZER_SERVICE = (
    ROOT / "almdina_erp" / "services" / "advanced_cutting_optimizer.py"
)
ENGINE_ADAPTER = (
    ROOT / "almdina_erp" / "infrastructure" / "cutting" / "domain_engine.py"
)
LEGACY_ENGINE_ADAPTER = (
    ROOT / "almdina_erp" / "infrastructure" / "cutting" / "legacy_engine.py"
)
LEGACY_IMPORTS = (
    "almdina_erp.almdina_erp.services.cutting_engine",
    "almdina_erp.almdina_erp.services.advanced_cutting_optimizer",
    "almdina_erp.almdina_erp.infrastructure.cutting.legacy_engine",
)


class TestCuttingDomainArchitecture(unittest.TestCase):
    def test_domain_cutting_has_no_framework_or_service_dependencies(self) -> None:
        python_files = sorted(CUTTING_DOMAIN.rglob("*.py"))
        self.assertGreaterEqual(len(python_files), 8)
        for path in python_files:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("import frappe", source)
                self.assertNotIn("from frappe", source)
                self.assertNotIn("import erpnext", source)
                self.assertNotIn(".services", source)
                self.assertNotIn(".infrastructure", source)

    def test_strategy_families_are_separate_modules(self) -> None:
        strategy_dir = CUTTING_DOMAIN / "strategies"
        for filename in (
            "maxrects.py",
            "shelf.py",
            "guillotine.py",
            "skyline.py",
        ):
            self.assertTrue((strategy_dir / filename).exists(), filename)

        registry = (CUTTING_DOMAIN / "registry.py").read_text(encoding="utf-8")
        self.assertIn("class PackingStrategy", registry)
        self.assertIn("STRATEGY_BY_KEY", registry)
        self.assertNotIn("def pack_maxrects", registry)
        self.assertNotIn("def pack_guillotine", registry)
        self.assertNotIn("def pack_skyline", registry)

    def test_old_service_modules_are_removed(self) -> None:
        self.assertFalse(CUTTING_SERVICE.exists())
        self.assertFalse(OPTIMIZER_SERVICE.exists())
        self.assertFalse(LEGACY_ENGINE_ADAPTER.exists())

    def test_runtime_has_no_legacy_cutting_imports(self) -> None:
        offenders: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for import_path in LEGACY_IMPORTS:
                if import_path in source:
                    offenders.append(
                        f"{path.relative_to(ROOT)} imports {import_path}"
                    )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_application_engine_adapter_uses_domain_not_services(self) -> None:
        source = ENGINE_ADAPTER.read_text(encoding="utf-8")
        self.assertIn("domain.cutting", source)
        self.assertNotIn("services.cutting_engine", source)
        self.assertNotIn("services.advanced_cutting_optimizer", source)
        self.assertIn("class DomainCuttingEngineAdapter", source)

    def test_legacy_engine_adapter_is_removed(self) -> None:
        self.assertFalse(LEGACY_ENGINE_ADAPTER.exists())


if __name__ == "__main__":
    unittest.main()
