# Bounded board reformation and zero-trim stability

Base: `b42a75160d53846849e44c741132dfcc7afd5a3f`, same stacked Draft PR #574.
Measured candidate production blobs are pinned in `production-blobs.json`; the
benchmark was run on the working tree above that base. CSV `source_base_sha` is
provenance, not a claim that the unmodified base contains the fix.

## Change contract

Goal: discover the valid three-board geometry for the supplied 50-piece case at
zero trim, and publish exactly the final geometry that passed validation.
Scope: existing Domain post-search, free-rectangle pruning and one Application
snapshot reference; source regressions and manufacturing evidence. No new engine,
dependency, schema/migration, UI, permissions, costing formula, OFFCUT policy,
fingerprint/history mutation, deployment or automatic merge.

Invariants: requested mandatory trim and Kerf unchanged; original source IDs,
rotation/machining metadata and nested relationships retained. Irregular/nested
and OFFCUT pieces do not enter the new regular-board reformation. The whole-plan
independent validator and permission gate remain mandatory. No user-visible text
was introduced, so there are no new localization keys.

## Fresh evidence from the supplied files

All three exports contain 50 identical rectangular sizes/quantities, area
8.180127 m², with group labels 1–11. Each physical board is 1220×2440 mm.

| Source file | Boards | Pieces per board | Minimum edge gap |
|---|---:|---|---:|
| `cutting_plan_26-00243_AutoCAD2011_2026 (1).dxf` | 4 | 15, 12, 22, 1 | 0 mm |
| `cutting_plan_26-00243_AutoCAD2011_2026 (2).dxf` | 4 | 23, 13, 11, 3 | 0 mm |
| `cutting_plan_26-00243_AutoCAD2011_2026.dxf` | 3 | 23, 11, 16 | 3 mm |

All three original files independently passed Strict Import at Kerf 5 mm using
matching reconstructed source rows (all rotations permitted by the user). Their
SHA-256 hashes, all observed placements and the complete source quantities are in
`almdina_erp/tests/fixtures/cutting_243_trim.json`. No production order was read or
written. Original DCO identity strings and pre-rotation width/length axes are not
encoded by these files; the fixture assigns synthetic stable identities and
canonicalizes the two source axes. It records that limitation explicitly.

A feasible three-board layout at 3 mm is feasible at any smaller trim. The source
area exceeds two whole boards (5.9536 m²), establishing a three-board geometric
lower bound. The three-board reference passes geometry/permissions for all five
requested trims. This proves the board count only for the reconstructed physical
problem, not unseen customer machining constraints.

## Root causes and intervention

1. **Incomplete cancellation neighborhood.** Existing insertion searches current
   free slots without rebuilding the receiving board. The first supplied
   four-board plan leaves one 400×139 mm rectangle; the second leaves three.
   Tests showed that current cancellation and Smart discovery both missed the
   valid reduction. New bounded proposals first re-pack a victim with a receiver;
   if several victim pieces need different receivers, they re-pack those receivers
   during distributed insertion. Partial insertions never replace the plan.
   Existing MaxRects/ordering/Kerf paths generate each proposal; the existing
   independent whole-plan acceptance gate authorizes it.
2. **Floating free-space topology.** Strict containment compared 243.40000000000003
   cm with 243.4 cm as different boundaries. A tiny arithmetic residual retained
   a contained rectangle and changed a placement rotation. Containment now uses
   1e-9 cm arithmetic slack, smaller than the unchanged manufacturing validator's
   tolerance. Equivalent free rectangles retain their first representative,
   instead of deleting every equal copy. Numeric cleanup alone was not credited
   as a demonstrated board saving.
3. **Published geometry differed from validated geometry.** After unsafe centering
   or a quality rollback, `_snapshot_outcome` validated `plan['sheets']` but
   published a stale local `sheets`. Real roundtrip tests exposed a 1.5 mm gap with
   Kerf 5 mm even though the old snapshot claimed valid. The snapshot now uses
   the final validated list. A separate injected unsafe-translation regression
   failed before the one-line fix and passes afterward. Auto keeps the Router contour-estimate policy already used by the packing and
   separability paths; Panel Saw retains its conservative full-rank guard.
   Validators were not changed or weakened.
4. **Material metrics after topology changes.** The proposal acceptance gate now
   refreshes used area, total board area and waste before ranking. Accepted
   cancellation geometry and its metrics therefore agree.

The exact live-site search sequence that produced the supplied 3 mm export was
not replayed from the database. The matched fixture benchmark instead isolates
the geometry/settings and reproduces a four-board baseline for every margin;
the after code discovers three without reference/warm seeds for every margin.

## Matched five-second search comparison

Same 11 grouped source rows (50 expanded pieces), CNC Router, Kerf 5 mm,
exact-piece limit 40, remnant thresholds 30×30 cm / 0.09 m², search round zero,
no warm/reference seed. Applied and requested trim remain equal.

