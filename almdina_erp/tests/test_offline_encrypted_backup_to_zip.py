from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pyrage import x25519

from almdina_erp.almdina_erp.domain.backups.encryption import AGE_ENCRYPTION_SCHEME
from almdina_erp.almdina_erp.domain.backups.export_format import EXPORT_FORMAT, EXPORT_FORMAT_VERSION
from almdina_erp.almdina_erp.infrastructure.backups import import_zip as import_mod
from almdina_erp.almdina_erp.infrastructure.backups.age_crypto import (
    chunked_sha256,
    encrypt_file_with_age_public_key,
)
from almdina_erp.almdina_erp.infrastructure.backups.import_zip import LocalBackupZipImporter
from almdina_erp.almdina_erp.offline.encrypted_backup_to_import_zip import (
    OfflineBackupZipError,
    build_import_zip_from_age_artifacts,
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


def _prepare_encrypted_package(root: Path) -> tuple[Path, Path, Path, str]:
    identity = x25519.Identity.generate()
    public_key = str(identity.to_public())
    private_key = str(identity)
    cipher_dir = root / "cipher"
    cipher_dir.mkdir()
    artifacts = []
    for kind, filename, payload in KINDS:
        plain = root / "plain-src" / filename
        plain.parent.mkdir(parents=True, exist_ok=True)
        plain.write_bytes(payload)
        cipher_name = f"{filename}.age"
        encrypt_file_with_age_public_key(
            source=plain,
            destination=cipher_dir / cipher_name,
            public_key=public_key,
        )
        artifacts.append(
            {
                "kind": kind,
                "filename": cipher_name,
                "size": (cipher_dir / cipher_name).stat().st_size,
                "checksum": chunked_sha256(cipher_dir / cipher_name),
                "encryption": AGE_ENCRYPTION_SCHEME,
                "plaintext_filename": filename,
                "plaintext_size": len(payload),
                "plaintext_checksum": _sha(payload),
            }
        )
    key_path = root / "backup-external.key"
    key_path.write_text(f"# created offline\n{private_key}\n", encoding="utf-8")
    manifest_path = root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "backup_id": IDENTIFIER,
                "operation_id": "op-external-1",
                "site": SITE,
                "created_at": "2026-11-08 12:00:00",
                "database_type": "mariadb",
                "target": "External",
                "operation_type": "Scheduled",
                "artifacts": artifacts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return cipher_dir, manifest_path, key_path, private_key


class FakeHistory:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def create_imported_completed(self, *, bundle, requested_by: str) -> str:
        self.calls.append((bundle.identifier, requested_by, len(bundle.artifacts)))
        return "imported-from-offline"

    def imported_backup_identifiers(self) -> set[str]:
        return set()


def test_offline_tool_builds_zip_accepted_by_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cipher_dir, manifest_path, key_path, _private = _prepare_encrypted_package(tmp_path)
    output = tmp_path / f"{IDENTIFIER}.zip"
    result = build_import_zip_from_age_artifacts(
        cipher_dir=cipher_dir,
        manifest_path=manifest_path,
        private_key_path=key_path,
        output_zip=output,
    )
    assert result == output.resolve()
    assert output.is_file()

    with zipfile.ZipFile(output, "r") as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        payload = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert payload["format"] == EXPORT_FORMAT
    assert payload["format_version"] == EXPORT_FORMAT_VERSION
    assert payload["backup_id"] == IDENTIFIER
    assert {item["name"] for item in payload["components"]} == {
        "database",
        "public_files",
        "private_files",
        "site_config",
    }
    assert not any(str(name).endswith(".age") for name in names)

    backups = tmp_path / "private" / "backups"
    backups.mkdir(parents=True)
    history = FakeHistory()
    monkeypatch.setattr(import_mod, "get_backup_path", lambda: str(backups))
    monkeypatch.setattr(
        import_mod.frappe,
        "get_site_path",
        lambda *parts: str(tmp_path.joinpath(*parts)) if parts else str(tmp_path),
        raising=False,
    )
    monkeypatch.setattr(import_mod.frappe, "local", SimpleNamespace(site=SITE), raising=False)

    imported = LocalBackupZipImporter(history=history).import_zip(
        str(output),
        site=SITE,
        site_slug=SLUG,
        database_type="mariadb",
        requested_by="Administrator",
    )
    assert imported.backup_identifier == IDENTIFIER
    assert history.calls
    assert sorted(path.name for path in backups.iterdir()) == sorted(name for _k, name, _p in KINDS)


def test_offline_tool_rejects_wrong_private_key(tmp_path: Path) -> None:
    cipher_dir, manifest_path, _key_path, _private = _prepare_encrypted_package(tmp_path)
    wrong = tmp_path / "wrong.key"
    wrong.write_text(str(x25519.Identity.generate()), encoding="utf-8")
    output = tmp_path / "out.zip"
    with pytest.raises(OfflineBackupZipError, match="Could not decrypt"):
        build_import_zip_from_age_artifacts(
            cipher_dir=cipher_dir,
            manifest_path=manifest_path,
            private_key_path=wrong,
            output_zip=output,
        )
    assert output.exists() is False


def test_offline_tool_rejects_tampered_ciphertext(tmp_path: Path) -> None:
    cipher_dir, manifest_path, key_path, _private = _prepare_encrypted_package(tmp_path)
    target = next(cipher_dir.glob("*-database.sql.gz.age"))
    data = bytearray(target.read_bytes())
    data[-9] ^= 0xFF
    target.write_bytes(data)
    output = tmp_path / "out.zip"
    with pytest.raises(OfflineBackupZipError, match="Could not decrypt"):
        build_import_zip_from_age_artifacts(
            cipher_dir=cipher_dir,
            manifest_path=manifest_path,
            private_key_path=key_path,
            output_zip=output,
        )
    assert output.exists() is False


def test_offline_tool_rejects_plaintext_checksum_mismatch(tmp_path: Path) -> None:
    cipher_dir, manifest_path, key_path, _private = _prepare_encrypted_package(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifacts"][0]["plaintext_checksum"] = "e" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "out.zip"
    with pytest.raises(OfflineBackupZipError, match="SHA-256 mismatch"):
        build_import_zip_from_age_artifacts(
            cipher_dir=cipher_dir,
            manifest_path=manifest_path,
            private_key_path=key_path,
            output_zip=output,
        )
    assert output.exists() is False


def test_offline_tool_rejects_missing_cipher_file(tmp_path: Path) -> None:
    cipher_dir, manifest_path, key_path, _private = _prepare_encrypted_package(tmp_path)
    next(cipher_dir.glob("*-files.tgz.age")).unlink()
    output = tmp_path / "out.zip"
    with pytest.raises(OfflineBackupZipError, match="Missing encrypted artifact"):
        build_import_zip_from_age_artifacts(
            cipher_dir=cipher_dir,
            manifest_path=manifest_path,
            private_key_path=key_path,
            output_zip=output,
        )
    assert output.exists() is False
