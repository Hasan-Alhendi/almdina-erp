"""Dimensional witnesses, not a capture of the customer's saved plan.

The three left sizes and second-board widths are supplied requirements.
Right-hand lengths/positions and the second-board anchor are synthetic, stated
explicitly so a successful fixture never claims to verify the live snapshot.
"""
from copy import deepcopy
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.edge_protection import protect_plan_edges
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _translate_if_clear
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece

METRICS = dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09)


def witness(placements, *, width=122, height=244, trim=0):
    sources = expand_piece_groups([
        dict(width_cm=w, length_cm=h, qty=1, allow_rotation=False,
             piece_instance_id=f"placement-witness-{i}")
        for i, (_, _, w, h) in enumerate(placements)
    ])
    pieces = [make_placed_piece(source, x, y, w, h, False)
              for source, (x, y, w, h) in zip(sources, placements)]
    sheet = dict(sheet_no=1, resource_kind="FULL_BOARD", w=width-2*trim, h=height-2*trim,
                 full_width_cm=width, full_length_cm=height,
                 applied_trim_width_cm=trim, applied_trim_length_cm=trim, pieces=pieces)
    used = sum(p["w"]*p["h"] for p in pieces)/10000
    plan = dict(method_key="MaxRects Best Short Side", machine_type="CNC Router", kerf_cm=.5,
                sheets=[sheet], unplaced=[], used_area_m2=used,
                total_board_area_m2=width*height/10000, waste_area_m2=width*height/10000-used)
    assert not validate_plan(plan, sources, width-2*trim, height-2*trim, kerf_cm=.5)
    return enrich_plan_metrics(plan, plan["method_key"], "CNC Router", **METRICS), sources


def staggered_witness():
    return witness([
        (0, 0, 39.3, 79.8), (0, 80.3, 39.9, 80), (0, 160.8, 39.9, 80),
        (40.4, 0, 39.3, 40), (80.2, 0, 41.8, 60),
        (40.4, 40.5, 39.3, 199), (80.2, 60.5, 41.8, 183.5),
    ])


def three_widths_witness():
    return witness([(1.5, 0, 39.3, 80),
                    (0, 160, 39.3, 80), (39.8, 160, 39.3, 80), (79.6, 160, 39.3, 80)])


def finish(plan, sources, *, policy=None, **kwargs):
    return protect_plan_edges(plan, sources, plan["sheets"][0]["w"], plan["sheets"][0]["h"], .5,
        policy=policy or EdgeProtectionPolicy(15, 20), max_centerable_edge_gap_cm=7,
        machine_type=kwargs.pop("machine_type", "CNC Router"), mirroring_allowed=False,
        metric_options=kwargs.pop("metric_options", METRICS), **kwargs)


def positions(plan):
    return {p["id"]: (p["x"], p["y"]) for p in plan["sheets"][0]["pieces"]}


def test_staggered_left_chain_centers_with_coupled_neighbors_instead_of_moving_whole_board():
    plan, sources = staggered_witness()
    original = deepcopy(plan)
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(0, 20))
    actual = positions(result)
    assert [actual[i][1] for i in (1, 2, 3)] == pytest.approx([1.6, 81.9, 162.4])
    # The outer right column spans the full board and must remain fixed.
    assert actual[5] == positions(plan)[5]
    assert actual[7] == positions(plan)[7]
    assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)
    assert plan == original


def test_three_393mm_widths_move_15mm_and_align_to_independent_anchor():
    plan, sources = three_widths_witness()
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(15, 0))
    actual = positions(result)
    assert [actual[i][0] for i in (2, 3, 4)] == pytest.approx([1.5, 41.3, 81.1])
    assert actual[1] == positions(plan)[1]
    assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)


def test_left_only_16mm_trial_is_collision_free_but_loses_real_shared_cut_length():
    plan, sources = staggered_witness()
    shifted = _translate_if_clear(plan, 0, "y", (1, 2, 3), 1.6, .5)
    assert shifted is not None
    assert not validate_plan(shifted, sources, 122, 244, kerf_cm=.5)
    before = sheet_cut_line_quality(plan["sheets"][0], .5)
    after = sheet_cut_line_quality(shifted["sheets"][0], .5)
    assert after[0] > before[0] + .05
    # A coupled alternative is geometrically different from treating all Kerf
    # contacts as one rigid board-wide component.
    coupled = deepcopy(shifted)
    for piece in coupled["sheets"][0]["pieces"]:
        if piece["id"] in (4, 6):
            piece["y"] += 2
    assert not validate_plan(coupled, sources, 122, 244, kerf_cm=.5)
    assert sheet_cut_line_quality(coupled["sheets"][0], .5)[0] <= before[0] + .05


