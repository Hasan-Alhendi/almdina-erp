# P4 — bounded joint Glass / L / Clipped nesting

Existing branch `feature/smart-cutting-search`, Draft PR #574, unchanged base
`fix/cutting-best-valid-plan`. Before source:
`970a2d37f2b99a5042ac2c0043b887ca572b5649`. Measured engine:
`c73ca0d072f0a841b7ab7e70227f4f09a163e80a`. The subsequent reader fix described
below does not alter optimizer output or search timing. Final-head CI and SHA are
recorded in PR #574. No merge, deployment or change to PR #570 is included.

## Change contract

Goal: discover better complete plans that allocate source pieces jointly between
Glass openings and real corner voids. Scope: existing Domain orchestration, a small
bounded Domain helper, preserving proven assignments, tests and evidence. The
native verification failure additionally required a 13-line read-only fix that
rehydrates existing snapshot corner transforms in the export reader.

No UI/workflow, Preview/Cache/selection/Exact Save API, database schema/migration,
pricing/OFFCUT, approval/production policy, fingerprint meaning, source identity,
manufacturing tolerance, material geometry definition, Kerf, preferred trim,
Adaptive Trim, machine or rotation/mirroring permission changes. No packing
library, general NFP engine or new abstraction layer. No new UI text/i18n impact.
Rollback is a revert; no historical data is rewritten.

## Confirmed causes and tests first

1. Glass First Fit can consume an L needed for a quad. Shape correctly reserves
   the existing Glass host/guest group, so it cannot reconsider that allocation.
2. A shape formation can lose on its intermediate industrial rank but win after
   Glass placement and rigid consolidation. Choosing one formation before those
   steps discards this opportunity.
3. `_select_guests` discarded the proven guest→opening mapping. `_place_guests`
   ran First Fit again after removing guests, even when a selected Glass host had
   moved. The direct path now resolves the same host's live hole and retains the
   proven local placement. A repacked plan still needs a new proven assignment.
4. Native testing exposed a separate projection loss: the fallback layout reader
   and export rebuild kept Glass links but dropped recorded corner quarter-turn/
   mirror fields. Unchanged validators then examined the wrong notch orientation
   and reported false `MATERIAL_OVERLAP`. Three reader regressions failed before
   copying those existing fields into both read projections. No validation rule
   or tolerance is bypassed; malformed/colliding geometry remains rejected.

The initial source-only Smart regressions had **3 failures / 4 passes** on the
unchanged before checkout: independent and dependent joint plans remained at two
boards, and could not beat the two separate paths. These tests invoke Smart from
source rows, not manually assembled placements. Test data were refined to make
the independent case require both voids, rather than incorrectly demanding a
weaker joint layout when a better industrial solution already exists.

## Minimal implementation

Production files only:

- `domain/cutting/joint_nesting.py`: feasibility gate, bounded formation completion,
  isolated targeted release/reassignment, unchanged rigid repack and validators.
- `domain/cutting/optimizer.py`: invoke once after the proven initial path, inside
  the existing deadline, offer valid finals through the existing portfolio/rank.
- `domain/cutting/shape_aware_nesting.py`: optional validated-formation collector,
  branch-local guest exclusions and a quarter-turn-only option for new joint paths.
- `domain/cutting/glass_opening_nesting.py`: retain direct assignment evidence;
  optional preservation of existing groups, occupied openings and actual depth.
- `domain/cutting/plan_portfolio.py`: existing manufacturing gate additionally
  excludes the proven ambiguous Glass machining-guest identity path below.
- `services/export_validation_service.py`: both read projections retain five
  existing corner transform fields. No nesting decision moves into this adapter.

Path A remains the current Glass→Shape→Plan Search path. Path B retains up to four
validated shape formations until Glass completion and rigid consolidation have
been compared. Path C releases at most two selected guest relations per parent,
in copied plans, preserving descendants as a rigid subtree. It tries both
Glass→Shape and Shape→Glass allocation directions, then completes/re-packs the
whole plan. It never combines coordinates from two independent plans.

Beam width 4, depth 2, at most 12 completed alternatives, within at most 1.5 seconds
of the **remaining shared** budget (also capped by 20% of the configured budget).
Existing maximum packing trials and the five-plan cache/gallery limit remain.
Regular-only and Panel Saw do not start joint search. Actual hole/void compatibility
is checked before branches start. `_locked_piece_ids` and `_same_nests` protections
remain unchanged for finished groups. Incumbents survive budget expiry and every
final is compared with unchanged `industrial_rank`; joint usage is not a bonus.

Diagnostics stay inside the existing Smart diagnostics object: final Glass/shape
guest counts, completed/unique-valid alternatives, relation-release attempts,
boards before/after and rejection reasons. A completed alternative need not use
both nest types. `guest_reassignments` counts validated temporary relation-release
attempts, not persisted moves or distinct doors. No diagnostic DB/UI fields added.

## Manufacturing limitation retained safely

A valid-width machining mark on a Glass guest reproduced `OVERLAY_SPANS_HOSTS` in
the existing Strict Import overlay ownership reconciliation: both the Glass outer
contour and its guest appear as owners. This is independent of packing validity.
Smart conservatively keeps these machining guests outside Glass, retaining their
source addons unchanged. It does not change DXF/overlay ownership to accept them.
The baseline addon portfolio fails Strict Import; its numerical score is not a
manufacturing-valid incumbent. Non-quarter clipped guests remain excluded too.

## Matched 10-second measurements

