from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "almdina_erp"
LEGACY_IMPORTS = (
    "almdina_erp.almdina_erp.services.cutting_engine",
    "almdina_erp.almdina_erp.services.advanced_cutting_optimizer",
    "almdina_erp.almdina_erp.infrastructure.cutting.legacy_engine",
)


class TestCuttingImportMigrationContract(unittest.TestCase):
    def test_runtime_uses_domain_cutting_and_canonical_engine_adapter(self) -> None:
        offenders: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for import_path in LEGACY_IMPORTS:
                if import_path in source:
                    offenders.append(
                        f"{path.relative_to(ROOT)} imports {import_path}"
                    )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_canonical_order_base_imports_cutting_domain_directly(self) -> None:
        source = (
            RUNTIME_ROOT
            / "doctype"
            / "door_cutting_order"
            / "door_cutting_order.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from almdina_erp.almdina_erp.domain.cutting import (", source)
        for symbol in (
            "expand_piece_groups",
            "optimize_plan",
            "round_value",
            "validate_plan",
        ):
            self.assertIn(symbol, source)
        for legacy in LEGACY_IMPORTS:
            self.assertNotIn(legacy, source)

    def test_compatibility_modules_are_thin_and_remain_available(self) -> None:
        cutting = (RUNTIME_ROOT / "services" / "cutting_engine.py").read_text(
            encoding="utf-8"
        )
        optimizer = (
            RUNTIME_ROOT / "services" / "advanced_cutting_optimizer.py"
        ).read_text(encoding="utf-8")
        legacy_engine = (
            RUNTIME_ROOT / "infrastructure" / "cutting" / "legacy_engine.py"
        ).read_text(encoding="utf-8")

        self.assertIn("domain.cutting import *", cutting)
        self.assertLess(len(cutting.splitlines()), 20)
        self.assertIn("domain.cutting.optimizer import *", optimizer)
        self.assertLess(len(optimizer.splitlines()), 25)
        self.assertIn("DomainCuttingEngineAdapter", legacy_engine)
        self.assertIn("domain_cutting_engine", legacy_engine)
        self.assertLess(len(legacy_engine.splitlines()), 20)


if __name__ == "__main__":
    unittest.main()
