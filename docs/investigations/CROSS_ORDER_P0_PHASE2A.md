# Cross-order P0 — Phase 2A ownership and isolation

Branch `agent/dco-cross-order-p0-phase2a-identity-isolation` starts at the verified Phase 1 HEAD `64cafe4c9982a11b7ca1e40f2780180c82f3fa8d`. Its merge base with `Develop` is `17e526b6648d35983967c03549e2348b05cb2839`; Develop was an ancestor when work began. Investigation PR #506 remains untouched. This phase changes no Recovery, schema, cutting algorithm, DXF, or Print Renderer.

## Ownership contract

| Data | Owner | Phase 2A boundary |
| --- | --- | --- |
| DCO inputs, board, customer, dimensions, status, measurement and piece geometry/quantity | Frappe Form / order and child documents | Cost GET is read-only; its presenter cannot copy these fields from a workspace. A document transition clears form-local work and rejects previous-visit operations. |
| Plan rows, settings, revision, geometry and edit draft | Plan Workspace store | A Plan payload must name the current order. An old response cannot reset or load B, and a presenter cannot project old geometry. Same-document draft survives a refresh. |
| Cost results, price settings, financial piece values and edit draft | Cost Workspace store | Only explicitly enumerated financial fields may be reconciled into the transitional Frappe view. A read does not own the order inputs or piece identity/geometry. |
| Preview request and displayed preview | Plan Preview Session | Preview/commit after an await requires its captured DocumentContext generation. An A preview cannot replace B's display. |
| Pending mutation impact and offcut assignments | Current DCO visit | Transition clears form-local impact. Post-save reconciliation and sequential Plan/Cost refresh check the captured document identity and generation after each await. |
| DOM form inputs, Native Save, Print HTML | Frappe form and Print Renderer respectively | Phase 2B owns the remaining stale DOM/save and atomic print-document boundary. Phase 2A does not alter these implementations. |

## Root causes and changes

1. **R1 — reusable `frm` retained stores:** `DocumentContext.synchronize` resets Plan, Cost and Preview synchronously on a real A→B visit. It does not reset NEW→Saved promotion or a same-document refresh.
2. **R2–R4 — in-flight reads owned only by a form object:** Plan/Cost load keys now carry DocumentContext identity and generation. B starts its own request. Old A replies do nothing, including when B is ready; payload `order_name` is verified before commit. A failed identity check never calls `reset(B)`.
3. **R5–R6 — stale Cost presentation and broad model projection:** snapshots, presenter, event identity and read projection are guarded. Cost reconciles financial fields only, preserving order inputs, piece names, dimensions, quantity, and local price edits. The field allowlist is by data ownership, not by board color.
4. **R7 — stale Plan projection:** Plan snapshot and presenter require current order ownership before writing legacy view fields including `cutting_plan_json`; preview awaits also check the visit generation.
5. **Additional asynchronous reconciliation:** after-save impact, sequential coordinator loads and offcut pending state are fenced by the existing DocumentContext. Permission and production-stage code is unchanged.

## Evidence and limits

The unchanged Phase 1 Node baseline started at 12 RED/3 GREEN. After this change it is 1 RED/14 GREEN. The remaining RED is the DOM stale-input-to-Native-Save case (`board DOM`), which requires Phase 2B form/save handling. The new `cross_order_phase2a_ownership.test.js` passes four scenarios covering simultaneous Plan/Cost/Preview/events, multiple order fields, distinct Frappe-style rows, controlled duplicate-name defense, wrong server payload, permissions, drafts and A→B→A visit generations. Mutation impact and workspace coordinator tests pass. Fixture-only changes add the canonical `order_name`/owner identity expected from the real API, retaining the original RED assertions.

The broad local run covered 103 JS files excluding the intentional RED suite: 95 pass and eight fail on both this branch and the pristine `Develop` worktree. The eight baseline failures are `dco_sticky_tabs_geometry`, `measurement_toolbar_ux_contract`, `order_action_permission_guard`, `corner_edge_apply_save_lifecycle`, `plan_tab_capabilities`, `cutting_plan_renderer`, `order_measurement_save_flush`, and `door_cutting_order_extra_addons_ux`. These are not counted as acceptance passes or fixed here. Node syntax, Python compile and whitespace checks pass.

