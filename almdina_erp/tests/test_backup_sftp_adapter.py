from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
)
from almdina_erp.almdina_erp.infrastructure.backups import sftp as sftp_mod
from almdina_erp.almdina_erp.infrastructure.backups.sftp import (
    SFTPBackupGateway,
    SSHAuthenticationError,
    SSHConfig,
    SSHConnectionError,
    SSHDownloadError,
    SSHRemotePathError,
    SSHUploadError,
)


class AuthenticationException(Exception):
    pass


class SSHException(Exception):
    pass


class FakeRemoteFile:
    def __init__(self, sftp: "FakeSFTP", name: str, mode: str) -> None:
        self.sftp = sftp
        self.name = name
        self.mode = mode
        self._pos = 0
        self.data = b""
        if "r" in mode:
            if name not in sftp.contents:
                raise OSError("missing remote file")
            self.data = sftp.contents[name]

    def __enter__(self) -> "FakeRemoteFile":
        return self

    def read(self, size: int = -1) -> bytes:
        if self.sftp.fail_read:
            raise OSError("remote read failed")
        self.sftp.read_calls.append(size)
        if size is None or size < 0:
            chunk = self.data[self._pos :]
            self._pos = len(self.data)
            return chunk
        chunk = self.data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def write(self, value: bytes) -> None:
        self.data += value

    def __exit__(self, *_args: object) -> None:
        if "w" in self.mode:
            self.sftp.contents[self.name] = self.data


class FakeSFTP:
    def __init__(
        self,
        *,
        fail_chdir: bool = False,
        fail_put: bool = False,
        corrupt_put: bool = False,
        fail_read: bool = False,
        size_override: int | None = None,
    ) -> None:
        self.fail_chdir = fail_chdir
        self.fail_put = fail_put
        self.corrupt_put = corrupt_put
        self.fail_read = fail_read
        self.size_override = size_override
        self.contents: dict[str, bytes] = {}
        self.removed: list[str] = []
        self.renames: list[tuple[str, str]] = []
        self.read_calls: list[int] = []

    @property
    def files(self) -> dict[str, int]:
        return {name: len(payload) for name, payload in self.contents.items()}

    def chdir(self, _path: str) -> None:
        if self.fail_chdir:
            raise OSError("path denied")

    def open(self, name: str, mode: str = "r") -> FakeRemoteFile:
        return FakeRemoteFile(self, name, mode)

    def remove(self, name: str) -> None:
        self.removed.append(name)
        self.contents.pop(name, None)

    def put(self, local: str, remote: str, confirm: bool = True) -> None:
        assert confirm is True
        if self.fail_put:
            raise OSError("disk full")
        data = bytearray(Path(local).read_bytes())
        if self.corrupt_put and data:
            data[0] ^= 0xFF
        self.contents[remote] = bytes(data)

    def get(self, remote: str, local: str) -> None:
        if remote not in self.contents:
            raise OSError("missing remote file")
        if getattr(self, "fail_get_name", None) == remote:
            raise OSError("transfer interrupted")
        Path(local).write_bytes(self.contents[remote])

    def stat(self, name: str) -> SimpleNamespace:
        if self.size_override is not None and name in self.contents:
            return SimpleNamespace(st_size=self.size_override)
        return SimpleNamespace(st_size=len(self.contents[name]))

    def rename(self, old: str, new: str) -> None:
        self.renames.append((old, new))
        self.contents[new] = self.contents.pop(old)

    def listdir(self) -> list[str]:
        return list(self.contents)

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


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(path: Path, *, kind: str = "database", checksum: str | None = None) -> BackupArtifact:
    payload = path.read_bytes()
    return BackupArtifact(
        kind=kind,
        path=str(path),
        filename=path.name,
        size=len(payload),
        checksum=checksum if checksum is not None else _sha(payload),
    )


def test_connection_checks_remote_write_access_without_creating_backup() -> None:
    sftp = FakeSFTP()
    client = FakeClient(sftp)
    gateway(client).test_connection()
    assert not sftp.contents
    assert client.connect_kwargs["look_for_keys"] is False
    assert "password" in client.connect_kwargs


def test_authentication_connection_and_remote_path_failures_are_classified() -> None:
    with pytest.raises(SSHAuthenticationError):
        gateway(FakeClient(FakeSFTP(), connect_error=AuthenticationException())).test_connection()
    with pytest.raises(SSHConnectionError):
        gateway(FakeClient(FakeSFTP(), connect_error=SSHException())).test_connection()
    with pytest.raises(SSHRemotePathError):
        gateway(FakeClient(FakeSFTP(fail_chdir=True))).test_connection()


