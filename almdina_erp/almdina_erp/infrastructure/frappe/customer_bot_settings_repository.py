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
    next_acceptance_epoch,
    read_customer_bot_runtime,
)
from almdina_erp.almdina_erp.application.customer_bot.settings_commands import (
    CustomerBotSettingsMissing,
    CustomerBotSettingsSnapshot,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
    dump_texts,
    load_texts,
    validate_texts,
)


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
            acceptance_epoch=int(data.get("acceptance_epoch") or 0),
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
        if not _claim_revision(expected_revision):
            return None
        currently_enabled, epoch = _locked_switch()
        new_epoch = next_acceptance_epoch(currently_enabled, epoch, enabled)
        assignments: dict[str, str] = {
            "enabled": "1" if enabled else "0",
            "modified": modified,
            "modified_by": actor,
        }
        if new_epoch != epoch:
            assignments["acceptance_epoch"] = str(new_epoch)
        for field, value in assignments.items():
            _upsert_single(field, value)
        return self.load()

    def published_if_same_acceptance(self, acceptance_epoch: int) -> dict[str, str] | None:
        if isinstance(acceptance_epoch, bool) or not isinstance(acceptance_epoch, int):
            return None
        rows = frappe.db.sql(
            """
            select field, value from `tabSingles`
            where doctype=%s and field in ('enabled', 'acceptance_epoch', 'published_texts')
            for update
            """,
            (DOCTYPE,),
            as_dict=True,
        )
        grouped: dict[str, str] = {}
        for row in rows:
            value = "" if row.value is None else str(row.value)
            previous = grouped.get(row.field)
            if previous is not None and previous != value:
                return None
            grouped[row.field] = value
        enabled = grouped.get("enabled", "0") in {"1", "True"}
        epoch = int(grouped.get("acceptance_epoch") or 0)
        if not enabled or epoch != acceptance_epoch:
            return None
        published = _texts(grouped.get("published_texts"))
        if validate_texts(published):
            return None
        return published


def load_customer_bot_runtime() -> CustomerBotRuntime:
    """Current switch and published copy for a future inbound layer."""

    return read_customer_bot_runtime(FrappeCustomerBotSettingsRepository())


def _write(
    assignments: Mapping[str, object],
    expected_revision: int,
    actor: str,
    modified: str,
) -> bool:
    if not _claim_revision(expected_revision):
        return False
    payload = dict(assignments)
    payload["modified"] = modified
    payload["modified_by"] = actor
    for field, value in payload.items():
        _upsert_single(field, "" if value is None else str(value))
    return True


def _claim_revision(expected_revision: int) -> bool:
    frappe.db.sql(
        """
        UPDATE `tabSingles`
        SET value = CAST(value AS UNSIGNED) + 1
        WHERE doctype=%s AND field='revision' AND value=%s
        """,
        (DOCTYPE, str(expected_revision)),
    )
    return int(frappe.db._cursor.rowcount) == 1


def _locked_switch() -> tuple[bool, int]:
    rows = frappe.db.sql(
        """
        select field, value from `tabSingles`
        where doctype=%s and field in ('enabled', 'acceptance_epoch')
        for update
        """,
        (DOCTYPE,),
        as_dict=True,
    )
    enabled_values = [str(row.value or "0") for row in rows if row.field == "enabled"]
    epoch_values = [int(row.value or 0) for row in rows if row.field == "acceptance_epoch"]
    return any(value in {"1", "True"} for value in enabled_values), max(epoch_values, default=0)


def _upsert_single(field: str, value: str) -> None:
    """Update every stored copy of one single field, and insert only when absent.

    MariaDB reports changed rows, not matched rows. A value that is already
    stored therefore has a changed-row count of zero, and several identical
    copies have a count other than one. Neither case means the field is missing.
    """

    existing = frappe.db.sql(
        "select 1 from `tabSingles` where doctype=%s and field=%s limit 1 for update",
        (DOCTYPE, field),
    )
    if existing:
        frappe.db.sql(
            "update `tabSingles` set value=%s where doctype=%s and field=%s",
            (value, DOCTYPE, field),
        )
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
