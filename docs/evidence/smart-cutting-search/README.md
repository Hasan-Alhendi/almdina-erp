# Smart Nesting — implementation and evidence

Source: `fix/cutting-best-valid-plan` at `e09092019bdcb08115412bbac4af729c8805715c`.
Branch: `feature/smart-cutting-search`. Stacked Draft PR; no merge or force push.

## Change contract and cause

Goal: one operator UI and one server-owned search for new System calculations.
Scope: Domain orchestration, presentation, necessary plan/preview adapters and tests.
Excluded: new packing engines/models, pricing, OFFCUT policy, production transitions,
DXF validators/identity contracts and historical data migration.

Each legacy mode selected a rectangular baseline before Glass/shape/search passes.
That premature selection could discard an Auto layout with better final nesting.
Smart finishes and retains the Auto seed, then compares independently valid complete
plans. Existing `industrial_rank`, `_candidate_is_better`, geometry/Kerf validation
and placement permissions remain authoritative. Strict improvements replace the
incumbent; stable generation order resolves ties.

## Architecture and search limits

- `smart` maps to `Smart Search`; all historical IDs/engine modes and the global
  `auto_pro` fallback remain intact. `settings_for_system_search` is the central
  server policy for new System creation/calculation and preview normalization.
- Auto is run once. Up to 64 additional unique kernel/order trials reuse Pro
  ordering, local sequences, repeated-size cycles and deterministic Deep restarts.
  Equivalent packing configurations/orders and geometric layouts are deduplicated.
- A bounded pool keeps three rectangular leaders plus two diverse seeds even
  when their rectangular rank is worse. At most six seeds, including Auto, receive
  complete post-passes. A raw candidate that improves the incumbent is validated
  immediately so expiration before post-passes cannot discard a valid improvement.
- Selective CP-SAT is restricted to small ordinary rectangular CNC problems; it
  receives only remaining time and never certifies irregular-shape optimality.
- One deadline includes Auto startup, optional trials and post-passes; Smart
  Adaptive Trim probes receive remaining budget. Saved time/Kerf/trim/machine
  values do not change. Atomic packing, validation and mandatory trim feasibility
  work can overrun the deadline. `search_elapsed_sec`, requested search limit,
  `total_elapsed_sec`, trim probe count and overrun diagnostics distinguish these.
- No algorithm picker remains in the plan editor, summary, requested trace row,
  native plan/settings fields or factory settings dialog/summary. Existing RTL
  layout and all physical settings stay in place. Storage and preview `SETTINGS`
  arrays retain the internal mode. New copy has Arabic translations.

## Lifecycle, permissions and compatibility

The mode is selected before the generation fingerprint. A browser-supplied legacy
executable mode cannot override Smart; unavailable/unknown explicit API modes still
fail validation. Recalculation requires `RECALCULATE_PLAN`; mode selection alone
never requests `EDIT_OPTIMIZER_SETTINGS`. Physical setting changes still require
that capability. Existing preview editing permissions, lifecycle and assignment
gates remain. Preview calculates only in memory; commit uses the trusted cached
settings/snapshot, rechecks ownership/revision/fingerprints, and never reoptimizes.
Background jobs continue through the same command and freshness policy.
Historical reads, frozen historical settings/hashes, approved/uploaded snapshots,
revision protection and production routing are unchanged. No backfill is added.
Metadata visibility/options are synchronized by the normal Frappe migration.

## Manufacturing evidence and intentional conservative selection

The real JS exporter followed by the full strict importer reproduced
`EXPECTED_PIECE_MISMATCH` for a non-quarter-angle guest inside four clipped corners.
`validate_plan` alone accepted that older geometry. The importer has no complete
proven identity contract for this path; this change does not weaken it or expand
DXF support. Smart rejects these candidates during final selection and retains a
valid earlier stage. The legacy modes/algorithms remain reproducible.

For the synthetic CNC Clipped-quad, all four legacy modes produce one geometry-valid
board that **fails strict import**. Smart chooses two boards that pass strict import.
This is an explicit manufacturing safety tradeoff, not a claimed nesting saving.

Six dedicated witnesses cover L quad/guests, clipped quad/angled-candidate fallback,
positive trim, Glass host/guests, repeated rotated pieces on multiple sheets and
liner/addons. Tests cover JSON save/reload/independent validation/actual JS export/
strict import. The Frappe integration class repeats these through actual plan
commands and database reload, exercises exact preview commit, background freshness,
and a real user with recalculation permission but no settings-edit permission.

## Matched benchmark

[All 120 measurements and strict-import outcomes](benchmark.csv): 12 synthetic
cases × 5 modes × 2 machine types. Historical modes run from the unchanged source
checkout; Smart runs from this implementation. Same rows/full board, Kerf 3 mm,
preferred trim per case, rotations/mirroring, remnant thresholds 30×30 cm/0.09 m²,
2-second requested budget and exact limit 20. Large-120 therefore uses the legacy
Optimal heuristic fallback. These are reproducers, not customer orders or proof
that an unseen order can fit in three boards. Times are single wall observations;
source measurements may overlap other work, so no speedup claim is made.

All 120 snapshots passed independent geometry validation. All 24 Smart snapshots
passed actual JS export and full strict import. The only four strict-import failures
were the legacy CNC Clipped-quad variants above. Smart retained the best valid
candidate it actually evaluated, without a board/rank regression among those
candidates. It does **not** guarantee the best independently run legacy result:
L-mixed reusable offcut is lower than legacy Deep on both machines.

