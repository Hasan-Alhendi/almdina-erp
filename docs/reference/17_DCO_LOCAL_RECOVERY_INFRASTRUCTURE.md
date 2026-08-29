# DCO Local Recovery Infrastructure

> **Status:** Canonical implementation reference
>
> **Story:** ALMADINA-128
>
> **Depends on:** [16 — DCO Recovery State Ownership](16_DCO_RECOVERY_STATE_OWNERSHIP.md)

## 1. Scope

ALMADINA-128 adds browser-local checkpoint infrastructure for Door Cutting Order.
It does not add restore/discard UX, automatic hydration, first-insert server
reconciliation, remote recovery, or cross-device synchronization. A local
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
  - `schema_version = 1`
  - stable `draft_id`
  - `mode = NEW | EDIT`
  - single `dirty_scope`
  - `target_name`
  - distinct `session_origin_modified` and `expected_server_modified`
  - `tab_session_id`
  - monotonic `recovery_revision`
  - `created_at` and `captured_at`
  - lowercase SHA-256 `payload_hash`
  - explicit `RecoveryProjection v1`
  - lightweight `asset_refs`

An unreconciled NEW record requires all server identity/version fields to be null.
An EDIT record requires the DCO name and both modified tokens. A write with an
older revision is rejected. Repeating the same revision and payload hash is
idempotent; the same revision with different content is a conflict. This prevents
a late local completion from replacing a newer checkpoint.

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

Failure transitions to `ERROR` without throwing into Frappe editing or Save.
`RESTORING` is reserved as a later-story seam; ALMADINA-128 never enters it.
Document navigation disposes the session through `AlmdinaDocumentContext` cleanup.

Every accepted mutation increments the recovery revision. Multiple mutations in
one browser frame coalesce into one write of the latest revision. Writes are
serialized; a mutation arriving during a write produces the next revision after
the current write settles. There is no timer cadence and no elapsed-time readiness
assumption.

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

After a normal first insert, the local NEW session stops writing under the promoted
form identity. It intentionally does not bind or delete the local record. Atomic
`draft_id -> target_name` server reconciliation and unknown insert-outcome handling
remain ALMADINA-129 work.

## 6. Failure and compatibility behavior

Repositories return explicit `{ok, value|error}` results. Known failure codes cover
unavailable APIs, open/blocked/schema/transaction failures, quota exhaustion,
invalid identities/revisions, oversized payloads/assets, corrupt records/assets,
hash mismatches, and missing owning drafts.

Record reads accept only schema version 1:

- a greater version returns `unknown_schema`;
- an older version returns `incompatible_schema`;
- invalid shape/hash returns an explicit corruption/integrity error;
- discovery returns valid records and reports rejected record identities/codes
  without reinterpreting them.

No failure is allowed to block form editing, current Save/Cancel, Plan/Cost behavior,
or scanner/crop behavior. No automatic migration is defined in v1.

## 7. Deferred behavior

The following remain explicitly deferred to ALMADINA-129 and later stories:

- checkpoint discovery UX, restore/discard prompt, and hydration;
- NEW first-insert idempotency and server reconciliation;
- EDIT restore/conflict UX and external edit resolution;
- official-save cleanup/retention policy;
- activation of local assets in Special Shape recovery;
- invoice, canonical Cutting Plan, lost calculation, and remote recovery behavior;
- BroadcastChannel/soft-lease multi-tab hints.

Server authorization and optimistic concurrency remain authoritative in every tab.
