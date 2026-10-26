from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import frappe
import frappe.utils.backups

from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import FrappeBackupEngine


def test_adapter_calls_frappe_backup_generator_with_files_and_full_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeGenerator:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            captured["init"] = kwargs
            stamp = "20261008_020000-site_local"
            self.backup_path_db = str(tmp_path / f"{stamp}-database.sql.gz")
            self.backup_path_files = str(tmp_path / f"{stamp}-files.tgz")
            self.backup_path_private_files = str(tmp_path / f"{stamp}-private-files.tgz")
            self.backup_path_conf = str(tmp_path / f"{stamp}-site_config_backup.json")

        def get_backup(self, **kwargs: object) -> None:
            captured["get_backup"] = kwargs
            for path in (
                self.backup_path_db,
                self.backup_path_files,
                self.backup_path_private_files,
                self.backup_path_conf,
            ):
                Path(path).write_bytes(b"valid-frappe-artifact")

    monkeypatch.setattr(frappe.utils.backups, "BackupGenerator", FakeGenerator)
    monkeypatch.setattr(
        frappe,
        "conf",
        SimpleNamespace(
            db_name="db",
            db_user="user",
            db_password="secret",
            db_socket=None,
            db_host="localhost",
            db_port=3306,
            db_type="mariadb",
        ),
    )
    monkeypatch.setattr(frappe.local, "site", "site.local", raising=False)

    bundle = FrappeBackupEngine().create()

    assert bundle.identifier == "20261008_020000-site_local"
    assert {artifact.kind for artifact in bundle.artifacts} == {
        "database",
        "public_files",
        "private_files",
        "site_config",
    }
    assert captured["get_backup"] == {"ignore_files": False, "force": True}
    assert captured["init"]["ignore_conf"] is True
    assert captured["init"]["compress_files"] is True
