# DCO Recovery State Ownership & Lifecycle Contracts

> **Status:** R1 contract baseline for `ALMADINA-127`<br>
> **Scope:** Door Cutting Order (DCO) recovery analysis only<br>
> **Runtime effect:** None. This document does not implement persistence or change product behavior.<br>
> **Baseline:** `Develop` at `3d03fe09087b078bb26ce92992b2ba4330d89b6b`

## 1. Purpose and hard boundaries

Recovery is an overlay that captures recoverable user intent and returns it to the
existing owner. It is not a new form lifecycle, state store, aggregate, or save
path. The existing explicit **Save/Cancel** behavior remains authoritative.

This R1 contract defines ownership, projections, version tokens, and conflict
rules. It deliberately does **not** implement IndexedDB, remote recovery,
autosave, a new DCO field, a new canonical aggregate, or multi-tab messaging.
It does not make plan previews durable, retry inserts, or change any runtime
readiness behavior. In particular, recovery must not use `setTimeout` as a
readiness signal; restoration waits for the existing document/workspace lifecycle.

The terms **MUST**, **MUST NOT**, and **SHOULD** in this document are contracts for
future recovery implementation. They do not assert that recovery persistence
exists in the current runtime.

## 2. Recovery State Ownership Map

| State | Current owner / source of truth | Recoverable projection | Restore/commit boundary |
|---|---|---|---|
| DCO form identity and visit generation | `AlmdinaDocumentContext` | Identity metadata only | Restore only while the captured identity/generation is current. NEW promotion reuses the same generation. |
| NEW/EDIT session intent | Existing order Edit Session | Mode, edit-active intent, and conflict tokens | Recovery may ask the existing Edit Session to enter/continue editing; it must not create a second session state machine. |
| Unsaved DCO header and piece requirements | Frappe form model under `AlmdinaDocumentContext` | `DcoInputProjection` | Hydrate the existing form model, mark it dirty, and leave final persistence to explicit Save or the already-existing internal checkpoint. |
| Plan working settings | Plan `WorkspaceStore` | Dirty Plan draft only | Restore through the Plan workspace after it is loaded; commit through the existing plan command. Never copy into `frm.doc`. |
| Cost working settings | Cost `WorkspaceStore` | Dirty Cost draft only, permission-filtered | Restore through the Cost workspace; commit through its focused API. Never bypass `view_costs` or reuse confidential values for another actor. |
| Workspace freshness and refresh order | `WorkspaceSyncCoordinator` | Reason/version metadata only | Coordinator invalidates and refreshes Plan before Cost and synchronizes acknowledged document versions. Recovery never mirrors freshness state into another owner. |
| Canonical Cutting Plan | Cutting Plan aggregate (`Draft`/`Approved`/`Superseded`) | Reference/freshness metadata only | Reload from the server. Plan snapshots, placed pieces, costs, DXF, and approval state are never form-recovery payload. |
| Disposable plan preview | `AlmdinaPlanPreviewSession` plus short-lived server preview cache | None | Regenerate. `preview_id` and cached preview payload are noncanonical, single-use, and outside recovery durability. |
| Customer invoice | Server application read model | `InvoiceInputProjection` dependency/freshness data only | Regenerate on the server before display/print. A rendered or cached invoice is never authoritative. |
| Special-shape documentation draft | Special Shape Documentation workspace history | Dirty `SpecialShapeDocumentationProjection` | Restore only into that bounded workspace. Its Save remains the only documentation commit. |
| Manufacturing geometry | DCO piece field `special_shape_geometry_json` | DCO piece input | Restore as a customer/manufacturing requirement; documentation JSON must not be used to reconstruct it. |
| Reference-image bytes | Private Frappe `File` attached to the DCO Detail | Durable File URL and safe metadata only | Blob/File/Data URL is upload transport only. The durable reference is `/private/files/...`. |
| Scanner acquisition | Loopback Scanner Bridge and browser `File` | None | Transient acquisition only; upload to private Frappe File before a reference can be durable. |
| Cross-tab presence | No current owner | Future `tab_session_id` metadata only | Advisory presence/soft lease only. Server optimistic concurrency remains the correctness boundary. |

### Ownership invariant

