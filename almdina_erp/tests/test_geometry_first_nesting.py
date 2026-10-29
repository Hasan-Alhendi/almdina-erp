"""Automatic polygon discovery must start at original expanded source pieces."""
import pytest
from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.tests.geometry_nesting_cases import CASES, source_rows


def run(name, *, budget=2, kerf=.3, rotate=None, mirror=False, machine='CNC Router'):
    w,h,_,_ = CASES[name]
    rows = source_rows(name)
    if rotate is not None:
        for row in rows:
            row['allow_rotation'] = rotate
    pieces = expand_piece_groups(rows)
    plan = opt.smart_search(pieces,w,h,kerf,time_limit_sec=budget,
                           machine_type=machine,mirroring_allowed=mirror)
    for candidate in plan['smart_candidates']:
        assert not validate_plan(candidate,pieces,w,h,kerf_cm=kerf)
        assert not placement_permission_errors(candidate,pieces,mirroring_allowed=mirror)
        assert len([p['id'] for s in candidate['sheets'] for p in s['pieces']]) == len(pieces)
    return pieces,plan


@pytest.mark.parametrize('name',['P5-L-different','P5-clip-different'])
def test_smart_discovers_nonidentical_interlocks_from_source(name):
    _,plan = run(name)
    assert len(plan['sheets']) == 1
    assert plan['smart_search']['shape_first']['valid_formations'] > 0


def test_nonidentical_material_that_cannot_interlock_keeps_safe_baseline():
    _,plan = run('P5-L-incompatible')
    assert len(plan['sheets']) == 2


def test_existing_rigid_anchors_miss_a_valid_contact_inside_overlapping_boxes():
    # Small deterministic failure witness justifies specialized contact anchors.
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _placed_corner
    from almdina_erp.almdina_erp.domain.cutting.nesting_consolidation import best_rigid_translation
    pieces=expand_piece_groups(source_rows('P5-L-different'))
    fixed=_placed_corner(pieces[0],x_cm=0,y_cm=5.3,mirrored=False,turns=0)
    moving=_placed_corner(pieces[1],x_cm=10.3,y_cm=0,mirrored=False,turns=2)
    assert not validate_plan({'sheets':[dict(sheet_no=1,w=45.3,h=45.3,pieces=[fixed,moving])],
                             'unplaced':[]},pieces,45.3,45.3,kerf_cm=.3)
    # A rigid insert into the original corner anchor cannot discover this
    # relative formation: the first piece also needs to move before packing.
    fixed['y']=0
    moving['x']=moving['y']=0
    assert best_rigid_translation(dict(w=45.3,h=45.3,pieces=[fixed]),[moving],.3,45.3,45.3) is None
