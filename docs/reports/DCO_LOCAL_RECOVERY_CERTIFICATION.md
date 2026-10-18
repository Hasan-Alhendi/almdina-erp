# DCO Local Recovery — Certification Report

**Assessment:** NOT CERTIFIED — PR must remain Draft; no merge or deployment.  
**Updated:** 2026-10-18  
**Repository / PR:** [Hasan-Alhendi/almdina-erp #532](https://github.com/Hasan-Alhendi/almdina-erp/pull/532)  
**Branch / observed HEAD:** `agent/dco-local-recovery-completion` / `13a3130c247341e2777d7534456d6b767c22b104`  
**Target / merge base:** `Develop` / `72037361b741a987db8eee48354a424610bfe525`  
**Required runtime:** Frappe `v16.17.5` (`75baafaa0bde07a86bf28764383b93b5df97bc7e`), ERPNext `v16.17.0` (`7b494dc9e8e47d288de5427bae25ce8a52c37d96`).  
**Scope:** ALMADINA-128, -129, -131 and -135 **Local**. ALMADINA-127 completed; -130 and -135 Final/Remote explicitly deferred.

## Evidence and status at this HEAD

At the time of this report update, the [current Frappe Integration run 39108775253](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39108775253) was **in progress**: 15 non-integration checks succeeded and 10 checks (nine integration matrix jobs and the pinned Desk runtime job) had not completed. They must be read again after this report-only commit, which will create a new HEAD and replace the relevant PR run. **No final-head pinned runtime PASS is claimed.**

On older tested HEAD `54e2480f4907a99da04699a2cd6e4d3df36807da`, [integration run 39067768721](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39067768721) yielded:

| Gate | Historical result | Latest-HEAD acceptance |
| --- | --- | --- |
| AL128 pinned real Desk | PASS | Reconfirmation pending |
| AL128 100-piece interactive performance | PASS as measurement (not a defined performance threshold) | Reconfirmation pending if relevant code changes |
| AL129 pinned MariaDB Native Save/token race | PASS | Reconfirmation pending |
| General rolling `full` | PASS | Final integrated run pending |
| `al129_customer` | FAIL: 3 cases | Not certified |
| `al129_new` | FAIL at Link/entry path | Not certified |
| `al131_edit` | FAIL at Recovery asset/form readiness | Not certified |
| `full_pinned` | FAIL: permission-type metadata test | Not certified |

The AL128 100-piece real Desk measurement used **40 samples for each Base/HEAD metric**, comparing against Develop `72037361` on the pinned runtime. Reported input-to-frame P95: Base **100.3 ms**, HEAD **104.4 ms**. Checkpoint acknowledgement P95: Base **474.2 ms**, HEAD **476.1 ms**. The test itself reported `NOT_ASSESSED_NO_ACCEPTANCE_THRESHOLD_DEFINED`: do not retrospectively invent a PASS threshold or claim a demonstrated speedup. Storage synthetic 200/500-piece stress and Chromium tests are distinct from this interactive measurement.

## Implementation and remaining proof

**Storage / AL128:** Reuses Frappe-compatible IndexedDB, atomic CAS, v1/v2 compatibility, quota/corruption handling and browser restart/isolation tests; no replacement storage stack. At prior HEADs, Chromium IndexedDB checks and pinned 100-piece benchmark passed. Full integrated evidence is still required.

**NEW / AL129:** Uses native Frappe Save, local CheckpointSession and a bound creation token. `NOT_FOUND` alone never releases a pending first-insert marker or authorizes a blind second INSERT. Earlier MariaDB race test passed. Customer, `default_edge_type`, live Awesomplete option selection, dynamic CREATE-only permissions and 100-piece lost-response/restore remain pinned Desk acceptance gates; their prior failing tests have targeted fixes under evaluation. Do not treat a cached search response as a successfully selected option.

**EDIT / AL131:** EDIT recovery application and UI logic have been selectively integrated with current Document Context/Edit Session and permission/version guards. Recovery must never auto-save or overwrite a later server version; permission, dispatch, row identity, rollback, Save/Cancel, two-tab CAS and A→B→A require real Desk proof. An earlier pinned job failed because the test used `window.AlmdinaDcoRecovery.LocalCheckpoint` before the DCO form assets were ready. Test readiness now checks the owning assets; a completed passing result is still required. The EDIT hydration implementation verifies server ownership at operation boundaries rather than per row, preserving post-await identity guards; network request count and 10/50/100-piece workloads must be checked in real Desk.

**Pinned Full:** `test_permission_type_sync_repairs_existing_custom_field_metadata` failed with `'eval:false' == 'eval:false'` on the prior pinned run. The permission-sync source and this test had identical Git blob hashes on Develop and the branch. A separate pinned Develop reproduction is configured; shared files alone do not prove a baseline failure. No skip, xfail or silent waiver is permitted.

**AL135 Local:** Remains blocked until the **same final HEAD** proves real NEW and EDIT flows; MariaDB token uniqueness; IndexedDB restart/offline/quota/corruption/CAS; 100-piece P50/P95 and 200/500 storage stress; server-side permissions/dispatch; extras/glass geometry and row identity; Arabic RTL; and Plan/Cost/Invoice/Production/DXF/OFFCUT plus merged cross-order PR #524/#531 non-regression.

## Jira and release controls

Latest issue status verified via the connected Jira account: **127 Done; 128 Ready for Review; 129 In Progress; 131 In Progress; 135 To Do**. No story will be marked Done solely due to a report, historical CI or a passing mock.

**Decision: BLOCKED / Draft.** Update this file with the *final* actual run links, complete pinned NEW/EDIT results, security and full-CI evidence, then change the PR to Ready for Review only when all Local gates truly pass. No merge to Develop and no server deployment. This report is a present-state evidence record, not certification.
