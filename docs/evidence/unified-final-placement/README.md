# Unified Centering & Edge Protection — isolated production replay

## Change contract and provenance

Goal: one geometry decision for positive protection, with fair bounded opportunities and measurable safety.
Scope: Domain final placement, Application candidate scheduling/diagnostics, and the export reconstruction defect exposed by the real Handle Recess round trip. No optimizer, setting, dependency, schema, capability, financial authority or deployment change.
Invariants: identical packing, piece IDs/dimensions/rotation/board membership; mandatory trim, continuous Kerf movement, manufacturing validation, frozen protected geometry, connected qualified remnants; unchanged V1–V4 definitions and disabled-policy execution path. Rollback is the feature commit; saved plans are never recalculated by reading/opening/exporting.

Read-only GETs on 2026-11-21 captured CP-2026-00653 / 00676 / 00677 / 00681 / 00709 for orders 26-00331 / 344 / 345 / 346 / 347. Raw documents remain private outside the repository. Fixtures retain geometry, machining metadata, quantities, rotation permissions and band thicknesses, with anonymized identities and no cost/contact fields. Occupancy outlines, holes and machining metadata were compared to the raw saved records for every piece: **zero differences on all five orders**. The fixtures preserve both saved coordinates and entry coordinates reconstructed by reversing recorded final shifts only; early centering/packing cannot be reversed from that snapshot. No claim of access to all historical gallery finalists or proof of the deployed Git SHA.

Baseline comparison loads the unmodified reviewed **50f2b956** modules directly from Git. Same geometry, 30 s configured alignment, 24 expensive trials, 64 pieces/sheet, four refinement rounds, same remnant thresholds 30×30 cm / 0.09 m². Timings are individual local wall-clock samples, not server predictions or statistical speed guarantees. Process peak MiB includes Python/imports and earlier orders in that process.

## 1. Why the saved 17-board plan stopped after eight boards

The saved CP-2026-00677 proves `tested=8`, `accepted=8`, `sheets_reached=8`; search 63.517 ms, preparation 92.659 ms, finalization 209.392 ms, snapshot validation 119.612 ms. Boards 8–13 were discovered but not tried; 15–16 stopped during preparation and 17 was not discovered. Rejected prechecks on earlier boards do not establish geometric impossibility on any later board.

The first broken time boundary is **not necessarily the native gallery's 30 s**. Both `_refine_smart_gallery` and `_refine_pattern_gallery` in the reviewed source cap **each projected candidate at 150 ms, including snapshot preparation**, inside the already bounded ALNS/Pattern stage. 150 − 92.659 = 57.341 ms before cooperative-call overrun, consistent with the saved ~63.5 ms tail. The saved Smart trace includes ALNS and Pattern improvements and nine completed candidates, but does not identify the winning candidate's budget source or preceding candidates' deadlines. Therefore the 150 ms cap is a code-proven, reproduced starvation path; the exact historical winning stage/timeline cannot be recovered from missing fields. New diagnostics record source, allocated slice, shared remaining time, previous candidate finalization, and remaining time at Domain/sheet entry.

Positive projection now shares the **remaining existing stage deadline** across unprojected candidates, capped once by configured alignment time. It never restarts that cap per candidate and adds no time to the stage. Disabled protection retains the old projection cap. Native gallery candidates still share their original absolute 30 s deadline. Mandatory validation is atomic and can finish after expiry; no new trial starts afterward.

## 2. Root causes proved before changing production code

The initial regression run on 50f2b956: **7 failed, 7 passed**. Failures prove duplicate objective weights from overlapping groups, sensitivity to candidate-group multiplicity, early centering under positive policy, giving back already accepted cutter improvement, the 150 ms projection cap in both ALNS and Pattern, and real board 8 choosing 15/20 instead of 17.5/17.5 mm. A further failing regression proves one rejected precheck at expiry was incorrectly labeling the whole axis GEOMETRY_REJECTED; it now reports time exhaustion while preserving the individual rejection.

