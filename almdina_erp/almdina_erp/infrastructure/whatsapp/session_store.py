from __future__ import annotations

import frappe


SETTINGS_DOCTYPE = "Almdina ERP Settings"
SESSION_ID_FIELD = "whatsapp_session_id"
SESSION_NAME_FIELD = "whatsapp_session_name"


class FrappeWhatsAppSessionStore:
    """Persist this site's OpenWA session id and name on the factory settings single."""

    def get_session_id(self) -> str:
        return _read_single(SESSION_ID_FIELD)

    def save_session_id(self, session_id: str) -> None:
        _write_single(SESSION_ID_FIELD, session_id)

    def get_session_name(self) -> str:
        return _read_single(SESSION_NAME_FIELD)

    def save_session_name(self, session_name: str) -> None:
        _write_single(SESSION_NAME_FIELD, session_name)


def _read_single(fieldname: str) -> str:
    row = frappe.db.sql(
        "select value from `tabSingles` where doctype = %s and field = %s",
        (SETTINGS_DOCTYPE, fieldname),
    )
    if row and row[0][0]:
        return str(row[0][0]).strip()
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    return str(settings.get(fieldname) or "").strip()


def _write_single(fieldname: str, value: object) -> None:
    stored = str(value or "").strip()
    frappe.db.sql(
        "select doctype from `tabSingles` where doctype = %s limit 1 for update",
        (SETTINGS_DOCTYPE,),
    )
    frappe.db.sql(
        "delete from `tabSingles` where doctype = %s and field = %s",
        (SETTINGS_DOCTYPE, fieldname),
    )
    if stored:
        frappe.db.sql(
            "insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)",
            (SETTINGS_DOCTYPE, fieldname, stored),
        )
    frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
    cache = getattr(frappe.db, "value_cache", None)
    if isinstance(cache, dict):
        cache.pop(SETTINGS_DOCTYPE, None)


__all__ = [
    "FrappeWhatsAppSessionStore",
    "SESSION_ID_FIELD",
    "SESSION_NAME_FIELD",
    "SETTINGS_DOCTYPE",
]
