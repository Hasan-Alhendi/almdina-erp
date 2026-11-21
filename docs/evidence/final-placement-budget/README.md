# Final placement budget starvation — measured correction

Base implementation: `1a07d119`, branch `feature/smart-edge-protection`, Draft PR #606.
The benchmark loads the original module directly from that Git object. It does
not reconstruct an approximation of the old algorithm.

## Scope and provenance

Goal: fair, measurable opportunities for multi-board protection within the
existing gallery tail and 24 expensive trials. Domain scheduling and bounded
generation, Application deadline/proof wiring, diagnostics, tests and docs only.
No setting, dependency, migration, optimizer/packing change or permission change.
Board count, physical identities/dimensions/orientation, Kerf, manufacturing
fingerprints, saved/Approved/Uploaded plans and the zero-policy path are preserved.

The user's isolated server log for order 26-00345 / CP-2026-00677 reports Draft,
17 boards, effective alignment budget 30 s, optimization limit 120 s, H15/V20 mm,
centering 7 cm, total elapsed 51.4 s and search elapsed 0.0. Board 1 had two
UNSAFE_MOVE decisions without details; boards 2–17 had 32 time_budget decisions.
That establishes starvation, not infeasible geometry. It does **not** identify
which phase consumed the site's time. The raw snapshot/piece geometry was not
provided or found locally. No server access, plan mutation or deployment occurred.

All JSON artifacts here contain **synthetic fixtures**, not customer data.
The dense witness has 48 Kerf-spaced 18×22 cm regular pieces on each 122×244 cm
board; the sparse witness has one 75×75 cm piece per existing board. The stage
never repacks or removes those boards. Fixtures cover 1, 2, 8 and 17 boards,
five alternatives, short budgets, failed proposals and unsupported geometry.

## Proven cause and correction

The regression failed for 2/8/17 boards on the old implementation: an expensive
matching-edge generator could consume the entire deadline before the first
translation trial. The actual dense benchmark also exposes repeated **whole-plan**
validation for every sheet baseline and accepted proposal. The old sheet trial
quotas started after this work and therefore did not schedule its cost. Generating
all events and sorting them also had no bound/checkpoints at several stages.
Gallery shares were reserved only after preparing the current candidate.

The fix:

1. Every eligible sheet gets a cheap protection pass before matching-edge or
   unequal-group refinement. Combine basic X/Y protection atomically where clear.
2. Divide remaining time by remaining eligible sheets; then rotate through
   boards with at most one expensive trial per board per round. Keep 24 total
   expensive trials and four rounds. More than 24 needy boards cannot all receive
   a trial; a 25-board regression explicitly leaves board 25 at TRIAL_BUDGET.
3. Bound events **before** costly scoring and sorting and check slice expiry
   while generating/scoring/ranking. Cache groups and actual baseline/current
   cutter profiles per sheet; compute final metrics once.
4. The actual independent engine validation port creates an exact ephemeral
   baseline proof, including permission/context checks. Reuse requires complete
   plan/source/context equality. Each accepted proposal checks its changed
   board with the existing full validator; unchanged sheets/identities must
   compare exactly through the existing translation-validation-scope helper.
   Final Application manufacturing validation still checks the entire plan.
5. Reserve the candidate's existing shared deadline before preparation. No
   second timer, restart, new setting or extra allowance is created. Atomic
   validation may complete after its slice, then no new trial starts. A completed
   safe candidate survives expiry.

Bounds/Kerf/swept clearance, actual complete cutter union, connected eligible
remnants, placement permissions, manufacturing export compatibility and final
snapshot validation remain acceptance gates. Adapter rejection restores the
complete baseline and marks the proposed acceptances as rolled back.

## Equal-budget dense results

Windows, Python 3.12.10, existing project dependencies. Sequential observations,
not CI timing assertions or CNC runtime estimates. Budget: **30 s** per plan.
Files: [baseline](baseline-dense.json), [fixed](fixed-dense.json).

| Boards × pieces | Reached before → after | Expensive trials before → after | Accepted atomic proposals before → after | Elapsed seconds before → after |
|---|---:|---:|---:|---:|
| 1 × 48 | 1 → 1 | 12 → 5 | 1 → 1 | 0.957 → 1.123 |
| 2 × 48 | 2 → 2 | 24 → 10 | 2 → 2 | 3.254 → 1.906 |
| 8 × 48 | 8 → 8 | 22 → 24 | 8 → 8 | 31.231 → 7.125 |
| 17 × 48 | **4 → 17** | **4 → 24** | **4 → 17** | **33.446 → 10.796** |

