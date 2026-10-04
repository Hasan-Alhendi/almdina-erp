from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
)
from almdina_erp.almdina_erp.application.security.whatsapp_settings_capability_migration import (
    whatsapp_settings_capability_updates,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches.txt"
MIGRATION = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "whatsapp_settings_capability_migration.py"
)
SERVICE = ROOT / "almdina_erp" / "services" / "whatsapp_service.py"


class TestWhatsAppSettingsCapabilityMigration(unittest.TestCase):
    def test_presentation_splits_session_and_messages(self) -> None:
        session = CAPABILITY_PRESENTATION[Capability.MANAGE_WHATSAPP_SESSION]
        messages = CAPABILITY_PRESENTATION[Capability.EDIT_WHATSAPP_MESSAGES]
        print_identity = CAPABILITY_PRESENTATION[Capability.EDIT_FACTORY_PRINT_IDENTITY]
        self.assertEqual(session["label"], "إدارة جلسة واتساب")
        self.assertEqual(session["risk"], "critical")
        self.assertEqual(messages["label"], "تعديل رسائل واتساب")
        self.assertEqual(messages["risk"], "sensitive")
        self.assertIn("لا يشمل رسائل واتساب", print_identity["description"])

    def test_backfill_is_idempotent_and_role_name_free(self) -> None:
        migration = MIGRATION.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", migration)
        self.assertNotIn("Production Manager", migration)
        self.assertNotIn("System Manager", migration)
        states = {
            "SettingsViewer": {
                Capability.VIEW_FACTORY_SETTINGS: True,
                Capability.MANAGE_WHATSAPP_SESSION: False,
                Capability.EDIT_FACTORY_PRINT_IDENTITY: False,
                Capability.EDIT_WHATSAPP_MESSAGES: False,
            },
            "PrintEditor": {
                Capability.VIEW_FACTORY_SETTINGS: True,
                Capability.EDIT_FACTORY_PRINT_IDENTITY: True,
                Capability.MANAGE_WHATSAPP_SESSION: False,
                Capability.EDIT_WHATSAPP_MESSAGES: False,
            },
            "AlreadySplit": {
                Capability.VIEW_FACTORY_SETTINGS: True,
                Capability.MANAGE_WHATSAPP_SESSION: True,
                Capability.EDIT_FACTORY_PRINT_IDENTITY: True,
                Capability.EDIT_WHATSAPP_MESSAGES: True,
            },
            "Clerk": {
                Capability.VIEW_FACTORY_SETTINGS: False,
                Capability.EDIT_FACTORY_PRINT_IDENTITY: False,
                Capability.MANAGE_WHATSAPP_SESSION: False,
                Capability.EDIT_WHATSAPP_MESSAGES: False,
            },
        }
        updates = whatsapp_settings_capability_updates(states)
        self.assertEqual(set(updates), {"SettingsViewer", "PrintEditor"})
        self.assertTrue(updates["SettingsViewer"][Capability.MANAGE_WHATSAPP_SESSION])
        self.assertFalse(updates["SettingsViewer"][Capability.EDIT_WHATSAPP_MESSAGES])
        self.assertTrue(updates["PrintEditor"][Capability.MANAGE_WHATSAPP_SESSION])
        self.assertTrue(updates["PrintEditor"][Capability.EDIT_WHATSAPP_MESSAGES])
        migrated = {role: dict(state) for role, state in states.items()}
        migrated.update(updates)
        self.assertEqual(whatsapp_settings_capability_updates(migrated), {})
        self.assertIn(
            "almdina_erp.patches.v1_0.split_whatsapp_factory_settings_capabilities",
            PATCHES.read_text(encoding="utf-8"),
        )

    def test_session_rpcs_require_the_session_capability(self) -> None:
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("def _require_whatsapp_session() -> None:", service)
        self.assertIn("Capability.MANAGE_WHATSAPP_SESSION", service)
        self.assertNotIn("VIEW_FACTORY_SETTINGS", service)
        for endpoint in (
            "get_whatsapp_session",
            "create_whatsapp_session",
            "reconnect_whatsapp_session",
            "stop_whatsapp_session",
            "get_whatsapp_qr",
        ):
            block = service.split(f"def {endpoint}(", 1)[1].split("def ", 1)[0]
            self.assertIn("_require_whatsapp_session()", block)


if __name__ == "__main__":
    unittest.main()
