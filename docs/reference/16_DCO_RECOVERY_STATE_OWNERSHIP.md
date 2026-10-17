# DCO Recovery State Ownership & Lifecycle Contracts

> **Status:** Architecture and lifecycle contract baseline for `ALMADINA-127`<br>
> **Scope:** State ownership and lifecycle contract characterization only. NEW recovery behavior belongs to `ALMADINA-129`; EDIT recovery and restore behavior are deferred to `ALMADINA-131`.<br>
> **Runtime effect:** None. This document does not implement persistence or change product behavior.<br>
> **Baseline:** `Develop` at `17e526b6648d35983967c03549e2348b05cb2839`

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
| NEW/EDIT session intent | Existing `AlmdinaDcoEditSessionCoordinator` | Mode, edit-active intent, and conflict tokens | Recovery may ask the existing Edit Session to enter/continue editing; it must not create a second session state machine. |
| Unsaved DCO header and piece requirements | Frappe form model under `AlmdinaDocumentContext` | `DcoInputProjection` | Hydrate the existing form model, mark it dirty, and leave final persistence to explicit Save or the already-existing internal checkpoint. |
| Local temporary recovery record and checkpoint state | Existing `CheckpointSession`, `LocalDraftRepository`, and `LocalAssetRepository` | Versioned allowlisted projections and durable private-file references only | Own local revision/hash/checkpoint metadata and temporary bytes; they do not own a DCO, workspace, price, or official Save. |
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
customer, order_date, order_notes, order_cutting_machine,
board_description, board_length_cm, board_width_cm,
default_edge_type, edge_color
```

Each piece contains a recovery `piece_key` plus only editable requirement fields:

```text
piece_type,
extra_double, extra_full_door_double, extra_liner,
liner_reference_side, liner_offset_cm, liner_width_cm, liner_start_cm, liner_length_cm,
extra_back_groove,
back_groove_reference_side, back_groove_offset_cm, back_groove_width_cm,
back_groove_start_cm, back_groove_length_cm,
extra_recessed_handle_cutout,
recessed_handle_reference_side, recessed_handle_offset_cm, recessed_handle_width_cm,
recessed_handle_start_cm, recessed_handle_length_cm,
clipped_corner_position, clipped_corner_width_cm, clipped_corner_length_cm,
width_cm, length_cm, qty, allow_rotation,
edge_long_right, edge_long_left, edge_width_top, edge_width_bottom, edge_break, edge_break_only,
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

### 3.3 Field Ownership / Mutation Capture Manifest

The current `frm.doc` and its `pieces` child rows are the canonical live input
model. Capture reads these model values after the existing mutation path has
updated them; it does not scrape rendered controls, retain a parallel Fast Entry
buffer, or infer state from calculated output. The recovery projection's
`HEADER_FIELDS` and `PIECE_FIELDS` allowlists in
`door_cutting_order_recovery_projection.js` are the capture manifest. The table
maps those allowlists to their current owner and restore boundary:

