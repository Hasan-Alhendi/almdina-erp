# P3 industrial nesting evidence

P3 preserves P0–P2. No schema, pricing, remnant lifecycle, saved-plan rewrite,
rotation permission or geometric-tolerance change. New code reuses the existing
packers, polygon checks, rigid translations, industrial rank and final gate.

## Manufacturing gate

A recorded angle alone no longer admits a guest. Validation requires an exact
plain rectangle, four real inward-facing clipped hosts in the matching 2×2
formation, the computed notch angle, board bounds and actual Kerf clearance.
Glass and machining-addon guests retain quarter-turn placement: their arbitrary
angle hole/toolpath import contract is unproven. The real JavaScript exporter
rejects these unsupported angled contours instead of silently dropping holes.
Uploaded original DXF and historical snapshots are not rewritten.

An actual JavaScript export → DXF parser → contour ownership roundtrip checks
five independent identities, contours, dimensions and CUT_PATH presence.
The roundtrip exposed and fixes `list.index` assigning all identical clipped
pieces to expected index zero. Existing Glass/liner/groove/handle export tests
remain enabled. The full 45-case liner geometry module is now a Static Checks
gate: seven pre-existing harness failures were reproduced on Develop and P2,
then fixed by using the current constructor and strict per-point comparisons.
Manufacturing dimensions and expected coordinate values are unchanged.
Symmetric contours whose semantic orientation cannot be resolved
still fail closed; no mirroring ambiguity rule was relaxed.

## Golden gap coverage

| Case | Evidence / executable test |
| --- | --- |
| Board edge, no artificial Kerf margin | `test_boundary_gap_candidate_does_not_pay_kerf_on_board_edges` |
| Kerf-only separation / contact score | `test_contact_point_score_rewards_kerf_contact_and_selects_the_tight_candidate` |
| Rotated piece fills a boundary gap | `test_rotation_fills_a_boundary_gap_without_changing_permission` |
| Scattered strips → one separable offcut | `test_same_board_compaction_converts_scattered_strips_to_one_offcut`: 0.20 → 0.597 m² on supplied valid layout |
| Two boards → one | `test_boundary_gap_eliminates_a_board_after_full_search_validation`: supplied layout; end-to-end Glass case below separately proves final-engine savings |
| L pair/quad void clearance | Existing `test_four_l_pieces_share_a_void_without_mirroring`, `test_a_guest_larger_than_the_kerf_inset_void_stays_outside` |
| Unused Glass capacity | `test_glass_opening_assignment_saves_a_final_board`: actual optimizer 2 → 1 |
| Rigid group blocks useful space | `test_compaction_moves_the_clipped_void_group_as_one_rigid_unit`; existing consolidation/host-chain tests |
| Visual gap vs physical coordinates | Final regression in `cutting_plan_renderer.test.js`: exact 20.3% position, border-box, unchanged plan |
| Mandatory gap must remain | Boundary 8.29 cm rejection versus valid 8.30 cm; `Mandatory-gap` benchmark stays at two boards |

## Requested 37-case source matrix

`almadina_nesting_cases_first_three_groups(1).pdf` was not supplied or found.
Do not treat the following group coverage as a verified mapping of its 37
individual numbered requirements. Exact 37/37 sign-off remains blocked on that
source; no case descriptions or pass counts have been invented.

| Requested group | Available coverage |
| --- | --- |
| 1–17: L/Clipped/Pairs/Quads/mixed | `test_cutting_shape_search.py`, pattern/offcut and rigid tests |
| 18–24: rotation/mirroring/exception | `test_placement_orientation.py`, shape-search permission tests, P3 negative/real-export tests |
| 25–37: void/Glass/nested hosts/movement | `test_glass_opening_nesting.py`, `test_nesting_consolidation.py`, P3 Glass assignment and rigid compaction |

## Bounded search / measurement

At most five de-duplicated shape partitions, three complete Glass assignment
variants, twelve compaction trials (three boards × four groups), and existing
cancellation/remnant limits. Post-passes share one deadline; final independent
validation remains mandatory. Existing base packing/mode startup and Adaptive
Trim probes are measured in wall time and are not a strict request-wide timeout.
No fragmentation score or historical metric field was introduced.

Run `scripts/benchmark_cutting_p1.py --label LABEL --output FILE` from each
measured checkout. `--machine-type` separates CNC Router and Panel Saw;
`--case Large-120 --mode 'Optimal Search'` includes its heuristic fallback.
Inputs, probes and final snapshots are emitted for independent validation.
Original customer-order data and physical CNC execution remain unavailable.
