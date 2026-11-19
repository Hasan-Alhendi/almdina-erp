# Smart edge protection — verification

Historical first iteration. Its whole-sheet movement policy is superseded by
[geometry-aware coupled final placement](geometry-aware-final-placement.md).
The results below describe the earlier implementation commits only.

Base: `Develop` at `2367b8ff`. Branch: `feature/smart-edge-protection`.

## Change contract

- Goal: retain existing centering; apply the smallest safe protection translation on ineligible axes.
- Scope: existing factory cutting settings, final System projection, temporary Preview freshness and operational snapshots.
- Invariants: mandatory trim, packing inputs/priorities, board count, piece identities/dimensions/rotation, internal Kerf and cutter connections, immutable saved plans and manufacturing fingerprint versions.
- Permissions: existing `EDIT_FACTORY_CUTTING_DEFAULTS`; no new capability or endpoint.
- Data: two non-negative finite Float fields, default zero; standard DocType sync only. No historical backfill or snapshot rewrite.
- Localization: existing Frappe translation path with five new Arabic catalog entries; existing locale direction ownership.
- Rollback: disable both margins with zero. Special/attached/nested geometry and OFFCUT are conservative no-ops.

## Policy and pipeline

Mandatory Trim → existing per-axis centering → existing compaction/final alignment → edge protection → full validation → Snapshot → existing save/export gates.

Protection subtracts the existing physical trim from its target rather than adding another trim. A whole sheet's regular group translates rigidly, independently per axis; no per-piece repacking. Existing gap eligibility still checks both sides individually. A useful remnant may lose only the small movement strip and must retain one connected eligible successor. Actual cutter length/segments/continuity and full geometry/permission checks guard every proposal. Adapter rejection restores the validated pre-protection result.

New snapshots preserve both policy values and compact `edge_positioning` decisions. Preview settings hashes include the policy; a live policy mismatch or a generation-time mismatch rejects the preview. Manufacturing fingerprints V1–V4 are unchanged.

## Local evidence

Python 3.12.10, project test environment; `python -E` avoids the host's unrelated Python home setting.

- `test_edge_protection.py`: **78 passed**, including native search/continuation, all five controlled gallery candidates, zero/positive Kerf and Trim, atomic rollback, factory authority, Preview rejection, snapshot reload, real JavaScript DXF export and strict re-import with matching coordinates.
- Related cutting/application/Preview/history/factory/localization suite (18 modules): **367 passed, 1 skipped, 153 subtests passed; 6 failures** listed below.
- JavaScript: new `factory_edge_protection.test.js`, existing settings RTL/LTR, candidate gallery and Preview ownership tests passed. Modified production JS syntax and Python compilation passed. `git diff --check` passed.
- Final isolated policy/DXF/native-search run: **115 passed**, including all five trim variants in the existing 243-case manufacturing/export/strict-import regression and joint Glass/L/clipped nesting. Earlier concurrent wall-time-limited runs produced varying native layout assertions; the isolated run passed without weakening tests. A factory-settings attribute-access regression exposed by the broader run was fixed and its existing Recalculate/lifecycle tests passed.

## Existing Develop failures and required localization repair

The initial related run's six failures were reproduced unchanged in a separate clean worktree at `2367b8ff`:

1. `test_fingerprint_final_hardening.TestV3RequiredRepresentation.test_v3_schema_meaning_cannot_change_under_the_same_version`: reviewed V3 schema digest differs from current base.
2. Factory settings frontend architecture: existing controller has 261 lines against its 255-line contract.
3. Unified settings console test: four existing CNC preset fields are absent from the tested surface.
4. Translation catalog gate: invalid context columns.
5. Translation catalog gate: duplicate keys.
6. Translation catalog gate: malformed existing CSV rows.

The real Frappe run then proved that the malformed CSV also fails the strict catalog loader. To satisfy the new Arabic settings contract, 19 existing English source fields containing commas were quoted and 13 shadowed duplicates removed, retaining Frappe's last effective translation. No text was rewritten. The existing translation gates now pass: the policy/localization run reports **110 passed, 10 subtests passed**. The real-parser regression additionally asserts both new Arabic field labels.

Other failures remain outside this change: the existing settings view-model JS test expects a removed algorithm display at row 5; CI also finds existing CNC button-style, drawing-text endpoint, asset-batch and ownership/audit contract drift. No tests or reviewed fingerprint hashes were weakened. The Draft must remain unmerged while required checks are unresolved.

On implementation commit `f82f2027`, real Frappe v16 installation and **migrate twice passed**, as did the new persistence/persona regression. Its full suites reported 2013 tests (11 failures, 1 error) and 131 site tests (1 catalog-parser error, 1 skipped); the catalog failures prompted the prerequisite repair above. No production deployment or machine/NC certification was performed.