Recovery stores a **projection**, not a second mutable copy of a canonical owner.
On restore it passes data back to `AlmdinaDocumentContext`, Edit Session,
`WorkspaceStore`, and `WorkspaceSyncCoordinator`. It must not introduce a
parallel form context, workspace store, refresh coordinator, edit-session map,
or save API.

## 3. Recovery Payload / Projection

### 3.1 Envelope

The logical envelope is versioned independently of DocType schemas:

```text
RecoveryEnvelope v1
  schema_version: 1
  draft_id: UUID
  mode: NEW | EDIT
  dirty_scope: DCO | PLAN | COST | SPECIAL_SHAPE
  target_name: null | existing DCO name
  session_origin_modified: null | server modified token
  expected_server_modified: null | latest acknowledged server modified token
  tab_session_id: UUID
  recovery_revision: monotonic integer for this draft
  captured_at: UTC timestamp
  payload_hash: SHA-256 of canonical projection JSON
  payload:
    dco: DcoInputProjection
    plan_workspace_draft: null | PlanWorkspaceDraftProjection
    cost_workspace_draft: null | CostWorkspaceDraftProjection
    special_shape_drafts: SpecialShapeDocumentationProjection[]
```

`draft_id`, `tab_session_id`, and the version tokens are recovery metadata. They
MUST NOT become new canonical DCO fields. `target_name` is null until a NEW
draft is reconciled with a successfully inserted DCO.

Only fields that the current actor may see and edit may be captured. Recovery
records are scoped at least by site, authenticated user, doctype, and `draft_id`.
They must not leak permlevel-1 cost data, another user's draft, or another site.

`dirty_scope` identifies the one mutable owner that was dirty at capture time.
The existing UI does not allow a dirty DCO form and a Plan/Cost edit draft at
the same time, so recovery MUST preserve that single-owner invariant. The DCO
projection may still be present as clean baseline context for a PLAN, COST, or
SPECIAL_SHAPE record; it must match the freshly loaded server DCO and must not be
rehydrated as a second dirty owner. A record claiming incompatible simultaneous
dirty owners is invalid and must be blocked rather than merged.

### 3.2 `DcoInputProjection v1`

Header requirements:

```text
customer, order_date, order_notes,
board_description, board_length_cm, board_width_cm,
default_edge_type, edge_color
```

Each piece contains a recovery `piece_key` plus only editable requirement fields:

```text
piece_type,
extra_double, extra_liner, extra_recessed_handle_cutout,
clipped_corner_position, clipped_corner_width_cm, clipped_corner_length_cm,
width_cm, length_cm, qty, allow_rotation,
edge_long_right, edge_long_left, edge_width_top, edge_width_bottom,
edge_long_right_type_override, edge_long_left_type_override,
edge_width_top_type_override, edge_width_bottom_type_override,
notes,
special_shape_drawing_json, special_shape_geometry_json
```

For EDIT, `piece_key` is the existing child name. For an unsaved NEW row it is a
recovery-local UUID. It is mapping metadata, not a DocType field, and array
position alone must not be used as identity.

The projection excludes:

- names generated by Frappe, `modified`, owner/audit fields, `docstatus`, status,
  revision lineage, production routing/assignment, and `approved_plan`;
- cut sizes, areas, edge meters/types/thicknesses, totals, prices, quote state,
  plan flags, engine fields, and every other server-derived/read-only value;
- canonical Cutting Plan rows/snapshot/DXF/cost snapshot;
- HTML, selected rows, timers, observers, request IDs, rendered surfaces,
  permission/capability results, and other UI cache;
- `blob:` URLs, object URLs, browser `File` objects, Data URLs/base64 image data,
  scanner responses, plan preview IDs, and preview payloads.

The main form projection may carry the last saved `special_shape_drawing_json`
visible on the child, but an independently dirty Special Shape Documentation
workspace is restored only through its bounded workspace projection. Main-form
restore must never silently overwrite a newer independently saved child drawing.

### 3.3 Workspace draft projections

`PlanWorkspaceDraftProjection v1` contains a baseline descriptor and only the
existing mutable settings:

