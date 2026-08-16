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

Status: ready for final CI validation.

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
