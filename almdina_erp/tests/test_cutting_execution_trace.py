from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.cutting.execution_trace import (
    CUTTING_EXECUTION_TRACE_VERSION,
    CuttingExecutionTrace,
    build_cutting_execution_trace,
)
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
    CuttingPlanPreviewSession,
)
from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AdaptiveTrimDecision,
    AppliedTrim,
    PlanQuality,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import normalize_plan_settings


class TraceEngine:
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
                **kwargs,
            }
        )
        return {
            "optimization_mode": "Auto Pro",
            "method_key": "MaxRects-BSSF",
            "method_label": "MaxRects Best Short Side",
            "ordering_strategy": "area_desc",
            "attempts": 23,
            "search_elapsed_sec": 1.25,
            "search_time_limit_sec": kwargs["time_limit_sec"],
            "solver_status": "HEURISTIC",
            "solver_wall_time_sec": 0.0,
            "industrial_metrics": {},
            "industrial_rank": [],
            "used_area_m2": 0.3,
            "total_board_area_m2": 2.9,
            "waste_area_m2": 2.6,
            "sheets": [{"sheet_no": 1, "pieces": [dict(pieces[0])]}],
            "unplaced": [],
        }

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]:
        return []


class TestCuttingExecutionTrace(unittest.TestCase):
    def test_contract_is_immutable_versioned_and_serializes_stably(self) -> None:
        settings = normalize_plan_settings(
            optimization_mode="auto_pro",
            machine_type="Panel Saw",
            optimization_time_limit_sec=17,
            kerf_mm=0,
            preferred_trim_mm=5,
        )
        decision = AdaptiveTrimDecision(
            preferred=AppliedTrim(0.5, 0.5),
            applied=AppliedTrim(0.5, 0.3),
            preferred_quality=PlanQuality(0, 2),
            applied_quality=PlanQuality(0, 1),
        )
        trace = build_cutting_execution_trace(
            plan_settings=settings,
            trim_decision=decision,
            optimizer_outcome={
                "optimization_mode": "Auto Pro",
                "method_key": "MaxRects-BSSF",
                "method_label": "MaxRects Best Short Side",
                "ordering_strategy": "area_desc",
                "attempts": 23,
                "search_elapsed_sec": 1.25,
                "search_time_limit_sec": 17,
                "solver_status": "HEURISTIC",
                "solver_wall_time_sec": 0.0,
            },
            engine_version="trace-test",
        )

        self.assertIsInstance(trace, CuttingExecutionTrace)
        self.assertEqual(trace.version, CUTTING_EXECUTION_TRACE_VERSION)
        with self.assertRaises(FrozenInstanceError):
            trace.requested_kerf_mm = 3  # type: ignore[misc]

        snapshot = trace.to_snapshot()
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["requested"]["optimization_mode"], "auto_pro")
        self.assertEqual(snapshot["requested"]["machine_type"], "Panel Saw")
        self.assertEqual(snapshot["requested"]["kerf_mm"], 0)
        self.assertEqual(snapshot["requested"]["preferred_trim_mm"], 5)
        self.assertEqual(snapshot["requested"]["optimization_time_limit_sec"], 17)
        self.assertTrue(snapshot["adaptive_trim"]["applied"])
        self.assertEqual(snapshot["adaptive_trim"]["reason"], "avoided_extra_board")
        self.assertEqual(snapshot["adaptive_trim"]["applied_width_trim_mm"], 5)
        self.assertEqual(snapshot["adaptive_trim"]["applied_length_trim_mm"], 3)
        self.assertEqual(snapshot["adaptive_trim"]["relaxed_axes"], ["length"])
        self.assertEqual(snapshot["optimizer"]["selected_mode"], "auto_pro")
        self.assertEqual(snapshot["optimizer"]["machine_type"], "Panel Saw")
        self.assertEqual(snapshot["optimizer"]["kerf_mm"], 0)
        self.assertEqual(snapshot["optimizer"]["time_limit_sec"], 17)
        self.assertEqual(snapshot["optimizer"]["actual_optimization_mode"], "Auto Pro")
        self.assertEqual(snapshot["optimizer"]["method_key"], "MaxRects-BSSF")
        self.assertEqual(snapshot["optimizer"]["attempts"], 23)
        self.assertEqual(snapshot["optimizer"]["elapsed_sec"], 1.25)
        self.assertEqual(snapshot["optimizer"]["solver_status"], "HEURISTIC")

    def test_optimizer_receives_exact_settings_and_snapshot_keeps_legacy_fields(self) -> None:
        settings = normalize_plan_settings(
            optimization_mode="auto_pro",
            machine_type="Panel Saw",
            optimization_time_limit_sec=17,
            kerf_mm=0,
            preferred_trim_mm=5,
        )
        engine = TraceEngine()
        outcome = optimize_order_plan(
            OptimizeOrderPlanCommand(
                engine_version="trace-test",
                input_fingerprint="trace-fingerprint",
                board=BoardGeometry(
                    full_width_cm=122,
                    full_length_cm=244,
                    trim_cm=0.5,
                    kerf_cm=0,
                ),
                optimizer=OptimizerOptions(
                    selected_mode=settings.optimization_mode,
                    machine_type=settings.machine_type,
                    time_limit_sec=settings.optimization_time_limit_sec,
                    exact_piece_limit=40,
                    min_remnant_width_cm=0,
                    min_remnant_length_cm=0,
                    min_remnant_area_m2=0,
                ),
                piece_rows=(
                    {
                        "id": 1,
                        "width_cm": 30,
                        "length_cm": 100,
                        "piece_type": "Regular",
                    },
                ),
                plan_settings=settings,
            ),
            engine=engine,
        )

        self.assertEqual(len(engine.calls), 1)
        call = engine.calls[0]
        self.assertEqual(call["selected_mode"], "auto_pro")
        self.assertEqual(call["machine_type"], "Panel Saw")
        self.assertEqual(call["kerf_cm"], 0)
        self.assertEqual(call["time_limit_sec"], 17)
        self.assertEqual(call["board_width_cm"], 121)
        self.assertEqual(call["board_length_cm"], 243)

        snapshot = outcome.snapshot
        trace = snapshot["execution_trace"]
        self.assertEqual(trace["requested"]["optimization_mode"], "auto_pro")
        self.assertEqual(trace["requested"]["kerf_mm"], 0)
        self.assertEqual(trace["requested"]["preferred_trim_mm"], 5)
        self.assertEqual(trace["requested"]["optimization_time_limit_sec"], 17)
        self.assertEqual(trace["optimizer"]["selected_mode"], "auto_pro")
        self.assertEqual(trace["optimizer"]["kerf_mm"], 0)
        self.assertEqual(trace["optimizer"]["time_limit_sec"], 17)
        self.assertEqual(trace["optimizer"]["actual_optimization_mode"], "Auto Pro")
        self.assertEqual(trace["optimizer"]["method_label"], "MaxRects Best Short Side")
        self.assertEqual(trace["adaptive_trim"]["reason"], "preferred_retained")

        # Backward-compatible optimization fields remain first-class snapshot keys.
        self.assertEqual(snapshot["optimization_mode"], "Auto Pro")
        self.assertEqual(snapshot["method_key"], "MaxRects-BSSF")
        self.assertEqual(snapshot["method_label"], "MaxRects Best Short Side")
        self.assertEqual(snapshot["attempts"], 23)
        self.assertEqual(snapshot["kerf_cm"], 0)
        self.assertIn("trim_policy", snapshot)
        self.assertIn("margin_policy", snapshot)
        self.assertIn("applied_trim_width_cm", snapshot)
        self.assertIn("applied_trim_length_cm", snapshot)

    def test_adaptive_trim_reason_distinguishes_feasibility_and_board_reduction(self) -> None:
        feasibility = AdaptiveTrimDecision(
            preferred=AppliedTrim(0.5, 0.5),
            applied=AppliedTrim(0.5, 0.0),
            preferred_quality=PlanQuality(1, 0),
            applied_quality=PlanQuality(0, 1),
        )
        boards = AdaptiveTrimDecision(
            preferred=AppliedTrim(0.5, 0.5),
            applied=AppliedTrim(0.5, 0.3),
            preferred_quality=PlanQuality(0, 2),
            applied_quality=PlanQuality(0, 1),
        )
        retained = AdaptiveTrimDecision(
            preferred=AppliedTrim(0.5, 0.5),
            applied=AppliedTrim(0.5, 0.5),
            preferred_quality=PlanQuality(0, 1),
            applied_quality=PlanQuality(0, 1),
        )
        self.assertEqual(feasibility.reason, "improved_feasibility")
        self.assertEqual(boards.reason, "avoided_extra_board")
        self.assertEqual(retained.reason, "preferred_retained")

    def test_preview_session_freezes_exact_trace_inside_exact_snapshot(self) -> None:
        trace = {
            "version": 1,
            "requested": {"optimization_mode": "auto_pro"},
            "adaptive_trim": {"applied": False, "reason": "preferred_retained"},
            "optimizer": {"method_key": "MaxRects-BSSF"},
        }
        session = CuttingPlanPreviewSession(
            preview_id="preview-1",
            order_name="DCO-1",
            user="planner@example.com",
            source_plan_name="PLAN-1",
            source_plan_modified="2026-08-30 01:00:00",
            input_fingerprint="input",
            settings_fingerprint="settings",
            settings={"packing_mode": "auto_pro"},
            snapshot={"execution_trace": trace, "sheets": [{"sheet_no": 1}]},
            created_at="2026-08-30 01:00:01",
        )
        restored = CuttingPlanPreviewSession.from_cache_value(session.as_cache_value())
        self.assertEqual(
            restored.snapshot["execution_trace"],
            session.snapshot["execution_trace"],
        )

    def test_exact_preview_commit_projects_trusted_snapshot_without_optimizer_rerun(self) -> None:
        root = Path(__file__).resolve().parents[1]
        commit_source = (
            root
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "cutting_plan_preview_commit.py"
        ).read_text(encoding="utf-8")
        preview_source = (
            root
            / "almdina_erp"
            / "services"
            / "cutting_plan_preview_service.py"
        ).read_text(encoding="utf-8")
        presenter_source = (
            root
            / "public"
            / "js"
            / "door_cutting_order"
            / "cutting_plan"
            / "door_cutting_order_plan_preview_presenter.js"
        ).read_text(encoding="utf-8")

        self.assertIn("snapshot=session.snapshot", preview_source)
        self.assertIn("trusted_snapshot = dict(snapshot)", commit_source)
        self.assertIn("snapshot=trusted_snapshot", commit_source)
        self.assertNotIn("optimize_order_plan(", commit_source)
        self.assertNotIn("calculate_system_plan(", commit_source)
        self.assertIn("plan.execution_trace", presenter_source)
        self.assertIn("adaptive.applied", presenter_source)
        self.assertIn("TRIM_REASON_LABELS", presenter_source)


if __name__ == "__main__":
    unittest.main()
