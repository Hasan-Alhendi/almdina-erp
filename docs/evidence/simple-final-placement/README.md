# Simple final sheet positioning — acceptance evidence

Base: `2367b8ff5cefe8186df450b218d5b53495259980` (`Develop`). Branch: `feature/simple-final-placement`. Draft only.

## Change contract

New System calculations position only the selected final gallery, after compaction/alignment and before independent final validation/snapshot. Each sheet is one rigid body. The pure axis rule freezes eligibility from the original final geometry; protection includes mandatory trim exactly once. Rejected centering retains a safe center on the other axis where possible, then uses prescribed protection endpoints or a safe axis alone. There is no positioning deadline, group discovery, search sweep, trial budget, new setting beyond H/V protection, or dependency.

Packing, ALNS, Pattern, Corner Search and final alignment sources/budgets are unchanged. `optimizer.py` only exposes its existing remnant eligibility predicate for reuse. Historical trim helpers remain unchanged. Factory fields default to zero, keep the existing cutting-settings capability, validate finite non-negative values, and invalidate stale Preview sessions. Manufacturing fingerprint V1–V4 definitions are unchanged; final geometry is projected before preview fingerprints/candidate IDs. Exact selected snapshot/seed pairs are retained, with unchanged raw continuation seeds.

Operational diff: **16 files, +384/-87 lines** (including schema/settings/wiring, machining export metadata and Arabic CSV fixes); the positioning module is **191 lines**. Runtime digest of the four geometry/application files above on this Windows checkout: `f25c7b2598915ead0b71a1be5efda27a6915ce315aa4e163cfc34bee82c8691f`.

## Native engine acceptance

Actual `DomainCuttingEngineAdapter` from dimension/quantity inputs, with no search replacement. Native search allowance 120 s; existing alignment allowance 30 s; existing ALNS/Pattern/Corner allowances 10 s each. Kerf 5 mm, trim 0, center threshold 70 mm, H/V protection 15/20 mm. Baseline loads the exact Develop Application Git object and uses the identical native search; current Domain differences on that path are the equivalent remnant-helper extraction and a default-preserving cutter-quality option. The final candidate run uses the frozen runtime digest above. Sequential observations on Windows/Python 3.12; ordinary desktop load remains, so these are observations, not speed guarantees or CNC timings.

| Order | Pieces | Boards before → after | Selected gallery coverage | Total seconds before → after | Positioning sum over gallery, s | Strict DXF |
|---|---:|---|---|---|---:|---|
| 26-00331 | 12 | 2 → 2 | 2/2/2/2/2 | 8.917 → 10.177 | 0.216 | Passed |
| 26-00344 | 76 | 8 → 8 | 8/8/8/8/8 | 60.073 → 61.292 | 1.834 | Passed |
| 26-00345 | 115 | 17 → 17 | 17/17/17/17/17 | 83.504 → 91.768 | 1.314 | Passed |
| 26-00346 | 21 | 2 → 2 | 2/2/2/2/2 | 16.645 → 15.009 | 0.295 | Passed |
| 26-00347 | 5 | 1 → 1 | 1/1/1/1/1 | 2.328 → 1.570 | 0.041 | Passed |

Every native finalist retains its exact board count, piece identities/dimensions/orientation, one common offset and mandatory trim. Full geometry/permissions validation passes. Snapshot JSON → persisted child reconstruction → actual Board Editor projection → actual JavaScript DXF → AutoCAD normalization → Strict Re-import preserves coordinates and identities. Machining metadata is compared by sheet and physical identity; emitted CUT_PATH agrees with the complete System cutter network within 0.05 mm.

All 17 sheets in **each** of the five 26-00345 finalists are processed: **85/85**, independently of alignment budget. All 150 sheet/finalist opportunities across the five orders are processed. The stage accepts the first prescribed endpoint on these native/captured orders: no industrial movement is rejected. Rejection/fallback behavior is separately exercised by regressions for geometry, qualified remnants, unsupported attachments/machines, and mixed center/protection axes.

Whole-run timing can change because the requested removal of early row centering exposes different geometry to existing compaction/alignment/refinement. The final stage preserves each entering cutter network; the following native gallery comparison also reports whole-pipeline differences rather than claiming identical legacy geometry.

