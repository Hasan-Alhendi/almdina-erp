from __future__ import annotations

from dataclasses import dataclass


DB_TYPES = frozenset({"mariadb", "postgres", "sqlite"})
DEFAULT_PORTS = {
    "mariadb": 3306,
    "postgres": 5432,
}


@dataclass(frozen=True, slots=True)
class DbRootConnection:
    """Resolved privileged DB connection used only for restore readiness/testing."""

    db_type: str
    host: str
    port: int
    username: str
    password: str
    source: str

    def validated(self) -> "DbRootConnection":
        db_type = str(self.db_type or "").strip().lower()
        if db_type not in DB_TYPES:
            raise ValueError("Database type must be MariaDB, PostgreSQL, or SQLite.")
        if db_type == "sqlite":
            return DbRootConnection(
                db_type=db_type,
                host="",
                port=0,
                username="",
                password="",
                source=str(self.source or "frappe").strip() or "frappe",
            )

        host = str(self.host or "").strip()
        username = str(self.username or "").strip()
        source = str(self.source or "").strip() or "frappe"
        if not host:
            raise ValueError("Database host is required.")
        if not username:
            raise ValueError("Root username is required.")
        if "\x00" in host or "\x00" in username:
            raise ValueError("Database connection values are invalid.")
        try:
            port = int(self.port)
        except (TypeError, ValueError) as exc:
            raise ValueError("Database port is invalid.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("Database port must be between 1 and 65535.")
        password = str(self.password or "")
        if not password:
            raise ValueError("Root password is required.")
        return DbRootConnection(
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            source=source,
        )

    @property
    def is_complete(self) -> bool:
        try:
            self.validated()
        except ValueError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class DbRootDefaults:
    db_type: str = "mariadb"
    host: str = "127.0.0.1"
    port: int = 3306
    username: str = "root"
    password: str = ""


@dataclass(frozen=True, slots=True)
class DbRootOverrides:
    db_type: str = ""
    host: str = ""
    port: int | None = None
    username: str = ""
    password: str = ""

    @property
    def has_custom_values(self) -> bool:
        return bool(
            str(self.db_type or "").strip()
            or str(self.host or "").strip()
            or self.port is not None
            or str(self.username or "").strip()
            or str(self.password or "")
        )


def default_port_for(db_type: str) -> int:
    normalized = str(db_type or "").strip().lower()
    return int(DEFAULT_PORTS.get(normalized, 3306))


def resolve_db_root_connection(
    *,
    defaults: DbRootDefaults,
    overrides: DbRootOverrides,
) -> DbRootConnection:
    """Prefer Almadina overrides when present; otherwise keep Frappe operational defaults."""

    base_type = str(defaults.db_type or "mariadb").strip().lower() or "mariadb"
    override_type = str(overrides.db_type or "").strip().lower()
    db_type = override_type or base_type
    if db_type == "maria":
        db_type = "mariadb"
    if db_type == "postgresql":
        db_type = "postgres"

    source = "custom" if overrides.has_custom_values else "frappe"
    host = str(overrides.host or "").strip() or str(defaults.host or "").strip() or "127.0.0.1"
    username = (
        str(overrides.username or "").strip()
        or str(defaults.username or "").strip()
        or ("postgres" if db_type == "postgres" else "root")
    )
    if overrides.port is not None:
        port = int(overrides.port)
    elif defaults.port:
        port = int(defaults.port)
    else:
        port = default_port_for(db_type)
    if db_type == "sqlite":
        return DbRootConnection(
            db_type="sqlite",
            host="",
            port=0,
            username="",
            password="",
            source=source,
        )
    password = str(overrides.password or "") or str(defaults.password or "")
    return DbRootConnection(
        db_type=db_type,
        host=host,
        port=port,
        username=username,
        password=password,
        source=source,
    )


def connection_is_ready(connection: DbRootConnection | None) -> bool:
    if connection is None:
        return False
    if connection.db_type == "sqlite":
        return True
    return connection.is_complete


__all__ = [
    "DB_TYPES",
    "DEFAULT_PORTS",
    "DbRootConnection",
    "DbRootDefaults",
    "DbRootOverrides",
    "connection_is_ready",
    "default_port_for",
    "resolve_db_root_connection",
]
