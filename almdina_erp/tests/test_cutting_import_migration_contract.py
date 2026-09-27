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

    def test_canonical_order_base_delegates_cutting_ownership(self) -> None:
        base = (
            RUNTIME_ROOT
            / "doctype"
            / "door_cutting_order"
            / "door_cutting_order.py"
        ).read_text(encoding="utf-8")
        plan_adapter = (
            RUNTIME_ROOT
            / "infrastructure"
            / "frappe"
            / "orders"
            / "plan_adapter.py"
        ).read_text(encoding="utf-8")

        self.assertIn("process_order_save(self._gateway())", base)
        self.assertIn("FrappeOrderPlanAdapter", base)
        self.assertNotIn("from almdina_erp.almdina_erp.domain.cutting import", base)
        for symbol in (
            "expand_piece_groups",
            "optimize_plan",
            "validate_plan",
        ):
            self.assertNotIn(symbol, base)

        self.assertIn(
            "from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (",
            plan_adapter,
        )
        self.assertIn("optimize_order_plan", plan_adapter)
        self.assertIn("domain_cutting_engine", plan_adapter)
        for legacy in LEGACY_IMPORTS:
            self.assertNotIn(legacy, base)
            self.assertNotIn(legacy, plan_adapter)

    def test_compatibility_modules_are_removed(self) -> None:
        for relative in (
            "services/cutting_engine.py",
            "services/advanced_cutting_optimizer.py",
            "infrastructure/cutting/legacy_engine.py",
        ):
            self.assertFalse((RUNTIME_ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
