# DCO Local Recovery — Certification Report

**Decision: BLOCKED.** Keep PR Draft; no merge or deployment. Updated 2026-10-19.

- Repository / PR: [Hasan-Alhendi/almdina-erp #532](https://github.com/Hasan-Alhendi/almdina-erp/pull/532).
- Branch: `agent/dco-local-recovery-completion`; target: `Develop`.
- Integrated Develop / merge-base: `672384921f55132b51081d51a7f96e0d2c159928`.
- Previous remote candidate: `90ac5096fe880ce1c9200f7df89b67e78eb0b626`; integration commit: `0976e0fd8b59d893dd5c37fad92c6f9b658a158b`.
- Candidate identity: the commit containing this report. Each integration job must archive `application-source-refs-<suite>` with the exact expected, checked-out and installed application SHA. A later commit requires new acceptance evidence.
- Required runtime: Frappe `v16.17.5` (`75baafaa0bde07a86bf28764383b93b5df97bc7e`), ERPNext `v16.17.0` (`7b494dc9e8e47d288de5427bae25ce8a52c37d96`), MariaDB 11.8; real Chromium.

## Root causes and corrections

1. **Unfinished EDIT hydration could overwrite its own recovery source.** Native `pieces_add`/`pieces_remove` callbacks advanced the checkpoint revision during partial hydration. The regression reproduced revision 3 becoming 5 before final authorization. Reuse the existing `editRestoreInProgress` guard in mutation capture and flush entry points; checkpoint the complete projection only after successful final verification. Failed restoration rolls back child additions/deletions/order and preserves the exact acknowledged source record. The guard carries its original DocumentContext visit: reusing the same Form for B does not suppress B checkpoints, and stale A completion cannot release a newer B restore guard.
2. **Native Save could run during that unfinished hydration.** A paused-restore regression proved `before_save` left validation enabled. The existing restoration guard now rejects that originating Save, uses an existing localized notice, and permits normal explicit Save after completion. A departed form never changes the replacement form's global validation flag.
3. **Runtime provenance was incomplete.** PR integration previously installed GitHub's synthetic merge commit and recorded only framework SHAs. Acceptance now installs/verifies the exact PR HEAD; baseline uses the immutable base SHA. Source provenance is archived per suite.
4. **Test assumptions drifted.** Arabic EDIT harness now loads its real catalog entry; print-source assertions check selected geometry after the approved removal of plan IDs from headers; Link browser test supports configured/system/bundled Chromium. No business changes were made to satisfy these tests.
5. **Pinned Permission Type baseline debt.** Existing repair updates only generated visibility metadata to Frappe's native expressions. Stronger integration coverage corrupts all three targets, checks exact repair, unchanged capability grants, and a second idempotent synchronization. Real pinned execution remains required.

Existing NEW token uniqueness/reconciliation, local atomic IndexedDB/CAS/hash/schema handling, DocumentContext identity, Edit Session ownership and Frappe persistence remain in place. `NOT_FOUND` does not authorize retry of an uncertain INSERT; contradictory reference wording was corrected. No new state framework, server draft DocType or remote recovery was introduced.

## Ownership and evidence gaps

| Owner | Implementation / remaining acceptance |
| --- | --- |
| DocumentContext / Edit Session | Existing identity/generation and edit-state owners retained; real navigation/late-response gates required. |
| Projection / CheckpointSession | Metadata allowlist test passes; no financial/Plan/Cost results added; unfinished EDIT writes now guarded. |
| IndexedDB / local repositories | Existing transactional CAS/hash/schema and Blob seam retained; current app assets remain private File references. |
| Frappe / MariaDB | Native explicit Save, current permissions/lifecycle and optimistic concurrency remain authoritative. |
| EDIT presentation | Extended actual Desk scenarios added; syntax/unit success is not runtime certification. |

New actual Desk coverage exercises refresh, offline checkpoint, tab reopen, full browser restart with a persistent profile, child identity/add/delete/reorder, edges/extras, external version conflict, server edit between restore and Save, pre-plan acknowledged/unacknowledged versions, two-tab CAS, real delayed requests, Back/Forward, dynamic permission revoke, dispatch, reassignment, explicit Return to Draft and Save/Cancel. Individual completed scenarios write `edit-scenario-results.json`; completion is emitted only after every scenario passes. No fabricated API response is used by these scenarios.

## Latest integrated runtime evidence

[Run 39242239422](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39242239422) tested exact HEAD `f6ee3580120bec7c314446e13c52cd88c83bf7cc`: **PASS** for `full_pinned`, `full_pinned_base_permission` (independent negative baseline diagnostic), `al128_desk`, `al129_new`, `al129_customer`, `al129_backend`; **FAIL** for rolling `full`, `al128_performance`, and `al131_edit`. All application-source artifacts confirm the expected SHA and pinned framework sources. These results are evidence for that commit, not acceptance of later fixes.

- EDIT screenshot proves the version conflict retained the draft and refused hydration; the test expected Arabic while its user session was English. Isolated EDIT users now explicitly use Arabic, and the scenario asserts the real acceptance locale.
- Rolling Frappe now upserts generated Custom Fields on every native `create_custom_field`, changing timestamps on repeated sync. The repair now creates only missing fields and repairs existing metadata without repeated native upsert; grant/idempotency assertions remain unchanged.
- The performance observer now joins actual committed writes by exact draft/revision, and registers completion observation before the gateway acknowledgement. A local real Chromium probe observed all 40 acknowledged writes. No storage result or missing sample is fabricated.
- Cross-order runtime run [39242239408](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39242239408) failed cold-start global readiness and obsolete print-plan-ID assertions. Readiness now guards `window.frappe`; print acceptance verifies source plan/revision, order, board, sheet count and geometry, preserving the approved omission of technical IDs/OFFCUT business routing from printed output. The runtime workflow now checks exact application HEAD.
- Its EDIT diagnostic also exposed a real jqXHR `.finally` failure in the production revert-target loader. A regression reproduced the exact error; the existing owner now normalizes the transport with `Promise.resolve`, preserving its identity and cleanup fences.

A new final integrated run is mandatory after these corrections.

## Earlier evidence

Latest historical integration [39216134747](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39216134747), ancestor `611004ab`, is **not** final-head acceptance:

| Suite | Historical result | Current candidate |
| --- | --- | --- |
| `full`, `al128_desk`, `al128_performance` | PASS | Pending integrated rerun |
| `al129_customer`, `al129_new`, `al129_backend` | PASS | Pending integrated rerun |
| `al131_edit` | FAIL: retained hidden Continue after Return to Draft | Pending integrated rerun with extended matrix |
| `full_pinned` | FAIL: Permission Type `eval:false` metadata | Pending repair verification |
| `full_pinned_base_permission` | Reproduced same defect on baseline | Diagnostic only; never substitutes for pinned acceptance |

Local verification on the integrated working tree:

- Python module lists from all required non-integration workflows: 1,042 tests, success, one pre-existing Frappe-runtime-only skip. That controller check must execute in installed integration; no new skip/xfail added.
- Registered Static frontend simulations: 67/67 PASS, including the newly registered EDIT application/UI regressions.
- Security/architecture/production/endpoint/documentation selection: 51/51 PASS.
- Actual Link browser helper suite: 17/17 PASS with Chromium 140.0.7339.16 / Playwright 1.55.0.
- Full unregistered JS inventory initially found five Develop failures. Four remain outside this release's registered gates: `dco_sticky_tabs_geometry` (missing translator in harness), `measurement_toolbar_shared_loop` (observer-frame assertion), `order_entry_locale` (obsolete translation assertion), `plan_tab_capabilities` (retired path). All reproduced on exact Develop `67238492`; they are not claimed fixed. The registered print-source regression was repaired and passes against both trees.
- Real Chromium IndexedDB: 7/7 PASS with Chromium 140.0.7339.16 / Playwright 1.55.0. Native quota failure retains acknowledged revision 1 when revision 2 fails; 200/500-piece payloads are 479,745 / 1,449,645 bytes (7 writes each, local P95 12.4 / 30.3 ms). These local storage figures are not Desk performance acceptance. The pagehide test now waits for actual durable acknowledgment before reading; it does not substitute another flush or a sleep.
- Actual Desk/MariaDB acceptance on this candidate: **PENDING**. No local Bench or MariaDB is available; use the existing isolated integration workflow.

Historical 100-piece measurements on `54e2480` (40 samples per metric): input P95 100.3→104.4 ms, checkpoint P95 474.2→476.1 ms (baseline→candidate). These are historical context, not current performance acceptance. Final report must include fresh Base/HEAD P50/P95, browser details, sample counts, serialization/write cost and an honest comparison; no invented absolute threshold or speedup claim.

## Jira and release controls

Verified Jira: 126 To Do (Epic), 127 Done, 128 READY FOR REVIEW, 129 In Progress, 130 To Do/deferred, 131 In Progress, 135 To Do. AL135 Local Gate remains BLOCKED pending the final integrated evidence; its Remote/Final Gate is a separate future workstream. Do not close stories merely because tests were added.

Retention: no automatic age-based deletion or destructive schema cleanup was added. Start New retains older drafts; explicit deletion and confirmed official-success cleanup remain revision/attempt fenced. Pending-unknown or conflicting drafts remain retained. Browser storage can be cleared/evicted; namespaces are not encryption or a complete shared-device security boundary. Private uploaded references require server access; transient Blob/Data URLs are not claimed durable app assets. Full offline application startup and remote/cross-device recovery are excluded.

Rollback: do not delete IndexedDB records or roll back token uniqueness. Disable/revert presentation corrections only after reviewing their safety regressions. No schema change, role grant, direct Develop commit or server deployment is part of this continuation.
