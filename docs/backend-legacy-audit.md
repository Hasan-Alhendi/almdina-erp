# Stage 10 — Backend Legacy Audit

Baseline: `Develop@453c000240b574b9739fc46ba392c17c42b766c9`

This audit classifies backend legacy-risk surfaces before Stage 11 changes any runtime behavior. The machine-readable source of truth is `almdina_erp/backend_legacy_inventory.json`; the CI contract is `almdina_erp/tests/test_backend_legacy_audit_contract.py`.

## Classification rule

Classification is by **runtime responsibility and public surface**, not by filename age.

- **Active** — canonical runtime owner that new code should use.
- **Compatibility** — intentionally preserves an old HTTP/Python path while delegating to a canonical owner or failing closed.
- **Legacy** — migration/splitting target for Stage 11. It may still be required today and must not be deleted merely because it is classified legacy.
- **Dead** — requires positive proof of zero hook, HTTP, Python-import and test consumers. No backend source met that bar in Stage 10.

## Result

| Classification | Count | Meaning |
|---|---:|---|
| Active | 8 | Canonical anchors inspected by the audit |
| Compatibility | 7 | Intentional public/import compatibility boundaries |
| Legacy | 16 | Stage 11 migration or split targets |
| Dead | 0 | Nothing is safe to delete without additional migration evidence |

The audit is deliberately scoped to known backend compatibility, duplicate-controller, mixed-service and retired-product boundaries. It is not a claim that every ordinary backend module is listed.

## Critical findings

### 1. The active Door Cutting Order controller is already thin, but its Frappe base is still required

`door_cutting_order_controller.DoorCuttingOrderController` is the sole active `override_doctype_class`. Its `validate()` delegates to the Application use case through `FrappeDoorCuttingOrderSaveGateway`.

However, Frappe requires the override to subclass the canonical DocType controller, so `door_cutting_order.py` cannot simply be deleted. It is a **Legacy migration target** because it still contains older save, plan and pricing implementations that the new gateway has superseded. Stage 11 must slim it while retaining the framework-compatible base class and any still-required inherited methods.

The alternate controller chain:

- `door_cutting_order_fast.py`
- `door_cutting_order_text_board.py`
- `door_cutting_order_domain.py`

is not the active override. It remains a compatibility/migration concern and should be removed only after remaining Python imports and behavior parity are proven.

### 2. Cutting algorithms already have canonical Domain ownership

New cutting code belongs to `domain/cutting` and `infrastructure/cutting/domain_engine.py`.

The following are compatibility-only import paths:

- `services/cutting_engine.py`
- `services/advanced_cutting_optimizer.py`
- `infrastructure/cutting/legacy_engine.py`

They must not regain algorithms. Stage 11 should migrate remaining imports to the Domain/canonical adapter and remove these aliases only when zero consumers remain.

### 3. `cutting_plan_service.py` is a mixed boundary, not a dead service

The module still owns active plan snapshot persistence (`create_plan_from_order`, plan approval/locking support), but it also exposes historical lifecycle HTTP functions such as submit/approve/send/lock which hooks route to focused canonical services.

Stage 11 must first separate plan persistence from compatibility endpoints. Deleting the module as one unit would remove active behavior.

### 4. Shop-floor legacy paths are intentionally preserved

`services/shop_floor_service.py` is a small lazy compatibility facade. Historical routes are redirected by `override_whitelisted_methods` to focused query, command, DXF, approval, dispatch and revision services.

`infrastructure/frappe/shop_floor_gateway.py` is also a compatibility facade for old Python imports. Removed role gates deliberately fail closed rather than silently authorizing an old caller. Its historical `create_stage` compatibility semantics also preserve an implicit Created event for legacy callers.

Stage 11 should migrate Python callers symbol-by-symbol. Public route compatibility must remain stable until the old routes are formally retired.

### 5. Replacement has a deliberate compatibility facade

`services/replacement_service.py` owns no replacement business logic; it lazy-delegates to focused creation, approval, execution and completion services. Keep it until existing clients no longer use its historical API paths.

### 6. Retired inventory/remnant endpoints are not evidence of dead modules by themselves

Inventory/remnant/preflight functionality is outside the active product scope. Old HTTP routes are intentionally mapped to `legacy_endpoint_service.retired_product_endpoint`, which fails closed.

The audited retirement set includes actual consumption, stock checks/execution, remnants, stock settings, benchmark/preflight, order-creation HTTP endpoints, and pause/resume stage endpoints.

These modules become deletion candidates only after Stage 11 proves that no active Python imports or deployment tooling still needs them. The old HTTP route must continue to fail closed even if the original implementation file is removed.

### 7. No backend file was classified Dead

This is intentional. A file is not Dead merely because the current UI does not call it or because a hook redirects its endpoint. Stage 11 must establish all four conditions before deletion:

1. no Frappe hook/runtime registration,
2. no supported HTTP caller,
3. no Python import caller,
4. no contract/test dependency that represents required compatibility.

## Frozen public compatibility contract

The inventory freezes the old-to-canonical mappings currently present in `hooks.py`, including:

- Cutting Plan legacy lifecycle routes → focused lifecycle/approval/review/dispatch/drawing services.
- Special price legacy route → `cost_permission_service`.
- Legacy DXF validation route → `dxf_export_service`.
- Shop-floor legacy query routes → `shop_floor_query_service`.
- Shop-floor drawing routes → focused DXF/drawing approval services.
- Shop-floor commands → `shop_floor_commands`, `order_dispatch_service`, and `order_revision_service`.
- Historical production start/finish → safe legacy adapters backed by canonical shop-floor commands.
- Retired inventory/remnant/preflight routes → explicit fail-closed retired endpoint.

CI must fail if any audited old route silently points back to an old implementation.

## Stage 11 execution order

1. **Controller chain** — identify exactly which inherited methods the active Frappe controller still needs, migrate those responsibilities to focused adapters/application code, slim the canonical base, then remove the alternate fast/text/domain chain when imports reach zero.
2. **Cutting imports** — replace internal imports of `cutting_engine`, `advanced_cutting_optimizer`, and `legacy_engine` with Domain/canonical imports; delete facades only after zero-consumer proof.
3. **Cutting-plan boundary** — split active plan snapshot persistence from historical HTTP lifecycle compatibility.
4. **Shop floor** — migrate Python imports off `shop_floor_service` and `shop_floor_gateway`; keep old HTTP routes mapped to canonical services during migration.
5. **Replacement** — move clients to focused replacement services and retire the facade only after route usage reaches zero.
6. **Retired product modules** — prove zero internal imports, preserve fail-closed old HTTP routing, then remove obsolete stock/remnant/preflight implementations.

Every Stage 11 batch must keep Static, Security and Frappe v16 Integration green before the next deletion/migration group starts.

## Stage 10 safety statement

Stage 10 changes no application runtime, business rule, permission rule, DocType behavior or API target. It adds only the audit inventory, architecture documentation and a CI contract that freezes the current safe routing/classification before Stage 11 begins.
