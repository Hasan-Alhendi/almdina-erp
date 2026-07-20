# Almdina ERP v1.0 — Implementation Traceability Matrix

الحالات المستخدمة:

- **Implemented — UAT Pending**: المنطق موجود في الكود، لكن لا يجوز اعتباره مقبولًا نهائيًا قبل الاختبار على Frappe/ERPNext/CNC الحقيقي.
- **Partially Implemented**: جزء من المتطلب موجود وما يزال Code Gap واضح.
- **UAT / Environment Only**: لا يحتاج منطق منتج إضافيًا حاليًا، لكن إثباته يتطلب بيئة فعلية.

هذه الوثيقة لا تغيّر Scope ولا معايير القبول في `REQUIREMENTS_v1.0.md`.

## Orders / Pieces / Edge Banding

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Order master data + board snapshot | Implemented — UAT Pending | `Door Cutting Order`, MDF Item custom fields, `order_defaults_service.py` | Verify Item defaults/API/import behavior on Bench |
| Piece dimensions/qty/notes/rotation | Implemented — UAT Pending | `Door Cutting Order Detail` + server validation | Legacy side-by-side regression |
| Area/edge calculations | Implemented — UAT Pending | `door_cutting_order.py` | Numeric sample reconciliation |
| Header Edge default + row override | Implemented — UAT Pending | order calculation + row snapshots | Verify UI/stock mapping |
| 12 baseline edge types/rates | Implemented — UAT Pending | `install.py`, `Edge Banding Type` | Verify exact names/rates on migrated site |
| User-managed edge prices survive migrate | Implemented — UAT Pending | `install.seed_edge_banding_types()` only backfills missing structure | Upgrade test |

## Optimization / Validation

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| 17 algorithms + Auto | Implemented — UAT Pending | `services/cutting_engine.py` | Benchmark + legacy comparison |
| Kerf / Trim / rotation | Implemented — UAT Pending | engine + order validation | Physical sample test |
| Bounds / overlap / count / orientation | Implemented — UAT Pending | engine validator + `export_validation_service.py` | Fault-injection test on Bench |
| Material/color/thickness source identity | Implemented — UAT Pending | Cutting Plan Source snapshots, remnant planning, DXF validator | Historical/migration test |
| Validation result + timestamp | Implemented — UAT Pending | `validation_status`, `validation_errors`, `validated_on` | Migrate old plans |
| Performance target | UAT / Environment Only | `performance_service.benchmark_order_cutting_engine()` | Measure ≤5s target on reference production environment |

## Cutting Plan / Revision / Immutability

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Plan separated from HTML | Implemented — UAT Pending | `Cutting Plan`, Source, Piece child tables | Bench schema sync |
| One approved historical plan reference | Implemented — UAT Pending | `approved_plan`, plan revisions/status transitions | Concurrent approval UAT |
| Immutable approved plan | Implemented — UAT Pending | controller guards + approved preview source | Direct API permission test |
| Replacement Mini Plan | Implemented — UAT Pending | `replacement_plan_service.py` + independent replacement validator | Full replacement UAT |

## Waste / Remnants

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Full boards distinguished from remnants | Implemented — UAT Pending | Cutting Plan Source `source_type` | Mixed-source job test |
| Reusable vs Scrap | Implemented — UAT Pending | persisted reconciliation in `remnant_service.py` | Physical offcut comparison |
| `Waste = Reusable + Scrap` | Implemented — UAT Pending | reconciliation invariant + regression tests | Production sample |
| Remnant status/lifecycle | Implemented — UAT Pending | `Board Remnant` | Concurrency UAT |
| Remnant-first optimization | Implemented — UAT Pending | `remnant_planning.py` | Multiple matching remnants test |
| Exact identity match | Implemented — UAT Pending | Item + Material + Color + Thickness | Same Item/different color/thickness test |
| Parent lineage | Implemented — UAT Pending | `parent_remnant` | Multi-generation remnant test |

## Stock / Reservation / Actual Consumption

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| No stock effect from preview | Implemented — UAT Pending | calculation services are side-effect free | Stock Ledger diff test |
| Optional reservation on approval | Implemented — UAT Pending | Material Reservation + Settings policy | ON/OFF UAT |
| Competing reservation awareness | Implemented — UAT Pending | `_active_reserved_qty` and row locks | Simultaneous-session UAT |
| Standard ERPNext Stock Entry | Implemented — UAT Pending | Material Issue/Receipt services | Ledger/accounting validation |
| Edge UOM conversion | Implemented — UAT Pending | stock service meter conversion | Real Item/UOM test |
| Planned vs Actual consumption | Implemented — UAT Pending | Actual reconciliation + variance child table | Issue/return UAT |
| Reverse actual variance | Implemented — UAT Pending | `actual_consumption_reversal.py` | Cancel/re-record UAT |
| Controlled order cancellation | Implemented — UAT Pending | lifecycle + cancellation wrapper | Stock dependency/repost UAT |

