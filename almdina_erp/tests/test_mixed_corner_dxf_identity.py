"""An equal-bbox noncorner must not disable proven corner-contour identity."""
from decimal import Decimal
from itertools import permutations
import json

import pytest

from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan, rows_with_identity
from almdina_erp.tests.test_corner_dxf_edge_binding import _spec
from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
from almdina_erp.tests.geometry_nesting_cases import source_rows
from almdina_erp.almdina_erp.domain.cutting.primitives import create_sheet, expand_piece_groups, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _placed_corner
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.services.strict_dxf_import_service import _find_exact_candidate


@pytest.mark.parametrize('noncorner', ['Glass', 'Regular'])
@pytest.mark.parametrize('kind', ['L-Shaped Corner', 'Clipped Corner'])
@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_mixed_square_inventory_uses_corner_contour_in_both_rotation_passes(noncorner, kind, order):
    kinds = ['L-Shaped Corner', 'Clipped Corner', noncorner]
    specs = [_spec(row_index=i+1, piece_type=value, allow_rotation=int(i < 2),
        finished_length_cm=Decimal('40'), cut_length_cm=Decimal('40'),
        clipped_corner_width_cm=Decimal('30'), clipped_corner_length_cm=Decimal('30'),
        side_profiles=(), edge_break=0) for i, value in enumerate(kinds)]
    # A nonrotatable square remains a direct size match but is excluded from
    # the rotated pass. Both passes must still identify the same real corner.
    inventory = [{'spec': specs[i]} for i in order]
    outer = ([[0,0],[100,0],[100,300],[400,300],[400,400],[0,400]]
        if kind == 'L-Shaped Corner' else [[0,0],[100,0],[400,300],[400,400],[0,400]])
    piece = {'geometry': {'outer': outer, 'holes': []}}
    found = [_find_exact_candidate(inventory, Decimal('40'), Decimal('40'),
        rotated=rotated, piece=piece) for rotated in (False, True)]
    assert all(match.index is not None for match in found)
    assert {inventory[match.index]['spec'].piece_type for match in found} == {kind}
    assert found[0].index == found[1].index


@pytest.mark.parametrize('noncorner', ['Glass', 'Regular'])
def test_equal_bbox_noncorner_does_not_resolve_genuinely_ambiguous_corner_rows(noncorner):
    specs = [_spec(row_index=i+1, piece_type='L-Shaped Corner' if i < 2 else noncorner,
        finished_length_cm=Decimal('40'), cut_length_cm=Decimal('40'),
        clipped_corner_width_cm=Decimal('30'), clipped_corner_length_cm=Decimal('30'),
        side_profiles=(), edge_break=0) for i in range(3)]
    piece = {'geometry': {'outer': [[0,0],[100,0],[100,300],[400,300],[400,400],[0,400]]}}
    match = _find_exact_candidate([{'spec': spec} for spec in specs],
        Decimal('40'), Decimal('40'), rotated=False, piece=piece)
    assert match.index is None and match.corner_reason == 'ambiguous'
    assert match.candidate_rows == (1, 2)


def test_equal_bbox_noncorner_does_not_turn_a_wrong_notch_into_a_size_match():
    specs = [_spec(row_index=i+1, piece_type='L-Shaped Corner' if i < 2 else 'Regular',
        finished_length_cm=Decimal('40'), cut_length_cm=Decimal('40'),
        clipped_corner_width_cm=Decimal(str(30-i*5)), clipped_corner_length_cm=Decimal(str(30-i*5)),
        side_profiles=(), edge_break=0) for i in range(3)]
    piece = {'geometry': {'outer': [[0,0],[200,0],[200,200],[400,200],[400,400],[0,400]]}}
    match = _find_exact_candidate([{'spec': spec} for spec in specs],
        Decimal('40'), Decimal('40'), rotated=False, piece=piece)
    assert match.index is None and match.corner_reason == 'none'


def test_recorded_mixed_portfolio_alternative_reloads_exports_and_strict_imports(tmp_path):
    # Fixed recorded placement, independent of time-budgeted search scheduling.
    # The equal-bbox clipped contour is exported before the L and Glass.
    rows = [dict(row, piece_instance_id=f'smart:{i}') for i, row in
        enumerate(rows_with_identity(source_rows('P5-joint-different')), 1)]
    pieces = expand_piece_groups(rows)
    first, second = create_sheet(1, 136.4, 45.3), create_sheet(2, 136.4, 45.3)
    first['pieces'] = [
        _placed_corner(pieces[2], x_cm=50.6, y_cm=0, mirrored=False, turns=1),
        _placed_corner(pieces[3], x_cm=65.81213203435597, y_cm=10.212132034355964, mirrored=False, turns=3),
        _placed_corner(pieces[0], x_cm=0, y_cm=0, mirrored=False, turns=0),
        make_placed_piece(pieces[5], 10.3, 17.7, 12, 12, False),
        _placed_corner(pieces[1], x_cm=101.11, y_cm=0, mirrored=False, turns=2),
    ]
    second['pieces'] = [make_placed_piece(pieces[4], 0, 5.3, 40, 40, False)]
    plan = dict(sheets=[first, second], unplaced=[], full_board_width_cm=136.4,
        full_board_length_cm=45.3, kerf_cm=.3, trim_cm=0, machine_type='CNC Router')
    assert not validate_plan(plan, pieces, 136.4, 45.3, kerf_cm=.3)
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)
    reloaded = json.loads(json.dumps(plan))
    imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, tmp_path))
    actual = [p for sheet in imported['sheets'] for p in sheet['pieces']]
    assert len(imported['sheets']) == 2 and len(actual) == len(pieces) == 6
    assert sorted(p['piece_instance_id'] for p in actual) == sorted(p['piece_instance_id'] for p in pieces)
    assert {p['source_piece_no']: p['piece_type'] for p in actual} == {
        1: 'L-Shaped Corner', 2: 'L-Shaped Corner', 3: 'Clipped Corner',
        4: 'Clipped Corner', 5: 'Glass', 6: 'Regular'}
