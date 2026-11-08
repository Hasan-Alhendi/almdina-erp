"""DXF machining round-trip when edge deduction and layer bits differ.

Proved before the fix, on a 600 mm wide door and a 3 mm saw:

- A left-side path on the cut blank and on the finished blank is the same
  path. Max point distance is 0 mm. Deducting the left band does not move
  the left reference edge, which stays at x = 0.
- A right-side path moves by the whole width deduction: 1 mm for a 1 mm
  band, and 3 mm when the bands are 1 mm and 2 mm. The public failure still
  says ``0.150``, which is the saw radius in centimetres, not that shift.
- A handle path cut with an 8 mm or 10 mm bit and checked with the 3 mm saw
  fails as ``coverage_gap`` with expected side ``edge_long_left``. The
  presenter shows that side as يسار.
- The client toolpath and ``liner_toolpath_mm`` match to 0 mm, so export and
  the domain generator already share one cut-frame reference.

The strict import was measuring every layer with the saw kerf. A recorded
layer bit is now the measurement diameter. A missing bit still inherits the
saw, and a path drawn on the finished frame is still rejected.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    liner_toolpath_mm,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.services import dxf_import_service as legacy
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf

KERF_MM = 3.0
LINER_BIT_MM = 6.0
HANDLE_BIT_MM = 10.0
LAYER_BITS = {
    "liner_tool_diameter_mm": LINER_BIT_MM,
    "handle_recess_tool_diameter_mm": HANDLE_BIT_MM,
    "rear_groove_tool_diameter_mm": KERF_MM,
}


def _settings(*, deduct: bool) -> PlanSettings:
    return PlanSettings("Auto", "CNC", 5, KERF_MM, 0, deduct_edge_thickness=deduct)


def _row(
    index: int,
    *,
    finished: tuple[float, float],
    cut: tuple[float, float],
    kind: str,
    side: str,
    offset_cm: float,
    width_cm: float,
    start_cm: float = 0,
    length_cm: float = 0,
):
    width, length = finished
    cut_width, cut_length = cut
    row = SimpleNamespace(
        name=f"row-{index}",
        piece_instance_id=f"dxf-roundtrip:{index}",
        piece_type="Regular",
        width_cm=width,
        length_cm=length,
        cut_width_cm=cut_width,
        cut_length_cm=cut_length,
        qty=1,
        allow_rotation=0,
        default_edge_type="",
        extra_liner=0,
        extra_back_groove=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        extra_full_door_double=0,
    )
    if kind == "liner":
        row.extra_liner = 1
        row.liner_reference_side = side
        row.liner_offset_cm = offset_cm
        row.liner_width_cm = width_cm
        row.liner_start_cm = start_cm
        row.liner_length_cm = length_cm
    else:
        row.extra_recessed_handle_cutout = 1
        row.recessed_handle_reference_side = side
        row.recessed_handle_offset_cm = offset_cm
        row.recessed_handle_width_cm = width_cm
        row.recessed_handle_start_cm = start_cm
        row.recessed_handle_length_cm = length_cm
    return row


def _order(rows, *, deduct: bool):
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=KERF_MM,
        default_edge_type="",
        deduct_edge_thickness=deduct,
        pieces=rows,
    )


def _place(origin, point):
    ox, oy = origin
    x, y = point
    return (ox + x, oy - y)


def _write(path, doors):
    document = ezdxf.new("R2010")
    model = document.modelspace()
    model.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    for door in doors:
        width = door["cut"][0] * 10
        height = door["cut"][1] * 10
        origin = door["origin"]
        outline = [(0, 0), (width, 0), (width, height), (0, height)]
        model.add_lwpolyline(
            [_place(origin, point) for point in outline],
            close=True,
            dxfattribs={"layer": "GEOMETRY"},
        )
        piece = LinerPiece("Regular", door["frame"][0], door["frame"][1])
        toolpath = liner_toolpath_mm(
            piece,
            door["side"],
            door["offset_cm"],
            door["width_cm"],
            door["bit_mm"],
            door.get("start_cm", 0),
            door.get("length_cm", 0),
        )
        if door.get("shift_x_mm"):
            toolpath = [(x + door["shift_x_mm"], y) for x, y in toolpath]
        layer = "Liner" if door["kind"] == "liner" else "Handle Recess"
        model.add_lwpolyline(
            [_place(origin, point) for point in toolpath],
            dxfattribs={"layer": layer},
        )
    document.saveas(path)


def _parse(path, order, *, deduct: bool, diameters):
    with patch.object(legacy.frappe, "get_site_path", return_value=str(path)):
        return parse_production_dxf(
            "/private/files/edge-deduction.dxf",
            order,
            settings=_settings(deduct=deduct),
            tool_diameters=diameters,
        )


def _issues(path, order, *, deduct: bool, diameters):
    with pytest.raises(DxfImportError) as caught:
        _parse(path, order, deduct=deduct, diameters=diameters)
    return {
        issue.target.source_piece_no: issue
        for issue in caught.value.issues
        if issue.target.source_piece_no
    }


DEDUCTED_DOORS = (
    {
        "finished": (60.0, 80.0),
        "cut": (59.9, 80.0),
        "kind": "liner",
        "side": "edge_long_left",
        "offset_cm": 2.0,
        "width_cm": 1.8,
        "bit_mm": LINER_BIT_MM,
        "origin": (20, 2300),
    },
    {
        "finished": (55.0, 70.0),
        "cut": (54.9, 70.0),
        "kind": "handle",
        "side": "edge_long_left",
        "offset_cm": 1.5,
        "width_cm": 3.8,
        "start_cm": 8.0,
        "length_cm": 18.0,
        "bit_mm": HANDLE_BIT_MM,
        "origin": (650, 2300),
    },
    {
        "finished": (60.0, 75.0),
        "cut": (59.7, 75.0),
        "kind": "liner",
        "side": "edge_long_right",
        "offset_cm": 2.0,
        "width_cm": 1.8,
        "bit_mm": LINER_BIT_MM,
        "origin": (20, 1350),
    },
    {
        "finished": (48.0, 40.0),
        "cut": (47.8, 40.0),
        "kind": "liner",
        "side": "edge_width_top",
        "offset_cm": 1.0,
        "width_cm": 1.2,
        "bit_mm": LINER_BIT_MM,
        "origin": (650, 1350),
    },
)


def _rows_for(doors):
    return [
        _row(
            index,
            finished=door["finished"],
            cut=door["cut"],
            kind=door["kind"],
            side=door["side"],
            offset_cm=door["offset_cm"],
            width_cm=door["width_cm"],
            start_cm=door.get("start_cm", 0),
            length_cm=door.get("length_cm", 0),
        )
        for index, door in enumerate(doors, start=1)
    ]


def _drawn(doors, *, frame_key):
    drawn = []
    for door in doors:
        item = dict(door)
        item["frame"] = door[frame_key]
        drawn.append(item)
    return drawn


def _single(tmp_path, door, name):
    drawn = dict(door)
    drawn["frame"] = door["cut"]
    drawn["origin"] = (40, 2000)
    path = tmp_path / name
    _write(path, [drawn])
    return path, _order(_rows_for((door,)), deduct=True)


def test_saw_kerf_measurement_reproduces_both_reported_messages(tmp_path):
    liner_path, liner_order = _single(tmp_path, DEDUCTED_DOORS[0], "liner-kerf.dxf")
    liner = _issues(liner_path, liner_order, deduct=True, diameters=None)[1]
    assert liner.code == "LINER_SHAPE_MISMATCH"
    assert liner.params["reason_code"] == "extension_short"
    assert liner.params["expected"] == "0.150"

    handle_path, handle_order = _single(tmp_path, DEDUCTED_DOORS[1], "handle-kerf.dxf")
    handle = _issues(handle_path, handle_order, deduct=True, diameters=None)[1]
    assert handle.code == "LINER_SHAPE_MISMATCH"
    assert handle.params["reason_code"] == "coverage_gap"
    assert handle.params["expected"] == "edge_long_left"
    assert handle.params["overlay_kind"] == "recessed_handle_cutout"


def test_recorded_layer_bits_round_trip_when_deduction_is_on(tmp_path):
    path = tmp_path / "deduct-on.dxf"
    _write(path, _drawn(DEDUCTED_DOORS, frame_key="cut"))
    order = _order(_rows_for(DEDUCTED_DOORS), deduct=True)
    snapshot = _parse(path, order, deduct=True, diameters=LAYER_BITS)
    pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
    assert {(piece["source_piece_no"], piece["cut_width_cm"]) for piece in pieces} == {
        (1, 59.9),
        (2, 54.9),
        (3, 59.7),
        (4, 47.8),
    }
    assert all(piece["overlays"] for piece in pieces)


def test_deduct_off_round_trip_uses_the_finished_cut_and_rejects_a_moved_path(tmp_path):
    door = {
        "finished": (60.0, 80.0),
        "cut": (60.0, 80.0),
        "kind": "liner",
        "side": "edge_long_right",
        "offset_cm": 2.0,
        "width_cm": 1.8,
        "bit_mm": LINER_BIT_MM,
        "origin": (40, 2200),
    }
    path = tmp_path / "deduct-off.dxf"
    _write(path, _drawn((door,), frame_key="cut"))
    order = _order(_rows_for((door,)), deduct=False)
    snapshot = _parse(path, order, deduct=False, diameters=LAYER_BITS)
    piece = snapshot["sheets"][0]["pieces"][0]
    assert piece["cut_width_cm"] == 60
    assert piece["overlays"][0]["kind"] == "liner"

    shifted = dict(door)
    shifted["frame"] = door["cut"]
    shifted["shift_x_mm"] = 4
    wrong = tmp_path / "shifted.dxf"
    _write(wrong, [shifted])
    issues = _issues(wrong, order, deduct=False, diameters=LAYER_BITS)
    assert issues[1].code == "LINER_SHAPE_MISMATCH"


def test_path_drawn_on_the_finished_frame_is_still_rejected(tmp_path):
    door = DEDUCTED_DOORS[2]
    drawn = dict(door)
    drawn["frame"] = door["finished"]
    path = tmp_path / "finished-frame.dxf"
    _write(path, [drawn])
    order = _order(_rows_for((door,)), deduct=True)
    issues = _issues(path, order, deduct=True, diameters=LAYER_BITS)
    assert issues[1].code == "LINER_OFFSET_MISMATCH"
    assert issues[1].params["reason_code"] == "tool_overcut"
    assert issues[1].params["expected"] == "2.000"


def test_a_plan_without_layer_bits_keeps_measuring_with_the_saw(tmp_path):
    door = dict(DEDUCTED_DOORS[0])
    door["bit_mm"] = KERF_MM
    door["frame"] = door["cut"]
    path = tmp_path / "shared-saw.dxf"
    _write(path, [door])
    order = _order(_rows_for((DEDUCTED_DOORS[0],)), deduct=True)
    snapshot = _parse(path, order, deduct=True, diameters=None)
    piece = snapshot["sheets"][0]["pieces"][0]
    assert piece["source_piece_no"] == 1
    assert piece["cut_width_cm"] == 59.9
    assert piece["overlays"][0]["kind"] == "liner"
