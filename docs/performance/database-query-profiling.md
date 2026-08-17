# Database query profiling

P5 uses database evidence before changing indexes or query structure. The profiler in
`almdina_erp.almdina_erp.infrastructure.frappe.hot_query_profiler` is intentionally a
Bench-only diagnostic: it is not a whitelisted HTTP method, it does not accept caller
SQL, and it only runs `EXPLAIN SELECT` for fixed shop-floor query shapes.

## What is profiled

The current profile covers the high-frequency `Production Stage` reads used by:

- worker inbox ordering,
- administrator inbox ordering,
- worker archive ordering,
- administrator archive ordering,
- personal order assignment/completion timing used by the Door Cutting Order list.

The first four profiles can run with only a representative user. The personal timing
profile is included when one or more representative Door Cutting Order names are
provided. At most 100 order names are accepted so a diagnostic invocation cannot
accidentally construct an unbounded `IN (...)` plan.

## Run on a representative site

Use a real worker account and a small sample of real order names from the same site:

```bash
bench --site <site> execute \
  almdina_erp.almdina_erp.infrastructure.frappe.hot_query_profiler.profile_hot_queries \
  --kwargs '{"user":"worker@example.com","order_names":["DCO-2026-00001","DCO-2026-00002"]}'
```

The command is read-only. It does not create, alter, or drop indexes and it does not
change order or production data.

## Read the evidence

Each EXPLAIN row is normalized to the fields that matter for a first pass:

- `table`: table or alias examined by the optimizer.
- `access_type`: MariaDB access method. `ALL` is a full table scan and deserves
  attention when the estimated row count is meaningful.
- `possible_keys`: indexes the optimizer considered.
- `selected_key`: index actually selected.
- `estimated_rows`: optimizer estimate of rows examined.
- `filtered_percent`: estimated percentage surviving the predicate.
- `extra`: optimizer notes such as `Using filesort` or `Using temporary`.
- `risk_flags`: neutral evidence markers (`full_scan`, `no_selected_key`, `filesort`,
  `temporary_table`). They are not automatic index recommendations.

Interpret results comparatively. A `filesort` over a handful of rows may be cheaper than
maintaining another index, while a repeated `ALL` scan over a growing Production Stage
table is much stronger evidence.

## Evidence required before an index change

Do not add an index from field names alone. For every proposed index, capture:

1. the query id and representative workload,
2. EXPLAIN before the change,
3. the candidate index and why its column order matches equality/range/order predicates,
4. EXPLAIN after the change,
5. affected write paths and expected maintenance cost,
6. regression tests and migration/idempotency coverage.

Prefer the smallest index that measurably improves a hot query. Avoid near-duplicate
indexes and do not optimize only for Administrator views if the dominant workload is a
worker-scoped query (or vice versa).

## Current P5 boundary

This profiling phase deliberately makes no schema changes. The next database phase may
add indexes only after representative EXPLAIN output from the deployed site proves that
they are justified.
