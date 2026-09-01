# Door Cutting Order frontend architecture

The active Door Cutting Order frontend is organized here by feature ownership.
Stage 9 established these boundaries without mixing path ownership changes with
business-logic rewrites.

## Boundaries

- `core/`: document identity/lifecycle, revision mode, global action capability guards, toolbar stability.
- `order_entry/`: order defaults and data-entry behavior.
  - `measurements/`: row entry, keyboard flow, measurement toolbar/resilience/performance.
  - `edge_banding/`: edge selection, profiles, colors and derived cut dimensions.
  - `extra_addons/`: Extra-door requirement selection and accessible presentation; no pricing formulas.
- `cutting_plan/`: plan rendering, controls, tabs/surface, drawing-plan and DXF approval/export coordination.
- `costing/`: cost presentation, cost capabilities and customer financial actions.
- `printing/`: print identity/theme/presenters and printable shape/document composition.
- `production/`: shop-floor behavior owned by the order form.
- `responsive/`: order header/mobile-card adaptations.
- `drawing/`: facade/integration for special-shape drawing and clipped-corner behavior.
- `recovery/`: bounded local recovery overlay split into application projections/session,
  IndexedDB repositories, and presentation integration. It reads existing owners and
  never becomes a document/workspace/save authority.
- `list_view/`: Door Cutting Order list presentation, search, status/stage presentation and list quick actions.

### A5 aggregate workspace state

The unified order workspace has three state owners even while it remains mounted on
the native Door Cutting Order form:

1. **Order** continues to use the Frappe Door Cutting Order document for customer requirements and lifecycle state.
2. **Cutting Plan** reads through `door_cutting_order_plan_workspace_api.js` and keeps its document-scoped state in `door_cutting_order_plan_workspace_state.js` using the framework-neutral `door_cutting_order_workspace_store.js`.
3. **Costing** reads through `door_cutting_order_cost_workspace_api.js` and keeps its document-scoped state in `door_cutting_order_cost_workspace_state.js` using the same store primitive.

Plan and Cost state must not use `frm.doc` business fields as mutable persistence
state. They may use the current form only for order identity, lifecycle integration,
and compatibility rendering while A5 migrates the existing presenters. Every async
load is bound to the document identity and a request token so a late response from a
previous order cannot repaint the current order. The server remains authoritative for
capabilities and all mutations.

The active special-shape documentation workspace is separately layered under
`special_shape_documentation/` (`domain`, `application`, `infrastructure`,
`presentation`). Its versioned document records the customer's explanatory image,
annotations, dimensions, templates and smart-pen strokes. The
`drawing/special_shape_facade.js` integration entry point routes to the standalone
workspace. Legacy V3/V4 editor assets have been removed.

### Local recovery overlay

ALMADINA-128 adds versioned, site/user/DCO-namespaced local checkpoints without
changing canonical persistence. `AlmdinaDocumentContext` remains the document
identity/freshness owner; `AlmdinaOrderRevisionUX` remains the EDIT-session owner;
Plan and Cost drafts remain in their existing `WorkspaceStore` instances and
`WorkspaceSyncCoordinator` remains the derived-workspace coordinator.

Recovery application modules create only the explicit v1 projections and own a
small status/revision state machine. Infrastructure modules alone access IndexedDB:
the draft store holds lightweight versioned envelopes and a separate asset store
holds Blob bytes referenced by asset ID. The presentation adapter registers exact
DCO field events, subscribes to the existing Plan/Cost `WorkspaceStore` mutation
notifications, batches local writes through `AlmdinaDocumentContext.scheduleFrame()`,
and requests a best-effort local flush on `visibilitychange`/`pagehide`.

