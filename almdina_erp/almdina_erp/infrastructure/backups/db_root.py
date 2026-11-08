from __future__ import annotations

from typing import Any, Callable

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.backups.db_root import (
    DbRootConnection,
    DbRootDefaults,
    DbRootOverrides,
    connection_is_ready,
    default_port_for,
    resolve_db_root_connection,
)


class DbRootConnectionError(RuntimeError):
    safe_code = "db_root_connection_failed"


class DbRootSettingsIncomplete(DbRootConnectionError):
    safe_code = "db_root_settings_incomplete"


class DbRootAuthenticationError(DbRootConnectionError):
    safe_code = "db_root_authentication_failed"


class DbRootHostUnreachable(DbRootConnectionError):
    safe_code = "db_root_host_unreachable"


class DbRootInsufficientPrivileges(DbRootConnectionError):
    safe_code = "db_root_insufficient_privileges"


def _conf_password(db_type: str) -> str:
    conf = frappe.conf
    if db_type == "postgres":
        return str(conf.get("postgres_root_password") or conf.get("root_password") or "")
    return str(conf.get("mariadb_root_password") or conf.get("root_password") or "")


def _conf_username(db_type: str) -> str:
    conf = frappe.conf
    if db_type == "postgres":
        return str(conf.get("postgres_root_login") or conf.get("root_login") or "postgres")
    return str(conf.get("mariadb_root_login") or conf.get("root_login") or "root")


def _normalize_ui_type(value: object) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    if text in {"mariadb", "maria"}:
        return "MariaDB"
    if text in {"postgres", "postgresql"}:
        return "PostgreSQL"
    if text == "sqlite":
        return "SQLite"
    return ""


def frappe_db_root_defaults() -> DbRootDefaults:
    db_type = str(frappe.conf.db_type or "mariadb").strip().lower() or "mariadb"
    if db_type == "maria":
        db_type = "mariadb"
    if db_type == "postgresql":
        db_type = "postgres"
    host = str(frappe.conf.db_host or "").strip() or "127.0.0.1"
    raw_port = frappe.conf.db_port
    port = cint(raw_port) if raw_port not in (None, "") else default_port_for(db_type)
    return DbRootDefaults(
        db_type=db_type,
        host=host,
        port=port or default_port_for(db_type),
        username=_conf_username(db_type),
        password=_conf_password(db_type),
    )


def settings_db_root_overrides(settings: Any | None = None) -> DbRootOverrides:
    settings = settings or frappe.get_single("Almdina ERP Settings")
    raw_type = str(settings.get("db_restore_type") or "").strip().lower()
    if raw_type in {"maria", "mariadb"}:
        raw_type = "mariadb"
    elif raw_type in {"postgresql", "postgres"}:
        raw_type = "postgres"
    elif raw_type == "sqlite":
        raw_type = "sqlite"
    else:
        raw_type = ""

    raw_port = settings.get("db_restore_port")
    if raw_port in (None, ""):
        port: int | None = None
    else:
        port = cint(raw_port) or None

    password = str(settings.get_password("db_restore_root_password", raise_exception=False) or "")
    return DbRootOverrides(
        db_type=raw_type,
        host=str(settings.get("db_restore_host") or "").strip(),
        port=port,
        username=str(settings.get("db_restore_root_username") or "").strip(),
        password=password,
    )


def resolve_effective_db_root(settings: Any | None = None) -> DbRootConnection:
    return resolve_db_root_connection(
        defaults=frappe_db_root_defaults(),
        overrides=settings_db_root_overrides(settings),
    )


def restore_runtime_ready(settings: Any | None = None) -> bool:
    try:
        return connection_is_ready(resolve_effective_db_root(settings))
    except Exception:
        return False


def public_db_root_settings(settings: Any | None = None) -> dict[str, Any]:
    """Browser-safe DB restore settings: never includes the password value."""

    defaults = frappe_db_root_defaults()
    overrides = settings_db_root_overrides(settings)
    resolved = resolve_db_root_connection(defaults=defaults, overrides=overrides)
    custom_password = bool(overrides.password)
    frappe_password = bool(defaults.password)
    display_type = _normalize_ui_type(overrides.db_type) or _normalize_ui_type(defaults.db_type) or "MariaDB"
    return {
        "db_restore_type": display_type,
        "db_restore_host": overrides.host or defaults.host,
        "db_restore_port": overrides.port if overrides.port is not None else defaults.port,
        "db_restore_root_username": overrides.username or defaults.username,
        "db_restore_root_password_configured": bool(custom_password or frappe_password),
        "db_restore_custom_password_configured": custom_password,
        "db_restore_source": resolved.source,
        "db_restore_ready": connection_is_ready(resolved),
        "db_restore_frappe_defaults": {
            "db_type": _normalize_ui_type(defaults.db_type) or "MariaDB",
            "host": defaults.host,
            "port": defaults.port,
            "username": defaults.username,
            "password_configured": frappe_password,
        },
    }


def credentials_payload(connection: DbRootConnection) -> dict[str, Any]:
    """Serialize credentials for the private restore request file only."""

    if connection.db_type == "sqlite":
        return {"db_type": "sqlite"}
    validated = connection.validated()
    return {
        "db_type": validated.db_type,
        "host": validated.host,
        "port": validated.port,
        "username": validated.username,
        "password": validated.password,
    }