1. Early `realize_sheet_edge_trim(balance_existing_applied=True)` ran before remnant rollback and compaction: confirmed by call-order/source and a failing spy regression. Positive placement bypasses it; mandatory trim is already established by packing. Zero policy retains the old calls/order exactly.
2. Eligible centering followed displacement in acceptance/proposal ranking: confirmed by source and the real 35 mm gap regression. It now precedes displacement after higher priorities.
3. `_placement_goals` used all overlapping candidate groups: confirmed by partition and multiplicity regressions. Physical goals now partition eligible pieces per axis using perpendicular projection bands frozen after compaction. These are objective regions, not forced rigid bodies. Movement candidates still include independent pieces, contact chains, whole translations and compound groups.
4. Native Basic/Refinement fairness already existed at reviewed HEAD; it was not enough for a 150 ms projection cap consumed by preparation. Fair stage sharing fixes that boundary. Physical-goal discovery is cheaper; expensive overlapping candidate discovery remains after every board's basic opportunity.
5. One bounds/Kerf/swept rejection does not exclude alternatives: confirmed by actual staggered/T tests where the isolated move fails the cutter contract but coupled unequal offsets succeed atomically. Incomplete search now remains explicit.

## 3. What the unified decision values

Every accepted proposal passes the shared continuous movement/bounds/Kerf guard, both-axis debt guard, complete actual cutter network, qualified connected remnant successor guard, source-identity/unchanged-board proof, full changed-board geometry and permission validation, manufacturing export restrictions, and final independent whole-plan engine validation. No half compound move can commit.

After these gates: attainable protection debt; qualified remnant quality; actual cutter length/internal continuity/segment quality; disjoint-axis alignment; eligible centering; stability. Remnant protection is a hard gate before scoring. Cutter quality is guarded against the **current accepted** profile, not just the original. On equal length neither continuity nor segment count may worsen. Count may rise only with proven shorter full union, as in the existing positive-policy contract.

Basic compares a bounded set of centering/minimum-inset single, X/Y and coordinated physical-group endpoints with real cutter metrics. Coordinated endpoints run before an easy isolated improvement can consume sharing needed by its neighbor. Refinement still uses four rounds and the same 24-trial cap. Candidate geometry is temporary; only fully validated improvements commit.

Each diagnostic goal reports fixed baseline eligibility/slack, actual gaps, requested shortfall, attainable debt and centering error. Each accepted trial records its first improved priority and before/after scores/cutter profiles. `EDGE_PROTECTED` means an accepted placement, not a promise that an infeasible requested margin was reached; the explicit requested shortfall remains visible. `search_status` records incomplete refinement separately.

## 4. Equal-input results

### Isolated existing refinement tail

Both versions are given the same **1.5 s remaining stage**, with the reviewed code retaining its own 150 ms placement cap. This reproduces the faulty scheduling boundary without changing packing or simulating a server recalculation.


| Order | Boards / pieces | Reached before → after | Trials after | Accepted / rejected trials after | Changed boards after | Seconds before → after |
| --- | --- | --- | --- | --- | --- | --- |
| 26-00331 | 2 / 12 | 2 → 2 | 10 | 2 / 8 | 2 | 0.111 → 0.089 |
| 26-00344 | 8 / 76 | 0 → 8 | 24 | 8 / 16 | 6 | 0.231 → 0.497 |
| 26-00345 | 17 / 115 | 0 → 17 | 24 | 17 / 7 | 17 | 0.232 → 0.727 |
| 26-00346 | 2 / 21 | 2 → 2 | 10 | 0 / 10 | 0 | 0.150 → 0.155 |
| 26-00347 | 1 / 5 | 1 → 1 | 5 | 1 / 4 | 1 | 0.061 → 0.039 |


For the 17-board repaired replay, **zero boards remain unexamined because of time**. All 17 receive a real trial; 17 trials accept and seven reject at the existing cap. Relative to the actual saved geometry, the additional changed boards are **8, 9, 10, 11, 12, 13, 15, 16, 17**. With a full 30 s Domain allowance, reviewed HEAD already reaches 17; its flaw is also objective selection, not solely first-board scheduling. The fixed Domain result has the same 231608 mm union as that full-budget baseline, with better centering on board 8 and useful coupled protection on 17.

### Five candidates

Five copies of each captured geometry are projected to exercise shared gallery scheduling; these are **not** the missing historical five distinct finalists. The 17-board case reaches **[17,17,17,17,17]** in both versions, with at most 24 trials per candidate; unused candidate time returns to later candidates. This is coverage of all 85 opportunities, not a claim that the displayed deduplicated gallery contains five copies.


