# Optimizer P0 — Golden Baseline certification

**Status:** `PARTIAL / BLOCKED_INPUT` — synthetic safety and baseline are reproducible; no real order can yet be replayed with complete authoritative inputs.

**Base:** `Develop` `e8453978e08044542c67f3e5030179d7cfb7f55b`.

**Scope:** P0 documentation, audit tools, and test fixtures only; production code, scoring, permissions, lifecycle and search unchanged.

## Gate A — Customer corpus evidence

The private archive `طلبات للمقارنة.rar` was inspected locally; original PDFs/DXFs and their customer details are **not** committed. A read-only audit can be repeated on an extracted local directory:

```bash
python -m almdina_erp.tests.optimizer_p0_dxf_audit /path/to/extracted
```

`MATCHED` below means the same **multiset of rectangular cut-envelope dimensions**, independent of placement and 90° orientation. It does **not** certify full input parity, actual contours, piece identity, board material, trim, kerf, machine or allowable rotations. Nonrectangular/interleaved GEOMETRY is deliberately left unverified. DXF unit metadata is mm.

| Case | Envelope evidence | Drawn board sources: designer / system | Classification | Reason / limitation |
|---|---:|---:|---|---|
| 108 | PDF: 52 requested; designer DXF: 50 CUT_PATH plus 2 OFFCUT entities | PDF: 4 full plus unspecified نقص / 5 full | `INPUT_MISMATCH` | Board-source and two missing-cut identities unresolved. The apparent 5→4 saving is **not certified**. No system DXF; L pair/quad examples remain observed design evidence only. |
| 154 | Designer DXF 67 cuts; designer PDF 67 pieces | 4 / unavailable | `INSUFFICIENT_EVIDENCE` | No paired System DXF or canonical input rows/settings; clipped-corner composition cannot be replayed. |
| 230 | 66 / 66 envelopes | 8 / 8 | `MATCHED` | Rectangular envelopes only. |
| 231 | 40 / 40 | 4 / 4 | `MATCHED` | Rectangular envelopes only. |
| 232 | 22 / 22 | 2 / 2 | `MATCHED` | Rectangular envelopes only. |
| 234 | 15 / 16 counted outline groups | 2 / 2 | `INSUFFICIENT_EVIDENCE` | Geometry groups are not reliably rectangular; the count difference needs source reconciliation before quality comparison. |
| 235 | 11 / 11 | 2 / 2 | `MATCHED` | Rectangular envelopes only. |
| 236 | 17 / 17 | 2 / 2 | `MATCHED` | Rectangular envelopes only. |
| 240 | 416 / 416 | 23 / 23 | `MATCHED` | Rectangular envelopes only; use for later large-case performance once inputs are certified. |
| 241 | 22 / 22 | 2 / 2 | `MATCHED` | Rectangular envelopes only. |
| 242 | nonrectangular line topology | 1 / 1 | `INSUFFICIENT_EVIDENCE` | Special shape must be compared by cut contours, not four-line grouping. |
| 243 | 50 / 50 | 3 / 4 | `MATCHED` | Envelope equality and drawn 3 vs 4 boards observed; true manufacturing feasibility, input parity and saving remain **unproven**. |
| 244 | 134 / 134 line groups, some interleaved/nonrectangular | 9 / 9 | `INSUFFICIENT_EVIDENCE` | Cannot certify valuable remnant improvement from envelopes. |
| 246 | 41 / 41 line groups, at least one nonrectangular group; one observed bounding-dimension discrepancy around 24.9/25.0 cm | 4 / 4 | `INSUFFICIENT_EVIDENCE` | Isolate and reconcile geometry difference before evaluating arrangement. |

No `MATCHED` row is replayable from this archive alone. To close `BLOCKED_INPUT`, export anonymized canonical **saved** DCO/Plan input and output per case: per-copy identity, exact cut dimensions/contours and shape metadata, extras/edges, `allow_rotation`, board material/dimensions and source, OFFCUT owner and provenance, applied trim, kerf, machine, mode/time/engine version, and immutable saved System/Uploaded Plan snapshots. For 108 additionally identify the two missing pieces, the physical نقص source and board ownership; for 154 supply the System Plan; for 242/244/246 reconcile nonrectangular cut topology and differences. Strip names, phone numbers, addresses, file links, prices and other private data before committing a fixture.

