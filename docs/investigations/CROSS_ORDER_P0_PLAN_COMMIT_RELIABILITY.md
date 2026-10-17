# P0 Plan preview commit receipt — incremental release gate

## Change contract

- Base: frozen cumulative candidate `2852c8a1be2d1275edc1de77e66ae12d50e5ab97` (#518); Develop `909fab12f9d17b0650a8b99c77db1710ff90fb2a`.
- Scope: Plan Preview's response-to-UI success boundary, read-only reconciliation of an absent response, original Desk Save network/DB evidence, and Arabic copy. No Recovery, optimizer, DXF, schema, authorization or print changes.
- Invariants: one-use preview token; source Plan/order/revision/document generation; server capabilities and stage checks; same-document edit draft; no A completion on B; no replay of uncertain commit.
- Rollback: revert this isolated increment and rebuild assets. No data migration.

## Historical observation versus proven defect

Run [38970724424](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38970724424) ended after a ready Preview for order `26-00003`, source `CP-2026-00001` revision 1 and requested Kerf 4. The coordinator was idle while the displayed canonical row and form still had Kerf 3. The old Artifact did not capture whether the commit HTTP request happened or what it returned. Its intermittent cause is **not proven** to be a null reply, Recovery, or a server rejection. Later run [38971665604](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38971665604) passed the same path.

A separate, deterministic defect was proven. On the original production implementation, `PlanPreviewSession.commit()` used `return result || true` after `AlmdinaPlanWorkspaceAPI.call()` unwrapped `frappe.call().message`. A completed HTTP 200 with `message:null`, `false` or `undefined` could return `true` to `saveEditingCommand`; the coordinator then closed the Plan editor and displayed success without a commit receipt. The original phase-lock Node test used only `{committed:true}` as a mock and did not detect this.

The new Node case failed on old code at `null` (`true !== false`). The test-only commits on this branch, ending at `4fef2ebdd380d224688e80268ffd71d102898427`, used the real Desk Save button after NEW → checkpoint → restore → Native Save → System Plan bootstrap → Preview. Its positive first commit returned HTTP 200, `exact_preview_commit:true`, the same order/Plan/revision/preview token, and Kerf 4. A second preview requested Kerf 5; only its commit response was injected as HTTP 200 `message:null`, without sending this second mutation to the server. The test timed out waiting for stale Preview plus an active Plan editor on the old code. Its captured requests show one real endpoint call per Save; the positive reply has the matching receipt and the second reply is null. Evidence: [RED run 38999026193](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38999026193), artifact `cross-order-p0-runtime-evidence` (`recovery-intersection.json`). This failure is intentional RED for the new assertion, not an unrelated regression. The pre-existing identity regression job passed.

## Implemented receipt and uncertain-outcome contract

The preview response now identifies its authoritative order, source System Plan name, revision and `modified`. The frontend captures that preview once. The commit endpoint already returns `plan_payload` after `repository.save_document(plan)`, with `committed_preview_id` and `exact_preview_commit:true`. The frontend accepts success only when the reply matches that preview's token, order, Plan, revision, source/status, and all requested settings. A contradictory reply is rejected; it cannot become valid through a subsequent read.

For an absent/false response or thrown transport error, the existing read-only Plan Workspace API may query the canonical System row once. Reconciliation succeeds only when the order, row identity/revision, later `modified`, System Draft status, valid plan, all requested settings and the full sanitized plan snapshot match the preview. This is an independently read durable state, not a fabricated commit receipt. It never re-sends the one-use Preview token. If proof is unavailable, the preview becomes stale, the Plan edit session and its draft remain open, and the user is told to check the saved plan before creating a new preview. If proof succeeds, the edit closes and an orange verified-on-server message distinguishes it from a normal acknowledged commit. Workspace/Cost refresh happens only after a proved durable result; its own failure keeps the existing post-commit warning.

`DocumentContext.isCurrent` checks the original visit token at the asynchronous commit boundary. Server-side authorization, stage checks, input fingerprint, one-use token consumption and transaction logic are unchanged. A generation change or A→B navigation makes the old result a no-op.

## Verification and open release gate

- RED on old code: Node null-response assertion and pinned Desk run above. The historic run's exact predicate remains unknown.
- Local GREEN under the proposed implementation: Phase 1 15/15, Phase 2A 4/4, Plan phase-lock/locale/state/Cost reconciliation Node cases; 40 preview and localization Python checks. The deterministic suite covers true receipt, null/false/undefined, mismatched order/token/Plan/revision/settings, server rejection, lost response with canonical proof, stale canonical read, A→B and same-document generation change.
- Pinned GREEN runtime, independent DB audit, reopen, full CI and final QA: **pending on the production fix SHA**. Do not fast-forward #518/#515/#514 or certify release from the local suite alone.

Independent review must verify that real Frappe Plan Workspace serialization permits the strict receipt and reconciliation, the injected null response retains the legitimate draft, no stale response mutates another order, and all dynamic permissions/printing/Recovery regressions remain green. A failure must be classified by the captured endpoint response and independent DB row, not by coordinator idle alone.
