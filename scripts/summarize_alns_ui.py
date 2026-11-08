"""Audit recorded Recalculate ALNS runs and draw actual material outlines."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import html
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_alns import metrics
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import material_signature

EVIDENCE = ROOT/'docs/evidence/alns-ui'


def normalized_manifest(manifest):
    return {key.replace('\\','/'): value for key,value in manifest.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', default='final-matrix')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    cohort = EVIDENCE/args.cohort
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    frozen = normalized_manifest(json.loads((EVIDENCE/'frozen-source-manifest.json').read_text(encoding='utf-8')))
    for name, expected in frozen.items():
        if hashlib.sha256((EVIDENCE/'source-snapshot'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Changed frozen source: '+name)
    index = json.loads((cohort/'index.json').read_text(encoding='utf-8'))
    rows, results, groups = [], {}, defaultdict(list)
    strict_count = 0
    for record in index:
        if record['returncode']:
            raise ValueError('Failed worker: '+record['file'])
        payload = (cohort/record['file']).read_bytes()
        if hashlib.sha256(payload).hexdigest() != record['sha256']:
            raise ValueError('Changed observation: '+record['file'])
        run = json.loads(payload)
        if normalized_manifest(run['source_manifest']) != frozen:
            raise ValueError('Observation source differs from frozen source: '+record['file'])
        if not run['valid'] or not run['strict'] or any(not check['passed'] for check in run['strict']):
            raise ValueError('Invalid geometry or failed/missing strict roundtrip: '+record['file'])
        case = str(record['case'])
        source = EVIDENCE/f'input-{case}.json'
        if not source.exists():
            source = ROOT/f'docs/evidence/alns-study/input-{case}.json'
        if hashlib.sha256(source.read_bytes()).hexdigest() != run['input_sha256']:
            raise ValueError('Input changed: '+case)
        actual = metrics(run['snapshot'],run['kerf_mm']/10)
        if actual != dict(run['final'],cutter_profile=tuple(run['final']['cutter_profile'])):
            raise ValueError('Stored metrics do not match snapshot: '+record['file'])
        strict_count += len(run['strict'])
        row = dict(case=case,arm=record['arm'],repeat=record['repeat'],boards=actual['boards'],
            pieces=actual['pieces'],remnant_m2=actual['reusable_m2'],cutter_mm=actual['cutter_profile'][0],
            segments=actual['cutter_profile'][1],family_splits=actual['family_splits'],
            wall_sec=run['wall'],native_budget_sec=run['budget'],alns_allowance_sec=run['refinement'],
            physical_gallery=len({material_signature(p) for p in run['gallery']}),
            strict_roundtrips=len(run['strict']),peak_rss_kib=run['peak_rss_kib'])
        rows.append(row)
        groups[(case,record['arm'])].append(row)
        results[(case,record['arm'],record['repeat'])] = run
    comparisons = []
    for (case,arm,repeat), run in results.items():
        if arm != 'alns':
            continue
        for control in ('native','equal_total_native'):
            baseline = results[(case,control,repeat)]
            before, after = final_system_sort_keys([baseline['snapshot'],run['snapshot']])
            comparisons.append(dict(case=case,repeat=repeat,control=control,
                comparison='better' if after<before else 'worse' if after>before else 'equal'))
    reference = {}
    for case in ('108','154'):
        inputs=json.loads((EVIDENCE/f'input-{case}.json').read_text(encoding='utf-8'))
        chosen=results.get((case,'alns',0))
        if chosen is None:
            continue
        new=metrics(chosen['snapshot'],.5)
        designer=inputs['designer']
        reference[case]=dict(exact_shape_inventory_equal=inputs['exact_shape_inventory_equal'],
            designer_remnant_m2=designer['largest_remnant_m2'],new_remnant_m2=new['reusable_m2'],
            designer_cutter_mm=designer['cut_profile'][0],new_cutter_mm=new['cutter_profile'][0],
            designer_segments=designer['cut_profile'][1],new_segments=new['cutter_profile'][1],
            remnant_gain_percent=100*(new['reusable_m2']/designer['largest_remnant_m2']-1),
            network_length_difference_mm=new['cutter_profile'][0]-designer['cut_profile'][0])
        render(case,[('Supplied system DXF',inputs['system']['plan']),
            ('Designer reference DXF',designer['plan']),('ALNS: repetition 0',chosen['snapshot'])],output)
    summary=dict(observations=len(rows),valid=len(rows),strict_roundtrips=strict_count,
        frozen_source_files=len(frozen),comparisons=comparisons,designer_comparison=reference,
        groups=[dict(case=key[0],arm=key[1],remnants=sorted({r['remnant_m2'] for r in values}),
                     cutter_mm=sorted({r['cutter_mm'] for r in values}),
                     segments=sorted({r['segments'] for r in values}),wall_sec=[r['wall_sec'] for r in values])
                for key,values in groups.items()])
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if rows:
        with (output/'observations.csv').open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in {'groups','comparisons'}},indent=2))


def render(case, plans, output):
    max_boards=max(len(p['sheets']) for _,p in plans)
    height=125+((max_boards+1)//2)*285
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="990" height="{height}" viewBox="0 0 990 {height}">',
         '<rect width="100%" height="100%" fill="#f5f7fa"/>',
         '<style>text{font-family:Arial,sans-serif;fill:#19334a;font-size:11px}</style>',
         f'<text x="20" y="26" font-size="19">Order {html.escape(case)}: actual material outlines, Kerf 5 mm</text>',
         '<text x="20" y="46">Reference layers interpreted as material at user request. 108 notch depths differ by 1 mm.</text>']
    drawing=[]
    for column,(label,plan) in enumerate(plans):
        x0=20+column*325
        actual=metrics(plan,.5)
        svg.append(f'<text x="{x0}" y="75" font-size="14">{html.escape(label)}</text>')
        svg.append(f'<text x="{x0}" y="94">{actual["boards"]} boards | remnant {actual["reusable_m2"]:.6f} m²</text>')
        svg.append(f'<text x="{x0}" y="111">Cutter {actual["cutter_profile"][0]/1000:.4f} m | {actual["cutter_profile"][1]} segments</text>')
        panel=dict(label=label,metrics=actual,sheets=[])
        for index,sheet in enumerate(plan['sheets']):
            x,y=x0+(index%2)*150,130+(index//2)*285
            svg.append(f'<rect x="{x}" y="{y}" width="{sheet["w"]}" height="{sheet["h"]}" fill="white" stroke="#18364c" stroke-width=".7"/>')
            drawing_sheet=dict(x=x,y=y,w=sheet['w'],h=sheet['h'],polygons=[])
            for piece in sheet['pieces']:
                polygon=piece.get('placement_outline_cm') or material_outline_cm(piece)
                if polygon is None:
                    raise ValueError('Cannot render unproven outline')
                key=str((piece.get('piece_type'),tuple(sorted((round(piece['w'],3),round(piece['h'],3))))))
                color='#'+''.join(f'{140+b%85:02x}' for b in hashlib.sha256(key.encode()).digest()[:3])
                points=' '.join(f'{x+a:.4f},{y+b:.4f}' for a,b in polygon)
                svg.append(f'<polygon points="{points}" fill="{color}" stroke="#355064" stroke-width=".35"><title>{html.escape(key)}</title></polygon>')
                drawing_sheet['polygons'].append(dict(points=polygon,color=color))
            svg.append(f'<text x="{x}" y="{y+sheet["h"]+17}">Board {index+1}: {len(sheet["pieces"])} pieces</text>')
            panel['sheets'].append(drawing_sheet)
        drawing.append(panel)
    svg.append('</svg>')
    path=output/f'comparison-{case}.svg'
    path.write_text('\n'.join(svg),encoding='utf-8')
    ET.parse(path)
    (output/f'drawing-{case}.json').write_text(json.dumps(dict(case=case,width=990,height=height,panels=drawing),indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