[Before](benchmark-before.csv) and [after](benchmark-after.csv): **64 observations**
from 32 matched inputs. These comprise all existing 24 V2 Smart cases (CNC + Panel
Saw) and eight source-only CNC witnesses. Same rows, boards, 3 mm Kerf, case trim,
rotation flags, mirroring disabled, seed derivation, remnant settings 30×30 cm /
0.09 m² and exact-piece limit 20; budget 10 seconds per observation. These are
synthetic reproducers, not customer orders or global-optimum claims.

| Witness | Boards before→after | Offcut m² before→after | Glass / shape guests after | Total seconds before→after |
|---|---:|---:|---:|---:|
| Independent Glass + L | 2→1 | 0.276458→0 | 1 / 1 | 1.841→2.719 |
| Competing guest | 1→1 | 0.122109→0.122109 | 1 / 1 | 1.568→2.075 |
| Glass + Clipped, quarter turns | 2→1 | 0.304668→0 | 1 / 1 | 1.755→2.563 |
| Machining guest safety guard | 2→2 | 0.304668→0.304668 | 0 / 0 | 1.660→1.731 |
| Glass inside L, child inside Glass | 2→1 | 0.705109→0 | 1 / 1 | 1.171→1.586 |
| Joint is not best | 1→1 | 0→0 | 6 / 0 | 1.328→1.999 |
| Regular-only | 1→1 | 0.600000→0.600000 | 0 / 0 | 0.133→0.132 |
| Mixed Glass + L + Clipped | 2→1 | 0.440076→0 | 2 / 2 | 4.972→6.929 |

Fewer boards take priority over the offcut on a discarded extra board. The
competing witness was already solved jointly by the original full search; the
new targeted regression separately proves recovery from its wrong shape-first
allocation: guest 6 moves to Glass and guest 7 fills the shape void. No improvement
is claimed for that already-solved default.

All 24 original cases retain their industrial rank or improve it; none regress.
Large-120 stays at 11 CNC / 12 Panel Saw boards. Glass-gap CNC and L-positive-trim
CNC stay at one board. L-mixed stays at 2 boards / 0.905980 m² CNC and 2 / 0.956480
m² Panel Saw. The pre-existing CNC gap to independent old Deep (0.960140 m²)
remains; P4 does not claim to close it.

All **141 after-candidate snapshots** pass real JS Export → full Strict Import;
all 32 after portfolios pass. Before, 31/32 portfolios pass; the addon witness
fails with `OVERLAY_SPANS_HOSTS`, explicitly retained in the evidence CSV.
Every portfolio contains five unique snapshots except the existing single/few-plan
boundary cases. [Detailed internal counts/times/RSS](joint-diagnostics.csv).

Maximum after total is 10.469 seconds (Large-120). Search deadlines are shared;
atomic packing, validation and snapshot projection can finish after the deadline.
No hard real-time promise or increase in configured search time is made.

Peak process RSS in matched runs: CNC batch 131180→131052 KiB; Panel batch
50600→50552 KiB; seven-witness joint batch 28360→28504 KiB (+144 KiB); standalone
mixed witness 22500→22656 KiB (+156 KiB). RSS includes interpreter/imports and is
not an isolated incremental heap measurement. Wall times are single observations
and may overlap local validation; no speedup/statistical performance claim.

## Active safety/lifecycle validation

Tests cover joint discovery through Smart, separate-path comparison, contested
assignment recovery, zero/positive Kerf, denied rotation, permitted/denied mirroring,
Panel/regular gates, real outlines, stable piece IDs, isolated subtree release,
expired budget, rank-first selection and unique five-plan portfolios.

Every new manufacturing witness tests JSON reload and all alternative snapshots
through actual JS export/full Strict Import. Reader tests protect persisted corner
transforms. The native Frappe test exercises Generate→Select→Save→Reload→native
validation→native export rebuild→JS Export→Strict Import, forbidding optimization
during save. Existing first-plan, cancellation, expiry, replay, concurrent-edit,
permissions, stage, cost, OFFCUT, approval/upload and fingerprint tests stay active.

Initial native certification correctly rejected the reader projection mismatch;
it was not bypassed. Final native/Static/Chromium results are recorded on the final
HEAD in PR #574 after completion. No customer site or machine was changed/tested.

```bash
# Run each checkout's real modules; fixtures are pure source data.
python /path/to/scripts/benchmark_joint_nesting.py --cases-file /path/to/almdina_erp/tests/joint_nesting_cases.py --label before --output /tmp/before.json --time-limit 10
python scripts/benchmark_joint_nesting.py --cases-file almdina_erp/tests/joint_nesting_cases.py --label after --output /tmp/after.json --time-limit 10
python scripts/benchmark_cutting_p1.py --label after --output /tmp/cnc.json --time-limit 10 --mode 'Smart Search'
python scripts/benchmark_cutting_p1.py --label after --output /tmp/panel.json --time-limit 10 --mode 'Smart Search' --machine-type 'Panel Saw'
python scripts/verify_cutting_benchmark_dxf.py --input /tmp/cnc.json --input /tmp/panel.json --input /tmp/after.json --output /tmp/strict.csv
python -m pytest -q almdina_erp/tests/test_joint_nesting.py almdina_erp/tests/test_glass_opening_nesting.py almdina_erp/tests/test_cutting_shape_search.py almdina_erp/tests/test_nesting_consolidation.py almdina_erp/tests/test_smart_cutting_search.py almdina_erp/tests/test_smart_plan_portfolio.py almdina_erp/tests/test_smart_cutting_manufacturing.py almdina_erp/tests/test_smart_cutting_lifecycle.py
# Isolated Frappe test site only:
bench --site test.localhost run-tests --module almdina_erp.tests.test_smart_cutting_integration
```