The added pinned Desk test uses the existing isolated Frappe v16.17.5 / ERPNext v16.17.0 fixture, opens A then B, injects a *controlled* A snapshot in Plan and Cost while B is visible, checks the model and child rows, intercepts Native `savedocs`, and reads B independently from the test server after Save. It records `phase2a-runtime-isolation.json`. This is a defensive boundary test, **not** a claim of spontaneous cross-order contamination. The Phase 1 runtime proof documents the prior controlled DB contamination and mixed final Print HTML; Phase 2A must be judged by its own CI evidence before approval.

## Acceptance and Phase 2B

Phase 2A acceptance requires R1–R7 Green, the new ownership tests Green, and successful pinned Desk evidence for the model/save boundary. The original Print-related assertion that rejects A geometry in a Plan presenter is Green; this does **not** certify the final Print Renderer, which still needs an atomic order/plan/revision/geometry/header snapshot across its asynchronous identity lookup. The stale DOM input Native Save test remains RED. Phase 2B must bind DOM flush and Save payload to current document ownership and make print use one captured, verified document identity throughout rendering. Do not make an A operation affect B in any DCO field, piece, workspace, draft, preview, late API response, save, print, or Recovery interaction.

Recovery implementation is unchanged. Phase 1 Desk NEW→Saved/Restore/Cancel/Edit certification was blocked at NEW Form navigation, so compatibility with the independent `Recovery-test` branch is unproved; keep branches separate and retest that lifecycle before merge. Dynamic capability checks and same-document draft control tests are Green locally, but they do not replace the blocked Desk Recovery evidence.

## Pinned Desk and CI verification

PR [#507](https://github.com/Hasan-Alhendi/almdina-erp/pull/507) is Draft against `Develop`. The code SHA `9f797bb2c543cc636d7a9fe48b679fcd753529b8` was exercised in [pinned run 38560776662](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38560776662) and its [evidence archive](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38560776662/artifacts/11892780941). Frappe 16.17.5 / ERPNext 16.17.0 opened both real Forms. The controlled A Cost/Plan snapshots were refused by B's presenters, with `costState` and `planState` hidden as `null`; B retained its black board, customer, rate, width 57 and unique child name. Native `savedocs` contained B's name, black board and B's child row; independent server read and database audit still show B black, A white. The fixture cleanup completed. This establishes the Phase 2A model and save boundary for that controlled case, not a proof that every possible stale DOM write is fixed.

The real saved A Plan API response was held across A→B. `sameFrm=true`, but B Plan state remained `idle` before and after releasing A, and the controlled projection of that actual A payload returned `false`. The old Phase 1 print probe then timed out waiting for the print identity callback because B had no printable Plan; **no final HTML was generated** in this guarded path. The full Print Renderer atomic identity contract remains a Phase 2B task. The separate original DOM stale-input RED remains (14 Green / 1 Red in the Phase 1 Node suite); it is not contradicted by the clean controlled Desk save.

Recovery on Develop again stopped at `NEW_route_requested` with a local `new-door-cutting-order-*` name; no NEW Form, restore/cancel or NEW→Saved completion was observed. Same-document Plan/Cost edit drafts, NEW→Saved DocumentContext promotion and dynamic permission controls pass in Node. Recovery code was not changed or merged from `Recovery-test`.

CI at the code SHA: the Phase 2A focused step and pinned Desk boundary are Green; the baseline suite's one remaining DOM RED is intentional. The pinned job is Red from the old saved-plan print probe and the existing NEW navigation Recovery blocker. Static Checks has the same two UX/style-debt failures as the original Base. F6/F7, Security UI (missing `arabic_operator_ui.js`) remain Base failures; Stage 12–15, factory permission/settings, asset-loading, endpoint auth and documentation jobs pass. General Frappe integration additionally failed test discovery because the Phase 1 browser harness imported Playwright at module import time, although that job does not install it. The harness now imports Playwright only when a browser test runs; the module imports under `python -S` without Playwright. This harness-only fix needs CI confirmation after the next push.

**Phase 2A decision: PASS for R1–R7 and the pinned controlled Desk ownership/save proof.** The PR remains Draft: Native Save DOM and atomic Print HTML are Phase 2B, and Recovery Desk certification remains blocked by the unchanged NEW route behavior. Do not treat the expected red jobs as merge approval.
