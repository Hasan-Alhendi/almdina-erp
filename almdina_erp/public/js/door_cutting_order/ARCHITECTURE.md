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

The complex drawing editor remains separately layered under `door_drawing_v3/`
(`domain`, `application`, `infrastructure`, `presentation`).

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
