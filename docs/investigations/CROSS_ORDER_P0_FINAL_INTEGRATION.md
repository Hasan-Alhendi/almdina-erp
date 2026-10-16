# Cross-order P0 — final semantic integration manifest

## Change contract and source fence (before merge)

- Goal: combine the certified cumulative P0 at `6cd990d251608cc3fece27d0204bd7c7c66db366` with Develop after merged PR #516 at `909fab12f9d17b0650a8b99c77db1710ff90fb2a`, retaining both contracts and certifying the result.
- In scope: semantic merge, targeted regression if a combined contract fails, isolated Desk/DB/HTML evidence, full PR CI and release review. Out of scope: feature redesign, production deployment, merge into Develop, changing Recovery behavior without a demonstrated defect, schema migration.
- Invariants: DocumentContext ownership/generation, Frappe Native Save, canonical Plan/Cost owners, frozen print source with post-await revalidation, dynamic capability and stage checks, trusted geometry, translated operator messages, Recovery DCO-only projection.
- Localization: preserve #516's English message IDs, Arabic catalog and parameter interpolation; preserve P0 print labels and translations, with unique keys. No new user-facing copy without a catalog entry.
- Expected files: Renderer and Arabic catalog only if semantic merge needs a targeted resolution; focused renderer/print/i18n tests, Recovery fixture/browser tests if coverage is missing, CI workflow and this report. No domain/optimizer, authorization or schema changes anticipated.
- Permission and financial data: no grant or read-scope change; financial Cost remains in its owner and capability boundary.
- Testing: Phase 1 15/15, Phase 2A 4/4, Phase 2B/3A, i18n and geometry, Recovery/Extra, pinned Desk and independent DB/HTML, full PR workflows. Rollback is to the prior application and matching assets; no migration rollback.

## Production origin and ownership

| Owner | Certified P0 contribution based on `6ff81adb` | Develop PR #516 contribution | Merge invariant |
| --- | --- | --- | --- |
| `core/door_cutting_order_document_context.js`; workspace registry/sync and action guard | Identity/generation invalidation, scoped async and permissions | No production delta | Keep distinct `isSameDocument` and active `isCurrent` semantics. |
| `order_entry/door_cutting_order_board_text_ux.js`, mutation policy and operator UX | Bind native form inputs and save to the original document visit | No production delta | No stale DOM to B; preserve current input and Frappe Save. |
| `cutting_plan/*workspace_state.js`, Plan presenter, tabs/source/preview and Plan UX/styles | Canonical row/visit ownership, first authorized plan action, draft isolation | No production delta | Preserve current row, revision, preview, capability and NEW promotion. |
| `costing/*workspace_state.js`, Cost presenter | Cost owner and visit guards; Cost GET may project only its financial setting/result compatibility fields, never board/piece inputs | No production delta | Keep financial edit drafts and permission scope, including re-projection during active Cost editing. |
| `cutting_plan/door_cutting_order_cutting_plan_renderer.js` | Freeze original frm token, row/revision/geometry/document/kerf/edge profiles/OFFCUT ownership and revalidate after await | Localize Liner error IDs and interpolate translated addon noun | Retain both the localized renderer messages and atomic printing, without copying untrusted DOM or a mutable frm. |
| `notes/door_cutting_order_notes_ux.js` and Document Context | Normalize jqXHR thenable before `.finally` | No production delta | Retain async ownership and cleanup. |
| `cutting_plan/secure_dxf_export.js`; `drawing/door_cutting_order_machining_overlay.js` | No P0 delta | Localized machining/DXF errors and existing manufacturing behavior | Preserve DXF geometry and translated placeholders. |
| `translations/ar.csv` | P0 Plan name/revision labels | Remove duplicate `Apply`; add machining/Liner catalog | One unique message ID each, translated placeholders retained. |
| Recovery production modules / DCO Detail schema | No Phase 3A Recovery code change | No #516 production Recovery code change | DCO-only projection, real child identity; verify Extra field capture and restore before release. |

Tests and docs under `almdina_erp/tests`, `.github/workflows` and `docs` are verification/contract evidence, not an alternate source of production authority. The pre-merge source tree is clean, #514 is an ancestor of #515, and both PRs remain Draft. Merge parents and final evidence will be recorded below after integration.

## Semantic merge and focused verification

The temporary candidate branch merged `909fab12` with two parents: its manifest commit on #515 (`94c2b998`) and current Develop. Git reported no textual conflicts. The renderer's P0 frozen source, canonical row/revision/geometry, document token, post-await authorization and machining inputs coexist with #516's translated error IDs and addon noun substitution; the Arabic catalog retains one key per message. No production file needed an integration edit. The 15 Phase 1 checks, four Phase 2A ownership checks, Native Save checks, ten original print transition checks, thenable checks, renderer/i18n, DXF, machining and Recovery projection focused checks passed locally. The combined result is not certified from those local tests alone.

An additional final HTML test uses the actual PlanTabs handler with a canonical System row, revision 7 and a liner narrower than the frozen kerf. It checks the Arabic machining error code/message in the written print document, alongside the source row identity and revision. Its fixture includes the required zero offset; without it the drawing cannot generate this particular machining error. The expanded transition suite is 11/11 locally.

The pinned Desk workflow now includes a separate NEW Extra test. It checks Liner, Back Groove and Recessed Handle on three distinct child rows across checkpoint, Start New cancel, Continue restore and first Native Save, plus B isolation. `audit_db` reads the saved document in a separate bench process and checks every configured Extra field and unique real child names. The browser and independent DB artifacts are `recovery-extras.json` and `database-audit.json`. This added runtime gate is pending execution; it is not evidence of a passing Desk lifecycle yet.