| Input family and exact capture fields | Current owner and mutation/capture point | Permitted recovery boundary |
|---|---|---|
| Order header: `customer`, `order_date`, `order_notes`, `order_cutting_machine`, `board_description`, `board_length_cm`, `board_width_cm`, `default_edge_type`, `edge_color` | Frappe `Door Cutting Order` form controls and `frm.doc`; ordinary control changes update the form model. | Capture/restore only these allowlisted inputs to the current form model. Never include read-only note preview/comment, status, production assignment, or derived totals. |
| Piece identity and dimensions: `piece_type`, `width_cm`, `length_cm`, `qty`, `allow_rotation`, `notes`; clipped-corner inputs `clipped_corner_position`, `clipped_corner_width_cm`, `clipped_corner_length_cm` | `frm.doc.pieces` (`Door Cutting Order Detail`); Fast Entry and row editors mutate the existing child row. `piece_key` maps persisted child `name` or a NEW recovery-local UUID and is never a DocType field. | Capture values from child rows by `piece_key`; restore only requirement fields. Do not capture row position as identity, Frappe child names into NEW rows, or read-only `piece_no`. |
| Direct Fast Entry extras: `extra_double`, `extra_full_door_double`, `extra_liner`, `extra_back_groove`, `extra_recessed_handle_cutout` | Existing Fast Entry and extra-addon controls mutate the same `frm.doc.pieces` row; calculation/presenter output is downstream. | Capture the five selection inputs only. Unit rates, totals, and other derived pricing are excluded and remain with Cost/pricing owners. |
| Liner machining requirement: `liner_reference_side`, `liner_offset_cm`, `liner_width_cm`, `liner_start_cm`, `liner_length_cm` | The liner add-on configuration/editor mutates the same `frm.doc.pieces` child input row, with the side relative to the door/edge and the numeric offset, width, start, and length expressed in centimeters. Geometry calculation, visualization, and generated toolpaths are downstream consumers, not independent owners of the inputs. | Capture and restore these five editable scalar requirements with the same `piece_key` as the corresponding DCO row. Preserve the side value and measurements without inferring them from a rendered path. Only existing validation and Save/checkpoint recomputation may update derived geometry; do not capture toolpaths, material costs, or unit prices. |
| Back-groove machining requirement: `back_groove_reference_side`, `back_groove_offset_cm`, `back_groove_width_cm`, `back_groove_start_cm`, `back_groove_length_cm` | The back-groove add-on configuration/editor updates the current `frm.doc.pieces` child input row; its reference side and centimeter dimensions belong to DCO input ownership, not Cutting Plan or the cost workspace. | Capture and restore exactly these editable requirement values on their `piece_key`, respecting the DCO dirty owner and current edit permissions. Never infer or replay generated groove toolpaths or any pricing. Downstream Plan/Cost data remains subject to existing lifecycle invalidation and reconciliation. |
| Recessed-handle machining requirement: `recessed_handle_reference_side`, `recessed_handle_offset_cm`, `recessed_handle_width_cm`, `recessed_handle_start_cm`, `recessed_handle_length_cm` | The recessed-handle add-on configuration/editor writes these reference-side and centimeter input values into the current `frm.doc.pieces` row; the machining overlay/CNC shape is derived output. | Capture and restore these five editable DCO inputs with row identity and document-scoped permissions, never the resulting toolpath, drawing cache, or manual/service cost. Preserve the existing single-dirty-owner and server-version conflict rules. |
| Side selection and bulk edge toggles: `edge_long_right`, `edge_long_left`, `edge_width_top`, `edge_width_bottom`, `edge_break`, `edge_break_only`; profile overrides `edge_long_right_type_override`, `edge_long_left_type_override`, `edge_width_top_type_override`, `edge_width_bottom_type_override` | Existing Fast Entry edge controls, “apply to all four” bulk action, multi-edge editor, and clipped-corner editor mutate the existing child rows. Mutation events and downstream invalidation observe the form model; DOM toggle classes are presentation only. | Capture the resulting selected-side flags and four per-side overrides from `frm.doc.pieces`. Do not capture aggregate `edge_type`, rates, meters, costs, or stale DOM state. Restore runs through the same form/context owner and leaves derived Plan/Cost refresh to the established Save/checkpoint lifecycle. |
| Shape requirement and documentation reference: `special_shape_geometry_json`, `special_shape_drawing_json` | Manufacturing geometry is DCO child input owned by the shape editor. Drawing reference/metadata is owned by the bounded Special Shape Documentation workspace; the DCO child value is only its last saved reference. | Capture geometry as DCO requirement. In the DCO projection, include only the last saved drawing JSON; capture an independently dirty drawing only through its workspace projection. Restore must not overwrite a newer workspace-saved drawing or persist transient file bytes/URLs. |
| Plan/Cost working fields: Plan `packing_mode`, `cutting_machine_type`, `optimization_time_limit_sec`, `kerf_mm`, `trim_margin_mm`; Cost `board_rate_usd`, `cutting_cost_per_board_usd` | Existing Plan and Cost `WorkspaceStore` / Edit Session own each mutable draft; current form values are not their owner. | Capture only when that exact workspace is dirty. Cost projection is filtered by current `view_costs` capability and actor/document scope; restore after canonical workspace load and baseline checks. Never copy Plan or Cost drafts into `frm.doc`. |
| Protected manual prices and calculated finance: `special_shape_custom_unit_price_usd`, `clipped_corner_edge_price_usd` and pricing status/notes/set-by/set-on fields; `extra_*_unit_price_usd`, `extra_*_total_usd`, estimates/final prices, rates, costs, quote totals/status | Focused authorized pricing commands and server `Document`/Cost services own protected manual price decisions; server calculations and canonical plan/cost snapshots own computed fields. | Excluded from every recovery projection, including the permission-filtered Cost settings draft. Preserve acknowledged server values; pending price commands require their existing command reconciliation and must not be replayed by recovery. No price or cost data may cross actor/document scope. |

The field sets above must stay aligned with `HEADER_FIELDS`, `PIECE_FIELDS`,
`PLAN_DRAFT_FIELDS`, and `COST_DRAFT_FIELDS` in the recovery projection module.
Any new mutable field requires an explicit owner, mutation source, sensitivity
classification, and restore boundary here plus a characterization test before
it enters a projection allowlist.

### 3.4 Workspace draft projections

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

### Authorization boundary

Capture and restore are permitted only for the current authenticated actor, site,
doctype, document, and active lifecycle. Evaluate the actor's current dynamic
capability and applicable document scope, assignment, and configurable stage at
capture and again at restore; never persist a capability result as authority or
infer access from a role name or fixed stage name. Cost values additionally
require the existing `view_costs` capability. Missing, stale, or indeterminate
authorization blocks restore. Frappe's server permission check remains final on
official Save.

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

