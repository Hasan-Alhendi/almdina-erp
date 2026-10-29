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
        original={p['id']:p for p in pieces}
        for sheet in candidate['sheets']:
            for p in sheet['pieces']:
                assert p['piece_instance_id']==original[p['id']]['piece_instance_id']
                assert p['source_piece_no']==original[p['id']]['source_piece_no']
                assert p['copy_no']==original[p['id']]['copy_no']
    return pieces,plan


@pytest.mark.parametrize('name',['P5-L-different','P5-clip-different'])
def test_smart_discovers_nonidentical_interlocks_from_source(name):
    pieces,plan = run(name)
    w,h,_,_=CASES[name]
    assert len(opt.auto_fast(pieces,w,h,.3)['sheets'])==2
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


@pytest.mark.parametrize('name',[n for n in CASES if n!='P5-addon-ambiguous'])
def test_nonidentical_portfolio_reloads_native_rebuild_exports_and_strict_imports(name,tmp_path):
    import json
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,OptimizeOrderPlanCommand,OptimizerOptions,optimize_order_plan)
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from almdina_erp.tests.test_smart_cutting_manufacturing import rows_with_identity,import_saved_plan
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.tests.test_glass_opening_nesting import _reload_export_snapshot, _lifecycle_placed_row
    from almdina_erp.almdina_erp.services.export_validation_service import _plan_to_export_snapshot
    from copy import deepcopy
    w,h,trim,_=CASES[name]
    rows=rows_with_identity(source_rows(name))
    outcome=optimize_order_plan(OptimizeOrderPlanCommand(engine_version='p5-test',input_fingerprint='p5-test',
        board=BoardGeometry(w,h,trim,.3),optimizer=OptimizerOptions('smart','CNC Router',2,20,30,30,.09),
        piece_rows=tuple(rows)),engine=domain_cutting_engine)
    if name in {'P5-L-different','P5-clip-different','P5-L-addon'}:
        assert len(outcome.snapshot['sheets'])==1
    for candidate in outcome.candidate_snapshots:
        saved=json.loads(json.dumps(candidate))
        _,_,native=_reload_export_snapshot(saved,board_w_cm=w,board_h_cm=h)
        native.placed_pieces=[_lifecycle_placed_row(p,s['sheet_no']) for s in saved['sheets'] for p in s['pieces']]
        for child,p in zip(native.placed_pieces,[p for s in saved['sheets'] for p in s['pieces']]):
            for key,value in p.items():
                if key.startswith(('liner_','back_groove_','recessed_handle_','extra_')):
                    setattr(child,key,value)
        source=native.sources[0]
        native.sources=[]
        for sheet in saved['sheets']:
            child=deepcopy(source)
            child.sheet_no=sheet['sheet_no']
            native.sources.append(child)
        native.required_boards=len(native.sources)
        rebuilt=_plan_to_export_snapshot(native)
        imported=import_saved_plan(saved,rows,export_real_js(rebuilt,tmp_path))
        assert sum(len(s['pieces']) for s in imported['sheets'])==sum(r['qty'] for r in rows)


@pytest.mark.parametrize('name,count',[('P5-single-guest',1),('P5-two-guests',2),('P5-many-guests',4)])
def test_single_notch_automatically_admits_one_two_and_multiple_guests(name,count):
    _,plan=run(name)
    assert len(plan['sheets'])==1
    assert len(plan['shape_nesting_diagnostics']['void_guests'])==count


