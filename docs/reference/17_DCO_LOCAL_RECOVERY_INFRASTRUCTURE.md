# DCO Local Recovery Infrastructure

> **Status:** Canonical implementation reference
>
> **Story:** ALMADINA-128
>
> **Depends on:** [16 — DCO Recovery State Ownership](16_DCO_RECOVERY_STATE_OWNERSHIP.md)

## 1. Scope

ALMADINA-128 adds browser-local checkpoint infrastructure for Door Cutting Order.
Its ALMADINA-129 consumer now adds bounded NEW discovery/hydration and first-insert
reconciliation as specified by
[18 — NEW DCO Recovery](18_DCO_NEW_RECOVERY.md). It still does not add EDIT
recovery, remote recovery, or cross-device synchronization. A local
checkpoint is temporary recovery state; it is not an official DCO Save and is not
a new business source of truth.

The implementation is a bounded overlay under
`public/js/door_cutting_order/recovery/`:

| Layer | Responsibility |
|---|---|
| Application projection | Explicit v1 allowlists for DCO, Plan, Cost, and Special Shape recovery inputs. Rejects transient assets/runtime objects. |
| Application checkpoint session | Owns recovery-only status, monotonic revision, the immutable origin token, and the latest acknowledged expected token. |
| Infrastructure IndexedDB gateway | Owns database open/upgrade, transactions, SHA-256, error normalization, and best-effort persistence permission. |
| Infrastructure repositories | Own versioned draft/asset records and fail-safe CRUD/discovery. |
| Presentation integration | Reads the existing Document Context, Edit Session, and WorkspaceStore owners; batches writes through Document Context frames and lifecycle events. |

The subsystem does not own the live Frappe document, edit-active state, Plan/Cost
drafts, workspace freshness, official persistence, permissions, or server
concurrency. Those remain with `AlmdinaDocumentContext`,
`AlmdinaOrderRevisionUX`, `WorkspaceStore`, and `WorkspaceSyncCoordinator`.

## 2. IndexedDB schema

Database: `almdina_erp_dco_recovery`, version `1`.

### `dco_recovery_drafts`

- key path: `storage_key`
- storage identity:
  `(site, authenticated user, Door Cutting Order, draft_id)`
- indexes: `namespace_key`, `target_key`, `captured_at`
- record contract:
  - `schema_version = 2` (`v1` remains readable as `official_save_state=ACTIVE`)
  - stable `draft_id`
  - `mode = NEW | EDIT`
  - single `dirty_scope`
  - `target_name`
  - distinct `session_origin_modified` and `expected_server_modified`
  - `tab_session_id`
  - monotonic `recovery_revision`
  - `created_at` and `captured_at`
  - `official_save_state = ACTIVE | PENDING_RECONCILIATION`
  - nullable `official_save_attempted_at`; once used, it is retained as the last
    reconciled attempt fence while `ACTIVE`
  - lowercase SHA-256 `payload_hash`
  - explicit `RecoveryProjection v1`
  - lightweight `asset_refs`

An unreconciled NEW record requires all server identity/version fields to be null.
An EDIT record requires the DCO name and both modified tokens. A write with an
older revision is rejected. Every write command also carries the session's last
persisted revision as `expected_recovery_revision`; the repository checks that base
inside the write transaction but does not store it as a record field. A missing
record therefore accepts only base `0`, and an existing record accepts only its
exact current revision. Repeating the same revision and payload hash remains
idempotent even after the first attempt committed; the same revision with different
content is a conflict. This prevents both a late completion and a stale tab that
batched several local mutations from replacing a newer checkpoint.
Once a NEW record is `PENDING_RECONCILIATION`, only an exact same-revision retry is
idempotent; a higher checkpoint write is rejected with `save_attempt_conflict`.
The pending revision is therefore the immutable payload boundary for that insert
attempt.

### `dco_recovery_assets`

- key path: `storage_key`
- indexes: `draft_key`, `namespace_key`
- record contract:
  `asset_id`, schema version, Blob, MIME type, length, SHA-256 content hash,
  file name, and creation timestamp

An asset can be written only for an existing draft. Asset identity is idempotent
for identical bytes and conflicts for different bytes. Deleting a draft deletes
every asset with its `draft_key` in the same IndexedDB transaction. Explicit asset
delete is also available.

The main recovery payload references `asset_id`; Blob bytes are never embedded in
every checkpoint. This repository is the durable browser-local seam for a later
non-server-backed scanner/drawing flow. ALMADINA-128 does not change the current
Special Shape behavior: its scanner `File` is uploaded immediately and the durable
current byte owner remains the private Frappe `File`.

## 3. Projection and capture

`RecoveryProjection v1` implements the exact R1 allowlists from the ownership
contract. It never serializes all of `frm.doc` or arbitrary controllers. It
excludes server-derived totals/status, canonical plan data, invoice HTML, preview
objects, DOM/dialog state, timers, permissions, request state, `File`/Blob values,
and `blob:`/Data URLs.

