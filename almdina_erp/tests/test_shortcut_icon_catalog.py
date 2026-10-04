from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.presentation.shortcut_icon_catalog import (
    SHORTCUT_ICONS_BY_LABEL,
    apply_sidebar_icon_catalog,
    icon_for_label,
)


class TestShortcutIconCatalog(unittest.TestCase):
    def test_known_arabic_labels_map_to_home_catalog_icons(self) -> None:
        self.assertEqual(icon_for_label("الزبائن"), "users")
        self.assertEqual(icon_for_label("الرئيسية"), "home")
        self.assertEqual(icon_for_label("طلبات قص الدرف"), "clipboard")
        self.assertEqual(icon_for_label("تحليل طلبات القص"), "es-line-reports")

    def test_apply_sidebar_icon_catalog_mutates_boot_items(self) -> None:
        bootinfo = {
            "workspace_sidebar_item": {
                "almdina erp": {
                    "items": [
                        {"label": "الزبائن", "type": "Link", "icon": "list"},
                        {"label": "Section", "type": "Section Break"},
                    ]
                }
            }
        }
        apply_sidebar_icon_catalog(bootinfo)
        items = bootinfo["workspace_sidebar_item"]["almdina erp"]["items"]
        self.assertEqual(items[0]["icon"], "users")
        self.assertNotIn("icon", items[1])

    def test_catalog_covers_workspace_shortcut_labels(self) -> None:
        expected = {
            "الزبائن",
            "إعدادات المعمل",
            "إدارة الأدوار",
            "إدارة الصلاحيات",
            "إدارة المستخدمين",
            "إدارة مسارات الإنتاج",
            "طلبات قص الدرف",
            "مراحل الإنتاج",
        }
        self.assertTrue(expected.issubset(set(SHORTCUT_ICONS_BY_LABEL)))
        self.assertIn("أنواع القشاط", next(k for k in SHORTCUT_ICONS_BY_LABEL if k.startswith("أنواع القشاط")))


if __name__ == "__main__":
    unittest.main()
