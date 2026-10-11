from __future__ import annotations

import frappe


# Same base languages Frappe treats as RTL in frappe.utils.jinja_globals.is_rtl.
RTL_BASE_LANGUAGES = frozenset({"ar", "he", "fa", "ps"})


def language_direction(language_code: str) -> str:
    base = str(language_code or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return "rtl" if base in RTL_BASE_LANGUAGES else "ltr"


class FrappeLanguageCatalog:
    """Read-only view of languages enabled on the Language DocType.

    Knowing a language code does not grant any capability. The read uses the
    caller's own permissions and does not write Language records.
    """

    def enabled_languages(self) -> list[dict[str, str]]:
        rows = frappe.get_all(
            "Language",
            filters={"enabled": 1},
            fields=["language_code", "language_name"],
            order_by="language_name asc",
        )
        languages: list[dict[str, str]] = []
        for row in rows:
            code = str(row.get("language_code") or "").strip().lower().replace("_", "-")
            if not code:
                continue
            name = str(row.get("language_name") or "").strip() or code
            languages.append({
                "code": code,
                "name": name,
                "direction": language_direction(code),
            })
        return languages


def enabled_language_codes(catalog: FrappeLanguageCatalog | None = None) -> frozenset[str]:
    source = catalog or FrappeLanguageCatalog()
    return frozenset(language["code"] for language in source.enabled_languages())


__all__ = [
    "RTL_BASE_LANGUAGES",
    "FrappeLanguageCatalog",
    "enabled_language_codes",
    "language_direction",
]
