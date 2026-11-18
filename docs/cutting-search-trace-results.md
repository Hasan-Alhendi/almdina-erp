# Cutting search trace — delivery evidence

Implementation: `197d3ff44d57f9ad6822937947bfbff4bb5e4cdf`; base Develop
`41d438001c5dfa9b146907c93d24b8490dd23150`.
Branch: `feature/cutting-search-trace-report`. Measurements recorded 2026-11-19
on Windows/Python 3.12.10. See [contract, schema and coverage matrix](cutting-search-trace.md).

## Executed verification

- **25 feature tests passed**: 23 collector/authorization/store tests and two real
  Chromium tests. Covers disabled deterministic results/input immutability,
  actual comparator keys, exceptions/generator scope, concurrent request isolation,
  partial inventory, quotas with reserved final gallery, cost exclusion, translation,
  XSS, offline navigation, contours/coordinate direction, prior rounds, default-off
  controls, lifecycle-disabled recording, permission revocation, repeated refresh,
  cross-order controls, matching preview identities, corrupt/expired artifacts and
  downloads after exact-token consumption.
- Broad related run: **343 passed, 178 subtests passed, 20 failed**. All 20 failed
  case IDs were replayed against the clean base worktree and all 20 failed there.
  Seventeen depend on the inherited DXF exporter defect; three concern existing
  malformed/duplicate Arabic catalog rows. No existing test was disabled or weakened.
- Follow-up after detailed Pattern instrumentation: **131 passed, 99 subtests
  passed, 3 inherited DXF failures** (Pattern/Corner strict roundtrips).
- Five Node suites passed: report API separation/URL encoding, preview ownership,
  gallery continuation/selection, exact-save phase locking and preview localization.
- `git diff --check` passed. Architecture, endpoint classification, permission
  matrix, preview exact-save/fingerprint, Kerf and mirroring guards were exercised
  in the related suites. Existing comparator outputs/geometry rules were retained.
- Offline visual audit of the actual regular/Glass/L exports at desktop and phone
  sizes: zero script errors. Glass holes and nonrectangular L material are visible;
  recorded sheet coordinates are not reflected vertically.

These are local results. They are not a claim that all repository CI gates or a
deployed Frappe integration passed. JUnit files remain with the local delivery;
the new report workflow runs the feature/contract checks and retains generated
HTML/JSON plus benchmarks as a GitHub Actions artifact.

## Reproduced inherited blockers

The base contains an empty `fetchValidatedPlan` in
`almdina_erp/public/js/door_cutting_order/cutting_plan/secure_dxf_export.js`.
The real export fixture fails at `fetchValidatedPlan(args).then(...)` before strict
import can run. The same source and failure exist in the clean base. This feature
does not repair or alter the separate exporter contract. Actual DXF/Strict Import
acceptance is therefore **not proved**, and production rollout remains gated.

The existing translation catalog has 15 invalid context columns, four malformed
rows and 12 duplicate keys in the base. The new rows are properly quoted, unique
and individually checked. An additional old configurable-permission suite also
reproduced its four obsolete-contract failures on the clean base. Unrelated
catalog/permission cleanup was not mixed into the observer change.

No isolated live Frappe site/DCO is connected here. Report-store and permission
tests use the real adapters with isolated Frappe facts/cache. The real Application
engine and preview-merge function produced the test artifacts. A live DCO
Preview → Selection → Exact Save → Reload → DXF run and deployed Redis TTL behavior
remain unverified. The report can never certify machine-ready NC or optimality.

## ON/OFF measurements

Twenty isolated worker processes: five inputs, two repetitions per ON/OFF state,
alternating the execution order. Identical input/settings/native budgets per case:
0.6 s native search, up to 0.6 s each ALNS/Pattern/Corner when applicable, 0.15 s
alignment per existing projection. These are configured search budgets, not an
end-to-end time cap. Geometry, validation/projection and reporting have additional
cost. No deadline was extended to compensate for observation.

Median values below. Search wall time includes collection but excludes report
serialization. Peak RSS is the entire worker process, including serialization
for ON. MiB is 2^20 bytes. Raw samples, paired geometry/rank equality and all
manifest hashes are in the linked JSON evidence.

| Input | OFF s | ON s | Peak RSS OFF / ON MiB | Export s | JSON / HTML MiB | Boards ON and OFF |
|---|---:|---:|---:|---:|---:|---:|
| regular | 2.090 | 1.516 | 37.8 / 63.3 | 0.279 | 1.93 / 1.97 | 1 |
| glass | 0.660 | 0.739 | 29.6 / 41.7 | 0.128 | 0.94 / 0.98 | 1 |
| L | 1.195 | 1.360 | 38.8 / 50.4 | 0.105 | 0.81 / 0.85 | 1 |
| clipped | 1.359 | 1.443 | 39.5 / 51.4 | 0.122 | 0.91 / 0.95 | 1 |
| reference-298 | 3.276 | 4.711 | 40.6 / 93.8 | 0.631 | 5.17 / 5.21 | 8 |

The regular OFF samples were 3.021 s and 1.159 s, showing substantial cold-process
and host variance; its lower ON median is not a speedup claim. Two repetitions
are illustrative, not a statistical performance guarantee. The reference case
shows about 44% extra search wall time and about 53 MiB extra peak RSS. The
feature remains opt-in and off by default.

The timed galleries were not identical in the ten paired comparisons. Board
counts stayed equal. Glass/L/Clipped winner industrial ranks matched in both
pairs; the regular first pair and both reference pairs differed. In reference
298 the largest eligible remnant was 2.02764 m² OFF versus 2.00812 m² ON, while
estimated cut count was 197 OFF versus 189 ON. Observation consumes real budget
and can reduce/exchange discoveries. This is disclosed, not presented as proof
of unchanged timed search quality. Deterministic untimed ON/OFF equality is tested;
the comparator and the final ordering policy themselves were not changed.

## Real artifacts and integrity

The local delivery contains ten ON reports (all five inputs, two repeats) and
three continuation reports. Every pair passed these checks:

- Canonical JSON hash equals `data_fingerprint`; HTML's embedded JSON equals the
  exported JSON exactly, including report ID and data fingerprint.
- Final ordered geometry identities equal the corresponding recorded preview
  gallery. Three real continuation rounds retain parent data and merge events.
- All 13 datasets use the implementation SHA above and the same source-file
  fingerprint. Every recorded source SHA-256 matches the delivered source.
- No observer errors, unexpected exception spans, unclosed spans, quota losses
  or omitted geometries occurred in these witnesses.
- Coverage is honestly **PARTIAL** in every report because coordinate probes and
  uninstrumented solver internals are outside V1 coverage. It is not advertised
  as exhaustive tracing of every internal state.

[Artifact IDs, hashes, counts and final galleries](evidence/cutting-search-trace/artifact-manifest.json)
and [benchmark samples/summary](evidence/cutting-search-trace/benchmark-summary.json)
are committed. Large HTML/JSON witnesses are delivered locally and reproduced by
the workflow rather than adding many megabytes to the source diff. No real
customer or production data was used or changed.

## Short usage

Grant `download_cutting_search_report` explicitly (Administrator follows existing
policy), open the normal System-plan edit/recalculate controls, check
**تسجيل تفاصيل البحث**, recalculate, then use **تحميل HTML** or **تحميل JSON**.
Continue Search adds a linked round accessible inside the report. Exact Save
retains the independently stored report for its 24-hour TTL. Download always
rechecks DCO read scope, System-plan access, capability, owner and site.

No merge or production deployment is authorized by this delivery.
