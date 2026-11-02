"""Persistence for one board-editor draft per order and source plan.

Writes this DocType only. It does not update Cutting Plan snapshot, status,
approval, placed pieces, or financial fields.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import (
    DraftInsertConflict,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import draft_key

DOCTYPE = "Board Editor Draft"


class FrappeBoardEditorDraftStore:
    def lock(self, key: str) -> dict[str, Any] | None:
        if not _table_ready():
            return None
        rows = frappe.db.sql(
            f"""
            SELECT name, draft_key, door_cutting_order, source_plan,
                   source_input_fingerprint, source_content_revision,
                   draft_version, distribution_fingerprint, layout_json
            FROM `tab{DOCTYPE}`
            WHERE draft_key=%s
            FOR UPDATE
            """,
            (key,),
            as_dict=True,
        )
        if not rows:
            return None
        return _row_to_record(rows[0])

    def insert(self, row: Mapping[str, Any]) -> dict[str, Any]:
        if not _table_ready():
            frappe.throw("Board editor drafts are not installed. Run migrate.")
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "draft_key": row["draft_key"],
                "door_cutting_order": row["door_cutting_order"],
                "source_plan": row["source_plan"],
                "source_input_fingerprint": row.get("source_input_fingerprint") or "",
                "source_content_revision": row.get("source_content_revision") or "",
                "draft_version": int(row["draft_version"]),
                "distribution_fingerprint": row["distribution_fingerprint"],
                "layout_json": json.dumps(row["layout_json"], separators=(",", ":"), sort_keys=True),
            }
        )
        try:
            doc.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError as exc:
            raise DraftInsertConflict from exc
        return _row_to_record(doc)

    def update_if_version(
        self,
        key: str,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> bool:
        current = self.lock(key)
        if current is None or int(current["draft_version"]) != int(expected_version):
            return False
        frappe.db.set_value(
            DOCTYPE,
            current["name"],
            {
                "draft_version": int(changes["draft_version"]),
                "distribution_fingerprint": changes["distribution_fingerprint"],
                "source_input_fingerprint": changes.get("source_input_fingerprint") or "",
                "source_content_revision": changes.get("source_content_revision") or "",
                "layout_json": json.dumps(
                    changes["layout_json"],
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
            update_modified=True,
        )
        return True


def read_editor_draft(
    order_name: str,
    plan_name: str,
    *,
    source_content_revision: str,
    source_input_fingerprint: str,
) -> dict[str, Any]:
    """Return draft metadata. An incompatible layout is not sent to the client."""

    empty = {
        "present": False,
        "compatible": False,
        "conflict": None,
        "draft_version": 0,
        "source_content_revision": "",
        "source_input_fingerprint": source_input_fingerprint,
        "distribution_fingerprint": "",
        "layout": None,
    }
    if not _table_ready():
        return empty
    key = draft_key(order_name, plan_name)
    row = frappe.db.get_value(
        DOCTYPE,
        {"draft_key": key},
        [
            "draft_version",
            "source_content_revision",
            "source_input_fingerprint",
            "distribution_fingerprint",
            "layout_json",
        ],
        as_dict=True,
    )
    if not row:
        return empty
    stored_revision = str(row.source_content_revision or "")
    compatible = stored_revision == str(source_content_revision or "")
    layout = None
    if compatible:
        try:
            parsed = json.loads(row.layout_json or "")
        except (TypeError, ValueError):
            parsed = None
        layout = parsed if isinstance(parsed, dict) else None
        compatible = layout is not None
    return {
        "present": True,
        "compatible": compatible,
        "conflict": None if compatible else "source",
        "draft_version": int(row.draft_version or 0),
        "source_content_revision": stored_revision,
        "source_input_fingerprint": str(row.source_input_fingerprint or ""),
        "distribution_fingerprint": str(row.distribution_fingerprint or ""),
        "layout": layout if compatible else None,
    }


def _table_ready() -> bool:
    return bool(frappe.db.table_exists(DOCTYPE))


def _row_to_record(row: Any) -> dict[str, Any]:
    layout = row.get("layout_json") if isinstance(row, Mapping) else row.layout_json
    if isinstance(layout, str):
        layout = json.loads(layout)
    name = row.get("name") if isinstance(row, Mapping) else row.name
    def value(field: str) -> Any:
        if isinstance(row, Mapping):
            return row.get(field)
        return getattr(row, field)

    return {
        "name": name,
        "draft_key": value("draft_key"),
        "door_cutting_order": value("door_cutting_order"),
        "source_plan": value("source_plan"),
        "source_input_fingerprint": value("source_input_fingerprint") or "",
        "source_content_revision": value("source_content_revision") or "",
        "draft_version": int(value("draft_version") or 0),
        "distribution_fingerprint": value("distribution_fingerprint"),
        "layout_json": layout,
    }