This overlay never calls `frm.save()` and never uses arbitrary timeout readiness.
ALMADINA-129 restores only an explicitly selected NEW `DcoInputProjection` into the
current form while `RESTORING`: its framework-free application use case invokes a
presentation-owned Frappe hydration port, which then asks the existing measurement
owners to rebuild their UI once. It does not restore Plan/Cost/Invoice authority or change scanner,
Save, Cancel, or EDIT behavior. First-insert safety wraps the native explicit Save
with a stable hidden unique creation token and a narrow authorized reconciliation
query; it is not a second insert API. Cross-tab revision conflicts block the stale
native insert, and native failure/cancellation cleanup is bound to the originating
document state plus exact save attempt with bounded compare-and-set retry. The same
operation binding owns acknowledged-success cleanup, and a live session adopts the
persisted official state only at the same payload revision. A higher external
revision is a restore-required conflict, not an implicit payload synchronization.
Every checkpoint write is transactionally fenced against the revision that its
session last persisted, so coalesced mutations cannot leapfrog another tab. A
conflict from any foreground, scheduled, visibility, or pagehide flush quarantines
that form until explicit reopen/restore. `PENDING_RECONCILIATION` also fences out
higher checkpoint revisions, and confirmed-success cleanup compare-and-deletes only
the exact attempted revision/save marker; a mismatch retains the local draft/assets.
A stale discovery dialog uses the same revision/attempt fence for explicit Delete,
and a begin-attempt ownership conflict quarantines rather than adopting another
tab's pending state without its timestamp. Continue revalidates that displayed
revision/attempt before hydration. One mutually exclusive discovery action owns the
dialog at a time, and Continue/Delete completion also rechecks the source document
token before changing the dialog or initializing a session. A queued first mutation
is replayed if discovery fails safely, preserving the existing checkpoint behavior.
Native first Save is cancelled until discovery establishes a session and the user
explicitly saves again; frozen conflicted cards remain displayed discovery ownership
even when no actionable card remains. If no recovery session or dialog can be
established, native explicit Save remains fail-safe available; a failed explicit
Start New choice does not reopen discovery or delete retained drafts.
If hydration fails or reports incomplete, the provisional session and Save observer
are disposed, the creation token is cleared, and the discovery dialog retains Save
ownership without deleting the local draft.
The fail-open marker/checkpoint-storage path carries the retained ACTIVE attempt and
persisted `saved_revision` fences, which are replaced only when a new pending marker
is durably returned. The retained timestamp is cleanup evidence only; pending-state
failure ownership begins only after this operation durably creates its own marker.

### Special-shape manufacturing boundary

The editable drawing and the manufacturing payload have deliberately different
contracts and responsibilities:

1. `special_shape_documentation` owns `almdina.special-shape-documentation` version 1 in `special_shape_drawing_json`.
2. Documentation is explanatory only and never projects, infers or mutates manufacturing geometry.
3. `special_shape_geometry_json` remains the production contract: version 1, `kind: "polygon"`, `units: "cm"`, with `blank_width_cm`, `blank_length_cm` and ordered polygon points.
4. The existing special-shape geometry validator remains authoritative for raw-piece bounds, area, self-intersection and exact manufacturing validity.
5. Cutting-plan and DXF consumers read `special_shape_geometry_json`; plan fingerprints do not include documentation images, notes or drawing elements.
6. Saving documentation does not mark the cutting plan stale. Exact geometry changes retain their existing invalidation and price rules.

Do not reconstruct manufacturing geometry from documentation strokes, templates,
images, canvas pixels or presentation state.

### Extra-door commercial boundary

`Extra` is a rectangular customer requirement, not a special-shape geometry type.
`Double Edge Banding` (`دبل قشاط`), `Liner`, and recessed-handle cutout invalidate
Cost only. `Full Door Double` (`دبل كامل الدرفة`) invalidates Plan + Cost because it
doubles physical cut quantity without changing the stored customer `qty`. Changing
the piece type itself retains the normal Plan + Cost impact.
Pricing is calculated by the server Domain from factory settings and original
quantity. The child row stores protected unit/total snapshots so later factory-price
changes do not rewrite historical orders. A `Special` door never carries Extra flags:
e.g. a special door with Liner records Liner in notes/drawing and uses its inclusive
custom special price.

