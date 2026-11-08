from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from almdina_erp.almdina_erp.domain.backups.db_root import (
    DbRootDefaults,
    DbRootOverrides,
    connection_is_ready,
    resolve_db_root_connection,
)
from almdina_erp.almdina_erp.infrastructure.backups import db_root as adapter
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services import backup_restore_service as service


class FakeSettings:
    def __init__(self, values: dict[str, Any] | None = None, passwords: dict[str, str] | None = None) -> None:
        self.values = values or {}
        self.passwords = passwords or {}

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.values.get(fieldname, default)

    def get_password(self, fieldname: str, raise_exception: bool = False) -> str:
        assert raise_exception is False
        return self.passwords.get(fieldname, "")


def test_resolve_falls_back_to_frappe_defaults_when_custom_empty() -> None:
    connection = resolve_db_root_connection(
        defaults=DbRootDefaults(
            db_type="mariadb",
            host="127.0.0.1",
            port=3307,
            username="root",
            password="frappe-secret",
        ),
        overrides=DbRootOverrides(),
    )
    assert connection.source == "frappe"
    assert connection.password == "frappe-secret"
    assert connection_is_ready(connection)


def test_resolve_prefers_custom_password_and_host() -> None:
    connection = resolve_db_root_connection(
        defaults=DbRootDefaults(password="frappe-secret", host="127.0.0.1", port=3306, username="root"),
        overrides=DbRootOverrides(host="db.internal", port=3307, username="restore", password="custom-secret"),
    )
    assert connection.source == "custom"
    assert connection.host == "db.internal"
    assert connection.port == 3307
    assert connection.username == "restore"
    assert connection.password == "custom-secret"


def test_incomplete_settings_are_not_ready() -> None:
    connection = resolve_db_root_connection(
        defaults=DbRootDefaults(password=""),
        overrides=DbRootOverrides(host="127.0.0.1"),
    )
    assert not connection_is_ready(connection)


def test_public_settings_never_expose_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "frappe_db_root_defaults",
        lambda: DbRootDefaults(password="frappe-secret", host="127.0.0.1", port=3306, username="root"),
    )
    settings = FakeSettings(
        {"db_restore_host": "db.internal", "db_restore_root_username": "restore"},
        {"db_restore_root_password": "custom-secret"},
    )
    public = adapter.public_db_root_settings(settings)
    dumped = json.dumps(public)
    assert "custom-secret" not in dumped
    assert "frappe-secret" not in dumped
    assert public["db_restore_custom_password_configured"] is True
    assert public["db_restore_root_password_configured"] is True


def test_connection_success_without_privileges(monkeypatch: pytest.MonkeyPatch) -> None:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql: str) -> None:
            self.sql = sql

        def fetchall(self):
            return [("GRANT SELECT ON *.* TO `restore`@`%`",)]

    class Handle:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    connection = resolve_db_root_connection(
        defaults=DbRootDefaults(password="x"),
        overrides=DbRootOverrides(password="x", host="127.0.0.1", username="restore"),
    )
    with pytest.raises(adapter.DbRootInsufficientPrivileges):
        adapter.test_db_root_connection(connection, mariadb_connect=lambda _c: Handle())


def test_authentication_failure_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    import pymysql

    def boom(_connection):
        raise pymysql.err.OperationalError(1045, "Access denied for user")

    connection = resolve_db_root_connection(
        defaults=DbRootDefaults(password="bad"),
        overrides=DbRootOverrides(password="bad", host="127.0.0.1", username="root"),
    )
    with pytest.raises(adapter.DbRootAuthenticationError) as exc:
        adapter.test_db_root_connection(connection, mariadb_connect=boom)
    assert "bad" not in str(exc.value)
    assert exc.value.safe_code == "db_root_authentication_failed"


def test_host_unreachable_is_classified() -> None:
    import pymysql

    def boom(_connection):
        raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")

    connection = resolve_db_root_connection(
        defaults=DbRootDefaults(password="x"),
        overrides=DbRootOverrides(password="x", host="missing.internal", username="root"),
    )
    with pytest.raises(adapter.DbRootHostUnreachable):
        adapter.test_db_root_connection(connection, mariadb_connect=boom)


def test_test_db_connection_endpoint_requires_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(capability: str, **_kwargs: Any) -> None:
        raise PermissionError(capability)

    monkeypatch.setattr(service, "require_doctype_capability", deny)
    monkeypatch.setattr(service, "_", lambda message: message)
    with pytest.raises(PermissionError) as exc:
        service.test_db_connection()
    assert Capability.MANAGE_DB_RESTORE_SETTINGS in str(exc.value)


def test_restore_runtime_ready_uses_custom_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "frappe_db_root_defaults",
        lambda: DbRootDefaults(password=""),
    )
    monkeypatch.setattr(
        adapter,
        "settings_db_root_overrides",
        lambda _settings=None: DbRootOverrides(
            host="127.0.0.1",
            port=3306,
            username="root",
            password="custom-secret",
        ),
    )
    assert adapter.restore_runtime_ready() is True


def test_write_restore_request_embeds_credentials_without_logging_them(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
    from almdina_erp.almdina_erp.infrastructure.backups import restore as restore_mod

    site_private = tmp_path / "private"
    site_private.mkdir()
    monkeypatch.setattr(
        restore_mod.frappe,
        "get_site_path",
        lambda *parts: str(site_private.joinpath(*parts)),
    )
    monkeypatch.setattr(restore_mod.frappe, "local", SimpleNamespace(site="site.local"))
    monkeypatch.setattr(restore_mod.frappe.utils, "get_bench_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        restore_mod,
        "resolve_effective_db_root",
        lambda: resolve_db_root_connection(
            defaults=DbRootDefaults(password=""),
            overrides=DbRootOverrides(
                host="127.0.0.1",
                port=3306,
                username="root",
                password="restore-secret",
            ),
        ),
    )
    monkeypatch.setattr(restore_mod, "restore_runtime_ready", lambda: True)
    monkeypatch.setattr(
        restore_mod,
        "bundle_manifest",
        lambda bundle: [
            {
                "kind": artifact.kind,
                "filename": artifact.filename,
                "size": artifact.size,
                "checksum": artifact.checksum,
            }
            for artifact in bundle.artifacts
        ],
    )

    def fake_bundle(name: str) -> BackupBundle:
        artifacts = tuple(
            BackupArtifact(kind=kind, path=f"/tmp/{name}-{kind}", filename=f"{name}-{kind}", size=1, checksum="a" * 64)
            for kind in ("database", "public_files", "private_files", "site_config")
        )
        return BackupBundle(identifier=name, artifacts=artifacts)

    path = restore_mod.write_restore_request(
        operation_id="op1",
        source_operation_id="source",
        source_operation_type="Manual",
        source_requested_by="Administrator",
        source_requested_on="2026-11-07",
        source_completed_on="2026-11-07",
        requested_by="Administrator",
        requested_on="2026-11-07",
        target=fake_bundle("target"),
        safety_operation_id="safety",
        safety=fake_bundle("safety"),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 2
    assert payload["db_root"]["password"] == "restore-secret"
    assert path.stat().st_mode & 0o777 == 0o600