def test_upload_verifies_size_and_sha256_before_rename(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle("20261008_020000-site_local", (_artifact(local),))
    sftp = FakeSFTP()
    reference = gateway(FakeClient(sftp)).upload(bundle)
    assert reference == "/srv/almadina/20261008_020000-site_local"
    assert sftp.contents[local.name] == b"database"
    assert len(sftp.renames) == 1
    assert sftp.renames[0][1] == local.name
    assert not any(name.endswith(".part") for name in sftp.contents)


def test_upload_failure_cleans_partial_files(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle("20261008_020000-site_local", (_artifact(local),))
    sftp = FakeSFTP(fail_put=True)
    with pytest.raises(SSHUploadError):
        gateway(FakeClient(sftp)).upload(bundle)
    assert sftp.removed
    assert sftp.renames == []
    assert sftp.contents == {}


def test_upload_rejects_checksum_mismatch_without_rename(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle("20261008_020000-site_local", (_artifact(local),))
    sftp = FakeSFTP(corrupt_put=True)
    unrelated = "20260901_010000-site_local-database.sql.gz"
    sftp.contents[unrelated] = b"keep-me"
    with pytest.raises(SSHUploadError) as raised:
        gateway(FakeClient(sftp)).upload(bundle)
    assert raised.value.safe_code == "ssh_upload_integrity_failed"
    assert sftp.renames == []
    assert unrelated in sftp.contents
    assert sftp.contents[unrelated] == b"keep-me"
    assert not any(name.endswith(".part") for name in sftp.contents)
    assert any(name.endswith(".part") for name in sftp.removed)


def test_upload_rejects_size_mismatch_without_rename(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle("20261008_020000-site_local", (_artifact(local),))
    sftp = FakeSFTP(size_override=1)
    with pytest.raises(SSHUploadError, match="size does not match"):
        gateway(FakeClient(sftp)).upload(bundle)
    assert sftp.renames == []
    assert not any(name.endswith(".part") for name in sftp.contents)
    assert any(name.endswith(".part") for name in sftp.removed)


def test_upload_rejects_remote_read_failure_without_rename(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    local.write_bytes(b"database")
    bundle = BackupBundle("20261008_020000-site_local", (_artifact(local),))
    sftp = FakeSFTP(fail_read=True)
    with pytest.raises(SSHUploadError, match="checksum could not be verified"):
        gateway(FakeClient(sftp)).upload(bundle)
    assert sftp.renames == []
    assert not any(name.endswith(".part") for name in sftp.contents)
    assert any(name.endswith(".part") for name in sftp.removed)


def test_upload_multiple_artifacts_all_verified(tmp_path: Path) -> None:
    files = [
        (tmp_path / "20261008_020000-site_local-database.sql.gz", "database", b"db-bytes"),
        (tmp_path / "20261008_020000-site_local-files.tgz", "public_files", b"public"),
        (tmp_path / "20261008_020000-site_local-private-files.tgz", "private_files", b"private"),
        (tmp_path / "20261008_020000-site_local-site_config_backup.json", "site_config", b'{"ok":1}'),
    ]
    artifacts = []
    for path, kind, payload in files:
        path.write_bytes(payload)
        artifacts.append(_artifact(path, kind=kind))
    bundle = BackupBundle("20261008_020000-site_local", tuple(artifacts))
    sftp = FakeSFTP()
    gateway(FakeClient(sftp)).upload(bundle)
    assert len(sftp.renames) == 4
    for path, _kind, payload in files:
        assert sftp.contents[path.name] == payload


def test_upload_reads_remote_file_in_chunks_for_large_payload(tmp_path: Path) -> None:
    local = tmp_path / "20261008_020000-site_local-database.sql.gz"
    payload = b"A" * (sftp_mod._REMOTE_READ_CHUNK + 128)
    local.write_bytes(payload)
    bundle = BackupBundle("20261008_020000-site_local", (_artifact(local),))
    sftp = FakeSFTP()
    gateway(FakeClient(sftp)).upload(bundle)
    assert sftp.contents[local.name] == payload
    assert sftp.read_calls
    assert all(size == sftp_mod._REMOTE_READ_CHUNK for size in sftp.read_calls)
    assert len(sftp.read_calls) >= 2
    assert max(sftp.read_calls) < len(payload)


def test_external_retention_deletes_only_old_valid_frappe_groups() -> None:
    sftp = FakeSFTP()
    for stamp in ("20261001_020000", "20261002_020000", "20261003_020000"):
        for suffix in ("database.sql.gz", "files.tgz", "private-files.tgz", "site_config_backup.json"):
            sftp.contents[f"{stamp}-site_local-{suffix}"] = b"x" * 10
    sftp.contents["unrelated.txt"] = b"x" * 10
    gateway(FakeClient(sftp)).apply_retention(2)
    assert "unrelated.txt" in sftp.contents
    assert not any(name.startswith("20261001_020000-site_local-") for name in sftp.contents)
    assert any(name.startswith("20261003_020000-site_local-") for name in sftp.contents)


def test_invalid_remote_path_is_rejected_before_connection() -> None:
    with pytest.raises(ValueError):
        gateway(FakeClient(FakeSFTP()), remote_path="../../etc")


def test_download_artifacts_writes_basenames_only(tmp_path: Path) -> None:
    sftp = FakeSFTP()
    name = "20261008_020000-site_local-database.sql.gz"
    sftp.contents[name] = b"x" * 8
    gateway(FakeClient(sftp)).download_artifacts([name], str(tmp_path))
    assert (tmp_path / name).is_file()
    assert (tmp_path / name).stat().st_size == 8


def test_download_artifacts_rejects_traversal_and_cleans_partial(tmp_path: Path) -> None:
    sftp = FakeSFTP()
    first = "20261008_020000-site_local-database.sql.gz"
    second = "20261008_020000-site_local-files.tgz"
    sftp.contents[first] = b"x" * 8
    sftp.contents[second] = b"x" * 8
    sftp.fail_get_name = second
    with pytest.raises(SSHDownloadError):
        gateway(FakeClient(sftp)).download_artifacts([first, second], str(tmp_path))
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(SSHDownloadError):
        gateway(FakeClient(sftp)).download_artifacts(["../etc/passwd"], str(tmp_path))
