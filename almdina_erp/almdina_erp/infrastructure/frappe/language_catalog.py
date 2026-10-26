from __future__ import annotations

from collections.abc import Iterable, Mapping


# Same base languages Frappe treats as RTL in frappe.utils.jinja_globals.is_rtl.
RTL_BASE_LANGUAGES = frozenset({"ar", "he", "fa", "ps"})


def stored_language_code(language_code: str) -> str:
    """Return the code Frappe stored, with underscores written as hyphens.

    Casing is part of the official code (``pt-BR``, ``zh-TW``). Comparison
    elsewhere may casefold a copy; this value is what Language and translation
    files use.
    """
    return str(language_code or "").strip().replace("_", "-")


def language_direction(language_code: str) -> str:
    base = stored_language_code(language_code).lower().split("-", 1)[0]
    return "rtl" if base in RTL_BASE_LANGUAGES else "ltr"


def present_enabled_languages(rows: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    languages: list[dict[str, str]] = []
    for row in rows:
        code = stored_language_code(str(row.get("language_code") or ""))
        if not code:
            continue
        name = str(row.get("language_name") or "").strip() or code
        languages.append({
            "code": code,
            "name": name,
            "direction": language_direction(code),
        })
    return languages


class FrappeLanguageCatalog:
    """Read-only view of languages enabled on the Language DocType.

    Knowing a language code does not grant any capability. ``frappe.get_all``
    bypasses DocType read permissions, so this list is not filtered by the
    caller's Language permissions. The adapter does not write Language records
    and does not grant access to any other document.
    """

    def enabled_languages(self) -> list[dict[str, str]]:
        import frappe

        rows = frappe.get_all(
            "Language",
            filters={"enabled": 1},
            fields=["language_code", "language_name"],
            order_by="language_name asc",
        )
        return present_enabled_languages(rows)


def enabled_language_codes(catalog: FrappeLanguageCatalog | None = None) -> frozenset[str]:
    source = catalog or FrappeLanguageCatalog()
    return frozenset(language["code"] for language in source.enabled_languages())


__all__ = [
    "RTL_BASE_LANGUAGES",
    "FrappeLanguageCatalog",
    "enabled_language_codes",
    "language_direction",
    "present_enabled_languages",
    "stored_language_code",
]