| Order | Actual total cutter mm, Develop → new | Largest qualified remnant m², Develop → new |
|---|---|---|
| 26-00331 | 22395.000 → 22395.000 | 1.430182 → 1.387621 |
| 26-00344 | 114321.500 → 114231.000 | 0.740421 → 0.727956 |
| 26-00345 | 232469.500 → 232553.000 | 1.723860 → 1.701900 |
| 26-00346 | 32928.871 → 32928.871 | 0.658956 → 0.646536 |
| 26-00347 | 9060.000 → 9166.000 | 1.328082 → 1.312425 |

## Every board in the selected native plans

Margins are physical **left/right; top/bottom mm**. Deltas apply to all pieces on that board. No row/group moves independently. Every row below is accepted; zero on one axis is a policy no-op.

| Order | Board | dx / dy mm | Before L/R; T/B | After L/R; T/B |
|---|---:|---|---|---|
| 26-00331 | 2 | 15.5 / -20 | 0/31; 92/0 | 15.5/15.5; 72/20 |
| 26-00331 | 1 | 15.5 / -16 | 0/31; 32/0 | 15.5/15.5; 16/16 |
| 26-00344 | 8 | 15 / 0 | 0/91; 0/0 | 15/76; 0/0 |
| 26-00344 | 7 | 15 / 0 | 0/223; 0/0 | 15/208; 0/0 |
| 26-00344 | 6 | 15 / -2 | 0/193; 4/0 | 15/178; 2/2 |
| 26-00344 | 5 | 15 / -2.5 | 0/174; 5/0 | 15/159; 2.5/2.5 |
| 26-00344 | 4 | 15 / -35 | 0/133; 70/0 | 15/118; 35/35 |
| 26-00344 | 3 | 2.5 / -18 | 0/5; 36/0 | 2.5/2.5; 18/18 |
| 26-00344 | 2 | 14 / -20 | 0/28; 72/0 | 14/14; 52/20 |
| 26-00344 | 1 | 12.5 / -34 | 0/25; 68/0 | 12.5/12.5; 34/34 |
| 26-00345 | 1 | 4.5 / -20 | 0/9; 81/0 | 4.5/4.5; 61/20 |
| 26-00345 | 2 | 4.5 / -20 | 0/9; 81/0 | 4.5/4.5; 61/20 |
| 26-00345 | 3 | 4.5 / -7.5 | 0/9; 15/0 | 4.5/4.5; 7.5/7.5 |
| 26-00345 | 4 | 4.5 / -20 | 0/9; 235/0 | 4.5/4.5; 215/20 |
| 26-00345 | 5 | 4.5 / -20 | 0/9; 235/0 | 4.5/4.5; 215/20 |
| 26-00345 | 6 | 4.5 / -20 | 0/9; 235/0 | 4.5/4.5; 215/20 |
| 26-00345 | 7 | 4.5 / -20 | 0/9; 235/0 | 4.5/4.5; 215/20 |
| 26-00345 | 8 | 4.5 / -20 | 0/9; 235/0 | 4.5/4.5; 215/20 |
| 26-00345 | 9 | 17.5 / -23 | 0/35; 46/0 | 17.5/17.5; 23/23 |
| 26-00345 | 10 | 15 / -10.5 | 0/119; 21/0 | 15/104; 10.5/10.5 |
| 26-00345 | 11 | 15 / -10.5 | 0/119; 21/0 | 15/104; 10.5/10.5 |
| 26-00345 | 12 | 16 / -4.5 | 0/32; 9/0 | 16/16; 4.5/4.5 |
| 26-00345 | 13 | 4.5 / -20 | 0/9; 77/0 | 4.5/4.5; 57/20 |
| 26-00345 | 14 | 4.5 / -20 | 0/9; 79/0 | 4.5/4.5; 59/20 |
| 26-00345 | 15 | 4.5 / -7.5 | 0/9; 15/0 | 4.5/4.5; 7.5/7.5 |
| 26-00345 | 16 | 11 / -4 | 0/22; 8/0 | 11/11; 4/4 |
| 26-00345 | 17 | 4.5 / 20 | 0/9; 0/1415 | 4.5/4.5; 20/1395 |
| 26-00346 | 2 | 6 / -9.5 | 0/12; 19/0 | 6/6; 9.5/9.5 |
| 26-00346 | 1 | 2.5 / -5.5 | 0/5; 11/0 | 2.5/2.5; 5.5/5.5 |
| 26-00347 | 1 | 8.5 / 0 | 0/17; 0/0 | 8.5/8.5; 0/0 |

