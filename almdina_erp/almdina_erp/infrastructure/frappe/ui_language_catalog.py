"""Languages shown by the Almdina Desk language switcher.

This list is not the workforce catalog. ``FrappeLanguageCatalog.enabled_languages``
still returns every enabled Language record. The switcher offers an enabled
language when it is English, the message-id language, which does not need
``translations/en.csv``, or when ``translations/<language-code>.csv`` exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from almdina_erp.almdina_erp.infrastructure.frappe.language_catalog import (
    FrappeLanguageCatalog,
    stored_language_code,
)


# English identifiers are the source messages. An enabled ``en`` row is offered
# even when the app has no en.csv. This is not a closed language set.
MESSAGE_ID_LANGUAGE = "en"


def default_translations_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "translations"


def language_match_key(language_code: str) -> str:
    return stored_language_code(language_code).lower()


def translation_catalog_keys(translations_dir: Path | None = None) -> frozenset[str]:
    directory = translations_dir or default_translations_directory()
    if not directory.is_dir():
        return frozenset()
    keys: set[str] = set()
    for path in directory.glob("*.csv"):
        if not path.is_file():
            continue
        key = language_match_key(path.stem)
        if key:
            keys.add(key)
    return frozenset(keys)


def almdina_ui_languages(
    catalog: FrappeLanguageCatalog | None = None,
    translations_dir: Path | None = None,
) -> list[dict[str, str]]:
    source = catalog or FrappeLanguageCatalog()
    catalogs = translation_catalog_keys(translations_dir)
    selected: list[dict[str, str]] = []
    for language in source.enabled_languages():
        if not isinstance(language, Mapping):
            continue
        code = str(language.get("code") or "")
        key = language_match_key(code)
        if not key:
            continue
        if key == MESSAGE_ID_LANGUAGE or key in catalogs:
            selected.append({
                "code": code,
                "name": str(language.get("name") or code),
                "direction": str(language.get("direction") or ""),
            })
    return selected


def resolve_ui_language(
    language: str,
    languages: list[dict[str, str]] | None = None,
) -> str | None:
    requested = language_match_key(language)
    if not requested:
        return None
    available = languages if languages is not None else almdina_ui_languages()
    for row in available:
        code = str(row.get("code") or "")
        if language_match_key(code) == requested:
            return code
    return None


__all__ = [
    "MESSAGE_ID_LANGUAGE",
    "almdina_ui_languages",
    "default_translations_directory",
    "language_match_key",
    "resolve_ui_language",
    "translation_catalog_keys",
]
