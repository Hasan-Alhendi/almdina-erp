from __future__ import annotations

from typing import Any

import pytest

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AppliedTrim,
    PlanQuality,
    resolve_adaptive_trim,
)


def test_policy_keeps_preferred_trim_when_it_is_already_feasible() -> None:
    calls: list[AppliedTrim] = []
    preferred = AppliedTrim(0.5, 0.5)

    decision = resolve_adaptive_trim(
        preferred=preferred,
        preferred_quality=PlanQuality(0, 1),
        evaluate=lambda trim: calls.append(trim) or PlanQuality(0, 1),
        has_pieces=True,
        physical_board_lower_bound=1,
    )

    assert decision.applied == preferred
    assert decision.mode == "preferred"
    assert decision.relaxed_axes == ()
    assert calls == []


def test_policy_relaxes_only_the_axis_that_improves_the_plan() -> None:
    preferred = AppliedTrim(0.5, 0.5)

    def evaluate(trim: AppliedTrim) -> PlanQuality:
        if trim.length_trim_cm <= 0:
            return PlanQuality(0, 1)
        return PlanQuality(1, 0)

    decision = resolve_adaptive_trim(
        preferred=preferred,
        preferred_quality=PlanQuality(1, 0),
        evaluate=evaluate,
        has_pieces=True,
        physical_board_lower_bound=1,
    )

    assert decision.applied == AppliedTrim(0.5, 0.0)
    assert decision.relaxed_axes == ("length",)


def test_policy_preserves_exact_largest_feasible_three_mm_trim() -> None:
    preferred = AppliedTrim(0.5, 0.5)

    def evaluate(trim: AppliedTrim) -> PlanQuality:
        return (
            PlanQuality(0, 1)
            if trim.length_trim_cm <= 0.3 + 1e-9
            else PlanQuality(1, 0)
        )

    decision = resolve_adaptive_trim(
        preferred=preferred,
        preferred_quality=PlanQuality(1, 0),
        evaluate=evaluate,
        has_pieces=True,
        physical_board_lower_bound=1,
    )

    assert decision.applied.width_trim_cm == pytest.approx(0.5)
    assert decision.applied.length_trim_cm == pytest.approx(0.3)
    assert decision.relaxed_axes == ("length",)


def test_policy_can_relax_both_axes_and_refine_each_one() -> None:
    preferred = AppliedTrim(0.5, 0.5)

    def evaluate(trim: AppliedTrim) -> PlanQuality:
        return (
            PlanQuality(0, 1)
            if trim.width_trim_cm <= 0.2 + 1e-9
            and trim.length_trim_cm <= 0.1 + 1e-9
            else PlanQuality(1, 0)
        )

    first = resolve_adaptive_trim(
        preferred=preferred,
        preferred_quality=PlanQuality(1, 0),
        evaluate=evaluate,
        has_pieces=True,
        physical_board_lower_bound=1,
    )
    second = resolve_adaptive_trim(
        preferred=preferred,
        preferred_quality=PlanQuality(1, 0),
        evaluate=evaluate,
        has_pieces=True,
        physical_board_lower_bound=1,
    )

    assert first == second
    assert first.applied.width_trim_cm == pytest.approx(0.2)
    assert first.applied.length_trim_cm == pytest.approx(0.1)
    assert first.relaxed_axes == ("width", "length")


class _GeometryEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "board_width_cm": board_width_cm,
                "board_length_cm": board_length_cm,
                "kerf_cm": kerf_cm,
                "selected_mode": kwargs["selected_mode"],
            }
        )

        max_length = max((float(piece["length_cm"]) for piece in pieces), default=0.0)
        row_width = sum(float(piece["width_cm"]) for piece in pieces)
        if len(pieces) > 1:
            row_width += kerf_cm * (len(pieces) - 1)
        fits = max_length <= board_length_cm + 1e-9 and row_width <= board_width_cm + 1e-9
        sheets = [{"sheet_no": 1, "pieces": pieces}] if fits and pieces else []
        unplaced = [] if fits else pieces
        board_area_m2 = board_width_cm * board_length_cm / 10_000 if sheets else 0.0
        used_area_m2 = (
            sum(float(piece["width_cm"]) * float(piece["length_cm"]) for piece in pieces)
            / 10_000
            if fits
            else 0.0
        )
        return {
            "method_key": "geometry-test",
            "method_label": "Geometry Test",
            "optimization_mode": kwargs["selected_mode"],
            "industrial_metrics": {},
            "used_area_m2": used_area_m2,
            "total_board_area_m2": board_area_m2,
            "waste_area_m2": max(0.0, board_area_m2 - used_area_m2),
            "sheets": sheets,
            "unplaced": unplaced,
        }

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]:
        return []