## Captured geometry and safety limits

The reference fixtures are anonymized read-only captures, not native search mocks. Their entry positions reverse recorded late shifts only; they cannot recover older early centering. The JSON also records **every board of these captured plans**, all five native finalists, physical margins, exact deltas, actual cutter profiles, diagnostics and final selected snapshots. Captured 26-00345 processes all 17 sheets and preserves the 35 mm horizontal-slack example at 17.5/17.5. The 0/9, 0/29, 0/30, 0/35, 0/70, 0/73, 0/119, 20/235, 60/60 and vertical/trim boundaries all have explicit tests.

Qualified remnants retain one connected factory-qualified successor per original qualified rectangle. Only the necessary displacement strips may be lost; fragmented or sub-threshold successors reject movement. This uses the existing rectangular remnant/separability contract, not remnant inventory behavior. Special exact local polygons, Glass/hosts, L/clipped shapes and local machining definitions retain their relative geometry. Absolute editor frames, explicit blank reservation rings, unsupported attached paths, OFFCUT and Panel Saw stay unmoved with a diagnostic reason. The manufacturing export projection now uses the existing common machining reader so Handle Recess/Rear Groove fields survive child reconstruction.

No saved/Approved/Uploaded plan is automatically repositioned. Preview commit saves the exact trusted snapshot; merging prior candidates does not rerun positioning (including the non-fixed-point 0/73 → 15/58 case). Positive trim and zero/positive protection pass actual persistence/Board Editor/DXF round trips. Native inputs exercise the real optimizer; catalog DB access alone is supplied by isolated edge-profile fixtures. These checks do not certify NC, clamping, feeds/depths, deployment, or production-machine execution.

## Validation and inherited failures

Final focused run: **170 passed, 151 subtests**; the additional exact-Special polygon regression passes. Previous alignment/ALNS/Pattern/Corner/trim/lifecycle run: **172 passed**. The full independent local run reached 342 passes and two failures: the inherited five-second trim=0.1 case, and a DXF-test sorting artifact where float tails reordered equal-X pieces. The latter now sorts at 1e-6 cm precision, well below its unchanged 1e-4 cm assertion tolerance; the actual native export/import regression passes. Full independent job results and exact-head CI audit are recorded in the Draft PR. Settings/gallery/Board Editor JavaScript contracts pass. No validator or golden schema assertion was weakened.

The new mixed-axis fallback regression first fails with 1.5/1.5 instead of 1.75/1.5, then passes after preserving the safe horizontal center. Application projection probes now count candidate preparation separately from selected final positioning; their fallback/validation assertions remain intact.

Develop has independently reproduced failures: V3 schema golden digest, 16 nested `pytest.approx` corner-test errors on this local Pytest, and the 243-case trim=0.1 test returning four boards under its five-second allowance on Windows. The Arabic catalog previously had three failing gates and caused the real Frappe parser to abort. CSV quoting and duplicate-key removal now preserve effective translations and pass those gates; the two new labels also have real Frappe parser/integration coverage. Baseline Frappe CI: [run 44525581405](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/44525581405) (install and migrate twice passed; 11 general failures/one error and one real-site translation error). Other inherited gates remain visible; this draft is not represented as merge-ready.

## Reproduce

```powershell
..\.venv-fragmentation\Scripts\python.exe -E -m pytest almdina_erp/tests/test_simple_final_placement.py almdina_erp/tests/test_simple_placement_settings.py -q
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_simple_final_placement --baseline --seconds 120 --output docs/evidence/simple-final-placement/baseline-native.json
..\.venv-fragmentation\Scripts\python.exe -E -m almdina_erp.tests.bench_simple_final_placement --seconds 120 --output docs/evidence/simple-final-placement/candidate-native.json
```

Artifacts: [baseline-native.json](baseline-native.json), [candidate-native.json](candidate-native.json). No merge, deployment, or change to the reference branch.
