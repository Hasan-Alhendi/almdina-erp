from __future__ import annotations

from typing import Any

from frappe.utils import flt

from .plan_adapter import FrappeOrderPlanAdapter


class FrappeCutDimensionPlanAdapter(FrappeOrderPlanAdapter):
    """Feed raw cutting sizes to the optimizer while preserving final sizes."""

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
        data["edge_thickness_mm"] = flt(
            getattr(row, "edge_thickness_mm", 0)
        )
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
        payload["version"] = 2
        payload["edge_allowance_policy"] = "per_selected_side"

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


__all__ = ["FrappeCutDimensionPlanAdapter"]
