# Cutting Plan release safety — operational acceptance

> **Owner:** release/DevOps + factory operations  
> **Scope:** every site/tenant that stores System or Uploaded DXF cutting plans.  
> **Policy:** preserve original DXF, immutable snapshots, revisions and approval history; no bulk repair or auto-approval.

This is a release *procedure*, not a migration, backup job, deployment command or authorization bypass. Follow [Upgrade Preflight](CUTTING_PLAN_UPGRADE_PREFLIGHT.md) and [Operations & Release](09_OPERATIONS_RELEASE.md).

## 1. Reference implementation vs. deployed version

- PR [#554](https://github.com/Hasan-Alhendi/almdina-erp/pull/554) was merged into `Develop` at Git commit `c9081524f6d8bc5cf88cb57f0d1df60d08373524` on **2026-10-26**.
- The final PR code HEAD was `c84e882428575540742136f363f06d72a129ec51`. These are **source-control references**, not verified server runtime IDs.
- Factory operational feedback after its update: **previously uploaded DXF files did not need to be uploaded again**. This is a useful UAT observation, **not proof that all historical plans were verified**.
- **Deployed app Git SHA/image digest: not yet independently captured.** The release owner must read it from the actual running container/image, compare with the intended artifact, and store the evidence in a *private* release record. Do not infer the deployed commit from the tip of `Develop` or `main`.

For every site, maintain a private, append-only record containing: deployment UTC timestamp; site identifier; previous and new **running** image digest / exact app SHA; Frappe/ERPNext versions; CI run SHA/status; backup bundle identifier and checksums; isolated-restore test; before/after audit classification counts; representative System/Uploaded/Approved/historical read-only UAT results; decision/approver; rollback compatibility assessment. Do not commit customer order IDs, files, site secrets or raw audit manifests to Git.

## 2. Before every deployment — verified recovery point

Almadina already supplies **Backup & Restore** through Factory Production Settings, using Frappe v16 `BackupGenerator`. Do not add a second ad hoc backup engine.

1. Confirm the correct site and operator backup capability, free disk space, running scheduler and `long` queue worker. Request a site backup and confirm the operation finished **successfully**, not merely `Queued`.
2. Verify the **same backup bundle** contains all four artifacts: **database**, **public files**, **private files**, and **site configuration**. Uploaded private DXF files are part of the private-files backup; confirm the required attachments are actually present after restoring. A database-only dump is *not* a complete cutting-plan backup.
3. Record the bundle ID, sizes and SHA-256 checksums. Keep a protected copy **off the application host**, with restricted access and the site's applicable encryption/retention policy. A backup only on the VPS is insufficient for loss of that VPS.
4. **Restore the bundle to an isolated site** using the project's tested restore workflow, not the production site. Verify order/plan counts, Approved links, access to representative System snapshots and original Uploaded DXF attachments, and the ability to read those DXFs. Confirm the isolate cannot send WhatsApp messages, production commands or other live integrations.
5. Record the restoration evidence. No successful restore test = **NO-GO** for risky migrations/deployments.

Never perform a restore, bulk update, fingerprint rewrite, stale-flag reset, plan regeneration or DXF replacement merely to validate a backup.

## 3. Immutable compatibility CI gate

The existing `.github/workflows/static-checks.yml` already has **Validate versioned cutting-plan fingerprint compatibility**, executing:

- `almdina_erp.tests.test_plan_fingerprint_compatibility`
- `almdina_erp.tests.test_fingerprint_final_hardening`
- `almdina_erp.tests.test_plan_upgrade_contract`
- `almdina_erp.tests.test_plan_upgrade_audit`

The same workflow also has **Validate cutting-plan lifecycle safety**. The Frappe v16 integration workflow supplies additional DB/integration evidence.

**Release rule:** do not remove, skip, weaken, or replace those gates with refreshed expected hashes. V1, known V2 variants, V3 and V4 must continue to be read according to their **original versioned meaning**. If manufacturing semantics must change, introduce a **new contract version with independent fixtures**, preserve old readers, and prove that an unchanged old plan remains compatible. Tests must still reject real manufacturing-input changes and damaged snapshots.

The release owner must also configure and verify GitHub **branch rules / required status checks** for `Develop` and `main`. The presence of a workflow alone does not prove that a red workflow blocks merge. Rules are controlled in GitHub settings and must be checked by a repo administrator.

## 4. Preflight of *real* historical plans

CI fixtures are necessary, not sufficient. On the **same isolated restored DB and file set**, generate authorized read-only inventory manifests before and after the proposed app update using `scripts/plan_upgrade_preflight.py`:

```bash
# Run with the isolated bench's Python environment; never on live production.
python scripts/plan_upgrade_preflight.py manifest --site ISOLATED_SITE --output /SECURE_PATH/before.json
# Change only the isolated app version; perform required isolated migrations.
python scripts/plan_upgrade_preflight.py manifest --site ISOLATED_SITE --output /SECURE_PATH/after.json
python scripts/plan_upgrade_preflight.py compare --before /SECURE_PATH/before.json --after /SECURE_PATH/after.json
```

These placeholders are not literal paths. Protect both manifests as operational records: they contain order/plan identifiers, though not customer names. **Earlier releases that do not emit the current manifest schema cannot produce a valid automatic before/after PASS**. Classify that first transition manually on the isolated copy and explicitly document the incomplete baseline.

- **PASS**: no unexpected loss/changes under complete evidence; proceed only after the remaining functional checks.
- **REVIEW_REQUIRED**: incomplete evidence, new/removed rows or unexplained classification/lifecycle difference; inspect and approve explicitly before deciding.
- **BLOCKED_BY_REGRESSION**: a formerly authorized plan loses eligibility or a required DXF disappears; **do not deploy** until root cause is fixed.

Include at least an unchanged known-legacy Uploaded DXF, a valid System plan, linked Approved, historical Cancelled/Superseded, a persisted stale plan and a true machining-input mismatch. Do not infer that Cancelled or PERSISTED_STALE can be revived automatically. No customer DXF or live manifest belongs in the repository.

## 5. Decision, rollback and follow-up

**GO** requires: correct running artifact identity, verified complete backup and isolated restore, green CI on that exact SHA, preflight reviewed and accepted, stage/approval safety checks, and signed release evidence. An unexplained new manufacturing block is **NO-GO**, not a prompt to re-upload hundreds of DXFs.

**Rollback is not automatically safe:** a version lacking a V4 reader may not understand plans created since the upgrade. Decide on a compatible reader/restore point and check any intervening writes first. Never roll back only the code while assuming newer plan contracts remain valid.

After deployment, compare the **actual running** artifact with the recorded SHA/digest; audit representative old plans **read-only**, verify new manufacturing cannot start with REVIEW_REQUIRED/PERSISTED_STALE, and confirm original DXF download still works with permissions. Recheck operations for unexpected stale/cancelled transitions. Retain the prior release record and the backup off-site.

## 6. Release acceptance record (copy outside Git)

```text
Site/tenant:
Release date (UTC):
Previous running SHA / image digest:
New running SHA / image digest:
Frappe / ERPNext versions:
GitHub CI run / exact SHA:
Complete DB + public + private + site-config backup ID / SHA-256:
Off-host copy confirmed:
Isolated restore verified (by / when):
Before/after manifest locations (restricted):
Before/after eligible / compatible / review-required / stale counts:
Unexplained classification changes / DXF losses:
System / Uploaded / linked Approved / historical / OFFCUT test evidence:
V4 rollback compatibility decision:
Decision: GO / REVIEW_REQUIRED / NO-GO
Approver:
Post-deployment checks and time:
```

**Acceptance criterion:** releasing the app never requires routine re-upload of unchanged cutting plans. This is demonstrated through fixed old-contract CI **and** site-specific upgrade preflight, not through a green workflow or an anecdotal single order alone.
