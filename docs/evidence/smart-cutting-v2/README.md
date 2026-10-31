# Smart Nesting V2 — final-plan portfolio and exact selection

Branch: `feature/smart-cutting-search`, existing Draft PR #574. Base remains
`fix/cutting-best-valid-plan`; PR #570 is unchanged. V1 source:
`0ec95804ee23fe02978b379ca5b299a7cf610d50`. Measured V2 production source:
`500fcf3bf6d990ede843977c58d28e27523af544`.

## Change contract

Goal: retain useful manufacturing-valid alternatives, preview them quickly, and
save exactly the selected server snapshot. Scope: existing optimizer orchestration,
application snapshot projection, cached Preview Session/service, System plan tabs,
preview presenter and tests. No packing engine, database schema, DXF identity or
validator change, historical fingerprint change, OFFCUT pricing change, migration,
approved/uploaded transition change, streaming or WebSocket is introduced.

Kerf, preferred trim, machine, rotation and mirroring permissions remain fixed
through each search and continuation. Adaptive Trim uses its existing policy;
effective per-axis margins and reasons remain visible through the existing renderer.
Physical setting edits retain their existing capability checks. New UI messages have
Arabic translations; geometry rendering and existing Zoom/Print/Export controls are
reused. Rollback consists of reverting these commits; temporary cache entries expire.

## Cause and search change

V1 kept one final result and discarded its internal alternatives. Its rectangular
seed selection also removed layouts before Glass, Shape-Aware and Plan Search had
finished, even when those later passes could produce a better final result. Repeating
the same winning rectangular configuration does not fix that loss.

V2 finishes the Auto seed first and retains its proven result. Short batches of
distinct existing Pro orders/local cycles promote both a rectangular leader and a
different layout. Existing deterministic Deep restarts are reused with an incumbent
and a completion callback, rather than running a second full optimizer. Completed
Glass/shape/search results are compared using unchanged `industrial_rank` and the
existing comparator. Small ordinary rectangular CNC problems may still receive
CP-SAT with remaining time. Legacy modes retain their existing paths.

At most five distinct valid snapshots survive. Geometry signatures ignore algorithm
names, labels, diagnostics and financial metadata. They retain piece/copy identity,
sheet dimensions/margins, placements, outlines, holes/hosts, clipped geometry,
rotation/mirroring and machining addons. Numeric representations, polygon start/
winding and JSON key/whitespace differences are normalized. A single distinct valid
plan remains a single card; alternatives are never fabricated.

One deadline is shared with Adaptive Trim. Search is capped at 500 packing trials
per batch and at most 17 completed-seed evaluations, including Auto and optional
exact output. Atomic packing, mandatory feasibility, validation and snapshot
projection can finish after the search deadline. The 10-second benchmark has a
maximum observed total of about 10.54 seconds; no hard real-time guarantee is made.

## Trust and lifecycle

The server retains snapshots and warm seeds in the existing 15-minute cache. The
browser receives candidate IDs and safe summaries plus the displayed snapshot.
Selection fetches an existing snapshot; it neither packs nor writes a plan. The
gallery is physically left on desktop, follows Arabic RTL internally and collapses
on mobile. It is wrapped inside the System tab only. Existing source-tab/edit
ownership continues to keep transient previews apart from approved/uploaded plans.

Preview/select/continue/save recheck document read scope, RECALCULATE_PLAN, stage
assignment and lifecycle. Physical setting changes additionally require
EDIT_OPTIMIZER_SETTINGS. The session checks owner/order, expiry, source name,
modified time, revision, settings hash and live generation fingerprint. Candidate
lookup checks its server-issued ID, manufacturing status and geometry hash.

Save holds the existing per-order database lock, consumes the token, applies the
selected cached snapshot exactly, computes plan-owned official cost and returns
candidate ID/hash in the receipt. It never invokes the optimizer. Displayed cost
estimates are calculated only on detached documents, only for the displayed plan
and only with VIEW_COSTS. Cancel/expiry leaves the previous saved plan intact.
First-System preview uses a detached source; the first plan is inserted only on
explicit save. Revision and fingerprint checks also cover this path.

Continue is an explicit request for one additional batch at the same configured
budget. It warms from proven candidates, retains the previous best, replaces the
old token and preserves the original expiry. There are at most three batches per
preview. A per-order lock serializes continuation and save; old/replayed tokens
cannot save. No automatic background search or unbounded retry is added.

Manufacturing gates check complete identity, geometry/Kerf, placement permissions
and existing native export validation. The known non-quarter clipped-void guest
remains excluded because its strict DXF identity cannot be proved. The legacy CNC
Clipped-quad one-board layouts still fail strict import; V2 deliberately retains
two importable boards. No validator is weakened to improve a reported score.

## Matched 10-second benchmark