An accepted proposal can move many pieces and both axes. On 8 and 17 boards the
old accepted proposals only inset Y: every sheet still had zero left margin.
The fixed result has **left 15 mm / top 20 mm on every sheet**, right 100 mm /
bottom 625 mm. No sheet is unprotected in this dense 30-second fixed witness.
On 17 boards the 7 remaining trials reject loss of real shared cutting; all
17 basic proposals have already passed the complete safety chain. The old run
left 26 axes explicitly timed out and 4 untested axes without an explanation.

| 17-board phase, exclusive milliseconds | Before | After |
|---|---:|---:|
| Group discovery | 70.975 | 212.845 |
| Alignment event generation / internal scoring | 185.077 | 386.380 |
| Outer event scoring | 74.195 | 94.555 |
| Proposal generation and sorting, excluding those child stages | 220.474 | 444.628 |
| Geometry validation | **31897.377** | **7331.884** |
| Actual Cutter-Center profiles | 217.968 | 525.106 |
| Remnant eligibility/connectivity | 28.291 | 101.095 |
| Translation / bounds / Kerf / swept checks | 136.359 | 856.014 |
| Final metric calculation | 490.907 | 106.941 |

The new run does more sheet-local geometric work and covers all 17 boards; the
old run spends 95% of its elapsed time rescanning the full plan. Geometry calls
change from 8 full-plan checks to one baseline plus 17 changed-board checks.
In Application the already completed exact baseline proof also removes that
duplicate baseline scan. Mandatory final snapshot validation is retained.
Generation/sorting figures are not added twice: the benchmark subtracts nested
child durations. Snapshot's diagnostic generation_sort is **inclusive**, with
policy_events/alignment_events/event_score/sorting available as breakdowns.

The 17-board complete cutter union is **384030 mm before and after**, with
unmodified dimensions, identities and board count. The largest qualified remnant
changes from 0.7869 to **0.7625 m²**, the permitted 15/20 mm margin-strip cost;
each original useful free rectangle retains one connected qualified successor.
This is not inventory/remnant reuse behavior.

Single-board time increases about 0.17 s in this observation because refinement
now rotates through bounded rounds; do not claim every input is faster or optimal.
Repeated 17-board OS-memory observations reach 4–5 boards before versus 17 after,
depending on when the cooperative deadline falls. The fixed 24-trial cap is unchanged.

## Gallery, memory and finalization

The sparse five-candidate / 17-board fixture reaches **[17,17,17,17,17]** boards
in both implementations, demonstrating its lower cost. Before, the first candidate
uses 24 trials but leaves all 17 horizontal axes unprotected; after, it protects
both axes in 17 trials. Across all five alternatives the corrected result has
85/85 boards protected or already protected. Finalization sums: **246.358 →
165.289 ms**; whole Application including final gallery comparison: **272.121 →
194.711 ms**. Individual candidate finalization/search/residual costs and rejection
counts are in [baseline-gallery.json](baseline-gallery.json) and
[fixed-gallery.json](fixed-gallery.json). These deliberately cheap fixtures do
not imply that 85 dense sheets fit in every allowance.

Separate dense 17-board process-peak runs include fixture/import memory:
[baseline](baseline-process-memory.json), [fixed](fixed-process-memory.json).
Their OS peak working sets are **47.273 → 46.629 MiB**; the repeat reaches
5 → 17 boards in 31.083 → 8.718 s. Deadline observations vary with host load,
so the repeat is reported alongside the main matrix rather than replacing it.
Separate sparse 17-board tracemalloc runs show **0.264 → 0.266 MiB** peak Python
allocations: effectively unchanged, about 2 KiB additional cached scheduling
state. These tracer runs are not used as the wall-time benchmark. Full process
working-set peaks and dense-gallery limits are recorded in their JSON artifacts.

