"""Opt-in observation must never become a new production candidate path."""
from copy import deepcopy
import json

import pytest

from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting import kerf_layout, registry
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, create_sheet, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
from scripts.research_direct_kerf import PairCollector, evaluated, valid


def pieces():
    return expand_piece_groups([dict(width_cm=20, length_cm=30, qty=3, allow_rotation=1)])


def test_raw_capture_does_not_repack_or_share_selected_data():
    calls, captured = [], []
    def packer(ps, w, h, kerf):
        calls.append(kerf)
        sheet = create_sheet(1, w, h)
        sheet['pieces'] = [make_placed_piece(ps[0], 1, 2, 20, 30, False)]
        return dict(sheets=[sheet], unplaced=[])
    ps = pieces()[:1]
    expected = kerf_layout.pack_with_stable_kerf(packer, ps, 100, 100, .5, ())
    assert calls == [.5, 0]
    calls.clear()
    def capture(direct, expanded):
        captured.append((direct, expanded))
        direct['sheets'][0]['pieces'][0]['x'] = 99
        expanded['sheets'][0]['pieces'][0]['y'] = 99
    actual = kerf_layout.pack_with_stable_kerf(packer, ps, 100, 100, .5, (),
                                             discarded_direct_callback=capture)
    assert calls == [.5, 0]
    assert len(captured) == 1
    assert actual == expected
    assert captured[0][0]['sheets'] is not captured[0][1]['sheets']


@pytest.mark.parametrize('kerf,expansion', [(0, 'unused'), (.5, None)])
def test_no_discarded_direct_when_zero_or_expansion_fails(monkeypatch, kerf, expansion):
    if kerf:
        monkeypatch.setattr(kerf_layout, 'expand_plan_kerf', lambda *a, **kw: expansion)
    observed = []
    kerf_layout.pack_with_stable_kerf(lambda *a: dict(sheets=[], unplaced=[]), [], 10, 10, kerf, (),
                                    discarded_direct_callback=lambda *a: observed.append(a))
    assert not observed


def test_direct_winner_is_not_reported_as_discarded(monkeypatch):
    direct = dict(sheets=[{'pieces': []}], unplaced=[])
    monkeypatch.setattr(kerf_layout, 'expand_plan_kerf',
                        lambda *a, **kw: dict(sheets=[{}, {}], unplaced=[]))
    observed = []
    assert kerf_layout.pack_with_stable_kerf(lambda *a: deepcopy(direct), [], 10, 10, .5, (),
        discarded_direct_callback=lambda *a: observed.append(a)) == direct
    assert not observed


@pytest.mark.parametrize('route', ['auto', 'preordered', 'deep'])
def test_capture_routes_independent_of_improvement_callback(monkeypatch, route):
    ps, records, improvements = pieces(), [], []
    def callback(*args):
        records.append(deepcopy(args))
    baseline = opt.auto_fast(ps, 80, 100, .5)
    if route == 'auto':
        result = opt.auto_fast(ps, 80, 100, .5, discarded_direct_callback=callback)
        assert result == baseline
    elif route == 'preordered':
        result = opt._run_preordered_method(ps, ps, 80, 100, .5,
            'MaxRects Contact Point', 'research', discarded_direct_callback=callback)
    else:
        # No result can improve this rank, but discarded alternatives must still
        # be observed. Deadline is constant; max_attempts bounds this test.
        baseline['industrial_rank'] = (-1,)
        baseline['attempts'] = 0
        monkeypatch.setattr(opt.time, 'monotonic', lambda: 1)
        result = opt.deep_search(ps, 80, 100, .5, initial_plan=baseline,
            max_attempts=3, candidate_callback=lambda p: improvements.append(p),
            discarded_direct_callback=callback)
        assert not improvements
    assert records
    assert all('method_key' in context and 'piece_ids' in context for _, _, context in records)
    assert 'discarded_direct' not in json.dumps(result)


def test_smart_attempt_order_and_result_unchanged_with_deterministic_clock(monkeypatch):
    original = opt._run_preordered_method
    def run(capture):
        clock, trace, records = [1.0], [], []
        def tick():
            clock[0] += .002
            return clock[0]
        def spy(*a, **kw):
            trace.append((a[4], a[5], a[6], tuple(p['id'] for p in a[0])))
            return original(*a, **kw)
        with monkeypatch.context() as m:
            m.setattr(opt.time, 'monotonic', tick)
            m.setattr(opt, '_run_preordered_method', spy)
            kwargs = dict(discarded_direct_callback=lambda *a: records.append(a)) if capture else {}
            result = opt.smart_search(pieces(), 80, 100, .5, time_limit_sec=.2, **kwargs)
        return result, trace, records
    baseline, before, _ = run(False)
    observed, after, records = run(True)
    assert records
    assert before == after
    assert observed == baseline


