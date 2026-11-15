"""Persistence for one board-editor drawing per order, source plan, and piece.

Writes this DocType only. It does not update Cutting Plan snapshot, status,
approval, placed pieces, order geometry, or financial fields.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.board_editor_drawing_save import (
    DrawingInsertConflict,
)

DOCTYPE = "Board Editor Drawing Draft"


class FrappeBoardEditorDrawingStore:
    def lock(self, key: str) -> dict[str, Any] | None:
        if not drawing_storage_ready():
            return None
        rows = frappe.db.sql(
            f"""
            SELECT name, drawing_key, door_cutting_order, source_plan,
                piece_instance_id, source_input_fingerprint, source_content_revision,
                drawing_version, document_fingerprint, drawing_json,
                prior_drawing_archive_json
            FROM `tab{DOCTYPE}`
            WHERE drawing_key=%s
            FOR UPDATE
            """,
            (key,),
            as_dict=True,
        )
        if not rows:
            return None
        return _row_to_record(rows[0])

    def read(self, key: str) -> dict[str, Any] | None:
        if not drawing_storage_ready():
            return None
        row = frappe.db.get_value(
            DOCTYPE,
            {"drawing_key": key},
            [
                "name",
                "drawing_key",
                "door_cutting_order",
                "source_plan",
                "piece_instance_id",
                "source_input_fingerprint",
                "source_content_revision",
                "drawing_version",
                "document_fingerprint",
                "drawing_json",
                "prior_drawing_archive_json",
            ],
            as_dict=True,
        )
        if not row:
            return None
        return _row_to_record(row)

    def read_for_plan(self, order_name: str, plan_name: str) -> list[dict[str, Any]]:
        if not drawing_storage_ready():
            return []
        rows = frappe.db.sql(
            f"""
            SELECT name, drawing_key, door_cutting_order, source_plan,
                piece_instance_id, source_input_fingerprint, source_content_revision,
                drawing_version, document_fingerprint, drawing_json,
                prior_drawing_archive_json
            FROM `tab{DOCTYPE}`
            WHERE door_cutting_order=%s AND source_plan=%s
            """,
            (order_name, plan_name),
            as_dict=True,
        )
        return [_row_to_record(row) for row in rows]

    def insert(self, row: Mapping[str, Any]) -> dict[str, Any]:
        if not drawing_storage_ready():
            frappe.throw(_("Board editor drawings are not installed. Run migrate."))
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "drawing_key": row["drawing_key"],
                "door_cutting_order": row["door_cutting_order"],
                "source_plan": row["source_plan"],
                "piece_instance_id": row["piece_instance_id"],
                "source_input_fingerprint": row.get("source_input_fingerprint") or "",
                "source_content_revision": row.get("source_content_revision") or "",
                "drawing_version": int(row["drawing_version"]),
                "document_fingerprint": row["document_fingerprint"],
                "drawing_json": _dump(row["drawing_json"]),
                "prior_drawing_archive_json": _dump(row.get("prior_drawing_archive_json") or []),
            }
        )
        try:
            doc.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError as exc:
            raise DrawingInsertConflict from exc
        return _row_to_record(doc)

    def delete(self, key: str) -> None:
        if not drawing_storage_ready():
            return
        name = frappe.db.get_value(DOCTYPE, {"drawing_key": key}, "name")
        if not name:
            return
        frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)

    def update_if_version(
        self,
        key: str,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> bool:
        current = self.lock(key)
        if current is None or int(current["drawing_version"]) != int(expected_version):
            return False
        values = {
            "drawing_version": int(changes["drawing_version"]),
            "document_fingerprint": changes["document_fingerprint"],
            "source_input_fingerprint": changes.get("source_input_fingerprint") or "",
            "source_content_revision": changes.get("source_content_revision") or "",
            "drawing_json": _dump(changes["drawing_json"]),
        }
        if "prior_drawing_archive_json" in changes:
            values["prior_drawing_archive_json"] = _dump(changes.get("prior_drawing_archive_json") or [])
        frappe.db.set_value(DOCTYPE, current["name"], values, update_modified=True)
        return True

    def archive_many(self, updates: Sequence[Mapping[str, Any]]) -> bool:
        """Apply every archive update or none. Versions are checked before writes."""

        locked: list[dict[str, Any]] = []
        for update in updates:
            row = self.lock(str(update.get("drawing_key") or ""))
            if row is None or int(row["drawing_version"]) != int(update.get("expected_version") or 0):
                return False
            locked.append(row)
        for update, row in zip(updates, locked, strict=True):
            wrote = self.update_if_version(
                str(update["drawing_key"]),
                int(row["drawing_version"]),
                update["changes"],
            )
            if not wrote:
                frappe.throw(_("Board editor drawing archive could not be stored together."))
        return True


def drawing_storage_ready() -> bool:
    return bool(frappe.db.table_exists(DOCTYPE))


def _dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _load_object(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _row_to_record(row: Any) -> dict[str, Any]:
    def value(field: str) -> Any:
        if isinstance(row, Mapping):
            return row.get(field)
        return getattr(row, field, None)

    drawing = _load_object(value("drawing_json"))
    archive = _load_object(value("prior_drawing_archive_json"))
    if not isinstance(archive, list):
        archive = []
    return {
        "name": value("name"),
        "drawing_key": str(value("drawing_key") or ""),
        "door_cutting_order": str(value("door_cutting_order") or ""),
        "source_plan": str(value("source_plan") or ""),
        "piece_instance_id": str(value("piece_instance_id") or ""),
        "source_input_fingerprint": str(value("source_input_fingerprint") or ""),
        "source_content_revision": str(value("source_content_revision") or ""),
        "drawing_version": int(value("drawing_version") or 0),
        "document_fingerprint": str(value("document_fingerprint") or ""),
        "drawing_json": drawing if isinstance(drawing, dict) else None,
        "prior_drawing_archive_json": archive,
    }


__all__ = [
    "DOCTYPE",
    "FrappeBoardEditorDrawingStore",
    "drawing_storage_ready",
]
