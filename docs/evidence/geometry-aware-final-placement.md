# Geometry-aware final placement — evidence

Branch `feature/smart-edge-protection`, Draft PR #606, base Develop `2367b8ff`.
Implementation follows the initial protection/settings commits `f82f2027` and
`d5f96305`; the whole-sheet-only policy is superseded.

## Change contract and root cause

Goal: improve final System group positions with bounded, atomic coupled moves.
Scope: domain final placement, the shared translation primitive, existing
application alignment-tail scheduling, regressions and canonical contracts.
No new setting, dependency, optimizer, endpoint, permission or migration.
Packing/ranking priorities, sheet count, identities, dimensions/orientations,
mandatory trim, Kerf, saved/Approved immutability and fingerprints V1–V4 remain
invariants. Snapshots remain authoritative; editor open never rearranges them.

Before implementation the two placement regressions failed (2 failed/1 passed).
Early centering uses projection groups; compaction/alignment can then change
them. The previous edge stage used the occupied span of **all** sheet pieces,
required every piece to be movable and translated the entire sheet. A full-height
right column therefore hid the left chain's 32 mm of usable slack. It also
declined final centering proposals instead of reevaluating the final geometry.

## Provenance and limits

The native UI exposed the test site's factory settings: Kerf 5 mm, trim 0,
centering 7 cm, protection H15/V20 mm, alignment tail 3 s and optimization 120 s.
The saved snapshot/source/manual-edit state of CP-2026-00653 and the deployed
Git revision were **not obtained**. No live plan or setting was changed.

These are synthetic dimensional witnesses, not a capture of order 26-00331.
Board 1220×2440 mm; known left sizes 393×798, 399×800, 399×800 mm; known second
board widths 393 mm. Right-hand heights/positions and the upper anchor on board
2 are explicit synthetic assumptions in the test. Results cannot certify the
customer's actual plan or a machine/NC setup.

## Construction and acceptance

Reuse projection, existing alignment/contact groups, movement intervals and
real cutter contacts. Add directional contact components so a vertical chain
remains discoverable in a staggered board-wide T-contact graph. Keep independent
pieces as choices; no Kerf contact is promoted to a mandatory rigid dependency.
Only eligible regular pieces move. Frozen special/nested contours stay in the
complete actual cutter network and full validators; unknown geometry fails closed.

Events are safe-interval endpoints, minimum protection insets, eligible centers
and existing matching-edge events. Try singles and pairs with different offsets,
including combined X/Y. Proposals use one shared atomic translator with final
bounds/Kerf and continuous relative swept-clearance prechecks. No intermediate
compound state is committed. Full geometry, permissions, manufacturing export
compatibility, connected eligible remnant successors, metrics and final adapter
validation remain mandatory. A useful remnant may lose a bounded margin strip;
fragmented or newly ineligible replacements are rejected.

Protection shortfall is evaluated on subgroup spans, separately per axis.
Then compare the actual complete network, coordinate-only alignment, minimum
displacement around large remnants and eligible centering. A coordinate match
does not claim shared cutting. A shorter complete network may have more merged
segments; equal-length moves preserve longest internal continuity. Every stage
uses the export's existing cutter-center generator, not a new DXF generator.

## Before/after geometry

Physical millimetres, trim zero. These are results through the actual Application
finalization and Snapshot pipeline using the stated witness packing input.

| Board / piece | Before (X,Y) | After (X,Y) |
|---|---:|---:|
| 1 / left 393×798 | 0,0 | 6,16 |
| 1 / left 399×800 | 0,803 | 0,819 |
| 1 / left 399×800 | 0,1608 | 0,1624 |
| 1 / middle upper 393×400 | 404,0 | 404,22.5 |
| 1 / middle lower 393×1990 | 404,405 | 404,427.5 |
| 1 / far upper 418×600 | 802,0 | 802,0 |
| 1 / far lower 418×1835 | 802,605 | 802,605 |
| 2 / synthetic upper anchor | 15,0 | 15,20 |
| 2 / 393 mm group, first | 0,1600 | 15,1600 |
| 2 / second | 398,1600 | 413,1600 |
| 2 / third | 796,1600 | 811,1600 |

