from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import frappe
from frappe import _
from frappe.utils import cint, flt


EdgeAxis = Literal["long", "width"]
EdgeSide = Literal[
    "long_right",
    "long_left",
    "width_top",
    "width_bottom",
]

SIDE_CONFIG: dict[EdgeSide, tuple[str, str, str]] = {
    "long_right": (
        "edge_long_right",
        "edge_long_right_type_override",
        "Long Right",
    ),
    "long_left": (
        "edge_long_left",
        "edge_long_left_type_override",
        "Long Left",
    ),
    "width_top": (
        "edge_width_top",
        "edge_width_top_type_override",
        "Width Top",
    ),
    "width_bottom": (
        "edge_width_bottom",
        "edge_width_bottom_type_override",
        "Width Bottom",
    ),
}

AXIS_SIDES: dict[EdgeAxis, tuple[EdgeSide, EdgeSide]] = {
    "long": ("long_right", "long_left"),
    "width": ("width_top", "width_bottom"),
}


@dataclass(frozen=True, slots=True)
class EdgeProfile:
    name: str
    thickness_mm: float
    rate_usd_per_meter: float


class FrappeEdgeProfileRepository:
    """Load edge master data once and resolve one effective profile per side."""

    def __init__(self, document: Any) -> None:
        self.document = document

    def side_is_selected(self, row: Any, side: EdgeSide) -> bool:
        selected_field, _override_field, _side_label = SIDE_CONFIG[side]
        return bool(cint(getattr(row, selected_field, 0)))

    def axis_is_selected(self, row: Any, axis: EdgeAxis) -> bool:
        return any(self.side_is_selected(row, side) for side in AXIS_SIDES[axis])

    def effective_type(self, row: Any, side: EdgeSide, index: int) -> str:
        if not self.side_is_selected(row, side):
            return ""

        _selected_field, override_field, side_label = SIDE_CONFIG[side]
        edge_type = str(
            getattr(row, override_field, "")
            or self.document.default_edge_type
            or ""
        ).strip()
        if edge_type:
            return edge_type

        frappe.throw(
            _(
                "Row {0}: Select a default Edge Type before choosing the {1} edge."
            ).format(index, _(side_label))
        )
        return ""

    def profile_for_side(
        self,
        row: Any,
        side: EdgeSide,
        index: int,
    ) -> EdgeProfile | None:
        edge_type = self.effective_type(row, side, index)
        if not edge_type:
            return None
        return self.profiles()[edge_type]

    def profiles_for_axis(
        self,
        row: Any,
        axis: EdgeAxis,
        index: int,
    ) -> tuple[EdgeProfile, ...]:
        return tuple(
            profile
            for side in AXIS_SIDES[axis]
            if (profile := self.profile_for_side(row, side, index)) is not None
        )

    def effective_profiles(
        self,
        row: Any,
        index: int,
    ) -> dict[EdgeSide, EdgeProfile | None]:
        return {
            side: self.profile_for_side(row, side, index)
            for side in SIDE_CONFIG
        }

    def profiles(self) -> dict[str, EdgeProfile]:
        flags = self.document.flags
        if flags.get("_order_edge_profiles_loaded"):
            return flags.get("_order_edge_profiles") or {}

        names = self._required_names()
        if not names:
            flags._order_edge_profiles = {}
            flags._order_edge_profiles_loaded = True
            return {}

        rows = frappe.get_all(
            "Edge Banding Type",
            filters={"name": ["in", sorted(names)]},
            fields=[
                "name",
                "thickness_mm",
                "rate_usd_per_meter",
                "disabled",
            ],
        )
        found = {str(row.name): row for row in rows}
        missing = sorted(names.difference(found))
        if missing:
            frappe.throw(
                _("Edge Banding Type {0} does not exist.").format(
                    ", ".join(missing)
                )
            )

        profiles: dict[str, EdgeProfile] = {}
        for name, row in found.items():
            if cint(row.disabled):
                frappe.throw(_("Edge Banding Type {0} is disabled.").format(name))

            thickness = flt(row.thickness_mm)
            rate = flt(row.rate_usd_per_meter)
            if not math.isfinite(thickness) or thickness <= 0:
                frappe.throw(
                    _(
                        "Edge Banding Type {0} must have a thickness greater than zero."
                    ).format(name)
                )
            if not math.isfinite(rate) or rate < 0:
                frappe.throw(
                    _("Edge Banding Type {0} has an invalid rate.").format(name)
                )

            profiles[name] = EdgeProfile(
                name=name,
                thickness_mm=thickness,
                rate_usd_per_meter=rate,
            )

        flags._order_edge_profiles = profiles
        flags._order_edge_profiles_loaded = True
        return profiles

    def thickness_map(self) -> dict[str, float]:
        return {
            name: profile.thickness_mm
            for name, profile in self.profiles().items()
        }

    def rate_map(self) -> dict[str, float]:
        return {
            name: profile.rate_usd_per_meter
            for name, profile in self.profiles().items()
        }

    def _required_names(self) -> set[str]:
        names: set[str] = set()
        for index, row in enumerate(self.document.pieces or [], start=1):
            for side in SIDE_CONFIG:
                edge_type = self.effective_type(row, side, index)
                if edge_type:
                    names.add(edge_type)
        return names


__all__ = [
    "AXIS_SIDES",
    "SIDE_CONFIG",
    "EdgeAxis",
    "EdgeProfile",
    "EdgeSide",
    "FrappeEdgeProfileRepository",
]
