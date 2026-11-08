# 19 — Backup ZIP Export Format

> **Status:** Canonical export contract (Phase 2)  
> **Audience:** Developers, QA, DevOps, Coding AI  
> **Scope:** Downloadable backup packages and Local ZIP Import (`operation_type=Imported`). Restore of imported packages remains out of scope.

## Purpose

Almadina keeps site backups as the four Frappe v16 artifacts produced by `BackupGenerator`. Download packages those artifacts into one portable ZIP with a machine-readable `manifest.json` so later Upload/Import/Restore phases can verify integrity without trusting client paths.

## Source artifacts (actual runtime names)

A complete site backup group shares one identifier:

`YYYYMMDD_HHMMSS-<site_slug>`

and consists of:

| Component name | Typical filename suffix |
|---|---|
| `database` | `-database.sql.gz` (optional `-enc`) |
| `public_files` | `-files.tar` / `-files.tgz` (optional `-enc`) |
| `private_files` | `-private-files.tar` / `-private-files.tgz` (optional `-enc`) |
| `site_config` | `-site_config_backup.json` (optional `-enc`) |

Operation metadata stores a JSON `artifact_manifest` of `{kind, filename, size, checksum}` plus a SHA-256 of the canonical manifest. Export builds the ZIP from that metadata and the on-disk (or SFTP-fetched) files. Original files are never modified or deleted by Download.

## ZIP layout

```text
<backup_id>.zip
├── manifest.json
├── <backup_id>-database.sql.gz
├── <backup_id>-files.tgz
├── <backup_id>-private-files.tgz
└── <backup_id>-site_config_backup.json
```

Member names are basenames only. Absolute server paths are forbidden in the archive and in the manifest.

## Manifest schema (`format_version`: 1)

```json
{
  "format": "almdina.backup.zip",
  "format_version": 1,
  "backup_id": "20261108_120000-site_local",
  "operation_id": "<Almdina Backup Operation id>",
  "site": "site.local",
  "created_at": "<operation completed_on>",
  "database_type": "mariadb",
  "target": "Local",
  "operation_type": "Manual",
  "components": [
    {
      "name": "database",
      "path": "20261108_120000-site_local-database.sql.gz",
      "size": 12345,
      "sha256": "<hex>",
      "required": true
    }
  ]
}
```

Rules:

- JSON must be valid UTF-8.
- `format` is stable; bump `format_version` for incompatible changes.
- Every required component must be listed with byte size and SHA-256.
- No passwords, SSH credentials, DB root settings, or absolute paths.
- Old backups without a pre-existing ZIP still export: the manifest is generated at download time from stored operation metadata and verified files.

## Eligibility and authorization

Download requires `manage_backups` on the server. Eligible operations:

- `status = Completed`
- `operation_type ∈ {Manual, Scheduled, Safety}`
- `target ∈ {Local, External}`
- non-empty `backup_identifier`

Queued / Running / Failed / Restore operations are rejected. The UI button is gated by `can_download`: Local rows also require a cheap on-disk database-artifact probe (one directory scan, no checksums); External rows stay metadata-only so the history panel never opens SFTP per row. The download endpoint re-validates fully and remains the authority.

## Local vs External

- **Local:** files are read from Frappe’s backup directory after path confinement and checksum verification.
- **External:** artifacts are fetched over the existing Paramiko SFTP gateway into a private temp directory, verified, packed, then cleaned up. Remote originals are not deleted. SSH credentials never enter the ZIP.

## Security invariants

- Client may send only `operation_id`.
- Path traversal and out-of-scope symlinks are rejected.
- Temporary staging lives under the site `private` directory and is removed after success or failure.
- User-facing errors use safe codes/messages without internal paths.

## Local ZIP Import

`manage_backups` may upload an `almdina.backup.zip` v1 package. The server validates the root `manifest.json`, component sizes/SHA-256, current-site slug, and current `database_type`, then materializes the four artifacts into `private/backups` and inserts an `Imported` / `Local` / `Completed` history row. Imported identifiers are excluded from automatic local retention in this phase. They are downloadable but not listed by `restorable()`.

Operational note: Frappe/`nginx` upload size limits remain infrastructure settings. Import code does not impose an application-level fixed ZIP size cap and streams members to disk.

## External age encryption

External backups are encrypted with **age X25519** (`pyrage`) before SFTP upload:

- Server stores only the **public** recipient (`external_backup_age_public_key`, `age1…`).
- Operator keeps the **private** identity (`AGE-SECRET-KEY-…`) offline. It is never stored in the site DB, settings Password fields, SFTP, logs, or retry metadata.
- Remote filenames use a `.age` suffix. Artifact manifests store ciphertext `size`/`checksum` plus `plaintext_*` fields and `encryption=age-x25519-v1`.
- Upload still uses `.part` → remote SHA-256 of **ciphertext** → rename.
- Legacy External rows without `encryption` remain Import-compatible ZIP downloadable.
- Encrypted External rows intentionally **do not** offer server-side plaintext ZIP Export (that would require the private key on the server). Offline flow: fetch `.age` files from SFTP → `age`/`pyrage` decrypt with the private key → verify plaintext SHA-256 → build `almdina.backup.zip` v1 for Import.

Generate keys offline, for example:

```bash
# with the age CLI, or via pyrage Identity.generate() in a trusted offline environment
age-keygen -o backup-external.key
# public age1… line → Almdina ERP Settings
# AGE-SECRET-KEY-… → operator vault only
```

### Offline rebuild of Import ZIP

Encrypted External packages are rebuilt on the operator machine with:

`scripts/offline_external_backup_to_zip.py`

Inputs: directory of `.age` files, operation `artifact_manifest` (or a descriptor object), and the local `AGE-SECRET-KEY` file. The tool decrypts, verifies each `plaintext_checksum`, then writes `almdina.backup.zip` v1 for ZIP Import. The private key never contacts the ERP server. Requires `pyrage`.

## Explicit non-goals (later phases)

Restoring imported ZIPs, External SFTP import destinations, cross-site imports, overwrite of existing artifact groups, changing how originals are created, and server-side decrypt of encrypted External packages into Import-compatible ZIP.
