from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "almdina_erp" / "application" / "security" / "workforce_management.py"
SERVICE = ROOT / "almdina_erp" / "services" / "workforce_service.py"
ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "language_catalog.py"
ASSETS = ROOT / "frontend_assets.py"
LOCALE = ROOT / "public" / "js" / "almdina_locale.js"


class TestDynamicLanguageFoundation(unittest.TestCase):
    def test_application_stays_framework_free_without_a_fixed_language_set(self) -> None:
        source = APPLICATION.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("SUPPORTED_LANGUAGES", source)
        self.assertNotIn('{"ar", "en"}', source)
        self.assertIn("allowed_languages", source)
        self.assertIn("WorkforceLanguageError", source)

    def test_enabled_catalog_accepts_a_third_language_and_rejects_others(self) -> None:
        from almdina_erp.almdina_erp.application.security.workforce_management import (
            WorkforceLanguageError,
            normalize_identity,
            normalize_language_code,
        )

        enabled = {"ar", "en", "fr"}
        self.assertEqual(normalize_language_code("FR", allowed_languages=enabled), "fr")
        identity = normalize_identity(
            email="worker@example.com",
            first_name="Worker",
            language="fr",
            allowed_languages=enabled,
        )
        self.assertEqual(identity.language, "fr")
        self.assertEqual(normalize_language_code("", allowed_languages=enabled), "ar")

        with self.assertRaises(WorkforceLanguageError) as disabled:
            normalize_language_code("de", allowed_languages=enabled)
        self.assertEqual(disabled.exception.code, "unsupported_language")
        self.assertEqual(disabled.exception.params["language"], "de")

        with self.assertRaises(WorkforceLanguageError) as invalid:
            normalize_language_code("not a language", allowed_languages=enabled)
        self.assertEqual(invalid.exception.code, "invalid_language_code")

    def test_official_frappe_language_codes_keep_their_casing(self) -> None:
        from almdina_erp.almdina_erp.application.security.workforce_management import (
            WorkforceLanguageError,
            normalize_language_code,
        )
        from almdina_erp.almdina_erp.infrastructure.frappe.language_catalog import (
            language_direction,
            present_enabled_languages,
            stored_language_code,
        )

        enabled = {"ar", "fr", "pt-BR", "zh-TW"}
        self.assertEqual(normalize_language_code("ar", allowed_languages=enabled), "ar")
        self.assertEqual(normalize_language_code("fr", allowed_languages=enabled), "fr")
        self.assertEqual(normalize_language_code("pt-BR", allowed_languages=enabled), "pt-BR")
        self.assertEqual(normalize_language_code("pt-br", allowed_languages=enabled), "pt-BR")
        self.assertEqual(normalize_language_code("PT_br", allowed_languages=enabled), "pt-BR")
        self.assertEqual(normalize_language_code("zh-TW", allowed_languages=enabled), "zh-TW")
        self.assertEqual(normalize_language_code("zh_tw", allowed_languages=enabled), "zh-TW")
        self.assertEqual(stored_language_code("pt_BR"), "pt-BR")
        self.assertEqual(stored_language_code("zh-TW"), "zh-TW")

        for code, direction in (
            ("ar", "rtl"),
            ("AR", "rtl"),
            ("fa", "rtl"),
            ("he", "rtl"),
            ("ps", "rtl"),
            ("fr", "ltr"),
            ("pt-BR", "ltr"),
            ("zh-TW", "ltr"),
        ):
            self.assertEqual(language_direction(code), direction, code)

        presented = present_enabled_languages([
            {"language_code": "pt-BR", "language_name": "Português (Brasil)"},
            {"language_code": "zh_TW", "language_name": "繁體中文"},
            {"language_code": "ar", "language_name": "العربية"},
            {"language_code": "  ", "language_name": "blank"},
        ])
        self.assertEqual([item["code"] for item in presented], ["pt-BR", "zh-TW", "ar"])
        self.assertEqual(presented[0]["direction"], "ltr")
        self.assertEqual(presented[2]["direction"], "rtl")
        self.assertNotIn("pt-br", [item["code"] for item in presented])

        with self.assertRaises(WorkforceLanguageError) as disabled:
            normalize_language_code("de", allowed_languages=enabled)
        self.assertEqual(disabled.exception.code, "unsupported_language")

        with self.assertRaises(WorkforceLanguageError) as invalid:
            normalize_language_code("not a language", allowed_languages=enabled)
        self.assertEqual(invalid.exception.code, "invalid_language_code")

    def test_service_rejects_disabled_languages_through_the_catalog(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("FrappeLanguageCatalog", source)
        self.assertIn("enabled_language_codes", source)
        self.assertIn('"languages": _language_catalog.enabled_languages()', source)
        self.assertIn("The selected user language is not supported.", source)
        self.assertIn("The language code is invalid.", source)
        self.assertNotIn("SUPPORTED_LANGUAGES", source)
        self.assertNotIn("ignore_permissions", source)

    def test_language_adapter_is_read_only(self) -> None:
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn('filters={"enabled": 1}', source)
        self.assertIn('"Language"', source)
        self.assertNotIn("ignore_permissions", source)
        self.assertNotIn("frappe.db.set_value", source)
        self.assertNotIn("insert(", source)
        self.assertIn('RTL_BASE_LANGUAGES = frozenset({"ar", "he", "fa", "ps"})', source)
        self.assertIn("def stored_language_code", source)
        self.assertIn("bypasses DocType read permissions", source)
        helper = source.split("def stored_language_code", 1)[1].split("def ", 1)[0]
        self.assertNotIn(".lower(", helper)

    def test_locale_asset_loads_before_consumers(self) -> None:
        source = ASSETS.read_text(encoding="utf-8")
        locale_asset = '"/assets/almdina_erp/js/almdina_locale.js"'
        foundation_asset = '"/assets/almdina_erp/js/frontend_foundation.js?v=2"'
        self.assertEqual(source.count(locale_asset), 1)
        self.assertLess(source.index(locale_asset), source.index(foundation_asset))
        self.assertNotIn("arabic_operator_ui.js", source)

        locale = LOCALE.read_text(encoding="utf-8")
        for export in ("currentLanguage", "direction", "isRTL", "translate", "translateLabel", "context"):
            self.assertIn(export, locale)
        self.assertNotIn("navigator.language", locale)
        self.assertNotIn("MutationObserver", locale)
        self.assertIn("window.__", locale)
