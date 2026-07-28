from __future__ import annotations

from typing import Any, Iterable

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.orders.cut_dimensions import (
    CutDimensionError,
    CutDimensionInput,
    calculate_cut_dimensions,
)

from .edge_profile_repository import (
    AXIS_SIDES,
    SIDE_CONFIG,
    EdgeProfile,
    FrappeEdgeProfileRepository,
)


class FrappeOrderCutDimensionAdapter:
    """Apply per-side edge allowance to Frappe child rows."""

    def __init__(
        self,
        document: Any,
        profiles: FrappeEdgeProfileRepository,
    ) -> None:
        self.document = document
        self.profiles = profiles

    def calculate_rows(self) -> None:
        for index, row in enumerate(self.document.pieces or [], start=1):
            resolved = self.profiles.effective_profiles(row, index)
            self._clear_inactive_overrides(row)

            try:
                result = calculate_cut_dimensions(
                    CutDimensionInput(
                        final_width_cm=flt(row.width_cm),
                        final_length_cm=flt(row.length_cm),
                        edge_long_right=cint(row.edge_long_right),
                        edge_long_left=cint(row.edge_long_left),
                        edge_width_top=cint(row.edge_width_top),
                        edge_width_bottom=cint(row.edge_width_bottom),
                        edge_long_right_thickness_mm=self._thickness(
                            resolved["long_right"]
                        ),
                        edge_long_left_thickness_mm=self._thickness(
                            resolved["long_left"]
                        ),
                        edge_width_top_thickness_mm=self._thickness(
                            resolved["width_top"]
                        ),
                        edge_width_bottom_thickness_mm=self._thickness(
                            resolved["width_bottom"]
                        ),
                    )
                )
            except CutDimensionError as error:
                self._raise_validation_error(index, str(error))

            long_profiles = self._selected_profiles(resolved, "long")
            width_profiles = self._selected_profiles(resolved, "width")
            all_profiles = (*long_profiles, *width_profiles)

            row.edge_long_type = self._common_profile_name(long_profiles)
            row.edge_width_type = self._common_profile_name(width_profiles)
            row.edge_long_thickness_mm = result.long_edge_thickness_mm
            row.edge_width_thickness_mm = result.width_edge_thickness_mm
            row.cut_width_cm = result.cut_width_cm
            row.cut_length_cm = result.cut_length_cm
            row.cut_size_label = self._size_label(
                result.cut_width_cm,
                result.cut_length_cm,
            )
            row.edge_type = self._common_profile_name(all_profiles)
            row.edge_thickness_mm = self._common_profile_value(
                all_profiles,
                "thickness_mm",
            )

    @staticmethod
    def _clear_inactive_overrides(row: Any) -> None:
        for selected_field, override_field, _ in SIDE_CONFIG.values():
            if not cint(getattr(row, selected_field, 0)):
                setattr(row, override_field, "")

    @staticmethod
    def _thickness(profile: EdgeProfile | None) -> float:
        return profile.thickness_mm if profile else 0

    @staticmethod
    def _selected_profiles(
        resolved: dict[str, EdgeProfile | None],
        axis: str,
    ) -> tuple[EdgeProfile, ...]:
        return tuple(
            profile
            for side in AXIS_SIDES[axis]
            if (profile := resolved[side]) is not None
        )

    @staticmethod
    def _common_profile_name(profiles: Iterable[EdgeProfile]) -> str:
        names = {profile.name for profile in profiles}
        return names.pop() if len(names) == 1 else ""

    @staticmethod
    def _common_profile_value(
        profiles: Iterable[EdgeProfile],
        fieldname: str,
    ) -> float:
        values = {float(getattr(profile, fieldname)) for profile in profiles}
        return values.pop() if len(values) == 1 else 0

    @staticmethod
    def _size_label(width_cm: float, length_cm: float) -> str:
        return f"{_format_number(width_cm)} × {_format_number(length_cm)}"

    @staticmethod
    def _raise_validation_error(index: int, code: str) -> None:
        messages = {
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
