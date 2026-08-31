# NEW DCO Recovery & First-Insert Reconciliation

> **Status:** Canonical implementation reference
>
> **Story:** ALMADINA-129
>
> **Depends on:** [16 — State Ownership](16_DCO_RECOVERY_STATE_OWNERSHIP.md),
> [17 — Local Infrastructure](17_DCO_LOCAL_RECOVERY_INFRASTRUCTURE.md)

## 1. Boundary

NEW recovery is a continuity overlay on the existing Frappe NEW Door Cutting
Order form. It discovers site/user-scoped local `DCO` projections, requires an
explicit choice, and returns those inputs to the current form model. It never
creates an official DCO, canonical Cutting Plan, invoice, or remote recovery
record. EDIT recovery remains deferred.

## 2. Discovery and identity

Opening a NEW form queries `LocalDraftRepository` for `NEW` records in the current
site, authenticated user, and Door Cutting Order namespace. No record is restored
silently. The Arabic dialog distinguishes local work by last update, customer,
measurement count, board description, edge color, and special-piece presence.

The actions are:

- `متابعة الطلب`: restores exactly the selected draft;
- `بدء طلب جديد`: creates a fresh recovery UUID and retains every old draft;
- `حذف المسودة`: confirms meaningful work, then deletes only that draft and its
  local assets through the repository transaction.

These choices are mutually exclusive for the discovery dialog: while one Continue,
Delete, or Start New action owns the dialog, every discovery action is disabled and
a second choice is ignored until the active operation settles. Async Continue/Delete
completion may update that dialog or initialize an empty NEW recovery session only
while the original initialization and `AlmdinaDocumentContext` token still own the
current form. A late final-card Delete after navigation may finish its repository
transaction, but it cannot hide or initialize the replacement document. If discovery
fails safely after the user has already edited the form, that queued first mutation
is replayed into the fail-open recovery session instead of being dropped.

`draft_id` is the stable UUID across checkpoint, reopen, restore, temporary Frappe
names, first Save, and reconciliation. Row `piece_key` values are restored into the
existing checkpoint owner's out-of-document WeakMap and retain row order.

## 3. Hydration

Hydration accepts only a verified `mode=NEW`, `dirty_scope=DCO` payload. It enters
`RESTORING`, then calls a framework-neutral hydration port. The presentation adapter
assigns only `RecoveryProjection v1` header fields, replaces the child table once
in projection order, maps recovery piece identities, refreshes fields, and invokes
the current measurement/keyboard presentation owners once. The application layer
does not depend on Frappe or `frm`. Normal
mutation checkpoints are ignored while `RESTORING`; after completion the native
form is dirty and normal editing resumes.

Plan workspace drafts, Cost workspace drafts, canonical plan objects, previews,
invoice output, workflow fields, and derived totals are rejected at this boundary.
No Save or network command is issued by hydration. Invalid/corrupt records fail
before form mutation. There is no timeout-based readiness assumption.

Durable private Frappe File references remain references in approved projection
fields. Browser-local Blob bytes remain in `LocalAssetRepository`; the draft
envelope carries only asset IDs. ALMADINA-129 does not redesign scanner/crop or
activate an independent NEW special-shape workspace restore.

## 4. First insert contract

Before native first Save, the integration flushes the latest checkpoint, persists
`PENDING_RECONCILIATION`, enters `OFFICIAL_SAVING`, and supplies the same UUID in
the hidden technical DCO field `recovery_creation_token`. The server validates a
canonical UUID and overwrites `recovery_creation_user` from `frappe.session.user`
in `before_insert`.

`recovery_creation_token` has a database unique constraint. Therefore two native
insert requests with the same identity cannot both commit: the DCO row itself is
the atomic `creation identity -> permanent DCO` binding. This does not create a
second insert endpoint or business identity.

The narrow reconciliation endpoint accepts only the token. It resolves only a DCO
bound to the current authenticated user, applies normal DCO read permission, never
accepts a permanent name, and requires `CREATE_ORDER` before proving that the
current user's token is unbound. Another actor's token is indistinguishable from an
unused token.

## 5. Outcomes and cleanup