def test_left_chain_16mm_alone_is_accepted_when_right_has_no_shared_cut_blocker():
    plan, sources = witness([(0, 0, 39.3, 79.8), (0, 80.3, 39.9, 80),
                             (0, 160.8, 39.9, 80), (50, 0, 70, 244)])
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(0, 20), align_cut_lines=False)
    assert [positions(result)[i][1] for i in (1, 2, 3)] == pytest.approx([1.6, 81.9, 162.4])
    assert positions(result)[4] == positions(plan)[4]


def test_coupled_policy_moves_have_different_offsets_and_preserve_t_contacts():
    plan, sources = staggered_witness()
    result, decisions = finish(plan, sources, policy=EdgeProtectionPolicy(0, 20), align_cut_lines=False)
    shifts = decisions[0]["piece_shifts_mm"]
    assert [shifts[i] for i in (1, 2, 3)] == [16, 16, 16]
    assert shifts[4] == shifts[6] and shifts[4] != 16
    assert all(positions(result)[i][0] == positions(plan)[i][0] for i in positions(plan))
    assert sheet_cut_line_quality(result["sheets"][0], .5)[0] <= 14592


def test_kerf_contacts_are_choices_not_a_board_wide_rigid_constraint():
    plan, sources = staggered_witness()
    result, decisions = finish(plan, sources, policy=EdgeProtectionPolicy(0, 20))
    # The narrow first door can align its real right-hand cutter center to
    # the two wider doors. A T contact does not mechanically lock all seven.
    assert positions(result)[1][0] == pytest.approx(.6)
    assert positions(result)[2][0] == 0
    assert any(d["axis"] == "x" and d["reason"] == "ALIGNED" for d in decisions)
    assert positions(result)[5] == positions(plan)[5]


@pytest.mark.parametrize("second", [False, True])
def test_standalone_centers_but_disjoint_unequal_bands_can_align_at_minimum_protection(second):
    placements = [(0, 0, 96, 20)] + ([(0, 50, 75, 20)] if second else [])
    plan, sources = witness(placements, width=100, height=100)
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(15, 0))
    assert [p["x"] for p in result["sheets"][0]["pieces"]] == pytest.approx([1.5, 1.5] if second else [2])


def test_original_edge_to_internal_cut_can_increase_internal_length_safely():
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_effect
    plan, sources = three_widths_witness()
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(15, 0))
    before, after = [sheet_cut_line_effect(p["sheets"][0], .5) for p in (plan, result)]
    assert before["full_mm"] == after["full_mm"]
    assert after["internal_mm"] > before["internal_mm"] + 800


def test_atomic_xy_and_relative_swept_clearance_never_accept_partial_or_jump_moves():
    from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import _translate_group_moves_if_clear as move
    plan, _ = witness([(0, 0, 10, 10), (20, 20, 10, 10)], width=100, height=100)
    original = deepcopy(plan)
    assert move(plan, 0, (("x", (1,), 20),), .5, check_swept=True) is not None
    assert move(plan, 0, (("x", (1,), 20), ("y", (1,), 20)), .5, check_swept=True) is None
    assert move(plan, 0, (("x", (1,), 40), ("y", (1,), 40)), .5, check_swept=True) is None
    assert plan == original


def test_frozen_glass_contour_does_not_block_independent_regular_protection():
    plan, sources = witness([(0, 0, 75, 20), (80, 80, 15, 15)], width=100, height=100)
    plan["sheets"][0]["pieces"][1]["piece_type"] = sources[1]["piece_type"] = "Glass"
    plan["sheets"][0]["pieces"][1]["glass_hole_local_mm"] = [[20,20], [130,20], [130,130], [20,130]]
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(15, 0))
    assert positions(result)[1][0] == 1.5
    assert result["sheets"][0]["pieces"][1] == plan["sheets"][0]["pieces"][1]
    assert not validate_plan(result, sources, 100, 100, kerf_cm=.5)


@pytest.mark.parametrize("kind", ["OFFCUT", "Panel Saw"])
def test_offcut_and_panel_saw_are_conservative_noops(kind):
    plan, sources = three_widths_witness()
    if kind == "OFFCUT":
        plan["sheets"][0]["resource_kind"] = kind
    result, decisions = finish(plan, sources, machine_type=kind if kind == "Panel Saw" else "CNC Router")
    assert result is plan
    assert all(d["reason"] == "GEOMETRY_REJECTED" for d in decisions)


