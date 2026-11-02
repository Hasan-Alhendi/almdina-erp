# Direct Kerf research — production selection unchanged

Change contract: observe previously discarded Direct layouts without repacking,
changing the stable-Kerf winner, search order, ranking, gallery, snapshots or
fingerprints. Only three Domain files have production changes. Optional callbacks
are not wired through Application, RPC, settings or persistence. No schema,
permission, localization or dependency change. Removing the callback plumbing
rolls back the feature without a data migration.

## Reproduction

From the repository root, using the declared project/test dependencies and Node:

```sh
OPENBLAS_NUM_THREADS=1 python scripts/research_direct_kerf.py \
  --budget 5 --repeats 2 --limit 16 --finish-seconds .5 --output /tmp/direct-research.json
python -m pytest -q almdina_erp/tests/test_direct_kerf_research.py
```

Source baseline: `bcbe2b815da63b30c039f0cafb1b3e0c34f0661d`.
Measured runtime: Python 3.12.14, Node 24.22.1, ezdxf 1.4.4 on Linux. Optional
OR-Tools is unavailable in this runtime; no dependency/configuration was changed
to disable it. CI uses its own declared environment.
The fixture reconstructs matched rectangular DXF sizes/quantities and observed
source-axis/contour order from the supplied archive, with source file SHA-256s.
Consecutive equal sizes are grouped without reordering. Identities are synthetic,
all rotations are permitted, and original DCO addons/grain constraints are not
claimed. Research uses mandatory trim 3 mm and Kerf 5 mm. Cases 235/325/3688
confirm on previously unbenchmarked board dimensions, not live production data.
Case 3700 is a previously observed raw-rank opportunity control.

## Measurement contract

- Each search/completion uses a fresh sequential Linux worker. Order alternates
  across repeats. Full evaluation/signatures are deferred; stored raw copies are
  evaluated once. Capture is not attached to production Application/RPC.
- The collector retains at most 16 immutable JSON pairs / 16 MiB, using a deterministic
  attempt key independent of optimizer RNG. Temporary copies/encoding and Python
  overhead are measured separately. No unbounded rejected-key set is retained.
- Sensitivity 4/8/16 uses nested subsets of the SAME stream, not differently timed
  searches. Byte limits did not bind; oversize rejection is tested.
- RSS uses `/proc/self/status` VmHWM for the current worker address space at the end
  of timed work, before output materialization (not inherited pre-exec `getrusage`).
  Wall time, CPU and cooperative-deadline overruns are explicit in the CSVs.
- Alignment is the fraction of Kerf-adjacent pairs sharing a perpendicular edge
  endpoint. Size splits count extra boards per repeated dimension family; small
  piece splits use the smallest-area repeated family. These are not CNC timings.
- Nomination requires valid completed arms, no extra boards/remnant loss, no worsening
  in alignment or size splits, and improvement in one organization metric against
  BOTH Expanded and the baseline Smart winner. Only nominees trigger JS/strict
  import in the tool; an additional captured-Direct roundtrip is an automated test.

## Result

Decision: **Reject production activation under the tested policy**. The observation
hook is useful, but restoring Direct has not beaten the existing completed Smart
winner in this sample. This is not a proof that no future schedule can help.

36 full-search observations (9 cases, two repeats, baseline/capture order reversed)
yielded 3,066 capture events and 238 retained pairs: 67 identical pairs, four
within-run geometry duplicates and 167 nonidentical pair comparisons. Counts include
repeats; they are not 167 independent globally unique layouts. Direct wins raw
industrial rank in 127 comparisons, and completed rank in 104. Organization improves
without the defined remnant/board tradeoff against paired Expanded in 89, but **zero**
Direct arms beat the corresponding baseline Smart rank or satisfy the joint
organization nomination against both comparators. No benchmark nominee was exported
because none qualified; the separate captured-Direct JS/strict witness passed.

| Case | Compared | Raw rank wins | Completed rank wins | Organization wins vs Expanded |
|---|---:|---:|---:|---:|
|107|25|23|21|17|
|232|30|24|18|14|
|243|16|12|14|10|
|3640|0|0|0|0|
|3687|30|26|26|24|
|235|2|0|0|0|
|325|16|10|4|4|
|3688|24|16|17|16|
|3700|24|16|4|4|

All compared arms pass the Domain gates; capture did not regress full-search board
counts in these runs. 243 stays on three boards. No discarded Direct event was
observed for 3640 in the sampled search; this does not assert its absence from every
possible ordering. Same-stream limits 4/8/16 produce 43/88/167 comparisons and zero
nominees at every limit. The largest retained payload was 2,112,019 bytes.

Paired capture-minus-baseline median wall time is -0.010 s (timing noise, not a
speedup claim); maximum added wall/CPU is 0.796/0.797 s on 3700. Median added search
RSS is 1,156 KiB and maximum is 2,088 KiB. Maximum deadline overrun is 0.435 s with
capture versus 0.411 s without; both are recorded, not treated as a hard deadline.
Observation has real cost despite not rerunning packers. No scheduling, ranking or
production activation is justified by these measurements.
