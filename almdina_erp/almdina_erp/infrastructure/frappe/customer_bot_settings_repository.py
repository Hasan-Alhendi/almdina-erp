"""MariaDB store for the customer-bot switch, draft, and published copy.

The document is a Frappe Single, so its fields live in ``tabSingles``. A
write first claims the revision row. The other fields change only after that
claim, in the same request transaction. A draft write does not touch the
published copy. Publish does not change the switch.
"""

from __future__ import annotations

from collections.abc import Mapping

import frappe

from almdina_erp.almdina_erp.application.customer_bot.read_runtime import (
    CustomerBotRuntime,
    read_customer_bot_runtime,
)
from almdina_erp.almdina_erp.application.customer_bot.settings_commands import (
    CustomerBotSettingsMissing,
    CustomerBotSettingsSnapshot,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import dump_texts, load_texts


DOCTYPE = "Customer Bot Settings"


class FrappeCustomerBotSettingsRepository:
    def load(self) -> CustomerBotSettingsSnapshot:
        rows = frappe.db.sql(
            "select field, value from `tabSingles` where doctype=%s",
            (DOCTYPE,),
            as_dict=True,
        )
        data = {row.field: row.value for row in rows}
        if "revision" not in data:
            raise CustomerBotSettingsMissing
        return CustomerBotSettingsSnapshot(
            enabled=str(data.get("enabled") or "0") in {"1", "True"},
            revision=int(data.get("revision") or 0),
            draft=_texts(data.get("draft_texts")),
            published=_texts(data.get("published_texts")),
            published_on=_text(data.get("published_on")),
            published_by=_text(data.get("published_by")),
            modified=_text(data.get("modified")),
            modified_by=_text(data.get("modified_by")),
        )

    def save_draft(
        self,
        texts: Mapping[str, str],
        expected_revision: int,
        actor: str,
        modified: str,
    ) -> CustomerBotSettingsSnapshot | None:
        if not _write({"draft_texts": dump_texts(texts)}, expected_revision, actor, modified):
            return None
        return self.load()

    def publish(
        self,
        texts: Mapping[str, str],
        expected_revision: int,
        actor: str,
        modified: str,
    ) -> CustomerBotSettingsSnapshot | None:
        payload = dump_texts(texts)
        if not _write(
            {
                "draft_texts": payload,
                "published_texts": payload,
                "published_on": modified,
                "published_by": actor,
            },
            expected_revision,
            actor,
            modified,
        ):
            return None
        return self.load()

    def set_enabled(
        self,
        enabled: bool,
        expected_revision: int,
        actor: str,
        modified: str,
    ) -> CustomerBotSettingsSnapshot | None:
        if not _write({"enabled": 1 if enabled else 0}, expected_revision, actor, modified):
            return None
        return self.load()


def load_customer_bot_runtime() -> CustomerBotRuntime:
    """Current switch and published copy for a future inbound layer."""

    return read_customer_bot_runtime(FrappeCustomerBotSettingsRepository())


def _write(
    assignments: Mapping[str, object],
    expected_revision: int,
    actor: str,
    modified: str,
) -> bool:
    frappe.db.sql(
        """
        UPDATE `tabSingles`
        SET value = CAST(value AS UNSIGNED) + 1
        WHERE doctype=%s AND field='revision' AND value=%s
        """,
        (DOCTYPE, str(expected_revision)),
    )
    if int(frappe.db._cursor.rowcount) != 1:
        return False
    payload = dict(assignments)
    payload["modified"] = modified
    payload["modified_by"] = actor
    for field, value in payload.items():
        _upsert_single(field, "" if value is None else str(value))
    return True


def _upsert_single(field: str, value: str) -> None:
    frappe.db.sql(
        "update `tabSingles` set value=%s where doctype=%s and field=%s",
        (value, DOCTYPE, field),
    )
    if int(frappe.db._cursor.rowcount) == 1:
        return
    frappe.db.sql(
        "insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)",
        (DOCTYPE, field, value),
    )


def _texts(payload: object) -> dict[str, str]:
    parsed = load_texts(payload if isinstance(payload, str) else None)
    return parsed or {}


def _text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


__all__ = [
    "DOCTYPE",
    "FrappeCustomerBotSettingsRepository",
    "load_customer_bot_runtime",
]
