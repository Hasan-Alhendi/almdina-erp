from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.orders.cut_dimensions import (
    CutDimensionError,
    CutDimensionInput,
    calculate_cut_dimensions,
)

from .edge_profile_repository import FrappeEdgeProfileRepository


class FrappeOrderCutDimensionAdapter:
    """Apply per-axis edge allowance to Frappe child rows."""

    def __init__(
        self,
        document: Any,
        profiles: FrappeEdgeProfileRepository,
    ) -> None:
        self.document = document
        self.profiles = profiles

    def calculate_rows(self) -> None:
        for index, row in enumerate(self.document.pieces or [], start=1):
            long_profile = self.profiles.profile_for(row, "long", index)
            width_profile = self.profiles.profile_for(row, "width", index)

            row.edge_long_type = long_profile.name if long_profile else ""
            row.edge_width_type = width_profile.name if width_profile else ""

            try:
                result = calculate_cut_dimensions(
                    CutDimensionInput(
                        final_width_cm=flt(row.width_cm),
                        final_length_cm=flt(row.length_cm),
                        long_edge_thickness_mm=(
                            long_profile.thickness_mm if long_profile else 0
                        ),
                        width_edge_thickness_mm=(
                            width_profile.thickness_mm if width_profile else 0
                        ),
                        edge_long_right=cint(row.edge_long_right),
                        edge_long_left=cint(row.edge_long_left),
                        edge_width_top=cint(row.edge_width_top),
                        edge_width_bottom=cint(row.edge_width_bottom),
                    )
                )
            except CutDimensionError as error:
                self._raise_validation_error(index, str(error))

            row.edge_long_thickness_mm = result.long_edge_thickness_mm
            row.edge_width_thickness_mm = result.width_edge_thickness_mm
            row.cut_width_cm = result.cut_width_cm
            row.cut_length_cm = result.cut_length_cm
            row.cut_size_label = self._size_label(
                result.cut_width_cm,
                result.cut_length_cm,
            )
            self._sync_legacy_summary(row, long_profile, width_profile)

    @staticmethod
    def _sync_legacy_summary(row: Any, long_profile: Any, width_profile: Any) -> None:
        profiles = [profile for profile in (long_profile, width_profile) if profile]
        names = {profile.name for profile in profiles}
        thicknesses = {profile.thickness_mm for profile in profiles}
        row.edge_type = names.pop() if len(names) == 1 else ""
        row.edge_thickness_mm = (
            thicknesses.pop() if len(thicknesses) == 1 else 0
        )

    @staticmethod
    def _size_label(width_cm: float, length_cm: float) -> str:
        return f"{_format_number(width_cm)} × {_format_number(length_cm)}"

    @staticmethod
    def _raise_validation_error(index: int, code: str) -> None:
        messages = {
            "long_edge_thickness_negative": _(
                "Row {0}: Long edge thickness cannot be negative."
            ),
            "width_edge_thickness_negative": _(
                "Row {0}: Width edge thickness cannot be negative."
            ),
            "cut_width_not_positive": _(
                "Row {0}: Edge allowance leaves no valid cutting width."
            ),
            "cut_length_not_positive": _(
                "Row {0}: Edge allowance leaves no valid cutting length."
            ),
        }
        template = messages.get(
            code,
            _("Row {0}: Cutting dimensions could not be calculated."),
        )
        frappe.throw(template.format(index))


def _format_number(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


__all__ = ["FrappeOrderCutDimensionAdapter"]
