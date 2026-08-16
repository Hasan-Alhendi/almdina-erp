# Backend Legacy Migration — Stage 11

Stage 11 executes the migration plan frozen by `backend_legacy_inventory.json`.
The Stage 10 inventory remains an immutable audit baseline. Completed removals are
recorded in `almdina_erp/backend_legacy_migrations.json`.

## Safety rules

- Migrate consumers before deleting a compatibility source.
- Keep the canonical Frappe DocType controller base even when its old business
  implementation is being slimmed.
- Preserve historical public HTTP routes until their compatibility contract is
  explicitly retired.
- Keep retired product routes fail-closed while obsolete implementation modules
  are removed.
- Record Stage 11 discoveries explicitly rather than rewriting the Stage 10 audit.
- Close each batch only after Static, Security, and Frappe v16 Integration are
  green on the same final SHA.

## Batch 1 — Alternate Door Cutting Order controller chain

Status: closed on `fca574cfbec79c8fc61d027c040088e0995e94e1`.

Removed:

- `door_cutting_order_fast.py`
- `door_cutting_order_text_board.py`
- `door_cutting_order_domain.py`
- `door_cutting_order_costing.py`
- `door_cutting_order_plan.py`

The first three files were identified in the Stage 10 audit. During Frappe app
regression tests, the migration contract exposed two more members of the same
inactive inheritance branch: `CostingDoorCuttingOrder(DomainDoorCuttingOrder)`
and `PlanDoorCuttingOrder(CostingDoorCuttingOrder)`. They are recorded as Stage
11 discoveries in the migration ledger before removal.

Canonical ownership remains:

- `door_cutting_order_controller.py` — only `override_doctype_class` entry point.
- `door_cutting_order.py` — canonical Frappe DocType base required by the
  framework subclass contract.
- `application/orders/process_order_save.py` — save orchestration.
- `infrastructure/frappe/orders/save_gateway.py` — composition root for focused
  order adapters.
- `infrastructure/frappe/orders/costing_adapter.py` — active costing adapter.
- `infrastructure/frappe/orders/plan_adapter.py` and
  `cut_dimension_plan_adapter.py` — active plan adapters.

The migration contract rejects any runtime Python reference to all five removed
modules/classes so the old inheritance branch cannot silently return. Existing
payload, costing and plan architecture tests now assert against the active
Application/Infrastructure owners instead of the retired controller classes.

## Batch 2 — Cutting imports

Status: closed on `342103d52c35c0eb01ffbb0944526ecefeb0563c`.

All in-repository runtime consumers of the historical cutting import facades now
use the canonical pure cutting Domain directly. The migration touched imports
only; optimizer calls, arguments, geometry, scoring and costing behavior were not
changed.

Migrated runtime consumers:

- `doctype/door_cutting_order/door_cutting_order.py`
- `services/performance_service.py`
- `services/production_settings_service.py`
- `services/remnant_planning.py`

Canonical ownership:

- `domain/cutting/__init__.py` — public pure-Domain cutting API.
- `infrastructure/cutting/domain_engine.py` — canonical Application engine adapter.

Compatibility preserved intentionally:

- `services/cutting_engine.py`
- `services/advanced_cutting_optimizer.py`
- `infrastructure/cutting/legacy_engine.py`

Those compatibility modules remain thin import aliases for historical/external
Python callers. Runtime architecture tests scan every production Python source
and reject any new internal dependency on them, while separate compatibility
tests ensure the facades themselves remain behavior-free.

## Batch 3 — Cutting Plan mixed service split

Status: closed on `e4db34e22b34cc1b85d136e7f706cd4353d16b62`.

The historical `cutting_plan_service.py` previously mixed two responsibilities:
Cutting Plan snapshot persistence/freeze behavior and historical lifecycle API
compatibility. The persistence responsibility now has one focused owner:
`cutting_plan_snapshot_service.py`.

Moved without changing the business behavior:

- `create_plan_from_order`
- `approve_plan`
- production-plan freeze behavior, now named `lock_order_for_production`

The focused snapshot owner still performs the same geometry validation, special
shape/documentation checks, special-price gate, snapshot persistence, approval
supersession, cost snapshot, selected system/custom plan validation, and order
field updates.

`drawing_approval_service.py` now calls the focused snapshot owner directly.

Compatibility preserved intentionally in `cutting_plan_service.py`:

- Python delegates: `create_plan_from_order`, `approve_plan`, and historical
  `_lock_order_for_production`.
- Historical whitelisted lifecycle endpoints: submit, approve, reject,
  pre-dispatch validation, and cutting-plan lock. Hooks continue routing those
  HTTP paths to their focused capability-protected services.

Architecture contracts enforce that the compatibility facade contains no Cutting
Plan persistence (`frappe.new_doc`, `plan.insert`, `frappe.db.set_value`) and that
product-scope, geometry, drawing approval, and special-price/documentation
contracts inspect the focused snapshot owner instead of the facade.

## Batch 4 — Shop Floor transitional production boundary

Status: ready for final CI validation.

The historical `production_service.py` previously mixed three concerns: legacy
stage bootstrap, order-status synchronization, and retired/public compatibility
endpoints. Those responsibilities are now separated while preserving behavior.

Focused owners:

- `production_stage_bootstrap_service.py` — legacy-compatible default stage
  creation with the same pending/auto-complete semantics.
- `order_status_sync_service.py` — canonical order-status synchronization from
  current production stage, replacements, and lifecycle state.
- `infrastructure/frappe/production_event_repository.py` — production-stage event
  persistence used by lifecycle cancellation.

Migrated internal consumers:

- `shop_floor_service.py`
- `order_lifecycle_service.py`
- `replacement_cancellation_service.py`
- `replacement_status_service.py`

`production_service.py` remains only as a backward-compatible facade. It exposes
the historical Python names as delegates and keeps legacy HTTP stage endpoints
fail-closed/protected through the existing legacy endpoint boundary.

A Static architecture scan now rejects any internal runtime import of
`services.production_service`. This prevents the transitional facade from
regaining business ownership while preserving compatibility for external callers.
