# Smart edge protection — verification

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

## Existing Develop failures — not weakened or bypassed

All six failures were reproduced unchanged in a separate clean worktree at `2367b8ff`:

1. `test_fingerprint_final_hardening.TestV3RequiredRepresentation.test_v3_schema_meaning_cannot_change_under_the_same_version`: reviewed V3 schema digest differs from current base.
2. Factory settings frontend architecture: existing controller has 261 lines against its 255-line contract.
3. Unified settings console test: four existing CNC preset fields are absent from the tested surface.
4. Translation catalog gate: invalid context columns.
5. Translation catalog gate: duplicate keys.
6. Translation catalog gate: malformed existing CSV rows.

Existing `factory_production_settings_view_model.test.js` also fails on clean base: it expects the removed algorithm display at row 5, which currently contains the trim value. That test remains unchanged. New policy translations are independently checked for exactly one well-formed Arabic row each.

These are merge blockers, not evidence of successful full CI. The Draft must remain unmerged until required checks are resolved. The new Frappe persistence/persona regression and standard install/migrate-twice require the real Frappe v16 CI environment. No production deployment or machine/NC certification was performed.
