"""Regression: final System projection should share real cutter-center segments."""

from copy import deepcopy

import pytest

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_search import _rectangular_cleanup_geometry
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece


class TwoRowsEngine:
    """Complete, real-geometry Smart candidate; no packing is mocked away."""

    def __init__(self):
        self.original = None

    def expand_pieces(self, rows):
        return expand_piece_groups(rows)

    def optimize(self, pieces, board_width_cm, board_length_cm, kerf_cm, **kwargs):
        assert (board_width_cm, board_length_cm, kerf_cm) == (100, 100, 0.5)
        plan = {
            "method_key": "MaxRects Best Short Side",
            "method_label": "Fixture",
            "optimization_mode": "smart",
            "sheets": [{
                "sheet_no": 1, "resource_kind": "FULL_BOARD", "w": 100, "h": 100,
                "pieces": [
                    make_placed_piece(pieces[0], 15.0, 0.0, 20.0, 20.0, False),
                    make_placed_piece(pieces[1], 15.3, 20.5, 20.0, 20.0, False),
                ],
            }],
            "unplaced": [],
            "used_area_m2": 0.08,
            "total_board_area_m2": 1.0,
            "waste_area_m2": 0.92,
        }
        self.original = enrich_plan_metrics(plan, plan["method_key"], "CNC Router")
        return {**deepcopy(self.original), "smart_candidates": [deepcopy(self.original)]}

    def validate(self, plan, pieces, board_width_cm, board_length_cm):
        return validate_plan(plan, pieces, board_width_cm, board_length_cm, kerf_cm=0.5)


def test_system_snapshot_recovers_three_mm_alignment_without_repacking():
    engine = TwoRowsEngine()
    rows = ({"width_cm": 20, "length_cm": 20, "qty": 2},)
    command = OptimizeOrderPlanCommand(
        engine_version="final-alignment-fixture", input_fingerprint="unchanged",
        board=BoardGeometry(100, 100, 0, 0.5),
        optimizer=OptimizerOptions("smart", "CNC Router", 10, 40, 30, 30, 0.09),
        piece_rows=rows,
        plan_settings=PlanSettings("smart", "CNC Router", 10, 5, 0),
    )
    outcome = optimize_order_plan(command, engine=engine)
    baseline = engine.original
    assert baseline is not None
    assert baseline["industrial_metrics"]["largest_reusable_free_area_m2"] > 0
    assert not validate_plan(baseline, engine.expand_pieces(list(rows)), 100, 100, kerf_cm=0.5)
    final = outcome.snapshot
    assert final["validation"]["is_valid"]
    assert len(final["sheets"]) == 1
    positioned = {p["id"]: p for p in final["sheets"][0]["pieces"]}
    assert positioned[1]["x"] == pytest.approx(positioned[2]["x"])
    before_length = _rectangular_cleanup_geometry(baseline, [0], 0.5)[1]
    after_length = _rectangular_cleanup_geometry(final, [0], 0.5)[1]
    assert after_length < before_length - 0.01  # centimeters: measured cutter-center network
    assert final["industrial_metrics"]["largest_reusable_free_area_m2"] >= (
        baseline["industrial_metrics"]["largest_reusable_free_area_m2"]
    )
    assert {(p["id"], p.get("piece_instance_id"), p.get("rotated"))
            for p in final["sheets"][0]["pieces"]} == {
        (p["id"], p.get("piece_instance_id"), p.get("rotated"))
        for p in baseline["sheets"][0]["pieces"]
    }
    assert engine.original == baseline  # never modify raw Smart seed