```text
baseline: plan_name|null, plan_modified|null, normalized_settings_hash
draft:
  packing_mode, cutting_machine_type,
  optimization_time_limit_sec, kerf_mm, trim_margin_mm
```

These are the exact names owned by the current Plan `WorkspaceStore`. The
existing API adapter maps `packing_mode` and `cutting_machine_type` to the
canonical Cutting Plan fields `optimization_mode` and `machine_type`; recovery
must reuse that adapter and must not add a second naming model. The projection
is captured only when the Plan `WorkspaceStore` is editing/dirty. Restore first
loads the current Plan workspace and requires the baseline plan identity/version
and settings hash to match. A missing/replaced/changed plan is a workspace
conflict even if the DCO `modified` token still matches.

`CostWorkspaceDraftProjection v1` contains:

```text
baseline: cutting_plan|null, normalized_settings_hash
draft: board_rate_usd, cutting_cost_per_board_usd
```

It is captured/restored only for an actor with the existing cost capability and
only while the Cost `WorkspaceStore` is editing/dirty. A fresh Cost workspace
load must still resolve the same plan and settings hash before draft hydration.
Focused pending special,
clipped-corner, or extra-price commands remain owned by their current cost UX/API
and require their existing authorization and reconciliation; recovery must not
turn unacknowledged confidential command data into DCO fields.

### Capture and restore rules

Capture is a read of the owners' current editable projections; it is not a
canonical save. Restore follows this order:

1. wait for the current `AlmdinaDocumentContext` identity/generation;
2. fetch current server state and capabilities;
3. when the captured scope needs Plan or Cost, activate and fully load those
   canonical workspaces before touching any recovered workspace draft;
4. run the NEW/EDIT token check, capability check, single-owner check, and every
   required DCO/Plan/Cost baseline comparison against those fresh snapshots;
5. restore only the captured `dirty_scope` through its current owner:
   - **DCO:** hydrate the existing form model, then use
     `WorkspaceSyncCoordinator` to invalidate affected Plan before Cost. Do not
     force-refresh derived workspaces while the restored DCO inputs are still
     unpersisted; the existing post-Save/checkpoint lifecycle owns reconciliation.
   - **PLAN/COST:** keep the DCO form clean and call the existing
     `WorkspaceStore.beginEdit()`/draft mutation path only after the canonical
     load and baseline checks have settled.
   - **SPECIAL_SHAPE:** restore only after that bounded workspace has loaded and
     confirmed its DCO/piece identity and capability.
6. perform no forced workspace load or refresh after a recovered Plan/Cost draft
   is installed: current `resolveLoad()` intentionally clears `baseline`,
   `draft`, `dirty`, and `editing` and would discard the recovered intent;
7. leave persistence to the existing explicit Save/Cancel action of that owner.

No timer delay is evidence that a document or workspace is ready.

## 4. NEW lifecycle contract

1. A NEW DCO recovery session receives a UUID `draft_id` before its first
   recoverable capture. Multiple NEW drafts are allowed and remain distinct.
2. `target_name`, `session_origin_modified`, and `expected_server_modified` are
   null before the first successful insert/reconciliation.
3. Restore opens a normal NEW Frappe DCO under `AlmdinaDocumentContext`, hydrates
   `DcoInputProjection`, then leaves it dirty. It does not autosave.
4. Cancel keeps the existing Frappe/Edit Session meaning. Recovery cleanup, when
   later implemented, must be explicit and must not change Cancel behavior.
5. The first Save uses the existing DCO insert path. Recovery identity is an
   idempotency/reconciliation key around that path, not a second insert endpoint
   or a new DCO field.
6. After an acknowledged insert, the existing Document Context promotes the
   provisional identity to the permanent DCO name without changing generation.
   Recovery binds `draft_id -> target_name` and initializes both modified tokens
   from the acknowledged server document.

## 5. EDIT lifecycle contract

1. EDIT recovery is keyed by site, user, DCO name, and `draft_id`; it does not
   replace the existing Edit Session keyed by DCO.
2. At session start, capture the server's DCO `modified` into both
   `session_origin_modified` and `expected_server_modified`.
3. Recovery capture never changes either token and never marks a server write as
   acknowledged.
4. Restore first loads the current server DCO and compares its `modified` with
   `expected_server_modified`. Equality allows hydration. Inequality is a
   conflict; do not auto-merge or silently overwrite.
