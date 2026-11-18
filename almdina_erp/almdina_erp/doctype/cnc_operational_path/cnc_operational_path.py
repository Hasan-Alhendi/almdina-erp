from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    OperationalFileError,
    normalize_path_piece_instance,
)


_PATH_SCOPE_MESSAGES = {
    "missing_piece_instance_id": "Piece-bound CNC paths must keep a piece instance id.",
    "sheet_perimeter_piece_forbidden": "The sheet perimeter path must not be tied to a piece instance.",
    "sheet_perimeter_duplicate": "A sheet may keep only one connected perimeter path.",
}


class CNCOperationalPath(Document):
    def validate(self) -> None:
        try:
            self.piece_instance_id = normalize_path_piece_instance(
                path_key=str(self.path_key or ""),
                operation_key=str(self.operation_key or ""),
                piece_instance_id=self.piece_instance_id,
            )
        except OperationalFileError as exc:
            frappe.throw(
                _(_PATH_SCOPE_MESSAGES.get(exc.code, exc.code)),
                frappe.ValidationError,
            )


__all__ = ["CNCOperationalPath"]
