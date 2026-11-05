# ABC search: opt-in implementation, adoption not established

Baseline: `0d3cf1dbe873686134a2648df7d0dd6996b8409f`. Production defaults remain
unchanged. This branch implements the first bounded research slice, not default
activation or a claim of superiority to a commercial optimizer.

## Change contract

- Goal: test A early bounded regrouping, B topology-aware side retention and
  C original-instance rectangular grid proposals as one Smart research path.
- Domain owns proposals/scheduling; Application still owns final projection,
  centering, compaction, alignment, independent validation and selection.
- Scope: optional Python policy, Domain generators, one internal side nominee,
  Application projection, eight-arm harness and regressions. No RPC/settings/UI,
  stored schema, dependency, NC, stock, authorization, financial, approved or
  uploaded plan changes. Existing labels are reused; no new product UI strings.
- Preserve native selection when policy is absent/disabled; keep native finalists
  before real final comparison. No extra board for organization, no synthetic
  source IDs, no mutation of sources/warm plans, no weakening of Kerf/Trim or
  orientation gates. Default Stable Kerf and legacy comparator stay unchanged.
- Rollback: remove optional policy/wiring and new modules/tests; no migration.

## Implementation boundaries

`ABCSearchPolicy(schedule=True, retention=True, templates=True)` can be passed
by trusted Python callers through `OptimizerOptions.research_abc`. It is not
connected to a factory field or a browser request. Legacy callers do not receive
new keyword arguments when no policy is supplied.

A starts at the first validated native kernel during Auto seed construction,
before waiting for all Auto methods to finish, within at most 10% of
the original Domain budget by default (research policy allows at most 20%). A/C
iterators alternate attempts, including failures; at most one C result can spawn
a follow-up A iterator. Every iterator shares a 24-packing-proposal allowance;
C uses at most six. A still uses existing native MaxRects orders/heuristics.
For eligible A/C calls only, remaining Auto seed kernels also observe the shared
cooperative deadline; native/default/unsupported calls retain their original
full seed pass. B-only observes seeds without this A/C deadline change. This is
an early checkpoint slice, not a full adaptive scheduler or evidence
that the chosen 10% policy is the best schedule.

C uses at most two repeated-size/permission families and grid proposals. It
places original pieces with actual internal Kerf once and fills residual space
with existing MaxRects primitives. It cannot open more sheets than the seed.
The first cohort excludes non-Regular, protected geometry/machining, OFFCUT,
Panel Saw and orders over 64 instances. This intentionally conservative whole-
order guard is narrower than the existing general-purpose P3 neighborhood gate.

B performs at most 12 exact raw topology measurements, retaining at most three
detached side entries. Valid native completions and bounded raw batch candidates
can enter; strict full proxy-rank improvement is not required to nominate. A
lower board count invalidates side entries using more sheets. One distinct side
nominee may reach Application alongside the native finalists; the native-first
alignment time shares remain intact. After independent projection/validation,
`final_system_sort_keys` chooses the winner and at most five unique views.
Native warm seeds are retained without mutation, including those deduplicated
after projection. The side view has no guaranteed extra alignment time.

Exact raw topology is screening, not certification of final geometry. Its
measurement/copy cost consumes native elapsed time. The extra snapshot can
increase finalization cost. Keeping discovered incumbents does not guarantee
that a shorter remaining native search finds the same minimum board count as
an independent unmodified full-budget run. Adoption therefore requires paired
operational evidence, not just geometry unit tests or fixed-work improvements.

## Reproduction

```sh
python -m pytest -q almdina_erp/tests/test_abc_cutting_search.py
python scripts/benchmark_abc.py --cases regular-48 3687 --budget 5 --repeats 2 \
  --strict --output /tmp/abc.json
```

On Windows, use a workspace-owned `--basetemp` for pytest when the shared user
temp pytest directory is inaccessible. The harness records child failures and
returns failure if any child fails or returns invalid geometry. Each arm is a
fresh sequential process; arm order reverses between repeats. It records wall/CPU/peak RSS, dependency
versions, source SHA/dirty status, raw/final metrics, actual canonical topology,
identity signatures, local work counts and optional actual JS/strict import.
RSS is the Python worker's own peak, not child Node memory.

`regular-48` is a reconstructed anonymized dimension-only witness with explicit
all-rotation/full-board assumptions. `3687` uses the existing reconstructed input
fixture. Neither is a live factory request or a designer reference seed. Solver
availability and exact-piece limit are recorded; geometry/trace fixtures do not
prove industrial grain, addons or original provenance.

See `implementation-results.md` for actual local results and environment limits.
The full preregistered corpus, held-out validation, A/A controls and production
Linux/Frappe CI remain gates before considering default activation. A smoke run
with one repetition does not pass those gates. Record every regression rather
than averaging away extra boards or validation failures. Actual DXF validation
does not certify CNC motion, clamping, tool depth or execution time.

The 2026-11-05 real-order DXF audit is recorded in
`298-real-dxf-comparability-ar.md`. For the structural comparison, the user
directed that the designer's `OFFCUT` be treated as required part #17. It remains
excluded from ABC performance claims until the original manufacturing settings
and source piece order are known.

The decision study for a remnant-directed Large Neighborhood Search is in
`remnant-search-study-ar.md`. It documents the existing remnant rank, the current
12-move local neighborhood, the gap a new search should address, and the
measurement gates. The values 92.64 and 66.25 remain user-reported pending their
unit and source metric.