def _command(
    pieces: tuple[dict[str, Any], ...],
    *,
    trim_cm: float = 0.5,
    kerf_cm: float = 0.3,
    mode: str = "maxrects",
) -> OptimizeOrderPlanCommand:
    return OptimizeOrderPlanCommand(
        engine_version="almadina-138-test",
        input_fingerprint="trim-contract",
        board=BoardGeometry(
            full_width_cm=122,
            full_length_cm=244,
            trim_cm=trim_cm,
            kerf_cm=kerf_cm,
        ),
        optimizer=OptimizerOptions(
            selected_mode=mode,
            machine_type="Auto",
            time_limit_sec=10,
            exact_piece_limit=40,
            min_remnant_width_cm=0,
            min_remnant_length_cm=0,
            min_remnant_area_m2=0,
        ),
        piece_rows=pieces,
    )


def _piece(width: float, length: float, piece_id: int = 1) -> dict[str, Any]:
    return {
        "id": piece_id,
        "width_cm": width,
        "length_cm": length,
        "piece_type": "Regular",
    }


def test_full_length_piece_relaxes_length_only_and_never_switches_mode_or_kerf() -> None:
    engine = _GeometryEngine()
    outcome = optimize_order_plan(
        _command((_piece(30, 244),), mode="maxrects"),
        engine=engine,
    )

    policy = outcome.snapshot["trim_policy"]
    assert policy["preferred_trim_mm"] == 5
    assert policy["applied_width_trim_mm"] == 5
    assert policy["applied_length_trim_mm"] == 0
    assert policy["relaxed_axes"] == ["length"]
    assert all(call["selected_mode"] == "maxrects" for call in engine.calls)
    assert all(call["kerf_cm"] == pytest.approx(0.3) for call in engine.calls)


def test_full_width_piece_relaxes_width_only() -> None:
    outcome = optimize_order_plan(
        _command((_piece(122, 30),)),
        engine=_GeometryEngine(),
    )

    policy = outcome.snapshot["trim_policy"]
    assert policy["applied_width_trim_mm"] == 0
    assert policy["applied_length_trim_mm"] == 5
    assert policy["relaxed_axes"] == ["width"]


def test_piece_using_full_board_requires_both_axes() -> None:
    outcome = optimize_order_plan(
        _command((_piece(122, 244),)),
        engine=_GeometryEngine(),
    )

    policy = outcome.snapshot["trim_policy"]
    assert policy["applied_width_trim_mm"] == 0
    assert policy["applied_length_trim_mm"] == 0
    assert policy["relaxed_axes"] == ["width", "length"]


def test_four_full_length_30cm_pieces_fit_real_width_with_kerf_after_length_relaxation() -> None:
    pieces = tuple(_piece(30, 244, piece_id=index) for index in range(1, 5))
    engine = _GeometryEngine()

    outcome = optimize_order_plan(_command(pieces), engine=engine)

    assert outcome.required_boards == 1
    assert outcome.snapshot["validation"]["is_valid"] is True
    assert outcome.snapshot["trim_policy"]["applied_width_trim_mm"] == 5
    assert outcome.snapshot["trim_policy"]["applied_length_trim_mm"] == 0
    assert outcome.snapshot["usable_board_width_cm"] == pytest.approx(121)
    assert 4 * 30 + 3 * 0.3 <= outcome.snapshot["usable_board_width_cm"]


def test_application_preserves_three_mm_as_largest_feasible_applied_trim() -> None:
    outcome = optimize_order_plan(
        _command((_piece(30, 243.4),)),
        engine=_GeometryEngine(),
    )

    assert outcome.snapshot["trim_policy"]["applied_width_trim_mm"] == 5
    assert outcome.snapshot["trim_policy"]["applied_length_trim_mm"] == 3
    assert outcome.snapshot["margin_policy"]["top_mm"] == 3
    assert outcome.snapshot["margin_policy"]["bottom_mm"] == 3


def test_preferred_trim_stays_unchanged_when_it_already_works() -> None:
    engine = _GeometryEngine()
    outcome = optimize_order_plan(
        _command((_piece(30, 100),)),
        engine=engine,
    )

    assert outcome.snapshot["trim_policy"]["mode"] == "preferred"
    assert outcome.snapshot["trim_policy"]["relaxed_axes"] == []
    assert outcome.snapshot["trim_policy"]["applied_width_trim_mm"] == 5
    assert outcome.snapshot["trim_policy"]["applied_length_trim_mm"] == 5
    assert len(engine.calls) == 1
