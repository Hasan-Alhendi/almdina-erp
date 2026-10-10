from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BackupArtifact:
    kind: str
    path: str
    filename: str
    size: int
    checksum: str


@dataclass(frozen=True, slots=True)
class BackupBundle:
    identifier: str
    artifacts: tuple[BackupArtifact, ...]

    @property
    def total_size(self) -> int:
        return sum(max(0, int(artifact.size)) for artifact in self.artifacts)


class BackupEngine(Protocol):
    def create(self) -> BackupBundle: ...

    def release(self, bundle: BackupBundle) -> None: ...


class BackupHistory(Protocol):
    def mark_running(self, operation_id: str) -> None: ...

    def mark_completed(self, operation_id: str, bundle: BackupBundle, reference: str = "") -> None: ...

    def mark_failed(self, operation_id: str, error_code: str) -> None: ...


class LocalRetentionGateway(Protocol):
    def apply(self, keep_last: int) -> None: ...


class ExternalBackupGateway(Protocol):
    def test_connection(self) -> None: ...

    def upload(self, bundle: BackupBundle) -> str: ...

    def apply_retention(self, keep_last: int) -> None: ...


def run_backup(
    *,
    operation_id: str,
    target: str,
    engine: BackupEngine,
    history: BackupHistory,
    keep_last: int,
    local_retention: LocalRetentionGateway | None = None,
    external: ExternalBackupGateway | None = None,
) -> BackupBundle:
    """Create one Frappe backup and apply retention only after success."""

    normalized_target = str(target or "").strip().lower()
    if normalized_target not in {"local", "external"}:
        raise ValueError("Backup target must be local or external.")
    if normalized_target == "local" and local_retention is None:
        raise ValueError("Local retention gateway is required.")
    if normalized_target == "external" and external is None:
        raise ValueError("External backup gateway is required.")

    history.mark_running(operation_id)
    bundle: BackupBundle | None = None
    try:
        bundle = engine.create()
        if normalized_target == "external":
            reference = external.upload(bundle)
            external.apply_retention(keep_last)
        else:
            reference = bundle.identifier
            local_retention.apply(keep_last)
        history.mark_completed(operation_id, bundle, reference)
        return bundle
    except Exception as exc:
        history.mark_failed(operation_id, _safe_error_code(exc))
        raise
    finally:
        if bundle is not None:
            engine.release(bundle)


def test_external_connection(gateway: ExternalBackupGateway) -> None:
    gateway.test_connection()


def _safe_error_code(error: Exception) -> str:
    code = getattr(error, "safe_code", None)
    if code:
        return str(code)[:140]
    return error.__class__.__name__[:140]


__all__ = [
    "BackupArtifact",
    "BackupBundle",
    "BackupEngine",
    "BackupHistory",
    "ExternalBackupGateway",
    "LocalRetentionGateway",
    "run_backup",
    "test_external_connection",
]