def test_each_offline_evaluation_uses_a_fresh_copy_and_reflects_y_once():
    ps = pieces()[:1]
    raw = dict(sheets=[dict(sheet_no=1, w=100, h=100,
        pieces=[make_placed_piece(ps[0], 1, 2, 20, 30, False)])], unplaced=[])
    original = deepcopy(raw)
    context = dict(method_key='MaxRects Best Short Side', ordering_strategy='test', complexity=3)
    first, second = [evaluated(raw, context, ps, 100, 100) for _ in range(2)]
    assert first['sheets'][0]['pieces'][0]['y'] == 68
    assert geometry_signature(first) == geometry_signature(second)
    assert raw == original
    first['sheets'][0]['pieces'][0]['y'] = -1
    assert second['sheets'][0]['pieces'][0]['y'] == 68


@pytest.mark.parametrize('limit', [4, 8, 16])
def test_collector_caps_bytes_and_count_without_geometry_work(monkeypatch, limit):
    monkeypatch.setattr(opt, 'enrich_plan_metrics', lambda *a, **kw: pytest.fail('hot-path evaluation'))
    monkeypatch.setattr('scripts.research_direct_kerf.geometry_signature',
                        lambda *a: pytest.fail('hot-path geometry signature'))
    collector = PairCollector(limit=limit, byte_limit=4096)
    raw = dict(sheets=[], unplaced=[])
    for i in range(200):
        collector(raw, raw, dict(method_key='test', ordering_strategy=str(i), piece_ids=(1, 2)))
        assert len(collector.entries) <= limit
        assert collector.bytes == sum(map(len, collector.entries.values())) <= 4096
    assert collector.counts['captured'] == 200
    assert collector.counts['capacity_rejected'] + collector.counts['evicted'] > 0
    first = collector.records()
    raw['sheets'].append({'mutated': True})
    assert collector.records() == first


def test_collector_determinism_duplicates_and_oversize():
    raw, context = dict(sheets=[], unplaced=[]), dict(method_key='a', ordering_strategy='b', piece_ids=(1,))
    a, b = PairCollector(), PairCollector()
    for collector in [a, b]:
        collector(raw, raw, context)
        collector(raw, raw, context)
        assert collector.counts['attempt_duplicates'] == 1
    assert a.entries == b.entries
    tiny = PairCollector(byte_limit=10)
    tiny(raw, raw, context)
    assert tiny.counts['oversized'] == 1 and tiny.bytes == 0 and not tiny.entries


@pytest.mark.parametrize('mutation', ['kerf', 'trim', 'rotation', 'identity', 'size'])
def test_offline_gate_rejects_manufacturing_mutations(mutation):
    ps = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=2, allow_rotation=0)])
    p = opt.auto_fast(ps, 100, 100, .5)
    assert valid(p, ps, 100, 100, .5)
    sheet = p['sheets'][0]
    one, two = sheet['pieces']
    if mutation == 'kerf':
        two.update(x=one['x']+one['w']+.1, y=one['y'])
    elif mutation == 'trim':
        one['x'] = -.1  # Outside the usable frame, so inside mandatory trim.
    elif mutation == 'rotation':
        one.update(rotated=True, w=30, h=20)
    elif mutation == 'identity':
        sheet['pieces'].pop()
    else:
        one['w'] += 1
    assert not valid(p, ps, 100, 100, .5)


def test_same_stream_sample_sensitivity_is_nested():
    collectors = [PairCollector(limit=k) for k in [4, 8, 16]]
    for i in range(100):
        for collector in collectors:
            collector({}, {}, dict(method_key='test', ordering_strategy=str(i), piece_ids=(1,)))
    assert set(collectors[0].entries) < set(collectors[1].entries) < set(collectors[2].entries)
    for c in collectors:
        assert c.counts['captured'] == len(c.entries) + c.counts['evicted'] + c.counts['capacity_rejected']


def test_captured_direct_finishes_and_roundtrips_real_js_strict_import(tmp_path):
    from scripts.research_direct_kerf import case_data, finish, strict_roundtrip
    case, rows, ps = case_data('235')
    w, h = case['width']-.6, case['height']-.6
    collector = PairCollector(4)
    opt.auto_fast(ps, w, h, .5, discarded_direct_callback=collector)
    assert collector.records()
    pair = collector.records()[0]
    raw = deepcopy(pair['direct'])
    direct = evaluated(raw, pair['context'], ps, w, h)
    assert valid(direct, ps, w, h, .5)
    direct = finish(direct, ps, w, h, .1)
    assert valid(direct, ps, w, h, .5)
    strict_roundtrip(direct, rows, case['width'], case['height'], tmp_path)
    assert raw == pair['direct']


def test_deep_without_warm_plan_captures_its_pro_initialization():
    records = []
    opt.deep_search(pieces(), 80, 100, .5, max_attempts=0,
                    discarded_direct_callback=lambda *a: records.append(a))
    assert records  # Even when no random restart can run.
