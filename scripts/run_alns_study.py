"""Sequential fresh-process ALNS evidence, including failures and A/A controls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.alns_research import OPERATORS
from scripts.benchmark_alns import source_manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="docs/evidence/alns-study/matrix")
    p.add_argument("--inputs", default="docs/evidence/alns-study")
    p.add_argument("--cases", nargs="+", default=["263", "298"])
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--budget", type=float, default=5)
    p.add_argument("--attempts", type=int, default=32)
    p.add_argument("--max-boards", type=int, default=3)
    p.add_argument("--area-first", action="store_true")
    p.add_argument("--screen-prefix", action="store_true")
    p.add_argument("--checkpoint-arms", nargs="+", default=["baseline", *OPERATORS, "fixed", "adaptive"])
    args = p.parse_args()
    output, inputs = ROOT/args.output, ROOT/args.inputs
    output.mkdir(parents=True, exist_ok=True)
    frozen_source = source_manifest()
    records = []

    def run(case, phase, arm, repeat, checkpoint=None, native_output=None):
        name = f"{case}-{phase}-{arm}-r{repeat}"
        destination = output/f"{name}.json"
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite evidence: {destination}")
        command = [sys.executable, str(ROOT/"scripts/benchmark_alns.py"), "--worker", "--case", case,
            "--input", str(inputs/f"input-{case}.json"), "--arm", arm,
            "--budget", str(120 if checkpoint else args.budget), "--attempts", str(args.attempts),
            "--strict", "--output", str(destination)]
        command.extend(["--max-boards", str(args.max_boards)])
        if args.area_first:
            command.append("--area-first")
        if args.screen_prefix:
            command.append("--screen-prefix")
        if checkpoint:
            command.extend(["--checkpoint", str(checkpoint)])
        if native_output:
            command.extend(["--native-output", str(native_output)])
        try:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
            if completed.returncode:
                result = dict(status="worker_failed", returncode=completed.returncode, stderr=completed.stderr)
                destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
            else:
                result = json.loads(destination.read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired as exc:
            result = dict(status="worker_timeout", stderr=str(exc.stderr))
            destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if result.get("source_manifest") != frozen_source and result.get("status") == "completed":
            result["status"] = "source_changed"
            destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
        row = dict(case=case, phase=phase, arm=arm, repeat=repeat, file=destination.name,
                   sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                   status=result["status"], valid=result.get("valid"), final=result.get("final"),
                   elapsed=result.get("elapsed"), peak_rss_kib=result.get("peak_rss_kib"),
                   strict=result.get("strict"), attempts=(result.get("trace") or {}).get("attempts"))
        records.append(row)
        (output/"index.json").write_text(json.dumps(dict(records=records, source_manifest=frozen_source), indent=2), encoding="utf-8")
        print(name, row["status"], (row["final"] or {}).get("boards"), round(row["elapsed"] or 0, 3), row["attempts"], flush=True)

    for case in args.cases:
        checkpoint = output/f"native-{case}.json"
        for repeat in range(args.repeats):
            arms = ["baseline", "aa", "fixed", "adaptive"]
            # Freeze the first baseline before running independent changed arms.
            if repeat % 2:
                arms.reverse()
            for arm in arms:
                run(case, "operational", arm, repeat,
                    native_output=checkpoint if repeat == 0 and arm == "baseline" else None)
        if not checkpoint.exists():
            continue
        for repeat in range(args.repeats):
            arms = args.checkpoint_arms.copy()
            if repeat % 2:
                arms.reverse()
            for arm in arms:
                run(case, "checkpoint", arm, repeat, checkpoint=checkpoint)
    if any(r["status"] != "completed" or not r["valid"] or any(s["passed"] is not True for s in r["strict"] or []) for r in records):
        raise SystemExit("One or more evidence observations failed; see index.json")


if __name__ == "__main__":
    main()
