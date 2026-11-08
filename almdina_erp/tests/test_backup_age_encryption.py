from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pyrage import x25519

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
)
from almdina_erp.almdina_erp.domain.backups.encryption import (
    AGE_ENCRYPTION_SCHEME,
    validate_age_public_key,
)
from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier
from almdina_erp.almdina_erp.infrastructure.backups import encrypted_external as enc_mod
from almdina_erp.almdina_erp.infrastructure.backups.age_crypto import (
    BackupEncryptionError,
    chunked_sha256,
    decrypt_file_with_age_private_key,
    encrypt_file_with_age_public_key,
)
from almdina_erp.almdina_erp.infrastructure.backups.encrypted_external import AgeEncryptedExternalGateway
from almdina_erp.almdina_erp.infrastructure.backups.export_zip import annotate_downloadable
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import bundle_manifest


def _keypair() -> tuple[str, str]:
    identity = x25519.Identity.generate()
    return str(identity.to_public()), str(identity)


def test_validate_age_public_key_accepts_recipient_and_rejects_secret() -> None:
    public_key, private_key = _keypair()
    assert validate_age_public_key(public_key) == public_key
    with pytest.raises(ValueError, match="backup_encryption_private_key_rejected"):
        validate_age_public_key(private_key)
    with pytest.raises(ValueError, match="backup_encryption_public_key_invalid"):
        validate_age_public_key("not-a-key")


def test_encrypt_decrypt_roundtrip_and_integrity(tmp_path: Path) -> None:
    public_key, private_key = _keypair()
    source = tmp_path / "20261108_120000-site_local-database.sql.gz"
    payload = b"PLAINTEXT-BACKUP-" + (b"x" * (1024 * 1024 + 64))
    source.write_bytes(payload)
    plaintext_sha = chunked_sha256(source)
    cipher = tmp_path / f"{source.name}.age"
    encrypt_file_with_age_public_key(source=source, destination=cipher, public_key=public_key)
    assert cipher.is_file()
    assert cipher.read_bytes()[:4] != b"PLAI"
    cipher_sha = chunked_sha256(cipher)

    restored = tmp_path / "restored.sql.gz"
    decrypt_file_with_age_private_key(source=cipher, destination=restored, private_key=private_key)
    assert restored.read_bytes() == payload
    assert chunked_sha256(restored) == plaintext_sha

    wrong_private = str(x25519.Identity.generate())
    with pytest.raises(BackupEncryptionError, match="backup_encryption_decrypt_failed"):
        decrypt_file_with_age_private_key(
            source=cipher,
            destination=tmp_path / "bad.out",
            private_key=wrong_private,
        )

    tampered = tmp_path / "tampered.age"
    data = bytearray(cipher.read_bytes())
    data[-12] ^= 0xFF
    tampered.write_bytes(data)
    with pytest.raises(BackupEncryptionError, match="backup_encryption_decrypt_failed"):
        decrypt_file_with_age_private_key(
            source=tampered,
            destination=tmp_path / "tampered.out",
            private_key=private_key,
        )
    assert cipher_sha != chunked_sha256(tampered)


def test_encrypted_external_gateway_uploads_ciphertext_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    public_key, private_key = _keypair()
    plain = tmp_path / "20261108_120000-site_local-database.sql.gz"
    plain.write_bytes(b"db-bytes-01")
    plaintext_sha = chunked_sha256(plain)
    bundle = BackupBundle(
        "20261108_120000-site_local",
        (
            BackupArtifact(
                "database",
                str(plain),
                plain.name,
                plain.stat().st_size,
                plaintext_sha,
            ),
        ),
    )

    uploaded: list[BackupBundle] = []

    class FakeInner:
        def test_connection(self) -> None:
            return None

        def apply_retention(self, keep_last: int) -> None:
            return None

        def upload(self, encrypted_bundle: BackupBundle):
            uploaded.append(encrypted_bundle)
            for artifact in encrypted_bundle.artifacts:
                assert artifact.filename.endswith(".age")
                assert Path(artifact.path).is_file()
                assert artifact.checksum == chunked_sha256(artifact.path)
                assert artifact.plaintext_checksum == plaintext_sha
                assert artifact.encryption == AGE_ENCRYPTION_SCHEME
            from almdina_erp.almdina_erp.application.backups.management import ExternalUploadResult

            return ExternalUploadResult(reference="/srv/x", stored_bundle=encrypted_bundle)

    monkeypatch.setattr(enc_mod.frappe, "get_site_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    result = AgeEncryptedExternalGateway(FakeInner(), public_key=public_key).upload(bundle)
    assert result.reference == "/srv/x"
    assert uploaded and uploaded[0].artifacts[0].filename.endswith(".age")
    # Staging ciphertext must be cleaned after upload returns.
    assert list(tmp_path.joinpath("private").glob("almdina-backup-age-*")) == []

    # Offline decrypt path using operator private key.
    cipher_path = tmp_path / "remote.age"
    # Re-encrypt once more for offline verification of the stored metadata contract.
    encrypt_file_with_age_public_key(source=plain, destination=cipher_path, public_key=public_key)
    out = tmp_path / "offline.sql.gz"
    decrypt_file_with_age_private_key(source=cipher_path, destination=out, private_key=private_key)
    assert out.read_bytes() == b"db-bytes-01"

    manifest = bundle_manifest(result.stored_bundle)
    assert manifest[0]["encryption"] == AGE_ENCRYPTION_SCHEME
    assert manifest[0]["plaintext_checksum"] == plaintext_sha
    assert "AGE-SECRET-KEY" not in json.dumps(manifest)


def test_backup_group_identifier_accepts_age_suffix() -> None:
    assert (
        backup_group_identifier("20261108_120000-site_local-database.sql.gz.age", "site_local")
        == "20261108_120000-site_local"
    )


def test_annotate_downloadable_hides_encrypted_external(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.infrastructure.backups.export_zip.frappe",
        SimpleNamespace(local=SimpleNamespace(site="site.local")),
        raising=False,
    )
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.infrastructure.backups.export_zip._local_backup_identifiers_present",
        lambda _slug: set(),
    )
    encrypted_manifest = json.dumps(
        [
            {
                "kind": "database",
                "filename": "20261108_120000-site_local-database.sql.gz.age",
                "size": 10,
                "checksum": "a" * 64,
                "encryption": AGE_ENCRYPTION_SCHEME,
                "plaintext_filename": "20261108_120000-site_local-database.sql.gz",
                "plaintext_size": 8,
                "plaintext_checksum": "b" * 64,
            }
        ]
    )
    legacy_manifest = json.dumps(
        [
            {
                "kind": "database",
                "filename": "20261108_120000-site_local-database.sql.gz",
                "size": 8,
                "checksum": "b" * 64,
            }
        ]
    )
    rows = annotate_downloadable(
        [
            {
                "operation_id": "enc-1",
                "status": "Completed",
                "target": "External",
                "operation_type": "Scheduled",
                "backup_identifier": "20261108_120000-site_local",
                "artifact_manifest": encrypted_manifest,
            },
            {
                "operation_id": "plain-1",
                "status": "Completed",
                "target": "External",
                "operation_type": "Scheduled",
                "backup_identifier": "20261108_120000-site_local",
                "artifact_manifest": legacy_manifest,
            },
        ]
    )
    assert rows[0]["can_download"] is False
    assert rows[1]["can_download"] is True
