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
from almdina_erp.almdina_erp.application.cutting.version import ENGINE_VERSION
from almdina_erp.almdina_erp.application.orders.plan_payloads import (
    PlanBoardInput,
    PlanCutInput,
    PlanMetadataPiece,
    PlanOptimizerSettings,
    PlanPieceInput,
    build_plan_input_payload,
    build_plan_metadata_payload,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import drawing_token
from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import (
    fingerprint_payload,
)
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
    domain_cutting_engine,
)

from .costing_adapter import FrappeOrderCostingAdapter
from .document_access import FrappeOrderDocumentAccess


class FrappeOrderPlanAdapter:
    """Adapt one Frappe order to cutting-plan Application use cases."""

    def __init__(
        self,
        document: Any,
        access: FrappeOrderDocumentAccess,
        costing: FrappeOrderCostingAdapter,
    ) -> None:
        self.document = document
        self.access = access
        self.costing = costing

    @staticmethod
    def piece_row_as_dict(row: Any) -> dict[str, Any]:
        return {
            "width_cm": flt(row.width_cm),
            "length_cm": flt(row.length_cm),
            "qty": cint(row.qty),
            "allow_rotation": cint(row.allow_rotation),
            "edge_long_right": cint(row.edge_long_right),
            "edge_long_left": cint(row.edge_long_left),
            "edge_width_top": cint(row.edge_width_top),
            "edge_width_bottom": cint(row.edge_width_bottom),
            "edge_type": row.edge_type or "",
            "edge_rate_usd": flt(row.edge_rate_usd),
            "edge_cost_usd": flt(row.edge_cost_usd),
            "piece_type": row.piece_type or "Regular",
            "clipped_corner_position": row.clipped_corner_position or "",
            "clipped_corner_width_cm": flt(row.clipped_corner_width_cm),
            "clipped_corner_length_cm": flt(row.clipped_corner_length_cm),
            "special_shape_geometry_json": (
                getattr(row, "special_shape_geometry_json", "") or ""
            ),
            "notes": row.notes or "",
        }

    def _plan_input_payload(
        self,
        source: Any | None = None,
    ) -> dict[str, Any]:
        source = source or self.document
        settings = self.access.settings
        description = str(
            getattr(source, "board_description", "") or ""
        ).strip()
        return build_plan_input_payload(
            version=1,
            board=PlanBoardInput(
                item=description,
                width_mm=self.access.normalized_number(
                    source.full_board_width_mm
                ),
                length_mm=self.access.normalized_number(
                    source.full_board_length_mm
                ),
            ),
            cut=PlanCutInput(
                kerf_mm=self.access.normalized_number(source.kerf_mm),
                trim_margin_mm=self.access.normalized_number(
                    source.trim_margin_mm
                ),
                packing_mode=str(source.packing_mode or "Auto Pro"),
                machine_type=str(source.cutting_machine_type or "Auto"),
                time_limit_sec=self.access.normalized_number(
                    source.optimization_time_limit_sec or 10
                ),
            ),
            optimizer=PlanOptimizerSettings(
                exact_piece_limit=(
                    cint(settings.optimal_search_piece_limit) or 40
                ),
                min_remnant_width_mm=self.access.normalized_number(
                    settings.min_remnant_width_mm
                ),
                min_remnant_length_mm=self.access.normalized_number(
                    settings.min_remnant_length_mm
                ),
                min_remnant_area_m2=self.access.normalized_number(
                    settings.min_remnant_area_m2
                ),
            ),
            pieces=(
                PlanPieceInput(
                    index=index,
                    width_cm=self.access.normalized_number(row.width_cm),
                    length_cm=self.access.normalized_number(row.length_cm),
                    qty=cint(row.qty),
                    allow_rotation=cint(row.allow_rotation),
                    piece_type=str(row.piece_type or "Regular"),
                    clipped_corner_position=str(
                        row.clipped_corner_position or ""
                    ),
                    clipped_corner_width_cm=self.access.normalized_number(
                        row.clipped_corner_width_cm
                    ),
                    clipped_corner_length_cm=self.access.normalized_number(
                        row.clipped_corner_length_cm
                    ),
                )
                for index, row in enumerate(source.pieces or [], start=1)
            ),
        ) | {
            "board": {
                **build_plan_input_payload(
                    version=1,
                    board=PlanBoardInput(
                        item=description,
                        width_mm=self.access.normalized_number(
                            source.full_board_width_mm
                        ),
                        length_mm=self.access.normalized_number(
                            source.full_board_length_mm
                        ),
                    ),
                    cut=PlanCutInput(
                        kerf_mm=0,
                        trim_margin_mm=0,
                        packing_mode="",
                        machine_type="",
                        time_limit_sec=0,
                    ),
                    optimizer=PlanOptimizerSettings(
                        exact_piece_limit=0,
                        min_remnant_width_mm=0,
                        min_remnant_length_mm=0,
                        min_remnant_area_m2=0,
                    ),
                    pieces=(),
                )["board"],
                "description": description,
            }
        }

    def plan_input_fingerprint(self) -> str:
        return fingerprint_payload(self._plan_input_payload())

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
                    drawing_token=drawing_token(
                        row.special_shape_drawing_json
                    ),
                    special_shape_status=str(
                        row.special_shape_status or ""
                    ),
                )
                for index, row in enumerate(
                    self.document.pieces or [],
                    start=1,
                )
            ),
        )

    def _metadata_fingerprint(self) -> str:
        return fingerprint_payload(self._plan_metadata_payload())

    def can_reuse_current_plan(self, input_fingerprint: str) -> bool:
        raw_plan = str(self.document.cutting_plan_json or "")
        stored_hash = str(self.document.calculated_plan_input_hash or "")
        if raw_plan and stored_hash:
            return decide_plan_reuse(
                PlanReuseContext(
                    has_plan_json=True,
                    has_snapshot_sheets=False,
                    requested_input_fingerprint=input_fingerprint,
                    stored_input_fingerprint=stored_hash,
                )
            ).reuse

        snapshot = self.access.parse_plan_snapshot()
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

        old_document = self.access.old_document()
        has_legacy_plan = bool(
            old_document and old_document.cutting_plan_json
        )
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

        legacy_fingerprint = fingerprint_payload(
            self._plan_input_payload(old_document)
        )
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

    def refresh_current_plan(self, input_fingerprint: str) -> None:
        metadata_fingerprint = self._metadata_fingerprint()
        if (
            self.document.cutting_plan_json
            and self.document.calculated_plan_metadata_hash
            and str(self.document.calculated_plan_metadata_hash)
            == metadata_fingerprint
        ):
            self.document.calculated_plan_input_hash = input_fingerprint
            self.document.plan_needs_recalculation = 0
            self.costing.refresh_from_stored_summary()
            return

        expanded = domain_cutting_engine.expand_pieces(
            [
                self.piece_row_as_dict(row)
                for row in (self.document.pieces or [])
            ]
        )
        snapshot = refresh_plan_metadata(
            self.access.parse_plan_snapshot(),
            expanded_pieces=expanded,
            input_fingerprint=input_fingerprint,
            metadata_fingerprint=metadata_fingerprint,
        )
        self.document.calculated_plan_input_hash = input_fingerprint
        self.document.calculated_plan_metadata_hash = metadata_fingerprint
        self.document.plan_needs_recalculation = 0
        self.access.set_plan_snapshot(snapshot)
        self.costing.refresh_from_plan(snapshot)

    def invalidate_current_plan(self) -> None:
        state = plan_invalidation_state(engine_version=ENGINE_VERSION)
        for fieldname, value in state.items():
            setattr(self.document, fieldname, value)
        self.access.clear_system_plan_if_available()
        self.costing.calculate_special_shape_pricing()

    def calculate_cutting_plan(self, input_fingerprint: str) -> None:
        settings = self.access.settings
        outcome = optimize_order_plan(
            OptimizeOrderPlanCommand(
                engine_version=ENGINE_VERSION,
                input_fingerprint=input_fingerprint,
                board=BoardGeometry(
                    full_width_cm=flt(
                        self.document.full_board_width_mm
                    )
                    / 10,
                    full_length_cm=flt(
                        self.document.full_board_length_mm
                    )
                    / 10,
                    trim_cm=flt(self.document.trim_margin_mm) / 10,
                    kerf_cm=flt(self.document.kerf_mm) / 10,
                ),
                optimizer=OptimizerOptions(
                    selected_mode=str(
                        self.document.packing_mode or "Auto Pro"
                    ),
                    machine_type=str(
                        self.document.cutting_machine_type or "Auto"
                    ),
                    time_limit_sec=(
                        flt(self.document.optimization_time_limit_sec) or 10
                    ),
                    exact_piece_limit=(
                        cint(settings.optimal_search_piece_limit) or 40
                    ),
                    min_remnant_width_cm=(
                        flt(settings.min_remnant_width_mm) / 10
                    ),
                    min_remnant_length_cm=(
                        flt(settings.min_remnant_length_mm) / 10
                    ),
                    min_remnant_area_m2=flt(
                        settings.min_remnant_area_m2
                    ),
                ),
                piece_rows=tuple(
                    self.piece_row_as_dict(row)
                    for row in (self.document.pieces or [])
                ),
            ),
            engine=domain_cutting_engine,
        )
        self.access.set_plan_snapshot(outcome.snapshot)
        self.document.calculated_plan_input_hash = input_fingerprint
        self.document.calculated_plan_metadata_hash = (
            self._metadata_fingerprint()
        )
        self.document.plan_needs_recalculation = 0
        self.document.packing_score = outcome.packing_score
        self.costing.refresh_from_plan(outcome.snapshot)


__all__ = ["FrappeOrderPlanAdapter"]