## Cost

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Planned cost snapshot | Implemented — UAT Pending | approved Cutting Plan cost fields | Price-change history test |
| Actual cost | Implemented — UAT Pending | `cost_service.py` | Report/screen reconciliation |
| Material variance | Implemented — UAT Pending | actual consumption services | Extra/returned stock valuation test |
| Edge variance historical rate | Implemented — UAT Pending | approved row `edge_rate_usd` snapshot | Master price-change regression |
| Remnant cost policy | Implemented — UAT Pending | Zero/Average Valuation/Configured Rate | Accounting policy sign-off |
| Replacement/internal failure cost | Implemented — UAT Pending | Replacement planned/actual loss | Customer charge protection test |

## Production / Incidents / Replacement

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Configurable routing | Implemented — UAT Pending | Production Routing master | Real routing assignment test |
| Start/Pause/Resume/Finish | Implemented — UAT Pending | production service + UI | Worker/session UAT |
| Working time excludes pauses | Implemented — UAT Pending | stage calculations | Timed scenario |
| Stage sequence enforcement | Implemented — UAT Pending | prerequisite check + controlled override | Permission test |
| Append-only stage events | Implemented — UAT Pending | Production Stage Event | Attempt edit/delete UAT |
| Incident per exceptional piece | Implemented — UAT Pending | Production Incident | Attachments/worker test |
| Replacement approval/start/complete | Implemented — UAT Pending | replacement services | End-to-end UAT |
| No order completion with open replacement | Implemented — UAT Pending | order status sync | Stage/replacement race test |

## Visual / Print / DXF

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Legacy visual plan | Implemented — UAT Pending | Door Cutting Order JS renderer | Side-by-side screenshots |
| Edge marks after rotation | Implemented — UAT Pending | renderer mapping | Physical orientation test |
| Variable-size remnant rendering | Implemented — UAT Pending | source-aware renderer | Mixed-source screenshot |
| Measurements print | Implemented — UAT Pending | legacy print + `Door Cutting Measurements` server Print Format | Browser/PDF test |
| Official server-side plan print | Implemented — UAT Pending | `Door Cutting Plan Official` Print Format | wkhtmltopdf/A4 pagination UAT |
| Approved print uses immutable Order Plan | Implemented — UAT Pending | approved preview isolation + server format | Replacement-plan coexistence test |
| DXF R12/mm/layers | Implemented — UAT Pending | secure DXF exporter | AutoCAD/Illustrator/CNC mandatory UAT |
| DXF server validation | Implemented — UAT Pending | `export_validation_service.py` | Corrupt-plan blocking test |
| DXF manifest | Implemented — UAT Pending | JSON manifest download | Traceability check |
| One safe DXF UI path | Implemented — UAT Pending | secure exporter removes legacy button asynchronously | Browser UAT |

## Permissions / Audit

| Requirement | Status | Implementation / Evidence | Remaining Validation |
|---|---|---|---|
| Role-based sensitive APIs | Implemented — UAT Pending | server role guards | Direct API tests per role |
| Cost hidden from workers | Implemented — UAT Pending | Permission Level fields | Desk/API permission UAT |
| Audit timestamps/users | Implemented — UAT Pending | Frappe tracking + stage events | Audit trail test |
| Stock/approval/replacement server enforcement | Implemented — UAT Pending | service guards | Attempt bypass by URL/API |

## Reports / Workspaces

Implemented reports:

1. Factory Operations Summary.
2. Factory Order Analysis.
3. Production Stage Performance.
4. Remnant Inventory.
5. Production Incidents and Replacements.
6. Order Stock Availability.
7. Board Usage Analysis.
8. Piece Size Usage Analysis.

Workspaces:

- Almdina ERP — daily operations.
- Almdina Reports — reporting entry point.

All report definitions remain **UAT Pending** until reconciled against source documents on a real site.

## Known Code / Configuration Gaps Still Open

1. **Authoritative new-order defaults for every creation path**: UI reads `Almdina ERP Settings`; real Bench/API/Import behavior must be verified so no static DocField default can override configured factory defaults. This remains a validation/code-cleanup item until tested and normalized on a real site.
2. **Legacy hardcoded UI language strings**: core/new workflows use translation functions, but the large legacy visual/print script still contains hardcoded Arabic strings. Conversion must be incremental with visual regression so the Baseline is not broken.
3. **Concurrent approval of the same order**: remnant/material races are protected, but same-order double-approval must be explicitly stress-tested and, if reproduced, protected with an order-row approval lock before Go-Live.
4. **Official A4 server PDF pagination**: Print Formats exist; wkhtmltopdf rendering must be checked with long/narrow sources and many pieces.
5. **Real ERPNext accounting behavior**: Material Issue/Receipt cancellation/repost dependencies require integration testing with the target Company/Warehouse/accounts.

## External Acceptance Gates

The following cannot be honestly marked Pass from source code review alone:

- `bench install-app` / `bench migrate` on Frappe/ERPNext v16.
- Permission matrix with real user accounts.
- Concurrent reservation/approval tests using simultaneous transactions.
- AutoCAD/Illustrator/CNC DXF tests and real mm scale.
- Browser/RTL/wkhtmltopdf print tests.
- 200-piece performance benchmark on reference server.
- Backup/Restore including attachments, Stock Ledger and remnant lineage.
- Signed Go-Live checklist in `UAT_v1.0.md`.
