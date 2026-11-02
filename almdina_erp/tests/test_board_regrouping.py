"""Bounded opt-in regrouping preserves completed work and manufacturing rules."""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import optimizer as opt, plan_search as search
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    create_sheet, expand_piece_groups, make_placed_piece,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors


OPTIONS = dict(machine_type="CNC Router", mirroring_allowed=False,
    metric_kwargs=dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09))


def golden(name="300", metadata=None):
    case = json.loads((Path(__file__).parent / "fixtures/regroup_native_baselines.json").read_text())[name]
    rows = deepcopy(case["rows"])
    for row in rows:
        row.update(metadata or {})
    pieces = expand_piece_groups(rows)
    source = {piece["id"]: piece for piece in pieces}
    sheets = []
    for number, placements in enumerate(case["placements"], 1):
        sheet = create_sheet(number, case["width"], case["height"])
        sheet["pieces"] = [make_placed_piece(source[pid], x, y, w, h, rotated)
            for pid, x, y, w, h, rotated in placements]
        sheet["board_marker"] = f"board-{number}"
        sheets.append(sheet)
    plan = dict(sheets=sheets, unplaced=[], method_key=case["method_key"], complexity=case["complexity"],
        used_area_m2=sum(piece["area_m2"] for piece in pieces))
    return opt.enrich_plan_metrics(plan, case["method_key"], "CNC Router"), pieces, rows, case


def regroup(plan, pieces, width=122, height=244, kerf=.5, **kwargs):
    return search.improve_board_regrouping(plan, pieces, width, height, kerf,
        **(OPTIONS | dict(deadline=time.monotonic()+3) | kwargs))


@pytest.mark.parametrize("name,expected", [("300", 2.32288), ("3687", 2.1899)])
def test_native_regroup_improves_two_system_witnesses_without_mutating_input(name, expected):
    plan, pieces, _, case = golden(name)
    original, sources, offered = deepcopy(plan), deepcopy(pieces), []
    result = regroup(plan, pieces, case["width"], case["height"], candidate_callback=offered.append)
    assert result is not plan and plan == original and pieces == sources
    assert result["industrial_rank"] < plan["industrial_rank"]
    assert result["industrial_metrics"]["largest_reusable_free_area_m2"] == pytest.approx(expected)
    assert len(result["sheets"]) == len(plan["sheets"]) == 3
    assert not validate_plan(result, pieces, case["width"], case["height"], kerf_cm=.5)
    assert not placement_permission_errors(result, pieces, mirroring_allowed=False)
    assert sorted(piece["piece_instance_id"] for sheet in result["sheets"] for piece in sheet["pieces"]) == sorted(
        piece["piece_instance_id"] for piece in pieces)
    assert sorted(sheet["board_marker"] for sheet in result["sheets"]) == sorted(
        sheet["board_marker"] for sheet in plan["sheets"])
    assert result["total_board_area_m2"] == pytest.approx(3*case["width"]*case["height"]/10000)
    assert result["waste_area_m2"] == pytest.approx(result["total_board_area_m2"]-result["used_area_m2"])
    ranks = [tuple(plan["industrial_rank"])] + [tuple(item["industrial_rank"]) for item in offered]
    assert len(ranks) > 1 and all(a > b for a, b in zip(ranks, ranks[1:]))
    assert offered[-1] is result


def test_later_expiration_cannot_erase_a_completed_valid_winner(monkeypatch):
    plan, pieces, _, _ = golden()
    winner = regroup(plan, pieces)
    now = [0.0]
    def proposals(*args):
        yield deepcopy(winner)
        now[0] = 2.0
        yield deepcopy(winner)
    monkeypatch.setattr(search, "_regrouped_board_candidates", proposals)
    monkeypatch.setattr(search.time, "monotonic", lambda: now[0])
    offered = []
    result = regroup(plan, pieces, deadline=1, candidate_callback=offered.append)
    assert now[0] > 1 and len(offered) == 1
    assert result["sheets"] == winner["sheets"]
    assert result is offered[0]


