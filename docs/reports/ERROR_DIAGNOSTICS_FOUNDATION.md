# Professional error diagnostics — first production slice

Base: `Develop` at `c9081524f6d8bc5cf88cb57f0d1df60d08373524`.

## Change contract

- Goal: preserve the real failure evidence from DXF geometry to an actionable, document-owned employee dialog; provide a reusable public error boundary.
- In scope: shared error normalization; opt-in caller-owned RPC; DXF upload failure transport; layout measurements, board and copy identities; bounded read-only pair previews; safe support references; Arabic/English copy and cache revisions.
- Out of scope for this slice: migrating every business endpoint, financial/production policy changes, a full rejected-file editor, centralized cross-site support infrastructure, and production deployment.
- Invariants: same manufacturing acceptance/rejection, tolerances, identity matching, stage authorization, fingerprints, approved snapshots and file persistence. No accepted-plan or data migration.
- Layers: additive Frappe boundary, presentation projections, existing API/UI owners, and framework-free geometric evidence. No global replacement of Frappe functions.
- Permission impact: no added endpoint or grant. Numeric previews are emitted only after the existing upload authorization reaches geometric parsing. They contain the affected pair, not private file paths or cost data.
- Localization: new display strings use Frappe translation keys and `ar.csv`; existing untouched DXF copy remains compatible.
- Rollback: previous app image/assets; no stored plan/schema changes. The server still emits native Frappe messages for old clients.

## Root causes and resolutions

1. `errorMessage` previously returned raw JSON/exception strings and missed nested `responseJSON`. It now consumes a versioned public envelope or known legacy server messages, rejects unexpected exception text, and supplies safe transport-specific fallbacks. Normalized objects are privately branded rather than trusting a caller-controlled boolean.
2. Frappe's native HTTP handlers can display an error before document ownership is checked. `ownedRpc` uses same-origin, CSRF-protected fetch **only for explicitly migrated app operations**. It neither invokes the native automatic error UI nor retries commands. Native `rpc` remains intact.
3. Layout validators computed clearance and discarded it. The original exception now carries the measured value in native units; the boundary explicitly converts mm/cm. The validity comparison is unchanged.
4. Early spacing validation precedes final identity assignment. Rejected uploads are optionally diagnosed with the **same canonical identity/add-on pipeline** on detached memory. No discovery index, text label or approximate substitute proves identity. Diagnosis failure preserves the original manufacturing rejection.
5. Pair targets lost sheet and copy context. They now carry both copy numbers and board context, including two copies of the same door. Export resolution is board-scoped and refuses ambiguous keys.
6. `msgprint` is a Desk-global singleton. A document cleanup could hide an unrelated later message if that singleton were reused. New diagnostic dialogs use their own native Frappe Dialog, have idempotent close, remove their DOM on hide, and register with the existing document owner.
7. Frappe loggers default to ERROR. The separate rotating `almdina_errors` channel explicitly records INFO diagnostic events, without changing other channels. Failed logging produces no invented support reference.

## Public protocol v1

The additive `almdina_error` member contains `schema_version`, `operation`, `title`, `outcome`, `issues`, `has_more`, `validation_coverage`, and an optional `request_reference`. Original exceptions and HTTP status still reach Frappe's transaction handling.

Each issue projects only code/category, employee copy, location, action, details, highlight/table and an optional numeric preview. Raw params, debug dictionaries, exception values, credentials, cost snapshots and file URLs are excluded. Unexpected exception logs retain class and frame locations without exception values, local variables or source-line contents.

This is a diagnostics schema; it does not change manufacturing fingerprint versions.

`unknown` means that the client cannot confirm the result. In particular, a proxy timeout is not presented as a confirmed failure to save. The rejected-upload footer is used only for a confirmed validation rejection.

## Resource and lifecycle limits

