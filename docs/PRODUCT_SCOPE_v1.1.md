# Almdina ERP Product Scope v1.1

**Effective date:** 2026-07-29
**Status:** Current product boundary

For the full Arabic SRS and acceptance criteria, see
`REQUIREMENTS_v1.1_AR.md`.

## Included

- Free-text board description.
- Board length and width, defaulting to 244 × 122 cm.
- Door measurements and regular, clipped-corner and special shapes.
- Per-side edge selection, edge thickness deductions and edge pricing.
- Cutting optimization and immutable approved cutting plans.
- Board, cutting and edge operational cost calculation.
- Special-shape pricing approval.
- Customer quote/invoice calculation.
- Customer invoice printing.
- Measurement and production printing.
- Production workflow, incidents and replacement pieces.
- DXF import/export and operational reports.

## Excluded

- ERPNext stock Items as the board identity.
- Warehouses and stock balances.
- Stock availability checks.
- Material reservations.
- Material consumption and reconciliation.
- Stock Entries and Stock Ledger movements.
- Board-remnant inventory, reservation and reuse.
- Inventory valuation and material-variance accounting.

Historical inventory DocTypes and services may remain temporarily in source only
to protect existing installations during migration. They are not part of the
active UI, approval workflow, costing calculation or installation setup and
must not be used by new product code.

## Cost and invoice rule

Inventory is excluded; pricing is not.

The active order total continues to include:

```text
Board cost = required boards × board rate
Cutting cost = required boards × cutting rate per board
Edge cost = sum of selected edge lengths × their rates
Operational order cost = board cost + cutting cost + edge cost
Customer quote total = operational order cost plus approved special-shape pricing
```

Customer invoice and measurement printing remain required product features.

## Architecture rule

- Business calculation belongs in `domain`.
- Use-case coordination belongs in `application`.
- Frappe and persistence belong in `infrastructure`.
- UI and printing consume calculated values and must not duplicate formulas.
- No active module may import stock, reservation, consumption or remnant
  services into order approval or customer costing.
