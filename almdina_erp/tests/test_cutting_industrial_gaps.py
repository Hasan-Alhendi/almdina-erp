"""Real geometry, exporter and packing witnesses for bounded industrial search."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess

import pytest

from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups, optimize_plan, validate_plan
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece


def clipped_rows(guest_type="Regular", **metadata):
    return [dict(piece_type="Clipped Corner", width_cm=20, length_cm=20, qty=4,
                 clipped_corner_position="Top Right", clipped_corner_width_cm=8,
                 clipped_corner_length_cm=8, allow_rotation=1),
            dict(piece_type=guest_type, width_cm=8, length_cm=3, qty=1,
                 allow_rotation=0, **metadata)]


def clipped_plan():
    pieces = expand_piece_groups(clipped_rows())
    plan = optimize_plan(pieces, 40.3, 40.3, .3, selected_mode="Auto Pro",
                         machine_type="CNC Router", time_limit_sec=2)
    assert len(plan["sheets"]) == 1
    assert not validate_plan(plan, pieces, 40.3, 40.3, kerf_cm=.3)
    return pieces, plan


def test_nonquarter_exception_requires_real_hosts_and_exact_rectangle():
    pieces, plan = clipped_plan()
    sheet = plan["sheets"][0]
    guest = next(p for p in sheet["pieces"] if p.get("placement_rotation_deg"))
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)
    for mutation in ("missing", "moved", "outline", "angle"):
        trial = deepcopy(plan)
        if mutation == "missing":
            trial["sheets"][0]["pieces"] = [deepcopy(guest)]
        elif mutation == "moved":
            trial["sheets"][0]["pieces"][0]["x"] += 10
        else:
            target = next(p for p in trial["sheets"][0]["pieces"] if p.get("placement_rotation_deg"))
            if mutation == "angle":
                target["placement_void_angle_deg"] = target["placement_rotation_deg"] = 33
            else:
                target["placement_outline_cm"][2] = [20, 20]
        assert validate_plan(trial, pieces, 40.3, 40.3, kerf_cm=.3)
        assert placement_permission_errors(trial, pieces, mirroring_allowed=False)


@pytest.mark.parametrize("field", ["extra_liner", "extra_back_groove", "extra_recessed_handle_cutout"])
def test_machining_guest_keeps_a_proven_quarter_turn(field):
    rows = clipped_rows(**{field: 1})
    pieces = expand_piece_groups(rows)
    plan = optimize_plan(pieces, 40.3, 40.3, .3, selected_mode="Auto Pro",
                         machine_type="CNC Router", time_limit_sec=1)
    guest = next(p for s in plan["sheets"] for p in s["pieces"] if p["id"] == pieces[-1]["id"])
    assert not guest.get("placement_outline_cm")
    assert guest[field] == 1
    assert not validate_plan(plan, pieces, 40.3, 40.3, kerf_cm=.3)


def export_real_js(plan, tmp_path, reject=False):
    source = tmp_path / "plan.json"
    output = tmp_path / "plan.dxf"
    source.write_text(json.dumps(plan))
    env = dict(os.environ, INDUSTRIAL_PLAN_IN=str(source), INDUSTRIAL_DXF_OUT=str(output))
    if reject:
        env["INDUSTRIAL_EXPECT_REJECT"] = "1"
    subprocess.run(["node", str(Path(__file__).parent / "js/secure_dxf_topology_export.test.js")],
                   env=env, check=True, capture_output=True, text=True, timeout=30)
    return output


def test_actual_js_angled_export_preserves_geometry_identity_and_import(tmp_path):
    import ezdxf
    from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
        ContourCandidate, ExpectedPieceEvidence, resolve_contour_ownership,
    )
    rows = clipped_rows()
    rows[0].update(width_cm=30, length_cm=24, clipped_corner_width_cm=12, clipped_corner_length_cm=6)
    rows[1].update(width_cm=10, length_cm=3)
    pieces = expand_piece_groups(rows)
    plan = optimize_plan(pieces,60.3,48.3,.3,selected_mode="MaxRects Best Short Side",machine_type="CNC Router",time_limit_sec=2,mirroring_allowed=True)
    assert len(plan["sheets"]) == 1
    plan.update(full_board_width_cm=60.3, full_board_length_cm=48.3, kerf_cm=.3, trim_cm=0)
    doc = ezdxf.readfile(export_real_js(plan, tmp_path))
    assert len(doc.modelspace().query('LINE[layer=="CUT_PATH"]')) > 0
    assert len(doc.modelspace().query('TEXT[layer=="TEXT"]')) == 5
    rings, pending = [], []
    for line in doc.modelspace().query('LINE[layer=="GEOMETRY"]'):
        a, b = line.dxf.start, line.dxf.end
        if not pending:
            pending.append((a.x, 483-a.y))
        endpoint = (b.x, 483-b.y)
        if math.dist(endpoint, pending[0]) < .001:
            rings.append(tuple(pending))
            pending = []
        else:
            pending.append(endpoint)
    assert not pending and len(rings) == 5
    actual = [material_outline_cm(p) for s in plan["sheets"] for p in s["pieces"]]
    for ring, outline in zip(rings, actual, strict=True):
        assert len(ring) == len(outline)
        assert all(any(math.dist(a,(b[0]*10,b[1]*10)) < .02 for b in outline) for a in ring)
    expected = tuple(ExpectedPieceEvidence(width=p["width_cm"]*10, height=p["length_cm"]*10,
        allow_rotation=bool(p["allow_rotation"]), piece_type=p["piece_type"],
        clipped_cut_width_mm=p.get("clipped_corner_width_cm",0)*10,
        clipped_cut_length_mm=p.get("clipped_corner_length_cm",0)*10,
        clipped_corner_position=p.get("clipped_corner_position","")) for p in pieces)
    resolved = resolve_contour_ownership(tuple(ContourCandidate(i,ring) for i,ring in enumerate(rings,1)),
                                         expected, dimension_tolerance=.2)
    assert len(resolved.parts) == 5
    assert {p.expected_piece_index for p in resolved.parts} == set(range(5))


@pytest.mark.parametrize("kind,metadata", [("Glass", {"glass_margin_mm": 5}),
    ("Regular", {"extra_liner": 1}), ("Regular", {"extra_back_groove": 1}),
    ("Regular", {"extra_recessed_handle_cutout": 1})])
def test_unsupported_angled_machining_cannot_silently_export(kind, metadata, tmp_path):
    pieces, plan = clipped_plan()
    guest = next(p for s in plan["sheets"] for p in s["pieces"] if p.get("placement_rotation_deg"))
    guest.update(piece_type=kind, glass_hole_local_mm=[[5,5],[75,5],[75,25],[5,25]], **metadata)
    plan.update(full_board_width_cm=40.3, full_board_length_cm=40.3, kerf_cm=.3, trim_cm=0)
    assert not export_real_js(plan, tmp_path, reject=True).exists()


def test_boundary_gap_candidate_does_not_pay_kerf_on_board_edges():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import _spot_on_sheet
    pieces = expand_piece_groups([dict(width_cm=10, length_cm=4, qty=2)])
    sheet = dict(sheet_no=1, w=10, h=8.3, pieces=[make_placed_piece(pieces[0],0,0,10,4,False)])
    spot = _spot_on_sheet(sheet, pieces[1], .3)
    assert spot is not None
    assert spot["x"] == 0 and spot["y"] == pytest.approx(4.3)
    trial = dict(sheets=[{**sheet, "pieces":[*sheet["pieces"], make_placed_piece(pieces[1],**{
        k:spot[k] for k in ("x","y","w","h","rotated")})]}], unplaced=[])
    assert not validate_plan(trial,pieces,10,8.3,kerf_cm=.3)
    assert _spot_on_sheet({**sheet,"h":8.29},pieces[1],.3) is None


def test_boundary_gap_eliminates_a_board_after_full_search_validation():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search
    from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
    pieces = expand_piece_groups([dict(width_cm=10,length_cm=4,qty=2)])
    plan = dict(sheets=[dict(sheet_no=i+1,w=10,h=8.3,pieces=[make_placed_piece(p,0,0,10,4,False)])
                        for i,p in enumerate(pieces)],unplaced=[])
    plan = enrich_plan_metrics(plan,"MaxRects Best Short Side","CNC Router",min_remnant_width_cm=1,
                              min_remnant_length_cm=1,min_remnant_area_m2=.0001)
    best = improve_plan_search(deepcopy(plan),pieces,10,8.3,.3,machine_type="CNC Router",time_limit_sec=1,
        min_remnant_width_cm=1,min_remnant_length_cm=1,min_remnant_area_m2=.0001)
    assert len(best["sheets"]) == 1
    assert not validate_plan(best,pieces,10,8.3,kerf_cm=.3)
    assert not placement_permission_errors(best,pieces,mirroring_allowed=False)


def test_pair_partition_improves_final_separable_offcut():
    rows=[dict(piece_type="L-Shaped Corner",width_cm=20,length_cm=20,qty=4,
        clipped_corner_position="Top Right",clipped_corner_width_cm=8,clipped_corner_length_cm=8,allow_rotation=1),
        dict(width_cm=30,length_cm=20,qty=2,allow_rotation=1)]
    pieces=expand_piece_groups(rows)
    plan=optimize_plan(pieces,60,50,.3,selected_mode="MaxRects Best Short Side",machine_type="CNC Router",time_limit_sec=2)
    assert len(plan["sheets"]) == 2
    assert plan["industrial_metrics"]["largest_reusable_free_area_m2"] >= .2
    assert not validate_plan(plan,pieces,60,50,kerf_cm=.3)


def glass_assignment_rows():
    return [dict(piece_type="Glass",width_cm=22,length_cm=12,glass_margin_mm=10,qty=1),
        dict(piece_type="Glass",width_cm=12,length_cm=12,glass_margin_mm=10,qty=1),
        dict(width_cm=9,length_cm=9,qty=1),dict(width_cm=18,length_cm=4,qty=1)]


def test_glass_opening_assignment_saves_a_final_board():
    pieces=expand_piece_groups(glass_assignment_rows())
    plan=optimize_plan(pieces,34.3,12,.3,selected_mode="Auto Pro",machine_type="CNC Router",time_limit_sec=2)
    assert len(plan["sheets"]) == 1
    assert len([p for s in plan["sheets"] for p in s["pieces"] if p.get("glass_host_piece_id")]) == 2
    assert not validate_plan(plan,pieces,34.3,12,kerf_cm=.3)
    assert not placement_permission_errors(plan,pieces,mirroring_allowed=False)


def test_same_board_compaction_converts_scattered_strips_to_one_offcut():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search
    from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
    pieces=expand_piece_groups([dict(width_cm=20,length_cm=100,qty=2)])
    plan=dict(sheets=[dict(sheet_no=1,w=100,h=100,pieces=[make_placed_piece(p,x,0,20,100,False)
        for p,x in zip(pieces,(20,60),strict=True)])],unplaced=[])
    metric=dict(min_remnant_width_cm=10,min_remnant_length_cm=10,min_remnant_area_m2=.01)
    plan=enrich_plan_metrics(plan,"MaxRects Best Short Side","CNC Router",**metric)
    saved=deepcopy(plan)
    best=improve_plan_search(plan,pieces,100,100,.3,machine_type="CNC Router",time_limit_sec=1,**metric)
    assert plan == saved
    assert len(best["sheets"]) == 1
    assert best["industrial_metrics"]["largest_reusable_free_area_m2"] >= .597
    assert not validate_plan(best,pieces,100,100,kerf_cm=.3)
    expired=improve_plan_search(plan,pieces,100,100,.3,machine_type="CNC Router",time_limit_sec=1,
                               deadline_monotonic=0,**metric)
    assert expired is plan


def test_contact_point_score_rewards_kerf_contact_and_selects_the_tight_candidate():
    from almdina_erp.almdina_erp.domain.cutting.strategies.maxrects import find_best_position_maxrects
    pieces=expand_piece_groups([dict(width_cm=10,length_cm=10,qty=2)])
    sheet=dict(w=100,h=100,pieces=[make_placed_piece(pieces[0],5,5,10,10,False)],free_rects=[
        dict(x=50,y=50,w=10,h=10),dict(x=15.3,y=5,w=10,h=10)])
    spot=find_best_position_maxrects(sheet,pieces[1],"contact_point",.3)
    assert spot["x"] == pytest.approx(15.3)
    plan=dict(sheets=[{**sheet,"sheet_no":1,"pieces":[*sheet["pieces"],make_placed_piece(pieces[1],
        spot["x"],spot["y"],10,10,False)]}],unplaced=[])
    assert not validate_plan(plan,pieces,100,100,kerf_cm=.3)


def test_rotation_fills_a_boundary_gap_without_changing_permission():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import _spot_on_sheet
    source=expand_piece_groups([dict(width_cm=9.7,length_cm=3.7,qty=1,allow_rotation=1)])[0]
    sheet=dict(w=10,h=10,pieces=[dict(x=0,y=0,w=6,h=10)])
    spot=_spot_on_sheet(sheet,source,.3)
    assert spot and spot["rotated"] and spot["x"] == pytest.approx(6.3)
    assert _spot_on_sheet(sheet,{**source,"allow_rotation":0},.3) is None


def test_compaction_moves_the_clipped_void_group_as_one_rigid_unit():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _translate_pieces
    from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
    pieces,small=clipped_plan()
    body=_translate_pieces(small["sheets"][0]["pieces"],30,30)
    plan=dict(sheets=[dict(sheet_no=1,w=120,h=120,pieces=body)],unplaced=[])
    metric=dict(min_remnant_width_cm=30,min_remnant_length_cm=30,min_remnant_area_m2=.09)
    plan=enrich_plan_metrics(plan,"MaxRects Best Short Side","CNC Router",**metric)
    best=improve_plan_search(plan,pieces,120,120,.3,machine_type="CNC Router",time_limit_sec=1,**metric)
    assert len(best["sheets"]) == 1
    assert best["industrial_rank"] < plan["industrial_rank"]
    before={p["id"]:p for p in body}
    after={p["id"]:p for p in best["sheets"][0]["pieces"]}
    shifts={(round(after[i]["x"]-before[i]["x"],5),round(after[i]["y"]-before[i]["y"],5)) for i in before}
    assert len(shifts) == 1
    for i in before:
        assert after[i].get("placement_rotation_deg") == before[i].get("placement_rotation_deg")
        assert after[i].get("corner_rotation_quarter_turns") == before[i].get("corner_rotation_quarter_turns")
    assert not validate_plan(best,pieces,120,120,kerf_cm=.3)
    assert not placement_permission_errors(best,pieces,mirroring_allowed=False)
