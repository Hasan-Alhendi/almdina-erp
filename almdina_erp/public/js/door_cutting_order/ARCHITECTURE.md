# Door Cutting Order frontend architecture

The active Door Cutting Order frontend is organized here by feature ownership.
Stage 9 established these boundaries without mixing path ownership changes with
business-logic rewrites.

## Boundaries

- `core/`: document identity/lifecycle, revision mode, global action capability guards, toolbar stability.
- `order_entry/`: order defaults and data-entry behavior.
  - `measurements/`: row entry, keyboard flow, measurement toolbar/resilience/performance.
  - `edge_banding/`: edge selection, profiles, colors and derived cut dimensions.
- `cutting_plan/`: plan rendering, controls, tabs/surface, drawing-plan and DXF approval/export coordination.
- `costing/`: cost presentation, cost capabilities and customer financial actions.
- `printing/`: print identity/theme/presenters and printable shape/document composition.
- `production/`: shop-floor behavior owned by the order form.
- `responsive/`: order header/mobile-card adaptations.
- `drawing/`: facade/integration for special-shape drawing and clipped-corner behavior.
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

- `public/css/door_cutting_order_responsive.css` is the global responsive style entry point and remains intentionally outside the JavaScript feature folders.
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