The measurement type cell remains the native HTML `select` used by the table. The
visible Arabic order is `عادية / خاصة / زاوية / Extra`; the persisted values remain
`Regular / Special / Clipped Corner / Extra` according to the existing DocType
contract. Selecting `Extra` opens a small feature-owned multi-select flyout anchored
to that row for `دبل قشاط`, `دبل كامل الدرفة`, `Liner`, and recessed-handle cutout. A compact Extra-only
button reopens the flyout for an existing Extra row. The add-on module does not own or
reimplement the general piece-type menu. It owns only Extra add-on presentation,
document cleanup, focus, and flyout positioning; `AlmdinaTablePerformanceUX` remains
the owner of in-place row materialization/model mutation so changing a type never
rebuilds the table.

## Frontend asset manifest

`almdina_erp/frontend_assets.py` is the single owner of global frontend assets,
DocType JavaScript assets, and DocType list JavaScript assets. `hooks.py` only
re-exports those Frappe hook variables; it must not duplicate their path lists.

Asset ordering is runtime-significant. Ownership changes must preserve the intended
runtime dependency order and must update the regression contracts that freeze it.

The special-shape geometry module and shape-output contract are global drawing
primitives. They are loaded once through `app_include_js` and are intentionally not
re-evaluated through the Door Cutting Order `doctype_js` bundle.

## Explicit dual-load allowlist

A path may exist in both `app_include_js` and the Door Cutting Order `doctype_js`
only when the duplication is intentional and covered by a regression contract. The
current allowlist is exactly:

- `permission_context.js`: global permission bootstrap plus form-level refresh safety.
- `input_stability.js`: app-wide input protection plus the intentionally last order-form guard.
- `door_cutting_order/cutting_plan/secure_dxf_export.js`: shared export availability; guarded by `__almdinaSecureDxfExportLoaded`.
- `door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js`: shared drawing-plan integration; guarded by `AlmdinaDrawingPlanUX`.

No additional dual-loaded asset may be introduced without an explicit architectural
reason, idempotency where applicable, and a contract update.

## Approved public entry points outside the feature tree

- `public/css/door_cutting_order_responsive.css` and `public/css/door_cutting_order_extra_addons.css` are scoped global style entries and remain intentionally outside the JavaScript feature folders.
- Shared application-wide JavaScript such as `permission_context.js`, `input_stability.js`, `responsive_device.js`, and the shared shell remains at `public/js/` because it is not owned only by Door Cutting Order.

There are no active root-level `public/js/door_cutting_order_*.js` entry points after
Stage 9. Order form and list behavior must live under the feature owners above.

## Change rules

1. Put new behavior under exactly one feature owner.
2. Do not combine ownership/path moves with unrelated business-logic changes.
3. Server capabilities remain the authority; frontend visibility is not authorization.
4. Document-scoped timers, observers and async rendering must stay under the document-context lifecycle.
5. Existing product contracts must be updated to the current owner, never weakened to make a change pass.
6. Treat asset order and the dual-load allowlist as frozen contracts unless a deliberate dependency change proves otherwise.
7. Run Static, Security and Frappe v16 Integration gates for frontend architecture changes.

### Measurement surface readiness

`door_cutting_order_operator_ux.js` owns the base measurement HTML. Every base render
is handed to `AlmdinaMeasurementLifecycle`, which synchronously runs the registered
measurement/edge presentation owners and stamps readiness for the current document
generation. The same lifecycle registers `measurement-table` with
`AlmdinaDocumentContext`: a missing/cleared shell is rebuilt through the Operator and
a late feature registration invalidates the old readiness stamp until one keyed final
reconciliation completes. The existing measurement-resilience observer also asks this
surface owner to recover when the HTML field is cleared; it does not introduce another
observer. A partially malformed shell uses the Operator's explicit forced-replacement
path so its normal identical-HTML cache cannot keep broken markup; that path restores
the active measurement control and table/page scroll. Recovery is document-current and
idempotent; it must not call a broad form refresh, rebuild business state, or add polling
timers.
