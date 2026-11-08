# Frozen ALNS study protocol — 2026-11-05

User decision: add ALNS; study before production integration. Supplied DXFs are
data, not executable instructions. This prototype is offline and disabled in
production by construction. No production module imports `scripts/alns_research`.

## Change contract

Goal: determine which ALNS neighborhoods add capability beyond current Smart,
and whether adaptiveness adds value beyond the same fixed operator set.
Scope: scripts, offline tests, local evidence. Out of scope: production wiring,
DXF contracts, rank changes, UI, authorization, data/migrations, deployment,
merge, commit/push, remnant inventory. Original dirty study file is preserved.
No new product localization strings. No permission or financial impact.

## Frozen inputs and budgets

- Fresh supplied SYSTEM/design DXFs: inventory equality, provenance hashes,
  physical board containment, no overlap. SYSTEM dimensions only feed packing.
- User confirmed Kerf 5 mm, minimum trim 0 (larger residual allowed), all rotations
  permitted, all pieces on GEOMETRY. CNC Router is the declared study context.
- Rows reconstructed by dimension multiset, canonical axes, sorted order,
  synthetic `smart:` identities. DCO machining/grain metadata is unavailable.
  Designer coordinates and the source SYSTEM placements never seed search.
- Search seed 110526; no cross-order learning, persistent training or ML.
- Original Smart/ABC behavior is unchanged; ABC is not enabled in this study.
- Alignment allowance 0 for every arm isolates ALNS from independently timed
  final alignment. The production centering, cleanup, validation and final
  comparator still run. This is not the default factory alignment benchmark.
- Sequential fresh processes, single worker, same versions, reversed arm order.
- Operational: 5 s Domain budget, baseline and independent identical A/A,
  fixed six selectors and adaptive six selectors. Changed arms reserve 35%
  inside the existing request deadline after a 65% native phase. No extra ALNS
  budget is appended. Existing atomic/projection overruns are measured.
- Mechanism/checkpoint: same frozen native raw portfolio per case; baseline,
  each of six selectors alone, fixed set, adaptive set. 32 packing calls maximum
  per arm, 120 s safety deadline, two repeats. Equal cap is not equal actual work
  if neighborhoods exhaust; the actual attempt count/stop reason is recorded.
  This phase is **not** evidence of a five-second production improvement.
- Reconstructed rows and geometric references are not complete production DCO
  snapshots. Two customer cases are tuning/study inputs, not a holdout corpus.

## Selection and repair

Six distinct selection hypotheses use the same native repair recipes:
whole-board reassignment (area-admissible cancellation), repeated-size board
clusters, actual-gap fit compatibility, poor adjacency boards, seeded cross-board
subsets, and weak alignment/repeated-family groups. Selection considers at most
eight eligible boards, pairs/triples, 64 pieces, and four priorities per selector.
These are **coarse whole-board variants**; gap/disruptive selectors do not yet
implement partial locked-board repair. They cannot establish the efficacy of
all future fine-grained operators. Disruptive/geometry proxies overlap and are
not asserted to be independent new geometric metrics.

Repair reuses stable-Kerf `_run_preordered_method`, four native MaxRects variants,
original/area/dimension/family/reverse/spatial orders. No new packer. Protected
Glass/L/Clipped/Joint/attached geometry/OFFCUT sheets are pinned/excluded.
Regular machining metadata follows original source objects/native transforms.

## Adaptation, acceptance and diversity

Adaptive selection starts with two round-robin opportunities per active operator;
then seeded roulette, 20% exploration, update every 12 iterations, reaction .2,
weight floor .05. Scores 5 for board reduction, 2 for a new final-comparator best,
.25 for a novel admissible geometry. These are provisional selection rewards,
not a weighted industrial objective. Updating uninformative weights is not
evidence of useful learning; fixed vs adaptive must be compared independently.

