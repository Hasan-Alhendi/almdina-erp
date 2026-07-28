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

from .door_cutting_order import ENGINE_VERSION
from .door_cutting_order_domain import DomainDoorCuttingOrder


class CostingDoorCuttingOrder(DomainDoorCuttingOrder):
    """Active controller delegating measurement and quote calculations to Domain."""

    def _calculate_piece_rows(self) -> None:
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
                    edge_type=str(row.edge_type or ""),
                )
                for row in (self.pieces or [])
            ),
            default_edge_type=str(self.default_edge_type or ""),
            edge_rates=self._get_edge_rate_map(),
        )

        for row, result in zip(self.pieces or [], summary.pieces):
            row.area_m2 = result.area_m2
            row.edge_meters = result.edge_meters
            row.edge_rate_usd = result.edge_rate_usd
            row.edge_cost_usd = result.edge_cost_usd

        self.total_area_m2 = summary.total_area_m2
        self.total_edge_meters = summary.total_edge_meters
        self.edge_cost_usd = summary.total_edge_cost_usd

    def _apply_order_costs(self, required_boards: int) -> None:
        summary = calculate_order_costs(
            required_boards=required_boards,
            board_rate_usd=flt(self.board_rate_usd),
            cutting_cost_per_board_usd=flt(self.cutting_cost_per_board_usd),
            edge_cost_usd=flt(self.edge_cost_usd),
        )
        self.required_boards = summary.required_boards
        self.mdf_cost_usd = summary.mdf_cost_usd
        self.cutting_cost_usd = summary.cutting_cost_usd
        self.total_cost_usd = summary.total_cost_usd

    def _refresh_costs_from_plan(self, settings: Any, snapshot: dict[str, Any]) -> None:
        self._apply_order_costs(len(snapshot.get("sheets") or []))
        waste = calculate_waste(
            waste_area_m2=flt(snapshot.get("waste_area_m2")),
            total_board_area_m2=flt(snapshot.get("total_board_area_m2")),
        )
        self.waste_area_m2 = waste.waste_area_m2
        self.waste_percent = waste.waste_percent
        self.packing_method = snapshot.get("method_label") or self.packing_method or ""
        self.engine_version = snapshot.get("engine_version") or ENGINE_VERSION
        self._calculate_special_shape_pricing(settings)

    def _refresh_costs_from_stored_summary(self, settings: Any) -> None:
        self._apply_order_costs(cint(self.required_boards))
        self.engine_version = self.engine_version or ENGINE_VERSION
        self._calculate_special_shape_pricing(settings)

    def _calculate_cutting_plan(self, settings: Any, input_fingerprint: str) -> None:
        # The optimizer remains in the compatibility base for this stage. Reapply
        # all resulting totals through the pure costing policy before persistence.
        super()._calculate_cutting_plan(settings, input_fingerprint)
        self._refresh_costs_from_plan(settings, self._parse_plan_snapshot())

    def _calculate_special_shape_pricing(self, settings: Any) -> None:
        pricing_settings = SpecialPricingSettings(
            design_fee_usd=self._finite(
                settings.default_special_design_fee_usd or 0,
                _("Default Special Design Fee USD / Piece"),
            ),
            cnc_fee_usd=self._finite(
                settings.default_special_cnc_fee_usd or 0,
                _("Default Special CNC Fee USD / Piece"),
            ),
            manual_edge_fee_usd=self._finite(
                settings.default_special_manual_edge_fee_usd or 0,
                _("Default Manual Edge Fee USD / Piece"),
            ),
            margin_percent=self._finite(
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
                        price_status=str(row.special_shape_price_status or ""),
                        approved_by=str(row.special_shape_price_approved_by or ""),
                        custom_unit_price_usd=flt(
                            row.special_shape_custom_unit_price_usd
                        ),
                    )
                    for row in (self.pieces or [])
                ),
                settings=pricing_settings,
                total_area_m2=flt(self.total_area_m2),
                board_and_cutting_cost_usd=(
                    flt(self.mdf_cost_usd) + flt(self.cutting_cost_usd)
                ),
                total_cost_usd=flt(self.total_cost_usd),
            )
        except CostingError as error:
            if str(error) == "special_shape_defaults_negative":
                frappe.throw(_("Special shape estimate defaults cannot be negative."))
            raise

        has_special = any(result.applicable for result in summary.pieces)
        for row, result in zip(self.pieces or [], summary.pieces):
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

        self.special_shapes_baseline_cost_usd = summary.baseline_cost_usd
        self.special_shapes_estimated_total_usd = summary.estimated_total_usd
        self.special_shapes_final_total_usd = summary.final_total_usd
        self.customer_quote_total_usd = summary.customer_quote_total_usd
        self.customer_quote_status = summary.customer_quote_status


__all__ = ["CostingDoorCuttingOrder"]