def test_complete_pair_outcome_beats_quad_without_forcing_nest_count():
    import time
    from almdina_erp.almdina_erp.domain.cutting.geometry_nesting import _pack
    from almdina_erp.almdina_erp.domain.cutting.geometry_nesting import _partitions
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _cluster_sheet
    pieces,plan=run('P5-four-choices',budget=3)
    w,h,_,_=CASES['P5-four-choices']
    baseline=opt.auto_fast(pieces,w,h,.3)
    partitions=_cluster_sheet(pieces,w,h,.3,mirroring_allowed=False,formation_alternatives=True)
    outcomes={tuple(b['kind'] for b in blocks):_pack(baseline,pieces,blocks,w,h,.3,False,
              frozenset(),time.monotonic()+2) for blocks in partitions}
    assert len(outcomes[('quad',)]['sheets'])==2
    assert not validate_plan(outcomes[('quad',)],pieces,w,h,kerf_cm=.3)
    # The legacy first pair chooses one inward orientation. Polygon contacts
    # must also try a narrower pair and repack all four remaining source pieces.
    diagnostic={'tested_combinations':0}
    contacts=_partitions(pieces,w,h,.3,False,time.monotonic()+2,diagnostic)
    pair_plans=[_pack(baseline,pieces,blocks,w,h,.3,False,frozenset(),time.monotonic()+2)
                for blocks in contacts if any(len(b['pieces'])==2 and b['kind']=='geometry' for b in blocks)]
    assert any(len(p['sheets'])==1 for p in pair_plans)
    assert any(len(p['sheets'])==1 and not validate_plan(p,pieces,w,h,kerf_cm=.3) for p in pair_plans)
    assert len(plan['sheets'])==1
    assert tuple(plan['industrial_rank'])==min(tuple(p['industrial_rank']) for p in plan['smart_candidates'])


def test_nonidentical_glass_L_clipped_complete_one_board_together():
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import nesting_coverage
    _,plan=run('P5-joint-different',budget=4)
    assert len(plan['sheets'])==1
    assert {'Glass','L-Shaped Corner','Clipped Corner','Joint'}<=nesting_coverage(plan)


@pytest.mark.parametrize('kerf',[0,.3,.7])
@pytest.mark.parametrize('rotate,mirror',[(0,False),(1,False),(1,True)])
def test_contact_search_obeys_real_kerf_and_transform_permissions(kerf,rotate,mirror):
    _,plan=run('P5-L-different',kerf=kerf,rotate=rotate,mirror=mirror)
    if not rotate and not mirror:
        assert all(not int(p.get('corner_rotation_quarter_turns') or 0) and not p.get('mirrored')
                   for c in plan['smart_candidates'] for s in c['sheets'] for p in s['pieces'])


@pytest.mark.parametrize('machine,regular_only',[('Panel Saw',False),('CNC Router',True)])
def test_shape_first_has_no_cost_for_panel_or_regular_orders(machine,regular_only,monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import geometry_nesting
    monkeypatch.setattr(geometry_nesting,'geometry_first_candidates',lambda *a,**k:pytest.fail('unnecessary irregular search'))
    if regular_only:
        pieces=expand_piece_groups([dict(width_cm=30,length_cm=20,qty=2)])
        opt.smart_search(pieces,100,100,.3,time_limit_sec=.1,machine_type=machine)
    else:
        run('P5-L-different',machine=machine)


def test_expiry_is_read_only_and_deterministic_contact_discovery_repeats():
    import time
    from copy import deepcopy
    from almdina_erp.almdina_erp.domain.cutting.geometry_nesting import geometry_first_candidates
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    pieces,first=run('P5-L-different')
    baseline=opt.auto_fast(pieces,45.3,45.3,.3)
    before=deepcopy(baseline)
    candidates,diagnostic=geometry_first_candidates(baseline,pieces,45.3,45.3,.3,machine_type='CNC Router',
        mirroring_allowed=False,deadline=time.monotonic()-1,metric_kwargs={})
    assert candidates==[] and diagnostic['reasons']['insufficient_budget']==1
    assert baseline==before
    _,second=run('P5-L-different')
    assert [geometry_signature(p) for p in first['smart_candidates']]==[geometry_signature(p) for p in second['smart_candidates']]


def test_portfolio_reserves_meaningful_shape_beside_better_rectangular_coordinates():
    from copy import deepcopy
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import retain_diverse_finals,nesting_coverage
    pieces=expand_piece_groups(source_rows('P5-L-different'))
    plan=opt.smart_search(pieces,90,90,.3,time_limit_sec=2)
    shaped=next(p for p in plan['smart_candidates'] if 'L-Shaped Corner' in nesting_coverage(p))
    plain=opt.auto_fast(pieces,90,90,.3)
    # Unit-test selection independently of the measured industrial formula.
    shaped=deepcopy(shaped);shaped['industrial_rank']=(0,1,0,-.1)
    rectangles=[]
    for i in range(5):
        candidate=deepcopy(plain)
        for sheet in candidate['sheets']:
            for p in sheet['pieces']:
                p['x']+=i*.1
        assert not validate_plan(candidate,pieces,90,90,kerf_cm=.3)
        candidate['industrial_rank']=(0,1,0,-1+i*.01)
        rectangles.append(candidate)
    selected=retain_diverse_finals([*rectangles,shaped])
    assert selected[0] is rectangles[0]
    assert shaped in selected and len(selected)==5


def test_ambiguous_corner_machining_cannot_be_certified_even_when_no_safe_baseline_exists():
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,OptimizeOrderPlanCommand,OptimizerOptions,optimize_order_plan)
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    outcome=optimize_order_plan(OptimizeOrderPlanCommand(engine_version='p5-guard',input_fingerprint='p5-guard',
        board=BoardGeometry(45.3,45.3,0,.3),optimizer=OptimizerOptions('smart','CNC Router',1,20,30,30,.09),
        piece_rows=tuple(source_rows('P5-addon-ambiguous'))),engine=domain_cutting_engine)
    assert not outcome.snapshot['validation']['is_valid']
    assert not outcome.candidate_snapshots
    assert len(outcome.snapshot['unplaced'])==len(outcome.expanded_pieces)


