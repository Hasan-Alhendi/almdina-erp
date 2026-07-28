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


_EDGE_SIDE_FIELDS = (
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
)


class FrappeOrderCutDimensionAdapter:
    """Apply the pure edge-allowance policy to Frappe child rows."""

    def __init__(self, document: Any) -> None:
        self.document = document

    def calculate_rows(self) -> None:
        thicknesses = self._edge_thickness_map()
        for index, row in enumerate(self.document.pieces or [], start=1):
            selected_edge = any(
                cint(getattr(row, fieldname, 0))
                for fieldname in _EDGE_SIDE_FIELDS
            )
            effective_edge_type = str(
                row.edge_type or self.document.default_edge_type or ""
            )
            thickness_mm = self._resolve_thickness(
                index=index,
                selected_edge=selected_edge,
                edge_type=effective_edge_type,
                thicknesses=thicknesses,
            )

            try:
                result = calculate_cut_dimensions(
                    CutDimensionInput(
                        final_width_cm=flt(row.width_cm),
                        final_length_cm=flt(row.length_cm),
                        edge_thickness_mm=thickness_mm,
                        edge_long_right=cint(row.edge_long_right),
                        edge_long_left=cint(row.edge_long_left),
                        edge_width_top=cint(row.edge_width_top),
                        edge_width_bottom=cint(row.edge_width_bottom),
                    )
                )
            except CutDimensionError as error:
                self._raise_validation_error(index, str(error))

            row.edge_thickness_mm = result.edge_thickness_mm
            row.cut_width_cm = result.cut_width_cm
            row.cut_length_cm = result.cut_length_cm
            row.cut_size_label = self._size_label(
                result.cut_width_cm,
                result.cut_length_cm,
            )

    @staticmethod
    def _resolve_thickness(
        *,
        index: int,
        selected_edge: bool,
        edge_type: str,
        thicknesses: dict[str, float],
    ) -> float:
        if not selected_edge:
            return 0.0
        if not edge_type:
            frappe.throw(
                _("Row {0}: Select an Edge Type before choosing edge sides.").format(
                    index
                )
            )
        if edge_type not in thicknesses:
            frappe.throw(
                _("Row {0}: Edge Banding Type {1} does not exist.").format(
                    index,
                    edge_type,
                )
            )

        thickness_mm = thicknesses[edge_type]
        if thickness_mm <= 0:
            frappe.throw(
                _(
                    "Row {0}: Edge Banding Type {1} must have a thickness greater than zero."
                ).format(index, edge_type)
            )
        return thickness_mm

    def _edge_thickness_map(self) -> dict[str, float]:
        names = {
            str(edge_type)
            for edge_type in [
                self.document.default_edge_type,
                *(row.edge_type for row in (self.document.pieces or [])),
            ]
            if edge_type
        }
        if not names:
            return {}

        flags = self.document.flags
        cache_key = tuple(sorted(names))
        if flags.get("_edge_thickness_names") == cache_key:
            return flags.get("_edge_thickness_map") or {}

        rows = frappe.get_all(
            "Edge Banding Type",
            filters={"name": ["in", list(cache_key)]},
            fields=["name", "thickness_mm"],
        )
        thicknesses = {
            str(row.name): flt(row.thickness_mm)
            for row in rows
        }
        flags._edge_thickness_names = cache_key
        flags._edge_thickness_map = thicknesses
        return thicknesses

    @staticmethod
    def _size_label(width_cm: float, length_cm: float) -> str:
        return f"{_format_number(width_cm)} × {_format_number(length_cm)}"

    @staticmethod
    def _raise_validation_error(index: int, code: str) -> None:
        messages = {
            "edge_thickness_negative": _(
                "Row {0}: Edge thickness cannot be negative."
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
