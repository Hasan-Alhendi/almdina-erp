"""Offline Direct-Kerf research; no production wiring or new packing strategy.

Run from the repository root. Synthetic identities/all-rotation source geometry
are explicit in the fixture. Worker RSS is measured in separate processes;
retained payload bytes are not a bound on whole-process RSS.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.evaluation import (
    evaluate_plan, placement_permission_errors, validate_plan,
)
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import (
    geometry_signature, manufacturing_export_rejection,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups

FIXTURE = Path(__file__).resolve().parents[1] / 'almdina_erp/tests/fixtures/direct_kerf_research.json'


class PairCollector:
    """Bottom-key bounded sample of attempts, not a raw-rank shortlist.

    Keys describe attempts, not complete geometry. Full geometry deduplication
    happens offline. No unbounded set of rejected keys or payloads is retained.
    """
    def __init__(self, limit=16, byte_limit=16 * 1024 * 1024):
        if limit < 1 or byte_limit < 1:
            raise ValueError('Positive sample and byte limits required')
        self.limit, self.byte_limit = limit, byte_limit
        self.entries = {}
        self.bytes = 0
        self.counts = dict(captured=0, attempt_duplicates=0, capacity_rejected=0,
                           oversized=0, evicted=0)

    def __call__(self, direct, expanded, context):
        self.counts['captured'] += 1
        key = hashlib.sha256(repr((context['method_key'], context['ordering_strategy'],
                                  context['piece_ids'])).encode()).hexdigest()
        if key in self.entries:
            self.counts['attempt_duplicates'] += 1
            return
        if len(self.entries) >= self.limit and key >= max(self.entries):
            self.counts['capacity_rejected'] += 1
            return
        # JSON bytes provide detached, immutable retention with exact payload
        # accounting. Stop encoding oversize pairs before building a huge string.
        payload = bytearray()
        for chunk in json.JSONEncoder(separators=(',', ':')).iterencode(
                dict(direct=direct, expanded=expanded, context=context)):
            chunk = chunk.encode()
            if len(payload) + len(chunk) > self.byte_limit:
                self.counts['oversized'] += 1
                return
            payload.extend(chunk)
        payload = bytes(payload)
        victims, remaining = [], self.bytes
        for worst in sorted(self.entries, reverse=True):
            if len(self.entries)-len(victims) < self.limit and remaining+len(payload) <= self.byte_limit:
                break
            if key >= worst:
                self.counts['capacity_rejected'] += 1
                return
            victims.append(worst)
            remaining -= len(self.entries[worst])
        for worst in victims:
            self.bytes -= len(self.entries.pop(worst))
            self.counts['evicted'] += 1
        self.entries[key] = payload
        self.bytes += len(payload)

    def records(self):
        return [json.loads(self.entries[key]) for key in sorted(self.entries)]


def peak_rss_kib():
    # getrusage can retain the pre-exec parent's high-water mark on Linux.
    # VmHWM belongs to this worker's current address space.
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmHWM:'):
            return int(line.split()[1])
    raise RuntimeError('Linux /proc VmHWM is required for isolated RSS measurement')


def case_data(name):
    case = json.loads(FIXTURE.read_text())['cases'][name]
    rows = [dict(width_cm=w, length_cm=h, qty=q, allow_rotation=1,
                 piece_type='Regular', piece_instance_id=f'smart:{i}')
            for i, (w, h, q) in enumerate(case['rows'], 1)]
    return case, rows, expand_piece_groups(rows)


def valid(plan, pieces, width, height, kerf):
    return not (validate_plan(plan, pieces, width, height, kerf_cm=kerf)
                or placement_permission_errors(plan, pieces, mirroring_allowed=False)
                or manufacturing_export_rejection(plan))


def metrics(plan):
    """Measured adjacency alignment and size splits; no composite score."""
    aligned = adjacent = 0
    groups = {}
    for si, sheet in enumerate(plan['sheets']):
        ps = sheet['pieces']
        for i, p in enumerate(ps):
            size = tuple(sorted((round(p['w'], 5), round(p['h'], 5))))
            groups.setdefault(size, [0, set()])
            groups[size][0] += 1
            groups[size][1].add(si)
            for q in ps[i+1:]:
                dx = max(q['x']-p['x']-p['w'], p['x']-q['x']-q['w'])
                dy = max(q['y']-p['y']-p['h'], p['y']-q['y']-q['h'])
                if (abs(dx-.5) < 1e-5 and dy < 0) or (abs(dy-.5) < 1e-5 and dx < 0):
                    adjacent += 1
                    axis, dim = ('y', 'h') if abs(dx-.5) < 1e-5 else ('x', 'w')
                    aligned += int(abs(p[axis]-q[axis]) < 1e-5 or
                                   abs(p[axis]+p[dim]-q[axis]-q[dim]) < 1e-5)
    repeated = [size for size, (n, _) in groups.items() if n > 1]
    small = min(repeated, key=lambda size: (size[0]*size[1], size)) if repeated else None
    return dict(smallest_repeated_size=small,
                small_piece_board_splits=len(groups[small][1])-1 if small else 0,
                boards=len(plan['sheets']), unplaced=len(plan.get('unplaced') or []),
                rank=list(plan['industrial_rank']), industrial=plan['industrial_metrics'],
                aligned=aligned, adjacent=adjacent,
                alignment_ratio=aligned/adjacent if adjacent else None,
                group_splits=sum(len(sheets)-1 for n, sheets in groups.values() if n > 1))


def evaluated(raw, context, pieces, width, height):
    # evaluate_plan reflects Y in place. Never evaluate a stored object twice.
    plan = evaluate_plan(deepcopy(raw), pieces, width, height, context['method_key'],
                         context['method_key'], context['complexity'])
    plan['ordering_strategy'] = context['ordering_strategy']
    return opt.enrich_plan_metrics(plan, context['method_key'], 'CNC Router')


def finish(plan, pieces, width, height, seconds):
    return opt._finish_plan_search(deepcopy(plan), pieces, width, height, .5,
        'CNC Router', seconds, False,
        dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09),
        require_importable_geometry=True)


def strict_roundtrip(plan, rows, full_width, full_height, directory):
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    snapshot = deepcopy(plan)
    snapshot.update(full_board_width_cm=full_width, full_board_length_cm=full_height,
                    kerf_cm=.5, kerf_mm=5, trim_cm=.3, machine_type='CNC Router',
                    applied_trim_width_cm=.3, applied_trim_length_cm=.3)
    imported = import_saved_plan(snapshot, rows, export_real_js(snapshot, directory))
    before = sorted((p['piece_instance_id'] for s in snapshot['sheets'] for p in s['pieces']))
    after = sorted((p['piece_instance_id'] for s in imported['sheets'] for p in s['pieces']))
    if before != after or len(imported['sheets']) != len(plan['sheets']):
        raise AssertionError('Strict import lost identity or board count')
    expected = sorted(sorted((round(p['x'], 4), round(p['y'], 4), round(p['w'], 4), round(p['h'], 4))
                             for p in s['pieces']) for s in snapshot['sheets'])
    actual = sorted(sorted((round(p['x'], 4), round(p['y'], 4), round(p['w'], 4), round(p['h'], 4))
                           for p in s['pieces']) for s in imported['sheets'])
    if expected != actual:
        raise AssertionError('Strict import changed material placements')


def worker(args):
    case, rows, pieces = case_data(args.case)
    width, height = case['width']-.6, case['height']-.6
    collector = PairCollector(args.limit)
    start, cpu = time.perf_counter(), time.process_time()
    kwargs = dict(discarded_direct_callback=collector) if args.mode == 'capture' else {}
    plan = opt.smart_search(pieces, width, height, .5, 'CNC Router', args.budget, **kwargs)
    elapsed, cpu = time.perf_counter()-start, time.process_time()-cpu
    result = dict(case=args.case, mode=args.mode, budget=args.budget, elapsed=elapsed,
        cpu=cpu, rss_kib=peak_rss_kib(),
        overrun=max(0, elapsed-args.budget), metrics=metrics(plan),
        valid=valid(plan, pieces, width, height, .5), counts=collector.counts,
        retained=len(collector.entries), retained_bytes=collector.bytes,
        plan=plan, pairs=collector.records())
    Path(args.output).write_text(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--finish-input')
    parser.add_argument('--case', default='243')
    parser.add_argument('--mode', choices=['baseline', 'capture'], default='baseline')
    parser.add_argument('--budget', type=float, default=5)
    parser.add_argument('--finish-seconds', type=float, default=.5)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--limit', type=int, choices=[4, 8, 16], default=16)
    parser.add_argument('--cases', nargs='+', default=['107', '232', '243', '3640', '3687', '235', '325', '3688', '3700'])
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if args.finish_input:
        case, _, pieces = case_data(args.case)
        plan = json.loads(Path(args.finish_input).read_text())
        start, cpu = time.perf_counter(), time.process_time()
        plan = finish(plan, pieces, case['width']-.6, case['height']-.6, args.finish_seconds)
        elapsed, cpu = time.perf_counter()-start, time.process_time()-cpu
        Path(args.output).write_text(json.dumps(dict(plan=plan, costs=dict(elapsed=elapsed, cpu=cpu,
            overrun=max(0, elapsed-args.finish_seconds),
            rss_kib=peak_rss_kib()))))
        return
    observations, comparisons, sensitivity = [], [], []
    for name in args.cases:
        case, rows, pieces = case_data(name)
        width, height = case['width']-.6, case['height']-.6
        for rep in range(args.repeats):
            runs = {}
            for mode in (['baseline', 'capture'] if rep % 2 == 0 else ['capture', 'baseline']):
                with tempfile.TemporaryDirectory() as td:
                    output = Path(td)/'worker.json'
                    subprocess.run([sys.executable, __file__, '--worker', '--case', name,
                        '--mode', mode, '--budget', str(args.budget), '--limit', str(args.limit),
                        '--output', str(output)], check=True)
                    runs[mode] = json.loads(output.read_text())
                observations.append({k: v for k, v in runs[mode].items() if k not in {'plan', 'pairs'}} | dict(repeat=rep))
            # Nested bottom-key subsets use the SAME captured attempt stream.
            for limit in [4, 8, 16]:
                if limit <= args.limit:
                    subset = runs['capture']['pairs'][:limit]
                    sensitivity.append(dict(case=name, repeat=rep, limit=limit, retained=len(subset),
                        payload_bytes=sum(len(json.dumps(p, separators=(',', ':')).encode()) for p in subset)))
            seen = set()
            baseline = runs['baseline']['plan']
            for index, pair in enumerate(runs['capture']['pairs']):
                plans = {kind: evaluated(pair[kind], pair['context'], pieces, width, height)
                         for kind in ['direct', 'expanded']}
                signature = tuple(geometry_signature(plans[k]) for k in ['direct', 'expanded'])
                if signature in seen:
                    comparisons.append(dict(case=name, repeat=rep, index=index, duplicate=True))
                    continue
                seen.add(signature)
                if signature[0] == signature[1]:
                    comparisons.append(dict(case=name, repeat=rep, index=index, identical=True))
                    continue
                before = {kind: metrics(p) for kind, p in plans.items()}
                validity = {kind: valid(p, pieces, width, height, .5) for kind, p in plans.items()}
                costs = {}
                for kind in (['direct', 'expanded'] if (rep+index) % 2 == 0 else ['expanded', 'direct']):
                    if not validity[kind]:
                        continue
                    with tempfile.TemporaryDirectory() as td:
                        source, output = Path(td)/'source.json', Path(td)/'finished.json'
                        source.write_text(json.dumps(plans[kind]))
                        subprocess.run([sys.executable, __file__, '--finish-input', str(source),
                            '--case', name, '--finish-seconds', str(args.finish_seconds),
                            '--output', str(output)], check=True)
                        completed = json.loads(output.read_text())
                    plans[kind], costs[kind] = completed['plan'], completed['costs']
                    validity[kind] = valid(plans[kind], pieces, width, height, .5)
                after = {kind: metrics(p) for kind, p in plans.items()}
                d, e = after['direct'], after['expanded']
                # Nomination requires no extra boards/remnant loss plus a real
                # organization improvement; raw industrial rank is insufficient.
                def organized(a, b):
                    return (a['boards'] <= b['boards'] and a['unplaced'] == b['unplaced'] == 0
                        and a['industrial']['largest_reusable_free_area_m2']+1e-6 >= b['industrial']['largest_reusable_free_area_m2']
                        and a['group_splits'] <= b['group_splits']
                        and (a['alignment_ratio'] or 0)+1e-6 >= (b['alignment_ratio'] or 0)
                        and (a['group_splits'] < b['group_splits'] or
                             (a['alignment_ratio'] or 0) > (b['alignment_ratio'] or 0)+1e-6))
                nominated = all(validity.values()) and organized(d, e) and organized(d, metrics(baseline))
                strict = None
                if nominated:
                    try:
                        with tempfile.TemporaryDirectory() as td:
                            strict_roundtrip(plans['direct'], rows, case['width'], case['height'], Path(td))
                        strict = True
                    except Exception as exc:
                        strict = str(exc)
                comparisons.append(dict(case=name, repeat=rep, index=index, before=before, after=after,
                    valid=validity, costs=costs, nominated=nominated, strict=strict,
                    beats_baseline_rank=d['rank'] < list(baseline['industrial_rank'])))
            Path(args.output).write_text(json.dumps(dict(observations=observations, comparisons=comparisons, sensitivity=sensitivity), indent=2))
            print(name, rep, 'boards baseline/capture', *(runs[m]['metrics']['boards'] for m in ['baseline', 'capture']),
                  'captured', runs['capture']['counts']['captured'], 'retained', runs['capture']['retained'], flush=True)


if __name__ == '__main__':
    main()
