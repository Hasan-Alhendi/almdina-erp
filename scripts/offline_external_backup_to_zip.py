#!/usr/bin/env python3
"""Offline: convert age-encrypted External backup artifacts into Import ZIP.

Run on the operator workstation only. The private key never leaves this machine.

Example:

  python scripts/offline_external_backup_to_zip.py \\
    --cipher-dir ./downloaded-age-files \\
    --manifest ./artifact_manifest.json \\
    --private-key ./backup-external.key \\
    --output-zip ./20261108_120000-site_local.zip \\
    --site site.local \\
    --database-type mariadb

Manifest may be:
  1) the operation ``artifact_manifest`` JSON array saved from Almdina, plus
     ``--site`` / ``--backup-id`` / ``--database-type`` as needed; or
  2) a descriptor object::

       {
         "backup_id": "...",
         "operation_id": "...",
         "site": "site.local",
         "created_at": "2026-11-08 12:00:00",
         "database_type": "mariadb",
         "target": "External",
         "operation_type": "Scheduled",
         "artifacts": [ ... encrypted artifact_manifest entries ... ]
       }

Requirements: Python 3.10+, ``pyrage`` (same dependency as Almdina External encryption).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_import_path() -> None:
    """Allow running from a bench checkout without installing the app editable."""

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main(argv: list[str] | None = None) -> int:
    _bootstrap_import_path()
    from almdina_erp.almdina_erp.offline.encrypted_backup_to_import_zip import (
        OfflineBackupZipError,
        build_import_zip_from_age_artifacts,
    )

    parser = argparse.ArgumentParser(
        description="Decrypt External .age backup artifacts offline into an almdina.backup.zip package.",
    )
    parser.add_argument("--cipher-dir", required=True, help="Directory containing the .age artifact files")
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to artifact_manifest JSON (array) or offline descriptor object",
    )
    parser.add_argument(
        "--private-key",
        required=True,
        help="Path to AGE-SECRET-KEY file (age-keygen output). Never store this on the ERP server.",
    )
    parser.add_argument("--output-zip", required=True, help="Destination path for the Import-compatible ZIP")
    parser.add_argument("--site", default="", help="Site name when not present in the manifest object")
    parser.add_argument("--backup-id", default="", help="Backup identifier when not present in the manifest object")
    parser.add_argument("--database-type", default="", help="mariadb|postgres|sqlite (default mariadb)")
    parser.add_argument("--operation-id", default="", help="Optional operation id recorded in ZIP manifest.json")
    parser.add_argument("--created-at", default="", help="Optional created_at timestamp for ZIP manifest.json")
    parser.add_argument("--target", default="", help="Optional target label (default External)")
    parser.add_argument("--operation-type", default="", help="Optional operation_type (default Scheduled)")
    args = parser.parse_args(argv)

    try:
        output = build_import_zip_from_age_artifacts(
            cipher_dir=args.cipher_dir,
            manifest_path=args.manifest,
            private_key_path=args.private_key,
            output_zip=args.output_zip,
            site=args.site,
            backup_id=args.backup_id,
            database_type=args.database_type,
            operation_id=args.operation_id,
            created_at=args.created_at,
            target=args.target,
            operation_type=args.operation_type,
        )
    except OfflineBackupZipError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - unexpected
        print(f"ERROR: unexpected failure: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote Import-compatible ZIP: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
