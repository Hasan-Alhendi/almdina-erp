from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.language_catalog import (
    FrappeLanguageCatalog,
    language_direction,
)
from almdina_erp.almdina_erp.services.workforce_service import (
    create_workforce_user,
    get_workforce_console,
)


class TestLanguageCatalogIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self._ensure_language("ar", "العربية", enabled=1)
        self._ensure_language("fr", "Français", enabled=1)
        self._ensure_language("pt-BR", "Português (Brasil)", enabled=1)
        self._ensure_language("zh-TW", "繁體中文", enabled=1)
        self._ensure_language("zu", "Zulu", enabled=0)

    def _ensure_language(self, code: str, name: str, *, enabled: int) -> None:
        if frappe.db.exists("Language", code):
            frappe.db.set_value("Language", code, {"enabled": enabled, "language_name": name})
            return
        frappe.get_doc({
            "doctype": "Language",
            "language_code": code,
            "language_name": name,
            "enabled": enabled,
        }).insert(ignore_permissions=True)

    def test_catalog_exposes_enabled_languages_without_extra_fields(self) -> None:
        self.assertEqual(language_direction("ar"), "rtl")
        self.assertEqual(language_direction("AR"), "rtl")
        self.assertEqual(language_direction("fa"), "rtl")
        self.assertEqual(language_direction("he"), "rtl")
        self.assertEqual(language_direction("ps"), "rtl")
        self.assertEqual(language_direction("fr"), "ltr")
        self.assertEqual(language_direction("pt-BR"), "ltr")
        self.assertEqual(language_direction("zh-TW"), "ltr")
        languages = FrappeLanguageCatalog().enabled_languages()
        codes = {language["code"] for language in languages}
        self.assertIn("ar", codes)
        self.assertIn("fr", codes)
        self.assertIn("pt-BR", codes)
        self.assertIn("zh-TW", codes)
        self.assertNotIn("pt-br", codes)
        self.assertNotIn("zh-tw", codes)
        self.assertNotIn("zu", codes)
        french = next(language for language in languages if language["code"] == "fr")
        self.assertEqual(french["name"], "Français")
        self.assertEqual(french["direction"], "ltr")
        self.assertEqual(set(french), {"code", "name", "direction"})

    def test_workforce_console_returns_the_enabled_catalog(self) -> None:
        console = get_workforce_console()
        codes = {language["code"] for language in console["languages"]}
        self.assertIn("fr", codes)
        self.assertNotIn("zu", codes)

    def test_service_rejects_a_disabled_language(self) -> None:
        with self.assertRaises(frappe.ValidationError) as raised:
            create_workforce_user({
                "email": "disabled-language@example.com",
                "first_name": "Disabled",
                "language": "zu",
                "temporary_password": "SecurePass123!",
                "roles": [],
            })
        self.assertIn(
            frappe._("The selected user language is not supported."),
            str(raised.exception),
        )
        self.assertFalse(frappe.db.exists("User", "disabled-language@example.com"))

    def test_service_accepts_an_enabled_third_language(self) -> None:
        created = create_workforce_user({
            "email": "french-worker@example.com",
            "first_name": "French",
            "language": "fr",
            "temporary_password": "SecurePass123!",
            "roles": [],
        })
        self.assertEqual(created["user"]["language"], "fr")
        self.assertEqual(frappe.db.get_value("User", "french-worker@example.com", "language"), "fr")

    def test_service_stores_the_official_language_code(self) -> None:
        created = create_workforce_user({
            "email": "brazil-worker@example.com",
            "first_name": "Brazil",
            "language": "pt-br",
            "temporary_password": "SecurePass123!",
            "roles": [],
        })
        self.assertEqual(created["user"]["language"], "pt-BR")
        self.assertEqual(
            frappe.db.get_value("User", "brazil-worker@example.com", "language"),
            "pt-BR",
        )