5. Hydration happens only while Document Context is current and current
   capabilities still allow the affected edits. The existing Edit Session remains
   the owner of edit-active/lock behavior.
6. Explicit Save retains its current behavior. On acknowledged success, advance
   `expected_server_modified`; `session_origin_modified` remains immutable.
7. Cancel discards the current form edit according to existing behavior. It must
   not implicitly publish or apply a recovery projection.

## 6. Version-token semantics

### `session_origin_modified`

The immutable DCO `modified` value observed when an EDIT session begins. It is
audit/context data: “what server version did this editing session start from?” It
is not the token for later writes after the same session has acknowledged a
checkpoint.

### `expected_server_modified`

The latest DCO `modified` value this session has **positively acknowledged**. It
is the optimistic-concurrency token for restore and the next DCO mutation.

- Start EDIT: `expected_server_modified = session_origin_modified`.
- A successful ordinary DCO Save or internal DCO checkpoint advances it from the
  authoritative response/reloaded document.
- A focused command advances it only if that command acknowledges a DCO
  `order_modified`/`document_modified` value and the existing
  `WorkspaceSyncCoordinator` reconciles it.
- Plan-only writes do not advance it unless the server explicitly reports that
  the DCO itself changed.
- A request sent, timed out, failed, or with an unknown outcome does not advance
  it. Re-query/reconcile authoritative state first.
- `WorkspaceSyncCoordinator` must keep its current rule: do not overwrite the
  dirty form's optimistic-concurrency token with a background-read version.

## 7. Existing internal pre-plan checkpoint save

The checkpoint is current product behavior, not recovery autosave:

- Order/piece inputs that affect planning are server-loaded by the optimizer.
  When those inputs are dirty, `persistPendingOrderInputs()` calls the existing
  Edit Session `persistOrderEditCheckpoint()` before planning.
- It flushes existing focused price edits, sets the preserve-edit-session intent,
  and calls native `frm.save()`.
- It is available only for an existing editable DCO, is a real canonical DCO
  write, and runs normal validation/invalidation.
- It does **not** mean “finish editing”; the Edit Session remains open. The
  ordinary Save action remains semantically distinct and locks/completes the
  edit session as it does today.
- Optimizer-only settings are sent to the focused plan command and do not request
  this broad DCO checkpoint.
- NEW DCOs cannot use the checkpoint; they must complete their normal first
  insert before a server-side plan can be calculated.
- After a successful checkpoint, first-plan creation is the existing explicit
  canonical Draft Cutting Plan command. Recalculation of an existing plan uses
  the current disposable preview followed by explicit commit. Neither operation
  is part of the DCO checkpoint itself.
- A failed or unknown checkpoint blocks the plan command and leaves the order
  inputs dirty; it must not be treated as acknowledged persistence.
- On acknowledged success it may advance `expected_server_modified`. It must not
  change `session_origin_modified`, create an autosave cadence, or become a
  recovery persistence mechanism.

## 8. First-insert idempotency and reconciliation for NEW

Current `AlmdinaDocumentContext` handles only the normal acknowledged promotion:
Frappe records `local_name -> permanent_name`, then the context aliases both names
inside the same generation. It cannot prove whether an insert succeeded when the
client loses the response.

The future recovery contract is:

1. `draft_id` is the stable, client-generated creation identity. Do not generate
   a new one for retries or restored tabs.
2. A server-side idempotency/reconciliation record, separate from DCO canonical
   fields, resolves `(site, user, doctype, draft_id)` to at most one DCO.
3. First insert and identity binding must be atomic from the server's perspective.
   Repeating the same `draft_id` returns the same outcome/name; it must not create
   a second DCO.
4. After a timeout/unknown outcome, query by `draft_id` before any retry. If bound,
   load that DCO and reconcile; if definitively unbound, the same key may be used
   for the insert attempt.
5. Bind the local recovery record to `target_name` before declaring the NEW draft
   complete. Cleanup occurs only after the permanent document and its modified
   token are acknowledged.
6. A payload mismatch under an already-bound `draft_id` is a conflict, not a new
   insert or silent overwrite.

