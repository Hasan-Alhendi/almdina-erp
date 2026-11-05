# P5 calibrated follow-up and deferred fallback projection

**2026-11-02 — P3 remains disabled by default.** This follow-up preserves the
earlier failed adoption observations. It does not relabel them as passing.

## Why another comparison was needed

An identical-baseline A/A experiment had changed 243's final rank and produced
a 0.529-second absolute wall difference in 110 without P3. Independent wall
observations alone could not attribute those differences to regrouping.

The new [predeclared protocol](p5-protocol.json) separates three questions:

1. Capture all native finalists immediately before optional P3 and replay them
   through the actual Application. Compare P3 with that same native trajectory.
2. On the immutable checkpoint, run the existing helper with its fixed packing
   caps twice, without a cooperative deadline. Require identical geometry,
   final rank and packing counts. This is not a five-second production run.
3. Retain independent fresh-process off/on wall and CPU observations, phase
   costs and every individual difference, alongside the same-trajectory result.

Source: `3d1f96714be062df6ff67dac8251f4d4dc57384c`. The measured environment had
Python 3.12.14, OR-Tools 9.15.6755 enabled, ezdxf 1.4.4 and pytest 9.2.0. This
does not silently combine the previous solver-unavailable timing observations.

Four new SYSTEM files were selected from archive metadata before opening their
geometry: 236, 240, 241, 242. The initial guessed IDs 237–239 were absent; the
metadata-only selection amendment is retained in the evidence. 242 contained
L corners and was excluded from the Regular-only cohort, without replacement.
236 has 17 pieces and a 122 x 280 cm board; 240 has 416 pieces; 241 has 22.

Together with the eleven earlier source cases, this gave fourteen cases, two
reversed-order repetitions and two arms: 56 fresh workers. Inputs reconstruct
SYSTEM geometry with allowed rotation/full-board assumptions, zero trim and no
machining reconstruction; they are not original DCO permissions or settings.
No designer coordinates or orientations were supplied.

## Result: safe observed effect, insufficient operational efficacy

| Observation | Result |
| --- | --- |
| Same-trajectory operational comparisons | 2 better, 26 equal, 0 worse |
| Repeatable operational winner | 300 only, in both repetitions |
| Fixed-work comparisons | 9 better, 19 equal, 0 worse |
| Native replay and fixed-work A/A equality | All 28 enabled workers exact |
| Measured maximum operational P3 tail | 0.222 seconds |
| Median independent enabled/disabled wall ratio | 1.0091 |
| New independent operational gains | None in 236, 240 or 241 |

The fixed-work gains repeated in 263, 298, 300 and 3687; 243 improved in only
one repetition. In contrast, only 300 improved repeatedly in the real deadline
window. P3 did not start in 16 of 28 enabled workers because no time remained.
Both efficacy conditions (two known repeatable wins and one fresh repeatable
win) failed. Fixed-work-only wins do not authorize default activation.

[All 28 paired observations](p5-calibrated-pairs.csv) retain independent-clock
differences too. The largest was +5.548 seconds in 298 despite no P3 tail call;
its alternative snapshot projections consumed about 5.94 seconds versus 0.83
in the independent baseline. The request budget is not a hard response-time
guarantee. In 240, native search alone took roughly 8.5–9.1 seconds against the
nominal five-second limit, followed by further snapshot preparation.

## Targeted production change: do not prepare an unused fallback

Application previously projected the main plan first, then projected every
Smart alternative. If any alternative was valid, its final rank selected the
returned snapshot and the first projection was discarded. Five alternatives
therefore caused six projections; the 416-piece case had one alternative and
still paid for two complete projections.

Application now projects and validates every alternative exactly as before.
When any is valid, it supplies the outcome for the existing final ranking.
Only if none is valid does Application project the main fallback. Non-Smart,
missing-portfolio and all-invalid cases retain their fallback behavior; the
existing incomplete-plan failure payload is preserved.

No candidate validation, centering, Kerf check, identity or permission check is
removed. This changes no packing algorithm, final ranking, number of gallery
alternatives, persisted setting, snapshot schema, localization text, permission,
financial boundary or migration. P3 stays explicitly opt-in. Rollback restores
the eager fallback call and needs no data conversion.

Before changing production code, original and prototype were replayed on all
fourteen frozen native portfolios twice in reversed order. Full
`OptimizationOutcome` equality was required, excluding only the newly measured
`total_elapsed_sec` in the winner and gallery snapshots. The actual patched
function was then compared with the exact old function on the same inputs:

- All 28 native comparisons had equal non-timing metadata, geometry, identities,
  candidate snapshots, selected rank and warm search seeds.
- Exactly one projection was avoided in every pair.
- Median projection-phase ratio was 0.8121, about 19% less time in that phase.
- 240 changed from two projections to one: about 4.00 to 1.88 seconds and 3.97
  to 1.93 seconds, saving 2.04–2.13 seconds. These are phase measurements on
  frozen inputs, not a 50% reduction in the whole request.

[All native projection pairs](projection-pairs.csv) include both timing orders.
Six regressions cover later better candidates, rejection of invalid
alternatives, all-invalid fallback, invalid fallback failure, no portfolio and
legacy modes, and unused invalid fallback. Five failed on the old eager code;
all six passed after the change. The tests are in the existing Application test
module, already selected by Static and Frappe workflows.

The 112 operational/checkpoint/fixed-work selected views were saved/reloaded;
all 24 distinct case/settings/material views passed actual JavaScript DXF export
and strict production import, including complete identity sets and equal material
placements. The long board and 416-piece case remain in that evidence.

## Change contract and remaining work

The production diff is limited to deferring fallback projection in Application,
its regressions and canonical evidence. All alternatives still reach their
independent manufacturing validation; the original fallback remains available.
Code/replay evidence does not certify actual CNC execution or machine motion.

P5 measurement is complete and its operational efficacy gate failed. The next
algorithmic task is stage scheduling: bounded regrouping can find improvements
on frozen inputs, but the native work often leaves it no deadline window.
This timing fix removes demonstrably discarded snapshot work; it does not by
itself allocate more search time to P3 or establish independent layout gains.
New scheduling proposals require a new predeclared comparison rather than
weakening the current criteria. Verify CI on the new commit before review;
the old commit's green checks do not certify this production change.
