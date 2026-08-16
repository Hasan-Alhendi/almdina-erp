# Backend Legacy Migration — Stage 11

Stage 11 executed the migration plan frozen by `backend_legacy_inventory.json`.
The Stage 10 inventory remains an immutable audit baseline; completed migrations
and removals are recorded in `almdina_erp/backend_legacy_migrations.json`.

## Safety rules

- Migrate consumers before deleting a compatibility source.
- Keep the canonical Frappe DocType base even when superseded business logic is removed from it.
- Preserve historical public HTTP routes until their compatibility contract is explicitly retired.
- Keep retired product routes fail-closed while obsolete implementation modules are removed.
- Record Stage 11 discoveries explicitly rather than rewriting the Stage 10 audit.
- Close each batch only after Static, Security, and Frappe v16 Integration are green on the same final SHA.

## Batch 1 — Alternate Door Cutting Order controller chain

Status: closed on `fca574cfbec79c8fc61d027c040088e0995e94e1`.

Removed the retired Fast/Text Board/Domain controller chain plus the discovered
Costing/Plan alternate controllers. The active Frappe override remains
`DoorCuttingOrderController` and save ownership is delegated to focused
Application/Infrastructure boundaries.

## Batch 2 — Cutting imports

Status: closed on `342103d52c35c0eb01ffbb0944526ecefeb0563c`.

In-repository runtime consumers were migrated away from the historical cutting
import modules. The old cutting import facades remain thin only for external
Python compatibility, while runtime architecture scans reject new internal
dependencies on them.

## Batch 3 — Cutting Plan mixed service split

Status: closed on `e4db34e22b34cc1b85d136e7f706cd4353d16b62`.

Cutting Plan snapshot creation, approval, and production freeze persistence moved
to `cutting_plan_snapshot_service.py`. `cutting_plan_service.py` remains a thin
compatibility facade for historical Python and whitelisted API names, with no
Cutting Plan persistence ownership.

## Batch 4 — Shop Floor transitional production boundary

Status: closed on `a482920f3d4d40a96b59c4125ac8fb10428e00b3`.

Stage bootstrap, order-status synchronization, and production event persistence
use focused owners directly. `production_service.py` remains only as a
backward-compatible/fail-closed facade, and Static architecture scans reject
internal runtime dependencies on it.

## Batch 5 — Replacement legacy implementation

Status: closed on `0354bb4604874a7293f8bb338c0d39ce8bbba429`.

Removed `services/replacement_cancellation_service.py`. The supported replacement
workflow remains owned by the current replacement facade/focused services. The
historical HTTP path remains frozen to `cancel_legacy_replacement`, which rejects
retired stock-reversal semantics.

## Batch 6 — Retired Stock / Remnant product implementation

Status: closed on `a593a46d636d349e416b74d1162837b885e21cbb`.

Removed the eight Stage 10 product modules:

- `actual_consumption_reversal.py`
- `actual_consumption_service.py`
- `performance_service.py`
- `preflight_service.py`
- `remnant_service.py`
- `settings_access_service.py`
- `stock_availability_service.py`
- `stock_service.py`

Also removed two Stage 11 discoveries that had no active Shop Floor command
consumer:

- `infrastructure/frappe/stock_execution_gateway.py`
- `infrastructure/frappe/remnant_execution_gateway.py`

Historical Stock/Remnant routes remain fail-closed through
`legacy_endpoint_service.retired_product_endpoint`. Revision activation keeps the
material-activity safety gate but no longer mutates retired stock/remnant
reservations. The historical Order Stock Availability report preserves its
permission guard and then fails closed.

## Batch 7 — Historical Order Creation implementation

Status: closed on `6417c554f50b6caf2a1352bbb8c6c5fc74c62c90`.

`order_creation_service.py` no longer owns defaults, document creation, or any
Frappe runtime logic. It is retained only as a documented, logic-free tombstone
for the historical module path. Static contracts prove zero runtime imports of
that module, while both old RPC names remain mapped to the fail-closed retired
product boundary.

## Batch 8 — Canonical Door Cutting Order base slimming

Status: closed on `6cb20b00abdd92434a2f2ca5f5d4c3fd65753a79`.

The Frappe-required `door_cutting_order.py` base was reduced from the historical
monolithic implementation to a small framework base and compatibility delegates.
Save orchestration belongs to `process_order_save` and the save gateway; cutting
plan work belongs to the focused plan adapter/Application cutting layer; costing,
piece policy, and document validation belong to their focused adapters.

During this slimming audit, the exact special-shape polygon validation dependency
that had previously lived in the monolithic base was exposed. It was preserved in
the canonical `FrappeOrderPiecePolicyAdapter`, including geometry-change price
invalidation/documentation behavior, rather than being copied back into the base.
Static, Security, and full Frappe v16 Integration all passed on the same Batch 8
SHA.

## Stage 11 closure

Stage 10 classified exactly 16 backend paths as `legacy`. Stage 11 closes that
inventory with no ambiguous legacy owner left:

- 12 Stage 10 legacy paths are removed.
- 4 Stage 10 paths are intentionally retained as framework/compatibility
  boundaries:
  - `doctype/door_cutting_order/door_cutting_order.py` — required slim Frappe base.
  - `services/cutting_plan_service.py` — thin Cutting Plan compatibility facade.
  - `services/production_service.py` — thin production compatibility facade.
  - `services/order_creation_service.py` — logic-free historical tombstone.
- 4 additional Stage 11 discoveries were recorded and removed rather than being
  silently folded into the Stage 10 baseline.
- Retired HTTP product surfaces remain fail-closed.
- No removed backend legacy implementation is restored to satisfy tests; stale
  contracts were redirected to the current canonical owner.

`test_backend_legacy_stage11_closure.py` freezes this final partition and the
required characteristics of each retained boundary. Stage 12 can therefore focus
on Permissions & Authorization Hardening without carrying unresolved Stage 11
backend ownership work.
