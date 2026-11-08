from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "public" / "js" / "factory_production_settings" / "renderer.js"
BACKUP_PANEL = ROOT / "public" / "js" / "factory_production_settings" / "backup_panel.js"
VIEW_MODEL = ROOT / "public" / "js" / "factory_production_settings" / "view_model.js"
DIALOGS = ROOT / "public" / "js" / "factory_production_settings" / "dialogs.js"
SERVICE = ROOT / "almdina_erp" / "services" / "backup_restore_service.py"
SETTINGS_SERVICE = ROOT / "almdina_erp" / "services" / "production_settings_service.py"
FACTORY_SETTINGS = ROOT / "almdina_erp" / "domain" / "security" / "factory_settings.py"


class BackupDbRestoreUiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.renderer = RENDERER.read_text(encoding="utf-8")
        cls.backup_panel = BACKUP_PANEL.read_text(encoding="utf-8")
        cls.view_model = VIEW_MODEL.read_text(encoding="utf-8")
        cls.dialogs = DIALOGS.read_text(encoding="utf-8")
        cls.service = SERVICE.read_text(encoding="utf-8")
        cls.settings_service = SETTINGS_SERVICE.read_text(encoding="utf-8")
        cls.factory_settings = FACTORY_SETTINGS.read_text(encoding="utf-8")

    def test_backup_management_panel_owns_collapsible_db_fields(self) -> None:
        """Regression: DocType/dialog-only wiring left the Backup History panel without fields."""

        self.assertIn("function dbRestoreSettingsHtml(", self.renderer)
        self.assertIn("dbRestoreSettingsHtml(snapshot", self.renderer)
        self.assertIn('data-db-restore-settings', self.renderer)
        self.assertIn("Database & Restore Settings", self.renderer)
        for fieldname in (
            "db_restore_type",
            "db_restore_host",
            "db_restore_port",
            "db_restore_root_username",
            "db_restore_root_password",
        ):
            self.assertIn(f'data-db-restore-field="{fieldname}"', self.renderer)

    def test_password_is_write_only_in_panel_markup(self) -> None:
        self.assertIn('type="password"', self.renderer)
        self.assertIn('value=""', self.renderer)
        self.assertNotIn("db.db_restore_root_password ||", self.renderer)
        self.assertNotIn("db_root.password", self.renderer)

    def test_backup_context_feeds_panel_and_settings_persist_fields(self) -> None:
        self.assertIn('payload["db_root"] = public_db_root_settings()', self.service)
        self.assertIn("public_db_root_settings(settings)", self.settings_service)
        self.assertIn("db_restore_root_password", self.settings_service)
        self.assertIn("saveDbRestoreSettings", self.backup_panel)
        self.assertIn("readDbRestoreForm", self.backup_panel)

    def test_settings_card_and_edit_dialog_still_reference_db_fields(self) -> None:
        self.assertIn('t("Database & Restore Settings")', self.view_model)
        self.assertIn('section("db_restore"', self.view_model)
        self.assertIn("db_restore_type", self.view_model)
        self.assertIn('section === "db_restore"', self.dialogs)
        self.assertIn('fieldname: "db_restore_root_password"', self.dialogs)

    def test_domain_save_allowlist_includes_db_restore_fields(self) -> None:
        for fieldname in (
            "db_restore_type",
            "db_restore_host",
            "db_restore_port",
            "db_restore_root_username",
            "db_restore_root_password",
        ):
            self.assertIn(f'"{fieldname}"', self.factory_settings)
        self.assertIn("DB_RESTORE", self.factory_settings)
        self.assertIn("MANAGE_DB_RESTORE_SETTINGS", self.factory_settings)
        self.assertIn("decide_settings_update", self.factory_settings)
        self.assertIn("Unsupported factory setting fields", self.factory_settings)

    def test_backup_panel_and_test_endpoint_gate_on_db_restore_capability(self) -> None:
        self.assertIn("can_manage_db_restore_settings", self.service)
        self.assertIn("MANAGE_DB_RESTORE_SETTINGS", self.service)
        self.assertIn("can_manage_db_restore_settings", self.renderer)
        self.assertIn("canManageDbRestoreSettings", self.view_model)


if __name__ == "__main__":
    unittest.main()
