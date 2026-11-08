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
        columns = (
            "name, draft_key, door_cutting_order, source_plan, "
            "source_input_fingerprint, source_content_revision, "
            "draft_version, distribution_fingerprint, layout_json"
        )
        if _archive_column_ready():
            columns += ", prior_draft_archive_json"
        if _create_tracking_ready():
            columns += (
                ", last_create_request_id, last_created_plan, last_created_draft_version"
            )
        rows = frappe.db.sql(
            f"""
            SELECT {columns}
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
        values = {
            "draft_version": int(changes["draft_version"]),
            "distribution_fingerprint": changes["distribution_fingerprint"],
            "source_input_fingerprint": changes.get("source_input_fingerprint") or "",
            "source_content_revision": changes.get("source_content_revision") or "",
            "layout_json": json.dumps(
                changes["layout_json"],
                separators=(",", ":"),
                sort_keys=True,
            ),
        }
        if _archive_column_ready() and "prior_draft_archive_json" in changes:
            archive = changes.get("prior_draft_archive_json")
            values["prior_draft_archive_json"] = (
                ""
                if archive in (None, "")
                else json.dumps(archive, separators=(",", ":"), sort_keys=True)
            )
        frappe.db.set_value(
            DOCTYPE,
            current["name"],
            values,
            update_modified=True,
        )
        return True

    def record_create(
        self,
        *,
        draft_name: str,
        request_id: str,
        plan_name: str,
        draft_version: int,
    ) -> None:
        if not _create_tracking_ready():
            frappe.throw("Board editor create tracking is not installed. Run migrate.")
        frappe.db.set_value(
            DOCTYPE,
            draft_name,
            {
                "last_create_request_id": str(request_id or ""),
                "last_created_plan": str(plan_name or ""),
                "last_created_draft_version": int(draft_version or 0),
            },
            update_modified=False,
        )


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
        "name": "",
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
            "name",
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
    from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
        tokens_operationally_equivalent,
    )

    stored_revision = str(row.source_content_revision or "")
    live_revision = str(source_content_revision or "")
    # Operational equivalence (not raw string equality): legacy empty/datetime
    # layout slots may match a live saved_layout_sha when fingerprint+revision
    # already agree. Real fingerprint/layout mismatches stay incompatible.
    compatible = tokens_operationally_equivalent(stored_revision, live_revision)
    layout = None
    if compatible:
        try:
            parsed = json.loads(row.layout_json or "")
        except (TypeError, ValueError):
            parsed = None
        layout = parsed if isinstance(parsed, dict) else None
        compatible = layout is not None
        # Prefer the live encoding for the client so the next save does not
        # re-introduce the legacy job-status label.
        if compatible and stored_revision != live_revision and live_revision:
            stored_revision = live_revision
    return {
        "present": True,
        "compatible": compatible,
        "conflict": None if compatible else "source",
        "name": str(row.name or ""),
        "draft_version": int(row.draft_version or 0),
        "source_content_revision": stored_revision,
        "source_input_fingerprint": str(row.source_input_fingerprint or ""),
        "distribution_fingerprint": str(row.distribution_fingerprint or ""),
        "layout": layout if compatible else None,
    }


def _table_ready() -> bool:
    return bool(frappe.db.table_exists(DOCTYPE))


def _archive_column_ready() -> bool:
    return bool(_table_ready() and frappe.db.has_column(DOCTYPE, "prior_draft_archive_json"))


def _create_tracking_ready() -> bool:
    return bool(
        _table_ready()
        and frappe.db.has_column(DOCTYPE, "last_create_request_id")
        and frappe.db.has_column(DOCTYPE, "last_created_plan")
        and frappe.db.has_column(DOCTYPE, "last_created_draft_version")
    )


def _row_to_record(row: Any) -> dict[str, Any]:
    layout = row.get("layout_json") if isinstance(row, Mapping) else row.layout_json
    if isinstance(layout, str):
        layout = json.loads(layout)
    name = row.get("name") if isinstance(row, Mapping) else row.name
    def value(field: str) -> Any:
        if isinstance(row, Mapping):
            return row.get(field)
        return getattr(row, field, None)

    archive = value("prior_draft_archive_json")
    if isinstance(archive, str) and archive.strip():
        try:
            archive = json.loads(archive)
        except (TypeError, ValueError):
            archive = None
    elif archive in ("", None):
        archive = None

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
        "prior_draft_archive_json": archive,
        "last_create_request_id": value("last_create_request_id") or "",
        "last_created_plan": value("last_created_plan") or "",
        "last_created_draft_version": int(value("last_created_draft_version") or 0),
    }
