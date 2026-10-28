# Almadina CAM — Cut Direction Editor (Design and release contract)

Status: **Phase 0 foundation only — NOT a production CNC feature**.
Source baseline: Develop 3b87b85d2a15ca90a74c2df8e7f05a0525e02b2f (2026-10-28).
No modifications to uploaded DXF bytes, Cutting Plan snapshots, approval, or NC programs.

## User outcome (Arabic-first)

Within a dedicated CNC preparation surface for an **approved, current** Cutting Plan,
a qualified technician sees cutter paths over each physical board, selects one CUT
PATH rather than an arbitrary door rectangle, and chooses:

- **Reverse travel** for an OPEN segment (two ends).
- **Select start point + clockwise/counterclockwise travel** for a CLOSED contour.
- **Keep until last / release constraint** as a distinct manufacturing instruction,
  not an alias for reverse.
- Reorder independent operations only when dependencies permit.
- Review arrows, start/end/release warnings, then save a **CAM draft**, not DXF.

A normal operator sees an approved setup/program only after an actual, tested
machine-specific CAM postprocessor and workholding validation exist.

## Invariants

1. A direction instruction is scoped to exact Cutting Plan name/revision and
   geometry fingerprint. Historical plans and uploaded originals remain unchanged.
2. The server resolves the current immutable approved plan; browser values never
   select an unvalidated historical/foreign order. Enforce separate capability
   for editing CAM; order read is not authorization for mutation.
3. Direction instruction targets **actual cutter-center paths** and includes
   sheet identity; paths shared by several pieces are not duplicated or attached
   naively to one piece number.
4. Open path direction = endpoint traversal; closed path direction alone does not
   determine where the final release occurs. Provide separate start point.
5. Changes must preserve the exact undirected geometry segment multiset. No
   changes to kerf, trim, rotation, offsets, or material contours.
6. A change in the plan, path decomposition, physical machine/tool setup, or
   validated release rules invalidates the corresponding machining draft.
7. Never claim an edited DXF will force ArtCAM/machine direction: CAD vertex order
   may be ignored or reordered by an external CAM processor.
8. Unsafe/ambiguous paths or missing machine setup: fail closed; display human-
   actionable Arabic error with sheet, piece (if proven), and path identity.
9. Physical orientation must use machine axes / material setup; screen RTL and
   coordinate Y flip must not be confused with machine top/bottom.
10. Design separate toolpath-order dependency checks; minimizing tool changes
    can never override workholding or product correctness constraints.

## Recommended implementation phases (new PRs or follow-ups)

### Phase 1 — visualization / scoped persistence

- Extract reusable CUT_PATH projection from existing **validated** geometry
  (never parse arbitrary text in the UI and trust it as manufacturing data).
- Show arrows on open/closed paths and click/tap/keyboard select within a
  zoomable viewer, physical board orientation explicit.
- Persist separate immutable-revision-scoped CAM DRAFT instructions with
  optimistic concurrency and schema version; not inside the approved plan's
  snapshot_json. Only permitted technicians may edit.
- Server recomputes/validates path IDs from canonical snapshot; rejects missing,
  duplicate or stale paths, and refuses saving to an unsuitable lifecycle state.
- Keep current DXF export and historical archives byte-for-byte unchanged.

### Phase 2 — production execution

- A qualified machine profile, cutter/tool settings, workholding and actual
  postprocessor MUST exist; map direction instructions to actual NC toolpaths.
- Independent verification of NC axes, feed/plunge, Z clearances, startup and
  shutdown, controller dialect, simulated path and physical machine qualification.
- Machine operation may start only after explicit review/approval under factory
  operational policy. Revocation on source/machine/tool changes.

## Tests required before showing UI

Pure contract: reverse open paths, rotate/reverse closed path, path identity under
reversal/rotation, duplicate geometry rejection, invalid coordinates, non-mutation.

Integration: permission denial; wrong order/tenant; stale plan; old approved
archive read-only; concurrent edits; generated and uploaded plan path parity;
shared edge path identities; physical Y orientation; device RTL; persistence
after reload; missing cutter-center paths; approve/cancel/reapprove lifecycle.

Regression: existing system/uploaded/approved DXF bytes, fingerprint V2/V3,
kerf/trim, OFFCUT identity, special geometry/liner, Frappe migrations, and
production-stage restrictions.

## Phase 0 implementation in this branch

The new pure function `orient_path` accepts an immutable path and an explicit
direction/start instruction; it validates the vertices and checks that the
undirected cut segments remain exactly unchanged at 0.001 mm precision.
`stable_path_id` keys a path to a sheet and to geometry, but the caller MUST
scope it to immutable plan revision and reject duplicate coincident identities.

**Neither function generates machine code, chooses an instrument, sets a safe
direction, saves data, nor changes an exported DXF. This code must not be exposed
as a "ready to cut" UI without Phases 1 and 2.**
