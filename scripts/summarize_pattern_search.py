"""Audit frozen pattern-search observations; report every control and tradeoff."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_alns import metrics
from scripts.summarize_alns_ui import normalized_manifest, render
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys

EVIDENCE = ROOT/'docs/evidence/pattern-search'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = normalized_manifest(json.loads((EVIDENCE/'frozen-source-manifest.json').read_text()))
    for name, expected in frozen.items():
        assert digest(EVIDENCE/'source-snapshot'/name) == expected, name
        assert digest(ROOT/name) == expected, 'Live source changed: '+name
    output = EVIDENCE/'report'
    output.mkdir(exist_ok=True)
    rows, results, groups, comparisons = [], {}, defaultdict(list), []
    for cohort in ('final-matrix', 'final-holdouts-certified'):
        index = json.loads((EVIDENCE/cohort/'index.json').read_text())
        assert len(index) == 24, (cohort, len(index))
        for record in index:
            name = record['file']
            path = EVIDENCE/cohort/name
            assert record['returncode'] == 0, (cohort, name, 'failed worker')
            assert digest(path) == record['sha256'], name
            raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
            if 'uncompressed_sha256' in record:
                assert hashlib.sha256(raw).hexdigest() == record['uncompressed_sha256'], name
            run = json.loads(raw)
            assert normalized_manifest(run['source_manifest']) == frozen, name
            assert run['valid'] and run['strict'], name
            assert len(run['strict']) == len(run['gallery']), name
            assert all(s['passed'] for s in run['strict']), name
            assert all(p['validation']['is_valid'] for p in run['gallery']), name
            case, arm, repeat = str(record['case']), record['arm'], record.get('repeat', 0)
            if cohort == 'final-matrix':
                source = ROOT/f'docs/evidence/alns-ui/input-{case}.json'
                if not source.exists():
                    source = ROOT/f'docs/evidence/alns-study/input-{case}.json'
            else:
                source = EVIDENCE/f'holdout-inputs-final/{case}.json'
            assert digest(source) == run['input_sha256'], name
            actual = metrics(run['snapshot'], run['kerf_mm']/10)
            assert actual == dict(run['final'], cutter_profile=tuple(run['final']['cutter_profile'])), name
            diagnostic = run['snapshot'].get('smart_search', {}).get('pattern_search', {})
            assert diagnostic.get('stop') != 'refinement_error' and not diagnostic.get('projection_errors'), name
            assert not any(str(s.get('status', '')).startswith('solver_error') for s in diagnostic.get('row_pricing', [])), name
            row = dict(cohort=cohort, case=case, arm=arm, repeat=repeat,
                boards=actual['boards'], pieces=actual['pieces'], unplaced=actual['unplaced'],
                remnant_m2=actual['reusable_m2'], cutter_mm=actual['cutter_profile'][0],
                segments=actual['cutter_profile'][1], family_splits=actual['family_splits'],
                native_sec=run['budget'], alns_sec=run['refinement'], patterns_sec=run['patterns'],
                allocated_sec=run['budget']+run['refinement']+run['patterns'], wall_sec=run['wall'],
                peak_rss_kib=run['peak_rss_kib'], strict_roundtrips=len(run['strict']))
            rows.append(row)
            groups[(cohort, case, arm)].append(row)
            results[(cohort, case, arm, repeat)] = run
    for (cohort, case, arm, repeat), run in results.items():
        if arm != 'patterns':
            continue
        for control in ('alns', 'equal_total_alns'):
            baseline = results[(cohort, case, control, repeat)]
            before, after = final_system_sort_keys([baseline['snapshot'], run['snapshot']])
            comparisons.append(dict(cohort=cohort, case=case, repeat=repeat, control=control,
                comparison='better' if after < before else 'worse' if after > before else 'equal',
                remnant_difference_m2=run['final']['reusable_m2']-baseline['final']['reusable_m2'],
                network_difference_mm=run['final']['cutter_profile'][0]-baseline['final']['cutter_profile'][0]))
    designer = {}
    for case in ('108', '154', '263', '298'):
        plans = [(label, results[('final-matrix', case, arm, 0)]['snapshot'])
                 for arm, label in [('alns', 'Previous stages: N10 + ALNS10'),
                                    ('equal_total_alns', 'Equal budget: N20 + ALNS10'),
                                    ('patterns', 'New: N10 + ALNS10 + Patterns10')]]
        render(case, plans, output)
        svg = output/f'comparison-{case}.svg'
        svg.write_text(svg.read_text(encoding='utf-8').replace(
            'Reference layers interpreted as material at user request. 108 notch depths differ by 1 mm.',
            'Cold repetition 0. Material geometry; measured cutter network is not CNC sequence certification.'), encoding='utf-8')
        if case in ('108', '154'):
            inputs = json.loads((ROOT/f'docs/evidence/alns-ui/input-{case}.json').read_text(encoding='utf-8'))
            reference = inputs['designer']
            designer[case] = dict(exact_shape_inventory_equal=inputs['exact_shape_inventory_equal'],
                reference_remnant_m2=reference['largest_remnant_m2'],
                reference_cutter_mm=reference['cut_profile'][0], reference_segments=reference['cut_profile'][1],
                new_remnants_m2=[r['remnant_m2'] for r in groups[('final-matrix', case, 'patterns')]],
                caveat='108 has 1 mm notch differences and different stock inset; not a controlled algorithm-only gain' if case=='108' else '')
    summary = dict(observations=len(rows), valid=len(rows),
        strict_roundtrips=sum(r['strict_roundtrips'] for r in rows), frozen_source_files=len(frozen),
        controls='Same frozen 2.3 source with new stage disabled, not a literal 2.2 checkout. Sequential cold workers; allocated budgets are cooperative, actual wall reported.',
        comparisons=comparisons, designer_comparison=designer,
        groups=[dict(cohort=k[0], case=k[1], arm=k[2],
            boards=sorted({r['boards'] for r in values}),
            remnants=sorted({r['remnant_m2'] for r in values}),
            cutter_mm=sorted({r['cutter_mm'] for r in values}), segments=sorted({r['segments'] for r in values}),
            wall_sec=[r['wall_sec'] for r in values]) for k, values in groups.items()])
    (output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (output/'observations.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    counts = defaultdict(int)
    for row in comparisons:
        counts[(row['cohort'], row['control'], row['comparison'])] += 1
    print(json.dumps(dict(observations=len(rows), strict_roundtrips=summary['strict_roundtrips'],
        comparisons={str(k): v for k, v in counts.items()}), indent=2))


if __name__ == '__main__':
    main()
