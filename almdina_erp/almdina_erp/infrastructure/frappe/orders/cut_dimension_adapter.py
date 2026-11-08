from __future__ import annotations

from typing import Any, Iterable

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    require_cut_dimension_cm,
)
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

    def calculate_rows(self, *, deduct_edge_thickness: bool | None = None) -> None:
        deduct = (
            self._resolved_deduct_edge_thickness()
            if deduct_edge_thickness is None
            else bool(deduct_edge_thickness)
        )
        for index, row in enumerate(self.document.pieces or [], start=1):
            resolved = self.profiles.effective_profiles(row, index)
            self._clear_inactive_overrides(row)

            try:
                result = calculate_cut_dimensions(
                    self._input(row, resolved, deduct_edge_thickness=deduct)
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

    def _resolved_deduct_edge_thickness(self) -> bool:
        """Read the current manufacturing plan, then factory defaults for a first plan.

        A missing historical value stays enabled. An explicit zero stays off.
        Reading another revision never writes the order rows; only this save
        path, or an explicit settings save, does.
        """

        order = self.document
        name = str(getattr(order, "name", "") or "").strip()
        is_new = bool(getattr(order, "is_new", lambda: False)())
        if name and not is_new:
            from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
                manufacturing_plan_document,
                plan_settings,
            )

            plan = manufacturing_plan_document(name)
            if plan is not None:
                return plan_settings(plan).deduct_edge_thickness
        from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
            factory_default_plan_settings,
        )

        return factory_default_plan_settings().deduct_edge_thickness

    def expected_policy_cut_cm(self, row: Any, *, deduct_edge_thickness: bool) -> tuple[float, float]:
        index = list(self.document.pieces or []).index(row) + 1
        resolved = self.profiles.effective_profiles(row, index)
        result = calculate_cut_dimensions(
            self._input(row, resolved, deduct_edge_thickness=bool(deduct_edge_thickness))
        )
        return (
            require_cut_dimension_cm(result.cut_width_cm, fieldname="cut_width_cm"),
            require_cut_dimension_cm(result.cut_length_cm, fieldname="cut_length_cm"),
        )

    def _input(
        self,
        row: Any,
        resolved: dict[str, EdgeProfile | None],
        *,
        deduct_edge_thickness: bool,
    ) -> CutDimensionInput:
        return CutDimensionInput(
            final_width_cm=flt(row.width_cm),
            final_length_cm=flt(row.length_cm),
            edge_long_right=cint(row.edge_long_right),
            edge_long_left=cint(row.edge_long_left),
            edge_width_top=cint(row.edge_width_top),
            edge_width_bottom=cint(row.edge_width_bottom),
            edge_long_right_thickness_mm=self._thickness(resolved["long_right"]),
            edge_long_left_thickness_mm=self._thickness(resolved["long_left"]),
            edge_width_top_thickness_mm=self._thickness(resolved["width_top"]),
            edge_width_bottom_thickness_mm=self._thickness(resolved["width_bottom"]),
            deduct_edge_thickness=deduct_edge_thickness,
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


def expected_policy_cut_cm(
    order: Any,
    row: Any,
    *,
    deduct_edge_thickness: bool,
) -> tuple[float, float]:
    adapter = FrappeOrderCutDimensionAdapter(
        order,
        FrappeEdgeProfileRepository(order),
    )
    return adapter.expected_policy_cut_cm(
        row,
        deduct_edge_thickness=deduct_edge_thickness,
    )


def sync_order_cut_dimensions(order: Any, *, deduct_edge_thickness: bool) -> bool:
    """Persist derived cut sizes for one explicit policy save.

    Edge selections, types, and thicknesses stay in place. Only the geometric
    cut size and its label change. Historical approved snapshots are not
    rewritten here.
    """

    profiles = FrappeEdgeProfileRepository(order)
    adapter = FrappeOrderCutDimensionAdapter(order, profiles)
    before = [
        (
            flt(getattr(row, "cut_width_cm", 0)),
            flt(getattr(row, "cut_length_cm", 0)),
            str(getattr(row, "cut_size_label", "") or ""),
        )
        for row in (order.pieces or [])
    ]
    adapter.calculate_rows(deduct_edge_thickness=bool(deduct_edge_thickness))
    changed = False
    for row, previous in zip(order.pieces or [], before, strict=True):
        current = (
            flt(row.cut_width_cm),
            flt(row.cut_length_cm),
            str(row.cut_size_label or ""),
        )
        if current == previous:
            continue
        changed = True
        if not getattr(row, "name", None):
            continue
        frappe.db.set_value(
            "Door Cutting Order Detail",
            row.name,
            {
                "cut_width_cm": row.cut_width_cm,
                "cut_length_cm": row.cut_length_cm,
                "cut_size_label": row.cut_size_label,
            },
            update_modified=False,
        )
    if changed:
        _invalidate_plans_for_cut_size_change(order)
    return changed


def _invalidate_plans_for_cut_size_change(order: Any) -> None:
    from almdina_erp.almdina_erp.services.cutting_plan_invalidation_service import (
        apply_stale_approved_plan_cancellation,
        invalidate_stale_draft_plans,
    )

    cancelled = apply_stale_approved_plan_cancellation(order)
    if cancelled and getattr(order, "name", None):
        updates = {"approved_plan": getattr(order, "approved_plan", None)}
        if hasattr(order, "drawing_dxf_status"):
            updates["drawing_dxf_status"] = order.drawing_dxf_status
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            updates,
            update_modified=False,
        )
    invalidate_stale_draft_plans(order)


__all__ = [
    "FrappeOrderCutDimensionAdapter",
    "expected_policy_cut_cm",
    "sync_order_cut_dimensions",
]