The current integration checkpoints:

- DCO requirement mutations for NEW forms and active EDIT sessions;
- a dirty Plan `WorkspaceStore` draft when its existing store subscription reports
  `editing && dirty`;
- a dirty Cost `WorkspaceStore` draft under the same rule.

Plan and Cost capture reads those existing stores and persists only their current
editable draft fields plus a normalized baseline-settings hash. It does not load,
restore, or reconcile a workspace. Special Shape projection and asset repositories
are seams only in this story; the standalone workspace runtime is unchanged.

Unsaved piece identities use recovery-local UUIDs held outside the DocType. Existing
EDIT child rows retain their permanent child names. NEW `draft_id` and
`tab_session_id` are secure UUIDs and never become canonical DCO fields.

## 4. Checkpoint lifecycle

The recovery-only status contract is:

`READY_CLEAN -> DIRTY -> LOCAL_SAVING -> LOCAL_SAVED`

ALMADINA-129 activates the NEW-only extensions `RESTORING`, `OFFICIAL_SAVING`,
`PENDING_RECONCILIATION`, and `COMPLETED`. While `RESTORING`, user-mutation
checkpoint effects are suppressed; it is not a second form lifecycle.

Failure transitions to `ERROR` without throwing into Frappe editing or Save.
ALMADINA-128 itself did not enter `RESTORING`; only the explicit ALMADINA-129 NEW
continuation action may enter it.
Document navigation disposes the session through `AlmdinaDocumentContext` cleanup.

Every accepted mutation increments the recovery revision. Multiple mutations in
one browser frame coalesce into one write of the latest revision. Writes are
serialized; a mutation arriving during a write produces the next revision after
the current write settles. Each write is fenced against the last revision that this
session actually persisted, not merely against its higher in-memory revision. A
background `stale_revision`, `revision_conflict`, or pending-attempt conflict
quarantines that form from later checkpoint and official-Save effects until the
draft is explicitly reopened and reconciled/hydrated. There is no timer cadence and
no elapsed-time readiness assumption.

When the page becomes hidden or receives `pagehide`, the current dirty session asks
the local repository to flush on a best-effort basis. No network request and no
official Save is attempted during unload. `navigator.storage.persist()` is requested
once as a best-effort hardening measure when available; its denial/failure does not
affect correctness or DCO availability.

## 5. Version tokens and current saves

For EDIT, the session captures the current server `modified` into both tokens:

- `session_origin_modified` is immutable for the lifetime of the session;
- `expected_server_modified` advances only after an acknowledged DCO Save exposes
  a new `frm.doc.modified`.

This includes the existing internal pre-plan checkpoint. That checkpoint remains a
real, explicit canonical Save initiated by the current Plan/Edit Session path; local
recovery neither calls it nor creates a cadence around it. The presentation adapter
only observes its acknowledged `after_save` result and records the advanced expected
token.

For a first insert, ALMADINA-129 flushes the latest checkpoint and marks the local
record pending before the existing explicit Frappe Save proceeds. A hidden unique
technical creation token on the DCO is the atomic binding; acknowledged or
server-reconciled success completes and then removes the local record only through a
compare-and-delete on the attempted recovery revision and exact attempt timestamp.
A higher checkpoint cannot be accepted while the attempt is pending, and any
cleanup mismatch retains the local record/assets. An unknown transport outcome
retains them for reconciliation. If persisting a new pending marker fails and the
existing fail-safe native Save proceeds, its operation keeps the ACTIVE record's
pre-attempt revision/timestamp fence for acknowledged-success cleanup; a successfully
created marker replaces that fence with its newly returned values.

## 6. Failure and compatibility behavior

Repositories return explicit `{ok, value|error}` results. Known failure codes cover
unavailable APIs, open/blocked/schema/transaction failures, quota exhaustion,
invalid identities/revisions, oversized payloads/assets, corrupt records/assets,
hash mismatches, and missing owning drafts.

Record reads accept schema versions 1 and 2:

- a greater version returns `unknown_schema`;
- v1 is read deterministically as active and is upgraded on the next write/state transition;
- versions older than v1 return `incompatible_schema`;
- invalid shape/hash returns an explicit corruption/integrity error;
- discovery returns valid records and reports rejected record identities/codes
  without reinterpreting them.

No failure is allowed to block form editing, current Save/Cancel, Plan/Cost behavior,
or scanner/crop behavior. Record v1 is compatibility-read and lazily rewritten as
v2 only by a later checkpoint or official-save state transition.

## 7. Deferred behavior

The following remain explicitly deferred to later stories:

- EDIT restore/conflict UX and external edit resolution;
- activation of local assets in Special Shape recovery;
- invoice, canonical Cutting Plan, lost calculation, and remote recovery behavior;
- BroadcastChannel/soft-lease multi-tab hints.

Server authorization and optimistic concurrency remain authoritative in every tab.
