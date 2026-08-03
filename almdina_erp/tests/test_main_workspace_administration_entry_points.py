from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (
    ROOT
    / "almdina_erp"
    / "workspace"
    / "almdina_erp"
    / "almdina_erp.json"
)


class TestMainWorkspaceAdministrationEntryPoints(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = json.loads(WORKSPACE.read_text(encoding="utf-8"))
        self.blocks = json.loads(self.workspace["content"])

    def test_main_workspace_contains_a_dedicated_administration_section(self) -> None:
        header_texts = [
            block.get("data", {}).get("text", "")
            for block in self.blocks
            if block.get("type") == "header"
        ]
        self.assertTrue(
            any("إدارة النظام ومسارات العمل" in text for text in header_texts)
        )

    def test_administration_shortcuts_use_existing_frappe_targets(self) -> None:
        expected = {
            "إدارة الأدوار": ("Role", "DocType"),
            "إدارة الصلاحيات": ("factory-permissions", "Page"),
            "إدارة المستخدمين": ("factory-workforce", "Page"),
            "إدارة مسارات الإنتاج": ("factory-master-data", "Page"),
        }
        shortcuts = {
            row["label"]: (row["link_to"], row["type"])
            for row in self.workspace["shortcuts"]
        }
        for label, target in expected.items():
            with self.subTest(label=label):
                self.assertEqual(shortcuts.get(label), target)

    def test_all_administration_shortcuts_are_rendered_as_equal_cards(self) -> None:
        cards = {
            block.get("data", {}).get("shortcut_name"): block.get("data", {}).get("col")
            for block in self.blocks
            if block.get("type") == "shortcut"
        }
        for label in (
            "إدارة الأدوار",
            "إدارة الصلاحيات",
            "إدارة المستخدمين",
            "إدارة مسارات الإنتاج",
        ):
            with self.subTest(label=label):
                self.assertEqual(cards.get(label), 3)


if __name__ == "__main__":
    unittest.main()
