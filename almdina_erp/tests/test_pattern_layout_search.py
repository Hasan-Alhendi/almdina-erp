"""Global source coverage, native geometry, permissions and safe UI projection."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import time

import pytest

from almdina_erp.tests.test_fixed_board_layout_search import fixture,METRICS
from almdina_erp.tests.test_alns_recalculation import command,FrozenEngine
from almdina_erp.almdina_erp.domain.cutting.pattern_master import PatternColumn,PatternSelection,valid_selection
from almdina_erp.almdina_erp.domain.cutting.pattern_layout_search import PatternPool,source_families,refine_pattern_layout
from almdina_erp.almdina_erp.infrastructure.cutting.pattern_solver import solve_pattern_master
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups,make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan,placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan


def pool_for(sources,seconds=10,width=10,height=10):
    return PatternPool(sources,width,height,.5,'CNC Router',False,METRICS,time.monotonic()+seconds)


def test_master_minimizes_boards_before_remnant_and_covers_quantities_exactly():
    columns=(PatternColumn((1,0),99,10,2,1),PatternColumn((0,1),99,10,2,1),
             PatternColumn((1,1),1,15,3,2))
    selected=solve_pattern_master(columns,(2,2),4,deadline=time.monotonic()+2)
    assert valid_selection(columns,(2,2),selected,4)
    assert selected.multiplicities==(0,0,2)
    assert selected.phases and selected.phases[0]=='optimal_in_pool'


def test_master_deadline_and_bad_models_return_no_selection():
    c=(PatternColumn((1,),1,1,1,1),)
    assert not solve_pattern_master(c,(1,),1,deadline=time.monotonic()-1).multiplicities
    assert not solve_pattern_master(c,(-1,),1,deadline=time.monotonic()+1).multiplicities
    assert not valid_selection(c,(1,),PatternSelection((True,)),1)
    assert not valid_selection(c,(1,2),PatternSelection((1,)),1)
    assert not valid_selection(c,(1,),None,1)


def test_family_equivalence_preserves_axes_row_banding_and_permissions():
    rows=[dict(width_cm=2,length_cm=3,qty=2,allow_rotation=1,piece_instance_id='a'),
          dict(width_cm=2,length_cm=3,qty=1,allow_rotation=0,piece_instance_id='b')]
    sources=expand_piece_groups(rows)
    families,_=source_families(sources)
    assert list(map(len,families))==[2,1]
    changed=deepcopy(sources)
    changed[1]['edge_long_right']=1
    assert len(source_families(changed)[0])==3


def test_69_piece_pool_is_not_disabled_and_reconstructs_every_original_copy():
    sources=expand_piece_groups([dict(width_cm=1,length_cm=1,qty=69,piece_instance_id='a')])
    pool=pool_for(sources,width=20,height=20)
    sheets=[]
    for index,subset in enumerate((sources[:35],sources[35:])):
        sheets.append(dict(sheet_no=index+1,w=20,h=20,pieces=[make_placed_piece(p,
            (i%7)*1.5,(i//7)*1.5,1,1,False) for i,p in enumerate(subset)]))
        assert pool.add(sheets[-1],'seed')==index
    original=deepcopy((sources,sheets))
    rebuilt=pool.reconstruct((1,1),dict(sheets=sheets,unplaced=[]))
    assert rebuilt is not None
    actual=[p for s in rebuilt['sheets'] for p in s['pieces']]
    assert Counter(p['piece_instance_id'] for p in actual)==Counter(p['piece_instance_id'] for p in sources)
    assert not validate_plan(rebuilt,sources,20,20,kerf_cm=.5)
    assert (sources,sheets)==original


def test_pool_rejects_wrong_axes_and_forbidden_rotation():
    _,sources,plan=fixture('grid')
    pool=pool_for(sources)
    bad=deepcopy(plan['sheets'][0])
    bad['pieces'][0].update(w=8,h=1,rotated=True)
    assert pool.add(bad,'forbidden') is None


def test_invalid_backend_answer_cannot_corrupt_incumbent():
    _,sources,plan=fixture()
    original=deepcopy((sources,plan))
    def malicious(columns,*a,**kw):
        return PatternSelection(tuple(2 for _ in columns),'fake')
    candidates,trace=refine_pattern_layout(plan,[plan],sources,10,10,.5,
        deadline=time.monotonic()+2,machine_type='CNC Router',mirroring_allowed=False,
        metric_kwargs=METRICS,solver=malicious)
    assert candidates[0]==plan
    assert trace['master_status']=='invalid_or_empty_selection'
    for candidate in candidates:
        assert not validate_plan(candidate,sources,10,10,kerf_cm=.5)
        assert not placement_permission_errors(candidate,sources,mirroring_allowed=False)
    assert (sources,plan)==original


@pytest.mark.parametrize('machine',['Panel Saw','Unsupported'])
def test_unsupported_machine_keeps_original(machine):
    _,sources,plan=fixture()
    candidates,trace=refine_pattern_layout(plan,[plan],sources,10,10,.5,
        deadline=time.monotonic()+1,machine_type=machine,mirroring_allowed=False,metric_kwargs=METRICS)
    assert candidates==[plan] and trace['stop']=='unsupported_or_expired'


def test_application_pattern_stage_keeps_native_and_old_alns_baseline():
    rows,_,plan=fixture()
    base=command(rows,seconds=1)
    old=optimize_order_plan(base,engine=FrozenEngine(plan))
    enabled=replace(base,optimizer=replace(base.optimizer,pattern_search_budget_sec=1))
    new=optimize_order_plan(enabled,engine=FrozenEngine(plan))
    before,after=final_system_sort_keys([old.snapshot,new.snapshot])
    assert after<=before
    assert new.snapshot['validation']['is_valid']
    assert new.snapshot['smart_search']['pattern_search']['additional_to_completed_alns']
    assert new.snapshot['smart_search']['pattern_search']['budget_sec']==1


def test_invalid_or_disabled_pattern_budget_does_not_invoke_stage(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import pattern_layout_search as search
    rows,_,plan=fixture()
    def fail(*a,**kw):
        raise AssertionError('disabled')
    monkeypatch.setattr(search,'refine_pattern_layout',fail)
    for budget in (0,-1,float('nan'),float('inf')):
        cmd=command(rows,seconds=0)
        cmd=replace(cmd,optimizer=replace(cmd.optimizer,pattern_search_budget_sec=budget))
        result=optimize_order_plan(cmd,engine=FrozenEngine(plan))
        assert 'pattern_search' not in result.snapshot['smart_search']


@pytest.mark.parametrize('transpose',[False,True])
def test_global_rows_cover_all_copies_and_respect_source_axes(transpose):
    from almdina_erp.almdina_erp.domain.cutting.shelf_layout_pricing import price_shelf_layout
    from almdina_erp.almdina_erp.infrastructure.cutting.pattern_solver import solve_shelf_master
    sources=expand_piece_groups([dict(width_cm=1,length_cm=3,qty=4,allow_rotation=0,piece_instance_id='axes')])
    sheets=[dict(sheet_no=i+1,w=10,h=10,pieces=[make_placed_piece(p,j*2,0,1,3,False)
        for j,p in enumerate(sources[i*2:i*2+2])]) for i in range(2)]
    plan=dict(sheets=sheets,unplaced=[])
    original=deepcopy((plan,sources))
    trial,trace=price_shelf_layout(plan,plan,sources,10,10,.5,deadline=time.monotonic()+3,
        solver=solve_shelf_master,min_remnant_m2=0,transpose=transpose)
    assert trace['status'] in {'optimal_in_rows','feasible'}
    assert trial is not None and len(trial['sheets'])==1
    assert not validate_plan(trial,sources,10,10,kerf_cm=.5)
    assert all((p['w'],p['h'],p['rotated'])==(1,3,False) for s in trial['sheets'] for p in s['pieces'])
    assert Counter(p['piece_instance_id'] for s in trial['sheets'] for p in s['pieces'])==Counter(p['piece_instance_id'] for p in sources)
    assert (plan,sources)==original


def test_free_space_partition_protects_kerf_across_artificial_seams():
    from almdina_erp.almdina_erp.domain.cutting.shelf_layout_pricing import disjoint_slots
    from almdina_erp.almdina_erp.domain.cutting.primitives import rects_have_clearance
    obstacle=dict(x=3,y=3,w=4,h=4)
    slots=disjoint_slots([dict(w=10,h=10,pieces=[obstacle])],.5)
    assert len(slots)==4
    for i,slot in enumerate(slots):
        assert rects_have_clearance(slot,obstacle,.5)
        assert all(rects_have_clearance(slot,other,.5) for other in slots[i+1:])


def test_rows_reject_backend_answer_without_exact_quantity_coverage():
    from almdina_erp.almdina_erp.domain.cutting.shelf_layout_pricing import price_shelf_layout
    from almdina_erp.almdina_erp.domain.cutting.pattern_master import ShelfSelection
    _,sources,plan=fixture()
    def corrupt(columns,*args,**kw):
        return ShelfSelection(tuple(tuple(0 for _ in rows) for rows in columns),'fake')
    trial,trace=price_shelf_layout(plan,plan,sources,10,10,.5,deadline=time.monotonic()+1,
        solver=corrupt,min_remnant_m2=0)
    assert trial is None and trace['status']=='invalid_coverage'


def test_expired_global_search_does_not_touch_sources_or_backend():
    _,sources,plan=fixture()
    def fail(*args,**kw):
        raise AssertionError('expired backend invoked')
    result,trace=refine_pattern_layout(plan,[plan],sources,10,10,.5,
        deadline=time.monotonic()-1,machine_type='CNC Router',mirroring_allowed=False,
        metric_kwargs=METRICS,solver=fail,row_solver=fail)
    assert result==[plan] and trace['stop']=='unsupported_or_expired'


def test_backend_exception_is_diagnosed_and_completed_geometry_survives():
    _,sources,plan=fixture()
    def fail(*args,**kw):
        raise RuntimeError('backend unavailable')
    candidates,trace=refine_pattern_layout(plan,[plan],sources,10,10,.5,
        deadline=time.monotonic()+2,machine_type='CNC Router',mirroring_allowed=False,
        metric_kwargs=METRICS,solver=fail,row_solver=fail)
    assert candidates[0]==plan and trace['master_status']=='solver_error:RuntimeError'
    assert trace['row_pricing'] and all(t['status']=='solver_error:RuntimeError' for t in trace['row_pricing'])
    assert all(not validate_plan(p,sources,10,10,kerf_cm=.5) for p in candidates)


@pytest.mark.parametrize('field',['extra_liner','extra_back_groove','extra_recessed_handle_cutout','extra_double'])
def test_machined_or_protected_sources_keep_the_existing_pipeline(field):
    _,sources,plan=fixture()
    sources[0][field]=1
    candidates,trace=refine_pattern_layout(plan,[plan],sources,10,10,.5,
        deadline=time.monotonic()+1,machine_type='CNC Router',mirroring_allowed=False,metric_kwargs=METRICS)
    assert candidates==[plan] and trace['stop']=='unsupported_or_expired'


@pytest.mark.parametrize('mirror',[False,True])
def test_corner_permission_is_checked_before_pattern_collection(mirror):
    from almdina_erp.tests.test_alns_recalculation import mixed_fixture
    _,sources,plan=mixed_fixture(mirror=True)
    candidates,trace=refine_pattern_layout(plan,[plan],sources,10,10,.5,
        deadline=time.monotonic()+2,machine_type='CNC Router',mirroring_allowed=mirror,
        metric_kwargs=METRICS,solver=solve_pattern_master)
    if not mirror:
        assert candidates==[plan] and trace['stop']=='invalid_incumbent'
    else:
        assert all(not placement_permission_errors(p,sources,mirroring_allowed=True) for p in candidates)
        assert trace['patterns']>0


@pytest.mark.parametrize('trim',[0,.3])
def test_new_gallery_passes_real_js_and_strict_import_with_requested_trim(trim):
    from scripts.benchmark_alns import strict_check
    rows,_,plan=fixture('grid')
    cmd=command(rows,seconds=0,trim=trim)
    cmd=replace(cmd,optimizer=replace(cmd.optimizer,pattern_search_budget_sec=1))
    result=optimize_order_plan(cmd,engine=FrozenEngine(plan))
    for snapshot in result.candidate_snapshots:
        assert snapshot['validation']['is_valid']
        assert strict_check(snapshot,rows)
        assert snapshot['kerf_cm']==.5


def test_new_projection_rejects_invalid_geometry_and_keeps_native(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import pattern_layout_search as search
    rows,_,plan=fixture()
    cmd=command(rows,seconds=0)
    baseline=optimize_order_plan(cmd,engine=FrozenEngine(plan))
    def corrupt(raw,*args,**kw):
        bad=deepcopy(raw)
        bad['sheets'][0]['pieces'][0]['x']=10000
        return [raw,bad],{'stop':'fake'}
    monkeypatch.setattr(search,'refine_pattern_layout',corrupt)
    enabled=replace(cmd,optimizer=replace(cmd.optimizer,pattern_search_budget_sec=1))
    result=optimize_order_plan(enabled,engine=FrozenEngine(plan))
    assert result.snapshot['validation']['is_valid']
    assert result.snapshot['smart_search']['pattern_search']['projected_improvements']==0
    assert [p['pieces'] for p in result.snapshot['sheets']]==[p['pieces'] for p in baseline.snapshot['sheets']]


def test_pattern_stage_is_capped_and_receives_multiple_native_seeds(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import pattern_layout_search as search
    rows,_,plan=fixture()
    alternate=deepcopy(plan)
    for sheet in alternate['sheets']:
        for piece in sheet['pieces']:
            piece['y']+=.25
    class MultipleSeeds(FrozenEngine):
        def optimize(self,*args,**kw):
            return dict(deepcopy(plan),smart_candidates=[deepcopy(plan),deepcopy(alternate)])
    seen=[]
    def observe(raw,seeds,*args,**kw):
        seen.append((len(seeds),kw['deadline']-time.monotonic()))
        return [raw],{'stop':'done'}
    monkeypatch.setattr(search,'refine_pattern_layout',observe)
    cmd=command(rows,seconds=0)
    cmd=replace(cmd,optimizer=replace(cmd.optimizer,pattern_search_budget_sec=100))
    result=optimize_order_plan(cmd,engine=MultipleSeeds(plan))
    assert seen[0][0]>=2 and 0<seen[0][1]<=4.25
    assert result.snapshot['smart_search']['pattern_search']['budget_sec']==5


def test_pattern_profiles_use_physical_board_frame_with_positive_margin():
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
    sources=expand_piece_groups([dict(width_cm=10,length_cm=10,qty=1,piece_instance_id='edge')])
    sheet=dict(sheet_no=1,w=10,h=10,pieces=[make_placed_piece(sources[0],0,0,10,10,False)])
    context=dict(full_width_cm=10.6,full_length_cm=10.6,applied_trim_width_cm=.3,applied_trim_length_cm=.3)
    pool=PatternPool(sources,10,10,.5,'CNC Router',False,METRICS,time.monotonic()+2,sheet_context=context)
    assert pool.add(sheet,'physical')==0
    expected=sheet_cut_line_quality(dict(sheet,**context),.5)
    assert pool.patterns[0].column.internal_units==round(expected[2]*1000)
    assert expected[2]>sheet_cut_line_quality(sheet,.5)[2]


def test_mixed_height_rows_keep_each_source_size_and_cover_uncommon_families():
    from almdina_erp.almdina_erp.domain.cutting.shelf_layout_pricing import row_patterns
    sources=expand_piece_groups([dict(width_cm=4,length_cm=2,qty=1,allow_rotation=0,piece_instance_id='short'),
        dict(width_cm=4,length_cm=3,qty=1,allow_rotation=0,piece_instance_id='tall')])
    families,_=source_families(sources)
    rows=row_patterns(families,9,10,.5,False,time.monotonic()+2)
    mixed=next(r for r in rows if r['column'].counts==(1,1))
    assert mixed['height']==3
    assert {(o['w'],o['h']) for _,o,_ in mixed['members']}=={(4,2),(4,3)}
    rows=[dict(width_cm=1+i*.01,length_cm=2+i*.01,qty=2,allow_rotation=0,piece_instance_id=f'rare:{i}') for i in range(32)]
    families,_=source_families(expand_piece_groups(rows))
    candidates=row_patterns(families,10,10,.5,False,time.monotonic()+2,limit=2)
    assert all(any(r['column'].counts[g] for r in candidates) for g in range(32))


def test_missing_corner_is_not_fabricated_as_a_regular_row():
    from almdina_erp.tests.test_alns_recalculation import mixed_fixture
    from almdina_erp.almdina_erp.domain.cutting.shelf_layout_pricing import price_shelf_layout
    _,sources,plan=mixed_fixture()
    incomplete=deepcopy(plan)
    incomplete['sheets'][-1]['pieces']=[]
    trial,trace=price_shelf_layout(incomplete,plan,sources,10,10,.5,deadline=time.monotonic()+1,
        solver=lambda *a,**k:None,min_remnant_m2=0)
    assert trial is None and trace['status']=='unsupported_pending'


def test_pattern_dominance_keeps_coverage_and_replaces_a_longer_network():
    sources=expand_piece_groups([dict(width_cm=3,length_cm=3,qty=2,piece_instance_id='shared')])
    pool=pool_for(sources)
    bad=dict(sheet_no=1,w=10,h=10,pieces=[make_placed_piece(p,i*4,0,3,3,False) for i,p in enumerate(sources)])
    good=dict(sheet_no=1,w=10,h=10,pieces=[make_placed_piece(p,i*3.5,0,3,3,False) for i,p in enumerate(sources)])
    assert pool.add(bad,'bad')==0
    before=pool.patterns[0].column.cutter_units
    assert pool.add(good,'good')==0
    assert len(pool.patterns)==1 and pool.patterns[0].column.cutter_units<before
    assert pool.add(bad,'old_alias')==0
    rebuilt=pool.reconstruct((1,),dict(sheets=[bad],unplaced=[]))
    assert rebuilt is not None and not validate_plan(rebuilt,sources,10,10,kerf_cm=.5)


def test_optional_refinement_exception_preserves_completed_baseline(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import pattern_layout_search as search
    rows,_,plan=fixture('grid')
    cmd=command(rows,seconds=0)
    expected=optimize_order_plan(cmd,engine=FrozenEngine(plan))
    def fail(*a,**kw):
        raise RuntimeError('isolated optional phase')
    monkeypatch.setattr(search,'refine_pattern_layout',fail)
    cmd=replace(cmd,optimizer=replace(cmd.optimizer,pattern_search_budget_sec=1))
    result=optimize_order_plan(cmd,engine=FrozenEngine(plan))
    assert result.snapshot['validation']['is_valid']
    assert result.snapshot['smart_search']['pattern_search']['stop']=='refinement_error'
    assert [s['pieces'] for s in result.snapshot['sheets']]==[s['pieces'] for s in expected.snapshot['sheets']]
