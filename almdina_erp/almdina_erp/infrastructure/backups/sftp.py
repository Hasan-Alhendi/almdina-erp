from __future__ import annotations

import io
import os
import posixpath
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from almdina_erp.almdina_erp.application.backups.management import BackupBundle
from almdina_erp.almdina_erp.domain.backups.policy import (
    backup_group_identifier,
    normalize_remote_path,
    retention_candidates,
)


class SFTPGatewayError(RuntimeError):
    safe_code = "ssh_operation_failed"


class SSHAuthenticationError(SFTPGatewayError):
    safe_code = "ssh_authentication_failed"


class SSHConnectionError(SFTPGatewayError):
    safe_code = "ssh_connection_failed"


class SSHRemotePathError(SFTPGatewayError):
    safe_code = "ssh_remote_path_invalid"


class SSHUploadError(SFTPGatewayError):
    safe_code = "ssh_upload_failed"


@dataclass(frozen=True, slots=True)
class SSHConfig:
    host: str
    port: int
    username: str
    auth_method: str
    remote_path: str
    site_slug: str
    password: str = ""
    private_key: str = ""
    private_key_passphrase: str = ""

    def validated(self) -> "SSHConfig":
        host = str(self.host or "").strip()
        username = str(self.username or "").strip()
        auth_method = str(self.auth_method or "").strip().lower().replace("_", " ")
        if not host or not username:
            raise ValueError("SSH host and username are required.")
        try:
            port = int(self.port)
        except (TypeError, ValueError) as exc:
            raise ValueError("SSH port is invalid.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("SSH port is invalid.")
        if auth_method not in {"password", "private key"}:
            raise ValueError("SSH authentication method is invalid.")
        if auth_method == "password" and not self.password:
            raise ValueError("SSH password is required.")
        if auth_method == "private key" and not self.private_key:
            raise ValueError("SSH private key is required.")
        return SSHConfig(
            host=host,
            port=port,
            username=username,
            auth_method=auth_method,
            remote_path=normalize_remote_path(self.remote_path),
            site_slug=str(self.site_slug or "").strip(),
            password=self.password,
            private_key=self.private_key,
            private_key_passphrase=self.private_key_passphrase,
        )


class SFTPBackupGateway:
    """Paramiko SFTP adapter with strict host-key verification."""

    def __init__(
        self,
        config: SSHConfig,
        *,
        client_factory: Callable[[], Any] | None = None,
        paramiko_module: Any | None = None,
    ) -> None:
        self.config = config.validated()
        self._paramiko = paramiko_module
        self._client_factory = client_factory

    def _module(self) -> Any:
        if self._paramiko is None:
            try:
                import paramiko
            except ImportError as exc:
                raise SSHConnectionError("Paramiko is not installed.") from exc
            self._paramiko = paramiko
        return self._paramiko

    def _private_key(self) -> Any:
        module = self._module()
        last_error: Exception | None = None
        for name in ("Ed25519Key", "ECDSAKey", "RSAKey", "DSSKey"):
            key_type = getattr(module, name, None)
            if key_type is None:
                continue
            try:
                return key_type.from_private_key(
                    io.StringIO(self.config.private_key),
                    password=self.config.private_key_passphrase or None,
                )
            except Exception as exc:  # key parsers expose multiple error types
                last_error = exc
        raise SSHAuthenticationError("SSH private key is invalid.") from last_error

    def _connect(self) -> tuple[Any, Any]:
        module = self._module()
        client = self._client_factory() if self._client_factory else module.SSHClient()
        try:
            if hasattr(client, "load_system_host_keys"):
                client.load_system_host_keys()
            if hasattr(client, "set_missing_host_key_policy"):
                client.set_missing_host_key_policy(module.RejectPolicy())
            kwargs: dict[str, Any] = {
                "hostname": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "timeout": 15,
                "banner_timeout": 15,
                "auth_timeout": 15,
                "allow_agent": False,
                "look_for_keys": False,
            }
            if self.config.auth_method == "password":
                kwargs["password"] = self.config.password
            else:
                kwargs["pkey"] = self._private_key()
            client.connect(**kwargs)
        except getattr(module, "AuthenticationException", ()):  # pragma: no branch
            client.close()
            raise SSHAuthenticationError("SSH authentication failed.") from None
        except SSHAuthenticationError:
            client.close()
            raise
        except (OSError, getattr(module, "SSHException", OSError)) as exc:
            client.close()
            raise SSHConnectionError("SSH connection failed.") from exc
        try:
            sftp = client.open_sftp()
            sftp.chdir(self.config.remote_path)
            return client, sftp
        except Exception as exc:
            client.close()
            raise SSHRemotePathError("SSH remote path is inaccessible.") from exc

    @staticmethod
    def _close(client: Any, sftp: Any) -> None:
        try:
            sftp.close()
        finally:
            client.close()

    def test_connection(self) -> None:
        client, sftp = self._connect()
        probe = f".almdina-connection-test-{uuid.uuid4().hex}"
        try:
            with sftp.open(probe, "wb") as stream:
                stream.write(b"")
            sftp.remove(probe)
        except Exception as exc:
            try:
                sftp.remove(probe)
            except Exception:
                pass
            raise SSHRemotePathError("SSH remote path is not writable.") from exc
        finally:
            self._close(client, sftp)

    def upload(self, bundle: BackupBundle) -> str:
        client, sftp = self._connect()
        uploaded: list[str] = []
        temporary: list[str] = []
        try:
            for artifact in bundle.artifacts:
                if artifact.filename != os.path.basename(artifact.filename):
                    raise SSHUploadError("Backup artifact name is invalid.")
                if not os.path.isfile(artifact.path):
                    raise SSHUploadError("Backup artifact is missing.")
                final_name = artifact.filename
                temp_name = f".{final_name}.{uuid.uuid4().hex}.part"
                temporary.append(temp_name)
                sftp.put(artifact.path, temp_name, confirm=True)
                if int(sftp.stat(temp_name).st_size) != int(artifact.size):
                    raise SSHUploadError("Uploaded backup size does not match.")
                sftp.rename(temp_name, final_name)
                temporary.remove(temp_name)
                uploaded.append(final_name)
            return posixpath.join(self.config.remote_path, bundle.identifier)
        except Exception as exc:
            for name in (*temporary, *uploaded):
                try:
                    sftp.remove(name)
                except Exception:
                    pass
            if isinstance(exc, SFTPGatewayError):
                raise
            raise SSHUploadError("SFTP upload failed.") from exc
        finally:
            self._close(client, sftp)

    def apply_retention(self, keep_last: int) -> None:
        client, sftp = self._connect()
        try:
            grouped: dict[str, list[str]] = {}
            database_groups: set[str] = set()
            for name in sftp.listdir():
                identifier = backup_group_identifier(name, self.config.site_slug)
                if not identifier:
                    continue
                grouped.setdefault(identifier, []).append(name)
                if "-database" in name:
                    database_groups.add(identifier)
            eligible = [identifier for identifier in grouped if identifier in database_groups]
            for identifier in retention_candidates(eligible, keep_last):
                for name in grouped[identifier]:
                    sftp.remove(name)
        except Exception as exc:
            if isinstance(exc, SFTPGatewayError):
                raise
            raise SSHUploadError("External backup retention failed.") from exc
        finally:
            self._close(client, sftp)


__all__ = [
    "SFTPBackupGateway",
    "SFTPGatewayError",
    "SSHAuthenticationError",
    "SSHConfig",
    "SSHConnectionError",
    "SSHRemotePathError",
    "SSHUploadError",
]
