from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import frappe
from frappe import _
from frappe.utils import cint, flt


EdgeAxis = Literal["long", "width"]


@dataclass(frozen=True, slots=True)
class EdgeProfile:
    name: str
    thickness_mm: float
    rate_usd_per_meter: float
    edge_color: str


class FrappeEdgeProfileRepository:
    """Load and validate edge master data once per order save."""

    def __init__(self, document: Any) -> None:
        self.document = document

    def axis_is_selected(self, row: Any, axis: EdgeAxis) -> bool:
        if axis == "long":
            return bool(cint(row.edge_long_right) or cint(row.edge_long_left))
        return bool(cint(row.edge_width_top) or cint(row.edge_width_bottom))

    def effective_type(self, row: Any, axis: EdgeAxis, index: int) -> str:
        if not self.axis_is_selected(row, axis):
            return ""

        fieldname = "edge_long_type" if axis == "long" else "edge_width_type"
        edge_type = str(
            getattr(row, fieldname, "")
            or self.document.default_edge_type
            or ""
        ).strip()
        if edge_type:
            return edge_type

        axis_label = _("Long") if axis == "long" else _("Width")
        frappe.throw(
            _("Row {0}: Select a {1} Edge Type before choosing its edge sides.").format(
                index,
                axis_label,
            )
        )
        return ""

    def profile_for(self, row: Any, axis: EdgeAxis, index: int) -> EdgeProfile | None:
        edge_type = self.effective_type(row, axis, index)
        if not edge_type:
            return None
        return self.profiles()[edge_type]

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
                "edge_color",
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
                edge_color=str(row.edge_color or ""),
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
            for axis in ("long", "width"):
                edge_type = self.effective_type(row, axis, index)
                if edge_type:
                    names.add(edge_type)
        return names


__all__ = [
    "EdgeAxis",
    "EdgeProfile",
    "FrappeEdgeProfileRepository",
]
