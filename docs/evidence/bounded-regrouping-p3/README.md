# Bounded regrouping P3 — adoption gate, 2026-11-02

**Status: experimental, disabled by default. P5 did not pass; production P6 is
not certified.** This is a reviewed implementation for explicit Domain research,
not automatic activation of P2, P3 or P4.

The subsequent [calibrated P5 follow-up](p5-calibrated.md) separates native
trajectory, fixed work and wall time, adds three independent Regular cases,
and verifies a targeted Application fix for discarded fallback projections.
P3 remains disabled; the earlier failed observations below remain unchanged.

## Change contract

- Goal: make bounded whole-board regroup proposals testable without displacing
  native search or losing completed work when a later proposal times out.
- Scope: two cutting Domain modules, focused tests and geometry fixtures,
  the existing Static Checks test list, and this canonical evidence.
- Invariants: complete source identities and quantities, physical Kerf,
  allowed transforms, protected nests, independent whole-plan validation,
  existing `industrial_rank`, no additional boards for organization.
- Localization, permissions, financial boundaries, schema and migrations:
  no changes. No new UI, persisted setting or RPC option.
- Rollback: remove the internal opt-in and helper; no data conversion.

## Frozen comparison

Baseline: `3d9e35b943c0102e014a9dc74598b847e4519a84`.
[Protocol](protocol.json) was written before results. Each arm ran sequentially
in a fresh Python 3.12 worker at a nominal five-second Application budget.
Eleven cases, two reversed-order repetitions: 22 paired observations per
variant. Research did not install OR-Tools; exact search was unavailable.

Known cases: 263, 296, 297, 298, 300, 243, 3687, 109 and 110. New SYSTEM files
were selected before opening: 230 and 231 were included; 234 was excluded for
non-Regular geometry, without replacement. These are reconstructed geometry
inputs, assuming all rotations, full boards, zero trim and no machining addons;
they are not original DCO permission/settings provenance.

Acceptance required safety, no observed increase in boards or final rank,
repeatable benefit in at least two known cases, median wall ratio <= 1.10 and
maximum paired wall increase <= 0.50 seconds. Network length and alignment are
diagnostics, not substituted ranking criteria. No threshold was relaxed.

| Research scheduling | Better / equal / worse | Median wall ratio | Maximum wall increase | Gate result |
| --- | --- | --- | --- | --- |
| P3 after native cancellation generator, before remaining native finishing | 6 / 15 / 1 | 0.9997 | 0.2616 s | Fail: 243 repeat 1 rank regression |
| P3 after native quality, return winner only at end of tail | 2 / 20 / 0 | 1.0195 | 0.4739 s | Fail: repeatable benefit in only one case |
| P3 after native quality, publish each completed winner immediately | 6 / 16 / 0 | 1.0129 | 0.5876 s | Fail: 110 repeat 0 wall increase |

All 132 research snapshots were complete and Domain-valid; no paired board
count increased. [All pairs](paired.csv), including failures, are retained.
None of these experiments reduced a complete order's board count.

The first scheduling improved 263, 298 and 3687 in both repeats. Its 243 loss
was 109 versus 110 estimated cuts after finishing. Native baseline itself
varied between those ranks across repetitions; time-limited search does not
give a cross-process dominance guarantee merely by retaining its initial seed.

The end-only tail found a better 3687 plan but lost all tail improvements when
a later attempt crossed the caller's deadline. Immediate publication retained
improvements in 300 and 3687 in both repetitions. The additional apparent wins
in 243 had **zero accepted P3 proposals**, so are not attributed to P3.
The 110 wall failure remains a failure even though its measured P3 tail was
only 0.0796 seconds: clock variability in the native work does not authorize
silently changing the frozen end-to-end criterion.

The native implementation was then compared directly with unchanged
`3d9e35b` in five cases (300, 3687, 243, 110, 230), two repetitions:
20 further workers, 5 better / 4 equal / 1 worse pairs, no board increases.
Both 300 and 3687 improved twice. The apparent 243 gain and loss again had
zero accepted P3 proposals; the original time-limited finishing varied.
This targeted parity check is not a replacement for the failed frozen gate.

## Native opt-in contract

`smart_search(..., experimental_regrouping=True)` is an internal explicit
research opt-in. Existing production callers omit it and retain `False`.
Panel Saw never enters it. It runs **after** the existing search and quality
pass, without a new reserved time slice, under the original overall deadline.

The helper proposes whole neighborhoods from the four eligible sheets with
fewest pieces, capped at 64 pieces per pack, three neighborhoods and 24 packing
attempts **per Smart invocation**. Orders are long-side, area and short-side;
methods are the four existing MaxRects variants. Pair/triple enumeration is
bounded, but the 24-attempt cap exhausted pairs in the measured experiments;
there is no demonstrated triple-search benefit. Research wrappers shared the
cap across a whole worker; the native cap is local to each Smart call, so
multiple Application continuations must not be represented as one 24-pack cap.

Only unlocked Regular FULL_BOARD sheets and source pieces without baked
geometry/overlays are eligible. Glass, L, clipped-corner groups, their guests
and OFFCUT boards remain intact. Packing receives original sources, preserving
permissions and machining metadata. Replacement is atomic; no partial subset
is committed. Unselected pieces and board metadata survive, packing caches are
replaced, board numbers and whole-plan area totals are recalculated.

Every proposal must improve the incumbent's existing industrial rank and pass
whole-plan completeness, bounds, overlap, physical Kerf and transform checks.
Each accepted proposal is immediately offered to the existing Smart portfolio.
A later rejected or late proposal cannot erase it. This does not claim that
every intermediate raw candidate wins after Application finishing or that
bounded search finds the optimum.

## Verification and remaining release work

`test_board_regrouping.py` covers two deterministic native System witnesses,
input immutability, identity/area/metadata, capped work, protected sheets,
zero Kerf, forbidden rotation, malformed candidates and deadline retention.
It also exercises actual Application snapshot/save/reload, actual JavaScript
DXF export and strict production import with zero/positive trim and valid
liner, rear groove, recessed handle and double-edge metadata.

The 152 selected benchmark snapshots passed save/reload; all 17 distinct
case/settings/geometry views passed actual JavaScript export and strict
production import, with complete identity sets and equal material placements.
The focused native module passed 37 tests. Local architecture/documentation/
localization contracts passed 57 tests and 66 subtests.

Run focused verification:

```bash
python -m pytest -q almdina_erp/tests/test_board_regrouping.py
```

The test is included in the existing Static Checks workflow. Integration must
be checked on the new PR SHA, not inferred from the old baseline's CI. Actual
CNC execution, motion/clamp limits and operator UAT remain outside automated
geometry evidence. No deployment or merge is authorized by this experiment.

Before default activation: resolve the end-to-end timing failure, repeat the
unchanged acceptance gates on fresh independent inputs, then certify the
enabled production path. Keep P2 and P4 separate; their experimental results
do not authorize activation here.
