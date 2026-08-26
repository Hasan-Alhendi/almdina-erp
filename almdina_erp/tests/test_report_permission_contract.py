from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "almdina_erp" / "report"
ACTIVE_OPERATIONAL_REPORTS = (
    "factory_operations_summary",
    "production_stage_performance",
    "production_incidents_and_replacements",
    "board_usage_analysis",
    "piece_size_usage_analysis",
)
RETIRED_STOCK_REPORTS = (
    "order_stock_availability",
    "remnant_inventory",
)


class TestReportPermissionContract(unittest.TestCase):
    def test_every_active_report_execute_has_an_explicit_report_guard(self) -> None:
        missing: list[str] = []
        for path in sorted(REPORTS.glob("*/*.py")):
            if path.name == "__init__.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "def execute(" not in source:
                continue
            if (
                "require_operational_report_access" not in source
                and "require_financial_report_access" not in source
            ):
                missing.append(str(path.relative_to(ROOT)))
        self.assertEqual(missing, [], f"Reports without matrix authorization: {missing}")

    def test_factory_order_analysis_is_financial_not_operational(self) -> None:
        source = (
            REPORTS / "factory_order_analysis" / "factory_order_analysis.py"
        ).read_text(encoding="utf-8")
        self.assertIn("require_financial_report_access()", source)
        self.assertNotIn("require_operational_report_access()", source)

    def test_operational_reports_use_operational_guard(self) -> None:
        for report in ACTIVE_OPERATIONAL_REPORTS:
            source = (REPORTS / report / f"{report}.py").read_text(encoding="utf-8")
            self.assertIn("require_operational_report_access()", source, report)

    def test_retired_stock_reports_have_no_active_source_directory(self) -> None:
        for report in RETIRED_STOCK_REPORTS:
            self.assertFalse((REPORTS / report).exists(), report)


if __name__ == "__main__":
    unittest.main()