This is a required contract for later implementation, not an R1 server change.

## 9. Scanner, drawing, and asset durability

`SpecialShapeDocumentationProjection v1` is keyed by DCO name plus permanent
piece name and contains the validated
`almdina.special-shape-documentation` version-1 document:

```text
canvas, reference, elements, notes, source, templateId
```

Asset rules:

- Scanner Bridge bytes, browser `File`, base64/Data URL upload data, and object
  URLs are transient and never recoverable payload.
- The durable byte owner is the private Frappe `File` attached to the DCO Detail.
- The durable documentation reference is the `/private/files/...` URL plus crop,
  rotation, lock, and image-size metadata inside `special_shape_drawing_json`.
- `special_shape_geometry_json` remains separate manufacturing geometry. Drawing
  documentation is explanatory and cannot be treated as manufacturing truth.
- Upload success alone is not documentation Save. A reference becomes part of
  the documented drawing only when the bounded workspace saves its JSON.
- Replacing/removing a file continues to use the existing deferred cleanup after
  documentation Save. Recovery must not delete a referenced file or persist an
  unattached transient URL.
- Plan fingerprint intentionally uses exact manufacturing geometry, not the
  documentation image/elements/notes.
- Invoice measurement rendering does use saved documentation; therefore drawing
  changes affect `InvoiceInputProjection`, not `CuttingPlanInputProjection` unless
  manufacturing geometry also changes.

## 10. `InvoiceInputProjection v1`

The customer invoice is a server-generated read model. Its effective current
input dependency is:

```text
order:
  name, customer, order_date, board_description, edge_color, revision,
  required_boards, board_rate_usd, cutting_cost_per_board_usd,
  mdf_cost_usd, cutting_cost_usd, edge_cost_usd, total_edge_meters,
  customer_quote_total_usd, total_cost_usd, customer_quote_status, order_notes

piece[]:
  name, piece_no, piece_type, width_cm, length_cm, qty,
  edge_type, edge_meters, edge_rate_usd, edge_cost_usd, notes,
  special_shape_drawing_json,
  special_shape_final_unit_price_usd, special_shape_price_note,
  clipped_corner_edge_price_usd, clipped_corner_edge_price_note,
  extra_double, extra_double_unit_price_usd, extra_double_total_usd,
  extra_liner, extra_liner_unit_price_usd, extra_liner_total_usd,
  extra_recessed_handle_cutout,
  extra_recessed_handle_cutout_unit_price_usd,
  extra_recessed_handle_cutout_total_usd
```

This projection is a dependency/fingerprint boundary, not a client-side invoice
builder and not data to write back. Many price/totals fields are derived from the
canonical Cutting Plan cost snapshot or focused pricing commands. Recovery saves
only the authorized source drafts it already owns, invalidates any cached invoice
when the effective projection changes, and asks the existing server service to
regenerate the read model before print. It never stores a rendered invoice as
authority and never creates a Sales Invoice aggregate.

## 11. `CuttingPlanInputProjection` and fingerprint/version contract

### Current canonical server projection

`CuttingPlanInputProjection v1` is currently assembled on the server by
`plan_input_fingerprint(order, plan)` and contains:

```text
version: 1
order: DCO name
order_revision
board: description, width_mm, length_mm
settings: optimization_mode, machine_type, time_limit_sec, kerf_mm, trim_margin_mm
pieces: FrappeCutDimensionPlanAdapter.piece_row_as_dict(row)[]
```

The current piece adapter includes normalized cut/final dimensions, quantity,
rotation, piece/clipped-corner requirements, exact
`special_shape_geometry_json`, selected edge sides and overrides, resolved edge
profiles/thickness/rates/costs, notes, and cut-size label. This is the current
fingerprint boundary; R1 does not narrow or reinterpret it.

The fingerprint is lowercase SHA-256 over deterministic JSON with sorted keys,
compact separators, and ASCII escaping. Its contract key is:

```text
(projection_name = CuttingPlanInputProjection,
 projection_version = 1,
 input_fingerprint,
 engine_version)
```

`engine_version` (`2.1.0-fast-save` at this baseline) is result provenance stored
separately from the input hash. Current invalidation compares the stored input
fingerprint; it does not make engine-version drift alone stale. Later recovery
must retain both values, must not put engine version into the v1 hash, and must
apply an explicit product/migration decision before changing that behavior.

