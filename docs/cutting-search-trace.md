# Cutting search report — change contract and coverage

Base: Develop `41d438001c5dfa9b146907c93d24b8490dd23150` (fetched 2026-11-18).
Branch: `feature/cutting-search-trace-report`.

Goal: opt-in, read-only evidence of the actual preview execution, downloadable
as offline HTML and JSON from one immutable recorded dataset.
Scope: observer, report projection, temporary private storage, capability and
existing preview/gallery controls. No optimizer ranking, manufacturing geometry,
plan settings fingerprint, save, historical snapshot or DXF contract changes.
Domain owns only the observer port/context and observation calls; Application
collects evidence; Infrastructure stores it; Presentation renders it.
No DocType or data migration. New capability is never granted by default.
UI strings use English message IDs and the existing Arabic translation catalog.
Tests cover disabled behavior, actual hierarchy, comparison keys, geometry,
resource loss, isolation, continuation, exact save and offline rendering.
Rollback: remove feature code; expiring reports require no historical migration.

## Coverage matrix (prepared before instrumentation)

| Actual boundary | Generates/receives | Can lose/reject | Minimum observation |
|---|---|---|---|
| `optimize_order_plan` / `_run_engine` | expanded inputs, mandatory trim, warm seeds | fallback, invalid projection | enclosing spans, input fingerprint, returned gallery |
| `auto_fast` / `run_single_method` / `_run_preordered_method` | actual packer order and raw arrangements | incomplete pack, direct/expanded kerf selection | attempt spans and returned geometry; kerf boundary observations |
| `smart_search.finish_batch` | up to 12 unique raw arrangements | only leader/diverse second finished; deadline/8 completion limit | whole batch, actual choices, promotion or skip reason |
| `_finish_plan_search` | baseline → Glass → shape → repair (plus conditional retry) | importability, validation, permissions, industrial comparison | nested function spans, each generated result, actual gate reason |
| `smart_search.offer` / `retain_diverse_finals` | validated finals | duplicate, rank, five-slot/coverage retention | rejection event, exact ranks, before/after portfolio |
| `improve_plan_search` / `_accept_candidate` | consolidation, repack, compaction, cancellation, remnants | failed repair, deadline, rank, validation | generator/attempt spans and explicit gate reasons |
| `improve_fixed_board_layout` (ALNS) | operator proposals/repairs | pinned geometry, count, remnant, duplicate, network/validation | attempt start/end, candidate, real operator rejection |
| `refine_system_layout.offer` | compound/rigid/skeleton proposals | duplicate, guard, final comparison, Pareto pruning | offer attempt, checks, comparison and portfolio changes |
| `PatternPool.add` / `refine_pattern_layout.offer` | individual board patterns / reconstructed complete plans | pattern limits, invalid shape/count, duplicate, final rank | pattern attempt distinguished from a completed plan; offer evidence |
| `refine_corner_layout.offer` | frames, cover solutions, guest exchanges | validation, duplicate, final rank | real attempt spans, reconstruction geometry, comparisons |
| `_snapshot_outcome` | physical trim, centering, alignment, manufacturing validation | invalid projection, unchanged/regressed proposal | raw→physical child link, validation result, returned geometry |
| `final_system_sort_keys` / `_candidate_is_better` | actual competing plans | legacy fallback, first differing criterion | keys returned by existing comparator, measured availability, decisive field |
| `optimize_order_plan` gallery mutations | native, post-ALNS, post-Pattern, post-Corner | duplicate projected geometry, five slots | actual gallery before/after each applied stage |
| `_build_session` | server validation, safe snapshots | validation issues, duplicate, cap | rejected/published geometry and final preview IDs/fingerprints |
| `merge_preview_candidates` | current and previous rounds | duplicate, shared final sort, cap | prior gallery, exact comparator, merged result, parent report |
| `commit_cutting_plan_preview` | existing trusted selected snapshot | stale/expired checks | no recomputation; report storage independent of consumed token |

Coverage is bounded by explicit instrumentation, not inferred from a fixed stage
list. Inner placement-coordinate probes are not plans. Unobserved boundaries or
observer errors produce PARTIAL; limits produce TRUNCATED with dropped counts.
Wall-clock budgets remain authoritative: observation can reduce the number of
attempts in a timed run; it must never extend deadlines or change comparators.

## Use and retention

1. Grant `download_cutting_search_report` through the existing Permission Matrix.
   Administrator follows the existing bypass. Other roles receive no default
   grant. Viewing the System plan and reading the DCO are also required.
2. In the existing System-plan controls, enter the normal edit/recalculate flow
   and enable **Record search details / تسجيل تفاصيل البحث**. It starts unchecked.
   The checkbox follows the existing recalculation capability, assignment and
   lifecycle gates. It is a diagnostic RPC argument, never a manufacturing setting.
