"""Synthetic cross-board witnesses; no customer dimensions or reference poses."""
from copy import deepcopy
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import fragmentation_search as search
from almdina_erp.almdina_erp.domain.cutting.fragmentation import (
    envelope_profile, has_fragmentation_benefit, has_complete_identity)
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _placed_corner

METRICS = dict(min_remnant_width_cm=1, min_remnant_length_cm=1, min_remnant_area_m2=.0001)


def witness(pinned=False, rotation=False):
    rows = [dict(width_cm=2, length_cm=10, qty=4, allow_rotation=rotation,
                 piece_instance_id="synthetic-strip", piece_type="Regular")]
    if pinned:
        rows.append(dict(width_cm=2, length_cm=2, qty=2, allow_rotation=False,
            piece_instance_id="synthetic-corner", piece_type="L-Shaped Corner",
            clipped_corner_position="Top Right", clipped_corner_width_cm=1,
            clipped_corner_length_cm=1))
    sources = expand_piece_groups(rows)
    sheets = []
    for i in range(2):
        pieces = [make_placed_piece(p, x, 0, 2, 10, False)
                  for p, x in zip(sources[i*2:i*2+2], (5, 13))]
        if pinned:
            pieces.append(_placed_corner(sources[4+i], x_cm=0, y_cm=0,
                                         mirrored=False, turns=0))
        sheets.append(dict(w=20, h=10, sheet_no=i+1, pieces=pieces))
    plan = enrich_plan_metrics(dict(sheets=sheets, unplaced=[]), "MaxRects Best Area", "Auto", **METRICS)
    plan.update(kerf_cm=.5, machine_type="Auto")
    assert not validate_plan(plan, sources, 20, 10, kerf_cm=.5)
    return sources, plan


def run(sources, plan, **kwargs):
    return search.search_fragmentation([plan], sources, 20, 10, .5,
        deadline=time.monotonic()+2, machine_type="Auto", mirroring_allowed=False,
        metric_kwargs=METRICS, **kwargs)


@pytest.mark.parametrize("pinned,rotation", [(False, False), (True, False), (True, True)])
def test_cross_board_repair_improves_space_preserves_identity_and_pinned_shapes(pinned, rotation):
    sources, plan = witness(pinned, rotation)
    before = deepcopy((sources, plan))
    proposal, trace = run(sources, plan)
    assert proposal is not None and trace["improvements"] > 0
    assert len(proposal["sheets"]) <= len(plan["sheets"])
    assert has_fragmentation_benefit(envelope_profile(proposal, .5), envelope_profile(plan, .5))
    assert has_complete_identity(proposal, sources)
    assert not validate_plan(proposal, sources, 20, 10, kerf_cm=.5)
    assert not placement_permission_errors(proposal, sources, mirroring_allowed=False)
    old = {p["id"]: i for i, s in enumerate(plan["sheets"]) for p in s["pieces"]}
    new = {p["id"]: i for i, s in enumerate(proposal["sheets"]) for p in s["pieces"]}
    assert any(new[k] != old[k] for k in old)
    if pinned:
        for index in range(2):
            assert proposal["sheets"][index]["pieces"][0] == plan["sheets"][index]["pieces"][-1]
    assert trace["attempts"] <= 96 and len(trace["events"]) <= 24
    assert (sources, plan) == before


@pytest.mark.parametrize("marker", ["source_offcut", "sheet_offcut", "identity", "special"])
def test_unproven_resources_identity_or_outline_never_reach_repair(monkeypatch, marker):
    sources, plan = witness()
    if marker == "source_offcut":
        sources[0]["resource_kind"] = "OFFCUT"
    elif marker == "sheet_offcut":
        plan["sheets"][0]["resource_kind"] = "OFFCUT"
    elif marker == "identity":
        plan["sheets"][0]["pieces"][0]["piece_instance_id"] = "wrong-copy"
    else:
        plan["sheets"][0]["pieces"][0]["piece_type"] = "Special"
    monkeypatch.setattr(search, "_repair", lambda *a, **kw: pytest.fail("Unsafe repair"))
    proposal, trace = run(sources, plan)
    assert proposal is None and trace["stop"] == "unsupported_cohort"


def test_expired_work_cannot_start_and_failed_final_gate_never_returns_proposal(monkeypatch):
    sources, plan = witness()
    with monkeypatch.context() as patch:
        patch.setattr(search, "_plain", lambda *a: pytest.fail("Expired work"))
        proposal, trace = search.search_fragmentation([plan], sources, 20, 10, .5,
            deadline=time.monotonic()-1, machine_type="Auto", mirroring_allowed=False,
            metric_kwargs=METRICS)
        assert proposal is None and trace["stop"] == "expired"
    monkeypatch.setattr(search, "_valid", lambda *a, **kw: None)
    proposal, trace = run(sources, plan)
    assert proposal is None and trace["rejections"]["final_validation_failed"] == 1


def test_missing_enabled_machining_details_cannot_publish_a_side_proposal():
    sources, plan = witness()
    sources[0]["extra_liner"] = 1
    plan["sheets"][0]["pieces"][0]["extra_liner"] = 1
    proposal, trace = run(sources, plan)
    assert proposal is None
    assert trace["rejections"].get("unproven_machining_parameters") == 1
