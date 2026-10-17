# DCO Local Recovery — Integration and Release Gate

**Decision: BLOCKED (not production-certified)**  
**Date reviewed:** 2026-10-17  
**Integration baseline:** `Develop` @ `72037361b741a987db8eee48354a424610bfe525`  
**Working branch:** `agent/dco-local-recovery-completion`  
**Scope:** ALMADINA-127 → 128 → 129 → 131 → 135 **Local only**.  
**Not in scope:** ALMADINA-130, Remote/Final 135, and new 132–134 feature behavior.  
**Acceptance versions:** Frappe `v16.17.5`, ERPNext `v16.17.0`.

This file is a **checkpoint assessment**, not a PASS certificate. Its creation does not alter Recovery runtime behavior, approve release, or advance Jira issue statuses.

## Continuation — verified 2026-10-17

- Jira direct issue access now works. ALMADINA-127 Architecture Gate was approved (Done); ALMADINA-128 remains Ready for Review, with 129/131/135 To Do. Historical Jira 403 text below is superseded.
- PR #532 at previous head 0bcee7e passed 15/15 workflows, including [integration run 39057418235](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39057418235): 1,567 + 81 tests and the new ownership test. These tests used moving Frappe 16.52.0/ERPNext 16.51.1, NOT the pinned acceptance runtime.
- The AL128 actual Frappe Desk performance workload has been corrected from 200/500 to 100 pieces per Jira acceptance; Base-versus-HEAD P50/P95 input-to-frame and IndexedDB checkpoint acknowledgement remain separately measured. Synthetic 200/500 storage tests remain unchanged.
- Existing Frappe v16 Integration workflow was extended on PR #532 to run the 100-piece benchmark pinned to Frappe v16.17.5 (75baafaa) and ERPNext v16.17.0 (7b494dc9). No production change.
- [First pinned run 39062569533](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/39062569533) installed/verified both pinned runtimes, but failed during isolated fixture seeding: Row 9 Liner lacked reference side and width. A targeted test fixture correction was committed as 763333785c5e4071bf107dc47d3eacf1ee1f54c0; succeeding runs must be examined before any PASS.
- Pinned NEW Desk run 38998378203 retains two unresolved Frappe Link test failures. EDIT integration has not yet been ported into current Develop; ALMADINA-135 Local Gate therefore cannot pass.
- The ownership drift Python test ran and passed in Static Checks. Historical pending-test statements later in this report were superseded by this run.

**Release decision: BLOCKED — no merge or deployment.**
## Continued implementation checkpoint — 2026-10-17

- ALMADINA-127 remains Done. 129 and 131 were transitioned to In Progress with linked implementation notes. 128 remains Ready for Review; 135 Local is NOT certified.
- All changes are on the same branch and Draft PR #532; `Develop` baseline remains `72037361...`, no merge or deployment.
- CI: replaced branch-name special casing with a maintainable integration matrix: moving `full`; pinned `full_pinned`, `al128_desk`, `al128_performance`, `al129_customer`, `al129_new`, `al129_backend`, `al131_edit`. Browser and MariaDB evidence are uploaded separately. Ref hash verification is retained. A queued job does not count as passing.
- AL128: baseline comparison changed to latest Develop; identical recovery assets no longer cause metadata handler exceptions or false claimed performance improvements. Real 100-piece input-to-frame and IndexedDB acknowledgement P50/P95 remain mandatory. The legacy `تعديل` label selector was updated to the stable PageEditAction component selector after pinned Desk logs showed the visible Edit control was not located.
- AL129: imported real pinned Customer/Awesomplete and multiple-NEW-draft/lost-response/100-piece tests from PR #505; added two-connection MariaDB unique-token race and six native reconciliation checks. Fixed unsafe production logic that previously cleared the pending creation marker on `NOT_FOUND`, which can occur while an earlier INSERT is still in flight. A `NOT_FOUND` now retains `PENDING_RECONCILIATION`, shows a translated warning and prevents another INSERT; discovery stays open and disallows resuming that card without definitive proof.
- AL131: integrated EDIT application, discovery, explicit confirmation, dynamic permission checks, server version conflict, safe row-hydration and rollback with modern Document Context/P0 async fences; ported application/UI tests and old real pinned EDIT Desk fixture/runner. Modern presentation, locale abstraction and error chrome retained; 31 translations added. These are code changes pending real acceptance on the new HEAD, not certified behavior.
- At head `6afb1855`, the static-validation, frontend DCO, browser IndexedDB and the other 12 non-integration checks had succeeded after resolving hardcoded Arabic and missing fallback. On earlier run `39064086399`, generic `integration/full` passed on moving version-16, but AL128 pinned Desk/benchmark failed at an obsolete Arabic Edit selector; not proof of production defect. Later AL128 runs on older heads re-confirmed the same selector failure.
- Latest head at this entry: `dfeadeca14d2a3104ffa4aa638d5061d21777a0a`. GitHub Actions runs for many recent heads are queued/backlogged. The final pinned NEW/EDIT, MariaDB race, 100-piece comparative numbers, and 135 Local Gate remain **NOT CERTIFIED** until their actual logs pass.
- Acceptance decision: **BLOCKED / Draft**. No automatic merge or production deployment.
## Executive summary and baseline