| Order | Five-candidate seconds before → after | Peak process MiB before → after |
| --- | --- | --- |
| 26-00331 | 0.624 → 0.543 | 41.48 → 40.37 |
| 26-00344 | 4.778 → 2.626 | 45.28 → 43.93 |
| 26-00345 | 3.285 → 3.161 | 48.14 → 47.39 |
| 26-00346 | 1.249 → 0.713 | 48.14 → 47.39 |
| 26-00347 | 0.230 → 0.196 | 48.14 → 47.39 |


### Dense synthetic coverage, 48 pieces/board, original 30 s allowance


| Boards | Reached before → after | Trials after | Accepted after | Seconds before → after |
| --- | --- | --- | --- | --- |
| 1 | 1 → 1 | 5 | 1 | 1.024 → 1.192 |
| 2 | 2 → 2 | 10 | 2 | 2.520 → 2.057 |
| 8 | 8 → 8 | 24 | 8 | 7.492 → 6.911 |
| 17 | 17 → 17 | 24 | 17 | 12.439 → 13.384 |


No claim that every case is faster. Dense 17-board quality evaluation costs more than reviewed HEAD in this sample; both cover 17. The cap needs **redistribution**, not an arbitrary increase: one basic expensive trial per board leaves seven for refinement. More boards than trials, heavy validation or a genuinely exhausted stage can still prevent coverage and are reported explicitly.

## 5. All 17 saved-board margins and remaining limits

Physical millimetres; X = left/right, Y = top/bottom. Saved coordinate origin is top-left. The user's `0/381` Y wording on board 15 is reversed in the saved geometry: its actual top/bottom is **381/0**, so the minimum safe motion yields **361/20**, preserving the large remnant's side.


| Board | Saved X → final X | Saved Y → final Y | Trials / accepted | Why protection remains limited |
| --- | --- | --- | --- | --- |
| 1 | 4.5/4.5 → 4.5/4.5 | 61/20 → 61/20 | 2/1 | X slack 9 mm: best balance 4.5/4.5; Y protected. |
| 2 | 4.5/4.5 → 4.5/4.5 | 7.5/7.5 → 7.5/7.5 | 2/1 | X slack 9; Y slack 15: balanced below request. |
| 3 | 4.5/4.5 → 4.5/4.5 | 215/20 → 215/20 | 1/1 | X slack 9: balance 4.5/4.5; Y minimum inset (235 mm outside eligibility). |
| 4 | 4.5/4.5 → 4.5/4.5 | 215/20 → 215/20 | 1/1 | X slack 9: balance 4.5/4.5; Y minimum inset (235 mm outside eligibility). |
| 5 | 4.5/4.5 → 4.5/4.5 | 215/20 → 215/20 | 1/1 | X slack 9: balance 4.5/4.5; Y minimum inset (235 mm outside eligibility). |
| 6 | 4.5/4.5 → 4.5/4.5 | 215/20 → 215/20 | 1/1 | X slack 9: balance 4.5/4.5; Y minimum inset (235 mm outside eligibility). |
| 7 | 4.5/4.5 → 4.5/4.5 | 215/20 → 215/20 | 1/1 | X slack 9: balance 4.5/4.5; Y minimum inset (235 mm outside eligibility). |
| 8 | 0/35 → 17.5/17.5 | 23/23 → 23/23 | 2/1 | Centerable 35 mm band centers; shared-cutter-compatible whole offset. |
| 9 | 0/73 → 15/58 | 4/4 → 4/4 | 2/1 | 73 mm exceeds 70 mm eligibility; minimum inset. Y slack 8. |
| 10 | 0/119 → 15/104 | 10.5/10.5 → 10.5/10.5 | 2/1 | 119 mm exceeds eligibility; minimum inset. Y slack 21. |
| 11 | 0/119 → 15/104 | 10.5/10.5 → 10.5/10.5 | 2/1 | Same geometry class as 10. |
| 12 | 0/4.5 → 4.5/4.5 | 81/0 → 61/20 | 2/1 | Original sheet envelope 4.5 mm is misleading: staggered X bands each have 9 mm and balance 4.5/4.5; small part insets separately. |
| 13 | 0/4.5 → 4.5/4.5 | 81/0 → 61/20 | 1/1 | Same as 12; no packing change. |
| 14 | 4.5/4.5 → 4.5/4.5 | 20/1395 → 20/1395 | 1/1 | X slack 9; Y minimum inset preserves the large connected remainder. |
| 15 | 4.5/4.5 → 4.5/4.5 | 381/0 → 361/20 | 1/1 | X slack 9; Y minimum inset preserves top remainder. |
| 16 | 0/4.5 → 4.5/4.5 | 7.5/7.5 → 7.5/7.5 | 1/1 | X slack 9; Y slack 15. |
| 17 | 0/16 → 15/17 | 4.5/4.5 → 4.5/4.5 | 1/1 | Unequal X offsets +15 mm / −1 mm protect bands without losing cutter sharing; Y slack 9. |


