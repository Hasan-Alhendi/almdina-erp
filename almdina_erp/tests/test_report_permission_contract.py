from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
RETIRED_REPORTS = (
    "factory_operations_summary",
    "factory_order_analysis",
    "production_stage_performance",
    "board_usage_analysis",
    "piece_size_usage_analysis",
    "production_incidents_and_replacements",
    "order_stock_availability",
    "remnant_inventory",
)


class TestReportPermissionContract(unittest.TestCase):
    def test_factory_report_modules_are_absent(self) -> None:
        report_root = APP / "report"
        for report in RETIRED_REPORTS:
            self.assertFalse((report_root / report).exists(), report)
        self.assertFalse((APP / "workspace" / "almdina_reports").exists())
        self.assertFalse((APP / "services" / "report_permission_service.py").exists())
        self.assertFalse(
            (APP / "application" / "security" / "report_access.py").exists()
        )

    def test_report_capabilities_are_retired_and_cost_view_remains(self) -> None:
        self.assertNotIn("view_operational_reports", ALL_CAPABILITIES)
        self.assertNotIn("view_financial_reports", ALL_CAPABILITIES)
        self.assertIn(Capability.VIEW_COSTS, ALL_CAPABILITIES)
        self.assertIn(Capability.PRINT_INTERNAL_COST_REPORT, ALL_CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