Recovery stores raw editable DCO requirements and a Plan workspace settings
draft. It does not calculate this server fingerprint in the browser. After DCO
normalization/checkpoint, the existing server adapter computes the authoritative
projection/fingerprint. A recovered fingerprint is a freshness hint only; it
does not authorize reuse of a plan snapshot.

The distinct legacy order adapter payload version 4 is not the canonical Cutting
Plan aggregate fingerprint above and must not be substituted for it.

### Projection changes

Any semantic field, normalization, unit, default, ordering, or adapter-shape
change requires a new projection version and compatibility/migration tests.
Changing the optimizer implementation requires a new `engine_version` even when
the input projection is unchanged. Approved plans remain immutable historical
revisions.

## 12. Multi-tab ownership and conflict rules

There is no current cross-tab DCO coordinator. Future multi-tab recovery follows
these rules:

- Each browser tab/session has a UUID `tab_session_id`; it is advisory metadata,
  not a concurrency token.
- `BroadcastChannel` may announce presence, draft revision, or a soft lease to
  reduce accidental concurrent editing. It must not transfer canonical authority,
  persist data, or declare a write safe.
- A soft lease may nominate one active-writer UX, but it can expire, race, or be
  unavailable. The server's optimistic-concurrency check against
  `expected_server_modified` is final.
- Two tabs editing the same DCO never silently overwrite or auto-merge. A server
  version mismatch blocks restore/save and requires explicit reload/discard or a
  later product-approved reconciliation flow.
- Plan and Cost drafts additionally compare their fresh workspace owner identity
  and normalized baseline settings. DCO token equality alone cannot authorize a
  restore because Cutting Plan is an independent aggregate.
- Tabs may hold different NEW drafts because each has a different `draft_id`.
  Two tabs with the same NEW `draft_id` share one creation identity and must use
  first-insert reconciliation, never independent inserts.
- Successful same-session acknowledged writes advance only that recovery
  session's `expected_server_modified`. Other tabs detect the new server version
  and conflict/reload.
- Server permissions, document authorization, and optimistic concurrency remain
  authoritative even if tab messaging reports no conflict.

## 13. Characterized gaps and deferred risks

These are known boundaries, not R1 implementation tasks:

1. ALMADINA-128 now provides the versioned local IndexedDB draft/asset repositories
   and behavior-neutral checkpoint overlay described in
   [17_DCO_LOCAL_RECOVERY_INFRASTRUCTURE.md](17_DCO_LOCAL_RECOVERY_INFRASTRUCTURE.md).
   Restore/hydration UX and every remote recovery store remain deferred.
2. Normal NEW promotion is response-bound; lost-response idempotency requires a
   later server reconciliation mechanism.
3. The local checkpoint session now records distinct `session_origin_modified` and
   `expected_server_modified` values. Restore/conflict enforcement is still
   deferred; native Frappe `modified` and focused API `expected_modified` remain
   the current server-write enforcement mechanisms.
4. Special Shape Documentation saves the child row directly and currently does
   not return/advance a parent-DCO modified token. Main-form recovery must reload
   that bounded workspace rather than assume the DCO token detects child-only
   drawing changes. A future child-workspace version contract is still required.
5. A successfully uploaded private image can be left attached but unreferenced if
   the user abandons before documentation Save. Existing cleanup is not changed.
6. Engine-version drift alone does not currently invalidate a Draft Cutting Plan.
   R1 records this explicitly; changing it is a product/runtime decision.
7. Plan/cost setting commands do not currently expose one uniform optimistic
   concurrency token. Recovery can compare fresh owner identity/settings before
   hydration, but enforcing atomic plan-setting conflicts requires a later
   focused API contract; it must not be simulated with the DCO token.
8. Preview caches are short-lived and single-use; recovery regenerates them.
9. Cross-tab messaging/soft leases do not exist and must remain advisory when
   implemented.

Any later implementation must be a focused consumer of these contracts and the
existing lifecycle owners. It requires separate authorization, storage,
retention/cleanup, migration, conflict, and end-to-end test decisions.
