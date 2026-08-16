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
- Close each batch only after Static, Security, and Frappe v16 Integration are
  green on the same final SHA.

## Batch 1 — Alternate Door Cutting Order controller chain

Status: implemented; CI validation required before closure.

Removed:

- `door_cutting_order_fast.py`
- `door_cutting_order_text_board.py`
- `door_cutting_order_domain.py`

Canonical ownership remains:

- `door_cutting_order_controller.py` — only `override_doctype_class` entry point.
- `door_cutting_order.py` — canonical Frappe DocType base required by the
  framework subclass contract.
- `application/orders/process_order_save.py` — save orchestration.
- `infrastructure/frappe/orders/save_gateway.py` and focused adapters — Frappe
  adaptation and persistence access.

The migration contract rejects any runtime Python reference to the removed
modules/classes so the old inheritance branch cannot silently return.