## Gate B — Independent synthetic geometry, not customer reproduction

`almdina_erp/tests/fixtures/optimizer_p0_synthetic.json` specifies board, kerf, source FULL_BOARD, no rotation, shape fields and proposed hand placements. The existing independent `validate_plan` accepts the one-board L pair with an interior guest, L quad with three guests, and four clipped corners with three guests at 2 mm kerf. P0 safety tests verify all copies and identities, permitted rotation, bounds, clearance and separate Glass host identity. The fixtures are intentionally **not** the dimensions or geometry of cases 108/154.

The **separate future-target** `optimizer_p0_gap_reference.py` is RED on the unchanged engine (3 failures): current `Auto` uses two boards in each shape case although the independent geometry validator accepts one. This records a P3/P4 gap and is excluded from default discovery and the mandatory P0 safety command. It does not establish an improvement on a real customer order. `BOARD_ELIMINATION` is a synthetic baseline for P2, not a claim that a board can already be removed in that case. `GLASS_OPENING_PRIORITY` is a protective working case, not a new failure.

## Gate C — Current-engine baseline

Run `python -m almdina_erp.tests.optimizer_p0_baseline` to regenerate the JSON metrics. The archived run is `OPTIMIZER_P0_SYNTHETIC_BASELINE.json` with base HEAD, mode `Auto`, machine `CNC Router`, 0.2 cm kerf and 2 s budget. It records boards, placed/unplaced, reported waste and reusable free area, largest **bounding-box** free rectangle dimensions, Glass guests, method/attempts and wall time. Times are environment-dependent. Existing waste and free-rectangle metrics use bounding envelopes and must **not** be interpreted as actual material pocket area; interstitial pocket occupancy is currently not measured. No real baseline was run because no case contains all required input and source data.

| Synthetic case | Boards | Placed / unplaced | Glass guests | Accepted one-board hand layout? |
|---|---:|---:|---:|---|
| `L_PAIR_NESTING` | 2 | 3 / 0 | 0 | Yes, independent validator. |
| `L_QUAD_NESTING` | 2 | 7 / 0 | 0 | Yes, independent validator. |
| `CLIPPED_CORNER_GROUP_NESTING` | 2 | 7 / 0 | 0 | Yes, independent validator. |
| `GLASS_OPENING_PRIORITY` | 1 | 2 / 0 | 1 | Existing host mechanism. |
| `BOARD_ELIMINATION` | 2 | 5 / 0 | 0 | No claimed removable board. |

The default reusable-remnant threshold is larger than these small synthetic boards, so the reported `largest_reusable_free_area_m2` is zero for every case. Do not use that zero as a real-world leftover-quality conclusion.

## Tests and certification decision

- Mandatory P0 safety: `11 passed` locally.
- Explicit future targets: `3 failed as expected` on the unchanged engine; separate command and file.
- Related optimizer, kerf and Glass geometry subset including safety: `115 passed, 3 deselected, 17 subtests passed` with OR-Tools installed. The three deselected Cutting Plan validations patch `frappe.get_doc`; the stub runtime cannot exercise them. A first run without OR-Tools also failed one solver test due missing local dependency; installing the declared package cleared it.
- Cutting/DXF architecture: `12 passed, 45 subtests passed`. Focused DXF contract with the existing Frappe stub: `1 passed, 2 subtests passed`. Full Frappe integration and three deselected cases remain unverified locally.
- `git diff --check` and Python compile check passed. No production source files changed.
- No production migration or release was performed. **P0 real Golden Corpus is blocked; do not advance to P1.**

## Risks

The verifier accepting an independently constructed geometry does not prove a machine can cut the layout with the exact toolpath and sequence. Rectangular envelope matches cannot establish exact contour or source equivalence. The factory uses real plans, so any later algorithm change must also pass DXF export/validation, machine profile, kerf, edges, extras and operator acceptance before deployment.