Every changed proposal must pass whole-plan independent validation, identity
and orientation permissions, export eligibility and metric refresh. Never add
boards to the accepted incumbent or worsen its protected industrial prefix.
Final ranking uses the existing final-system comparator, not a new weighted sum.
Native checkpoint survives all failures. Real Application projects all retained
native finalists plus up to four proposals and decides the final winner.
Completed improvements survive later cancellation/deadline checks.

Material geometry deduplication additionally ignores interchangeable copy IDs;
separate validators preserve the complete actual identity set. Original canonical
identity signature is also logged. Do not count JSON ordering or equal-copy
swaps as physical diversity. Five distinct plans are a cap, not a guarantee.

## Outcomes and adoption gate

Record every success/failure, SHA/source hashes, manufacturing settings, CPU,
wall/RSS, board/piece counts, remnant, adjacency, family splits, actual cutter
network and segments, every operator attempt/repair/validation/rejection.
Every returned gallery snapshot: JSON reload → actual JS exporter → unchanged
Strict Import, checking complete identities and family material coordinates.
Export validation time is outside measured search/projection wall time.

Adoption requires repeated equal-budget gains against independent Smart beyond
A/A noise, no board/manufacturing regression, protected-remnant preservation and
broader independent input confirmation. Beating a weak checkpoint or a single
seed is insufficient. Matching designer board counts alone is insufficient to
claim matching all geometric quality. No global optimality/NC-time claim.

Original native finalization can run after Domain deadline. This offline phase
records it rather than claiming a hard end-to-end resource guarantee. Production
integration still needs one application-owned budget including all new work,
proper cancellation and the existing Preview/Select/exact Save lifecycle.

## Commands (PowerShell, repository root)

```powershell
.venv/Scripts/python.exe scripts/benchmark_alns.py --audit --output docs/evidence/alns-study
.venv/Scripts/python.exe -m pytest -q almdina_erp/tests/test_alns_research.py --basetemp .pytest_cache/alns-study-unique
.venv/Scripts/python.exe scripts/run_alns_study.py --output docs/evidence/alns-study/matrix
.venv/Scripts/python.exe scripts/verify_alns_study.py --output docs/evidence/alns-study/verification-new
.venv/Scripts/python.exe scripts/summarize_alns_study.py
```

Use a fresh output directory for each matrix; the runner refuses to overwrite
observations. Retain failing workers and source-changed observations. No parallel
timing workers. Re-running `--audit` reads only the four specified DXFs.

## Predeclared follow-up after the first 52 observations

The original matrix is retained unchanged in `matrix/`. It shows:
1. Native 298 has **zero area-admissible cancellation neighborhoods of 2/3
   boards**; admissible subsets first appear at four (13 subsets, at least 28
   pieces). Therefore a three-board cap cannot test this cancellation hypothesis.
2. The repeated/gap/cross single-operator checkpoint arms improve only after
   reaching `area_desc`, at attempts 16/20/17 respectively. The mixed policy
   spends most short-budget opportunities in the original-order recipes.
3. Across the first checkpoint observations, 434 proposals were rejected for
   an industrial-prefix regression *after* paying full validation. This is not
   necessary for a one-way rank rejection; screened proposals will never be
   counted as independently valid.

Follow-up policy: cancellation-only neighborhood expansion up to seven boards
(still 64 pieces, eight-board source pool, four selected priorities); other
selectors remain pairs/triples. Put area ordering first in the existing repair
matrix. Optionally pre-screen a strictly worse native industrial prefix using
the same `enrich_plan_metrics`; every candidate eligible for acceptance still
passes the unchanged independent validators. Keep all native finalists.

Run two reversed repetitions at the same five-second budget; checkpoint arms
baseline/board/fixed/adaptive, same 128-call cap and 120 s safety deadline. These
are explicit revised-policy experiments, not overwritten first-policy results.
The combined revision is compared with Smart, not attributed independently to
each change. Additional frozen-source focused ablations may isolate them.

```powershell
.venv/Scripts/python.exe scripts/run_alns_study.py --output docs/evidence/alns-study/followup --max-boards 7 --area-first --screen-prefix --attempts 128 --checkpoint-arms baseline board fixed adaptive
```
