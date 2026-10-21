# ALMADINA Optimizer — roadmap status

**Base:** `Develop` at `e8453978e08044542c67f3e5030179d7cfb7f55b` (2026-10-21).

**Direction:** Hybrid Optimizer + Global LNS + Selective True-Shape Nesting.

**Priority:** correctness → manufacturing safety → optimization quality → performance.
**Current gate:** P0 `PARTIAL / BLOCKED_INPUT`; see [OPTIMIZER_P0_GATE.md](OPTIMIZER_P0_GATE.md). Do not start P1 from an unapproved golden baseline.

| Phase | Status / scope | Acceptance test | Prerequisites | Main risk |
|---|---|---|---|---|
| P0 Golden Baseline | **PARTIAL**. Anonymized DXF-envelope comparison, independent synthetic shape fixtures, current-engine baseline. No production code. | Reproducible safety tests and benchmark; complete real input/snapshot/source provenance before real-case replay. | Matched system/designer artifacts and canonical inputs. | PDF/DXF drawings do not encode all optimizer inputs; offcut can masquerade as a full-board saving. |
| P1 Quality Metrics | Waiting. Define measured board/source, useful leftover dimensions, cut effort, actual geometric pocket occupancy and safety; no score change until validated. | Metric invariance under harmless representation changes; deterministic values on certified golden cases; no financial or production change. | P0 acceptance and input provenance. | Bounding-box waste falsely describes shaped material or Glass cavities. |
| P2 Board Elimination + Global LNS | Waiting. Improve placement across all boards without replacing the existing optimizer; compare eligible candidate layouts using P1 measurements. | New RED→GREEN board-elimination fixture, no loss/duplicate pieces, permitted rotations/kerf/source, valid machine layout, no regression on golden board counts and runtime budget. | P0, P1. | Searching a feasible-looking layout that cannot be cut on the selected machine. |
| P3 Shape Complementarity | Waiting. Discover combinations of L and clipped corners using real cut outlines and current allowed orientations. No order-number special cases. | `L_PAIR_NESTING`, `L_QUAD_NESTING`, `CLIPPED_CORNER_GROUP_NESTING` turn GREEN while independent geometry/DXF validation, kerf, edge/add-on constraints remain GREEN. | P0 and P1; P2 if shared search infrastructure is used. | Treating bounding rectangles as solid, invalid clearance or an unproven rotation. |
| P4 Interstitial Pocket Packing + Glass-First | Waiting. Pack eligible guests into proven inter-piece pockets and Glass holes as distinct geometry relations; compare whole-plan quality. | Safe Glass host identity and separate shape-pocket relation; prove guest eligibility, area/kerf, board count and global quality on targeted tests. | P1, P3; existing Glass contracts. | Mixing cut-out Glass waste with space between material contours. |
| P5 Selective Angled Rotation | Conditional, **not approved**. Only enable for individually proven need with material/machine/add-on constraints. | Separate RED→GREEN case proves gain and machining validity; existing `rotated` contract preserved until a dedicated approved design. | P3/P4 evidence and explicit product decision. | Grain, machining direction, edge binding, and incompatible persisted rotation semantics. |
| P6 Performance & Production Certification | Waiting. Determinism, bounded time, versioned rollout and real operator verification. | Targeted + DXF regression, golden quality/safety, performance envelopes, pinned Frappe/ERPNext runtime where required and production-like acceptance. | Approved P1–P4 and any approved P5. | Search-time amplification on large orders. |
| P7 Learning from Employee Corrections | Future study only. Capture authorized correction signals without changing live plans. | Privacy/provenance and held-out improvement demonstrated; no silent model-driven production actions. | P6 and explicit approval. | Learning from incorrect or incomparable human edits. |

## Resume instructions

1. Read this file and `OPTIMIZER_P0_GATE.md`, then verify the latest `Develop` and any open optimizer Draft PR; avoid duplicating P0.
2. For P0 closure obtain canonical per-order piece inputs, cut dimensions/contours, flags and permissions for rotation, machine, kerf, applied trim, board and OFFCUT sources, and the exact saved System Plan snapshot with engine version/settings. Reconcile any one-millimetre/shape differences before calling a pair MATCHED as a *complete input*.
3. Run `python -m pytest -q almdina_erp/tests/test_optimizer_p0_safety.py` and `python -m almdina_erp.tests.optimizer_p0_baseline`. Run `python -m pytest -q almdina_erp/tests/optimizer_p0_gap_reference.py` only to observe the three intentionally failing future-target tests; its filename excludes it from default test discovery and the P0 passing gate.
4. Never label P0 PASS merely because the DXF envelope multiset matches. Maintain `BLOCKED_INPUT` until a replayable, source-complete real corpus is verified.

## Fixed invariants for every later phase

Approved plans immutable; no new cost, stock or production behavior; `allow_rotation`, edge banding, grooves and add-ons respected; no free-angle rotation by default; no fixed roles; capability and board-source boundaries unchanged; DXF/geometry validation mandatory; Panel Saw plans must meet its cut feasibility. Start each phase with a failing targeted test, then the smallest architectural change, relevant optimizer/DXF regression, baseline comparison and this status update. One stage at a time; no automatic merge.
