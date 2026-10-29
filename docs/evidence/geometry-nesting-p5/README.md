# P5 — geometry-first nesting and shape coverage

Change contract: discover proven irregular formations automatically from original
expanded pieces, complete them with the existing packers/Glass/search, and retain
useful validated alternatives. Manufacturing geometry, permissions and industrial
ranking remain authoritative. No UI/API/cache/schema/cost/lifecycle changes; no
new packing engine, dependency, migration, production access or deployment.
Localization impact: internal diagnostic keys only; no new product text.

Original HEAD: `cf11a2bed108ef646b5fa89a61cafa67d64e11a6`. Measured production
implementation: `7a64b443dbfaf73bdd77a4ae04bf5e5e991b82ff`. Later evidence/reporting
changes do not alter that engine. Same branch and stacked Draft PR #574; #570,
Develop and main are unchanged.

## What was actually reproduced

No authorized fixture/export of the failing customer order was supplied or
available through a connected read-only test-site tool. These are representative
source-level regressions, not a claim to reproduce or certify that exact order.

Before implementation, two source-only Smart tests fail: non-identical L and
non-identical Clipped both use two boards where exact material fits on one.
The protected incompatible witness remains two boards. A separate deterministic
geometry witness demonstrates why inserting a rigid piece at the first piece's
original origin misses a valid relative formation: both bodies must move before
packing. The proven pose is test evidence only, never an optimizer input.

The source tests also expose a distinct pre-existing manufacturing limitation:
Strict Import rejects machining on a symmetric corner with ambiguous semantic
orientation (`LINER_SHAPE_MISMATCH`, `orientation_unresolved`), even for separate
boards. A new regression initially fails because that baseline was called valid.
Smart now uses the existing contour matcher to reject the unprovable candidate.
When selected edge bands provide the import binding, it preserves that proof
only when the imported semantic orientation also matches the machining transform.
A positive equivalent-band regression and native catalog/save test protect this
supported case; symmetric geometry alone is not treated as universal rejection.
If no provable baseline exists, the established incomplete-plan failure payload
contains every original piece as unplaced. It cannot be selected/saved as valid.
The original source, machining metadata and importer are unchanged. Asymmetric
L with a liner has a separate positive export/import and native-save witness.

## Proven causes and targeted changes

1. `_identical_groups` intentionally excludes different dimensions/notches. The
   historical exact-group generator stays intact. `geometry_nesting.py` adds a
   Smart-only generator for contacts between compatible non-identical corners.
2. Rigid translation anchors do not generate relative formations that reposition
   both pieces. Vertex contacts, edge normals and offset-edge axis intercepts now
   propose translations. Real `material_outline_cm`, overlap/distance and board
   checks authorize them; boxes are search bounds, never material substitutes.
3. A smallest-area partial nest can lose a narrower formation whose *complete*
   plan saves a board. The search keeps compact, narrow and short variants,
   singles, pairs, legacy quads and disjoint pair combinations. Empty voids are
   explicit alternatives. Existing MaxRects/free-space/search packs the remainder.
   An additional source witness proves the historical void grid can miss an
   axis-aligned rectangle inside a clipped diamond. Nine bounded centre/edge
   proposals in the new path find it using the same material/Kerf proof. The
   old P4 guest-order path keeps its allocation behavior and runtime.
4. P4's early joint pass mainly saw the original baseline. Proven shape-first
   seeds now share its Glass/consolidation/search completion, without enumerating
   shapes again. At most two later distinct promising irregular finals get a
   short completion. Existing guest/subtree reassignment remains protected.
5. Rank-only top five could evict every useful nest for coordinate variations.
   The industrial winner is always first. Within its board count, the bounded
   portfolio may retain the best proven Joint/L/Clipped/Glass coverage before
   filling remaining slots by the unchanged rank. No extra-board reservation or
   unconditional nest priority replaces the winner.

Coverage counts actual bbox intrusion on already validated material, excluding
Glass ancestors, or proven formation/guest records. Engine names and decorative
metadata cannot manufacture coverage. The geometry signature still retains
identity, opening ownership and actual transforms; historical fingerprints do
not change.

Production changes are confined to **five Domain files**:

- `domain/cutting/geometry_nesting.py` — specialized contact/formation and complete
  shape-first generation (one helper, no external engine).
- `domain/cutting/optimizer.py` — bounded scheduling, common final retention,
  counters and fail-closed unsupported-baseline handling.
- `domain/cutting/plan_portfolio.py` — genuine coverage, same-board diversity and
  existing contour-proof reuse for corner machining.
- `domain/cutting/joint_nesting.py` — reuse existing completion for shape seeds;
  existing P4 reassignment limits/locks preserved.
