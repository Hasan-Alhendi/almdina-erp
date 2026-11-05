# Same-count layout quality

Goal: improve a valid regular/full-board Smart winner within its existing deadline.
Only Domain `plan_search.py` and `optimizer.py` change production behavior. No seed,
industrial ranking, mandatory trim, Kerf, shape/OFFCUT policy, snapshot/fingerprint,
permission, localization, dependency or schema change. Reverting this patch needs no migration.

## Evidence and reproduction

Baseline: `76698c5ae2fcd89e50598773578b101203e98329`. Linux, Python 3.12.14,
Node 24.22.1, ezdxf 1.4.4; OR-Tools unavailable locally (CI installs declared dependencies).
Workers run sequentially with alternating arm order, identical five-second Application
budgets, isolated CPU/wall/VmHWM RSS measurements, and actual final snapshot metrics.

```sh
python scripts/benchmark_layout_quality.py --repeats 3 --output /tmp/layout.json
python scripts/benchmark_layout_quality.py --cases 243-canonical --trim-mm 0.1 --repeats 2 --output /tmp/trim.json
python scripts/benchmark_layout_quality.py --cases 3687 243-canonical --budget 1 --repeats 2 --output /tmp/short.json
python scripts/benchmark_layout_quality.py --worker --variant validation-only --case 3687 --output /tmp/ablation.json
python -m pytest -q almdina_erp/tests/test_same_count_layout_quality.py
```

`observations.csv`: 54 corpus observations (nine cases, three repeats), 20 canonical
243 margin controls (0/.1/1/2/3 mm, two repeats), 16 short-budget controls (.4/1 s),
six validation-only ablations. All 45 candidate final snapshots serialize/reload and
pass actual JS Export → Strict Import. 107/3640/3700 were not used to tune this repair.
All inputs reconstruct DXF geometry, synthetic identities, allowed rotations and full
boards; they do not establish original DCO/addon/material provenance. The two 243
fixtures have the same dimension multiset but different source axes/grouping/order.
Both 3687 DXFs contain three full-size outlines/42 matching rectangles; neither
encodes an actual OFFCUT record or the alleged “نقص” board's ownership/source.

## Result and bounds

3687 reproduces in all three matched runs: raw adjacency alignment 37/70→42/74,
size splits 5→4, edge-line estimate 102→91, same three boards/2.125714 m² remnant.
After real Application centering: 35/70→39/74, 107→100 lines, cut-span estimate
6675.3→6795 cm (+119.7 cm). Median wall/CPU: 5.754→5.276 s; peak RSS 21084→20716 KiB.
Validation-only retains the old geometry: deduplication alone does not solve 3687.
All other corpus geometries retain their organization metrics/boards/remnant.

Canonical 243 stays three boards at all five five-second margin controls. At 3 mm
its organization is unchanged; zero/one-mm gains also occur with validation-only.
At .1 mm alignment slightly falls (42.11→41.94%) while lines/span improve (125→123,
8404.68→8350.04 cm). This is a search-timing/ranking tradeoff, not a pair-repair claim.
No observed board/remnant regression; five-second controls are faster and use less
RSS. At one second canonical 243 stays four boards in both arms, with a 0.110 s
worst wall increase; no three-board guarantee is claimed for those short budgets.
Application finalization already exceeds requested time (explicit in CSV); the repair
uses the original Domain deadline, at most .25 s/5% reclaimed only after an area
proof of minimum boards. No extra post-deadline search budget is appended.

Acceptance uses existing rank/full validators plus nonworsening adjacency alignment
and size splits; max three pairs/64 pieces per packing call. Protected shapes,
nests, baked geometry, OFFCUT and Panel Saw skip this movement. The existing board
cancellation area guard remains unchanged. No new ranking weights or CNC-time claim.
The bounded neighborhood is not a proof of designer-level or globally optimal packing.
