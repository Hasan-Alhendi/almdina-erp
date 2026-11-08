# 19 — Backup ZIP Export Format

> **Status:** Canonical export contract (Phase 2)  
> **Audience:** Developers, QA, DevOps, Coding AI  
> **Scope:** Downloadable backup packages only. Upload/Import remain out of scope.

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

## Explicit non-goals (later phases)

Upload Backup, Import Backup, restoring imported ZIPs, replacing local retention with uploaded packages, and changing how originals are created.
