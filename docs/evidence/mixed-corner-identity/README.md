# Mixed corner identity discovered during geometry-quality research

Baseline: `e1fe07225ae6ecb4e126faf222278a91cfa94811`.

## Change contract

Goal: preserve real corner identity when equal-size Glass/Regular rows coexist.
Scope: the existing strict-import candidate selector; one condition now invokes
the existing full-contour matcher for a geometrically classified corner even
when some dimension matches are noncorners. No optimizer, ordering, ranking,
centering, trim, Kerf, snapshot, permissions, financial, schema, localization or
historical-data changes. No manufacturing tolerance is relaxed. Revert the
selector change to roll back; no migration is needed.

## Reproduction and root cause

A five-second run of the existing `P5-joint-different` sources retained a valid
two-board alternative behind its one-board winners. Its first exported contour
was a 40 x 40 cm clipped corner; an L and a nonrotatable Glass had the same outer
size. The actual JS export failed full Strict Import with
`PIECE_IDENTITY_AMBIGUOUS; PIECE_MISSING`. Four earlier alternatives passed.

`_find_exact_candidate` previously consulted `_unique_corner_contour_candidate`
only if **all** remaining dimension matches were corners. The direct pass
included Glass and fell back to the first L row. The rotated pass excluded the
nonrotatable Glass and geometrically identified the clipped row. The strict
contract then saw two different corner identities. Legacy-ingested corner
metadata alone does not prove identity and must not override the contour.

The fix keeps dimension and rotation gates, then uses the existing contour
matcher when the imported outer ring proves a corner. Its notch matching,
ambiguity handling, edge binding and permissions remain authoritative. There
is no new geometric matcher and no fallback to guessing a source row.

## Deterministic tests

`test_mixed_corner_dxf_identity.py` records the failing placement independently
of time-budgeted search. It asserts geometric/permission validity, JSON reload,
actual JS export, full Strict Import, six preserved instance identities and
correct L/Clipped/Glass/Regular row types. Twenty-four parameterized checks cover
both corner kinds, Glass/Regular distractors and all six inventory orders.
Three negative checks preserve genuine row ambiguity and reject a wrong notch.

Before the fix the initial 25-case regression command had **17 failures / 8
passes**, including the actual export/import witness. After the fix:

```sh
python -m pytest -q \
  almdina_erp/tests/test_mixed_corner_dxf_identity.py \
  almdina_erp/tests/test_corner_dxf_edge_binding.py \
  almdina_erp/tests/test_strict_dxf_persisted_cut_contract.py \
  almdina_erp/tests/test_dxf_manufacturing_identity.py \
  almdina_erp/tests/test_dxf_topology_persistence.py \
  almdina_erp/tests/test_dxf_hole_topology.py

python -m pytest -q \
  almdina_erp/tests/test_mixed_corner_dxf_identity.py \
  almdina_erp/tests/test_geometry_first_nesting.py \
  almdina_erp/tests/test_joint_nesting.py
```

The first command passed 218 tests before the final three negative checks were
added; the second passed **90 tests**, including all final 28 new cases. Counts
overlap and must not be summed as unique coverage. The new file is explicitly
included in Static Checks.

The existing benchmark/verification scripts were also run over all eight P4
and eleven P5 source cases, with a five-second budget:

```sh
python scripts/benchmark_joint_nesting.py \
  --cases-file almdina_erp/tests/joint_nesting_cases.py \
  --label audit --time-limit 5 --output /tmp/p4.json
python scripts/benchmark_joint_nesting.py \
  --cases-file almdina_erp/tests/geometry_nesting_cases.py \
  --label audit --time-limit 5 --output /tmp/p5.json
python scripts/verify_cutting_benchmark_dxf.py \
  --input /tmp/p4.json --input /tmp/p5.json \
  --expected-rejected-case P5-addon-ambiguous --output /tmp/strict.csv
```

Re-importing the exact recorded portfolio bytes changed **88/89 to 89/89**
successful positive roundtrips; all 18 positive cases now pass every retained
alternative. `P5-addon-ambiguous` remains rejected before export. No geometry or
board allocation changed. Thirteen additional recorded regular/oracle/pair
snapshots passed actual export/import, including 243 at 0/.1/1/2/3 mm trim.

## Limits

This fixes a manufacturing roundtrip defect, not the remaining layout-quality
gap. It does not claim optimal nesting, designer-level arrangement or a CNC
time reduction. P4/P5 sources are synthetic; customer DXF geometry reconstructs
sizes/quantities with test identities and permitted rotations, not live DCO
machining or material provenance. Local tests use the existing Frappe stub;
native Frappe is covered by the branch's integration workflow, not a local site.

The wider audit found that extra pair orderings alone did not repair canonical
243: 108 pair trials produced only three valid two-board pair packings and no
better final existing rank. Supplying designer board membership diagnostically
allowed existing packers to recreate three boards, but the resulting network
was longer than the incumbent despite its better edge-line rank. Thus no
unproven ordering/ranking/centering/search-policy change accompanies this fix.