- `domain/cutting/shape_aware_nesting.py` — optional shared deadline checks while
  seating guests and optional centre/edge proposals for the new path; historical
  exact-group formation behavior is unchanged.

## Search bounds and diagnostics

Only CNC/Auto orders with actual corners enter the new search. Regular-only and
Panel Saw are gated out. All work uses the existing configured shared deadline:
at most `min(3 seconds, 35% of budget)` for geometry-first, 45% of that local
remaining time for formation enumeration. The existing P4 local joint allocation
is unchanged. Later completion is capped at two candidates, at most 0.3 seconds
each from remaining time. Atomic validation/projection can finish after deadline;
there is no hard real-time or global-optimum claim.

Local caps: 48 source pairs, 192 contact positions per permitted orientation pair,
eight diverse partitions, eight completed geometry-first alternatives and the
unchanged five trusted cache/gallery candidates. Legacy global trial constants
are not multiplied. Overlap/clearance/identity/permission checks are not skipped.

`smart_search.shape_first` records eligible/tested source combinations, distinct
generated and complete-plan-proven formations, completed plans, per-piece traces,
initial Glass reservation, actual final coverage and explicit reasons. Reasons
separate legacy dimension mismatch, denied transforms, provable material-area
rejection, bounded contact miss, enumeration caps, budget exhaustion, repack,
validation and unsupported manufacturing identity. A bounded miss is not proof
of global incompatibility. `smart_search.portfolio` records unique valid offers,
plans dominated by the industrial winner, unique plans pruned from five slots,
coverage and rejection events. Counts are events/unique signatures as named;
they are not claimed to be exhaustive counts of all mathematically feasible nests.

## Matched benchmark

The identical script runs each checkout's real engine, each observation in a
fresh worker: 24 existing CNC/Panel cases + eight P4 witnesses + eleven P5 source
cases, and a separate unchanged Deep L-mixed comparison, at 10 seconds each.
Sources, expanded identity, machine, Kerf, preferred/adaptive Trim, permissions,
remnant thresholds and exact-piece limit are identical. Reporting-only hooks
count distinct generated formations; they do not change placements/rank/limits.
The launcher streams snapshots so a growing parent process does not contaminate
worker high-water RSS. RSS includes the interpreter/imports. These are single
wall-time/RSS observations, not statistical speedup claims.

The 43 Smart inputs plus the independent Deep comparison produce **88 matched
observations**. Programmatic comparison verifies every source row, identity,
setting and machine is identical. All 32 existing P4 inputs preserve or improve
the validated industrial rank. The four P4 two-to-one witnesses stay one board.

| CNC witness | Generated formations before→after | Boards before→after | Reusable offcut m² before→after | Total seconds before→after |
|---|---|---|---|---|
| Existing Clipped quad, axis-aligned guest | 3→17 | 2→1 | 0.150319→0 | 0.942→1.410 |
| Non-identical L | 2→3 | 2→1 | 0→0 | 0.111→0.256 |
| Non-identical Clipped | 2→3 | 2→1 | 0→0 | 0.140→0.212 |
| Single L, one guest | 0→2 | 2→1 | 0→0 | 0.073→0.126 |
| Single L, two guests | 0→2 | 2→1 | 0→0 | 0.166→0.233 |
| Single L, four guests | 0→2 | 2→1 | 0→0 | 0.850→0.971 |
| Non-identical L + Clipped + Glass | 4→10 | 2→1 | 0.299433→0 | 2.581→2.895 |
| Non-identical asymmetric L + liner | 2→3 | 2→1 | 0→0 | 0.129→0.221 |
| Protected incompatible L | 0→4 | 2→2 | 0→0 | 0.099→0.148 |
| Pair/quad choices | 3→29 | 1→1 | 0→0 | 1.704→2.871 |
| Larger realistic mixed source order | 4→8 | 2→2 | 2.610800→2.610800 | 5.148→6.961 |

The eight valid two-to-one improvements do not include the negative machining
witness: it is rejected before export, **not** counted as a zero-board saving.
An extra board's offcut disappearing after a board saving is consistent with
the existing board-count-first rank. The protected case generates valid singles,
not a fabricated interlock; material area proves its proposed pair cannot fit.

Across Smart inputs, potential source pairs remain 165 (including Panel Saw);
the new path tests 114 CNC source pairs. Distinct generated formations across
the full search are **65→476**; new-path formations proven in complete plans total
145. These include singles and alternatives, not 476 useful final nests.
Trusted unique gallery snapshots total **172→190**. Actual coverage:

| Coverage | Cases before→after | Retained plans before→after |
|---|---|---|
| L | 6→16 | 11→29 |
| Clipped | 3→7 | 4→12 |
| Glass | 10→10 | 40→36 |
| Joint | 5→6 | 8→9 |

