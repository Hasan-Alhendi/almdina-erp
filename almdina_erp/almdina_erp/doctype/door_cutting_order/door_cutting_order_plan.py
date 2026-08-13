from __future__ import annotations

from typing import Any

from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.application.cutting.plan_reuse import (
    PlanReuseContext,
    decide_plan_reuse,
    plan_invalidation_state,
)
from almdina_erp.almdina_erp.application.cutting.refresh_plan_metadata import (
    refresh_plan_metadata,
)
from almdina_erp.almdina_erp.infrastructure.cutting.legacy_engine import (
    legacy_cutting_engine,
)

from .door_cutting_order import ENGINE_VERSION
from .door_cutting_order_costing import CostingDoorCuttingOrder


class PlanDoorCuttingOrder(CostingDoorCuttingOrder):
    """Active controller adapting Frappe documents to cutting Application use cases."""

    def _can_reuse_current_plan(self, input_fingerprint: str, settings: Any) -> bool:
        raw_plan = str(self.cutting_plan_json or "")
        stored_hash = str(self.calculated_plan_input_hash or "")

        if raw_plan and stored_hash:
            return decide_plan_reuse(
                PlanReuseContext(
                    has_plan_json=True,
                    has_snapshot_sheets=False,
                    requested_input_fingerprint=input_fingerprint,
                    stored_input_fingerprint=stored_hash,
                )
            ).reuse

        snapshot = self._parse_plan_snapshot()
        snapshot_hash = str(snapshot.get("input_fingerprint") or "")
        initial = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=bool(raw_plan),
                has_snapshot_sheets=bool(snapshot.get("sheets")),
                requested_input_fingerprint=input_fingerprint,
                stored_input_fingerprint=stored_hash,
                snapshot_input_fingerprint=snapshot_hash,
            )
        )
        if initial.reuse or initial.reason not in {
            "missing_legacy_plan",
            "legacy_fingerprint_required",
        }:
            return initial.reuse

        old_doc = self._get_old_doc()
        has_legacy_plan = bool(old_doc and old_doc.cutting_plan_json)
        legacy_probe = decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=bool(raw_plan),
                has_snapshot_sheets=bool(snapshot.get("sheets")),
                requested_input_fingerprint=input_fingerprint,
                snapshot_input_fingerprint=snapshot_hash,
                has_legacy_plan=has_legacy_plan,
            )
        )
        if not legacy_probe.needs_legacy_fingerprint:
            return legacy_probe.reuse

        legacy_fingerprint = self._plan_input_fingerprint(settings, old_doc)
        return decide_plan_reuse(
            PlanReuseContext(
                has_plan_json=bool(raw_plan),
                has_snapshot_sheets=bool(snapshot.get("sheets")),
                requested_input_fingerprint=input_fingerprint,
                snapshot_input_fingerprint=snapshot_hash,
                has_legacy_plan=True,
                legacy_input_fingerprint=legacy_fingerprint,
            )
        ).reuse

    def _refresh_current_plan_without_optimization(
        self,
        settings: Any,
        input_fingerprint: str,
    ) -> None:
        metadata_fingerprint = self._plan_metadata_fingerprint()
        if (
            self.cutting_plan_json
            and self.calculated_plan_metadata_hash
            and str(self.calculated_plan_metadata_hash) == metadata_fingerprint
        ):
            self.calculated_plan_input_hash = input_fingerprint
            self.plan_needs_recalculation = 0
            self._refresh_costs_from_stored_summary(settings)
            return

        expanded = legacy_cutting_engine.expand_pieces(
            [self._piece_row_as_dict(row) for row in (self.pieces or [])]
        )
        snapshot = refresh_plan_metadata(
            self._parse_plan_snapshot(),
            expanded_pieces=expanded,
            input_fingerprint=input_fingerprint,
            metadata_fingerprint=metadata_fingerprint,
        )
        self.calculated_plan_input_hash = input_fingerprint
        self.calculated_plan_metadata_hash = metadata_fingerprint
        self.plan_needs_recalculation = 0
        self._set_cutting_plan_json(snapshot)
        self._refresh_costs_from_plan(settings, snapshot)

    def _mark_plan_for_recalculation(self, settings: Any) -> None:
        state = plan_invalidation_state(engine_version=ENGINE_VERSION)
        for fieldname, value in state.items():
            setattr(self, fieldname, value)

        from almdina_erp.almdina_erp.services.dual_plan_fields import has_dual_plan_field

        if has_dual_plan_field("system_plan_json"):
            self.system_plan_json = ""
        boards = cint(self.required_boards)
        if boards > 0:
            self._refresh_costs_from_stored_summary(settings)
            return
        self.mdf_cost_usd = 0
        self.cutting_cost_usd = 0
        self.total_cost_usd = flt(self.edge_cost_usd)
        self._calculate_special_shape_pricing(settings)

    def _calculate_cutting_plan(self, settings: Any, input_fingerprint: str) -> None:
        outcome = optimize_order_plan(
            OptimizeOrderPlanCommand(
                engine_version=ENGINE_VERSION,
                input_fingerprint=input_fingerprint,
                board=BoardGeometry(
                    full_width_cm=flt(self.full_board_width_mm) / 10,
                    full_length_cm=flt(self.full_board_length_mm) / 10,
                    trim_cm=flt(self.trim_margin_mm) / 10,
                    kerf_cm=flt(self.kerf_mm) / 10,
                ),
                optimizer=OptimizerOptions(
                    selected_mode=str(self.packing_mode or "Auto Pro"),
                    machine_type=str(self.cutting_machine_type or "Auto"),
                    time_limit_sec=flt(self.optimization_time_limit_sec) or 10,
                    exact_piece_limit=cint(settings.optimal_search_piece_limit) or 40,
                    min_remnant_width_cm=flt(settings.min_remnant_width_mm) / 10,
                    min_remnant_length_cm=flt(settings.min_remnant_length_mm) / 10,
                    min_remnant_area_m2=flt(settings.min_remnant_area_m2),
                ),
                piece_rows=tuple(
                    self._piece_row_as_dict(row) for row in (self.pieces or [])
                ),
            ),
            engine=legacy_cutting_engine,
        )

        self._set_cutting_plan_json(outcome.snapshot)
        self.calculated_plan_input_hash = input_fingerprint
        self.calculated_plan_metadata_hash = self._plan_metadata_fingerprint()
        self.plan_needs_recalculation = 0
        self.packing_score = outcome.packing_score
        self._refresh_costs_from_plan(settings, outcome.snapshot)


__all__ = ["PlanDoorCuttingOrder"]