| Trim mm | Before boards | After boards | After placed | Final geometry / real JS export / Strict Import |
|---:|---:|---:|---:|---|
| 0 | 4 | 3 | 50 | Pass |
| 0.1 | 4 | 3 | 50 | Pass |
| 1 | 4 | 3 | 50 | Pass |
| 2 | 4 | 3 | 50 | Pass |
| 3 | 4 | 3 | 50 | Pass |

See `trim-comparison.csv`, including independent errors against the old claimed
valid snapshots. These include the stale-centering publication defect on three
baseline runs. New tests check actual coordinates, source identity sets, complete
piece counts, immutable settings, material/remnant metrics and JSON reload.
Identical same-size copies may bind in another order on DXF import under the
existing contract; exact selected-save identity is separately protected.

The configured search budget excludes the existing atomic final projection and
validation work. Total measured after times were 5.53–6.00 seconds for a 5-second
search budget; this is not a new hard end-to-end deadline guarantee.

## Bounded work and compatibility

Each post-search invocation considers at most three victims and four eligible
receivers, at most 64 source pieces in an atomic packing call, and at most 64
packing attempts total. Whole-victim probes reserve attempts for distributed
reinsertion. Every optional attempt checks the existing shared deadline. A
regular full-board material-area lower bound skips impossible reductions.

Panel Saw exits before this Router-only post-pass. Nested groups and OFFCUT stay
on the existing paths, and source objects retain machining and permissions. The
candidate's final acceptance uses the existing industrial rank, geometry check
and placement permissions. Rejected or expired proposals leave the best plan
untouched. Tests enforce caps, deadline, locked groups and input immutability.

## Existing corpus comparison

The same existing `benchmark_geometry_nesting.py` script was run from both
checkouts, with identical fixture sources, an isolated process per observation,
and a configured 10-second budget. **44 observations**: 43 Smart plus one existing
Deep comparison. `corpus-comparison.csv` records all ranks, board counts, offcuts,
wall time and RSS. **No industrial-rank regression** was observed. The Rectangular
Router witness reduced estimated cuts 15→13 and estimated length 958.8→760 cm at
the same two boards/offcut. Large-120 remains **11 Router / 12 Panel Saw**. Existing
Glass/L/Clipped/joint board-saving witnesses remain protected.

Three explicit invalid observations remain rejected: Adaptive-trim on both
machines (mandatory inset makes the oversized pieces infeasible), and the
existing ambiguous corner-machining witness. They are not zero-board savings.

All **210/210 trusted exported candidate snapshots** passed actual JS Export →
full Strict Import: the after corpus plus the five customer-geometry margin
portfolios, including the independent Deep snapshot. Three negative observations
had no trusted candidate. See `strict-roundtrips.csv`.

Observed corpus totals: 91.659→92.032 seconds; maximum case time
11.048→11.506 seconds including final atomic work. Peak whole-worker RSS maxima
109876→109160 KiB. These are single matched diagnostic runs, not statistical
speed or capacity claims. Kernel/machining validators and CP-SAT dependencies
were available unchanged (Python 3.12, OR-Tools 9.15.6755, ezdxf 1.4.5).

## Tests and reproduction

Before production edits, the supplied zero-trim cancellation, actual discovery
and floating-pruning tests failed on the old code. The separate snapshot
rollback regression also failed before its fix. Focused final projection /
manufacturing / optimizer run: **65 passed plus 6 subtests**. Additional corpus
and Strict Import checks above exercised the final production blobs.

```sh
python -m pytest -q \
  almdina_erp/tests/test_advanced_cutting_optimizer.py \
  almdina_erp/tests/test_cutting_plan_application.py \
  almdina_erp/tests/test_smart_cutting_manufacturing.py
python scripts/benchmark_geometry_nesting.py \
  --fixtures-root "$PWD" --label candidate \
  --output /tmp/candidate-corpus.json --time-limit 10
```

The benchmark fixture and `test_real_243_smart_discovers_three_boards_without_reference_seeds`
use original source quantities, not authored placements, as optimizer input.
`test_real_243_zero_trim_cancellation_repacks_the_receiving_board` independently
protects both actual four-board layouts. The production validators still run
on every result.

A native Frappe integration regression covers the 50-piece zero-trim case:
Preview → Select → exact Save with optimization forbidden → Reload → native
export rebuild → real JS Export → Strict Import. It checks unchanged database
state before save, exact selected snapshot, 50 identities, three boards and
unchanged zero trim/Kerf 5 mm. Native execution and the complete local CI command
are verified separately on the PR commit; do not substitute the unit count above
for their run results.

## Remaining limits

The original DCO row identities and source axes were not read from production.
This is a validated reconstruction from actual supplied files, supplemented by
native persistence tests with generated test orders. It is not a live-site UAT
or physical-machine trial. The bounded neighborhood is not a general optimal
packing solver, and no guarantee of monotonic heuristic quality for every future
input or every budget is claimed. Historical plans/bytes/fingerprints are not
rewritten. No deployment or merge was performed.