| Outcome | Local state / action |
|---|---|
| Client/server validation or definite responded failure | Return to `ACTIVE`; retain the draft. |
| Transport failure with unknown outcome | Remain `PENDING_RECONCILIATION`; do not retry or delete. |
| Reconciliation says `NOT_FOUND` | Server has proved absence; return to `ACTIVE`; the next explicit Save may reuse the same token. |
| Acknowledged insert or reconciliation says `CREATED` | Enter `COMPLETED`, then delete the local draft/assets, and use the server-returned permanent DCO. |
| Reconciliation unavailable | Do not hydrate a pending draft and do not retry insert; retain local state. |

Cleanup ordering is server proof, `COMPLETED`, then local delete. A failed local
delete leaves a discoverable pending record that resolves idempotently next time.
An exact same-revision retry preserves a stored `PENDING_RECONCILIATION` marker;
higher checkpoint revisions are refused while that insert attempt is pending, so
the attempted payload cannot move underneath an acknowledged result. Only the
explicit server-proven `NOT_FOUND` transition may return the record to `ACTIVE`.
That transition is compare-and-set against both the recovery revision and the exact
`official_save_attempted_at` it reconciled. The timestamp is retained as the last
attempt fence while `ACTIVE`, and each later attempt advances it monotonically, so
a late `NOT_FOUND` cannot clear a newer pending attempt from another tab.
Pending reconciliation and hydration also retain the source DocumentContext token,
and require `AlmdinaDocumentContext.isCurrent`, so a late response cannot mutate a
departed form, change global Save validation, delete its checkpoint, or route the
user back to it.
If the source form becomes inactive while its asynchronous `before_save` work is
pending, the hook rejects that originating Save with a private cancellation error;
it does not write the process-global validation flag on behalf of a departed form.
It may return only the exact attempt created by that Save to `ACTIVE`; a pending
attempt merely observed from another tab is preserved. The originating state and
attempt remain lexically available until this correction finishes, with a direct
repository compare-and-set fallback if DocumentContext cleanup disposed the session.
That fallback re-reads the record, verifies the same pending attempt, and uses its
current checkpoint revision as a defensive compatibility fence. If the record
changes between the read and compare-and-set, cleanup re-reads and retries a bounded
number of times while the exact attempt is still pending. A stale revision before native insert is
a cross-tab ownership conflict and blocks that insert; it never fails open over a
newer local payload. Native Save completion/failure handling retains the originating
state and exact attempt, so reusing the same form object cannot mutate a replacement
document's recovery session. This applies to acknowledged success as well as failure:
success deletes only the originating draft and does not dispose the replacement
observer/session; ownership is rechecked after asynchronous local deletion. The
delete itself compares both the originating attempt's recovery revision and exact
attempt timestamp, retaining the draft/assets on either mismatch. When marker
creation fails but native Save remains fail-safe available, the operation compares
against the prior ACTIVE attempt and persisted `saved_revision` fences, never an
unpersisted higher in-memory revision; a successful marker creation replaces them
with the new attempt. That prior timestamp is cleanup evidence only; failure
handling treats an operation as pending only when that operation durably created
its own pending marker. A
fallback CAS may synchronize a live session only when its revision still matches.
A higher persisted revision represents a different, non-hydrated payload: the
current session is quarantined from checkpointing and official Save until the user
reopens the draft and restores that newer payload. The same quarantine applies when
the conflict is discovered by a scheduled, visibility, or pagehide checkpoint
flush or while beginning an attempt owned by another tab; the stale session never
manufactures ownership of the other tab's attempt timestamp. Discovery-dialog
deletion is likewise compare-and-delete against the revision and attempt shown to
the user; a mismatch disables that card's actions instead of adopting an unseen
revision behind the old summary, so the newer draft is retained for reopen.
Continue also re-reads and matches the displayed revision/attempt before creating a
session, and each discovery choice locks all mutually exclusive dialog actions for
the full async operation. Continue/Delete additionally retain their selected card's
revision/attempt fence. Each checkpoint command compares the session's last persisted base revision,
so accumulating multiple in-memory mutations cannot leapfrog another tab's newer
record.
Recovery infrastructure failure is logged/fail-safe and does not remove native
explicit DCO creation. There is no official autosave, periodic `frm.save()`, remote
sync, cross-device restore, or product behavior change outside NEW continuity.
