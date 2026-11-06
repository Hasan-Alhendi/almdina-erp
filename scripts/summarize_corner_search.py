"""Audit every frozen coupled-corner observation, including gallery tradeoffs."""
import csv
import argparse
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_alns import metrics
from scripts.summarize_alns_ui import render,normalized_manifest
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.optimizer import _largest_reusable_free_area

EVIDENCE=ROOT/'docs/evidence/corner-search'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def read_run(path,record):
    assert digest(path)==record['sha256'],path
    raw=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
    if 'uncompressed_sha256' in record:
        assert hashlib.sha256(raw).hexdigest()==record['uncompressed_sha256'],path
    return json.loads(raw)


def main():
    global EVIDENCE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root',default=str(EVIDENCE))
    args=parser.parse_args()
    EVIDENCE=Path(args.evidence_root)
    frozen=json.loads((EVIDENCE/'frozen-source-manifest.json').read_text())
    for name,expected in frozen.items():
        assert digest(EVIDENCE/'source-snapshot'/name)==expected,'Frozen source changed: '+name
    output=EVIDENCE/'report'
    output.mkdir(exist_ok=True)
    rows,results,groups=[],{},defaultdict(list)
    for cohort,count in (('final-main',12),('final-regular',4),('final-holdout',12)):
        index=json.loads((EVIDENCE/cohort/'index.json').read_text())
        assert len(index)==count,(cohort,len(index))
        for record in index:
            assert record['returncode']==0,record
            run=read_run(EVIDENCE/cohort/record['file'],record)
            assert normalized_manifest(run['source_manifest'])==frozen,record['file']
            assert run['valid'] and len(run['strict'])==len(run['gallery']) and run['strict'],record['file']
            assert all(check['passed'] for check in run['strict']),record['file']
            assert all(p['validation']['is_valid'] for p in run['gallery']),record['file']
            case,arm,repeat=record['case'],record['arm'],record['repeat']
            if case.startswith('holdout'):
                source=ROOT/f'docs/evidence/pattern-search/holdout-inputs-final/{case}.json'
            else:
                source=ROOT/f'docs/evidence/alns-ui/input-{case}.json'
                if not source.exists():source=ROOT/f'docs/evidence/alns-study/input-{case}.json'
            assert digest(source)==run['input_sha256'],record['file']
            actual=metrics(run['snapshot'],run['kerf_mm']/10)
            for candidate in run['gallery']:
                measured=_largest_reusable_free_area(candidate,30.,30.,.09,machine_type='CNC Router')
                assert math.isclose(measured,candidate['industrial_metrics']['largest_reusable_free_area_m2'],
                                    rel_tol=0.,abs_tol=1e-8),record['file']
            expected=run['final']
            assert all(actual[k]==v for k,v in expected.items() if k!='cutter_profile'),record['file']
            assert actual['cutter_profile'][1]==expected['cutter_profile'][1],record['file']
            # Python 3.12 compensated sum can differ from 3.11 by floating
            # roundoff for diagonal cuts. One nanometre in mm is the audit
            # tolerance; counts and source/snapshot hashes stay exact.
            assert all(math.isclose(actual['cutter_profile'][i],expected['cutter_profile'][i],abs_tol=1e-6,rel_tol=0.)
                       for i in (0,2)),record['file']
            diagnostic=run['snapshot'].get('smart_search',{}).get('corner_search',{})
            assert diagnostic.get('stop')!='refinement_error' and not diagnostic.get('projection_errors'),record['file']
            assert not str(diagnostic.get('master_status','')).startswith('solver_error'),record['file']
            assert not any(str(x.get('status','')).startswith('solver_error') for x in diagnostic.get('row_pricing',[])),record['file']
            applied=diagnostic.get('budget_sec',0.)
            row=dict(cohort=cohort,case=case,arm=arm,repeat=repeat,boards=actual['boards'],pieces=actual['pieces'],
                remnant_m2=actual['reusable_m2'],cutter_mm=actual['cutter_profile'][0],segments=actual['cutter_profile'][1],
                native_sec=run['budget'],alns_sec=run['refinement'],patterns_sec=run['patterns'],
                corners_configured_sec=run['corners'],corners_applied_sec=applied,
                allocated_sec=run['budget']+run['refinement']+run['patterns']+applied,
                wall_sec=run['wall'],peak_rss_kib=run['peak_rss_kib'],strict_roundtrips=len(run['strict']))
            rows.append(row)
            results[cohort,case,arm,repeat]=run
            groups[cohort,case,arm].append(row)
    comparisons=[]
    for (cohort,case,arm,repeat),run in results.items():
        if arm!='coupled':continue
        for control in ('prior','equal_total_prior'):
            baseline=results.get((cohort,case,control,repeat))
            if baseline is None:continue
            before,after=final_system_sort_keys([baseline['snapshot'],run['snapshot']])
            comparisons.append(dict(cohort=cohort,case=case,repeat=repeat,control=control,
                comparison='better' if after<before else 'worse' if after>before else 'equal'))
    references=[]
    for case in ('108','154'):
        inputs=json.loads((ROOT/f'docs/evidence/alns-ui/input-{case}.json').read_text(encoding='utf-8'))
        designer=inputs['designer']
        for repeat in (0,1):
            run=results['final-main',case,'coupled',repeat]
            gallery=[metrics(p,.5) for p in run['gallery']]
            feasible=[(i,m) for i,m in enumerate(gallery)
                if m['boards']<=designer['boards'] and m['reusable_m2']>=designer['largest_remnant_m2']-1e-9]
            choice=min(feasible,key=lambda pair:pair[1]['cutter_profile'][0])
            dominators=[i for i,m in feasible if m['cutter_profile'][0]<=designer['cut_profile'][0]+1e-5
                        and m['cutter_profile'][1]<=designer['cut_profile'][1]]
            references.append(dict(case=case,repeat=repeat,
                exact_shape_inventory_equal=inputs['exact_shape_inventory_equal'],
                designer_remnant_m2=designer['largest_remnant_m2'],designer_cutter_mm=designer['cut_profile'][0],
                designer_segments=designer['cut_profile'][1],default=gallery[0],
                shortest_preserving_reference_remnant_candidate=choice[0],balanced=choice[1],
                numerically_dominating_candidates=dominators,gallery=gallery,
                caveat='108 notch depths differ by 1 mm and reference uses a different stock inset; numeric comparison is not an algorithm-only controlled gain' if case=='108' else 'Exact source-shape inventory; stock inset differs'))
            if repeat==0:
                render(case,[('Previous: N10 + ALNS10 + Patterns10',results['final-main',case,'prior',0]['snapshot']),
                    ('Designer reference DXF',designer['plan']),('New default: coupled corner search',run['snapshot']),
                    (f'Shorter network: gallery candidate {choice[0]+1}',run['gallery'][choice[0]])],output)
                path=output/f'comparison-{case}.svg'
                svg=path.read_text(encoding='utf-8').replace('width="990"','width="1320"').replace('viewBox="0 0 990','viewBox="0 0 1320')
                path.write_text(svg,encoding='utf-8')
                path=output/f'drawing-{case}.json'
                drawing=json.loads(path.read_text())
                drawing['width']=1320
                path.write_text(json.dumps(drawing,indent=2),encoding='utf-8')
    summary=dict(observations=len(rows),strict_roundtrips=sum(r['strict_roundtrips'] for r in rows),
        frozen_source_files=len(frozen),strict_contract='Source family bboxes + identity inventory + actual material outer contours',
        controls='Same frozen 2.4 code with coupled stage disabled; prior stages finish first. N10 main: 30 / 40 / 40 allocated search seconds. Regular-only skips corners. Cooperative budgets; actual wall reported.',
        comparisons=comparisons,designer_comparison=references,
        groups=[dict(cohort=k[0],case=k[1],arm=k[2],boards=sorted({r['boards'] for r in values}),
            remnants_m2=sorted({r['remnant_m2'] for r in values}),cutter_mm=sorted({r['cutter_mm'] for r in values}),
            segments=sorted({r['segments'] for r in values}),wall_sec=[r['wall_sec'] for r in values]) for k,values in groups.items()])
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (output/'observations.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(dict(observations=len(rows),strict_roundtrips=summary['strict_roundtrips'],
        references=[{k:r[k] for k in ('case','repeat','numerically_dominating_candidates')} for r in references],
        comparisons=comparisons),indent=2))


if __name__=='__main__':main()
