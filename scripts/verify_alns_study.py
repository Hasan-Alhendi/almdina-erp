"""Isolated, sequential regression workers; retain native/runtime failures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"docs/evidence/alns-study/verification"
MODULES = ["test_alns_research", "test_board_regrouping", "test_same_count_layout_quality",
    "test_abc_cutting_search", "test_cutting_kerf_clearance", "test_smart_plan_portfolio",
    "test_cutting_plan_application", "test_plan_preview_session_exact_commit",
    "test_cutting_plan_lifecycle_safety", "test_plan_fingerprint_compatibility",
    "test_cutting_domain_architecture", "test_stage13_quality_gates",
    "test_stage15_documentation_contract", "test_smart_cutting_lifecycle",
    "test_final_cut_line_alignment", "test_smart_cutting_manufacturing"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--modules", nargs="+", choices=MODULES, default=MODULES)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if (output/"index.json").exists():
        raise FileExistsError("Use a fresh verification output directory")
    if sys.platform == "win32":
        import ctypes
        # Inherited by child workers: report native crashes without leaving
        # a Windows fault dialog holding the subprocess pipe open.
        ctypes.windll.kernel32.SetErrorMode(2)
    records = []
    for module in args.modules:
        xml = output/f"{module}.xml"
        bootstrap = ("from almdina_erp.tests.frappe_test_stub import install_if_unavailable; "
                     "install_if_unavailable(); import pytest, sys; raise SystemExit(pytest.main(sys.argv[1:]))")
        command = [sys.executable, "-c", bootstrap, "-q", f"almdina_erp/tests/{module}.py",
                   "--basetemp", f".pytest_cache/alns-isolated-{module}", "--junitxml", str(xml)]
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=240)
            row = dict(module=module, returncode=result.returncode, command=command)
            (output/f"{module}.txt").write_text(result.stdout+result.stderr, encoding="utf-8")
            if xml.exists():
                suite = ET.parse(xml).getroot().find("testsuite")
                row["summary"] = dict(suite.attrib) if suite is not None else {}
        except subprocess.TimeoutExpired as exc:
            row = dict(module=module, error="timeout", stdout=str(exc.stdout), stderr=str(exc.stderr))
        records.append(row)
        (output/"index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(module, row.get("returncode", "timeout"), row.get("summary", {}), flush=True)
    if any(row.get("returncode") != 0 for row in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