@pytest.mark.parametrize("fault", ["missing", "duplicate", "kerf", "rotation", "extra_board", "unplaced"])
def test_invalid_or_incomplete_proposals_never_displace_the_incumbent(monkeypatch, fault):
    plan, pieces, _, _ = golden()
    bad = deepcopy(plan)
    first, second = bad["sheets"][0]["pieces"][:2]
    if fault == "missing": bad["sheets"][0]["pieces"].pop()
    elif fault == "duplicate": second["id"] = first["id"]
    elif fault == "kerf": second.update(x=first["x"], y=first["y"])
    elif fault == "rotation":
        next(piece for piece in pieces if piece["id"] == first["id"])["allow_rotation"] = 0
        first["rotated"] = True
    elif fault == "extra_board": bad["sheets"].append(create_sheet(4, 122, 244))
    else: bad["unplaced"] = [pieces[0]]
    # Claim a better remnant in stale metadata; native enrichment must ignore it.
    bad["industrial_rank"] = [0]
    monkeypatch.setattr(search, "_regrouped_board_candidates", lambda *args: iter([bad]))
    offered = []
    assert regroup(plan, pieces, candidate_callback=offered.append) is plan
    assert not offered


def small_plan():
    pieces = expand_piece_groups([dict(width_cm=6, length_cm=7, qty=2, allow_rotation=0)])
    sheets = [dict(create_sheet(i+1, 10, 10), pieces=[make_placed_piece(piece, 0, 0, 6, 7, False)])
        for i, piece in enumerate(pieces)]
    return opt.enrich_plan_metrics(dict(sheets=sheets, unplaced=[]), "MaxRects Bottom Left"), pieces


@pytest.mark.parametrize("marker", ["source_offcut", "placed_offcut", "sheet_offcut", "glass", "corner",
    "geometry", "overlay", "source_geometry", "source_overlay", "outline", "special", "guest",
    "mirrored", "quarter_turn", "panel", "expired", "unplaced"])
def test_protected_boards_or_expired_search_do_not_start_packing(monkeypatch, marker):
    plan, pieces = small_plan()
    placed = plan["sheets"][0]["pieces"][0]
    options = {}
    if marker == "source_offcut": pieces[0]["resource_kind"] = "OFFCUT"
    elif marker == "placed_offcut": placed["resource_kind"] = "OFFCUT"
    elif marker == "sheet_offcut": plan["sheets"][0]["resource_kind"] = "OFFCUT"
    elif marker == "glass": pieces[0]["piece_type"] = "Glass"
    elif marker == "corner": pieces[0]["piece_type"] = "L-Shaped Corner"
    elif marker == "geometry": placed["geometry"] = {"outer": [[0, 0], [1, 1]]}
    elif marker == "overlay": placed["overlays"] = [{"layer": "Liner"}]
    elif marker == "source_geometry": pieces[0]["geometry"] = {"outer": [[0, 0], [1, 1]]}
    elif marker == "source_overlay": pieces[0]["overlays"] = [{"layer": "Liner"}]
    elif marker == "outline": placed["placement_outline_cm"] = [[0, 0], [1, 1]]
    elif marker == "special": pieces[0]["special_shape_geometry_json"] = "{}"
    elif marker == "guest": placed["glass_host_piece_id"] = pieces[1]["id"]
    elif marker == "mirrored": placed["mirrored"] = True
    elif marker == "quarter_turn": placed["placement_quarter_turns"] = 1
    elif marker == "panel": options["machine_type"] = "Panel Saw"
    elif marker == "expired": options["deadline"] = time.monotonic()-1
    else: plan["unplaced"] = [pieces[0]]
    monkeypatch.setattr(opt, "_run_preordered_method", lambda *a, **kw: pytest.fail("unsafe packing"))
    assert regroup(plan, pieces, 10, 10, **options) is plan


