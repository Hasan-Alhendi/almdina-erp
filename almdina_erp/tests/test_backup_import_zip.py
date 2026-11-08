from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.backups.export_format import EXPORT_FORMAT, EXPORT_FORMAT_VERSION
from almdina_erp.almdina_erp.infrastructure.backups import import_zip as import_mod
from almdina_erp.almdina_erp.infrastructure.backups.import_zip import (
    BackupImportError,
    LocalBackupZipImporter,
)


SITE = "site.local"
SLUG = "site_local"
IDENTIFIER = "20261108_120000-site_local"
KINDS = (
    ("database", f"{IDENTIFIER}-database.sql.gz", b"db-bytes-01"),
    ("public_files", f"{IDENTIFIER}-files.tgz", b"public-bytes"),
    ("private_files", f"{IDENTIFIER}-private-files.tgz", b"private-byte"),
    ("site_config", f"{IDENTIFIER}-site_config_backup.json", b'{"ok":true}'),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_payload(components: list[dict] | None = None, **overrides) -> dict:
    items = components or [
        {
            "name": kind,
            "path": filename,
            "size": len(payload),
            "sha256": _sha(payload),
            "required": True,
        }
        for kind, filename, payload in KINDS
    ]
    payload = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "backup_id": IDENTIFIER,
        "operation_id": "source-op",
        "site": SITE,
        "created_at": "2026-11-08 12:00:00",
        "database_type": "mariadb",
        "target": "Local",
        "operation_type": "Manual",
        "components": items,
    }
    payload.update(overrides)
    return payload


def _build_zip(path: Path, *, payload: dict | None = None, members: dict[str, bytes] | None = None) -> Path:
    body = payload if payload is not None else _manifest_payload()
    files = members if members is not None else {filename: content for _kind, filename, content in KINDS}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr("manifest.json", json.dumps(body).encode("utf-8"))
        for name, content in files.items():
            archive.writestr(name, content)
    return path


class FakeHistory:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.fail = False

    def create_imported_completed(self, *, bundle, requested_by: str) -> str:
        if self.fail:
            raise RuntimeError("history boom")
        self.calls.append((bundle.identifier, requested_by, len(bundle.artifacts)))
        return "imported-op-1"

    def imported_backup_identifiers(self) -> set[str]:
        return set()


@pytest.fixture
def import_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backups = tmp_path / "private" / "backups"
    backups.mkdir(parents=True)
    private = tmp_path / "private"
    history = FakeHistory()

    monkeypatch.setattr(import_mod, "get_backup_path", lambda: str(backups))
    monkeypatch.setattr(
        import_mod.frappe,
        "get_site_path",
        lambda *parts: str(tmp_path.joinpath(*parts)) if parts else str(tmp_path),
        raising=False,
    )
    monkeypatch.setattr(import_mod.frappe, "local", SimpleNamespace(site=SITE), raising=False)
    return SimpleNamespace(backups=backups, private=private, history=history, root=tmp_path)


def test_import_valid_zip_writes_four_artifacts_and_registers_history(import_env) -> None:
    zip_path = _build_zip(import_env.root / "ok.zip")
    originals = {path.name: path.read_bytes() for path in import_env.backups.glob("*")}
    assert originals == {}

    result = LocalBackupZipImporter(history=import_env.history).import_zip(
        str(zip_path),
        site=SITE,
        site_slug=SLUG,
        database_type="mariadb",
        requested_by="Administrator",
    )
    assert result.operation_id == "imported-op-1"
    assert result.backup_identifier == IDENTIFIER
    written = sorted(path.name for path in import_env.backups.iterdir())
    assert written == sorted(filename for _k, filename, _p in KINDS)
    assert import_env.history.calls
    assert list(import_env.private.glob("almdina-backup-import-*")) == []