3. Recalculate and review the ordinary gallery. **Download HTML / تحميل HTML**
   and **Download JSON / تحميل JSON** refer to that execution. Download does not
   run the engine. HTML opens locally without a server, internet or libraries.
4. Continue Search creates the next linked report and embeds the previous round.
   The report's round selector opens each round's own timeline, candidates and
   comparisons. Merge events identify prior/current/retained preview candidates.
5. Exact Save still commits the selected server snapshot. Download links remain
   available during the form visit after its preview token is consumed. Reports
   and saved download URLs expire after **24 hours**; the ordinary preview TTL
   and three-round limit are unchanged. A browser reload does not restore the
   in-memory download buttons; an already saved URL remains subject to server
   authorization and the report TTL.

Artifacts live in compressed, private Redis values scoped by site, owner and
order, with `expires_in_sec=86400`. Redis expiration owns cleanup. There are no
public URLs, File records, new DocTypes, snapshot fields or migrations. Capability,
System-plan access and DCO read permission are rechecked on every download;
knowing a report ID is insufficient. JSON is diagnostic evidence, never an input
accepted by Save/Approve. Cost/price/rate fields are excluded from piece evidence.
Report persistence failure logs the problem, tells the user, and returns the
already validated preview with its existing exact token.

## JSON v1.0 contract

The exported JSON object is the source of truth. HTML embeds that same object in
`script#evidence` using script-safe JSON escaping and renders via DOM text nodes.
There are no external resources or HTML interpolation of order data. CSP blocks
network resources, frames, forms and base-URL changes. Four pages render summary,
actual nested execution, searchable/paged candidates, and selection evidence.

| Field | Type and meaning |
|---|---|
| `schema_version` | String `1.0`; consumers should reject an unsupported major version |
| `report_id`, `run_id` | Independent random 32-character hexadecimal identifiers |
| `round_id`, `parent_run_id` | Zero-based integer round; previous run ID or null |
| `preview_id` | Real server preview token reference, or null for isolated engine witnesses |
| `engine_version`, `git_sha` | Existing engine version and deployed Git revision; unavailable Git metadata is disclosed |
| `input_fingerprint`, `settings_fingerprint` | Existing preview fingerprints; recording does not enter either input |
| `input_specification`, `effective_settings` | Operational board/optimizer/piece inputs when observed, and server-normalized settings; not replacement save data |
| `events` | Ordered evidence, with integer `seq`, elapsed seconds where applicable, `kind`, active `span_id`, candidate IDs and actual reason/data |
| `spans` | Real calls/generators: ID, parent ID, kind, name, input order/parameters, input/output candidate IDs, start/end sequence, duration and stop reason |
| `attempts` | Attempt-kind spans using the same `span_id`; not a fabricated list of optimizer phases |
| `candidates` | Map by observation identity: geometry signature + observed industrial rank + method. Includes source, parent candidate, inventory completeness, validation evidence, status and ordered reasons |
| `geometries` | Map by existing geometry signature. Each layout is stored once with sheet dimensions and actual material `outline_cm` / `holes_cm`, units cm |
| `decisions` | Actual comparison events: comparator, keys, criterion order, measured cutter availability/profiles, ranked IDs, first decisive criterion and adjacent comparisons |
| `gallery_history` | Actual before/after/removed candidate IDs, policy reason, related comparison sequences; continuation also records preview candidate IDs |
| `final_gallery`, `preview_gallery` | Ordered final candidate/geometry identities and the server preview ID/signature mapping. Final publication is reserved even when the search-event quota is exhausted |
| `previous_round`, `previous_report_id` | Previous immutable dataset/ID when recorded; unavailable prior evidence is explicitly disclosed |
| `coverage_manifest` | Status, observed boundaries, limitations, losses, omitted geometries, observer errors and unclosed spans |
| `data_fingerprint` | SHA-256 of canonical UTF-8 JSON after removing this top-level field |

Canonicalization: Python `json.dumps(data, ensure_ascii=False, sort_keys=True,
separators=(',', ':'), allow_nan=False)`. HTML and JSON contain identical report
IDs and hashes. Embedded previous-round hashes retain their independent meaning.
The benchmark additionally records source-file SHA-256 values and a combined
source fingerprint so witnesses from a working tree remain auditable.

`complete` means full piece inventory placed, with no unplaced pieces. It does
**not** certify manufacturing validation, export, machine-ready NC, or optimality.
A board pattern containing a subset of the order is incomplete even if its own
`unplaced` list is empty. An arrangement can be observed more than once with
different ranks; geometry remains deduplicated. Missing/unproven contours are
disclosed and omitted rather than drawn as bounding rectangles. Glass holes and
L/Clipped contours come from the existing manufacturing geometry functions.
The coordinate system is the existing sheet top-left origin, x right and y down;
SVG preserves it without an additional reflection.

