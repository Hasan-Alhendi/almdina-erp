"""Paired source-only regression corpus from existing project fixtures."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=1)
    parser.add_argument("--regroup", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    from almdina_erp.tests.cutting_243_cases import source_case
    from almdina_erp.tests.geometry_nesting_cases import (
        CASES as shapes,
        source_rows as shape_rows,
    )
    from almdina_erp.tests.joint_nesting_cases import (
        CASES as joints,
        source_rows as joint_rows,
    )
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,
        OptimizerOptions,
        OptimizeOrderPlanCommand,
        optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
        DomainCuttingEngineAdapter,
    )
    from almdina_erp.almdina_erp.domain.cutting.evaluation import (
        validate_plan,
        placement_permission_errors,
    )
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    import time

    corpus = []
    case = source_case()
    for trim in (0, 0.3):
        corpus.append(
            (f"project-243-trim-{trim}", 122, 244, trim, deepcopy(case["rows"]))
        )
    for name in ("P5-L-different", "P5-clip-different", "P5-realistic-mixed"):
        width, height, trim, _ = shapes[name]
        corpus.append((name, width, height, trim, shape_rows(name)))
    for name in ("P4-clipped", "P4-mixed", "P4-regular"):
        width, height, trim, _ = joints[name]
        corpus.append((name, width, height, trim, joint_rows(name)))
    output = []
    for name, width, height, trim, rows in corpus:
        for i, row in enumerate(rows, 1):
            row["piece_instance_id"] = row.get("piece_instance_id") or f"corpus:{i}"
        started = time.perf_counter()
        options = dict(
            alns_search_budget_sec=10,
            pattern_search_budget_sec=10,
            corner_search_budget_sec=10,
        )
        if args.regroup:
            options["fragmentation_regrouping"] = True
        command = OptimizeOrderPlanCommand(
            "corpus",
            "corpus",
            BoardGeometry(width, height, trim, 0.5),
            OptimizerOptions("smart", "Auto", args.budget, 40, 30, 30, 0.09, **options),
            tuple(rows),
            allow_piece_mirroring=True,
        )
        result = optimize_order_plan(command, engine=DomainCuttingEngineAdapter())
        checks = []
        for plan in result.candidate_snapshots or (result.snapshot,):
            errors = validate_plan(
                plan,
                list(result.expanded_pieces),
                width - 2 * trim,
                height - 2 * trim,
                kerf_cm=0.5,
            )
            errors += placement_permission_errors(
                plan, list(result.expanded_pieces), mirroring_allowed=True
            )
            checks.append(
                dict(
                    valid=not errors and plan["validation"]["is_valid"],
                    boards=len(plan["sheets"]),
                    signature=geometry_signature(plan),
                )
            )
        output.append(
            dict(
                case=name,
                wall_sec=time.perf_counter() - started,
                boards=result.required_boards,
                unplaced=len(result.snapshot["unplaced"]),
                rank=result.snapshot["industrial_rank"],
                gallery=checks,
            )
        )
        print(name, result.required_boards, flush=True)
    args.output.write_text(
        json.dumps(
            dict(
                commit=subprocess.check_output(
                    ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
                ).strip(),
                regroup=args.regroup,
                budget=args.budget,
                cases=output,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
