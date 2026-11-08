from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.piece_mirroring import (
    PieceMirroringPolicyError,
    normalize_allow_piece_mirroring,
)

from .document_access import FrappeOrderDocumentAccess


class FrappeOrderBoardInputAdapter:
    """Validate and normalize customer-order board requirements only.

    Kerf, trim margin, usable board geometry, optimizer settings, and rates are
    Cutting Plan concerns and intentionally do not participate in DCO save.
    """

    def __init__(self, document: Any, access: FrappeOrderDocumentAccess) -> None:
        self.document = document
        self.access = access

    def load_snapshot(self) -> None:
        description = str(getattr(self.document, "board_description", "") or "").strip()
        if not description:
            frappe.throw(_("Board description is required."))

        length_cm, width_cm = self.access.board_dimensions()

        self.document.board_description = description
        self.document.board_length_cm = length_cm
        self.document.board_width_cm = width_cm
        self.document.full_board_length_mm = length_cm * 10
        self.document.full_board_width_mm = width_cm * 10
        try:
            self.document.allow_piece_mirroring = normalize_allow_piece_mirroring(
                getattr(self.document, "allow_piece_mirroring", None)
            )
        except PieceMirroringPolicyError:
            frappe.throw(_("Piece mirroring permission is invalid."))


__all__ = ["FrappeOrderBoardInputAdapter"]
