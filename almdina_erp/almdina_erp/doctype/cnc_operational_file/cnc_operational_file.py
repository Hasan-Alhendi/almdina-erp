from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    OPERATIONAL_FILE_STATUSES,
    OperationalFileError,
    validate_operational_path_rows,
)


_PATH_SCOPE_MESSAGES = {
    "missing_piece_instance_id": "Piece-bound CNC paths must keep a piece instance id.",
    "sheet_perimeter_piece_forbidden": "The sheet perimeter path must not be tied to a piece instance.",
    "sheet_perimeter_duplicate": "A sheet may keep only one connected perimeter path.",
}


class CNCOperationalFile(Document):
    def validate(self) -> None:
        if str(self.status or "") not in OPERATIONAL_FILE_STATUSES:
            frappe.throw(_("Operational file status is not valid."), frappe.ValidationError)
        order_name = str(self.door_cutting_order or "").strip()
        plan_name = str(self.cutting_plan or "").strip()
        sheet_no = int(self.sheet_no or 0)
        revision = int(self.plan_revision or 0)
        if not order_name or not plan_name or sheet_no <= 0 or revision <= 0:
            frappe.throw(_("Operational file identity is incomplete."), frappe.ValidationError)
        self.identity_key = f"{order_name}::{plan_name}::{revision}::{sheet_no}"
        self.sheet_key = f"sheet:{sheet_no}"
        existing = frappe.db.exists(
            "CNC Operational File",
            {"identity_key": self.identity_key},
        )
        if existing and existing != self.name:
            frappe.throw(
                _("An operational file already exists for this approved sheet."),
                frappe.ValidationError,
            )
        try:
            normalized = validate_operational_path_rows(
                [
                    {
                        "path_key": row.path_key,
                        "operation_key": row.operation_key,
                        "piece_instance_id": row.piece_instance_id,
                        "dxf_layer": row.dxf_layer,
                        "sequence": row.sequence,
                        "tool_preset": row.tool_preset,
                    }
                    for row in (self.paths or [])
                ]
            )
        except OperationalFileError as exc:
            frappe.throw(
                _(_PATH_SCOPE_MESSAGES.get(exc.code, exc.code)),
                frappe.ValidationError,
            )
        for row, values in zip(self.paths or [], normalized, strict=True):
            row.piece_instance_id = values["piece_instance_id"]


__all__ = ["CNCOperationalFile"]