| Case | Machine | Smart boards | Reusable offcut m² | Actual seconds | Strict import |
|---|---|---:|---:|---:|---|
| L-tight | CNC Router | 1 | 0.000000 | 0.2153 | Pass |
| Clipped-quad | CNC Router | 2 | 0.150319 | 0.1977 | Pass |
| L-positive-trim | CNC Router | 1 | 0.000000 | 1.7367 | Pass |
| Rectangular | CNC Router | 2 | 0.193725 | 0.4284 | Pass |
| L-mixed | CNC Router | 2 | 0.799800 | 0.8568 | Pass |
| Glass-clipped | CNC Router | 3 | 0.600000 | 0.69 | Pass |
| Large-120 | CNC Router | 11 | 0.850038 | 2.1378 | Pass |
| Adaptive-trim | CNC Router | 1 | 0.000000 | 0.1173 | Pass |
| Glass-assignment-gap | CNC Router | 1 | 0.000000 | 0.1263 | Pass |
| L-pair-offcut | CNC Router | 2 | 0.200000 | 0.3322 | Pass |
| Boundary-kerf | CNC Router | 1 | 0.000000 | 0.0186 | Pass |
| Mandatory-gap | CNC Router | 2 | 0.000000 | 0.029 | Pass |
| L-tight | Panel Saw | 2 | 0.122109 | 0.0881 | Pass |
| Clipped-quad | Panel Saw | 2 | 0.150319 | 0.0653 | Pass |
| L-positive-trim | Panel Saw | 2 | 0.000000 | 0.2626 | Pass |
| Rectangular | Panel Saw | 2 | 0.000000 | 0.0958 | Pass |
| L-mixed | Panel Saw | 2 | 0.777140 | 0.4015 | Pass |
| Glass-clipped | Panel Saw | 3 | 0.300000 | 0.1715 | Pass |
| Large-120 | Panel Saw | 12 | 1.892220 | 2.1904 | Pass |
| Adaptive-trim | Panel Saw | 1 | 0.000000 | 0.0484 | Pass |
| Glass-assignment-gap | Panel Saw | 2 | 0.000000 | 0.0512 | Pass |
| L-pair-offcut | Panel Saw | 2 | 0.200000 | 0.0982 | Pass |
| Boundary-kerf | Panel Saw | 1 | 0.000000 | 0.0095 | Pass |
| Mandatory-gap | Panel Saw | 2 | 0.000000 | 0.011 | Pass |

CNC Large-120 improves Auto 12→11 and matches Pro/Deep/Optimal's 11. Rectangular
matches 2 boards / 0.193725 m². Glass-assignment-gap remains 1 CNC board; Glass-clipped
remains 3. L-mixed CNC: Smart 0.7998 m² versus legacy Deep 0.96014 m², both 2 boards.
Panel Saw L-mixed: Smart 0.77714 m² versus legacy Deep 0.95648 m², both 2 boards.
No global optimality, ten Large-120 boards or two Glass-clipped boards are proven.

Reproduce from this checkout (run the four old modes from a source worktree):

```bash
python /path/to/smart-checkout/scripts/benchmark_cutting_p1.py --label source --output before-cnc.json
python scripts/benchmark_cutting_p1.py --label smart --mode 'Smart Search' --output after-cnc.json
# Repeat both with --machine-type 'Panel Saw'.
python scripts/verify_cutting_benchmark_dxf.py --input before-cnc.json --input after-cnc.json --input before-panel.json --input after-panel.json --output benchmark.csv
```

## Changed production files

- Domain: `domain/cutting/catalog.py`, `optimizer.py`, `plan_settings.py`.
- Application: `application/cutting/optimize_order_plan.py`.
- Infrastructure: `infrastructure/frappe/cutting_plan_command_repository.py`,
  `cutting_plan_workspace.py`.
- Services: `services/cutting_plan_command_service.py`, `cutting_plan_preview_service.py`.
- Metadata: `doctype/cutting_plan/cutting_plan.json`,
  `doctype/almdina_erp_settings/almdina_erp_settings.json`.
- DCO presentation: `door_cutting_order_plan_edit_session_ux.js`,
  `door_cutting_order_plan_settings_summary_ux.js`, `door_cutting_order_plan_preview_session.js`,
  `door_cutting_order_plan_preview_presenter.js`, `door_cutting_order_plan_controls_ux.js`.
- Factory presentation: `factory_production_settings/dialogs.js`, `view_model.js`.
- Arabic translation catalog. Other changes are focused tests, benchmark/evidence,
  canonical docs and Static Checks scheduling/coverage for the stacked PR base.

## Validation and limits

Targeted catalog/settings/permission/preview/fingerprint/application/background suites:
127 passed + 47 subtests before the final two added regressions. Final focused suites:
45 passed + 49 subtests. The local Static Checks command sequence was run; historical
mode enumeration and metadata-visibility tests were updated for the explicit new
contract, with frozen historical rejection of Smart retained. No assertion was
weakened or new skip added. Final affected local Static Checks passed (940 tests + 22 subtests in the optimizer/UI
step, one pre-existing skip; all other scheduled local steps passed). GitHub/Frappe CI results
are recorded in the Draft PR.

Remaining limits: non-quarter void-guest strict import is deliberately excluded from
Smart; pre-existing Panel Saw touching L contours at Kerf=0 can still fail closed in
all modes; deadlines are cooperative around existing atomic stages; bounded search
can miss an independent Deep result; live Arabic Desk screenshots, physical CNC
execution and the original customer orders are not certified. Rollback is code/
metadata only; no stored plan migration is needed. Existing Smart snapshots remain
readable with this catalog; rolling back to code predating the new catalog requires
retaining its read compatibility.
