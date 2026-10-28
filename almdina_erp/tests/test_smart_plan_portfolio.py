"""Portfolio contracts: genuine geometry diversity, bounded warm search and export."""
from copy import deepcopy
import pytest
from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature


def problem():
    return expand_piece_groups([dict(width_cm=w,length_cm=h,qty=1,allow_rotation=1)
        for w,h in [(40,30),(30,20),(50,15),(18,45),(25,25)]])


def test_distinct_completed_plans_and_best_retention():
    pieces=problem()
    plan=opt.smart_search(pieces,100,100,.3,time_limit_sec=.6)
    candidates=plan['smart_candidates']
    assert 2<=len(candidates)<=5
    signatures=[geometry_signature(c) for c in candidates]
    assert len(signatures)==len(set(signatures))
    assert tuple(plan['industrial_rank'])==min(tuple(p['industrial_rank']) for p in candidates)
    for p in candidates:
        assert not validate_plan(p,pieces,100,100,kerf_cm=.3)
        assert not placement_permission_errors(p,pieces,mirroring_allowed=False)


def test_signature_ignores_names_but_retains_identity_holes_and_transforms():
    plan=opt.auto_fast(problem(),100,100,.3)
    same=deepcopy(plan)
    same.update(method_key='Another engine',method_label='Anything',attempts=999,score=100)
    for sheet in same['sheets']:
        sheet['sheet_label']='Another name'
        sheet['pieces'].reverse()
        for p in sheet['pieces']:
            p.update(label='Display only',notes='memo')
    assert geometry_signature(same)==geometry_signature(plan)
    for key,value in [('id',999),('x',.01),('mirrored',True),('glass_hole_local_mm',[[1,1],[2,1],[2,2],[1,2]])]:
        changed=deepcopy(plan)
        changed['sheets'][0]['pieces'][0][key]=value
        assert geometry_signature(changed)!=geometry_signature(plan)


def test_continuation_uses_warm_candidates_even_when_no_search_time_remains(monkeypatch):
    pieces=problem()
    previous=opt.smart_search(pieces,100,100,.3,time_limit_sec=.4)
    monkeypatch.setattr(opt,'auto_fast',lambda *a,**kw:pytest.fail('warm search restarted Auto'))
    result=opt.smart_search(pieces,100,100,.3,time_limit_sec=0,seed_plans=tuple(previous['smart_candidates']),search_round=1)
    assert tuple(result['industrial_rank'])<=tuple(previous['industrial_rank'])
    assert geometry_signature(previous) in {geometry_signature(c) for c in result['smart_candidates']}


def test_preview_session_candidates_roundtrip_without_changing_v1_settings_hash():
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import CuttingPlanPreviewSession
    candidate={'candidate_id':'server-id','snapshot':{'sheets':[]}}
    session=CuttingPlanPreviewSession('token','DCO','user','CP','modified','input','settings',{}, {},'now',
        candidates={'server-id':candidate},search_round=1,source_revision=2,expires_at='later')
    assert CuttingPlanPreviewSession.from_cache_value(session.as_cache_value())==session