- Identity enrichment: at most 200 pieces and 8,192 vertices; normal accepted imports keep their original pipeline and are unaffected by this optional diagnostic limit.
- Preview: exactly the two affected outlines and their holes, at most 512 vertices. Bounds are recomputed from finite numeric coordinates; oversized/malformed previews are omitted rather than approximated.
- Public response: at most 100 grouped cards, 20 detail lines per card, 100 table rows and 20 cells per row. Additional-card truncation is explicit. Further checks may remain after an early rejection.
- The preview is a read-only close-up, not a full-board manufacturing preview, editable plan or downloadable file. It has no persistence or extra file endpoint.
- Late A→B and A→B→A results cannot show feedback, reload a newer document or move focus. Closing a dialog and subsequent document cleanup are safe to repeat.
- Changed shared assets and the lazy upload asset have explicit cache revisions; lazy-page declarations and their ownership assertions use the matching revisions.

## Validation evidence

New regressions were run before implementation: missing clearance/board/copy evidence and the malformed/raw error extraction failed on the old code.

Local evidence includes:

- Synthetic real DXF imports through both legacy and strict entry points: 59.8×31 cm (quantity 2) versus 59.8×30.8 cm, misleading TEXT, and a real 3 mm clearance against 5 mm kerf. Rejection is preserved while exact door/copy identity and measurement are retained; source order remains unchanged.
- Original manufacturing identity/import/export suites, domain/presentation contracts, locale and architecture gates.
- Error normalization and owned-RPC Node tests: malformed nested messages, unexpected exceptions, incompatible schema, known HTTP statuses, CSRF/same-origin, freeze cleanup and no automatic retries.
- All JavaScript simulation files were exercised: 135 passed; four pre-existing failures were reproduced separately on the clean base worktree (listed below).
- Chromium 140 / Playwright 1.55: five browser cases passed, including Arabic at 375 px, English desktop, DOM injection checks, numeric SVG rendering, document deactivation, A→B→A and non-JSON 504 uncertainty without retries. The browser harness uses real shipped scripts/fetch/DOM and a local test server; it is not a full Desk deployment.
- An expanded Python selection produced 631 passing tests and 768 passing subtests, with four pre-existing rendering assertions reproduced on the clean base (below). Subsequently added targeted regressions are separately included in the permanent CI step.

`TestErrorResponseIntegration` is added to the real Bench suite to prove native V1 serialization, retained HTTP 417/native fallback, database rollback, and a file-backed support reference after rollback. Its result must be assessed from the candidate SHA's Frappe Integration run, not inferred from local stubs.

Pre-existing Python assertions (not changed or weakened):

- `test_dxf_print_edge_contract.py::test_custom_dxf_and_system_plan_share_the_same_print_renderer`
- `test_dxf_print_edge_contract.py::test_shared_renderer_draws_edge_markers_on_screen_and_print`
- `test_exact_dxf_geometry_rendering.py::test_renderer_consumes_one_canonical_geometry_model`
- `test_exact_dxf_geometry_rendering.py::test_extra_addon_print_marks_and_legend_stay_visible`

Pre-existing Node failures (not changed or weakened): `dco_sticky_tabs_geometry.test.js`, `measurement_toolbar_shared_loop.test.js`, `order_entry_locale.test.js`, `plan_tab_capabilities.test.js`. These broader legacy files are not the active Static Checks commands. The actual CI result remains authoritative.

The existing foundation assertion expecting arbitrary `Error.message` was deliberately changed to expect the supplied safe fallback, with new regressions proving the privacy behavior. Asset URL assertions retain the same ownership/order checks at the new cache revisions. No manufacturing/security assertions were relaxed.

## Operations and next migration slices

Deploy only a reviewed, CI-certified SHA using the existing release process. Reload Desk assets after deployment. No migration/backfill/re-upload of historical DXF is introduced by this slice.

Support can look up an employee reference in the site's rotating `almdina_errors.log`; logs carry operation, stable codes and safe technical frame locations for unexpected failures. Access to logs remains operational, not a new employee permission.

The reusable foundation is present, but the whole project migration is not claimed complete. Next bounded slices are:

1. Migrate production command and pricing adapters with typed reason codes and their existing action/document owners.
2. Add field-level links and error summaries to measurement/save validation, preserving the edit/recovery session.
3. Migrate background-job and integration outcomes, distinguishing command success from notification failure.
4. Expand visual diagnosis beyond the affected-pair close-up only when supported by the same authorized parsing evidence and resource limits.

Each slice needs its own change contract, relevant server/browser regressions and employee acceptance. The first-factory UAT and production deployment are not substitutes for, or implied by, the local test results.
