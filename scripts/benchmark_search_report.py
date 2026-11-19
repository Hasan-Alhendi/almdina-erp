"""Reproducible real-engine trace witnesses and isolated ON/OFF measurements."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizerOptions,
    OptimizeOrderPlanCommand,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.application.cutting.version import ENGINE_VERSION
from almdina_erp.almdina_erp.application.cutting.search_report import (
    SearchReport,
    canonical_json,
    fingerprint,
)
from almdina_erp.almdina_erp.domain.cutting.search_trace import observe_search
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
    DomainCuttingEngineAdapter,
)
from almdina_erp.almdina_erp.presentation.cutting.search_report_html import (
    render_search_report,
)
from scripts.benchmark_abc import peak_rss_kib


def cases():
    corner = lambda kind: dict(
        piece_type=kind,
        width_cm=20,
        length_cm=20,
        qty=4,
        allow_rotation=1,
        clipped_corner_position="Top Right",
        clipped_corner_width_cm=8,
        clipped_corner_length_cm=8,
    )
    cases = {
        "regular": dict(
            width=100,
            height=100,
            rows=[
                dict(width_cm=w, length_cm=h, qty=1, allow_rotation=1)
                for w, h in [(40, 30), (30, 20), (50, 15), (18, 45), (25, 25)]
            ],
        ),
        "glass": dict(
            width=34.3,
            height=12,
            rows=[
                dict(
                    piece_type="Glass",
                    width_cm=22,
                    length_cm=12,
                    qty=1,
                    glass_margin_mm=10,
                ),
                dict(
                    piece_type="Glass",
                    width_cm=12,
                    length_cm=12,
                    qty=1,
                    glass_margin_mm=10,
                ),
                dict(width_cm=9, length_cm=9, qty=1),
                dict(width_cm=18, length_cm=4, qty=1),
            ],
        ),
        "L": dict(
            width=40.3,
            height=40.3,
            rows=[corner("L-Shaped Corner"), dict(width_cm=10, length_cm=10, qty=1)],
        ),
        "clipped": dict(
            width=40.3,
            height=40.3,
            rows=[corner("Clipped Corner"), dict(width_cm=8, length_cm=3, qty=1)],
        ),
    }
    source = ROOT / "docs/evidence/alns-study/input-298.json"
    if source.exists():
        cases["reference-298"] = json.loads(source.read_text(encoding="utf-8"))
    return cases


def source_provenance():
    paths = set()
    for directory in (
        "domain/cutting",
        "application/cutting",
        "infrastructure/cutting",
        "presentation/cutting",
    ):
        paths.update((ROOT / "almdina_erp/almdina_erp" / directory).glob("*.*"))
    for name in (
        "services/cutting_plan_preview_service.py",
        "services/cutting_search_report_service.py",
        "infrastructure/frappe/cutting_search_report_store.py",
        "infrastructure/frappe/cutting_plan_workspace.py",
    ):
        paths.add(ROOT / "almdina_erp/almdina_erp" / name)
    paths.update(
        (ROOT / "almdina_erp/public/js/door_cutting_order/cutting_plan").glob("*.js")
    )
    paths.update([Path(__file__), ROOT / "almdina_erp/translations/ar.csv"])
    hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
        if p.is_file() and p.suffix in {".py", ".js", ".html", ".csv"}
    }
    return dict(
        git_sha=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        source_fingerprint=fingerprint(hashes),
        source_files_sha256=hashes,
        witness_context="Isolated Application engine and preview merge; no connected Frappe site.",
    )


def command_for(case, budget):
    rows = tuple(
        dict(piece_type="Regular", allow_rotation=0) | row for row in case["rows"]
    )
    digest = fingerprint(dict(width=case["width"], height=case["height"], rows=rows))
    return OptimizeOrderPlanCommand(
        engine_version=ENGINE_VERSION,
        input_fingerprint=digest,
        board=BoardGeometry(case["width"], case["height"], 0, 0.3),
        optimizer=OptimizerOptions(
            "smart",
            "CNC Router",
            budget,
            40,
            30,
            30,
            0.09,
            alignment_search_budget_sec=0.15,
            alns_search_budget_sec=budget,
            pattern_search_budget_sec=budget,
            corner_search_budget_sec=budget,
        ),
        piece_rows=rows,
        allow_piece_mirroring=True,
    )


def worker(args):
    command = command_for(cases()[args.case], args.budget)
    digest = command.input_fingerprint
    report = (
        SearchReport(
            engine_version=ENGINE_VERSION,
            **source_provenance(),
            input_fingerprint=digest,
            settings_fingerprint=fingerprint(
                dict(budget=args.budget, kerf=0.3, trim=0)
            ),
        )
        if args.trace
        else None
    )
    started = time.perf_counter()
    with observe_search(report):
        outcome = optimize_order_plan(command, engine=DomainCuttingEngineAdapter())
    search_wall = time.perf_counter() - started
    gallery = list(outcome.candidate_snapshots or (outcome.snapshot,))
    assert all(s["validation"]["is_valid"] for s in gallery)
    serialize_wall = 0
    size = {}
    if report:
        report.gallery([], gallery, "published_preview")
        report.metadata["preview_gallery"] = [
            dict(geometry_fingerprint=geometry_signature(s)) for s in gallery
        ]
        started = time.perf_counter()
        data = report.export()
        target = Path(args.output).with_suffix("")
        report_json = canonical_json(data)
        html = render_search_report(data)
        target.with_suffix(".report.json").write_text(report_json, encoding="utf-8")
        target.with_suffix(".report.html").write_text(html, encoding="utf-8")
        serialize_wall = time.perf_counter() - started
        size = dict(
            json_bytes=len(report_json.encode("utf-8")),
            html_bytes=len(html.encode("utf-8")),
            events=len(data["events"]),
            spans=len(data["spans"]),
            attempts=len(data["attempts"]),
            geometries=len(data["geometries"]),
            candidates=len(data["candidates"]),
            coverage=data["coverage_manifest"],
        )
        assert [c["geometry_fingerprint"] for c in data["final_gallery"]] == [
            geometry_signature(s) for s in gallery
        ]
    result = dict(
        case=args.case,
        trace=bool(args.trace),
        budget=args.budget,
        input_fingerprint=digest,
        search_wall_sec=search_wall,
        serialization_wall_sec=serialize_wall,
        peak_rss_kib=peak_rss_kib(),
        boards=len(outcome.snapshot["sheets"]),
        gallery=[geometry_signature(s) for s in gallery],
        rank=outcome.snapshot["industrial_rank"],
        valid=True,
        **size,
    )
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        args.case,
        "ON" if args.trace else "OFF",
        round(search_wall, 3),
        result["boards"],
        flush=True,
    )


def continuation_witness(output, budget):
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
        merge_preview_candidates,
    )

    command = command_for(cases()["regular"], budget)
    previous = None
    retained = {}
    seeds = ()
    for index in range(3):
        report = SearchReport(
            round_id=index,
            parent_run_id=previous["run_id"] if previous else None,
            engine_version=ENGINE_VERSION,
            input_fingerprint=command.input_fingerprint,
            settings_fingerprint=fingerprint(command.optimizer.__repr__()),
            **source_provenance(),
        )
        if previous:
            report.metadata["previous_round"] = previous
        with observe_search(report):
            outcome = optimize_order_plan(
                replace(command, seed_plans=seeds, search_round=index),
                engine=DomainCuttingEngineAdapter(),
            )
            current = {}
            for snapshot in outcome.candidate_snapshots or (outcome.snapshot,):
                signature = geometry_signature(snapshot)
                candidate_id = signature[:24]
                current[candidate_id] = dict(
                    candidate_id=candidate_id,
                    geometry_fingerprint=signature,
                    snapshot=snapshot,
                )
            retained = (
                merge_preview_candidates(current, retained) if retained else current
            )
            report.gallery(
                [], [c["snapshot"] for c in retained.values()], "published_preview"
            )
        seeds = outcome.search_seeds
        report.metadata["preview_gallery"] = [
            dict(
                preview_candidate_id=c["candidate_id"],
                geometry_fingerprint=c["geometry_fingerprint"],
            )
            for c in retained.values()
        ]
        data = report.export()
        assert [c["geometry_fingerprint"] for c in data["final_gallery"]] == [
            c["geometry_fingerprint"] for c in retained.values()
        ]
        assert not data["coverage_manifest"]["unclosed_spans"]
        if index:
            assert any(
                e["reason"] == "continue_merge_final_sort_dedup_limit"
                for e in data["gallery_history"]
            )
        (output / f"continue-round-{index}.report.json").write_text(
            canonical_json(data), encoding="utf-8"
        )
        (output / f"continue-round-{index}.report.html").write_text(
            render_search_report(data), encoding="utf-8"
        )
        previous = data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuation", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--case", default="regular", choices=cases())
    parser.add_argument("--budget", type=float, default=0.6)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.continuation:
        continuation_witness(output, args.budget)
        return
    results = []
    for case in cases():
        for repeat in range(2):
            for on in ([False, True] if repeat == 0 else [True, False]):
                target = output / f'{case}-{"on" if on else "off"}-{repeat}.json'
                command = [
                    sys.executable,
                    "-E",
                    __file__,
                    "--worker",
                    "--case",
                    case,
                    "--budget",
                    str(args.budget),
                    "--output",
                    str(target),
                ]
                if on:
                    command.append("--trace")
                subprocess.run(command, cwd=ROOT, check=True, timeout=120)
                results.append(json.loads(target.read_text(encoding="utf-8")))
                (output / "benchmark.json").write_text(
                    json.dumps(results, indent=2), encoding="utf-8"
                )


if __name__ == "__main__":
    main()