def test_import_rejects_duplicate_existing_files(import_env) -> None:
    zip_path = _build_zip(import_env.root / "dup.zip")
    (import_env.backups / f"{IDENTIFIER}-database.sql.gz").write_bytes(b"existing")
    with pytest.raises(BackupImportError, match="backup_import_duplicate"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert (import_env.backups / f"{IDENTIFIER}-files.tgz").exists() is False


def test_import_rejects_bad_checksum_and_leaves_backups_clean(import_env) -> None:
    payload = _manifest_payload()
    payload["components"][0]["sha256"] = "e" * 64
    zip_path = _build_zip(import_env.root / "bad-hash.zip", payload=payload)
    with pytest.raises(BackupImportError, match="backup_import_integrity_failed"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert list(import_env.backups.iterdir()) == []


def test_import_rejects_path_traversal_member(import_env) -> None:
    zip_path = import_env.root / "trav.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../evil.txt", b"nope")
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(BackupImportError):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert list(import_env.backups.iterdir()) == []


def test_import_rejects_missing_manifest(import_env) -> None:
    zip_path = import_env.root / "no-manifest.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for _kind, filename, payload in KINDS:
            archive.writestr(filename, payload)
    with pytest.raises(BackupImportError, match="backup_import_missing_manifest"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )


def test_import_rejects_site_and_db_mismatch(import_env) -> None:
    zip_path = _build_zip(import_env.root / "site.zip", payload=_manifest_payload(site="other.local"))
    with pytest.raises(BackupImportError, match="backup_import_site_mismatch"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    zip_path = _build_zip(
        import_env.root / "db.zip",
        payload=_manifest_payload(database_type="postgres"),
    )
    with pytest.raises(BackupImportError, match="backup_import_database_type_mismatch"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )


def test_import_history_failure_rolls_back_written_files(import_env) -> None:
    zip_path = _build_zip(import_env.root / "hist.zip")
    import_env.history.fail = True
    with pytest.raises(BackupImportError, match="backup_import_history_failed"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert list(import_env.backups.iterdir()) == []


def test_import_rejects_size_mismatch_as_zip_bomb_guard(import_env) -> None:
    payload = _manifest_payload()
    payload["components"][0]["size"] = 2  # smaller than actual member bytes
    zip_path = _build_zip(import_env.root / "bomb.zip", payload=payload)
    with pytest.raises(BackupImportError):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert list(import_env.backups.iterdir()) == []


def test_import_rejects_encrypted_member(import_env, monkeypatch: pytest.MonkeyPatch) -> None:
    zip_path = _build_zip(import_env.root / "enc.zip")
    real_zipfile = zipfile.ZipFile

    class EncryptedZip(real_zipfile):
        def infolist(self):  # noqa: ANN001
            infos = list(super().infolist())
            for info in infos:
                info.flag_bits |= 0x1
            return infos

    monkeypatch.setattr(import_mod.zipfile, "ZipFile", EncryptedZip)
    with pytest.raises(BackupImportError, match="backup_import_encrypted"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert list(import_env.backups.iterdir()) == []


def test_import_rejects_absolute_member_paths(import_env) -> None:
    zip_path = import_env.root / "abs.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("/tmp/evil.txt", b"nope")
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(BackupImportError, match="backup_import_unsafe_path"):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )


def test_import_rejects_corrupt_crc(import_env) -> None:
    zip_path = _build_zip(import_env.root / "crc.zip")
    data = bytearray(zip_path.read_bytes())
    # Flip a payload byte while leaving the central directory CRC untouched.
    flipped = False
    for index in range(len(data) - 30, 40, -1):
        if data[index] not in (0, 0x50, 0x4B):
            data[index] ^= 0xFF
            flipped = True
            break
    assert flipped
    zip_path.write_bytes(data)
    with pytest.raises(BackupImportError):
        LocalBackupZipImporter(history=import_env.history).import_zip(
            str(zip_path),
            site=SITE,
            site_slug=SLUG,
            database_type="mariadb",
            requested_by="Administrator",
        )
    assert list(import_env.backups.iterdir()) == []


def test_imported_is_downloadable_and_restorable() -> None:
    from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory

    assert "Imported" in FrappeBackupHistory.RESTORABLE_OPERATION_TYPES
    assert "Imported" in FrappeBackupHistory.DOWNLOADABLE_LOCAL_OPERATION_TYPES
    assert set(FrappeBackupHistory.RESTORABLE_OPERATION_TYPES) <= set(
        FrappeBackupHistory.DOWNLOADABLE_LOCAL_OPERATION_TYPES
    )


def test_retention_skips_imported_identifiers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import frappe_backup as fb

    root = tmp_path / "backups"
    root.mkdir()
    for stamp in ("20261101_010000-site_local", "20261102_010000-site_local"):
        for suffix in ("database.sql.gz", "files.tgz", "private-files.tgz", "site_config_backup.json"):
            (root / f"{stamp}-{suffix}").write_bytes(b"x")

    captured: dict[str, object] = {}

    def fake_cleanup(complete, limit):
        captured["ids"] = sorted(complete)
        captured["limit"] = limit

    monkeypatch.setattr(fb, "frappe", SimpleNamespace(local=SimpleNamespace(site=SITE)), raising=False)
    monkeypatch.setattr(
        "frappe.desk.page.backups.backups.cleanup_old_backups",
        fake_cleanup,
    )
    monkeypatch.setattr("frappe.utils.backups.get_backup_path", lambda: str(root))
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.infrastructure.backups.history.FrappeBackupHistory.imported_backup_identifiers",
        lambda self: {"20261102_010000-site_local"},
    )

    fb.FrappeLocalRetention().apply(1)
    assert captured["ids"] == ["20261101_010000-site_local"]
    assert (root / "20261102_010000-site_local-database.sql.gz").exists()
