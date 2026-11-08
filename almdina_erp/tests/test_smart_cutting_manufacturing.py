"""Generate/save/reload/validate/actual JS export/strict import witnesses."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable
install_if_unavailable()

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry, OptimizeOrderPlanCommand, OptimizerOptions, optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import _largest_reusable_free_area
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
from almdina_erp.almdina_erp.services import dxf_import_service as legacy
from almdina_erp.almdina_erp.services import strict_dxf_import_service as strict
from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js


def corner(kind):
    return dict(piece_type=kind, width_cm=20, length_cm=20, qty=4, allow_rotation=1,
                clipped_corner_position="Top Right", clipped_corner_width_cm=8,
                clipped_corner_length_cm=8)


CASES = [
    (40.3, 40.3, 0, [corner("L-Shaped Corner"), dict(width_cm=10, length_cm=10, qty=1)]),
    (40.3, 40.3, 0, [corner("Clipped Corner"), dict(width_cm=8, length_cm=3, qty=1)]),
    (41.3, 41.3, .5, [corner("L-Shaped Corner"), dict(width_cm=10, length_cm=10, qty=1)]),
    (34.3, 12, 0, [dict(piece_type="Glass", width_cm=22, length_cm=12, qty=1, glass_margin_mm=10),
                   dict(piece_type="Glass", width_cm=12, length_cm=12, qty=1, glass_margin_mm=10),
                   dict(width_cm=9, length_cm=9, qty=1), dict(width_cm=18, length_cm=4, qty=1)]),
    (60, 40, 0, [dict(width_cm=40, length_cm=60, qty=2, allow_rotation=1)]),
    (80, 60, 0, [dict(width_cm=30, length_cm=40, qty=2, extra_liner=1,
                    liner_reference_side="edge_long_left", liner_width_cm=2,
                    liner_offset_cm=3, liner_start_cm=2, liner_length_cm=20)]),
]


def rows_with_identity(rows):
    return [dict(piece_type="Regular", allow_rotation=0) | row for row in rows]


def import_saved_plan(plan, rows, path):
    order_rows = [SimpleNamespace(**dict(row, name=f"row-{i}", piece_instance_id=f"smart:{i}",
        cut_width_cm=row.get("cut_width_cm", row["width_cm"]),
        cut_length_cm=row.get("cut_length_cm", row["length_cm"]))) for i,row in enumerate(rows,1)]
    order = SimpleNamespace(name="SMART-ROUNDTRIP", pieces=order_rows, allow_piece_mirroring=bool(plan.get("allow_piece_mirroring")),
        board_width_cm=plan["full_board_width_cm"], board_length_cm=plan["full_board_length_cm"],
        full_board_width_mm=plan["full_board_width_cm"]*10,
        full_board_length_mm=plan["full_board_length_cm"]*10)
    settings = PlanSettings("smart", plan["machine_type"], .4, plan["kerf_cm"]*10, plan["trim_cm"]*10)
    with patch.object(legacy.frappe, "get_site_path", return_value=str(path)):
        return strict.parse_production_dxf("/private/files/smart.dxf", order, settings=settings)


@pytest.mark.parametrize("trim_mm", [0, .1, 1, 2, 3])
def test_real_243_discovery_snapshot_reload_export_strict_import(trim_mm, tmp_path):
    from almdina_erp.tests.cutting_243_cases import source_case
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature

    rows = [dict(row, piece_instance_id=f"smart:{i}")
        for i, row in enumerate(rows_with_identity(source_case()["rows"]), 1)]
    outcome = optimize_order_plan(OptimizeOrderPlanCommand(
        engine_version="real-243-regression", input_fingerprint="real-243-regression",
        board=BoardGeometry(122, 244, trim_mm/10, .5),
        optimizer=OptimizerOptions("smart", "CNC Router", 5, 40, 30, 30, .09),
        piece_rows=tuple(rows),
    ), engine=domain_cutting_engine)
    snapshot = outcome.snapshot
    assert outcome.required_boards == len(snapshot["sheets"]) == 3
    assert snapshot["validation"]["is_valid"]
    assert snapshot["trim_cm"] == trim_mm/10
    assert snapshot["kerf_cm"] == .5
    assert snapshot["total_board_area_m2"] == pytest.approx(3*(122-.2*trim_mm)*(244-.2*trim_mm)/10000)
    assert snapshot["waste_area_m2"] == pytest.approx(snapshot["total_board_area_m2"]-8.180127)
    assert not validate_plan(snapshot, list(outcome.expanded_pieces),
        122-.2*trim_mm, 244-.2*trim_mm, kerf_cm=.5)
    assert len({p["piece_instance_id"] for s in snapshot["sheets"] for p in s["pieces"]}) == 50
    assert snapshot["industrial_metrics"]["largest_reusable_free_area_m2"] == pytest.approx(
        _largest_reusable_free_area(snapshot, 30, 30, .09, machine_type="CNC Router"))
    saved = tmp_path / "selected.json"
    saved.write_text(json.dumps(snapshot))
    reloaded = json.loads(saved.read_text())
    assert geometry_signature(reloaded) == geometry_signature(snapshot)
    imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, tmp_path))
    assert len(imported["sheets"]) == 3
    assert sum(len(s["pieces"]) for s in imported["sheets"]) == 50
    # Duplicate-size copies may bind in another order; their material geometry
    # and complete source-identity set must survive the existing DXF contract.
    assert {p["piece_instance_id"] for s in imported["sheets"] for p in s["pieces"]} == {
        p["piece_instance_id"] for s in snapshot["sheets"] for p in s["pieces"]}
    for before, after in zip(snapshot["sheets"], imported["sheets"], strict=True):
        geometry = lambda sheet: sorted(tuple(p[k] for k in ("x", "y", "w", "h")) for p in sheet["pieces"])
        assert len(before["pieces"]) == len(after["pieces"])
        for expected, actual in zip(geometry(before), geometry(after), strict=True):
            assert actual == pytest.approx(expected, abs=.0001)


@pytest.mark.parametrize("width,height,trim,rows", CASES)
def test_smart_saved_snapshot_exports_and_strictly_imports(width, height, trim, rows, tmp_path):
    rows = rows_with_identity(rows)
    outcome = optimize_order_plan(OptimizeOrderPlanCommand(
        engine_version="smart-manufacturing-test", input_fingerprint="smart-manufacturing-test",
        board=BoardGeometry(width, height, trim, .3),
        optimizer=OptimizerOptions("smart", "CNC Router", .4, 20, 30, 30, .09),
        piece_rows=tuple(rows), allow_piece_mirroring=True,
    ), engine=domain_cutting_engine)
    assert outcome.snapshot["validation"]["is_valid"]
    for candidate in outcome.candidate_snapshots or (outcome.snapshot,):
        assert candidate["industrial_metrics"]["largest_reusable_free_area_m2"] == pytest.approx(
            _largest_reusable_free_area(
                {"sheets": candidate["sheets"]}, 30, 30, .09,
                machine_type="CNC Router",
            )
        )
    ranks = [tuple(candidate["industrial_rank"]) for candidate in outcome.candidate_snapshots]
    assert ranks == sorted(ranks)
    if ranks:
        assert tuple(outcome.snapshot["industrial_rank"]) == ranks[0]
    saved = tmp_path / "saved-snapshot.json"
    for candidate in outcome.candidate_snapshots or (outcome.snapshot,):
        saved.write_text(json.dumps(candidate))
        reloaded = json.loads(saved.read_text())
        assert reloaded == json.loads(json.dumps(candidate))
        assert not validate_plan(reloaded, list(outcome.expanded_pieces),
            reloaded["usable_board_width_cm"], reloaded["usable_board_length_cm"], kerf_cm=.3)
        assert not placement_permission_errors(reloaded, list(outcome.expanded_pieces), mirroring_allowed=True)
        imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, tmp_path))
        assert sum(len(s["pieces"]) for s in imported["sheets"]) == sum(row["qty"] for row in rows)
