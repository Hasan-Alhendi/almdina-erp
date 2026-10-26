from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
    run_backup,
)


class FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.released = False

    def create(self) -> BackupBundle:
        if self.fail:
            raise RuntimeError("database password must never reach history")
        return BackupBundle(
            "20261008_020000-site",
            (BackupArtifact("database", "/private/db.sql.gz", "db.sql.gz", 10, "abc"),),
        )

    def release(self, bundle: BackupBundle) -> None:
        self.released = bool(bundle)


class FakeHistory:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def mark_running(self, operation_id: str) -> None:
        self.events.append(("running", operation_id))

    def mark_completed(self, operation_id: str, bundle: BackupBundle, reference: str = "") -> None:
        self.events.append(("completed", reference))

    def mark_failed(self, operation_id: str, error_code: str) -> None:
        self.events.append(("failed", error_code))


class FakeRetention:
    def __init__(self) -> None:
        self.applied: list[int] = []

    def apply(self, keep_last: int) -> None:
        self.applied.append(keep_last)


class FakeExternal:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.fail_upload = fail_upload
        self.retention: list[int] = []

    def test_connection(self) -> None:
        return None

    def upload(self, bundle: BackupBundle) -> str:
        if self.fail_upload:
            raise OSError("secret remote error")
        return f"/remote/{bundle.identifier}"

    def apply_retention(self, keep_last: int) -> None:
        self.retention.append(keep_last)


def test_manual_local_backup_applies_retention_after_success() -> None:
    history = FakeHistory()
    retention = FakeRetention()
    engine = FakeEngine()
    result = run_backup(
        operation_id="op-1",
        target="local",
        engine=engine,
        history=history,
        keep_last=7,
        local_retention=retention,
    )
    assert result.identifier.endswith("-site")
    assert retention.applied == [7]
    assert history.events[-1][0] == "completed"
    assert engine.released is True


def test_failed_backup_never_runs_retention_and_history_has_safe_code_only() -> None:
    history = FakeHistory()
    retention = FakeRetention()
    with pytest.raises(RuntimeError):
        run_backup(
            operation_id="op-2",
            target="local",
            engine=FakeEngine(fail=True),
            history=history,
            keep_last=7,
            local_retention=retention,
        )
    assert retention.applied == []
    assert history.events[-1] == ("failed", "RuntimeError")


def test_external_upload_failure_never_runs_external_retention() -> None:
    external = FakeExternal(fail_upload=True)
    history = FakeHistory()
    with pytest.raises(OSError):
        run_backup(
            operation_id="op-3",
            target="external",
            engine=FakeEngine(),
            history=history,
            keep_last=4,
            external=external,
        )
    assert external.retention == []
    assert history.events[-1] == ("failed", "OSError")