def test_dense_sheet_over_existing_64_piece_cap_skips_expensive_work(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import edge_protection as edge
    plan, sources = witness([((i % 13)*2.5, (i//13)*2.5, 1, 1) for i in range(65)])
    monkeypatch.setattr(edge, "sheet_cut_line_quality", lambda *a: pytest.fail("dense topology scan"))
    monkeypatch.setattr(edge, "validate_plan", lambda *a, **k: pytest.fail("dense full validation"))
    result, decisions = finish(plan, sources)
    assert result is plan
    assert {d["detail"] for d in decisions} == {"piece_limit"}


def test_expired_budget_skips_and_expiry_after_acceptance_retains_best_proven(monkeypatch):
    from types import SimpleNamespace
    from almdina_erp.almdina_erp.domain.cutting import edge_protection as edge
    plan, sources = three_widths_witness()
    assert finish(plan, sources, deadline_monotonic=0)[0] is plan
    expired = [False]
    validate = edge.validate_plan
    def expire(*args, **kwargs):
        result = validate(*args, **kwargs)
        if args[0]["sheets"][0]["pieces"][1]["x"] > 0:
            expired[0] = True
        return result
    monkeypatch.setattr(edge, "time", SimpleNamespace(monotonic=lambda: 100 if expired[0] else 1))
    monkeypatch.setattr(edge, "validate_plan", expire)
    diagnostics = {}
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(15, 0),
                       deadline_monotonic=10, diagnostics=diagnostics)
    # The early pass proves 15.5/15.5 mm before the later 15/16 mm alignment
    # alternative. Expiry must retain that exact completed basic candidate.
    assert positions(result)[2][0] == pytest.approx(1.55)
    assert positions(result)[1][0] == 1.5
    assert diagnostics["accepted"] == 1
    assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)


@pytest.mark.parametrize("factory", [staggered_witness, three_widths_witness])
@pytest.mark.parametrize("policy", [EdgeProtectionPolicy(), EdgeProtectionPolicy(15, 20), EdgeProtectionPolicy(0, 20)])
def test_final_placement_is_deterministic_idempotent_and_bounded(factory, policy):
    plan, sources = factory()
    diagnostics = {}
    first, _ = finish(plan, sources, policy=policy, diagnostics=diagnostics)
    second, _ = finish(first, sources, policy=policy)
    repeated, _ = finish(plan, sources, policy=policy)
    assert first == second == repeated
    assert diagnostics.get("tested", 0) <= 24
    assert not validate_plan(first, sources, 122, 244, kerf_cm=.5)


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("factory", [staggered_witness, three_widths_witness])
def test_mirrored_layouts_remain_valid_without_changing_piece_orientation(factory, axis):
    plan, sources = factory()
    size = "w" if axis == "x" else "h"
    for piece in plan["sheets"][0]["pieces"]:
        piece[axis] = plan["sheets"][0][size]-piece[axis]-piece[size]
    result, _ = finish(plan, sources)
    assert not validate_plan(result, sources, 122, 244, kerf_cm=.5)
    assert finish(result, sources)[0] == result
    for before, after in zip(plan["sheets"][0]["pieces"], result["sheets"][0]["pieces"], strict=True):
        assert {k:v for k,v in before.items() if k not in {"x","y"}} == {k:v for k,v in after.items() if k not in {"x","y"}}


def test_positive_mandatory_trim_is_counted_once_for_a_connected_chain():
    plan, sources = witness([(0,0,39.3,80),(39.8,0,39.3,80),(79.6,0,39.3,80)], trim=.5)
    result, _ = finish(plan, sources, policy=EdgeProtectionPolicy(15,0))
    assert result["sheets"][0]["pieces"][0]["x"] == pytest.approx(1.05)
    assert result["sheets"][0]["applied_trim_width_cm"] == .5
    assert not validate_plan(result,sources,121,243,kerf_cm=.5)


def _two_board_rows_and_plan():
    templates = [factory()[0]["sheets"][0] for factory in (staggered_witness, three_widths_witness)]
    placements = [p for sheet in templates for p in sheet["pieces"]]
    rows = tuple(dict(width_cm=p["w"], length_cm=p["h"], qty=1, allow_rotation=False,
                      piece_instance_id=f"geometry-integration-{i}") for i, p in enumerate(placements))
    sources = expand_piece_groups(list(rows))
    sheets, cursor = [], 0
    for sheet_no, template in enumerate(templates, 1):
        sheet = deepcopy(template)
        sheet["sheet_no"] = sheet_no
        sheet["pieces"] = [make_placed_piece(sources[cursor+i], p["x"], p["y"], p["w"], p["h"], False)
                           for i, p in enumerate(template["pieces"])]
        cursor += len(template["pieces"])
        sheets.append(sheet)
    used = sum(p["w"]*p["h"] for p in placements)/10000
    plan = enrich_plan_metrics(dict(method_key="MaxRects Best Short Side", sheets=sheets, unplaced=[],
        used_area_m2=used, total_board_area_m2=5.9536, waste_area_m2=5.9536-used),
        "MaxRects Best Short Side", "CNC Router", **METRICS)
    return rows, plan


def _integrated_outcome(*, native=False, seed_plans=(), search_round=0):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizeOrderPlanCommand, OptimizerOptions, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    rows, raw = _two_board_rows_and_plan()
    class WitnessPacking(DomainCuttingEngineAdapter):
        def optimize(self, *args, **kwargs):
            return deepcopy(raw)
    command = OptimizeOrderPlanCommand("geometry-integration", "unchanged", BoardGeometry(122,244,0,.5),
        OptimizerOptions("smart", "CNC Router", .5, 40, 30, 30, .09,
            alignment_search_budget_sec=.5, max_centerable_edge_gap_cm=7,
            edge_protection=EdgeProtectionPolicy(15,20)), rows,
        seed_plans=seed_plans, search_round=search_round)
    return optimize_order_plan(command, engine=DomainCuttingEngineAdapter() if native else WitnessPacking())


def test_two_boards_share_existing_global_trial_cap_and_both_get_an_opportunity():
    rows,plan = _two_board_rows_and_plan()
    diagnostics = {}
    result,_ = finish(plan,expand_piece_groups(list(rows)),diagnostics=diagnostics)
    assert 0 < diagnostics["tested"] <= 24
    assert len(diagnostics["sheets"]) == 2
    assert all(s["tested"] > 0 for s in diagnostics["sheets"])
    assert not validate_plan(result,expand_piece_groups(list(rows)),122,244,kerf_cm=.5)


def test_positive_policy_uses_one_shared_gallery_tail_instead_of_a_second_budget(monkeypatch):
    from types import SimpleNamespace
    from almdina_erp.tests.test_edge_protection import _command, _GalleryEngine
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as application
    from almdina_erp.almdina_erp.domain.cutting import edge_protection as edge
    times,deadlines = [100.0],[]
    monkeypatch.setattr(application,"time",SimpleNamespace(monotonic=lambda: times[0]))
    protect = edge.protect_plan_edges
    def capture(*args,**kwargs):
        deadlines.append(kwargs["deadline_monotonic"])
        assert kwargs["align_cut_lines"]
        times[0] += .01
        # Keep actual search/validation, with its own clock in the same frame.
        return protect(*args,**kwargs)
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda: times[0]))
    monkeypatch.setattr(edge,"protect_plan_edges",capture)
    outcome = application.optimize_order_plan(_command(alignment_search_budget_sec=.2),engine=_GalleryEngine())
    assert len(deadlines) == len(outcome.candidate_snapshots) == 5
    assert all(100 < d <= 100.2 for d in deadlines)
    assert all(s["validation"]["is_valid"] for s in outcome.candidate_snapshots)


def test_native_continue_gallery_and_preview_reload_preserve_proven_final_geometry():
    import json
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import CuttingPlanPreviewSession
    first = _integrated_outcome(native=True)
    continued = _integrated_outcome(native=True, seed_plans=first.search_seeds, search_round=1)
    for outcome in (first,continued):
        for snapshot in outcome.candidate_snapshots:
            assert snapshot["validation"]["is_valid"]
            assert snapshot["edge_protection_horizontal_mm"] == 15
            assert snapshot["edge_protection_vertical_mm"] == 20
            assert not validate_plan(snapshot,outcome.expanded_pieces,122,244,kerf_cm=.5)
        session = CuttingPlanPreviewSession("preview","order","user","source","revision","input","settings",
                                           {},outcome.snapshot,"now")
        restored = CuttingPlanPreviewSession.from_cache_value(json.loads(json.dumps(session.as_cache_value())))
        assert restored.snapshot == json.loads(json.dumps(outcome.snapshot))


@pytest.mark.parametrize("native", [False, True], ids=["staggered-witness", "real-native-packing"])
def test_calculation_snapshot_editor_projection_actual_dxf_and_strict_reimport(tmp_path, native):
    import json
    import os
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import ezdxf
    from almdina_erp.tests.test_edge_protection import _services
    _services()
    from almdina_erp.tests.test_glass_opening_nesting import _lifecycle_placed_row
    from almdina_erp.tests.test_cutter_center_paths import _import, _order, _piece, _layer_segments
    from almdina_erp.almdina_erp.application.cutting.board_editor_projection import project_board_editor
    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import sanitize_plan_snapshot
    from almdina_erp.almdina_erp.services.export_validation_service import _plan_to_export_snapshot
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors
    from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf
    outcome = _integrated_outcome(native=native)
    saved = sanitize_plan_snapshot(json.loads(json.dumps(outcome.snapshot)))
    assert saved["validation"]["is_valid"]
    if not native:
        assert [p["y"] for p in saved["sheets"][0]["pieces"][:3]] == pytest.approx([1.6,81.9,162.4])
        assert [p["x"] for p in saved["sheets"][1]["pieces"][1:]] == pytest.approx([1.5,41.3,81.1])
    before = deepcopy(saved)
    project_board_editor(saved)
    assert saved == before  # opening the editor never invokes rearrangement
    cutting_plan = SimpleNamespace(snapshot_json=json.dumps(saved),
        placed_pieces=[_lifecycle_placed_row(p,s["sheet_no"]) for s in saved["sheets"] for p in s["pieces"]],
        sources=[SimpleNamespace(sheet_no=s["sheet_no"], source_type="Full Board", remnant=None,
            board_item=None, material="", color="", thickness_mm=18, full_width_mm=1220,
            full_length_mm=2440, usable_width_mm=1220, usable_length_mm=2440,
            source_area_m2=2.9768) for s in saved["sheets"]],
        engine_version=saved["engine_version"], method_key=saved["method_key"], method_label=saved["method_label"],
        full_board_width_mm=1220, full_board_length_mm=2440, usable_board_width_mm=1220,
        usable_board_length_mm=2440, kerf_mm=5, trim_margin_mm=0, used_area_m2=saved["used_area_m2"],
        total_source_area_m2=saved["total_board_area_m2"], waste_area_m2=saved["waste_area_m2"],
        required_boards=outcome.required_boards)
    rebuilt = _plan_to_export_snapshot(cutting_plan)
    def geometry(plan):
        return sorted((s["sheet_no"],p["source_piece_no"],*(round(p[k],5) for k in ("x","y","w","h")))
                      for s in plan["sheets"] for p in s["pieces"])
    assert geometry(rebuilt) == geometry(saved)
    assert not _kerf_errors(rebuilt)
    cases = tmp_path/"geometry.json"
    cases.write_text(json.dumps([rebuilt]))
    subprocess.run(["node",str(Path(__file__).parents[1]/"tests/js/secure_dxf_topology_export.test.js")],
        check=True,capture_output=True,text=True,
        env=dict(os.environ,PERIMETER_CASES=str(cases),PERIMETER_OUTPUT_DIR=str(tmp_path)))
    path = tmp_path/"0.dxf"
    path.write_bytes(rebuild_autocad_dxf(path.read_bytes()))
    document = ezdxf.readfile(path)
    assert len(_layer_segments(document,"GEOMETRY")) == 11*4
    assert _layer_segments(document,"CUT_PATH")
    rows,_ = _two_board_rows_and_plan()
    order = _order([_piece(width_cm=r["width_cm"],length_cm=r["length_cm"],qty=1,
        cut_width_cm=r["width_cm"],cut_length_cm=r["length_cm"],
        piece_instance_id=r["piece_instance_id"]) for r in rows])
    imported = _import(str(path),order,kerf_mm=5,trim_mm=0)
    assert imported["saw_center_status"] == "Present"
    # Identical-size independent order rows can bind in either order on import;
    # assert their exact geometric multiset, without inventing copy provenance.
    def physical_geometry(plan):
        return sorted((s["sheet_no"],*(round(p[k],5) for k in ("x","y","w","h")))
                      for s in plan["sheets"] for p in s["pieces"])
    assert physical_geometry(imported) == physical_geometry(rebuilt)