[All measurements and strict-import results](benchmark.csv): 144 observations:
12 identical synthetic cases × 5 V1 modes × 2 machine types, followed by V2 Smart
on those same 24 inputs. These are reproducible synthetic fixtures, not customer
orders. All use the same board/rows, 3 mm Kerf, case-specific preferred trim,
rotation permissions, mirroring disabled, 30×30 cm / 0.09 m² remnant thresholds
and exact-piece limit 20. Budget is 10 seconds in every observation. Times are
single wall-clock observations on this environment; no speedup claim is made.

All 144 default snapshots pass geometry validation. All 24 V2 portfolios contain
1–5 unique valid plans: 52 CNC + 49 Panel Saw = **101 candidate snapshots**. Every
one passes the real JS exporter followed by full Strict Import. All 24 V1 Smart
defaults pass too. The only four legacy strict-import failures are CNC
Clipped-quad under Auto/Auto Pro/Deep/Optimal, retained explicitly in the CSV.

No V2 default regresses board count or reusable offcut against V1 Smart in these
24 measured cases. L-mixed improves on both machines. V2 CNC is still below the
best independently run old Deep result; no superiority or global optimum is claimed.

| Case / machine | V1 boards / offcut m² | V2 boards / offcut m² | V2 unique | V2 seconds |
|---|---:|---:|---:|---:|
| L-mixed / CNC | 2 / 0.799800 | 2 / 0.905980 | 5 | 3.8065 |
| L-mixed / Panel Saw | 2 / 0.777140 | 2 / 0.956480 | 5 | 2.9558 |
| Large-120 / CNC | 11 / 0.850038 | 11 / 0.850038 | 5 | 10.5348 |
| Large-120 / Panel Saw | 12 / 1.892220 | 12 / 1.892220 | 5 | 10.4948 |
| Glass-assignment-gap / CNC | 1 / 0 | 1 / 0 | 5 | 0.4384 |
| L-positive-trim / CNC | 1 / 0 | 1 / 0 | 5 | 6.3192 |
| Mandatory-gap / CNC | 2 / 0 | 2 / 0 | 1 | 0.0758 |

Old Deep L-mixed: CNC 2 boards / **0.960140 m²**, Panel Saw 2 / **0.956480 m²**.
V2 matches the Panel Saw witness and improves V1 CNC, while retaining the documented
CNC gap. Producing more plans costs additional work; the configured budget is
unchanged and continuation always requires an explicit click.

## Active validation and reproduction

- Domain/application tests: distinct final plans, best retention, invalid-candidate
  exclusion, metadata deduplication, identities/holes/addons/reflections, single-plan
  output, bounded warm continuation, unchanged physics and Adaptive Trim.
- Native Frappe `TestSmartCuttingIntegration`: DB unchanged during preview and
  selection; exact chosen save with optimizer forbidden; cost recalculation; replay,
  cancel, expiry, concurrent source edits, wrong IDs/owner/order, fingerprint changes,
  first-plan creation, continuation/token replacement and real capability checks.
- Every manufacturing witness now tests all alternatives through JSON save/reload,
  independent geometry/permission validation, real JS Export and Strict Import.
- Node session tests cover read-only switching, forged IDs, wrong candidate receipts,
  mismatched snapshot identity, stale in-flight responses, expiry and continuation.
- Chromium tests use the shipped session/presenter/renderer and actual generated
  snapshots at 1280 px and 390 px in Arabic RTL. They verify physical left placement,
  collapse, no page overflow, read-only switching, explicit continuation and one-plan
  copy. They are a component certification; native Frappe persistence is tested
  separately. Screenshots are uploaded by the existing Chromium workflow.

```bash
# Run from each measured checkout; the script uses that checkout's real modules.
python /path/to/scripts/benchmark_cutting_p1.py --label v1 --output /tmp/v1-cnc.json --time-limit 10 --include-smart
python /path/to/scripts/benchmark_cutting_p1.py --label v1 --output /tmp/v1-panel.json --time-limit 10 --include-smart --machine-type 'Panel Saw'
python scripts/benchmark_cutting_p1.py --label v2 --output /tmp/v2-cnc.json --time-limit 10 --mode 'Smart Search'
python scripts/benchmark_cutting_p1.py --label v2 --output /tmp/v2-panel.json --time-limit 10 --mode 'Smart Search' --machine-type 'Panel Saw'
python scripts/verify_cutting_benchmark_dxf.py --input /tmp/v1-cnc.json --input /tmp/v1-panel.json --input /tmp/v2-cnc.json --input /tmp/v2-panel.json --output /tmp/benchmark.csv
python -m pytest -q almdina_erp/tests/test_smart_plan_portfolio.py almdina_erp/tests/test_smart_cutting_search.py almdina_erp/tests/test_smart_cutting_manufacturing.py
node almdina_erp/tests/js/plan_candidate_gallery.test.js
python -m pytest -q tests/browser/test_smart_plan_gallery_chromium.py
# Isolated test Frappe site only:
bench --site test.localhost run-tests --module almdina_erp.tests.test_smart_cutting_integration
```

Final-head CI links and actual outcomes are recorded in PR #574 after completion.
