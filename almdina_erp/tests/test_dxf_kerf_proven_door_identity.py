"""Kerf diagnostics must never confuse physical cut IDs with order door rows."""

from __future__ import annotations

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (  # noqa: E402
    TARGET_CONTOUR_PAIR,
    TARGET_PIECE_PAIR,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (  # noqa: E402
    ContourCandidate,
    ExpectedPieceEvidence,
    resolve_contour_ownership,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (  # noqa: E402
    present_issue,
)
from almdina_erp.almdina_erp.services.dxf_import_service import (  # noqa: E402
    DxfImportError,
    _extract_pieces,
    _validate_piece_spacing,
)


def _rect(x1, y1, x2, y2):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _build_parts(order_rows, cut_boxes, *, dimension_tolerance=2.0):
    expected = tuple(
        ExpectedPieceEvidence(
            width=width,
            height=height,
            allow_rotation=allow_rotation,
            source_piece_no=source,
            copy_no=copy,
        )
        for source, copy, width, height, allow_rotation in order_rows
    )
    contours = [
        ContourCandidate(key=index, polygon=_rect(*box))
        for index, box in enumerate(cut_boxes, start=1)
    ]
    topology = resolve_contour_ownership(
        contours, expected,
        dimension_tolerance=dimension_tolerance,
        geometry_tolerance=0.25,
    )
    sheet = {
        "sheet_no": 1,
        "offset_x_mm": 0,
        "offset_y_mm": 0,
        "full_width_mm": 2000,
        "full_height_mm": 2000,
        "pieces": [],
    }
    pieces = _extract_pieces(
        topology,
        sheets=[sheet],
        trim_mm=0,
        usable_width_cm=200,
        usable_length_cm=200,
    )
    return topology, pieces


def _spacing_issue(pieces, *, kerf_mm=5):
    with pytest.raises(DxfImportError) as raised:
        _validate_piece_spacing(pieces, kerf_mm=kerf_mm)
    assert len(raised.value.issues) == 1
    return raised.value.issues[0]


def test_unique_order_rows_are_reported_not_contour_sequence():
    topology, pieces = _build_parts(
        [(8, 1, 200, 100, False), (2, 1, 100, 100, False)],
        [(0, 0, 100, 100), (104, 0, 304, 100)],
    )
    assert [part.proven_source_piece_no for part in topology.parts] == [2, 8]
    assert [piece["_proven_source_piece_no"] for piece in pieces] == [2, 8]
    item = _spacing_issue(pieces)
    assert item.code == "KERF_VIOLATION"
    assert item.target.kind == TARGET_PIECE_PAIR
    assert item.target.pair_piece_nos == (2, 8)
    card = present_issue(item)
    assert card.target == "الدرفتان 2 و8."
    assert "الدرفتين" in card.problem
    assert "5" in card.action


def test_identical_door_rows_remain_contour_numbers_not_invented_identity():
    topology, pieces = _build_parts(
        [(8, 1, 100, 100, False), (2, 1, 100, 100, False)],
        [(0, 0, 100, 100), (104, 0, 204, 100)],
    )
    assert all(part.proven_source_piece_no is None for part in topology.parts)
    item = _spacing_issue(pieces)
    assert item.target.kind == TARGET_CONTOUR_PAIR
    assert item.target.pair_contour_nos == (1, 2)
    assert present_issue(item).target == "مسارا القص 1 و2."


def test_two_interchangeable_copies_prove_door_but_not_copy():
    topology, pieces = _build_parts(
        [(8, 1, 100, 100, False), (8, 2, 100, 100, False)],
        [(0, 0, 100, 100), (104, 0, 204, 100)],
    )
    assert {part.proven_source_piece_no for part in topology.parts} == {8}
    item = _spacing_issue(pieces)
    assert item.target.kind == TARGET_PIECE_PAIR
    assert item.target.pair_piece_nos == (8, 8)


def test_global_matching_proves_row_even_if_one_contour_locally_matches_two():
    topology, pieces = _build_parts(
        [(8, 1, 100, 100, False), (2, 1, 101, 100, False)],
        [(0, 0, 100, 100), (104, 0, 207, 100)],
    )
    assert [part.proven_source_piece_no for part in topology.parts] == [8, 2]
    assert _spacing_issue(pieces).target.pair_piece_nos == (8, 2)


def test_only_one_proven_row_must_not_be_presented_as_proven_pair():
    topology, pieces = _build_parts(
        [(8, 1, 100, 100, False), (2, 1, 100, 100, False), (5, 1, 200, 100, False)],
        [(0, 0, 100, 100), (104, 0, 204, 100), (400, 0, 600, 100)],
    )
    assert [part.proven_source_piece_no for part in topology.parts] == [None, None, 5]
    item = _spacing_issue([pieces[1], pieces[2]], kerf_mm=200)
    # A partial proof is insufficient for a door-pair claim.
    assert item.target.kind == TARGET_CONTOUR_PAIR


def test_overlap_preserves_geometry_rule_but_uses_proven_door_pair():
    _, pieces = _build_parts(
        [(3, 1, 100, 100, False), (9, 1, 200, 100, False)],
        [(0, 0, 100, 100), (90, 0, 290, 100)],
    )
    item = _spacing_issue(pieces)
    assert item.code == "MATERIAL_OVERLAP"
    assert item.target.pair_piece_nos == (3, 9)


def test_original_kerf_numeric_tolerance_is_unchanged():
    _, pieces = _build_parts(
        [(3, 1, 100, 100, False), (9, 1, 200, 100, False)],
        [(0, 0, 100, 100), (104.95, 0, 304.95, 100)],
    )
    _validate_piece_spacing(pieces, kerf_mm=5)
    _spacing_issue(pieces, kerf_mm=5.1)