Rank keys are the original signed sort values (lower sorts first). Their actual
order is preserved: industrial inventory/boards/machine/remnant criteria, then
measured cutter-center criteria when available, then the remaining industrial
criteria. Unsupported measured geometry uses the existing all-legacy fallback.
The report explicitly warns that largest eligible remnant area does not prove
best industrial reuse. Diversity reservation and board-pattern dominance are
reported as their own policies rather than attributed to the final comparator.

## Evidence boundaries and failure semantics

The request-local ContextVar port contains no Frappe, storage or rendering.
NullSink avoids binding inputs/collecting geometry when disabled. Generator
contexts are restored between yields; exceptions close their spans, and nested
or concurrent requests do not share a collector. Observation failures cannot
change a manufacturing result; their independent counters are retained.

Default limits are 30,000 search events and 16 MiB deduplicated geometry per
round. Limits never change optimizer deadlines or selection rules. Reaching
them yields `TRUNCATED`, explicit loss counts and an `evidence_loss` event;
final preview identities remain available even if geometry cannot be retained.
Open spans, missing source/parent evidence and observer failures yield `PARTIAL`.
`COMPLETE` is permitted only with no known limitations/losses/errors/open spans.

V1 conservatively declares **PARTIAL**: placement-coordinate probes, internal
CP-SAT states and uninstrumented internal pruning are not exhaustively captured.
It records real calls, returned/yielded arrangements and instrumented rejection
gates, not every transient placement in every packer. `returned` is explicitly
the observed function return; it is not a fabricated claim of solver exhaustion.
Generic/combined guard reasons retain their actual meaning and are not narrowed
to a cause that was never measured. The coverage matrix describes boundaries,
not a claim that every inner branch has been instrumented.

## Changed layers and purpose

| Files/group | Why |
|---|---|
| `domain/cutting/search_trace.py` | Optional observation port, safe request-local scope and real call/generator spans |
| Existing Domain optimizer/packing/validation/ALNS/Pattern/Corner modules | Small decorators and evidence calls at the coverage-matrix boundaries; no comparator/geometry policy change |
| `application/cutting/search_report.py` | Bounded collector, deduplicated contours, actual decision projection, canonical hash and explicit coverage |
| `application/cutting/optimize_order_plan.py`, `plan_preview_session.py` | Observe physical projection, final galleries and round merge; additive optional report ID in the private session |
| Existing capability catalog and Permission Matrix | One explicit download capability and System-plan view dependency; no default recalculate grant |
| `infrastructure/frappe/cutting_search_report_store.py` | Private compressed site/user/order-scoped TTL artifacts with integrity verification |
| `services/cutting_search_report_service.py`, existing preview service | Authorized opt-in creation, linked rounds, publication and download, independent of exact-token consumption |
| `presentation/cutting/search_report.html`, `search_report_html.py` | Offline Arabic RTL four-page projection of recorded JSON only |
| Existing workspace API, preview session and plan controls JS | Separate diagnostic argument, stale-response ownership, default-off checkbox and two existing-surface download links |
| `translations/ar.csv` | Official Arabic messages for new user-visible copy; existing historical catalog defects left unchanged |
| Report unit/access/browser tests and preview ownership tests | Real observer, isolated adapters, offline DOM/SVG/XSS, lifecycle/permission/refresh and exact-token contracts |
| `scripts/benchmark_search_report.py`, report workflow | Reproducible isolated-process measurements, real engine artifacts, three-round merge witnesses and CI artifact retention |

## Reproduction and release limits

```bash
python -m pip install '.[test]' playwright
python -m playwright install chromium
python -m pytest -q almdina_erp/tests/test_cutting_search_report.py \
  almdina_erp/tests/test_cutting_search_report_access.py \
  almdina_erp/tests/test_cutting_search_report_browser.py
python scripts/benchmark_search_report.py --output /tmp/search-trace
python scripts/benchmark_search_report.py --continuation --output /tmp/search-trace
```

`CHROMIUM_PATH` can point at an existing Chromium binary. On this Windows host,
Python is invoked with `-E` because the host's unrelated PYTHONHOME points to a
different runtime. The new workflow retains JSON, HTML, benchmark and JUnit
artifacts. See the delivery results for measured overhead and inherited failures.

There is no connected isolated Frappe site/customer DCO in this environment.
Engine witnesses use real Application/Domain execution on committed fixture
dimensions, including reference input 298. Authorization/cache tests use isolated
Frappe facts/adapters; they are not a claim of a deployed ERP end-to-end run.
Redis deployment behavior and live DCO Preview → Exact Save → Reload → DXF still
require the existing site integration gates before production rollout. No
production deployment, historical snapshot rewrite or automatic merge is made.
