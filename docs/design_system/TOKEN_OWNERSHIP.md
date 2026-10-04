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

Current temporary allowlist:

- `.dco-plan-tabs` active-tab underline in `almdina_components.css` (migrate to `.alm-tabs` later)
- `.dco-tab-edit-toolbar` compact button sizing in `almdina_components.css` (migrate with DCO toolbar pattern later)

## Migration policy (presentation only)

1. Prefer aliases first: `--apc-radius-md: var(--alm-radius-md)`.
2. Do not change Domain/Application/Services, capabilities, RPC payloads, or Frappe page-action ownership.
3. Do not replace measurement grids, cutting boards, permission matrices, or shop-floor drag logic with new widgets.
4. Migrate Admin Console pages before Workbench, Lists, then DCO.
5. One surface family per PR when class/markup swaps begin.
6. Admin status/risk badges use `AlmdinaUi.badge()` + `.alm-badge--*`; Feature CSS may keep layout sizing (`.aw-badge`, `.apc-badge`, `.aps-status-pill`) but must not own status palettes.

## Enforcement

Gate: `almdina_erp.tests.test_design_system_contract`

Phase 0/1 checks include:

- foundational tokens exist (color, type, space, radius, shadow, status)
- shared CSS rejects new Feature-prefix selectors outside allowlist
- `frontend_assets.py` CSS/JS asset paths stay unique (query string ignored)
- ownership doc remains present
