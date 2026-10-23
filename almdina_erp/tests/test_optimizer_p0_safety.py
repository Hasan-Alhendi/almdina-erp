"""P0 synthetic safety gate. Customer drawings are deliberately not fixtures."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import optimize_plan
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    expand_piece_groups,
    make_placed_piece,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "optimizer_p0_synthetic.json").read_text()
)
CASES = FIXTURE["cases"]
SETTINGS = FIXTURE["engine_settings"]
SHAPE_CASES = (
    "L_PAIR_NESTING",
    "L_QUAD_NESTING",
    "CLIPPED_CORNER_GROUP_NESTING",
)


def _requested(name):
    case = CASES[name]
    return expand_piece_groups(case["rows"]), case["board_cm"]


def _manual(name):
    case = CASES[name]
    pieces, board = _requested(name)
    placed = [
        make_placed_piece(piece, x, y, piece["width_cm"], piece["length_cm"], False)
        for piece, (x, y) in zip(pieces, case["one_board_coordinates_cm"], strict=True)
    ]
    return pieces, board, {"sheets": [{"sheet_no": 1, "pieces": placed}], "unplaced": []}


@pytest.mark.parametrize("name", CASES)
def test_current_optimizer_keeps_every_piece_and_a_valid_full_board_plan(name):
    pieces, (width, height) = _requested(name)
    plan = optimize_plan(
        pieces, width, height, SETTINGS["kerf_cm"],
        selected_mode=SETTINGS["selected_mode"],
        machine_type=SETTINGS["machine_type"],
        time_limit_sec=SETTINGS["time_limit_sec"],
    )
    assert not plan["unplaced"]
    placed = [piece for sheet in plan["sheets"] for piece in sheet["pieces"]]
    assert {piece["id"] for piece in placed} == {piece["id"] for piece in pieces}
    assert all(piece["resource_kind"] == "FULL_BOARD" for piece in placed)
    assert all(not piece["rotated"] for piece in placed)
    assert validate_plan(plan, pieces, width, height, kerf_cm=SETTINGS["kerf_cm"]) == []


@pytest.mark.parametrize("name", SHAPE_CASES)
def test_one_board_shape_reference_is_valid_with_actual_outlines_and_kerf(name):
    pieces, (width, height), plan = _manual(name)
    assert len(plan["sheets"]) == 1
    assert all(piece["resource_kind"] == "FULL_BOARD" for piece in plan["sheets"][0]["pieces"])
    assert validate_plan(plan, pieces, width, height, kerf_cm=SETTINGS["kerf_cm"]) == []


def test_shape_reference_rejects_kerf_violation_and_forbidden_rotation():
    pieces, (width, height), plan = _manual("L_PAIR_NESTING")
    too_close = deepcopy(plan)
    too_close["sheets"][0]["pieces"][1]["x"] = 4.1
    assert validate_plan(too_close, pieces, width, height, kerf_cm=0.2)
    rotated = deepcopy(plan)
    rotated["sheets"][0]["pieces"][0]["rotated"] = True
    assert validate_plan(rotated, pieces, width, height, kerf_cm=0.2)


def test_reference_rejects_duplicate_physical_identity_and_board_overflow():
    pieces, (width, height), plan = _manual("L_PAIR_NESTING")
    duplicated = deepcopy(plan)
    duplicated["sheets"][0]["pieces"][1]["id"] = pieces[0]["id"]
    assert validate_plan(duplicated, pieces, width, height, kerf_cm=0.2)
    outside = deepcopy(plan)
    outside["sheets"][0]["pieces"][1]["x"] = width
    assert validate_plan(outside, pieces, width, height, kerf_cm=0.2)


def test_glass_opening_host_is_explicit_and_not_a_shape_group_pocket():
    pieces, (width, height) = _requested("GLASS_OPENING_PRIORITY")
    plan = optimize_plan(pieces, width, height, 0.2, selected_mode="Auto")
    assert len(plan["sheets"]) == 1
    guests = [p for s in plan["sheets"] for p in s["pieces"] if p.get("glass_host_piece_id")]
    assert len(guests) == 1
    assert guests[0]["glass_host_piece_id"] == pieces[0]["id"]
    assert validate_plan(plan, pieces, width, height, kerf_cm=0.2) == []
