# Backend Legacy Migration — Stage 11

Stage 11 executes the migration plan frozen by `backend_legacy_inventory.json`.
The Stage 10 inventory remains an immutable audit baseline. Completed removals are
recorded in `almdina_erp/backend_legacy_migrations.json`.

## Safety rules

- Migrate consumers before deleting a compatibility source.
- Keep the canonical Frappe DocType controller base even when its old business implementation is being slimmed.
- Preserve historical public HTTP routes until their compatibility contract is explicitly retired.
- Keep retired product routes fail-closed while obsolete implementation modules are removed.
- Record Stage 11 discoveries explicitly rather than rewriting the Stage 10 audit.
- Close each batch only after Static, Security, and Frappe v16 Integration are green on the same final SHA.

## Batch 1 — Alternate Door Cutting Order controller chain

Status: closed on `fca574cfbec79c8fc61d027c040088e0995e94e1`.

Removed `door_cutting_order_fast.py`, `door_cutting_order_text_board.py`,
`door_cutting_order_domain.py`, `door_cutting_order_costing.py`, and
`door_cutting_order_plan.py`. Canonical ownership remains in the thin Frappe
override, the required base DocType controller, and focused Application/Frappe
save, costing, and plan adapters.

## Batch 2 — Cutting imports

Status: closed on `342103d52c35c0eb01ffbb0944526ecefeb0563c`.

All in-repository runtime consumers use the canonical pure cutting Domain. The
historical cutting import facades remain only for external/Python compatibility,
and architecture scans reject new internal dependencies on them.

## Batch 3 — Cutting Plan mixed service split

Status: closed on `e4db34e22b34cc1b85d136e7f706cd4353d16b62`.

Cutting Plan snapshot creation, approval, and production freeze persistence moved
to `cutting_plan_snapshot_service.py`. `cutting_plan_service.py` remains a thin
compatibility facade for historical Python and whitelisted API names, with no
Cutting Plan persistence ownership.

## Batch 4 — Shop Floor transitional production boundary

Status: closed on `a482920f3d4d40a96b59c4125ac8fb10428e00b3`.

Stage bootstrap and order-status synchronization moved to focused owners, and
lifecycle event persistence uses `production_event_repository.py` directly.
`production_service.py` remains only as a backward-compatible/fail-closed facade.
Static architecture scans reject internal runtime dependencies on it.

## Batch 5 — Replacement legacy implementation

Status: closed on `0354bb4604874a7293f8bb338c0d39ce8bbba429`.

Removed `services/replacement_cancellation_service.py`. The current replacement
workflow remains owned by `replacement_service.py` and focused boundaries. The
historical HTTP path remains frozen in `override_whitelisted_methods` and routes
to `legacy_endpoint_service.cancel_legacy_replacement`, which rejects retired
stock-reversal semantics and delegates supported cancellation to the current
replacement facade.

## Batch 6 — Retired Stock / Remnant product implementation

Status: ready for final CI validation.

Removed the eight Stage 10 legacy product modules:

- `actual_consumption_reversal.py`
- `actual_consumption_service.py`
- `performance_service.py`
- `preflight_service.py`
- `remnant_service.py`
- `settings_access_service.py`
- `stock_availability_service.py`
- `stock_service.py`

Also removed two Stage 11 discoveries that were no longer referenced by the
active Shop Floor command path:

- `infrastructure/frappe/stock_execution_gateway.py`
- `infrastructure/frappe/remnant_execution_gateway.py`

The historical Stock/Remnant HTTP routes remain mapped to
`legacy_endpoint_service.retired_product_endpoint` and therefore fail closed.
`order_revision_activation.py` keeps the historical material-activity check as a
revision safety boundary but no longer mutates retired stock/remnant reservations;
its legacy release fields remain present as empty values. The historical Order
Stock Availability report keeps its operational report permission guard and then
fails closed instead of importing the retired Stock service.

Static contracts assert that all ten implementation paths are absent, reject any
runtime Python references to their module paths, and confirm the two removed
Shop Floor execution gateways cannot silently return.