All 17 currently report TRIAL_BUDGET for further refinement. This does not invalidate their accepted moves. A finite search is not a proof of global optimality or of every alternative's impossibility. Reinvoking a deliberately incomplete search can find additional improvements; it is not used on saved-plan open/reload. Completed standalone/staggered/mirrored witnesses are deterministic and idempotent. The 17-board incomplete replay is not claimed to be a fixed point.

## 6. Actual time attribution

Selected repaired projection of 26-00345 (milliseconds; nested measures are inclusive and must not be added twice):


| Stage | ms |
| --- | --- |
| Allocated candidate share | 1500.000 |
| Snapshot preparation (including baseline validation) | 97.796 |
| Remaining at Domain entry | 1406.000 |
| groups | 1.498 |
| candidate_groups | 14.692 |
| basic_generation | 34.904 |
| basic_cutter | 20.901 |
| generation_sort | 54.092 |
| policy_events | 9.229 |
| alignment_events | 22.601 |
| event_score | 2.410 |
| sorting | 19.513 |
| translation | 196.533 |
| cutter | 36.187 |
| geometry | 107.321 |
| permissions | 0.935 |
| export_check | 0.523 |
| remnant_quality | 12.863 |
| remnants | 10.878 |
| metrics | 15.970 |
| Complete Domain search | 514.430 |
| All snapshot validation (baseline + final) | 193.942 |
| Complete candidate finalization | 723.997 |


124 movement attempts = 100 precheck rejections + 24 expensive trials; 17 accepted + 7 expensive rejections. Root rejection counts include cheap attempts and therefore differ from expensive rejected trials.


| Board | Remaining at basic entry ms | Local basic slice ms | Preparation ms | Trials / accepted |
| --- | --- | --- | --- | --- |
| 1 | 1406.000 | 82.706 | 1.049 | 2/1 |
| 2 | 1375.000 | 85.938 | 0.964 | 2/1 |
| 3 | 1360.000 | 90.667 | 0.410 | 1/1 |
| 4 | 1360.000 | 97.143 | 0.390 | 1/1 |
| 5 | 1344.000 | 103.385 | 0.382 | 1/1 |
| 6 | 1328.000 | 110.667 | 0.695 | 1/1 |
| 7 | 1328.000 | 120.727 | 0.408 | 1/1 |
| 8 | 1313.000 | 131.300 | 0.523 | 2/1 |
| 9 | 1297.000 | 144.111 | 1.586 | 2/1 |
| 10 | 1281.000 | 160.125 | 1.085 | 2/1 |
| 11 | 1250.000 | 178.571 | 1.009 | 2/1 |
| 12 | 1235.000 | 205.833 | 1.492 | 2/1 |
| 13 | 1203.000 | 240.600 | 1.751 | 1/1 |
| 14 | 1188.000 | 297.000 | 0.748 | 1/1 |
| 15 | 1172.000 | 390.667 | 0.905 | 1/1 |
| 16 | 1156.000 | 578.000 | 1.855 | 1/1 |
| 17 | 1110.000 | 1110.000 | 2.660 | 1/1 |


Five-candidate 26-00345 timing, from final Application diagnostics:


| Candidate | Shared remaining at entry s | Allocated share s | Preparation ms | Domain remaining at entry s | Search ms | Finalization ms | Trials / accepted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 30.000 | 6.000 | 101.978 | 5.890 | 391.002 | 575.553 | 24/17 |
| 2 | 29.406 | 7.351 | 119.281 | 7.242 | 354.175 | 541.759 | 24/17 |
| 3 | 28.859 | 9.620 | 103.118 | 9.511 | 316.680 | 499.150 | 24/17 |
| 4 | 28.343 | 14.171 | 163.196 | 14.000 | 479.476 | 751.248 | 24/17 |
| 5 | 27.562 | 27.562 | 126.133 | 27.437 | 391.153 | 589.915 | 24/17 |


