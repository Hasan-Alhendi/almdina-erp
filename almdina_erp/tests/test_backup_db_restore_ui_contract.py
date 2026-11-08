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
API = ROOT / "public" / "js" / "factory_production_settings" / "api.js"


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
        cls.api = API.read_text(encoding="utf-8")

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
        self.assertIn("dbRestoreSection", self.view_model)
        self.assertIn("backupScheduleSection", self.view_model)
        self.assertIn("db_restore_type", self.view_model)
        self.assertIn('section === "db_restore"', self.dialogs)
        self.assertIn('fieldname: "db_restore_root_password"', self.dialogs)

    def test_backup_panel_wires_delete_search_filters_and_details(self) -> None:
        self.assertIn("deleteBackup", self.api)
        self.assertIn("delete_backup", self.service)
        self.assertIn("deleteBackup", self.backup_panel)
        self.assertIn("aps-backup-delete", self.backup_panel)
        self.assertIn("openBackupDelete", self.backup_panel)
        self.assertIn("openBackupDetails", self.backup_panel)
        self.assertIn("aps-backup-details", self.renderer)
        self.assertIn("aps-backup-delete", self.renderer)
        self.assertIn("data-backup-summary", self.renderer)
        self.assertIn("data-backup-toolbar", self.renderer)
        self.assertIn("data-backup-filter", self.renderer)
        self.assertIn("data-backup-advanced", self.renderer)
        self.assertIn("filterBackupRows", self.renderer)
        self.assertIn("can_download", self.renderer)
        self.assertIn("aps-backup-retry", self.renderer)
        self.assertIn("next_retry_on", self.renderer)
        self.assertIn('t("Encrypted External path")', self.renderer)
        self.assertIn("openBackupDelete", self.dialogs)
        self.assertIn("openBackupDetails", self.dialogs)
        self.assertIn("Remote external files will not be removed", self.dialogs)

    def test_delete_label_has_arabic_translation_without_required_context(self) -> None:
        translations = (ROOT / "translations" / "ar.csv").read_text(encoding="utf-8")
        self.assertRegex(translations, r"(?m)^Delete,حذف(?:$|,)")
        self.assertIn("frappe.db.commit()", (ROOT / "almdina_erp" / "infrastructure" / "backups" / "delete_backup.py").read_text(encoding="utf-8"))
        self.assertIn('operation_type || "") === "Restore"', self.renderer)

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

    def test_download_button_and_endpoint_use_operation_id(self) -> None:
        self.assertIn("download_backup_zip", self.service)
        self.assertIn("MANAGE_BACKUPS", self.service)
        self.assertIn("aps-backup-download", self.renderer)
        self.assertIn('t("Download")', self.renderer)
        self.assertIn("can_download", self.renderer)
        self.assertIn("downloadBackup", self.backup_panel)
        self.assertIn("downloadBackupZipMethod", self.backup_panel)
        self.assertIn("parseDownloadErrorPayload", self.backup_panel)
        self.assertIn('form.method = "POST"', self.backup_panel)
        self.assertIn("iframe", self.backup_panel)
        self.assertNotIn("window.open(url", self.backup_panel)
        self.assertIn("downloadBackupZipMethod", self.api)
        self.assertIn("operation_id", self.backup_panel)
        self.assertIn("importBackupZip", self.api)
        self.assertIn("import_backup_zip", self.service)
        self.assertIn("aps-backup-import", self.renderer)
        self.assertIn('t("Import Backup")', self.renderer)
        self.assertIn("importBackup", self.backup_panel)
        self.assertIn('allowed_file_types: [".zip"]', self.backup_panel)
        self.assertIn('t("Backup imported successfully.")', self.backup_panel)
        self.assertIn('t("Validating and importing the backup package...")', self.backup_panel)
        translations = (ROOT / "translations" / "ar.csv").read_text(encoding="utf-8")
        for key in (
            "Import Backup",
            "Backup imported successfully.",
            "Could not import the backup package.",
            "A backup with these files already exists on this site.",
            "You do not have permission to import backups.",
        ):
            self.assertIn(key, translations)


if __name__ == "__main__":
    unittest.main()
