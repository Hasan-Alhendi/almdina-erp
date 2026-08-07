from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSFER = ROOT / "almdina_erp" / "application" / "security" / "permission_transfer.py"
SERVICE = ROOT / "almdina_erp" / "services" / "permission_management_service.py"
PAGE = ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js"


class TestPermissionTransfer(unittest.TestCase):
    def test_permission_transfer_module_is_not_part_of_runtime(self) -> None:
        self.assertFalse(TRANSFER.exists())

    def test_permission_service_exposes_manual_editing_only(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        for token in (
            "export_role_permissions",
            "export_permission_bundle",
            "preview_permission_import",
            "preview_permission_bundle_import",
            "import_permission_bundle",
            "PERMISSION_TRANSFER_SCHEMA",
            "permission_transfer",
            "Almdina Permission Import",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertIn("preview_role_permissions", source)
        self.assertIn("update_role_permissions", source)

    def test_permission_ui_has_no_import_export_or_template_shortcut(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        for token in (
            "apc-export",
            "apc-import",
            "تصدير JSON",
            "استيراد للمعاينة",
            "preview_permission_import",
            "export_role_permissions",
            "permission_bundle",
            "PermissionTemplate",
            "تطبيق قالب",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertIn("حدد صلاحياته يدويًا", source)


if __name__ == "__main__":
    unittest.main()
