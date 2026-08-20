from __future__ import annotations

from typing import Any

from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.orders.plan_payloads import (
    PlanMetadataPiece,
    build_plan_metadata_payload,
)
from .plan_adapter import FrappeOrderPlanAdapter


class FrappeCutDimensionPlanAdapter(FrappeOrderPlanAdapter):
    """Feed raw cutting sizes and per-side edge metadata to the plan."""

    @staticmethod
    def piece_row_as_dict(row: Any) -> dict[str, Any]:
        data = FrappeOrderPlanAdapter.piece_row_as_dict(row)
        data["final_width_cm"] = flt(row.width_cm)
        data["final_length_cm"] = flt(row.length_cm)
        data["width_cm"] = flt(getattr(row, "cut_width_cm", 0)) or flt(
            row.width_cm
        )
        data["length_cm"] = flt(getattr(row, "cut_length_cm", 0)) or flt(
            row.length_cm
        )
        for fieldname in (
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
        ):
            data[fieldname] = str(getattr(row, fieldname, "") or "")
        data["edge_long_type"] = str(row.edge_long_type or "")
        data["edge_width_type"] = str(row.edge_width_type or "")
        data["edge_long_thickness_mm"] = flt(row.edge_long_thickness_mm)
        data["edge_width_thickness_mm"] = flt(row.edge_width_thickness_mm)
        data["edge_long_rate_usd"] = flt(row.edge_long_rate_usd)
        data["edge_width_rate_usd"] = flt(row.edge_width_rate_usd)
        data["edge_long_cost_usd"] = flt(row.edge_long_cost_usd)
        data["edge_width_cost_usd"] = flt(row.edge_width_cost_usd)
        data["cut_size_label"] = str(
            getattr(row, "cut_size_label", "") or ""
        )
        return data

    def _plan_input_payload(
        self,
        source: Any | None = None,
    ) -> dict[str, Any]:
        payload = super()._plan_input_payload(source)
        source_document = source or self.document
        payload["version"] = 4
        payload["edge_allowance_policy"] = "per_side_edge_profile"

        for item, row in zip(
            payload.get("pieces") or [],
            source_document.pieces or [],
        ):
            item["width_cm"] = self.access.normalized_number(
                getattr(row, "cut_width_cm", 0) or row.width_cm
            )
            item["length_cm"] = self.access.normalized_number(
                getattr(row, "cut_length_cm", 0) or row.length_cm
            )

        return payload

    def _effective_side_type(
        self,
        row: Any,
        selected_field: str,
        override_field: str,
    ) -> str:
        if not cint(getattr(row, selected_field, 0)):
            return ""
        return str(
            getattr(row, override_field, "")
            or self.document.default_edge_type
            or ""
        )

    def _plan_metadata_payload(self) -> dict[str, Any]:
        return build_plan_metadata_payload(
            default_edge_type=str(self.document.default_edge_type or ""),
            edge_color=str(self.document.edge_color or ""),
            pieces=(
                PlanMetadataPiece(
                    index=index,
                    piece_type=str(row.piece_type or "Regular"),
                    edge_long_right=cint(row.edge_long_right),
                    edge_long_left=cint(row.edge_long_left),
                    edge_width_top=cint(row.edge_width_top),
                    edge_width_bottom=cint(row.edge_width_bottom),
                    edge_type=str(row.edge_type or ""),
                    edge_rate_usd=self.access.normalized_number(
                        row.edge_rate_usd
                    ),
                    edge_cost_usd=self.access.normalized_number(
                        row.edge_cost_usd
                    ),
                    area_m2=self.access.normalized_number(row.area_m2),
                    notes=str(row.notes or ""),
                    edge_long_type=str(row.edge_long_type or ""),
                    edge_width_type=str(row.edge_width_type or ""),
                    edge_long_rate_usd=self.access.normalized_number(
                        row.edge_long_rate_usd
                    ),
                    edge_width_rate_usd=self.access.normalized_number(
                        row.edge_width_rate_usd
                    ),
                    edge_long_cost_usd=self.access.normalized_number(
                        row.edge_long_cost_usd
                    ),
                    edge_width_cost_usd=self.access.normalized_number(
                        row.edge_width_cost_usd
                    ),
                    edge_long_right_type=self._effective_side_type(
                        row,
                        "edge_long_right",
                        "edge_long_right_type_override",
                    ),
                    edge_long_left_type=self._effective_side_type(
                        row,
                        "edge_long_left",
                        "edge_long_left_type_override",
                    ),
                    edge_width_top_type=self._effective_side_type(
                        row,
                        "edge_width_top",
                        "edge_width_top_type_override",
                    ),
                    edge_width_bottom_type=self._effective_side_type(
                        row,
                        "edge_width_bottom",
                        "edge_width_bottom_type_override",
                    ),
                )
                for index, row in enumerate(
                    self.document.pieces or [],
                    start=1,
                )
            ),
        )


__all__ = ["FrappeCutDimensionPlanAdapter"]
