from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.surface_access import Surface
from almdina_erp.almdina_erp.application.security.workspace_visibility import (
    WORKSPACE_ENTRY_SURFACES,
    filter_workspace_content,
    workspace_item_allowed,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (
    ROOT
    / "almdina_erp"
    / "workspace"
    / "almdina_erp"
    / "almdina_erp.json"
)


class TestWorkspaceServerVisibility(unittest.TestCase):
    def _workspace_doc(self) -> dict:
        return json.loads(WORKSPACE.read_text(encoding="utf-8"))

    def test_every_main_workspace_shortcut_has_a_business_surface(self) -> None:
        doc = self._workspace_doc()
        missing = [
            shortcut.get("label")
            for shortcut in doc.get("shortcuts", [])
            if shortcut.get("label") not in WORKSPACE_ENTRY_SURFACES
        ]
        self.assertEqual([], missing)

    def test_order_only_projection_removes_denied_shortcuts_and_empty_sections(self) -> None:
        doc = self._workspace_doc()
        surfaces = {surface: False for surface in set(WORKSPACE_ENTRY_SURFACES.values())}
        surfaces[Surface.ORDERS] = True

        filtered = json.loads(filter_workspace_content(doc["content"], surfaces))
        shortcut_names = {
            block.get("data", {}).get("shortcut_name")
            for block in filtered
            if block.get("type") == "shortcut"
        }
        header_text = {
            block.get("data", {}).get("text", "")
            for block in filtered
            if block.get("type") == "header"
        }

        self.assertEqual({"طلبات قص الدرف"}, shortcut_names)
        self.assertTrue(any("التشغيل اليومي" in value for value in header_text))
        self.assertFalse(any("الإعدادات الأساسية" in value for value in header_text))
        self.assertFalse(any("إدارة النظام ومسارات العمل" in value for value in header_text))
        self.assertFalse(any("التقارير التشغيلية والتكلفة" in value for value in header_text))

    def test_v16_sidebar_link_uses_surface_instead_of_parent_visibility(self) -> None:
        surfaces = {
            Surface.ORDERS: True,
            Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE: False,
        }
        order_link = {
            "type": "Link",
            "parent_page": "Almdina ERP",
            "link_to": "Door Cutting Order",
            "label": "طلبات قص الدرف",
        }
        report_link = {
            "type": "Link",
            "parent_page": "Almdina ERP",
            "link_to": "Production Stage Performance",
            "label": "أداء مراحل الإنتاج",
        }

        self.assertIs(workspace_item_allowed(order_link, surfaces), True)
        self.assertIs(workspace_item_allowed(report_link, surfaces), False)

    def test_boot_filters_frappe_v16_sidebar_pages_and_workspace_content(self) -> None:
        source = (ROOT / "boot.py").read_text(encoding="utf-8")
        self.assertIn('"sidebar_pages"', source)
        self.assertIn("workspace_item_allowed", source)
        self.assertIn("project_workspace_page", source)
        self.assertIn("Unknown child links inside the Almdina shell fail closed", source)


if __name__ == "__main__":
    unittest.main()