The adversarial **five alternatives × 17 dense boards × 48 pieces** run is
deliberately more expensive. In [fixed-dense-gallery.json](fixed-dense-gallery.json),
candidate coverage is **[11,2,0,0,0]** and accepted proposals total 13. Search
itself costs 4.320 s; preparation/final validation outside search costs 26.672 s.
Candidate finalization is [8.807,9.118,4.745,4.282,4.040] s, and the complete
Application finishes in 32.760 s including final gallery comparison. Later
candidates expire **during mandatory preparation**, before their own search;
no additional search allowance is granted. The absolute search deadline is
still 30 s; mandatory atomic snapshot work may finish after it. This run
overlapped a deterministic native compatibility check and is diagnostic, not
the isolated wall-time matrix above. The independent data file retains each
candidate's exact outcome so this remaining limit is visible.
The [old dense-gallery run](baseline-dense-gallery.json) reaches **[1,1,0,0,0]**,
accepts only two one-axis proposals and takes **59.524 s** overall. Thus this
adversarial gallery improves from **2 → 13** board/candidate opportunities and
**59.524 → 32.760 s**, while still leaving later candidates unevaluated. The
extra baseline scans in old candidate preparation are also removed. Dense-gallery
process peaks are 74.613 → 75.426 MiB, about 0.8 MiB more for cached state;
no unbounded event list is retained.

## Decisions and remaining unprotected cases

New snapshots distinguish:

- NOT_EVALUATED_TIME_BUDGET: no proposal evaluated within its available time;
  candidate preparation or the sheet slice can consume the allowance.
- TRIAL_BUDGET: remaining work exceeds the unchanged 24-trial cap.
- GEOMETRY_REJECTED: known bounds/Kerf/path/manufacturing or eligibility rejection;
  detail/rejected counters identify the actual gate. A protected special shape
  is not claimed to be invalid geometry; it is ineligible for this movement.
- NO_IMPROVEMENT: evaluated proposals do not improve the admissible objective.
- REMNANT_PRESERVED: a proposed move destroys an eligible connected remnant.
- EDGE_PROTECTED / CENTERED / ALIGNED / ALREADY_PROTECTED: retained results;
  search_status independently records unfinished refinement.

The 25th sheet is deliberately TRIAL_BUDGET in the cap regression. Forced
mid-finalization expiry leaves the first candidate explicitly unevaluated;
the four later 17-board candidates still receive their remaining fair shares.
Expired/unsupported geometry is never silently reported as a failed trial.
The previous staggered fixture still cannot achieve full horizontal inset
between packed columns; its actual cutter/safety rejection remains documented.
No result here guarantees full protection on CP-2026-00677 without its geometry.

When all useful work cannot fit, these diagnostics explain the unresolved
axes. In particular, the 34 decisions on each unevaluated dense-gallery candidate
are NOT_EVALUATED_TIME_BUDGET. The remaining axes of its partially processed
candidates carry the same explicit reason. No rejected geometry is inferred
from those missing trials; increasing the trial cap would not recover time
consumed by mandatory finalization.

## Validation and reproduction

Regression first: the new starvation test fails on old 1a07d119 for 2/8/17 sheets,
with no translation trial reached. The corrected focused budget module covers
1/2/8/17 boards, five alternatives, expiry during finalization/generation/validation,
the 24-trial limit, exact proof reuse and completed-candidate retention.

Actual Application → Snapshot → persisted export projection → existing JavaScript
DXF → normalization → Strict Re-import passes for 1/2/8/17 boards, preserving
finished geometry and CUT_PATH. The existing native-packing, staggered, gallery,
Preview/Continue, editor projection, special geometry, trim and lifecycle suites
remain in the related run. Geometry in DXF does not certify machine NC/clamping.

Related local suite: **350 passed, 1 skipped, 132 subtests passed**. The old four
manufacturing-fixture failures documented in the previous evidence are outside
this run. The independent CI job includes the new budget module. CI results and
the exact tested head are recorded on PR #606; it remains Draft and unmerged.
Disabled-protection native comparison still performs 241 actual packing attempts
and yields 3 boards/5 candidates with coordinate SHA256
`5d23b4899c2b10344f374d7078b6d4ea5a7bd292aa697642c5946cae3453608a`,
identical to Develop and 1a07d119. No fingerprint/schema fixture was changed.

```powershell
..\.venv-fragmentation\Scripts\python.exe -E -m pytest almdina_erp/tests/test_final_placement_budget.py -q
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_final_placement_budget --baseline --dense --boards 1 2 8 17 --seconds 30
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_final_placement_budget --dense --boards 1 2 8 17 --seconds 30
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_final_placement_budget --gallery --boards 17 --seconds 30
```

No new dependency is required. Baseline runs use Git's local 1a07d119 object.
No production recalculation, deployment or approved-plan modification was performed.
