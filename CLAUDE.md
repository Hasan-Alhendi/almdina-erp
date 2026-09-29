# Almadina ERP — Claude Project Instructions

This file is a bootstrap for Claude. It does **not** replace the repository contract.

## Authority and precedence

1. `AGENTS.md` is the authoritative coding contract.
2. Canonical documents referenced by `AGENTS.md` define the architecture, product scope, security, lifecycle, frontend, testing, and release contracts.
3. If this file conflicts with `AGENTS.md` or a canonical document, stop and report the discrepancy. Do not silently reconcile it.
4. Do not rely on prior chat context as a substitute for reading the current repository state.

## Required session start

Before proposing or making a code change:

1. Read `AGENTS.md` completely.
2. Read the mandatory documents it references, including:
   - `docs/reference/README.md`
   - `docs/PRODUCT_SCOPE_v1.1.md`
   - `docs/reference/02_ARCHITECTURE.md`
   - `docs/reference/07_CHANGE_RULES.md`
3. Read the canonical specialist document for the area being changed.
   - For UI/UX, JavaScript, CSS, Page/Form/List/Report work, also read `docs/reference/13_FRONTEND_ARCHITECTURE.md` and the lifecycle standard it references.
   - For security, cutting/DXF, workflows, data/UI, testing, or operations, read the corresponding canonical reference before editing.
4. Inspect the current implementation and nearby tests before suggesting a fix.
5. Check `git status`, the current branch, and the relevant diff.

## Git safety

- Never make implementation changes directly on `Develop` or `main`.
- Start targeted work from the latest `Develop` on a dedicated feature/fix branch.
- Do not mix unrelated features in one branch or PR.
- Do not merge, force-push, delete branches, or rewrite shared history unless the user explicitly requests it.
- Target normal development PRs to `Develop`; `main` is release-only unless explicitly stated otherwise.

## Change Contract before code

Before editing, define:

```text
Goal:
User-visible behavior:
In scope:
Out of scope:
Invariants that must stay unchanged:
Expected layers/files:
Permission/security impact:
Financial data impact:
Schema/migration impact:
Tests required:
Rollback risk:
Docs affected:
```

If the required diff expands beyond the expected layers/files or changes an invariant, stop and re-evaluate the scope instead of broadening it automatically.

## Architecture guardrails

- `domain/` remains framework-free and may not import Frappe or outer layers.
- `application/` remains framework-free and may not depend on services, infrastructure, DocTypes, pages, reports, or presentation.
- Frappe/persistence/files/external integrations belong in `infrastructure/`.
- RPC endpoints in `services/` stay thin: explicit authorization, input translation, use-case wiring; no duplicated business formulas.
- UI/print/report layers consume server/domain decisions and calculated values; they do not become a second business authority.
- Do not solve dependency cycles by moving business logic into services.
- Do not expand legacy compatibility facades or tombstones for new features.

## Product-scope guardrails

Active Product Scope v1.1 excludes new Stock/Warehouse/Reservation/Consumption/Stock Entry/Board Remnant behavior and excluded query-report features. Historical code may remain for migration compatibility but is not a foundation for new product behavior.

## Security and financial guardrails

- Business authority is Capability-based, narrowed by document scope, lifecycle, production-stage operational role, and assignment as applicable.
- Do not introduce fixed Role-name authorization.
- `System Manager` is not an automatic factory superuser; `Administrator` is the explicit exception.
- Identifier knowledge never grants access. Validate parent/document/file scope and fail closed on missing or invalid identifiers.
- Keep internal cost/financial visibility separate from operational/order visibility.
- Never send sensitive financial fields to unauthorized clients and hide them only with CSS/JS.

## Lifecycle and frontend guardrails

- Server/Application/Domain remain authoritative for lifecycle and permission decisions.
- Preserve one clear owner for mutable frontend state and async lifecycle.
- Stale async responses must not overwrite newer document/page state.
- Do not use random permanent `refresh()` calls, duplicate observers, or duplicate event handlers to mask ownership bugs.
- Preserve Arabic-first/RTL behavior, desktop/mobile contracts, keyboard-heavy workflows, focus, accessibility, loading/error/empty/dirty states.
- Do not introduce React/Vue or another frontend architecture without an explicit architectural decision.

## Data, migrations, and tests

- Schema/data migrations must be idempotent and safe when `migrate` runs twice.
- Preserve approved plans, snapshots, and historical semantics unless the requested contract explicitly changes them.
- Prefer a regression test that reproduces a bug before or with the fix.
- Never weaken an existing test merely to make a change pass.
- Run targeted tests first, then the relevant broader quality gates/CI.
- Do not use `continue-on-error`, `|| true`, or equivalent mechanisms to hide required quality failures.

## Completion report

For implementation tasks, finish with:

- Done
- Files changed
- Tests run and results
- Security/permission impact
- Data/migration impact
- What explicitly did not change
- Remaining risks or unverified items
- Next step

Keep changes targeted. After the Stage 15 architecture freeze, broad refactors require an explicit architectural decision and approval.
