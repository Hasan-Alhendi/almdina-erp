# DXF-181 golden baseline fixture

`dxf_181_golden_baseline.json` is an anonymized, reduced geometry fixture. Its source evidence was checked against the available `3442.dxf` and order-measurement PDF: the DXF has 47 `CUT_PATH` polylines and 2 `OFFCUT` polylines; the PDF has 12 measurement rows with 49 requested copies. The source also has four `Liner` polylines and four sheet outlines. No names, phone numbers, tenant identifiers, source text entities, or customer document are included.

The five reported swapped dimensions come from the Jira story context. The DXF/PDF files do not contain the persisted `allow_rotation` values or a trustworthy identity link from every contour to its saved row. For that reason, the fixture reduces the geometric pattern and marks its `allow_rotation=false` values as synthetic. It reproduces the diagnostic failure mode; it does not claim that these five exact fixture rows are the five saved production rows.

## Baseline diagnosis

The topology layer first tries an injective inventory assignment. When it fails, `_forbidden_rotation_error` performs a relaxed assignment with rotation enabled, then retains a forbidden rotation only when excluding that single contour-to-piece edge makes the assignment impossible. It returns a diagnostic only when exactly one such edge exists. With multiple forced rotations, or repeated equal-size copies that leave alternate assignments, the function returns no rotation diagnostic. The caller then reports `EXPECTED_PIECE_MISMATCH` with generic order-level target data. This is the reproducible baseline defect; the production algorithm remains unchanged in Story 181.

One test intentionally asserts the desired multi-rotation identity contract and is marked as an expected failure until ALMADINA-182 implements that diagnosis. The passing baseline snapshot records the current code, target, and parameter values without weakening that expectation.
