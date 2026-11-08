"""DXF round-trip for an L notch and a symmetric clipped corner.

The exported door 5 contour was 400 mm square with notch bites of 100 mm and
99 mm. The 1 mm came from the client notch formula subtracting a selected band
while the plan's deduction flag was off. The clipped door is a 600 mm square
with a 300 mm isosceles cut, so an unordered contour matches both the saved
orientation and one mirror. A consistently directed boundary is the evidence
that selects the orientation the file actually stores.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.corner_contour_rotation import (
    _corner_polygon_mm,
    _transform_polygon,
    measure_l_remainings_cm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import consistent_directed_rings
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.services.dxf_export_service import _export_deduct_edge_thickness
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf

KERF_MM = 3.0


def _settings(*, deduct: bool) -> PlanSettings:
    return PlanSettings("Auto", "CNC", 5, KERF_MM, 0, deduct_edge_thickness=deduct)


def _profiles(names):
    thickness = {"THICK": 2}
    return {
        str(name): {
            "name": str(name),
            "thickness_mm": thickness.get(str(name), 1),
            "disabled": 0,
        }
        for name in names
    }


def _row(
    *,
    piece_type: str,
    finished: tuple[float, float],
    cut: tuple[float, float],
    position: str,
    notch: tuple[float, float],
    edges: dict[str, int],
    edge_break: int = 0,
):
    width, length = finished
    cut_width, cut_length = cut
    notch_width, notch_length = notch
    return SimpleNamespace(
        piece_instance_id="roundtrip:1",
        piece_type=piece_type,
        width_cm=width,
        length_cm=length,
        cut_width_cm=cut_width,
        cut_length_cm=cut_length,
        qty=1,
        allow_rotation=1,
        clipped_corner_position=position,
        clipped_corner_width_cm=notch_width,
        clipped_corner_length_cm=notch_length,
        edge_long_right=edges.get("long_right", 0),
        edge_long_left=edges.get("long_left", 0),
        edge_width_top=edges.get("width_top", 0),
        edge_width_bottom=edges.get("width_bottom", 0),
        edge_long_right_type_override="",
        edge_long_left_type_override="",
        edge_width_top_type_override="",
        edge_width_bottom_type_override="",
        edge_break=edge_break,
        edge_break_only=0,
        edge_type="PVC" if edge_break else "",
        extra_liner=0,
        extra_back_groove=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        extra_full_door_double=0,
        liner_reference_side="",
        liner_offset_cm=0,
        liner_width_cm=0,
        liner_start_cm=0,
        liner_length_cm=0,
        liner_specs_json="",
    )


def _order(row, *, allow_piece_mirroring: int = 0):
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=KERF_MM,
        default_edge_type="PVC",
        allow_piece_mirroring=allow_piece_mirroring,
        pieces=[row],
    )


def _place(origin, point):
    ox, oy = origin
    return (ox + point[0], oy - point[1])


def _write(path, polygon, *, reverse=False, flip_index=None):
    document = ezdxf.new("R2010")
    model = document.modelspace()
    model.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    points = [_place((80, 2200), point) for point in polygon]
    if reverse:
        points = list(reversed(points))
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        if flip_index == index:
            start, end = end, start
        model.add_line(start, end, dxfattribs={"layer": "GEOMETRY"})
    document.saveas(path)


def _polygon(piece_type, width_mm, height_mm, cut_x_mm, cut_y_mm):
    polygon = _corner_polygon_mm(
        piece_type=piece_type,
        position="Top Right",
        width_mm=width_mm,
        height_mm=height_mm,
        cut_x_mm=cut_x_mm,
        cut_y_mm=cut_y_mm,
    )
    assert polygon is not None
    return polygon


def _parse(path, order, *, deduct: bool):
    with (
        patch(
            "almdina_erp.almdina_erp.services.piece_cut_dimension_service._default_profile_loader",
            side_effect=_profiles,
        ),
        patch(
            "almdina_erp.almdina_erp.services.dxf_import_service.frappe.get_site_path",
            return_value=str(path),
        ),
    ):
        return parse_production_dxf(
            "/private/files/corner-roundtrip.dxf",
            order,
            settings=_settings(deduct=deduct),
        )


def _issues(path, order, *, deduct: bool):
    with pytest.raises(DxfImportError) as caught:
        _parse(path, order, deduct=deduct)
    return caught.value.issues


def _piece(snapshot):
    return snapshot["sheets"][0]["pieces"][0]


def test_export_flag_keeps_explicit_zero_and_missing_on():
    assert _export_deduct_edge_thickness(0) == 0
    assert _export_deduct_edge_thickness(False) == 0
    assert _export_deduct_edge_thickness("0") == 0
    assert _export_deduct_edge_thickness(None) == 1
    assert _export_deduct_edge_thickness(1) == 1


def test_directed_cycle_requires_every_segment_to_agree():
    square = [((0, 0), (10, 0)), ((10, 0), (10, 10)), ((10, 10), (0, 10)), ((0, 10), (0, 0))]
    assert len(consistent_directed_rings(square, 0.05)) == 1
    broken = [((0, 0), (10, 0)), ((10, 10), (10, 0)), ((10, 10), (0, 10)), ((0, 10), (0, 0))]
    assert consistent_directed_rings(broken, 0.05) == []


def test_deduct_off_l_notch_round_trips_with_outer_or_inner_band(tmp_path):
    polygon = _polygon("L-Shaped Corner", 400, 400, 100, 100)
    for edges, edge_break in (
        ({}, 0),
        ({"long_right": 1}, 0),
        ({"width_top": 1, "long_left": 1}, 1),
    ):
        path = tmp_path / f"l-off-{edge_break}-{len(edges)}.dxf"
        _write(path, polygon)
        row = _row(
            piece_type="L-Shaped Corner",
            finished=(40, 40),
            cut=(40, 40),
            position="Top Right",
            notch=(10, 10),
            edges=edges,
            edge_break=edge_break,
        )
        snapshot = _parse(path, _order(row), deduct=False)
        piece = _piece(snapshot)
        assert "directed_contour_mm" not in piece
        assert measure_l_remainings_cm(piece["geometry"]["outer"], rotated=False) == pytest.approx((30, 30))
        if edges or edge_break:
            assert piece["corner_rotation_quarter_turns"] == 0
            assert piece["corner_mirrored"] == 0


def test_deduct_on_l_notch_follows_each_selected_thickness(tmp_path):
    polygon = _polygon("L-Shaped Corner", 399, 400, 99, 100)
    path = tmp_path / "l-on.dxf"
    _write(path, polygon)
    row = _row(
        piece_type="L-Shaped Corner",
        finished=(40, 40),
        cut=(39.9, 40),
        position="Top Right",
        notch=(10, 10),
        edges={"long_right": 1},
    )
    snapshot = _parse(path, _order(row), deduct=True)
    piece = _piece(snapshot)
    assert measure_l_remainings_cm(piece["geometry"]["outer"], rotated=False) == pytest.approx((30, 30))

    unequal = _polygon("L-Shaped Corner", 398, 399, 98, 99)
    unequal_path = tmp_path / "l-unequal.dxf"
    _write(unequal_path, unequal)
    # 2 mm on the notch width side and 1 mm on the notch length side.
    unequal_row = _row(
        piece_type="L-Shaped Corner",
        finished=(40, 40),
        cut=(39.8, 39.9),
        position="Top Right",
        notch=(10, 10),
        edges={"long_right": 1, "width_top": 1},
    )
    unequal_row.edge_long_right_type_override = "THICK"
    unequal_snapshot = _parse(unequal_path, _order(unequal_row), deduct=True)
    assert measure_l_remainings_cm(
        _piece(unequal_snapshot)["geometry"]["outer"],
        rotated=False,
    ) == pytest.approx((30, 30))


def test_one_millimetre_l_notch_is_still_rejected(tmp_path):
    polygon = _polygon("L-Shaped Corner", 400, 400, 100, 99)
    path = tmp_path / "l-99.dxf"
    _write(path, polygon)
    row = _row(
        piece_type="L-Shaped Corner",
        finished=(40, 40),
        cut=(40, 40),
        position="Top Right",
        notch=(10, 10),
        edges={"long_right": 1},
    )
    issues = _issues(path, _order(row), deduct=False)
    assert [item.code for item in issues] == ["L_CORNER_NOTCH_MISMATCH"]
    assert Decimal(issues[0].params["axes"][0]["delta_mm"]) != 0


def test_directed_clipped_corner_keeps_the_banded_side(tmp_path):
    polygon = _polygon("Clipped Corner", 600, 600, 300, 300)
    path = tmp_path / "clip.dxf"
    _write(path, polygon)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1},
    )
    snapshot = _parse(path, _order(row), deduct=False)
    piece = _piece(snapshot)
    assert piece["corner_rotation_quarter_turns"] == 0
    assert piece["corner_mirrored"] == 0
    assert piece["edge_width_top"] == 1
    assert piece["edge_long_right"] == 0


def test_clipped_corner_without_a_direction_stays_ambiguous(tmp_path):
    polygon = _polygon("Clipped Corner", 600, 600, 300, 300)
    path = tmp_path / "clip-ambiguous.dxf"
    _write(path, polygon, flip_index=1)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1},
    )
    issues = _issues(path, _order(row), deduct=False)
    assert [item.code for item in issues] == ["CORNER_EDGE_UNRESOLVED"]
    assert issues[0].params["reason"] == "ambiguous"


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_directed_clipped_corner_round_trips_each_quarter_turn(tmp_path, turns):
    polygon = _transform_polygon(
        _polygon("Clipped Corner", 600, 600, 300, 300),
        mirrored=False,
        quarter_turns=turns,
        width=600,
        height=600,
    )
    path = tmp_path / f"clip-turn-{turns}.dxf"
    _write(path, polygon)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1, "long_left": 1},
    )
    piece = _piece(_parse(path, _order(row), deduct=False))
    assert piece["corner_rotation_quarter_turns"] == turns
    assert piece["corner_mirrored"] == 0
    assert piece["edge_width_top"] == 1
    assert piece["edge_long_left"] == 1
    assert piece["edge_long_right"] == 0


def test_equal_swapped_bands_stay_equivalent_without_direction(tmp_path):
    polygon = _polygon("Clipped Corner", 600, 600, 300, 300)
    path = tmp_path / "clip-equivalent.dxf"
    _write(path, polygon, flip_index=1)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1, "long_right": 1},
    )
    piece = _piece(_parse(path, _order(row), deduct=False))
    assert piece["corner_rotation_quarter_turns"] == 0
    assert piece["corner_mirrored"] == 0


def test_different_band_types_need_the_directed_proof(tmp_path):
    polygon = _polygon("Clipped Corner", 600, 600, 300, 300)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1, "long_right": 1},
    )
    row.edge_long_right_type_override = "THICK"
    proven = tmp_path / "clip-types.dxf"
    _write(proven, polygon)
    piece = _piece(_parse(proven, _order(row), deduct=False))
    assert piece["corner_rotation_quarter_turns"] == 0
    assert piece["corner_mirrored"] == 0
    assert piece["edge_width_top"] == 1
    assert piece["edge_long_right"] == 1

    ambiguous = tmp_path / "clip-types-ambiguous.dxf"
    _write(ambiguous, polygon, flip_index=2)
    issues = _issues(ambiguous, _order(row), deduct=False)
    assert [item.code for item in issues] == ["CORNER_EDGE_UNRESOLVED"]
    assert issues[0].params["reason"] == "ambiguous"


def test_allowed_mirror_keeps_the_banded_side(tmp_path):
    polygon = _transform_polygon(
        _polygon("Clipped Corner", 600, 600, 300, 300),
        mirrored=True,
        quarter_turns=0,
        width=600,
        height=600,
    )
    path = tmp_path / "clip-allowed-mirror.dxf"
    _write(path, polygon)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1},
    )
    piece = _piece(_parse(path, _order(row, allow_piece_mirroring=1), deduct=False))
    assert piece["corner_mirrored"] == 1
    assert piece["corner_rotation_quarter_turns"] == 0
    assert piece["edge_width_top"] == 1
    assert piece["edge_long_right"] == 0


def test_reversed_clipped_direction_is_a_forbidden_mirror(tmp_path):
    polygon = _polygon("Clipped Corner", 600, 600, 300, 300)
    path = tmp_path / "clip-mirror.dxf"
    _write(path, polygon, reverse=True)
    row = _row(
        piece_type="Clipped Corner",
        finished=(60, 60),
        cut=(60, 60),
        position="Top Right",
        notch=(30, 30),
        edges={"width_top": 1},
    )
    issues = _issues(path, _order(row), deduct=False)
    assert [item.code for item in issues] == ["FORBIDDEN_MIRRORING"]
