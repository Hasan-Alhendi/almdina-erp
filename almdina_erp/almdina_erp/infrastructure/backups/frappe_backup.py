from __future__ import annotations

import hashlib
import fcntl
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
)
from almdina_erp.almdina_erp.domain.backups.policy import backup_artifact_kind, backup_group_identifier
from almdina_erp.almdina_erp.infrastructure.backups import restore_state


_ARTIFACTS = (
    ("database", "backup_path_db"),
    ("public_files", "backup_path_files"),
    ("private_files", "backup_path_private_files"),
    ("site_config", "backup_path_conf"),
)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


class FrappeBackupEngine:
    """Thin adapter over Frappe v16 ``BackupGenerator``.

    ``BackupGenerator`` is used directly so Almdina retention runs only after
    the new backup succeeds; ``scheduled_backup`` deletes aged files before it
    starts and therefore cannot satisfy that safety invariant.
    """

    def __init__(self, *, ephemeral: bool = False) -> None:
        self.ephemeral = bool(ephemeral)
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def _destination(self) -> str | None:
        if not self.ephemeral:
            return None
        if self._temporary is None:
            private_root = frappe.get_site_path("private")
            os.makedirs(private_root, exist_ok=True)
            self._temporary = tempfile.TemporaryDirectory(
                prefix="almdina-external-backup-",
                dir=private_root,
            )
        return self._temporary.name

    def create(self) -> BackupBundle:
        from frappe.utils.backups import BackupGenerator

        generator = BackupGenerator(
            frappe.conf.db_name,
            frappe.conf.db_user,
            frappe.conf.db_password,
            db_socket=frappe.conf.db_socket,
            db_host=frappe.conf.db_host,
            db_port=frappe.conf.db_port,
            db_type=frappe.conf.db_type,
            backup_path=self._destination(),
            ignore_conf=True,
            compress_files=True,
        )
        if self.ephemeral:
            generator.get_backup(ignore_files=False, force=True)
        else:
            from frappe.utils.backups import get_backup_path

            root = Path(get_backup_path())
            root.mkdir(parents=True, exist_ok=True)
            with (root / ".almdina-backup.lock").open("a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                generator.set_backup_file_name()
                if any(Path(str(getattr(generator, attr))).exists() for _, attr in _ARTIFACTS):
                    raise RuntimeError("Backup artifacts already exist.")
                generator.get_backup(ignore_files=False, force=True)

        site_slug = str(frappe.local.site).replace(".", "_")
        artifacts: list[BackupArtifact] = []
        identifier = ""
        for kind, attribute in _ARTIFACTS:
            path = Path(str(getattr(generator, attribute, "") or ""))
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"Frappe backup artifact is missing: {kind}")
            group = backup_group_identifier(path.name, site_slug)
            if not group:
                raise RuntimeError(f"Frappe backup artifact name is invalid: {kind}")
            if identifier and group != identifier:
                raise RuntimeError("Frappe backup artifacts do not share one identifier.")
            identifier = group
            artifacts.append(
                BackupArtifact(
                    kind=kind,
                    path=str(path.resolve()),
                    filename=path.name,
                    size=path.stat().st_size,
                    checksum=_checksum(path),
                )
            )
        return BackupBundle(identifier=identifier, artifacts=tuple(artifacts))

    def release(self, bundle: BackupBundle) -> None:
        del bundle
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


class FrappeLocalRetention:
    """Apply Frappe's grouped cleanup only to validated site backup files."""

    def apply(self, keep_last: int) -> None:
        from frappe.desk.page.backups.backups import cleanup_old_backups
        from frappe.utils.backups import get_backup_path

        limit = int(keep_last)
        if limit < 1:
            raise ValueError("Local backup retention must be positive.")
        root = Path(get_backup_path()).resolve()
        if restore_state.active(Path(frappe.get_site_path()).resolve()):
            return
        if not root.is_dir():
            return
        site_slug = str(frappe.local.site).replace(".", "_")
        with (root / ".almdina-backup.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # A failed history lookup must never turn imported files into candidates.
            protected = set(frappe.get_all(
                "Almdina Backup Operation",
                filters={"operation_type": "Imported", "target": "Local", "status": "Completed"},
                pluck="backup_identifier",
            ))
            protected.update(path.name.removeprefix(".almdina-imported-") for path in root.glob(".almdina-imported-*"))
            grouped: dict[str, list[Path]] = defaultdict(list)
            kinds: dict[str, set[str]] = defaultdict(set)
            for path in root.iterdir():
                if not path.is_file() or path.is_symlink() or not _inside(root, path):
                    continue
                identifier = backup_group_identifier(path.name, site_slug)
                if not identifier or identifier in protected:
                    continue
                grouped[identifier].append(path)
                kind = backup_artifact_kind(path.name)
                if kind:
                    kinds[identifier].add(kind)
            complete = {
                identifier: paths
                for identifier, paths in grouped.items()
                if kinds[identifier] == {"database", "public_files", "private_files", "site_config"}
            }
            cleanup_old_backups(complete, limit)


def bundle_manifest(bundle: BackupBundle) -> list[dict[str, Any]]:
    return [
        {
            "kind": artifact.kind,
            "filename": artifact.filename,
            "size": artifact.size,
            "checksum": artifact.checksum,
        }
        for artifact in bundle.artifacts
    ]


__all__ = [
    "FrappeBackupEngine",
    "FrappeLocalRetention",
    "bundle_manifest",
]
