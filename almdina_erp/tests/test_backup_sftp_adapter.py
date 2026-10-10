from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
)
from almdina_erp.almdina_erp.infrastructure.backups.sftp import (
    SFTPBackupGateway,
    SSHAuthenticationError,
    SSHConfig,
    SSHConnectionError,
    SSHRemotePathError,
    SSHUploadError,
)


class AuthenticationException(Exception):
    pass


class SSHException(Exception):
    pass


class FakeRemoteFile:
    def __init__(self, sftp: "FakeSFTP", name: str) -> None:
        self.sftp = sftp
        self.name = name
        self.data = b""

    def __enter__(self) -> "FakeRemoteFile":
        return self

    def write(self, value: bytes) -> None:
        self.data += value

    def __exit__(self, *_args: object) -> None:
        self.sftp.files[self.name] = len(self.data)


class FakeSFTP:
    def __init__(self, *, fail_chdir: bool = False, fail_put: bool = False) -> None:
        self.fail_chdir = fail_chdir
        self.fail_put = fail_put
        self.files: dict[str, int] = {}
        self.removed: list[str] = []

    def chdir(self, _path: str) -> None:
        if self.fail_chdir:
            raise OSError("path denied")

    def open(self, name: str, _mode: str) -> FakeRemoteFile:
        return FakeRemoteFile(self, name)

    def remove(self, name: str) -> None:
        self.removed.append(name)
        self.files.pop(name, None)

    def put(self, local: str, remote: str, confirm: bool = True) -> None:
        assert confirm is True
        if self.fail_put:
            raise OSError("disk full")
        self.files[remote] = Path(local).stat().st_size

    def stat(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(st_size=self.files[name])

    def rename(self, old: str, new: str) -> None:
        self.files[new] = self.files.pop(old)

    def listdir(self) -> list[str]:
        return list(self.files)

    def close(self) -> None:
        return None


class FakeClient:
    def __init__(self, sftp: FakeSFTP, *, connect_error: Exception | None = None) -> None:
        self.sftp = sftp
        self.connect_error = connect_error
        self.connect_kwargs: dict[str, object] = {}

    def load_system_host_keys(self) -> None:
        return None

    def set_missing_host_key_policy(self, policy: object) -> None:
        assert policy is not None

    def connect(self, **kwargs: object) -> None:
        self.connect_kwargs = kwargs
        if self.connect_error:
            raise self.connect_error

    def open_sftp(self) -> FakeSFTP:
        return self.sftp

    def close(self) -> None:
        return None


PARAMIKO = SimpleNamespace(
    AuthenticationException=AuthenticationException,
    SSHException=SSHException,
    RejectPolicy=lambda: object(),
)


def config(**overrides: object) -> SSHConfig:
    values = {
        "host": "backup.internal",
        "port": 22,
        "username": "backup",
        "auth_method": "Password",
        "password": "not-a-real-secret",
        "remote_path": "/srv/almadina",
        "site_slug": "site_local",
    }
    values.update(overrides)
    return SSHConfig(**values)


def gateway(client: FakeClient, **overrides: object) -> SFTPBackupGateway:
    return SFTPBackupGateway(
        config(**overrides),
        client_factory=lambda: client,
        paramiko_module=PARAMIKO,
    )


def test_connection_checks_remote_write_access_without_creating_backup() -> None:
    sftp = FakeSFTP()
    client = FakeClient(sftp)
    gateway(client).test_connection()
    assert not sftp.files
    assert client.connect_kwargs["look_for_keys"] is False
    assert "password" in client.connect_kwargs


def test_authentication_connection_and_remote_path_failures_are_classified() -> None:
    with pytest.raises(SSHAuthenticationError):
        gateway(FakeClient(FakeSFTP(), connect_error=AuthenticationException())).test_connection()
    with pytest.raises(SSHConnectionError):
        gateway(FakeClient(FakeSFTP(), connect_error=SSHException())).test_connection()
    with pytest.raises(SSHRemotePathError):
        gateway(FakeClient(FakeSFTP(fail_chdir=True))).test_connection()


def test_upload_verifies_size_and_returns_scoped_reference(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle(
        "20261008_020000-site_local",
        (BackupArtifact("database", str(local), local.name, local.stat().st_size, "checksum"),),
    )
    sftp = FakeSFTP()
    reference = gateway(FakeClient(sftp)).upload(bundle)
    assert reference == "/srv/almadina/20261008_020000-site_local"
    assert sftp.files[local.name] == local.stat().st_size


def test_upload_failure_cleans_partial_files(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle(
        "20261008_020000-site_local",
        (BackupArtifact("database", str(local), local.name, local.stat().st_size, "checksum"),),
    )
    sftp = FakeSFTP(fail_put=True)
    with pytest.raises(SSHUploadError):
        gateway(FakeClient(sftp)).upload(bundle)
    assert sftp.removed


def test_external_retention_deletes_only_old_valid_frappe_groups() -> None:
    sftp = FakeSFTP()
    for stamp in ("20261001_020000", "20261002_020000", "20261003_020000"):
        for suffix in ("database.sql.gz", "files.tgz", "private-files.tgz", "site_config_backup.json"):
            sftp.files[f"{stamp}-site_local-{suffix}"] = 10
    sftp.files["unrelated.txt"] = 10
    gateway(FakeClient(sftp)).apply_retention(2)
    assert "unrelated.txt" in sftp.files
    assert not any(name.startswith("20261001_020000-site_local-") for name in sftp.files)
    assert any(name.startswith("20261003_020000-site_local-") for name in sftp.files)


def test_invalid_remote_path_is_rejected_before_connection() -> None:
    with pytest.raises(ValueError):
        gateway(FakeClient(FakeSFTP()), remote_path="../../etc")
