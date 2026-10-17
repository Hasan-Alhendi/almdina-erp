"""Glass opening geometry against the stored margin and the cut outline."""

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    parse_geometry_mm,
    serialize_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    FORBIDDEN_ROTATION,
    piece_target,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    ContourCandidate,
    ExpectedPieceEvidence,
    PartGeometry,
    resolve_contour_ownership,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import (
    GLASS_GEOMETRY_AMBIGUOUS,
    GLASS_MARGIN_MISMATCH,
    GLASS_MULTIPLE_OPENINGS,
    GLASS_OPENING_INVALID,
    GLASS_OPENING_MISSING,
    GLASS_OPENING_OUTSIDE,
    GLASS_OPENING_UNEXPECTED,
    GlassIdentityContour,
    GlassIdentityExpectation,
    cut_insets_mm,
    glass_hole_ring_mm,
    reassign_glass_identity,
    validate_glass_dxf_opening,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    expand_piece_groups,
    make_placed_piece,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import issue
from almdina_erp.almdina_erp.services.dxf_import_service import (
    _glass_opening_issues,
)

TOLERANCE = 0.25
OUTER = ((0.0, 0.0), (521.0, 0.0), (521.0, 725.0), (0.0, 725.0))
HOLE = ((65.0, 65.0), (456.0, 65.0), (456.0, 660.0), (65.0, 660.0))


def _rect(x1, y1, x2, y2):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _check(outer, holes, **kwargs):
    payload = {
        "piece_type": "Glass",
        "margin_mm": 65,
        "rotated": False,
        "allow_rotation": True,
        "tolerance": TOLERANCE,
    }
    payload.update(kwargs)
    return validate_glass_dxf_opening(outer=outer, holes=holes, **payload)


def test_matching_rectangular_opening_is_accepted():
    decision = _check(OUTER, (HOLE,))

    assert decision.ok
    assert abs((456 - 65) - 391) < 1e-9
    assert abs((660 - 65) - 595) < 1e-9


def test_two_identical_glass_doors_stay_two_pieces():
    # The factory file 149.dxf is not in the repository. These rectangles are
    # its two glass doors: outer 521×725, opening 391×595, margin 65 mm.
    contours = [
        ContourCandidate(key=1, polygon=_rect(0, 0, 521, 725)),
        ContourCandidate(key=2, polygon=_rect(65, 65, 456, 660)),
        ContourCandidate(key=3, polygon=_rect(600, 0, 1121, 725)),
        ContourCandidate(key=4, polygon=_rect(665, 65, 1056, 660)),
    ]
    expected = (
        ExpectedPieceEvidence(width=521, height=725, allow_rotation=True),
        ExpectedPieceEvidence(width=521, height=725, allow_rotation=True),
    )

    topology = resolve_contour_ownership(
        contours,
        expected,
        dimension_tolerance=2.0,
        geometry_tolerance=TOLERANCE,
    )

    assert len(topology.parts) == 2
    assert topology.hole_contour_keys == (2, 4)
    for part in topology.parts:
        decision = _check(part.geometry.outer, part.geometry.holes)
        assert decision.ok


def test_missing_multiple_outside_open_and_bad_margin_are_rejected():
    assert _check(OUTER, ()).code == GLASS_OPENING_MISSING
    assert _check(OUTER, (HOLE, HOLE)).code == GLASS_MULTIPLE_OPENINGS
    assert _check(OUTER, (_rect(65, 65, 600, 660),)).code == GLASS_OPENING_OUTSIDE
    assert _check(OUTER, (_rect(0, 65, 456, 660),)).code == GLASS_OPENING_OUTSIDE
    assert _check(OUTER, (((65, 65), (456, 65), (456, 660)),)).code == GLASS_OPENING_INVALID
    shifted = _rect(60, 65, 456, 660)
    mismatch = _check(OUTER, (shifted,))
    assert mismatch.code == GLASS_MARGIN_MISMATCH
    assert mismatch.params["expected_inset_mm"] == 65
    assert mismatch.params["actual_inset_mm"] == 60


def test_one_side_outside_geometry_tolerance_is_rejected():
    # 64 mm on the top side is 1 mm away from 65, beyond the 0.25 mm tolerance.
    hole = _rect(65, 65, 456, 661)
    decision = _check(OUTER, (hole,))

    assert decision.code == GLASS_MARGIN_MISMATCH
    assert decision.params["actual_inset_mm"] == 64


def test_regular_opening_is_not_accepted_as_glass():
    decision = _check(OUTER, (HOLE,), piece_type="Regular")

    assert decision.code == GLASS_OPENING_UNEXPECTED
    assert _check(OUTER, (), piece_type="Regular").ok
    assert _check(OUTER, (), piece_type="Clipped Corner").ok
    assert _check(OUTER, (), piece_type="Special").ok


def test_same_size_regular_and_glass_follow_the_opening():
    assigned, error = reassign_glass_identity(
        (
            GlassIdentityContour(521, 725, hole_count=1, expected_index=0),
            GlassIdentityContour(521, 725, hole_count=0, expected_index=1),
        ),
        (
            GlassIdentityExpectation(521, 725, False, is_glass=False),
            GlassIdentityExpectation(521, 725, False, is_glass=True),
        ),
        dimension_tolerance=2,
    )

    assert error is None
    assert assigned == (1, 0)


def test_ambiguous_same_size_pair_is_rejected_without_a_door_number():
    _assigned, error = reassign_glass_identity(
        (
            GlassIdentityContour(521, 725, hole_count=1, expected_index=0),
            GlassIdentityContour(521, 725, hole_count=1, expected_index=1),
        ),
        (
            GlassIdentityExpectation(521, 725, False, is_glass=False),
            GlassIdentityExpectation(521, 725, False, is_glass=True),
        ),
        dimension_tolerance=2,
    )
    presented = present_issue(
        issue(
            GLASS_GEOMETRY_AMBIGUOUS,
            "IDENTITY",
            target=piece_target(),
            params={"identity_unproven": True},
        )
    )

    assert error == GLASS_GEOMETRY_AMBIGUOUS
    assert "الدرفة" not in presented.target
    assert "DXF Validation Failed" not in presented.problem


def test_rotation_uses_existing_quarter_turn_and_rejects_a_mirror():
    rotated_outer = _rect(0, 0, 725, 521)
    clockwise_hole = _rect(65, 65, 660, 458)
    accepted = _check(
        rotated_outer,
        (clockwise_hole,),
        rotated=True,
        allow_rotation=True,
        long_left_mm=2,
    )
    forbidden = _check(
        rotated_outer,
        (clockwise_hole,),
        rotated=True,
        allow_rotation=False,
        long_left_mm=2,
    )
    mirrored = _check(
        OUTER,
        (_rect(65, 65, 458, 665),),
        rotated=False,
        long_left_mm=2,
        width_top_mm=5,
    )

    assert accepted.ok
    assert forbidden.code == FORBIDDEN_ROTATION
    assert mirrored.code == GLASS_MARGIN_MISMATCH
    placed = glass_hole_ring_mm(
        cut_width_mm=521,
        cut_length_mm=725,
        margin_mm=65,
        long_left_mm=2,
        rotated=True,
    )
    assert placed[0] == (65.0, 63.0)


def test_no_band_and_band_use_the_finished_margin_on_the_cut_outline():
    plain = cut_insets_mm(margin_mm="65.001")
    banded = cut_insets_mm(
        margin_mm=65,
        long_left_mm=1,
        long_right_mm=1,
        width_bottom_mm=1,
        width_top_mm=1,
    )
    banded_outer = _rect(0, 0, 519, 723)
    banded_hole = _rect(64, 64, 455, 659)
    consumed = _check(OUTER, (HOLE,), long_left_mm=65)

    assert plain["long_left"] == plain["width_top"]
    assert str(plain["long_left"]) == "65.001"
    assert all(value == 64 for value in banded.values())
    assert _check(
        banded_outer,
        (banded_hole,),
        long_left_mm=1,
        long_right_mm=1,
        width_bottom_mm=1,
        width_top_mm=1,
    ).ok
    assert consumed.code == GLASS_MARGIN_MISMATCH
    assert consumed.params["reason"] == "band_consumes_margin"


def test_decimal_margin_is_not_rounded_to_a_whole_millimetre():
    hole = _rect(65.001, 65.001, 521 - 65.001, 725 - 65.001)

    assert _check(OUTER, (hole,), margin_mm="65.001").ok
    assert _check(OUTER, (HOLE,), margin_mm="66.001").code == GLASS_MARGIN_MISMATCH


def test_snapshot_keeps_the_real_opening_coordinates():
    stored = serialize_geometry_mm(PartGeometry(outer=OUTER, holes=(HOLE,)))
    restored = parse_geometry_mm(stored)

    assert restored.outer == OUTER
    assert restored.holes == (HOLE,)
    assert _check(restored.outer, restored.holes).ok


def test_system_plan_carries_one_hole_and_does_not_add_a_piece():
    glass = expand_piece_groups([
        {
            "qty": 2,
            "width_cm": 52.1,
            "length_cm": 72.5,
            "piece_type": "Glass",
            "glass_margin_mm": 65,
        }
    ])
    placed = make_placed_piece(glass[0], 0, 0, 52.1, 72.5, False)
    banded = expand_piece_groups([
        {
            "qty": 1,
            "width_cm": 51.9,
            "length_cm": 72.3,
            "piece_type": "Glass",
            "glass_margin_mm": 65,
            "edge_long_left": 1,
            "edge_long_right": 1,
            "edge_width_top": 1,
            "edge_width_bottom": 1,
            "edge_long_thickness_mm": 1,
            "edge_width_thickness_mm": 1,
        }
    ])
    banded_placed = make_placed_piece(banded[0], 0, 0, 51.9, 72.3, False)
    regular = make_placed_piece(
        expand_piece_groups([
            {"qty": 1, "width_cm": 52.1, "length_cm": 72.5, "piece_type": "Regular"}
        ])[0],
        0, 0, 52.1, 72.5, False,
    )
    corner = make_placed_piece(
        expand_piece_groups([
            {
                "qty": 1,
                "width_cm": 52.1,
                "length_cm": 72.5,
                "piece_type": "Clipped Corner",
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 10,
                "clipped_corner_length_cm": 10,
            }
        ])[0],
        0, 0, 52.1, 72.5, False,
    )

    assert len(glass) == 2
    assert placed["area_m2"] == pytest.approx(52.1 * 72.5 / 10000)
    assert placed["glass_hole_local_mm"][0] == [65.0, 65.0]
    assert placed["glass_hole_local_mm"][2] == [456.0, 660.0]
    assert banded_placed["glass_hole_local_mm"][0] == [64.0, 64.0]
    assert "glass_hole_local_mm" not in regular
    assert "glass_hole_local_mm" not in corner
    assert corner["piece_type"] == "Clipped Corner"


def test_generated_ring_matches_the_cut_inset_formula():
    ring = glass_hole_ring_mm(
        cut_width_mm=521,
        cut_length_mm=725,
        margin_mm=65,
    )

    assert ring == HOLE


def test_import_issue_names_the_door_only_after_identity_is_known():
    labeled = [{
        "piece_type": "Glass",
        "source_piece_no": 8,
        "copy_no": 1,
        "rotated": False,
        "_outline_mm": OUTER,
        "_holes_mm": (_rect(60, 65, 456, 660),),
        "_glass_spec": {
            "margin_mm": 65,
            "long_left_mm": 0,
            "long_right_mm": 0,
            "width_bottom_mm": 0,
            "width_top_mm": 0,
            "allow_rotation": True,
        },
    }]

    issues = _glass_opening_issues(labeled)
    presented = present_issue(issues[0])

    assert issues[0].code == GLASS_MARGIN_MISMATCH
    assert presented.target == "الدرفة 8."
    assert "65" in presented.details[0]
    assert "60" in presented.details[0]
    assert "DXF Validation Failed" not in presented.problem


def test_failed_glass_validation_is_raised_before_plan_persistence():
    source = Path(
        "almdina_erp/almdina_erp/services/shop_floor_dxf_service.py"
    ).read_text(encoding="utf-8")
    parse_at = source.index("custom_snapshot = parse_production_dxf")
    save_at = source.index("plan = save_uploaded_dxf_plan")
    error_at = source.index("except DxfImportError")

    assert error_at < save_at
    assert parse_at < save_at
    assert _glass_opening_issues([]) == []
