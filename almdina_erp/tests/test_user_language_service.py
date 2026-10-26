from __future__ import annotations

import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.language_catalog import (
    FrappeLanguageCatalog,
)
from almdina_erp.almdina_erp.infrastructure.frappe.ui_language_catalog import (
    almdina_ui_languages,
)
from almdina_erp.almdina_erp.services.user_language_service import (
    set_current_user_language,
)
from almdina_erp.boot import boot_session


class TestUserLanguageService(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self._ensure_language("ar", "العربية", enabled=1)
        self._ensure_language("en", "English", enabled=1)
        self._ensure_language("fr", "Français", enabled=1)
        self._ensure_language("zu", "Zulu", enabled=0)

    def _ensure_language(self, code: str, name: str, *, enabled: int) -> None:
        if frappe.db.exists("Language", code):
            frappe.db.set_value(
                "Language",
                code,
                {"enabled": enabled, "language_name": name},
            )
            return
        frappe.get_doc({
            "doctype": "Language",
            "language_code": code,
            "language_name": name,
            "enabled": enabled,
        }).insert(ignore_permissions=True)

    def _user(self, email: str, language: str) -> None:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": "Language",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
            })
            user.insert(ignore_permissions=True)
        user.language = language
        user.save(ignore_permissions=True)
        self.addCleanup(self._delete_user, email)

    def _delete_user(self, email: str) -> None:
        frappe.set_user("Administrator")
        if frappe.db.exists("User", email):
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)

    def test_boot_session_exposes_the_switcher_catalog(self) -> None:
        bootinfo: dict = {}
        boot_session(bootinfo)
        codes = {language["code"] for language in bootinfo["almdina_ui_languages"]}
        self.assertEqual(codes, {"ar", "en"})
        arabic = next(language for language in bootinfo["almdina_ui_languages"] if language["code"] == "ar")
        self.assertEqual(set(arabic), {"code", "name", "direction"})

    def test_live_switcher_catalog_is_arabic_and_english(self) -> None:
        codes = {language["code"] for language in almdina_ui_languages()}
        self.assertEqual(codes, {"ar", "en"})
        enabled = {language["code"] for language in FrappeLanguageCatalog().enabled_languages()}
        self.assertIn("fr", enabled)
        self.assertNotIn("zu", enabled)

    def test_guest_is_rejected(self) -> None:
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            set_current_user_language("en")

    def test_unavailable_language_is_rejected(self) -> None:
        email = "language-switcher-invalid@example.com"
        self._user(email, "ar")
        frappe.set_user(email)
        with self.assertRaises(frappe.ValidationError):
            set_current_user_language("fr")
        with self.assertRaises(frappe.ValidationError):
            set_current_user_language("zu")
        self.assertEqual(frappe.db.get_value("User", email, "language"), "ar")

    def test_only_the_session_user_language_changes(self) -> None:
        current = "language-switcher-current@example.com"
        other = "language-switcher-other@example.com"
        self._user(current, "ar")
        self._user(other, "ar")
        frappe.set_user(current)

        result = set_current_user_language("EN")

        self.assertEqual(result, {"language": "en"})
        self.assertEqual(frappe.db.get_value("User", current, "language"), "en")
        self.assertEqual(frappe.db.get_value("User", other, "language"), "ar")

    def test_client_cannot_name_another_user(self) -> None:
        self.assertEqual(
            list(inspect.signature(set_current_user_language).parameters),
            ["language"],
        )
        with self.assertRaises(TypeError):
            set_current_user_language("en", user="language-switcher-other@example.com")
        with self.assertRaises(TypeError):
            set_current_user_language("en", email="language-switcher-other@example.com")
