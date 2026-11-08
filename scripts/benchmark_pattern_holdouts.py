"""Sequential independent holdouts; real Application and JS/Strict roundtrips."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--budget',type=float,default=2.)
    args=parser.parse_args()
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    inputs=Path(args.inputs)
    cases=json.loads((inputs/'index.json').read_text(encoding='utf-8'))
    records=[]
    for position,item in enumerate(cases):
        source=inputs/item['file']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Changed holdout input')
        settings=json.loads(source.read_text(encoding='utf-8'))['test_settings']
        arms=[('alns',args.budget,0.),('patterns',args.budget,args.budget),
              ('equal_total_alns',2*args.budget,0.)]
        if position%2:
            arms.reverse()
        for arm,budget,patterns in arms:
            target=output/f'{item["case"]}-{arm}.json'
            command=[sys.executable,str(ROOT/'scripts/benchmark_alns_ui.py'),'--worker',
                '--case',item['case'],'--input',str(source),'--budget',str(budget),
                '--refinement',str(args.budget),'--patterns',str(patterns),
                '--trim-mm',str(settings['trim_mm']),'--kerf-mm',str(settings['kerf_mm']),
                '--strict','--output',str(target)]
            if not settings['allow_mirroring']:
                command.append('--no-mirroring')
            try:
                result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180)
                record=dict(case=item['case'],arm=arm,returncode=result.returncode,file=target.name,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None,
                    stderr=result.stderr)
                print(result.stdout,flush=True)
            except subprocess.TimeoutExpired as error:
                record=dict(case=item['case'],arm=arm,returncode=-1,file=target.name,error=str(error))
            records.append(record)
            (output/'index.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    if any(r['returncode'] for r in records):
        raise SystemExit(1)


if __name__=='__main__':
    main()
