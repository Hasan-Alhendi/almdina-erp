"""Local, sequential cutting benchmarks from DCO evidence, with no Frappe site.

The optimizer receives DCO rows only. Designer geometry is measured separately.
Run each arm in a fresh process with the same Python environment and budget.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=120)
    parser.add_argument("--dimensions", choices=("saved", "nominal"), default="saved")
    parser.add_argument("--arm", default="baseline")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--ignore-liner", action="store_true",
                        help="Explicit layout-only experiment; disable liner in memory, never in the DCO file")
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,
        OptimizerOptions,
        OptimizeOrderPlanCommand,
        optimize_order_plan,
    )
    from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
        DomainCuttingEngineAdapter,
    )
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import (
        plan_cut_line_quality,
    )
    import almdina_erp.almdina_erp.domain.cutting.plan_portfolio as portfolio

    raw = args.input.read_bytes()
    dco = json.loads(raw)
    diagnostic = json.loads(args.diagnostic.read_bytes())["plans"][0]
    settings = diagnostic["settings"]
    trim = settings["trim_margin_mm"] / 10
    kerf = settings["kerf_mm"] / 10
    rows = []
    changes = []
    for source in dco["pieces"]:
        row = dict(
            source,
            final_width_cm=source["width_cm"],
            final_length_cm=source["length_cm"],
        )
        if args.dimensions == "saved":
            row.update(
                width_cm=source["cut_width_cm"], length_cm=source["cut_length_cm"]
            )
        row["deduct_edge_thickness"] = args.dimensions == "saved"
        if args.ignore_liner:
            row.update(extra_liner=0, liner_specs_json=None)
        rows.append(row)
        if (source["width_cm"], source["length_cm"]) != (
            source["cut_width_cm"],
            source["cut_length_cm"],
        ):
            changes.append(
                dict(
                    piece_no=source["piece_no"],
                    qty=source["qty"],
                    nominal=[source["width_cm"], source["length_cm"]],
                    saved=[source["cut_width_cm"], source["cut_length_cm"]],
                )
            )
    candidates = {}
    offers = Counter()
    projected = []
    application = importlib.import_module(
        "almdina_erp.almdina_erp.application.cutting.optimize_order_plan"
    )
    snapshot_outcome = application._snapshot_outcome

    def capture_projection(*a, **kw):
        result = snapshot_outcome(*a, **kw)
        if len(projected) < 24:
            projected.append(result.snapshot)
        return result

    application._snapshot_outcome = capture_projection
    if args.capture:
        retain = portfolio.retain_diverse_finals

        def capture(plans, *a, **kw):
            offers["retention_calls"] += 1
            for plan in plans:
                signature = geometry_signature(plan)
                if signature not in candidates and len(candidates) < 80:
                    candidates[signature] = deepcopy(plan)
            return retain(plans, *a, **kw)

        portfolio.retain_diverse_finals = capture

    class Engine(DomainCuttingEngineAdapter):
        def optimize(self, *a, **kw):
            plan = super().optimize(*a, **kw)
            self.native = deepcopy(plan)
            return plan

    engine = Engine()
    opts = OptimizerOptions(
        "smart",
        settings["machine_type"],
        args.budget,
        40,
        30,
        30,
        0.09,
        alns_search_budget_sec=10,
        pattern_search_budget_sec=10,
        corner_search_budget_sec=10,
        **({"fragmentation_regrouping": True} if args.arm == "regroup" else {}),
    )
    command = OptimizeOrderPlanCommand(
        "fragmentation-benchmark",
        "local-" + hashlib.sha256(raw).hexdigest(),
        BoardGeometry(
            dco["full_board_width_mm"] / 10,
            dco["full_board_length_mm"] / 10,
            trim,
            kerf,
        ),
        opts,
        tuple(rows),
        PlanSettings(
            "smart",
            settings["machine_type"],
            args.budget,
            kerf * 10,
            trim * 10,
            deduct_edge_thickness=args.dimensions == "saved",
        ),
        bool(dco["allow_piece_mirroring"]),
    )
    started, cpu = time.perf_counter(), time.process_time()
    outcome = optimize_order_plan(command, engine=engine)
    wall, cpu = time.perf_counter() - started, time.process_time() - cpu
    gallery = list(outcome.candidate_snapshots or (outcome.snapshot,))
    sha = subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip()
    tracked = subprocess.check_output(
        ["git", "-C", str(args.repo), "diff", "HEAD"], text=True
    )
    report = dict(
        arm=args.arm,
        case=dco["name"],
        commit=sha,
        diff_sha256=hashlib.sha256(tracked.encode()).hexdigest(),
        python=sys.version,
        platform=platform.platform(),
        budget=args.budget,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        dimensions=args.dimensions,
        ignored_addons=["liner"] if args.ignore_liner else [],
        input_size_differences=changes,
        unknown_special_sources=[
            r["piece_no"]
            for r in rows
            if r["piece_type"] == "Special" and not r.get("special_shape_geometry_json")
        ],
        wall_sec=wall,
        cpu_sec=cpu,
        winner=outcome.snapshot,
        gallery=gallery,
        sources=outcome.expanded_pieces,
        search_seeds=outcome.search_seeds,
        native=engine.native,
        completed_candidates=list(candidates.values()),
        projected_candidates=projected,
        capture=dict(offers, unique=len(candidates), cap=80),
        cutter_profiles=[plan_cut_line_quality(p, kerf) for p in gallery],
    )
    files = sorted(
        {
            *args.repo.glob("almdina_erp/almdina_erp/domain/cutting/**/*.py"),
            *args.repo.glob("almdina_erp/almdina_erp/application/cutting/*.py"),
            *args.repo.glob("almdina_erp/almdina_erp/infrastructure/cutting/*.py"),
            *args.repo.glob("scripts/*fragmentation*.py"),
            args.repo / "pyproject.toml",
        }
    )
    report["source_sha256"] = {
        str(p.relative_to(args.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                case=dco["name"],
                arm=args.arm,
                wall=round(wall, 3),
                boards=outcome.required_boards,
                valid=outcome.snapshot["validation"],
                gallery=len(gallery),
                captured=len(candidates),
            ),
            ensure_ascii=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
