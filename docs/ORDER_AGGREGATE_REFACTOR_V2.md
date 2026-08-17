# Order Aggregate Refactor V2

**Status:** Accepted target architecture / implementation in progress  
**Scope:** Door Cutting Order, Cutting Plan, Door Cutting Costing, customer quote flow  
**Branch:** `agent/refactor-order-aggregates-v1`

## 1. Decision

Almdina ERP will no longer treat `Door Cutting Order` as the persistence owner for order requirements, cutting-plan state, and financial state at the same time.

The target model has three explicit aggregates:

1. **Door Cutting Order** — customer requirements and production lifecycle.
2. **Cutting Plan** — optimizer settings, geometry, DXF, validation, revisions, and the selected production plan.
3. **Door Cutting Costing** — preliminary/approved price snapshots derived from one concrete Cutting Plan.

The operator may continue to see one Arabic-first workspace with tabs, but each tab uses its own document state and command boundary.

## 2. Ownership

### Door Cutting Order owns

- customer, order date/reference and notes;
- board description and commercial board dimensions;
- requested door/piece rows;
- edge-band selections and special-shape customer geometry;
- order revision/lifecycle;
- production routing, current stage and assignment;
- links to the current/approved plan only.

It does **not** own optimizer settings, plan JSON, DXF state, cost rates, cost totals or customer quote totals in the target model.

### Cutting Plan owns

- `source_type`: System or Uploaded DXF;
- immutable revision chain through `revision` + `based_on_plan`;
- Draft / Approved / Superseded / Cancelled lifecycle;
- `optimization_mode`, `machine_type`, `optimization_time_limit_sec`;
- `kerf_mm`, `trim_margin_mm`;
- calculation fingerprints and stale state;
- optimizer/quality metrics;
- source sheets and placed pieces;
- validated snapshot JSON;
- DXF file and DXF validation state;
- approval actor/time.

An Approved plan is immutable. Any later design change creates a new Draft revision. The previously Approved plan remains the production authority until another Draft is explicitly approved.

### Door Cutting Costing owns

- one link to the Door Cutting Order;
- one link to the exact Cutting Plan it prices;
- Preliminary / Approved / Superseded lifecycle;
- board/cutting rates;
- required board count copied from the plan;
- edge and special-shape financial lines;
- operational cost, customer quote total, internal loss and actual cost;
- audit actor/time.

Money is not stored inside operational plan snapshots in the target model.

## 3. User flow

### Order Entry

1. Create/edit Door Cutting Order requirements.
2. Save the order.
3. Select a **preliminary algorithm** in the unified workspace; the value belongs to the Draft Cutting Plan, not DCO.
4. Calculate the Draft System plan.
5. Generate a Preliminary Door Cutting Costing snapshot.
6. Print a preliminary customer quote clearly marked as preliminary.

### Designer

1. Open the same order workspace and select Cutting Plan.
2. Work on the current Draft plan or create a Draft revision from an Approved plan.
3. Edit advanced plan settings and/or upload a DXF plan according to capabilities.
4. Recalculate/validate.
5. Approve the selected plan.
6. Approval supersedes the previous Approved plan and generates an Approved costing snapshot.

### Production

Production reads **only the Approved Cutting Plan link**. A newer Draft cannot change production silently.

## 4. Permission direction

Target permission ownership:

- Order capabilities apply to Door Cutting Order.
- Planning/DXF capabilities apply to Cutting Plan.
- Cost/customer-document capabilities apply to Door Cutting Costing.
- Production capabilities remain on the production/order workflow boundary.

`Door Cutting Order.write` must never be required simply to edit a Draft Cutting Plan or a Costing snapshot.

## 5. Frontend direction

One workspace, three state owners:

```text
Door Cutting Order workspace shell
├── Order tab   -> Order API / order state
├── Plan tab    -> Cutting Plan API / plan state
└── Cost tab    -> Costing API / costing state
```

The shell may initially remain mounted inside the DCO form to preserve the high-quality order-entry grid, but Plan and Cost tabs must not use `frm.doc` as their mutable persistence state.

Each tab owns its own:

- API adapter;
- store/baseline/dirty state;
- edit/save/cancel session;
- loading/error/empty states;
- action visibility from server capability context.

## 6. Implementation slices

### A1 — Aggregate foundation

- Cutting Plan working/revision fields and lifecycle.
- Door Cutting Costing + Costing Line DocTypes.
- Pure lifecycle/use-case contracts and regression tests.

### A2 — Plan command migration

- Draft creation/revision commands.
- Plan-owned optimization calculation.
- DXF ownership moved to Cutting Plan.
- Approval switches only plan links; no full DCO save.

### A3 — Costing command migration

- Preliminary costing from Draft plan.
- Approved costing from Approved plan.
- Special-shape pricing moved out of order piece rows.
- Preliminary and approved customer-document commands.

### A4 — Thin Door Cutting Order

- Remove plan/cost fields from DCO and financial fields from DCO Detail.
- Order save validates customer requirements and derived cut dimensions only.
- Remove dual-plan compatibility and order-owned optimizer/cost adapters.

### A5 — Unified workspace UX

- One Arabic-first shell with Order / Cutting Plan / Cost tabs.
- Contextual top Edit / Save / Cancel action.
- Preliminary vs approved price status is visually explicit.
- Mobile/desktop responsive behavior and keyboard accessibility.

### A6 — Permission cutover and cleanup

- Rebind capability catalog to aggregate owners.
- Remove legacy PlanFieldAccess/CostEdit/PageAction compatibility owners made obsolete by the split.
- Run static, security, browser and Frappe v16 integration gates.

## 7. Non-negotiable invariants

- No automatic mutation of an Approved Cutting Plan.
- No silent replacement of production plan by a Draft.
- No cost data inside operational plan snapshot JSON.
- No `Door Cutting Order.write` requirement for focused Plan/Cost commands.
- No client-only authorization.
- No role-name authorization in JavaScript.
- No `ignore_permissions` as a permission solution.
- Domain/Application layers remain framework-free.
