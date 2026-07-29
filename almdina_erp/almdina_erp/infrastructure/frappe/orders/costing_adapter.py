from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.orders.costing import (
    CostingError,
    PieceCostInput,
    SpecialPricingPieceInput,
    SpecialPricingSettings,
    calculate_order_costs,
    calculate_piece_costs,
    calculate_special_pricing,
    calculate_waste,
)

from .document_access import FrappeOrderDocumentAccess
from .edge_profile_repository import FrappeEdgeProfileRepository


class FrappeOrderCostingAdapter:
    """Apply pure costing results to one Frappe order document."""

    def __init__(
        self,
        document: Any,
        access: FrappeOrderDocumentAccess,
        profiles: FrappeEdgeProfileRepository,
        *,
        engine_version: str,
    ) -> None:
        self.document = document
        self.access = access
        self.profiles = profiles
        self.engine_version = engine_version

    def calculate_piece_rows(self) -> None:
        summary = calculate_piece_costs(
            (
                PieceCostInput(
                    width_cm=flt(row.width_cm),
                    length_cm=flt(row.length_cm),
                    qty=cint(row.qty),
                    edge_long_right=cint(row.edge_long_right),
                    edge_long_left=cint(row.edge_long_left),
                    edge_width_top=cint(row.edge_width_top),
                    edge_width_bottom=cint(row.edge_width_bottom),
                    edge_long_right_type=str(
                        row.edge_long_right_type_override or ""
                    ),
                    edge_long_left_type=str(
                        row.edge_long_left_type_override or ""
                    ),
                    edge_width_top_type=str(
                        row.edge_width_top_type_override or ""
                    ),
                    edge_width_bottom_type=str(
                        row.edge_width_bottom_type_override or ""
                    ),
                )
                for row in (self.document.pieces or [])
            ),
            default_edge_type=str(self.document.default_edge_type or ""),
            edge_rates=self.profiles.rate_map(),
        )

        for row, result in zip(self.document.pieces or [], summary.pieces):
            row.area_m2 = result.area_m2
            row.edge_long_meters = result.edge_long_meters
            row.edge_width_meters = result.edge_width_meters
            row.edge_meters = result.edge_meters
            row.edge_long_rate_usd = result.edge_long_rate_usd
            row.edge_width_rate_usd = result.edge_width_rate_usd
            row.edge_long_cost_usd = result.edge_long_cost_usd
            row.edge_width_cost_usd = result.edge_width_cost_usd
            row.edge_cost_usd = result.edge_cost_usd
            row.edge_rate_usd = self._legacy_rate(result)

        self.document.total_area_m2 = summary.total_area_m2
        self.document.total_edge_meters = summary.total_edge_meters
        self.document.edge_cost_usd = summary.total_edge_cost_usd

    @staticmethod
    def _legacy_rate(result: Any) -> float:
        rates = {
            rate
            for rate, meters in (
                (result.edge_long_rate_usd, result.edge_long_meters),
                (result.edge_width_rate_usd, result.edge_width_meters),
            )
            if meters > 0
        }
        return rates.pop() if len(rates) == 1 else 0

    def apply_order_costs(self, required_boards: int) -> None:
        summary = calculate_order_costs(
            required_boards=required_boards,
            board_rate_usd=flt(self.document.board_rate_usd),
            cutting_cost_per_board_usd=flt(
                self.document.cutting_cost_per_board_usd
            ),
            edge_cost_usd=flt(self.document.edge_cost_usd),
        )
        self.document.required_boards = summary.required_boards
        self.document.mdf_cost_usd = summary.mdf_cost_usd
        self.document.cutting_cost_usd = summary.cutting_cost_usd
        self.document.total_cost_usd = summary.total_cost_usd

    def refresh_from_plan(self, snapshot: dict[str, Any]) -> None:
        self.apply_order_costs(len(snapshot.get("sheets") or []))
        waste = calculate_waste(
            waste_area_m2=flt(snapshot.get("waste_area_m2")),
            total_board_area_m2=flt(snapshot.get("total_board_area_m2")),
        )
        self.document.waste_area_m2 = waste.waste_area_m2
        self.document.waste_percent = waste.waste_percent
        self.document.packing_method = (
            snapshot.get("method_label")
            or self.document.packing_method
            or ""
        )
        self.document.engine_version = (
            snapshot.get("engine_version") or self.engine_version
        )
        self.calculate_special_shape_pricing()

    def refresh_from_stored_summary(self) -> None:
        self.apply_order_costs(cint(self.document.required_boards))
        self.document.engine_version = (
            self.document.engine_version or self.engine_version
        )
        self.calculate_special_shape_pricing()

    def calculate_special_shape_pricing(self) -> None:
        settings = self.access.settings
        pricing_settings = SpecialPricingSettings(
            design_fee_usd=self.access.finite(
                settings.default_special_design_fee_usd or 0,
                _("Default Special Design Fee USD / Piece"),
            ),
            cnc_fee_usd=self.access.finite(
                settings.default_special_cnc_fee_usd or 0,
                _("Default Special CNC Fee USD / Piece"),
            ),
            manual_edge_fee_usd=self.access.finite(
                settings.default_special_manual_edge_fee_usd or 0,
                _("Default Manual Edge Fee USD / Piece"),
            ),
            margin_percent=self.access.finite(
                settings.default_special_margin_percent or 0,
                _("Default Special Shape Margin Percent"),
            ),
        )
        try:
            summary = calculate_special_pricing(
                (
                    SpecialPricingPieceInput(
                        piece_type=str(row.piece_type or "Regular"),
                        qty=cint(row.qty),
                        area_m2=flt(row.area_m2),
                        edge_cost_usd=flt(row.edge_cost_usd),
                        price_status=str(
                            row.special_shape_price_status or ""
                        ),
                        approved_by=str(
                            row.special_shape_price_approved_by or ""
                        ),
                        custom_unit_price_usd=flt(
                            row.special_shape_custom_unit_price_usd
                        ),
                    )
                    for row in (self.document.pieces or [])
                ),
                settings=pricing_settings,
                total_area_m2=flt(self.document.total_area_m2),
                board_and_cutting_cost_usd=(
                    flt(self.document.mdf_cost_usd)
                    + flt(self.document.cutting_cost_usd)
                ),
                total_cost_usd=flt(self.document.total_cost_usd),
            )
        except CostingError as error:
            if str(error) == "special_shape_defaults_negative":
                frappe.throw(
                    _("Special shape estimate defaults cannot be negative.")
                )
            raise

        has_special = any(result.applicable for result in summary.pieces)
        for row, result in zip(self.document.pieces or [], summary.pieces):
            if not has_special:
                row.special_shape_estimated_unit_price_usd = 0
                row.special_shape_custom_unit_price_usd = 0
                row.special_shape_final_unit_price_usd = 0
                row.special_shape_price_status = "Not Applicable"
                continue
            if not result.applicable:
                continue

            row.special_shape_estimated_unit_price_usd = (
                result.estimated_unit_price_usd
            )
            row.special_shape_final_unit_price_usd = result.final_unit_price_usd
            if not result.preserve_approval:
                row.special_shape_price_status = "Estimated"
                row.special_shape_custom_unit_price_usd = 0
                row.special_shape_price_note = ""
                row.special_shape_price_approved_by = ""
                row.special_shape_price_approved_on = None

        self.document.special_shapes_baseline_cost_usd = (
            summary.baseline_cost_usd
        )
        self.document.special_shapes_estimated_total_usd = (
            summary.estimated_total_usd
        )
        self.document.special_shapes_final_total_usd = summary.final_total_usd
        self.document.customer_quote_total_usd = (
            summary.customer_quote_total_usd
        )
        self.document.customer_quote_status = summary.customer_quote_status


__all__ = ["FrappeOrderCostingAdapter"]
