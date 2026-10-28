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

