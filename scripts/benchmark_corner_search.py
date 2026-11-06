"""Frozen sequential comparisons for coupled corners, controls and holdouts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_alns import source_manifest

EVIDENCE=ROOT/'docs/evidence/corner-search'


def manifest():
    files=source_manifest()
    for name in ('scripts/benchmark_alns_ui.py','scripts/study_designer_layout.py',
                 'almdina_erp/almdina_erp/infrastructure/frappe/cutting_plan_workspace.py'):
        files[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return {k.replace('\\','/'):v for k,v in files.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--evidence-root',default=str(EVIDENCE))
    parser.add_argument('--cohort',choices=('main','regular','holdout'),default='main')
    parser.add_argument('--output')
    parser.add_argument('--budget',type=float,default=10.)
    parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args()
    evidence=Path(args.evidence_root)
    frozen_path=evidence/'frozen-source-manifest.json'
    if args.freeze:
        assert not frozen_path.exists(),'Never overwrite a measured source freeze'
        evidence.mkdir(parents=True,exist_ok=True)
        frozen=manifest()
        frozen_path.write_text(json.dumps(frozen,indent=2),encoding='utf-8')
        for name in frozen:
            target=evidence/'source-snapshot'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes())
        print('Frozen source files:',len(frozen))
        return
    frozen=json.loads(frozen_path.read_text())
    assert manifest()==frozen,'Source changed since freeze'
    assert args.output and args.budget>0
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    cases=['108','154'] if args.cohort=='main' else ['263','298'] if args.cohort=='regular' else [f'holdout-{i:02d}' for i in range(5,9)]
    records=[]
    for repeat in range(args.repeats):
        for case in cases:
            if args.cohort=='holdout':
                source=ROOT/f'docs/evidence/pattern-search/holdout-inputs-final/{case}.json'
                settings=json.loads(source.read_text())['test_settings']
            else:
                source=ROOT/f'docs/evidence/alns-ui/input-{case}.json'
                if not source.exists():source=ROOT/f'docs/evidence/alns-study/input-{case}.json'
                settings=dict(trim_mm=0,kerf_mm=5,allow_mirroring=True)
            arms=[('prior',args.budget,0.),('coupled',args.budget,min(10.,args.budget))]
            if args.cohort!='regular':arms.append(('equal_total_prior',args.budget+min(10.,args.budget),0.))
            if repeat%2:arms.reverse()
            for arm,budget,corners in arms:
                assert manifest()==frozen,'Source changed during matrix'
                target=output/f'{case}-{arm}-r{repeat}.json'
                cmd=[sys.executable,str(ROOT/'scripts/benchmark_alns_ui.py'),'--worker',
                    '--case',case,'--input',str(source),'--budget',str(budget),
                    '--refinement',str(min(10.,args.budget)),'--patterns',str(min(10.,args.budget)),
                    '--corners',str(corners),'--strict','--trim-mm',str(settings['trim_mm']),
                    '--kerf-mm',str(settings['kerf_mm']),'--output',str(target)]
                if not settings['allow_mirroring']:cmd.append('--no-mirroring')
                try:
                    result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=180)
                    record=dict(case=case,arm=arm,repeat=repeat,returncode=result.returncode,
                        file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None,
                        stderr=result.stderr)
                    if target.exists():
                        run=json.loads(target.read_text())
                        assert {k.replace('\\','/'):v for k,v in run['source_manifest'].items()}==frozen
                        print(case,arm,repeat,round(run['wall'],3),run['final'],flush=True)
                except subprocess.TimeoutExpired as error:
                    record=dict(case=case,arm=arm,repeat=repeat,returncode=-1,file=target.name,error=str(error))
                records.append(record)
                (output/'index.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
                if record['returncode']:raise SystemExit('Worker failed; retained in index')


if __name__=='__main__':main()