def test_shared_local_cap_and_oversize_guard(monkeypatch):
    plan, pieces, _, _ = golden()
    calls = []
    def reject(sequence, subset, *args):
        calls.append(len(subset))
        return dict(unplaced=subset, sheets=[])
    monkeypatch.setattr(opt, "_run_preordered_method", reject)
    assert regroup(plan, pieces) is plan
    assert len(calls) == 24 and max(calls) <= 64
    monkeypatch.setattr(search, "_MAX_REPACK_PIECES", 1)
    calls.clear()
    assert regroup(plan, pieces) is plan and not calls


@pytest.mark.parametrize("kerf", [0, .5])
def test_repacking_uses_source_permissions_and_preserves_untouched_board(monkeypatch, kerf):
    plan, pieces = small_plan()
    protected = deepcopy(plan["sheets"][0])
    protected.update(sheet_no=3, resource_kind="OFFCUT")
    extra = expand_piece_groups([dict(width_cm=6, length_cm=7, qty=1, allow_rotation=0)])[0]
    extra.update(id=3, piece_instance_id="protected", resource_kind="OFFCUT")
    protected["pieces"] = [make_placed_piece(extra, 0, 0, 6, 7, False)]
    plan["sheets"].append(protected)
    pieces.append(extra)
    seen = []
    original = opt._run_preordered_method
    def record(sequence, subset, *args):
        seen.extend(subset)
        return original(sequence, subset, *args)
    monkeypatch.setattr(opt, "_run_preordered_method", record)
    proposals = list(search._regrouped_board_candidates(plan, pieces, 10, 10, kerf, time.monotonic()+3))
    assert proposals and seen and all(piece["id"] != 3 and not piece["allow_rotation"] for piece in seen)
    for candidate in proposals:
        offcut = next(sheet for sheet in candidate["sheets"] if sheet.get("resource_kind") == "OFFCUT")
        assert offcut["pieces"] == protected["pieces"]
        assert all(not piece["rotated"] for sheet in candidate["sheets"] for piece in sheet["pieces"])


@pytest.mark.parametrize("enabled,machine", [(False, "CNC Router"), (True, "CNC Router"), (True, "Panel Saw")])
def test_smart_opt_in_runs_only_after_native_quality_with_the_original_deadline(monkeypatch, enabled, machine):
    pieces = expand_piece_groups([dict(width_cm=90, length_cm=60, qty=2)])
    baseline = opt.auto_fast(pieces, 100, 100, .5, machine)
    monkeypatch.setattr(opt.time, "monotonic", lambda: 0)
    monkeypatch.setattr(opt, "auto_fast", lambda *a, **kw: deepcopy(baseline))
    monkeypatch.setattr(opt, "_run_preordered_method", lambda *a, **kw: deepcopy(baseline))
    monkeypatch.setattr(opt, "_cp_sat_available", lambda: False)
    monkeypatch.setattr(opt, "_finish_plan_search", lambda plan, *a, **kw: plan)
    monkeypatch.setattr(opt, "deep_search", lambda *a, **kw: kw["initial_plan"])
    events = []
    def quality(plan, *a, **kw):
        events.append(("quality", kw["deadline"]))
        return plan
    def regrouped(plan, *a, **kw):
        events.append(("regroup", kw["deadline"]))
        kw["candidate_callback"](deepcopy(plan))
        return plan
    monkeypatch.setattr(search, "improve_same_count_layout", quality)
    monkeypatch.setattr(search, "improve_board_regrouping", regrouped)
    kwargs = dict(experimental_regrouping=True) if enabled else {}
    result = opt.smart_search(pieces, 100, 100, .5, machine, 1, **kwargs)
    assert events == ([("quality", 1), ("regroup", 1)] if enabled and machine != "Panel Saw" else [("quality", 1)])
    assert result["sheets"] == baseline["sheets"]


