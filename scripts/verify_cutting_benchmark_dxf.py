"""Export benchmark snapshots with the real JS exporter and strictly re-import.

Inputs are JSON files emitted by benchmark_cutting_p1.py. No production orders
are fetched or changed. Geometry validity and strict manufacturing import are
separate evidence columns; unsupported legacy layouts remain visible failures.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path.cwd()))
from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan, rows_with_identity
from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = []
    for source in args.input:
        for row in json.loads(Path(source).read_text()):
            plan = row["snapshot"]
            strict_valid, error = True, ""
            candidates = row.get("candidate_snapshots") or [plan]
            signatures = [geometry_signature(candidate) for candidate in candidates]
            assert len(signatures) == len(set(signatures)), "Duplicate candidate geometry"
            for index, candidate in enumerate(candidates):
                try:
                    with TemporaryDirectory() as directory:
                        path = export_real_js(candidate, Path(directory))
                        imported = import_saved_plan(candidate, rows_with_identity(row["rows"]), path)
                    assert sum(len(s["pieces"]) for s in imported["sheets"]) == sum(r["qty"] for r in row["rows"])
                except Exception as exc:
                    strict_valid, error = False, f"candidate {index+1}: {exc}"
                    break
            record = dict(label=row["label"], head=row["head"],case=row["case"], mode=row["mode"], machine=row["machine_type"],
                valid=plan["validation"]["is_valid"], boards=len(plan["sheets"]),
                reusable_offcut_m2=plan["industrial_metrics"]["largest_reusable_free_area_m2"],
                budget_sec=row['time_limit_sec'], runtime_sec=round(row["runtime_sec"], 4), unique_candidates=len(candidates),strict_import_valid=strict_valid,
                strict_import_error=error)
            records.append(record)
            print(record, flush=True)
    with Path(args.output).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    if any(r["mode"] == "Smart Search" and not r["strict_import_valid"] for r in records):
        raise SystemExit("Smart manufacturing benchmark failed; see CSV")


if __name__ == "__main__":
    main()