def _connect_mariadb(connection: DbRootConnection) -> Any:
    try:
        import pymysql
    except ImportError as exc:
        raise DbRootConnectionError("MariaDB client library is unavailable.") from exc
    try:
        return pymysql.connect(
            host=connection.host,
            port=connection.port,
            user=connection.username,
            password=connection.password,
            connect_timeout=8,
            read_timeout=8,
            write_timeout=8,
            autocommit=True,
        )
    except pymysql.err.OperationalError as exc:
        code = int(exc.args[0]) if exc.args else 0
        if code in {1045, 1698, 1044}:
            raise DbRootAuthenticationError("Database authentication failed.") from exc
        if code in {2003, 2002, 2006, 2013}:
            raise DbRootHostUnreachable("Database host or port is unreachable.") from exc
        raise DbRootConnectionError("Database connection failed.") from exc
    except OSError as exc:
        raise DbRootHostUnreachable("Database host or port is unreachable.") from exc


def _connect_postgres(connection: DbRootConnection) -> Any:
    try:
        import psycopg2
    except ImportError as exc:
        raise DbRootConnectionError("PostgreSQL client library is unavailable.") from exc
    try:
        return psycopg2.connect(
            host=connection.host,
            port=connection.port,
            user=connection.username,
            password=connection.password,
            dbname="postgres",
            connect_timeout=8,
        )
    except Exception as exc:
        message = str(exc).lower()
        if "password" in message or "authentication" in message:
            raise DbRootAuthenticationError("Database authentication failed.") from exc
        if "could not connect" in message or "timeout" in message or "refused" in message:
            raise DbRootHostUnreachable("Database host or port is unreachable.") from exc
        raise DbRootConnectionError("Database connection failed.") from exc


def _mariadb_has_restore_privileges(connection: Any) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.execute("SHOW GRANTS")
        grants = " ".join(str(row[0]).upper() for row in cursor.fetchall())
    if "ALL PRIVILEGES ON *.*" in grants:
        return True
    if "ON *.*" in grants and "WITH GRANT OPTION" in grants:
        return True
    required = ("CREATE", "DROP", "ALTER", "INSERT", "DELETE", "CREATE USER")
    return all(token in grants for token in required) and "ON *.*" in grants


def _postgres_has_restore_privileges(connection: Any) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.execute("SELECT COALESCE(rolsuper, false) FROM pg_roles WHERE rolname = current_user")
        row = cursor.fetchone()
    return bool(row and row[0])


def test_db_root_connection(
    connection: DbRootConnection,
    *,
    mariadb_connect: Callable[[DbRootConnection], Any] | None = None,
    postgres_connect: Callable[[DbRootConnection], Any] | None = None,
) -> dict[str, Any]:
    """Authenticate and verify restore-capable privileges without mutating databases."""

    try:
        validated = connection.validated()
    except ValueError as exc:
        raise DbRootSettingsIncomplete(str(exc)) from exc

    if validated.db_type == "sqlite":
        return {
            "ok": True,
            "authenticated": True,
            "has_restore_privileges": True,
            "safe_code": "db_root_sqlite_ready",
            "source": validated.source,
        }

    handle = None
    try:
        try:
            if validated.db_type == "postgres":
                handle = (postgres_connect or _connect_postgres)(validated)
                privileged = _postgres_has_restore_privileges(handle)
            else:
                handle = (mariadb_connect or _connect_mariadb)(validated)
                privileged = _mariadb_has_restore_privileges(handle)
        except DbRootConnectionError:
            raise
        except Exception as exc:
            # Test doubles may raise driver errors directly; keep codes safe.
            message = str(exc).lower()
            if "access denied" in message or "authentication" in message or "password" in message:
                raise DbRootAuthenticationError("Database authentication failed.") from exc
            if "can't connect" in message or "could not connect" in message or "refused" in message or "timeout" in message:
                raise DbRootHostUnreachable("Database host or port is unreachable.") from exc
            if getattr(exc, "args", None) and exc.args and exc.args[0] in {1045, 1698, 1044}:
                raise DbRootAuthenticationError("Database authentication failed.") from exc
            if getattr(exc, "args", None) and exc.args and exc.args[0] in {2003, 2002, 2006, 2013}:
                raise DbRootHostUnreachable("Database host or port is unreachable.") from exc
            raise DbRootConnectionError("Database connection failed.") from exc
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

    if not privileged:
        raise DbRootInsufficientPrivileges("Database user lacks restore privileges.")
    return {
        "ok": True,
        "authenticated": True,
        "has_restore_privileges": True,
        "safe_code": "db_root_connection_ok",
        "source": validated.source,
    }


__all__ = [
    "DbRootAuthenticationError",
    "DbRootConnectionError",
    "DbRootHostUnreachable",
    "DbRootInsufficientPrivileges",
    "DbRootSettingsIncomplete",
    "credentials_payload",
    "frappe_db_root_defaults",
    "public_db_root_settings",
    "resolve_effective_db_root",
    "restore_runtime_ready",
    "settings_db_root_overrides",
    "test_db_root_connection",
]
