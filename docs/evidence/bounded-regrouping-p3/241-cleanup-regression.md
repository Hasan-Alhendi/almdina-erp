# Order 241: close final gaps without changing native search

2026-11-02. Baseline: `a5bd27b642d38631e4656af028cb90f79c8a1f6a`.
P3 remains disabled by default. Earlier failed adoption gates still stand.

## Reproduced defect

The archived SYSTEM 241 layout matches the supplied before screenshot: 22
regular rectangles on two 122 × 244 cm boards, split 7/15, a 1 cm physical
inset and 0.5 cm Kerf. The usable frame is 120 × 242 cm. Previous P5
zero-trim experiments did not cover this physical configuration.

Existing cleanup moved pieces toward a free edge, breaking Kerf contacts.
The first board's occupied height grew from 236.3 to 242 cm, yet estimated
cut count improved from 47 to 46. Both plans had two boards and zero useful
remnant. Rigid column centering alone does not create that internal gap.

| Exact archived-layout replay | Original | Old cleanup | Final compaction |
| --- | ---: | ---: | ---: |
| Boards | 2 | 2 | 2 |
| Reusable remnant, m² | 0 | 0 | 0 |
| Summed occupied bounding area, cm² | 55,744.22 | 57,015.20 | 55,744.22 |
| Unique cutter-center network, m | 30.710 | 32.276 | 29.926 |
| Estimated cuts | 47 | 46 | 46 |

Network length measures geometry, not CNC machining time. The archive is a
causal witness; the screenshots do not establish the deployed SHA or original
DCO permissions.

## Why the first prototype was rejected

An early acceptance guard prevented spreading inside native cleanup. On
identical captured finish inputs, 241's selected network improved from
31.298 to 30.873 m with the same useful remnant. However, its changed early
incumbent also changed subsequent local-search sequences. A real five-second
run returned zero useful remnant where an earlier baseline trajectory found
0.101412 m². Independent clocks alone cannot isolate all such differences,
but this was insufficient evidence to activate the early guard.

That guard is not in the production change. All pre-existing Domain search
functions, packers, incumbent selection and experimental P3 behavior remain
unchanged. The correction runs only after native optimization has returned.

## Final correction

During Smart snapshot projection, after existing edge centering, a Domain
helper tries four deterministic translation sweeps: each axis toward either
board edge. It never rotates pieces, regroups them or adds boards.

The pass is limited to at most the existing 64-piece repair cap, CNC/Auto,
complete plain Regular full-board plans with proven metrics and zero useful
remnant. Positive useful remnants, OFFCUT, imported geometry, overlays,
outlines and recorded nests retain their existing layout. Large orders and
other optimizer modes do not enter the new pass.

Each accepted sweep must preserve completeness, board count, machine
feasibility and useful-remnant priority; it must not increase occupied
bounding area or actual cutter-center network length and must improve at
least one of those geometric quantities. Full validation and transform
permissions remain mandatory. Network measurement reuses the canonical
`cutter_center_segments` implementation and its existing collinear tolerance.

Final ranks are recalculated from the actual projected geometry using the
unchanged `industrial_rank`. If two alternatives become identical, only the
best visible copy remains. Every original raw warm seed is retained for
continuation; no synthetic replacement is created to pad the gallery.

## Verification protocol

Before/after Application projection uses exactly the same captured native
portfolios, 1 cm trim and 0.5 cm Kerf: 241, 236 and 298, plus a separate
241 portfolio whose five alternatives all have zero useful remnant. The
comparison substitutes the exact old `_snapshot_outcome` function from
`a5bd27b`; it does not rerun native search on independent clocks.

The native 241 winner with 0.101412 m² useful remnant is unchanged; its three
zero-remnant alternatives improve geometrically. In the separate all-zero
portfolio, three of five geometries improve and two remain unchanged. Orders
236 and 298 retain their entire gallery geometry and ranks. All original raw
warm-seed geometries survive in every case. The gallery may contain fewer
than five views when final compaction collapses duplicates.

Focused coverage includes the real archived source, both native cleanup
origins, short/long search budgets, zero/positive Kerf units, protected
geometry, positive-remnant/Panel Saw/large-order exclusions, duplicate-view
handling with unchanged warm seeds, and actual 1 cm-trim Application →
save/reload → JavaScript export → strict production import.

## Scope and limits

This repairs a proven avoidable-gap cause. It does not promise automatic
recovery of the archived 7/15 allocation, removal of every gap from every
alternative, or fewer boards in 236/298. Reconstructed SYSTEM inputs assume
allowed rotations; original DCO grain and addon permissions were unavailable.
No designer poses are supplied to native search.

No new UI text, persisted field, setting, schema, permission, financial data or
migration is introduced. Approved snapshots are not rewritten. Rollback
removes the final-projection call, helper and duplicate-view filter.
