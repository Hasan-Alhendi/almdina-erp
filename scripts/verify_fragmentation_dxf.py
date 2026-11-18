"""Actual JS export and strict import of every benchmark gallery candidate."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from almdina_erp.tests.frappe_test_stub import install_if_unavailable

    install_if_unavailable()
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    from almdina_erp.almdina_erp.domain.cutting.evaluation import (
        validate_plan,
        placement_permission_errors,
    )
    from almdina_erp.almdina_erp.services import dxf_import_service as legacy
    from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
        parse_production_dxf,
    )

    result = {}
    for path in args.runs:
        run = json.loads(path.read_bytes())
        number = run["case"].split("-")[-1]
        dco = json.loads(
            next(args.evidence.glob(f"DCO-26-{number}*.json")).read_bytes()
        )
        profiles = {}
        for row in dco["pieces"]:
            for axis, sides in (
                ("long", ("left", "right")),
                ("width", ("top", "bottom")),
            ):
                for side in sides:
                    field = f"edge_{axis}_{side}"
                    if row.get(field):
                        name = (
                            row.get(field + "_type_override")
                            or dco["default_edge_type"]
                        )
                        thickness = row[f"edge_{axis}_thickness_mm"]
                        assert name not in profiles or profiles[name] == thickness
                        profiles[name] = thickness
        rows = [
            SimpleNamespace(**{**row, "name": f"local-{row['piece_no']}",
                **(dict(extra_liner=0, liner_specs_json=None)
                   if "liner" in run.get("ignored_addons", []) else {})})
            for row in dco["pieces"]
        ]
        order = SimpleNamespace(**{**dco, "pieces": rows})

        def load_profiles(doctype, *, filters, fields):
            assert doctype == "Edge Banding Type"
            return [
                SimpleNamespace(name=n, disabled=0, thickness_mm=profiles[n])
                for n in filters["name"][1]
            ]

        checks = []
        for index, snapshot in enumerate(run["gallery"], 1):
            reloaded = json.loads(json.dumps(snapshot))
            assert geometry_signature(reloaded) == geometry_signature(snapshot)
            directory = args.output.parent / "dxf" / path.stem / str(index)
            directory.mkdir(parents=True, exist_ok=True)
            exported = export_real_js(reloaded, directory.resolve())
            expected = Counter(p["piece_instance_id"] for p in run["sources"])
            settings = PlanSettings(
                "smart",
                snapshot["machine_type"],
                run["budget"],
                snapshot["kerf_cm"] * 10,
                snapshot["trim_cm"] * 10,
                deduct_edge_thickness=run["dimensions"] == "saved",
            )
            with (
                patch.object(
                    legacy.frappe, "get_site_path", return_value=str(exported.resolve())
                ),
                patch.object(legacy.frappe, "get_all", load_profiles, create=True),
            ):
                try:
                    imported = parse_production_dxf(
                        "/private/files/local.dxf", order, settings=settings
                    )
                except legacy.DxfImportError as error:
                    checks.append(
                        dict(
                            index=index,
                            passed=False,
                            issues=Counter(i.code for i in error.issues),
                            details=[
                                dict(code=i.code, params=i.params)
                                for i in error.issues[:3]
                            ],
                        )
                    )
                    continue
            actual = Counter(
                p["piece_instance_id"] for s in imported["sheets"] for p in s["pieces"]
            )

            # The importer may exchange physical copies of the same source row.
            def placements(plan):
                return sorted(
                    tuple(
                        sorted(
                            (
                                p["source_piece_no"],
                                *[round(p[k], 3) for k in ("x", "y", "w", "h")],
                            )
                            for p in s["pieces"]
                        )
                    )
                    for s in plan["sheets"]
                )

            errors = validate_plan(
                reloaded,
                run["sources"],
                snapshot["usable_board_width_cm"],
                snapshot["usable_board_length_cm"],
                kerf_cm=snapshot["kerf_cm"],
            )
            errors += placement_permission_errors(
                reloaded,
                run["sources"],
                mirroring_allowed=snapshot["allow_piece_mirroring"],
            )
            checks.append(
                dict(
                    index=index,
                    passed=not errors
                    and actual == expected
                    and placements(imported) == placements(reloaded),
                    identity_match=actual == expected,
                    geometry_errors=errors,
                    placements_match=placements(imported) == placements(reloaded),
                    saw_center_status=imported.get("saw_center_status"),
                    pieces=sum(actual.values()),
                    dxf=str(exported),
                )
            )
        result[path.name] = checks
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(args.output, flush=True)


if __name__ == "__main__":
    main()