def test_internal_counters_distinguish_proven_area_rejection_from_enumeration_limit():
    import time
    from almdina_erp.tests.geometry_nesting_cases import one
    from almdina_erp.almdina_erp.domain.cutting.geometry_nesting import _partitions
    pieces=expand_piece_groups([one(cut_x=2+i*.1,cut_y=2+i*.1) for i in range(12)])
    diagnostic={'tested_combinations':0}
    _partitions(pieces,45,45,.3,False,time.monotonic()+2,diagnostic)
    assert diagnostic['eligible_combinations']==66
    assert diagnostic['tested_combinations']==48
    assert diagnostic['reasons']['combination_enumeration_limit']==18
    assert diagnostic['reasons']['material_area_exceeds_board']==48
    assert not diagnostic['reasons'].get('budget_unvisited_combinations')


def test_quarter_turn_clipped_guest_needs_a_non_grid_anchor_from_original_sources():
    from almdina_erp.tests.joint_nesting_cases import corner,regular
    pieces=expand_piece_groups([corner('Clipped Corner'),regular(8,3)])
    plan=opt.smart_search(pieces,40.3,40.3,.3,time_limit_sec=3,machine_type='CNC Router')
    assert len(plan['sheets'])==1
    assert not validate_plan(plan,pieces,40.3,40.3,kerf_cm=.3)
    assert all(not p.get('placement_rotation_deg') for s in plan['sheets'] for p in s['pieces'])


def test_symmetric_corner_with_equivalent_bands_keeps_a_provable_machining_baseline(tmp_path):
    from unittest.mock import patch
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,OptimizeOrderPlanCommand,OptimizerOptions,optimize_order_plan)
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.almdina_erp.services import piece_cut_dimension_service
    rows=source_rows('P5-addon-ambiguous')
    rows[0].update(edge_long_left=1,edge_long_right=1,edge_width_top=1,edge_width_bottom=1,
                   edge_long_type='P5-band',edge_width_type='P5-band')
    for side in ('edge_long_left','edge_long_right','edge_width_top','edge_width_bottom'):
        rows[0][side+'_type_override']='P5-band'
    # Reference catalog fixture only; geometry/identity/import validators are real.
    with patch.object(piece_cut_dimension_service,'_default_profile_loader',
                      return_value={'P5-band':dict(thickness_mm=0,disabled=0)}):
        for mode in ('Auto','smart'):
            outcome=optimize_order_plan(OptimizeOrderPlanCommand(engine_version='p5-bands',input_fingerprint='p5-bands',
                board=BoardGeometry(45.3,45.3,0,.3),optimizer=OptimizerOptions(mode,'CNC Router',2,20,30,30,.09),
                piece_rows=tuple(rows)),engine=domain_cutting_engine)
            assert outcome.snapshot['validation']['is_valid']
            for snapshot in outcome.candidate_snapshots or (outcome.snapshot,):
                imported=import_saved_plan(snapshot,rows,export_real_js(snapshot,tmp_path))
                assert sum(len(s['pieces']) for s in imported['sheets'])==2
            if mode=='smart':
                assert outcome.candidate_snapshots