Glass still covers the same ten cases; some redundant Glass coordinates give
way to useful shape alternatives. The default never yields to a worse rank.
Detailed generated/tested/proven counts, ranking/pruning, per-piece traces and
reasons are in [search-diagnostics.csv](search-diagnostics.csv).

Large-120 remains 11 CNC / 12 Panel boards with offcuts 0.850038 / 1.892220 m².
Glass-gap and L-positive-trim CNC remain one board. Pure L-mixed CNC remains
2 boards / 0.905980 m², still below unchanged old Deep's 0.960140 m² at 2 boards.
No superiority to Deep or global optimum is claimed.

All **190 Smart candidate snapshots**, plus the independent Deep snapshot,
pass actual JS Export → full Strict Import: **191/191**. The explicit negative
witness has no trusted candidate and fails the existing incomplete-plan gate.
Before, two portfolios fail Strict Import: `P5-joint-different` candidate 2
(`PIECE_IDENTITY_AMBIGUOUS; PIECE_MISSING`) and `P5-addon-ambiguous` candidate 1
(`LINER_SHAPE_MISMATCH`). Those failures remain visible in the before CSV; they
are not accepted as manufacturing evidence or hidden by weaker import checks.

Maximum Smart total runtime is **10.472→10.556 seconds**, including final atomic
validation/projection. Sum across the 43 Smart observations is 82.497→108.121
seconds; extra search effort consumes the same configured budget. Per-case peak
RSS increases by at most 648 KiB in this run. Whole-worker peaks are
100948→100756 KiB, dominated by optional CP-SAT/interpreter imports; no memory
reduction claim follows from those single observations.

[Full before benchmark](benchmark-before.csv) · [Full after benchmark](benchmark-after.csv)
· [Measured production blob identities](production-blobs.csv).

## Validation and reproduction

Final targeted local regression suite: **205 passed** (`/tmp/p5-final-local.log`);
36 new geometry tests are included. The implementation-stage CI at `307f54fa`
passed all three workflows, including 1029 static tests + 22 subtests and native
Frappe 1711 unit + 103 integration tests. Final delivered-head CI results are
linked in PR #574, after the last two geometry/native regressions were added.
Existing P4 two-to-one witnesses remain active. New cases include
compatible/incompatible non-identical L, unequal Clipped, single/two/four guests,
pair-vs-quad full outcomes, mixed Glass/L/Clipped, asymmetric machining, ambiguous
machining rejection, true geometry diversity, warm/budget/permission boundaries
and deterministic repeated discovery. No tests are skipped or validation assertions
relaxed. The old unsupported-angle witness's expected two-board fallback becomes
one board only with the newly proven axis-aligned guest; its angle/clearance
assertions stay intact and an actual JS Export/Strict Import proof is added.

Each supported P5 portfolio is JSON reloaded, rebuilt by the native export
projection, exported using the actual JavaScript exporter and fully Strict
Imported. Actual Frappe tests additionally exercise Preview → Select → exact Save
with optimization forbidden → Reload → native validation/rebuild → JS Export →
Strict Import. A rejected ambiguous machining preview cannot mutate the prior
saved plan. Existing first-plan, cancel/expiry/replay/concurrency, capabilities,
stage, cost, OFFCUT, uploaded/approved and fingerprint guards stay active.

```bash
python -m pytest -q almdina_erp/tests/test_geometry_first_nesting.py almdina_erp/tests/test_joint_nesting.py almdina_erp/tests/test_glass_opening_nesting.py almdina_erp/tests/test_cutting_shape_search.py almdina_erp/tests/test_nesting_consolidation.py almdina_erp/tests/test_smart_cutting_search.py almdina_erp/tests/test_smart_plan_portfolio.py almdina_erp/tests/test_smart_cutting_manufacturing.py almdina_erp/tests/test_smart_cutting_lifecycle.py
# Run the same script from the original and implementation worktrees:
python /path/to/scripts/benchmark_geometry_nesting.py --fixtures-root /path/to/implementation --label before --output /tmp/before.json --time-limit 10
python /path/to/scripts/benchmark_geometry_nesting.py --fixtures-root /path/to/implementation --label after --output /tmp/after.json --time-limit 10
# Existing verifier is used for supported candidates; the intentional ambiguous
# machining rejection is separately recorded as fail-closed, never as a saving.
python scripts/verify_cutting_benchmark_dxf.py --input /tmp/after.json --expected-rejected-case P5-addon-ambiguous --output /tmp/strict-after.csv
# Native isolated test site only:
bench --site test.localhost run-tests --module almdina_erp.tests.test_smart_cutting_integration
```

Limits remain: bounded contact discovery is not complete NFP nesting; arbitrary
non-quarter rotations and machining guests inside Glass remain excluded. No
customer-order UAT, machine toolpath sequence or deployed-site proof is claimed.