The existing local Recovery implementation is to be extended rather than rebuilt. `Develop` already contains `RecoveryProjection`, `CheckpointSession`, IndexedDB gateway, local draft/asset repositories, NEW Recovery presentation, and NEW server insert reconciliation. The checked baseline also contains P0 cross-order isolation from merged PRs [#524](https://github.com/Hasan-Alhendi/almdina-erp/pull/524) and [#531](https://github.com/Hasan-Alhendi/almdina-erp/pull/531). Old recovery branch ancestry is not suitable for wholesale merge.

Jira reads were attempted but returned **403 — app not installed on this instance**. Consequently, Jira descriptions, current acceptance criteria, comments, and statuses have not been independently certified and no Jira changes are claimed.

## Story / gate matrix

| Story | Confirmed evidence | Decision at this checkpoint |
| --- | --- | --- |
| 127 Ownership/Lifecycle | `docs/reference/16_DCO_RECOVERY_STATE_OWNERSHIP.md` and tests exist on current Develop; historical [#501](https://github.com/Hasan-Alhendi/almdina-erp/pull/501) closed unmerged. This branch adds a schema-to-projection ownership drift test. | **BLOCKED** until runtime/lifecycle gates and Jira criteria are verified |
| 128 IndexedDB | [#504](https://github.com/Hasan-Alhendi/almdina-erp/pull/504) was merged. Its description reports Chromium/IndexedDB tests but does not certify this integrated HEAD's pinned real Desk/storage-performance gate. | **BLOCKED** on integrated acceptance |
| 129 NEW | NEW runtime and first-creation token reconciliation exist in current Develop. Historical [#505](https://github.com/Hasan-Alhendi/almdina-erp/pull/505) is open, unmerged. Pinned Desk [run 38998378203](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38998378203) failed: **17 passed, 2 failed**. | **BLOCKED** |
| 131 EDIT | Historical [#495](https://github.com/Hasan-Alhendi/almdina-erp/pull/495) and [#499](https://github.com/Hasan-Alhendi/almdina-erp/pull/499) remain open, unmerged. An old pinned Desk [run 38161956364](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38161956364) succeeded, but EDIT application and UI integration are absent from current Develop. | **NOT integrated; BLOCKED** |
| 135 Local | Cannot be accepted before certified NEW, EDIT, storage durability, full cross-order regression, and interactive performance evidence. | **BLOCKED**; Remote/Final gate explicitly excluded |

## Verified implementation: ownership drift test

`almdina_erp/tests/test_dco_local_recovery_architecture.py` now includes
`test_all_editable_dco_fields_have_explicit_recovery_ownership`.

It compares the **actual live DocType schema** to `RecoveryProjection.HEADER_FIELDS` and `PIECE_FIELDS`. It fails if a new editable header or piece input lacks an explicit Recovery ownership decision, a retired input remains in the projection, a field is duplicated, or a captured field gains `read_only` or nonzero `permlevel`.

At this checkpoint a direct schema/projection comparison of the exact GitHub files found:

- **9** captured header fields, **42** captured piece fields;
- no missing or stale field names, duplicate allowlist entries, or protected allowlist fields;
- four intentionally excluded editable header fields: Frappe `naming_series`, technical `board_item`, and separately owned Cost inputs `board_rate_usd` and `cutting_cost_per_board_usd`.

This is a **static schema comparison**, not a passing Python test execution or Frappe Desk certificate.

### Field ownership

The DCO allowlist covers Customer/order date/notes, cutting machine, board dimensions/description, default edge and color, dimensions, quantity, piece kind, rotation, per-side edging and overrides, notes, clipped corners/glass margin, liner, back groove, recessed handle, both double variants, and special-shape drawing/geometry inputs. Official DCO/Frappe remains the owner of saved data. Plan, Cost, Invoice, price/permlevel fields, production state and derived manufacturing quantities remain outside this DCO input projection.

## Detailed NEW acceptance failure

The **pinned** Frappe/ERPNext `v16.17.5/v16.17.0` [CI run 38998378203](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38998378203) logged two distinct failures:

1. `test_real_desk_customer_native_entry_and_permission_differential`: a Playwright `wait_for_function` timed out inside `_set_link` for **`default_edge_type`** during `_fill_header`. This alone does **not** prove a production permission fault.
2. `test_real_desk_customer_control_link_autocomplete_isolated`: a UI assertion on `sourceExactValueCount == 1` failed. Network search, request arguments, and typed-cache assertions had passed. A successful API response is **not sufficient** to assert the Frappe Link dropdown behavior is correct.

Before modifying production code or selectors: reproduce against the same Develop base, inspect actual Frappe ControlLink/Awesomplete DOM and lifecycle, compare the failure to the baseline, and preserve end-to-end Customer selection and Save assertions. Never skip or dilute the tests merely to obtain green CI.

## EDIT integration risk

Older EDIT branches differ from current Develop and add a substantial UI lifecycle implementation (`door_cutting_order_edit_recovery.js` plus discovery, conflict, rollback, and save hooks). Current Develop has subsequently changed cross-order async ownership, translation handling and recovery status lifecycle. An unconditional checkout/merge of that old presentation file would risk reintroducing stale callbacks and misrouted A→B→A updates.

Integrate the EDIT application through current `AlmdinaDocumentContext`, edit-session, native Save/Cancel and permission owners, preserving `session_origin_modified` and acknowledged-only `expected_server_modified`. Test rollback, updated-server conflict, multi-tab interaction, production dispatch restrictions and delayed async events **on the new integrated HEAD**.

## Test and performance evidence

| Requirement | Evidence currently available | Integrated gate |
| --- | --- | --- |
| Static field ownership | Compared exact Develop schema and allowlist (9 headers, 42 pieces), no drift | Static comparison checked; new Python test execution pending |
| Real Chromium / IndexedDB | Historical #504 suite only | Pending on new HEAD |
| NEW real pinned Frappe Desk | 17 passed, 2 failed, run 38998378203 | Fail |
| EDIT real pinned Frappe Desk | Historical old-branch run 38161956364 passed | Not evidence for current HEAD |
| Interactive 100-piece performance and P50/P95 | No comparable base-versus-HEAD numbers established | Pending |
| 200/500-piece storage stress | Historic tests exist | Pending on new HEAD |
| Concurrent token inserts and lost responses | Test implementations exist, not fully certified on this HEAD | Pending |
| Full integration / cross-order / Plan / Cost / DXF / OFFCUT regression | Latest Develop contains merged P0 work; no combined Recovery certification run | Pending |

No local Bench or Chromium run was performed as part of this repository audit; no numerical runtime/performance conclusion is inferred.

## Security, compatibility, and limits

No production code or schema was changed in this checkpoint commit. Recovery data remains local to the browser profile; a user with full access to the same browser profile or a cleared browser storage area is outside the durable security/loss guarantee. User/site namespace keys are not encryption. Authentication, dynamic server authorization, version conflict prevention, explicit user restore choice, and no silent official Save are required gates.

## Required continuation before PASS

1. Run the updated ownership test in CI with base differential; close actual 127 issues without duplicating its owners.
2. Re-certify IndexedDB v1/v2, CAS, corruption/quota/aborted transactions, browser restart and 100-piece interactive performance on pinned Desk.
3. Repair and rerun the two NEW Desk failures **from evidence**; prove one order per creation token under actual concurrent DB transactions and safe unknown HTTP result.
4. Port EDIT **selectively** from historical branches, preserving newest Develop's lifecycle/cross-order fences. Re-run the real pinned EDIT suite on the integrated branch.
5. Execute complete ALMADINA-135 **Local only** matrix with real version pinning, browser/Desk failures, base-vs-HEAD P50/P95, no duplicate DCO, no silent overwrite, and all regression checks.
6. Reconcile with latest Develop, update Jira only after access and evidence, and mark PR Ready for Review only after all mandatory gates are genuinely green.

**Release decision: BLOCKED. Do not merge/deploy as certified Local Recovery.**