@pytest.mark.parametrize("trim", [0, .3])
@pytest.mark.parametrize("addons", [False, True])
def test_native_winner_survives_snapshot_reload_and_actual_strict_dxf(trim, addons, tmp_path):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan, export_real_js
    metadata = dict(extra_liner=1, liner_reference_side="edge_long_left", liner_width_cm=1,
        liner_offset_cm=1, liner_start_cm=1, liner_length_cm=5,
        extra_back_groove=1, back_groove_reference_side="edge_long_right",
        back_groove_width_cm=.7, back_groove_offset_cm=2, back_groove_start_cm=1, back_groove_length_cm=5,
        extra_recessed_handle_cutout=1, recessed_handle_reference_side="edge_width_top",
        recessed_handle_width_cm=1, recessed_handle_offset_cm=1, recessed_handle_start_cm=1,
        recessed_handle_length_cm=3, extra_double=1, extra_double_reference_sides="edge_long_right") if addons else {}
    plan, pieces, rows, case = golden(metadata=metadata)
    result = regroup(plan, pieces)
    assert result["industrial_rank"] < plan["industrial_rank"]
    for sheet in result["sheets"]:
        for piece in sheet["pieces"]:
            assert all(piece[key] == value for key, value in metadata.items())
    class Frozen:
        expand_pieces = domain_cutting_engine.expand_pieces
        validate = domain_cutting_engine.validate
        def optimize(self, *args, **kwargs):
            return deepcopy(result)
    command = OptimizeOrderPlanCommand("regroup-test", "regroup-test",
        BoardGeometry(case["width"]+2*trim, case["height"]+2*trim, trim, .5),
        OptimizerOptions("smart", "CNC Router", 5, 40, 30, 30, .09), tuple(rows))
    snapshot = optimize_order_plan(command, engine=Frozen()).snapshot
    assert snapshot["validation"]["is_valid"] and snapshot["trim_cm"] == trim
    assert snapshot["total_board_area_m2"] == pytest.approx(3*case["width"]*case["height"]/10000)
    saved = tmp_path/"selected.json"
    saved.write_text(json.dumps(snapshot))
    reloaded = json.loads(saved.read_text())
    assert reloaded == snapshot
    imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, tmp_path))
    assert len(imported["sheets"]) == 3
    assert {piece["piece_instance_id"] for sheet in imported["sheets"] for piece in sheet["pieces"]} == {
        piece["piece_instance_id"] for piece in pieces}


def test_no_rotation_zero_kerf_source_survives_actual_strict_dxf(tmp_path):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan, export_real_js
    rows = [dict(width_cm=6, length_cm=7, qty=2, allow_rotation=0, piece_type="Regular",
        piece_instance_id="smart:1")]
    pieces = expand_piece_groups(rows)
    plan, _ = small_plan()
    # Rebuild from the exact request identities.
    for sheet, piece in zip(plan["sheets"], pieces):
        sheet["pieces"] = [make_placed_piece(piece, 0, 0, 6, 7, False)]
    result = regroup(plan, pieces, 10, 10, 0)
    class Frozen:
        expand_pieces = domain_cutting_engine.expand_pieces
        validate = domain_cutting_engine.validate
        def optimize(self, *args, **kwargs):
            return deepcopy(result)
    snapshot = optimize_order_plan(OptimizeOrderPlanCommand("no-rotation", "no-rotation",
        BoardGeometry(10, 10, 0, 0), OptimizerOptions("smart", "CNC Router", 1, 40, 30, 30, .09),
        tuple(rows)), engine=Frozen()).snapshot
    assert snapshot["validation"]["is_valid"] and snapshot["kerf_cm"] == 0
    imported = import_saved_plan(snapshot, rows, export_real_js(snapshot, tmp_path))
    assert sum(len(sheet["pieces"]) for sheet in imported["sheets"]) == 2
    assert all(not piece["rotated"] for sheet in imported["sheets"] for piece in sheet["pieces"])