Board 1's left chain reaches 16/16 mm vertically. Middle chain moves 22.5 mm;
the far-right full-height column stays fixed. An additional 6 mm horizontal
translation of the narrow first door aligns its actual right cutter with the
wider doors. Full horizontal 15 mm protection is blocked by the tightly packed
neighboring columns; the preference does not force an unsafe inset.
Board 2 achieves horizontal 15/16 mm and aligns with its unchanged X=15 mm anchor.

## Actual cutter evidence

| Witness | Full canonical mm | Merged segments | Longest internal mm | Total internal mm |
|---|---:|---:|---:|---:|
| Board 1 before | 14592 | 14 | 2440 | 8072 |
| Board 1 after | 13789 | 15 | 2440 | 8873 |
| Board 2 before | 8014 | 10 | 1191.5 | 6801 |
| Board 2 after | 8014 | 10 | 1194 | 8014 |

The generator offsets every finished edge, including at the original board edge.
Increasing the clipped internal length after an inset is therefore legitimate;
it does not imply losing shared cuts. Full canonical union length is measured
separately. Individual perimeters do not change under translation.

| Trial | Geometry / Kerf | Full network | Decision |
|---|---|---|---|
| Left Y+16 alone, right fixed | valid | 14608 mm, +16 | reject lost sharing |
| Left Y+16 + middle Y+20 | valid | 14588 mm, −4 | admissible coupled alternative |
| Final coupled placement + X alignment | valid | 13789 mm, −803 | accepted after full gates |
| Three widths X+15 | valid | 8014 mm, unchanged | accepted; aligned, protected |
| Compound ending at/through another door | invalid final/swept clearance | not evaluated as safe | atomic rejection |
| Margin destroys factory remnant eligibility | geometrically possible | insufficient | reject remnant |
| Final adapter rejects proposed geometry | domain may pass | insufficient | restore complete baseline |

The count increase 14→15 is accepted with a shorter proven network, rather than
mistaking segment count for cut length. DXF geometry is not NC certification.

## Verification and bounded performance

Focused feature run: **109 passed** (31 geometry-aware tests and 78 existing edge-policy tests)
pass. Tests include safe left-only Y+16 with genuinely independent right pieces,
coupled unequal moves/T contacts, 96/75 alignment versus standalone 96 centering,
frozen Glass with actual hole contour, unknown special/nested/attached geometry,
OFFCUT/Panel Saw, positive trim, mirrored layouts, idempotence, global caps,
expired budget and retention of the last completed candidate.

Two integration variants pass Application→Snapshot→persisted export projection→
actual JavaScript DXF→AutoCAD normalization→strict re-import: the stated witness,
and real native packing from the 11 dimension rows. All 11 finished outlines and
CUT_PATH are present and exact geometry survives. Identical-size independent
source rows can bind in either order at import; the test checks their exact
geometric multiset, without inventing copy provenance. Snapshot persistence and
translations preserve original source identity metadata exactly.

Native Preview/Continue Search/gallery/cache reload and editor projection pass.
JS editor-open, gallery/continuation and Arabic/English settings tests pass.
Disabled policy's deterministic native 42-piece/3-board/5-candidate output uses
241 real packing attempts and retains SHA256
`5d23b4899c2b10344f374d7078b6d4ea5a7bd292aa697642c5946cae3453608a`,
identical to both preceding branch and Develop baselines.

Existing caps remain: 64 pieces/sheet, 24 expensive trials/plan, four local
sweeps; remaining trials are shared fairly between boards. The existing factory
alignment time tail is shared across gallery candidates. Deadline checks stop
new work; a completed safe result is retained. A zero alignment budget disables
arbitrary matching-edge events but retains bounded policy events.

Diagnostic Windows/Python 3.12 run (not timing assertions): staggered final stage
137 ms/15 trials, second-board stage 30 ms/12 trials, complete two-board witness
Application finalization 214 ms. A 65-piece sheet skipped at the existing limit
in 0.14 ms, before topology/free-space/full validation work. These measurements
were taken while other local checks were running; they are not CNC runtimes.

CI and broader suite results are recorded on PR #606 for the tested head.
The broader cutting/history/Preview/editor/architecture run reports **249 passed,
1 skipped and 132 subtests passed**, with four failures in
`test_manufacturing_cut_contract.py`. All four reproduce on clean Develop
`2367b8ff` (48 passed/4 failed in the corresponding isolated baseline run):
three old fixture rows lack stable physical identities and one Glass fixture
lacks its fingerprint margin. No reviewed hash or unrelated contract is weakened.
Other known Develop CI failures remain tracked in the initial evidence.
