from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.domain.cutting import (
    expand_piece_groups,
    optimize_plan,
    validate_plan,
)
from almdina_erp.almdina_erp.domain.cutting.catalog import require_engine_mode


class DomainCuttingEngineAdapter:
    """Adapt the pure cutting Domain to the Application cutting engine port."""

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return expand_piece_groups(rows)

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        *,
        selected_mode: str,
        machine_type: str,
        time_limit_sec: float,
        exact_piece_limit: int,
        min_remnant_width_cm: float,
        min_remnant_length_cm: float,
        min_remnant_area_m2: float,
    ) -> dict[str, Any]:
        plan = optimize_plan(
            pieces,
            board_width_cm,
            board_length_cm,
            kerf_cm,
            selected_mode=require_engine_mode(selected_mode),
            machine_type=machine_type,
            time_limit_sec=time_limit_sec,
            exact_piece_limit=exact_piece_limit,
            min_remnant_width_cm=min_remnant_width_cm,
            min_remnant_length_cm=min_remnant_length_cm,
            min_remnant_area_m2=min_remnant_area_m2,
        )
        plan["kerf_cm"] = max(0.0, float(kerf_cm or 0))
        return plan

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]:
        return validate_plan(
            plan,
            pieces,
            board_width_cm,
            board_length_cm,
            kerf_cm=max(0.0, float(plan.get("kerf_cm") or 0)),
        )


domain_cutting_engine = DomainCuttingEngineAdapter()


__all__ = ["DomainCuttingEngineAdapter", "domain_cutting_engine"]
