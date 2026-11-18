"""Individual glass margins and glass-door liner safety."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.almdina_erp.application.orders.plan_payloads import (
    PlanPieceInput,
    _plan_piece_payload,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import parse_geometry_mm
from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import (
    cut_insets_mm,
    glass_hole_ring_mm,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    liner_region_polygon_mm,
    merged_liner_toolpaths_mm,
    transform_point,
    validation_code,
)
from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import (
    freeze_geometry_piece,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    ExtraAddonError,
    ExtraAddonPieceInput,
    ExtraAddonRates,
    calculate_extra_addon_pricing,
)
from almdina_erp.almdina_erp.domain.orders.glass_margins import (
    MODE_ALL,
    MODE_INDIVIDUAL,
    GlassSideMargins,
    cut_frame_thickness_mm,
    fingerprint_glass_fields,
    normalized_glass_margin_fields,
    opening_from_margins,
    resolve_glass_side_margins,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    PieceGeometry,
    geometry_changed,
    validate_glass_opening,
)
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf


RATES = ExtraAddonRates(
    double_usd=4,
    full_door_double_usd=6,
    liner_usd=2.5,
    back_groove_usd=3,
    recessed_handle_cutout_usd=1.25,
)
SIDES = GlassSideMargins(
    mode=MODE_INDIVIDUAL,
    top_mm=Decimal("50"),
    bottom_mm=Decimal("80"),
    right_mm=Decimal("40"),
    left_mm=Decimal("60"),
)


def _required_piece(**extra):
    piece = {
        "piece_instance_id": "door-1",
        "width_cm": 100.0,
        "length_cm": 100.0,
        "final_width_cm": 100.0,
        "final_length_cm": 100.0,
        "qty": 1,
        "allow_rotation": 0,
        "edge_long_right": 0,
        "edge_long_left": 0,
        "edge_width_top": 0,
        "edge_width_bottom": 0,
        "edge_break": 0,
        "edge_break_only": 0,
        "piece_type": "Glass",
        "extra_double": 0,
        "extra_double_reference_sides": "",
        "clipped_corner_position": "",
        "clipped_corner_width_cm": 0.0,
        "clipped_corner_length_cm": 0.0,
        "special_shape_geometry_json": "",
        "liner_specs_json": "",
        "edge_long_thickness_mm": 0.0,
        "edge_width_thickness_mm": 0.0,
    }
    piece.update(extra)
    return piece


def test_uniform_margin_stays_centered_and_legacy_rows_keep_it():
    opening = validate_glass_opening(
        outer_width_cm=Decimal("100"),
        outer_length_cm=Decimal("100"),
        glass_margin_mm=65,
    )
    assert opening.opening_width_mm == Decimal("870")
    assert opening.origin_x_mm == Decimal("65")
    assert opening.origin_y_mm == Decimal("65")

    legacy = resolve_glass_side_margins({
        "piece_type": "Glass",
        "glass_margin_mm": 65,
    })
    assert legacy is not None
    assert legacy.mode == MODE_ALL
    assert legacy.uniform_mm == Decimal("65")
    assert fingerprint_glass_fields({
        "piece_type": "Glass",
        "glass_margin_mm": 65,
    }) == {"glass_margin_mm": 65.0}
    stored = normalized_glass_margin_fields({
        "piece_type": "Glass",
        "glass_margin_mm": 65,
    })
    assert stored["glass_margin_mode"] == MODE_ALL
    assert stored["glass_margin_top_mm"] == 0
    reopened = resolve_glass_side_margins({**stored, "piece_type": "Glass"})
    assert reopened.uniform_mm == Decimal("65")


def test_individual_margins_place_the_opening_from_the_top_left():
    opening = opening_from_margins(
        SIDES,
        outer_width_cm=Decimal("100"),
        outer_length_cm=Decimal("100"),
    )
    assert opening["opening_width_mm"] == Decimal("900")
    assert opening["opening_length_mm"] == Decimal("870")
    assert opening["origin_x_mm"] == Decimal("60")
    assert opening["origin_y_mm"] == Decimal("50")
    ring = glass_hole_ring_mm(
        cut_width_mm=1000,
        cut_length_mm=1000,
        side_margins=SIDES,
    )
    assert ring[0] == (60.0, 50.0)
    assert ring[2] == (960.0, 920.0)


def test_saving_individual_margins_reopens_the_same_opening():
    stored = normalized_glass_margin_fields({
        "piece_type": "Glass",
        "glass_margin_mode": MODE_INDIVIDUAL,
        "glass_margin_top_mm": 50,
        "glass_margin_bottom_mm": 80,
        "glass_margin_right_mm": 40,
        "glass_margin_left_mm": 60,
    })
    assert stored["glass_margin_mm"] == 0
    reopened = validate_glass_opening(
        outer_width_cm=100,
        outer_length_cm=100,
        source={**stored, "piece_type": "Glass"},
    )
    assert reopened.opening_width_mm == Decimal("900")
    assert reopened.opening_length_mm == Decimal("870")
    assert geometry_changed(
        PieceGeometry(piece_type="Glass", width_cm=100, length_cm=100, qty=1, glass_margin_mm=65),
        PieceGeometry(
            piece_type="Glass",
            width_cm=100,
            length_cm=100,
            qty=1,
            glass_margin_mode=MODE_INDIVIDUAL,
            glass_margin_top_mm=50,
            glass_margin_bottom_mm=80,
            glass_margin_right_mm=40,
            glass_margin_left_mm=60,
        ),
        drawing_changed=False,
    )


def test_individual_fingerprint_changes_and_uniform_fingerprint_omits_side_keys():
    uniform = freeze_geometry_piece(_required_piece(glass_margin_mm=65.0))
    individual = freeze_geometry_piece(_required_piece(**fingerprint_glass_fields({
        "piece_type": "Glass",
        "glass_margin_mode": MODE_INDIVIDUAL,
        "glass_margin_top_mm": 50,
        "glass_margin_bottom_mm": 80,
        "glass_margin_right_mm": 40,
        "glass_margin_left_mm": 60,
    })))
    assert "glass_margin_mode" not in uniform
    assert individual["glass_margin_mode"] == MODE_INDIVIDUAL
    assert "glass_margin_mm" not in individual
    expanded = expand_piece_groups([{
        "qty": 1,
        "width_cm": 100,
        "length_cm": 100,
        "piece_type": "Glass",
        "piece_instance_id": "door-1",
        "glass_margin_mode": MODE_INDIVIDUAL,
        "glass_margin_top_mm": 50,
        "glass_margin_bottom_mm": 80,
        "glass_margin_right_mm": 40,
        "glass_margin_left_mm": 60,
    }])
    assert expanded[-1]["glass_margin_left_mm"] == 60.0
    regular = expand_piece_groups([{
        "qty": 1,
        "width_cm": 40,
        "length_cm": 60,
        "piece_type": "Regular",
        "piece_instance_id": "door-2",
    }])
    assert "glass_margin_mm" not in regular[-1]
    assert "glass_margin_mode" not in regular[-1]


def test_plan_payload_keeps_uniform_glass_rows_unchanged():
    piece = _plan_piece_payload(PlanPieceInput(
        index=1,
        width_cm=100,
        length_cm=100,
        qty=1,
        allow_rotation=0,
        piece_type="Glass",
        clipped_corner_position="",
        clipped_corner_width_cm=0,
        clipped_corner_length_cm=0,
        glass_margin_mm=65,
    ))
    assert piece["glass_margin_mm"] == 65.0
    assert "glass_margin_mode" not in piece


def test_glass_accepts_only_a_liner_and_keeps_its_price():
    summary = calculate_extra_addon_pricing(
        [ExtraAddonPieceInput(piece_type="Glass", qty=2, liner=True)],
        rates=RATES,
    )
    assert summary.pieces[0].selected_codes == ("liner",)
    assert summary.pieces[0].total_usd == 5
    with pytest.raises(ExtraAddonError) as raised:
        calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(
                piece_type="Glass",
                qty=1,
                liner=True,
                back_groove=True,
            )],
            rates=RATES,
        )
    assert raised.value.code == "glass_addon_not_allowed"
    regular = calculate_extra_addon_pricing(
        [ExtraAddonPieceInput(piece_type="Regular", qty=1, back_groove=True)],
        rates=RATES,
    )
    assert regular.pieces[0].selected_codes == ("back_groove",)


def test_liner_must_stay_inside_the_glass_frame():
    piece = LinerPiece(
        "Glass",
        100,
        100,
        glass_frame_left_mm=60,
        glass_frame_right_mm=40,
        glass_frame_top_mm=50,
        glass_frame_bottom_mm=80,
    )
    assert validation_code(piece, "edge_long_left", 1, 2) == ""
    assert validation_code(piece, "edge_long_left", 4, 3) == "liner_enters_glass_opening"
    region = liner_region_polygon_mm(piece, "edge_long_left", 1, 2, 0, 20)
    hole = glass_hole_ring_mm(cut_width_mm=1000, cut_length_mm=1000, side_margins=SIDES)
    assert not any(point_in_polygon(point, hole) for point in region)
    guest = ((100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0))
    assert all(point_in_polygon(point, hole) for point in guest)
    assert not any(point_in_polygon(point, region) for point in guest)


def test_two_liners_can_meet_at_a_glass_corner():
    piece = LinerPiece(
        "Glass",
        100,
        100,
        glass_frame_left_mm=80,
        glass_frame_right_mm=80,
        glass_frame_top_mm=80,
        glass_frame_bottom_mm=80,
    )
    specs = [
        {"side": "edge_width_top", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
        {"side": "edge_long_left", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
    ]
    paths = merged_liner_toolpaths_mm(piece, specs, 1.5, 5)
    assert len(paths) == 1
    assert len(paths[0]) > 2


def test_rotation_and_mirror_move_the_asymmetric_opening():
    ring = glass_hole_ring_mm(cut_width_mm=1000, cut_length_mm=1000, side_margins=SIDES)
    rotated = glass_hole_ring_mm(
        cut_width_mm=1000,
        cut_length_mm=1000,
        side_margins=SIDES,
        rotated=True,
    )
    assert rotated[0] == (80.0, 60.0)
    assert rotated[2][0] - rotated[0][0] == pytest.approx(870)
    assert rotated[2][1] - rotated[0][1] == pytest.approx(900)
    turned = [
        transform_point(point, mirrored=False, quarter_turns=2, width=1000, height=1000)
        for point in ring
    ]
    assert min(point[0] for point in turned) == pytest.approx(40)
    assert min(point[1] for point in turned) == pytest.approx(80)
    mirrored = [
        transform_point(point, mirrored=True, quarter_turns=0, width=1000, height=1000)
        for point in ring
    ]
    assert min(point[0] for point in mirrored) == pytest.approx(40)
    assert min(point[1] for point in mirrored) == pytest.approx(50)


def test_edge_band_deduction_changes_only_the_cut_inset():
    deducted = cut_insets_mm(
        side_margins=SIDES,
        long_left_mm=1,
        long_right_mm=1,
        width_top_mm=1,
        width_bottom_mm=1,
        deduct_edge_thickness=True,
    )
    kept = cut_insets_mm(
        side_margins=SIDES,
        long_left_mm=1,
        long_right_mm=1,
        width_top_mm=1,
        width_bottom_mm=1,
        deduct_edge_thickness=False,
    )
    assert deducted["long_left"] == Decimal("59")
    assert kept["long_left"] == Decimal("60")
    source = {
        "piece_type": "Glass",
        "width_cm": 100,
        "length_cm": 100,
        "glass_margin_mode": MODE_INDIVIDUAL,
        "glass_margin_top_mm": 50,
        "glass_margin_bottom_mm": 80,
        "glass_margin_right_mm": 40,
        "glass_margin_left_mm": 60,
        "edge_long_left": 1,
        "edge_long_right": 1,
        "edge_width_top": 1,
        "edge_width_bottom": 1,
        "edge_long_thickness_mm": 1,
        "edge_width_thickness_mm": 1,
    }
    frames = cut_frame_thickness_mm(source, cut_width_cm=99.8, cut_length_cm=99.8)
    untouched = cut_frame_thickness_mm(source, cut_width_cm=100, cut_length_cm=100)
    assert frames["left"] == pytest.approx(59)
    assert untouched["left"] == pytest.approx(60)


def _line_loop(modelspace, points, layer):
    sequence = (*points, points[0])
    for start, end in zip(sequence, sequence[1:]):
        modelspace.add_line(start, end, dxfattribs={"layer": layer})


def test_asymmetric_glass_opening_and_liner_round_trip_through_dxf():
    piece = LinerPiece(
        "Glass",
        100,
        100,
        glass_frame_left_mm=60,
        glass_frame_right_mm=40,
        glass_frame_top_mm=50,
        glass_frame_bottom_mm=80,
    )
    path = merged_liner_toolpaths_mm(
        piece,
        [{"side": "edge_long_left", "offset_cm": 1, "start_cm": 2, "length_cm": 20}],
        2,
        5,
    )[0]
    document = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "GEOMETRY", "Liner"):
        document.layers.add(name)
    model = document.modelspace()
    _line_loop(model, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), "SHEET_OUTLINE")
    origin = (100, 100)

    def place(point):
        return (origin[0] + point[0], origin[1] + 1000 - point[1])

    _line_loop(model, (
        place((0, 1000)),
        place((1000, 1000)),
        place((1000, 0)),
        place((0, 0)),
    ), "GEOMETRY")
    _line_loop(model, (
        place((60, 920)),
        place((960, 920)),
        place((960, 50)),
        place((60, 50)),
    ), "GEOMETRY")
    model.add_lwpolyline(
        [place(point) for point in path],
        dxfattribs={"layer": "Liner"},
    )
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    document.saveas(handle.name)
    order = SimpleNamespace(
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        default_edge_type="",
        pieces=[SimpleNamespace(
            qty=1,
            allow_rotation=0,
            extra_liner=1,
            extra_back_groove=0,
            extra_full_door_double=0,
            extra_recessed_handle_cutout=0,
            extra_double=0,
            liner_reference_side="edge_long_left",
            liner_offset_cm=1,
            liner_width_cm=2,
            liner_start_cm=2,
            liner_length_cm=20,
            liner_specs_json="",
            edge_long_right=0,
            edge_long_left=0,
            edge_width_top=0,
            edge_width_bottom=0,
            edge_long_thickness_mm=0,
            edge_width_thickness_mm=0,
            edge_break=0,
            piece_type="Glass",
            piece_instance_id="door-glass",
            width_cm=100,
            length_cm=100,
            cut_width_cm=100,
            cut_length_cm=100,
            glass_margin_mm=0,
            glass_margin_mode=MODE_INDIVIDUAL,
            glass_margin_top_mm=50,
            glass_margin_bottom_mm=80,
            glass_margin_right_mm=40,
            glass_margin_left_mm=60,
        )],
    )
    settings = normalize_plan_settings(
        optimization_mode=DEFAULT_OPTIMIZATION_MODE_ID,
        machine_type=DEFAULT_MACHINE_TYPE,
        optimization_time_limit_sec=DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        kerf_mm=0,
        preferred_trim_mm=0,
    )
    with patch.object(dxf_import_service.frappe, "get_site_path", return_value=handle.name):
        snapshot = parse_production_dxf(handle.name, order, settings=settings)
    imported = snapshot["sheets"][0]["pieces"][0]
    hole = parse_geometry_mm(imported["geometry"]).holes[0]
    assert max(point[0] for point in hole) - min(point[0] for point in hole) == pytest.approx(900)
    assert max(point[1] for point in hole) - min(point[1] for point in hole) == pytest.approx(870)
    assert min(point[0] for point in hole) - origin[0] == pytest.approx(60)
    liners = [overlay for overlay in imported["overlays"] if overlay["kind"] == "liner"]
    assert len(liners) == 1
