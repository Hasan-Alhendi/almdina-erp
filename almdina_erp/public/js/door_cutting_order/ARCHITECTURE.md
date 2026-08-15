# Door Cutting Order frontend architecture

This directory is the migration target for the active Door Cutting Order frontend.
The refactor is intentionally behavior-preserving: files move by feature ownership
before any implementation cleanup or consolidation happens.

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
- `drawing/`: facade/integration for special-shape drawing.
- `list_view/`: Door Cutting Order list presentation, search, status/stage presentation and list quick actions.

The complex drawing editor remains separately layered under `door_drawing_v3/`
(`domain`, `application`, `infrastructure`, `presentation`).

## Frontend asset manifest

`almdina_erp/frontend_assets.py` is the single owner of global frontend assets,
DocType JavaScript assets, and DocType list JavaScript assets. `hooks.py` only
re-exports those Frappe hook variables; it must not duplicate their path lists.

Asset ordering is runtime-significant. Reorganizing ownership must preserve the
existing sequence exactly unless a separate behavior change explicitly changes a
dependency and updates the relevant regression contracts.

## Migration rules

1. Move one feature group at a time and preserve script contents and load order first.
2. Do not combine a path move with business-logic changes.
3. Server capabilities remain the authority; frontend visibility is not authorization.
4. Document-scoped timers, observers and async rendering must stay under the document-context lifecycle.
5. Existing product contracts must be updated to the new owner, never weakened to make a move pass.
6. Run Static, Security and Frappe v16 Integration gates after every completed migration batch.

## First migration batch: core

The first batch owns these existing scripts without changing their behavior:

- `door_cutting_order_document_context.js`
- `door_cutting_order_action_permission_guard.js`
- `door_cutting_order_toolbar_stability_ux.js`
- `door_cutting_order_revision_ux.js`
- `order_lifecycle.js`

During the first move their basenames stay unchanged; only their directory changes to
`door_cutting_order/core/`. Renaming or consolidating them, if useful, is a later step.