## 7. Cutter, remnants, DXF and regressions

26-00345: saved actual cutter union **231621.5 → 231608 mm**; reconstructed pre-final entry **231630.5 → 231608 mm**. Largest qualified remnant **1.7263 → 1.7019 m²**, exactly the justified 20 mm strip on the large board remainder, still connected and factory-qualified. This is geometrical evidence, not CNC time/clamp/NC certification.

All five isolated orders pass Snapshot JSON persistence, child-table reconstruction, real JavaScript DXF export, AutoCAD normalization and actual Strict Re-import. Exact final coordinates/dimensions and anonymized per-copy identities match. Required machining metadata is preserved and actual emitted CUT_PATH length matches the complete System cutter geometry within 0.05 mm. The real 26-00347 Handle Recess initially failed: `_plan_to_export_snapshot` copied liner fields but omitted handle/rear-groove metadata. It now uses the existing common machining reader; no validator was weakened. Shape-aware imported contours may intentionally lack a System ranking score; their emitted CUT_PATH is measured directly.

Other-order tradeoffs are explicit: 26-00344 changes six boards vs eight under the reviewed objective; its union 114220.5 mm is 52.5 mm longer than the old result, but improves its original 114321.5 mm and preserves largest remnant 0.740421 m² (old 0.722601). Old search could give back current cutter gains. 26-00346 accepts zero rather than two old proposals: ten trials reject lost shared cutter quality; protected Glass/L/Clipped/attached machining remains intact, not a time failure. 26-00347 improves actual union 9068.5 → 9060 mm while consuming a permitted margin strip; the connected qualified remnant remains 1.286332 m² (original 1.328082, reviewed result 1.313662). Exact per-sheet coordinates/rejections/remnants are retained in the JSON files.

Local validation: **379 passed, one skipped, 135 subtests** in the final broad geometry/lifecycle/fingerprint-compatibility/architecture suite, including the expiry-reason regression; another **71 passed** for ALNS recalculation, compound refinement, Pattern Search and coupled corners. Final CI result and exact head are recorded in PR #606. Three JS contracts pass (editor open, candidate gallery/Continue Search, bilingual factory settings). Disabled protection native packing: **241 packing attempts, three boards, five candidates**, exact gallery identity/geometry SHA-256 **5d23b4899c2b10344f374d7078b6d4ea5a7bd292aa697642c5946cae3453608a**, unchanged from the Develop compatibility evidence.

The broader V3 reviewed-schema guard remains a known inherited failure (expected cfd5ace5… vs actual 7a6a4ecd…); neither the schema nor its golden assertion was changed. Full Frappe tests require the real Bench CI environment, including install/migrate twice. There is no site recalculation, merge or deployment in this work.

## 8. Reproduction and exact limits

```powershell
# Existing local interpreter; -E ignores host PYTHONHOME.
..\.venv-fragmentation\Scripts\python.exe -E -m pytest almdina_erp/tests/test_unified_final_placement.py almdina_erp/tests/test_final_placement_budget.py -q
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_unified_final_placement --baseline --projection --output before.json
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_unified_final_placement --projection --output after.json
# Omit --projection for full Domain replay; --gallery for five projections;
# --synthetic for the 1/2/8/17 dense witnesses.
```

Artifacts: `before/after-domain.json`, `before/after-projection.json`, `before/after-gallery.json`, `before/after-synthetic.json`; fixture source `almdina_erp/tests/fixtures/unified_placement`. All recorded stages, accepted priorities, physical goal margins and rejection reasons are reproducible.

Remaining limits: 64 pieces/sheet, 24 expensive trials/candidate, four bounded rounds; cooperative indivisible checks may overrun their slice; zero guaranteed coverage after real deadline exhaustion. Unsupported geometry remains conservative. Source capture contains final plans rather than native raw seed galleries, so this does not certify a full new 120 s production optimizer run, exact historical candidate timing, the deployed SHA, or machine execution. Saved Approved/Uploaded plans are untouched. No globally optimal placement, universal 17-board guarantee or universal speedup is claimed.
