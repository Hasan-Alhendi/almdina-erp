"""Repeatable P0 synthetic benchmark; run from the repository root.

python -m almdina_erp.tests.optimizer_p0_baseline
"""

import json
import subprocess
import time
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.version import ENGINE_VERSION
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import (
    _free_rectangles_for_sheet,
    optimize_plan,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups


def run():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "optimizer_p0_synthetic.json").read_text()
    )
    settings = fixture["engine_settings"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    cases = {}
    for name, case in fixture["cases"].items():
        pieces = expand_piece_groups(case["rows"])
        width, height = case["board_cm"]
        started = time.perf_counter()
        plan = optimize_plan(
            pieces, width, height, settings["kerf_cm"],
            selected_mode=settings["selected_mode"],
            machine_type=settings["machine_type"],
            time_limit_sec=settings["time_limit_sec"],
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        errors = validate_plan(plan, pieces, width, height, kerf_cm=settings["kerf_cm"])
        if errors:
            raise AssertionError(f"{name}: {errors}")
        rectangles = [
            (round(r["w"], 3), round(r["h"], 3))
            for sheet in plan["sheets"] for r in _free_rectangles_for_sheet(sheet)
        ]
        cases[name] = {
            "boards": len(plan["sheets"]),
            "placed": sum(len(s["pieces"]) for s in plan["sheets"]),
            "unplaced": len(plan["unplaced"]),
            "waste_m2_reported": round(plan["waste_area_m2"], 6),
            "largest_reusable_free_area_m2_reported": round(
                plan["industrial_metrics"]["largest_reusable_free_area_m2"], 6
            ),
            "largest_bbox_free_rectangle_cm": max(
                rectangles, key=lambda rect: rect[0] * rect[1], default=None
            ),
            "glass_opening_guests": sum(
                bool(p.get("glass_host_piece_id")) for s in plan["sheets"] for p in s["pieces"]
            ),
            "shape_group_pocket_guests": "not_measured_in_P0",
            "elapsed_ms": elapsed_ms,
            "method_key": plan.get("method_key"),
            "ordering_strategy": plan.get("ordering_strategy"),
            "attempts": plan.get("attempts"),
        }
    return {
        "develop_head": head,
        "engine_version": ENGINE_VERSION,
        "fixture": "synthetic",
        "settings": settings,
        "cases": cases,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
