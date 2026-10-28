"""Run identical synthetic inputs from any checkout; no production orders are claimed.

Run this script with the checkout being measured as the working directory:
    python /path/to/benchmark_cutting_p1.py --label before --output /tmp/before.json
The hooks record stages only; they delegate every optimization to real code.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.getcwd())

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry, OptimizeOrderPlanCommand, OptimizerOptions, optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting import optimizer
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups


def regular(width, length, qty=1, rotation=0):
    return {"width_cm": width, "length_cm": length, "qty": qty, "allow_rotation": rotation}


def corner(kind, width, length, cut, qty):
    return dict(regular(width, length, qty, 1), piece_type=kind,
                clipped_corner_position="Top Right", clipped_corner_width_cm=cut,
                clipped_corner_length_cm=cut)


CASES = {
    "L-tight": (40.3, 40.3, 0, [
        corner("L-Shaped Corner", 20, 20, 8, 4), regular(10, 10),
    ]),
    "L-positive-trim": (40.3, 41, 0.1, [
        corner("L-Shaped Corner", 20, 20, 8, 4), regular(10, 10),
    ]),
    "Rectangular": (100, 100, 0, [
        regular(w, h) for w, h in ((100, 38.5), (38.5, 61), (100, 38.5),
                                  (58.5, 61), (40, 60), (60, 30))
    ]),
    "L-mixed": (122, 244, 0, [
        corner("L-Shaped Corner", 50, 60, 20, 7),
        regular(60, 90, 4), regular(25, 40, 5, 1),
    ]),
    "Glass-clipped": (100, 100, 0, [
        dict(regular(70, 70, 2), piece_type="Glass", glass_margin_mm=100),
        corner("Clipped Corner", 40, 40, 20, 4), regular(15, 20, 3, 1),
    ]),
    "Large-120": (122, 244, 0, [
        regular(50, 90, 36), regular(30, 70, 36, 1), regular(22, 40, 48, 1),
    ]),
    "Adaptive-trim": (100, 100, 0.5, [regular(100, 40, 2)]),
    "Glass-assignment-gap": (34.3, 12, 0, [
        dict(regular(22, 12), piece_type="Glass", glass_margin_mm=10),
        dict(regular(12, 12), piece_type="Glass", glass_margin_mm=10),
        regular(9, 9), regular(18, 4),
    ]),
    "L-pair-offcut": (60, 50, 0, [
        corner("L-Shaped Corner", 20, 20, 8, 4), regular(30, 20, 2, 1),
    ]),
    "Boundary-kerf": (10, 8.3, 0, [regular(10, 4, 2)]),
    "Mandatory-gap": (10, 8.29, 0, [regular(10, 4, 2)]),
}
MODES = ("Auto", "Auto Pro", "Deep Search", "Optimal Search")
BASE_FUNCTION = dict(zip(MODES, ("auto_fast", "auto_pro", "deep_search", "optimal_search")))


def summary(plan):
    return {
        "boards": len(plan.get("sheets") or []),
        "unplaced": len(plan.get("unplaced") or []),
        "offcut_m2": (plan.get("industrial_metrics") or {}).get("largest_reusable_free_area_m2"),
        "rank": plan.get("industrial_rank"), "solver_status": plan.get("solver_status"),
    }


class RecordingEngine:
    def __init__(self):
        self.probes = []

    expand_pieces = staticmethod(expand_piece_groups)

    def optimize(self, pieces, width, height, kerf, **kwargs):
        # Develop predates the explicit mirroring argument; every run disables it.
        if "mirroring_allowed" not in inspect.signature(optimizer.optimize_plan).parameters:
            kwargs.pop("mirroring_allowed", None)
        probe = {"usable_cm": [width, height], "stages": []}

        def observe(stage, original):
            def call(*args, **kw):
                started = time.perf_counter()
                result = original(*args, **kw)
                probe["stages"].append(dict(
                    stage=stage, runtime_sec=time.perf_counter() - started,
                    search_budget_sec=kw.get("time_limit_sec"), **summary(result),
                ))
                return result
            return call

        with ExitStack() as stack:
            name = BASE_FUNCTION[kwargs["selected_mode"]]
            stack.enter_context(patch.object(optimizer, name, observe("baseline", getattr(optimizer, name))))
            for module, function, stage in (
                ("glass_opening_nesting", "nest_glass_openings", "nested"),
                ("shape_aware_nesting", "apply_shape_aware_nesting", "shaped"),
                ("plan_search", "improve_plan_search", "searched"),
            ):
                qualified = optimizer.__package__ + "." + module
                if importlib.util.find_spec(qualified) is not None:
                    target = importlib.import_module(qualified)
                    stack.enter_context(patch.object(target, function, observe(stage, getattr(target, function))))
            started = time.perf_counter()
            result = optimizer.optimize_plan(pieces, width, height, kerf, **kwargs)
            probe.update(runtime_sec=time.perf_counter() - started, final=summary(result))
        result["kerf_cm"] = kerf
        self.probes.append(probe)
        return result

    def validate(self, plan, pieces, width, height):
        return validate_plan(plan, pieces, width, height, kerf_cm=plan["kerf_cm"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--time-limit", type=float, default=2)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--machine-type", choices=("CNC Router", "Panel Saw"), default="CNC Router")
    parser.add_argument("--exact-piece-limit", type=int, default=20)
    args = parser.parse_args()
    results = []
    for case, (width, length, trim, rows) in CASES.items():
        if args.case and args.case != case:
            continue
        for mode in MODES:
            if args.mode and args.mode != mode:
                continue
            if mode == "Optimal Search" and sum(row["qty"] for row in rows) > args.exact_piece_limit and not args.mode:
                continue
            engine = RecordingEngine()
            command = OptimizeOrderPlanCommand(
                engine_version="synthetic-p1-benchmark", input_fingerprint="synthetic-p1-benchmark",
                board=BoardGeometry(width, length, trim, 0.3),
                optimizer=OptimizerOptions(mode, args.machine_type, args.time_limit, args.exact_piece_limit, 30, 30, 0.09),
                piece_rows=tuple(rows),
            )
            started = time.perf_counter()
            outcome = optimize_order_plan(command, engine=engine)
            result = dict(
                label=args.label, head=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                case=case, mode=mode, machine_type=args.machine_type, full_board_cm=[width, length], preferred_trim_cm=trim,
                kerf_cm=0.3, mirroring=False, remnant=[30, 30, 0.09], time_limit_sec=args.time_limit,
                exact_piece_limit=args.exact_piece_limit,
                rows=rows, runtime_sec=time.perf_counter() - started,
                probes=engine.probes, snapshot=outcome.snapshot,
            )
            results.append(result)
            Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(json.dumps(dict(case=case, mode=mode, runtime=round(result["runtime_sec"], 3),
                                  valid=outcome.snapshot["validation"]["is_valid"],
                                  **summary(outcome.snapshot))), flush=True)


if __name__ == "__main__":
    main()
