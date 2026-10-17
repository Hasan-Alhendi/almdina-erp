# Almdina Design System — Token & Layer Ownership

> **Status:** Presentation contract (Phase 0 freeze)  
> **Authority:** Complements `docs/reference/13_FRONTEND_ARCHITECTURE.md` (`FE-ARCH-016`)  
> **Scope:** Visual identity only. Never owns business rules, capabilities, costing, or lifecycle.

## Goal

Stop Feature CSS from inventing parallel design systems (`apc-*`, `aps-*`, `aw-*`, …) for brand, radius, shadow, typography, spacing, and semantic status.

Feature CSS may keep **domain/layout** tokens. It must not redefine **foundational visual grammar**.

## Namespace ownership

| Prefix | Owner | Allowed contents | Forbidden contents |
|---|---|---|---|
| `alm-*` | Design System | brand/semantic colors, typography, spacing, radius, shadows, focus, button/control heights, shared components/patterns | Feature geometry, DCO column widths, kanban layout, stage rails |
| `apc-*` | Factory Permissions | permission-matrix layout, capability grouping chrome | brand hex, radius/shadow/type/space scales, status palettes |
| `aps-*` | Factory Production Settings | section accent mapping to DS tones, settings panel layout | independent radius/shadow/brand scales |
| `aw-*` | Factory Workforce | workforce table/card layout | independent radius/shadow/brand scales |
| `prw-*` | Factory Master Data / Routing | stage rail, editor geometry, workflow story layout | independent brand/status scales (alias `--alm-*`) |
| `sf-*` | Shop Floor | kanban columns, board geometry, production-card hierarchy | independent brand/radius/shadow scales (alias `--alm-*`) |
| `dco-*` | Door Cutting Order | measurement grid, plan canvas, edge rendering, sticky measurement geometry | brand/status/type/space scales that belong to DS |
| `apa-*` | Factory Plan Archive | archive list/layout specifics | foundational DS primitives |

## Layer ownership

| Layer | Files (target) | Owns |
|---|---|---|
| Foundations | this doc + `FE-ARCH-016` | Frappe-native first, RTL/Arabic-first, presentation-only, no business logic |
| Tokens | `public/css/almdina_design_tokens.css` | all foundational CSS variables |
| Components | `public/css/almdina_components.css` + `AlmdinaUi` | buttons, controls, empty, card, panel, badge, status, state |
| Patterns | `public/css/almdina_patterns.css` | page intro, toolbar, summary cards, section header |
| Page templates | `public/css/almdina_page_templates.css` | admin / workbench / list / transaction page-family grammar |
| Feature presentation | Feature CSS/JS | domain layout only; consume DS tokens/components/patterns |

## Shared CSS leakage rule

Shared DS stylesheets (`almdina_design_tokens.css`, `almdina_components.css`, `almdina_patterns.css`, `almdina_page_templates.css`) must not introduce Feature selectors such as `.apc-*`, `.aps-*`, `.aw-*`, `.prw-*`, `.sf-*`, `.dco-*` except entries on an explicit temporary allowlist in `test_design_system_contract.py`.

Current allowlist: **empty** (Phase 6). The former entries were resolved as:

- `.dco-plan-tabs` active-tab underline — removed from shared CSS; it was fully shadowed by the plan-content owner (`door_cutting_order_plan_content_styles.js`), which remains the single owner.
- `.dco-tab-edit-toolbar` compact button sizing — replaced by the generic `.alm-actions--compact` component; the DCO toolbar opts in via class.

## Migration policy (presentation only)

1. Prefer aliases first: `--apc-radius-md: var(--alm-radius-md)`.
2. Do not change Domain/Application/Services, capabilities, RPC payloads, or Frappe page-action ownership.
3. Do not replace measurement grids, cutting boards, permission matrices, or shop-floor drag logic with new widgets.
4. Migrate Admin Console pages before Workbench, Lists, then DCO.
5. One surface family per PR when class/markup swaps begin.
6. Admin status/risk badges use `AlmdinaUi.badge()` + `.alm-badge--*`; Feature CSS may keep layout sizing (`.aw-badge`, `.apc-badge`, `.aps-status-pill`) but must not own status palettes.
7. Workbench — Factory Master Data overview (migrated): intro/summary/toolbar via patterns (`prw-hero alm-page-intro`, `prw-summary alm-summary-grid`, `prw-toolbar alm-toolbar`), route status via `AlmdinaUi.status()`, planning badge via `AlmdinaUi.badge()`, empty/error via `.alm-state`. The routing editor (stage rail, library, story rows) keeps its `prw-*` geometry and is not migrated yet.
8. Workbench — Shop Floor page chrome (migrated): intro via `almdina-sf-hero alm-page-intro`, board toolbar via `alm-toolbar`, `--sf-radius-*` / `--sf-shadow` alias `--alm-*`, hero stats / board metrics / error state read `--alm-status-*`. Kanban columns, production cards (status accents, completed styling), drag/drop and the shared loading markup stay frozen as domain visualization. Legacy `.almdina-sf-*` rules injected by `shared_shell.js` (operator profiles only) were removed in Phase 6, so operators and managers now share the same Shop Floor presentation owner.
9. Lists — Type A native Frappe lists (migrated chrome): static scales (typography, spacing, radius, shadow) are global on `:root` so native surfaces without `.almdina-ui` can read them; `almdina_list_table.css` owns row/table chrome via tokens; the list canvas belongs to `almdina_page_templates.css`. `door_cutting_order_list.css` (column geometry, pinned by `test_dco_compact_list_ux`) and `door_cutting_order_mobile_list.css` (allowlisted identity) are deferred to the DCO step.
10. DCO — JS style-injection debt (FE-ARCH-009) is frozen by a ratchet (`DCO_STYLE_INJECTION_DEBT` in `test_design_system_contract.py`): no new DCO module may inject `<style>`, and migrated modules must be removed from the list. Several injected rules are pinned in place by existing feature tests (e.g. `test_cut_dimensions_architecture` requires the cut-size hide rule inside its module, and `measurement_presentation_readiness.test.js` forbids `!important` in `door_cutting_order_measurement_structure.css`), so each migration is an explicit contract change, not a silent move.

## Enforcement

Gate: `almdina_erp.tests.test_design_system_contract`

Phase 0/1 checks include:

- foundational tokens exist (color, type, space, radius, shadow, status)
- shared CSS rejects new Feature-prefix selectors outside allowlist
- `frontend_assets.py` CSS/JS asset paths stay unique (query string ignored)
- ownership doc remains present
