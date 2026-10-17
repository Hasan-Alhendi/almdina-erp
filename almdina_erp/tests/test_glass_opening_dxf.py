"""Glass opening geometry against the stored margin and the cut outline."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    parse_geometry_mm,
    serialize_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CATEGORY_DIMENSIONS,
    CUT_SIZE_MISMATCH,
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
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
    present_issues,
    render_error_cards_html,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import issue
from almdina_erp.almdina_erp.services.dxf_import_service import (
    _expected_order_pieces,
    _glass_opening_issues,
    _side_band_mm,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import OrderPieceCutSpec
from almdina_erp.almdina_erp.services.strict_dxf_import_service import _proxy_order

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
    assert "60" in presented.highlight
    assert "65" in presented.highlight
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


def _side(decision, name):
    return next(row for row in decision.params["sides"] if row["side"] == name)


def test_margin_message_shows_order_band_expected_actual_and_tolerance():
    decision = _check(OUTER, (_rect(60, 65, 456, 660),), long_left_mm=2)
    left = _side(decision, "long_left")
    presented = present_issue(issue(
        decision.code,
        decision.category,
        target=piece_target(source_piece_no=8, copy_no=1),
        params=decision.params,
    ))
    card = render_error_cards_html([issue(
        decision.code,
        decision.category,
        target=piece_target(source_piece_no=8, copy_no=1),
        params=decision.params,
    )])

    assert left["order_margin_mm"] == 65
    assert left["band_mm"] == 2
    assert left["expected_inset_mm"] == 63
    assert left["actual_inset_mm"] == 60
    assert left["delta_mm"] == pytest.approx(-3)
    assert decision.params["tolerance_mm"] == TOLERANCE
    assert "● اليسار" in card
    assert "63" in card and "60" in card and "-3" in card
    assert "0.25" in card
    assert "6.5 سم" in presented.highlight or "6.5 سم" in "".join(presented.details)
    assert "التفاصيل الهندسية" in card


def test_rotated_message_uses_the_validator_side_map():
    decision = _check(
        _rect(0, 0, 725, 521),
        (_rect(65, 65, 660, 461),),
        rotated=True,
        allow_rotation=True,
        long_left_mm=2,
    )
    left = _side(decision, "long_left")
    top = _side(decision, "width_top")

    assert decision.params["orientation"] == "orientation_cw"
    assert left["expected_inset_mm"] == 63
    assert left["actual_inset_mm"] == 60
    assert left["dxf_side"] == "top"
    assert top["actual_inset_mm"] == 65
    assert top["violates"] is False


def test_missing_margin_is_not_presented_as_zero():
    decision = _check(OUTER, (HOLE,), margin_mm=None, long_left_mm=2)
    presented = present_issue(issue(
        decision.code,
        decision.category,
        target=piece_target(source_piece_no=8, copy_no=1),
        params=decision.params,
    ))
    text = " ".join((presented.problem, presented.highlight, *presented.details, presented.action))

    assert decision.code == GLASS_MARGIN_MISMATCH
    assert decision.params["margin_known"] is False
    assert decision.params["order_margin_mm"] is None
    assert "لم يتم العثور على هامش بلور محفوظ للدرفة 8." in presented.problem
    assert "افتح شكل الدرفة، أدخل الهامش، اضغط اعتماد الشكل، ثم احفظ طلب القص وأعد رفع الملف." in presented.action
    assert "غير محفوظ" in text
    assert "هامش البلور في الطلب 0 مم" not in text
    assert "0 مم" not in presented.problem
    assert "0 مم" not in presented.highlight


def test_stored_zero_margin_reports_the_real_negative_inset():
    decision = _check(OUTER, (HOLE,), margin_mm=0, long_left_mm=2)
    presented = present_issue(issue(
        decision.code,
        decision.category,
        target=piece_target(source_piece_no=8, copy_no=1),
        params=decision.params,
    ))
    text = " ".join((presented.problem, presented.highlight, presented.action, *presented.details))

    assert decision.params["margin_known"] is True
    assert decision.params["order_margin_mm"] == 0
    assert decision.params["expected_inset_mm"] == -2
    assert "0 مم" in text
    assert "-2" in text
    assert "غير محفوظ" not in text
    assert "اخفض قشاط" not in presented.action


def test_each_glass_code_has_a_specific_reason():
    samples = {
        GLASS_OPENING_MISSING: _check(OUTER, ()),
        GLASS_MULTIPLE_OPENINGS: _check(OUTER, (HOLE, HOLE)),
        GLASS_OPENING_INVALID: _check(OUTER, (((65, 65), (456, 65), (456, 660)),)),
        GLASS_OPENING_OUTSIDE: _check(OUTER, (_rect(0, 65, 456, 660),)),
        GLASS_OPENING_UNEXPECTED: _check(OUTER, (HOLE,), piece_type="Regular"),
        GLASS_GEOMETRY_AMBIGUOUS: None,
    }
    ambiguous = present_issue(issue(
        GLASS_GEOMETRY_AMBIGUOUS,
        "IDENTITY",
        target=piece_target(),
        params={"identity_unproven": True, "reason": "same_size_opening_not_unique"},
    ))
    assert "رقم درفة" in ambiguous.highlight
    assert "الدرفة" not in ambiguous.target
    for code, decision in samples.items():
        if decision is None:
            continue
        presented = present_issue(issue(decision.code, decision.category, params=decision.params))
        assert presented.code == code
        assert presented.highlight
        assert "DXF Validation Failed" not in presented.problem
    invalid = samples[GLASS_OPENING_INVALID]
    assert invalid.params["geometry_errors"] == ["not_rectangle"]
    assert "ليست مستطيلاً" in present_issue(issue(
        invalid.code, invalid.category, params=invalid.params
    )).highlight


def test_identical_glass_copies_group_and_different_values_stay_separate():
    def glass_issue(copy_no, hole):
        decision = _check(OUTER, (hole,))
        return issue(
            decision.code,
            decision.category,
            target=piece_target(source_piece_no=8, copy_no=copy_no),
            params=decision.params,
        )

    same = present_issues([
        glass_issue(1, _rect(60, 65, 456, 660)),
        glass_issue(2, _rect(60, 65, 456, 660)),
    ])
    different = present_issues([
        glass_issue(1, _rect(60, 65, 456, 660)),
        glass_issue(2, _rect(50, 65, 456, 660)),
    ])
    mixed = present_issues([
        glass_issue(1, _rect(60, 65, 456, 660)),
        issue(GLASS_OPENING_MISSING, "TOPOLOGY", target=piece_target(source_piece_no=8, copy_no=2)),
    ])

    assert len(same) == 1
    assert same[0].target == "الدرفة 8 — النسختان 1 و2."
    assert len(different) == 2
    assert len(mixed) == 2


def test_glass_dialog_escapes_untrusted_text_and_leaves_other_errors_unchanged():
    glass = issue(
        GLASS_OPENING_INVALID,
        "TOPOLOGY",
        target=piece_target(source_piece_no=8, copy_no=1),
        params={"geometry_errors": ["<script>alert(1)</script>"], "margin_known": True, "order_margin_mm": 65, "tolerance_mm": 0.25},
    )
    other = issue(
        CUT_SIZE_MISMATCH,
        CATEGORY_DIMENSIONS,
        target=piece_target(source_piece_no=3, copy_no=1),
        params={"actual_width_cm": 10, "actual_height_cm": 20, "expected_width_cm": 11, "expected_height_cm": 21},
    )
    glass_html = render_error_cards_html([glass])
    other_html = render_error_cards_html([other])

    assert "<script>" not in glass_html
    assert "&lt;script&gt;" in glass_html
    assert "التفاصيل الهندسية" not in other_html
    assert "ما المشكلة؟" in other_html
    assert "مقاس القص غير مطابق" in other_html


def _glass_spec(**overrides):
    values = dict(
        row_index=1,
        finished_width_cm=Decimal("52.3"),
        finished_length_cm=Decimal("72.7"),
        cut_width_cm=Decimal("52.1"),
        cut_length_cm=Decimal("72.5"),
        width_deduction_mm=Decimal("2"),
        length_deduction_mm=Decimal("2"),
        allow_rotation=1,
        piece_type="Glass",
        qty=2,
        side_profiles=(),
    )
    values.update(overrides)
    return OrderPieceCutSpec(**values)


def _saved_glass_row(**overrides):
    values = dict(
        qty=2,
        piece_type="Glass",
        allow_rotation=1,
        cut_width_cm=52.1,
        cut_length_cm=72.5,
        finished_width_cm=52.3,
        finished_length_cm=72.7,
        width_cm=52.3,
        length_cm=72.7,
        glass_margin_mm=65,
        edge_long_left=0,
        edge_long_right=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_long_thickness_mm=0,
        edge_width_thickness_mm=0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _issues_for_saved_row(row):
    proxy = _proxy_order(SimpleNamespace(pieces=[row]), [_glass_spec(piece_type=row.piece_type)], SimpleNamespace(kerf_mm=5))
    expected = _expected_order_pieces(proxy)
    labeled = []
    for candidate in expected:
        labeled.append({
            "piece_type": candidate["piece_type"],
            "source_piece_no": candidate["source_piece_no"],
            "copy_no": candidate["copy_no"],
            "rotated": False,
            "_outline_mm": OUTER,
            "_holes_mm": (HOLE,),
            "_glass_spec": {
                "margin_mm": candidate.get("glass_margin_mm"),
                "margin_state": candidate.get("margin_state"),
                "long_left_mm": _side_band_mm(candidate, "edge_long_left", "edge_long_thickness_mm"),
                "long_right_mm": _side_band_mm(candidate, "edge_long_right", "edge_long_thickness_mm"),
                "width_bottom_mm": _side_band_mm(candidate, "edge_width_bottom", "edge_width_thickness_mm"),
                "width_top_mm": _side_band_mm(candidate, "edge_width_top", "edge_width_thickness_mm"),
                "allow_rotation": bool(candidate.get("allow_rotation")),
                "finished_width_mm": candidate.get("finished_width_cm") * 10,
                "finished_length_mm": candidate.get("finished_length_cm") * 10,
            },
        })
    return expected, _glass_opening_issues(labeled)


def test_saved_glass_margin_reaches_both_copies_through_the_import_proxy():
    expected, issues = _issues_for_saved_row(_saved_glass_row())

    assert len(expected) == 2
    assert [row["glass_margin_mm"] for row in expected] == [65, 65]
    assert {row["margin_state"] for row in expected} == {"stored"}
    assert issues == []


def test_finished_cut_gap_stays_visible_when_saved_bands_are_zero():
    row = _saved_glass_row()
    proxy = _proxy_order(SimpleNamespace(pieces=[row]), [_glass_spec()], SimpleNamespace(kerf_mm=5))
    piece = proxy.pieces[0]

    assert piece.glass_margin_mm == 65
    assert piece.edge_long_left == 0
    assert piece.edge_width_thickness_mm == 0
    assert round((piece.finished_width_cm - piece.cut_width_cm) * 10, 3) == 2
    assert round((piece.finished_length_cm - piece.cut_length_cm) * 10, 3) == 2


def test_saved_band_changes_the_expected_inset_without_hiding_the_margin():
    expected, issues = _issues_for_saved_row(_saved_glass_row(
        edge_long_left=1,
        edge_long_right=1,
        edge_width_top=1,
        edge_width_bottom=1,
        edge_long_thickness_mm=1,
        edge_width_thickness_mm=1,
    ))
    presented = present_issues(issues)
    text = " ".join(card.problem + card.highlight + card.action + "".join(card.details) for card in presented)

    assert expected[0]["margin_state"] == "stored"
    assert expected[0]["glass_margin_mm"] == 65
    assert len(presented) == 1
    assert presented[0].target == "الدرفة 1 — النسختان 1 و2."
    assert "لم يتم العثور على هامش بلور محفوظ" not in text
    assert "64" in text
    assert "فرق المقاس النهائي عن محيط القص" in text
    assert "+2" in text


def test_blank_margin_asks_the_user_to_apply_the_shape():
    _expected, issues = _issues_for_saved_row(_saved_glass_row(glass_margin_mm=None))
    presented = present_issues(issues)

    assert len(presented) == 1
    assert presented[0].problem == "لم يتم العثور على هامش بلور محفوظ للدرفة 1."
    assert presented[0].action == "افتح شكل الدرفة، أدخل الهامش، اضغط اعتماد الشكل، ثم احفظ طلب القص وأعد رفع الملف."
    assert "glass_margin_absent_on_import_row" not in presented[0].highlight


def test_missing_margin_field_is_an_internal_read_fault():
    row = _saved_glass_row()
    del row.glass_margin_mm
    _expected, issues = _issues_for_saved_row(row)
    presented = present_issues(issues)
    text = presented[0].problem + presented[0].highlight + presented[0].action

    assert _expected[0]["margin_state"] == "absent"
    assert _expected[0]["glass_margin_mm"] is None
    assert "glass_margin_absent_on_import_row" in text
    assert "افتح شكل الدرفة" not in text


def test_stored_zero_margin_is_not_reported_as_a_missing_field():
    _expected, issues = _issues_for_saved_row(_saved_glass_row(glass_margin_mm=0))
    presented = present_issues(issues)
    text = presented[0].problem + presented[0].highlight + "".join(presented[0].details)

    assert _expected[0]["margin_state"] == "zero"
    assert _expected[0]["glass_margin_mm"] == 0
    assert "لم يتم العثور على هامش بلور محفوظ" not in text
    assert "0 مم" in text


def test_regular_row_does_not_use_the_glass_margin_check():
    row = _saved_glass_row(piece_type="Regular", glass_margin_mm=65)
    _expected, issues = _issues_for_saved_row(row)

    assert issues == []