## 5. EDIT lifecycle contract: session ownership and deferred recovery

This section records current EDIT session ownership and version-token constraints
for future recovery work. ALMADINA-127 does not implement EDIT checkpointing,
restoration, or conflict UX; those behaviors belong to ALMADINA-131.

1. The current Edit Session remains keyed by DCO. Any future EDIT recovery record
   is keyed by site, user, DCO name, and `draft_id`; it must not replace that
   session owner.
2. At session start, capture the server's DCO `modified` into both
   `session_origin_modified` and `expected_server_modified`.
3. Recovery capture never changes either token and never marks a server write as
   acknowledged.
4. ALMADINA-131 restore must first load the current server DCO and compare its
   `modified` with `expected_server_modified`. Equality may permit hydration;
   inequality is a conflict and must not auto-merge or silently overwrite.
5. Any ALMADINA-131 hydration must happen only while Document Context is current
   and current capabilities still allow the affected edits. The existing Edit
   Session remains the owner of edit-active/lock behavior.
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
  extra_full_door_double, extra_full_door_double_unit_price_usd, extra_full_door_double_total_usd,
  extra_liner, extra_liner_unit_price_usd, extra_liner_total_usd,
  extra_back_groove, extra_back_groove_unit_price_usd, extra_back_groove_total_usd,
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

`CuttingPlanInputProjection v2` is currently assembled on the server by
`plan_input_fingerprint(order, plan)` and contains:

```text
version: 2
order: DCO name
order_revision
board: width_mm, length_mm
settings: optimization_mode, machine_type, time_limit_sec, kerf_mm, trim_margin_mm
pieces: cut/final dimensions, quantity, rotation, piece type, clipped-corner
        and special-shape geometry, selected edge sides, and edge thickness
```

Commercial labels stay out of this hash: customer name, board description, edge
color, edge-profile names, rates, costs, notes, and cut-size labels. Those
fields do not cancel an approved plan or show the mismatch banner. Changing
piece size, quantity, edge sides/thickness, board size, or optimizer settings
does. Freshness comparison still accepts stored v1 hashes when only the board
label changed, so historical plans are not mass-cancelled.

The piece adapter used for optimizer input may still carry commercial labels for
display; only the freshness/input hash is narrowed. Stored v1 fingerprints remain
comparable through `freshness_expected_fingerprint`.

The fingerprint is lowercase SHA-256 over deterministic JSON with sorted keys,
compact separators, and ASCII escaping. Its contract key is:

```text
(projection_name = CuttingPlanInputProjection,
 projection_version = 2,
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

## 13. Frappe compatibility contract: source review baseline

The compatibility target for this contract is **Frappe v16.17.5** at commit
`75baafaa0bde07a86bf28764383b93b5df97bc7e` and **ERPNext v16.17.0** at commit
`7b494dc9e8e47d288de5427bae25ce8a52c37d96`. These are the immutable source
revisions reviewed for this contract. In Frappe's
[`form.js`](https://github.com/frappe/frappe/blob/75baafaa0bde07a86bf28764383b93b5df97bc7e/frappe/public/js/frappe/form/form.js),
`frm.save()` runs the existing form validation/before-save path and returns a
Promise; the native form save module also retains the dedicated Cancel endpoint
in [`save.js`](https://github.com/frappe/frappe/blob/75baafaa0bde07a86bf28764383b93b5df97bc7e/frappe/public/js/frappe/form/save.js).
On the server, [`Document._save` and `check_if_latest`](https://github.com/frappe/frappe/blob/75baafaa0bde07a86bf28764383b93b5df97bc7e/frappe/model/document.py)
retain permission checks and compare the loaded `modified` token before updating;
a stale version raises `TimestampMismatchError`. The recovery contract therefore
keeps official Save/Cancel, server permission enforcement, and native optimistic
concurrency as the persistence authority.

This is **source-level compatibility evidence only**. It does not claim an
installed v16.17.5/ERPNext v16.17.0 site, browser certification, or actual
Frappe Runtime test. The retained Frappe v16.51.0 / ERPNext v16.50.0 environment
does not prove behavior for the pinned target. Actual Runtime and browser
certification remain assigned to stories that require those tests, including
ALMADINA-128, ALMADINA-129, ALMADINA-131, and ALMADINA-135.
These contracts were checked against the pinned Frappe source and the
current DCO implementation; unrelated Print Format Editor or Wiki draft
implementations are not treated as drop-in DCO services or lifecycle authority.

**Evidence classification:** A — Architecture, static, and characterization
tests are ALMADINA-127 acceptance evidence. B — actual target-version Frappe
Runtime and browser certification are separate certification evidence and are
not claimed or required to mark this architecture-only story complete.

## 14. Characterized gaps and deferred risks

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
