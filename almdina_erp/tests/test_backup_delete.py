from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from almdina_erp.almdina_erp.application.backups.delete_backup import (
    DELETE_ORPHAN_ERROR_CODES,
    BackupDeleteError,
    BackupDeleteResult,
    DeletableBackupOperation,
    delete_backup_operation,
)
from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.backups.export_zip import annotate_downloadable
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory
from almdina_erp.almdina_erp.services import backup_restore_service as service


IDENTIFIER = "20261108_120000-site_local"
KINDS = (
    ("database", f"{IDENTIFIER}-database.sql.gz", b"db-bytes"),
    ("public_files", f"{IDENTIFIER}-files.tgz", b"pub-bytes"),
    ("private_files", f"{IDENTIFIER}-private-files.tgz", b"priv-bytes"),
    ("site_config", f"{IDENTIFIER}-site_config_backup.json", b'{"ok":1}'),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bundle(root: Path) -> BackupBundle:
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for kind, filename, payload in KINDS:
        path = root / filename
        path.write_bytes(payload)
        artifacts.append(
            BackupArtifact(
                kind=kind,
                path=str(path.resolve()),
                filename=filename,
                size=len(payload),
                checksum=_sha(payload),
            )
        )
    return BackupBundle(identifier=IDENTIFIER, artifacts=tuple(artifacts))


def _manifest_json(bundle: BackupBundle) -> str:
    return json.dumps(
        [
            {
                "kind": artifact.kind,
                "filename": artifact.filename,
                "size": artifact.size,
                "checksum": artifact.checksum,
            }
            for artifact in bundle.artifacts
        ]
    )


class FakeDeleteGateway:
    def __init__(
        self,
        operation: DeletableBackupOperation,
        *,
        shared_refs: int = 0,
        restore_protected: bool = False,
        busy: bool = False,
        bundle: BackupBundle | None = None,
        artifacts_absent: bool = False,
        fail_files_at: int | None = None,
        fail_files: bool = False,
        fail_record: bool = False,
        fail_record_after_files: bool = False,
        sftp_remove_calls: list[Any] | None = None,
    ) -> None:
        self.operation = operation
        self.shared_refs = shared_refs
        self.restore_protected = restore_protected
        self.busy = busy
        self.bundle = bundle
        self.artifacts_absent = artifacts_absent
        self.fail_files_at = fail_files_at
        self.fail_files = fail_files
        self.fail_record = fail_record
        self.fail_record_after_files = fail_record_after_files
        self.sftp_remove_calls = sftp_remove_calls if sftp_remove_calls is not None else []
        self.deleted_files = False
        self.deleted_record = False
        self.load_calls = 0
        self.events: list[str] = []
        self.marked_codes: list[str] = []
        self.status = operation.status
        self.error_summary = operation.error_summary

    def load_operation(self, operation_id: str) -> DeletableBackupOperation:
        self.load_calls += 1
        if operation_id != self.operation.operation_id:
            raise BackupDeleteError("backup_delete_not_found")
        return DeletableBackupOperation(
            operation_id=self.operation.operation_id,
            operation_type=self.operation.operation_type,
            target=self.operation.target,
            status=self.status,
            backup_identifier=self.operation.backup_identifier,
            error_summary=self.error_summary,
        )

    def count_other_local_references(self, backup_identifier: str, *, exclude_operation_id: str) -> int:
        assert backup_identifier == self.operation.backup_identifier
        assert exclude_operation_id == self.operation.operation_id
        return self.shared_refs

    def is_protected_by_active_restore(self, *, operation_id: str, backup_identifier: str) -> bool:
        return self.restore_protected

    def is_backup_or_export_busy(self, *, operation_id: str, backup_identifier: str) -> bool:
        return self.busy

    def prepare_local_delete_bundle(self, operation_id: str) -> BackupBundle:
        assert operation_id == self.operation.operation_id
        assert self.status == "Completed"
        self.events.append("prepare")
        assert self.bundle is not None
        return self.bundle

    def local_artifacts_absent(self, operation_id: str) -> bool:
        assert operation_id == self.operation.operation_id
        self.events.append("artifacts_absent_check")
        return self.artifacts_absent

    def mark_operation_failed(self, operation_id: str, error_code: str) -> None:
        assert operation_id == self.operation.operation_id
        self.status = "Failed"
        self.error_summary = error_code
        self.marked_codes.append(error_code)
        self.events.append(f"mark:{error_code}")

    def delete_prepared_local_files(self, bundle: BackupBundle) -> None:
        self.events.append("unlink_start")
        assert "mark:backup_delete_pending" in self.events
        assert self.events.index("mark:backup_delete_pending") < self.events.index("unlink_start")
        if self.fail_files:
            raise BackupDeleteError("backup_delete_files_failed")
        for index, artifact in enumerate(bundle.artifacts):
            if self.fail_files_at is not None and index == self.fail_files_at:
                self.events.append(f"unlink_fail_at:{index}")
                raise BackupDeleteError("backup_delete_files_failed")
            Path(artifact.path).unlink(missing_ok=True)
            self.events.append(f"unlink:{index}")
        self.deleted_files = True
        self.events.append("unlink_done")

    def delete_remaining_local_files(self, operation_id: str) -> None:
        assert operation_id == self.operation.operation_id
        self.events.append("unlink_remaining_start")
        assert self.bundle is not None
        if self.fail_files:
            raise BackupDeleteError("backup_delete_files_failed")
        for index, artifact in enumerate(self.bundle.artifacts):
            if self.fail_files_at is not None and index == self.fail_files_at:
                raise BackupDeleteError("backup_delete_files_failed")
            Path(artifact.path).unlink(missing_ok=True)
        self.deleted_files = True
        self.events.append("unlink_remaining_done")

    def delete_operation_record(self, operation_id: str) -> None:
        assert operation_id == self.operation.operation_id
        if self.fail_record or (self.fail_record_after_files and self.deleted_files):
            raise BackupDeleteError("backup_delete_record_failed")
        self.deleted_record = True
        self.events.append("record_deleted")


def test_delete_marks_failed_before_first_unlink(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "backups")
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-local", "Manual", "Local", "Completed", IDENTIFIER),
        bundle=bundle,
    )
    result = delete_backup_operation(operation_id="op-local", gateway=gateway)
    assert result.outcome == "files_and_record"
    assert gateway.marked_codes[0] == "backup_delete_pending"
    assert gateway.events.index("mark:backup_delete_pending") < gateway.events.index("unlink_start")
    assert gateway.events.index("unlink_start") < gateway.events.index("unlink:0")
    assert all(not Path(artifact.path).exists() for artifact in bundle.artifacts)


def test_delete_imported_removes_files(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "backups")
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-imp", "Imported", "Local", "Completed", IDENTIFIER),
        bundle=bundle,
    )
    result = delete_backup_operation(operation_id="op-imp", gateway=gateway)
    assert result.outcome == "files_and_record"
    assert gateway.deleted_files and gateway.deleted_record


def test_shared_reference_deletes_record_only_without_mark(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "backups")
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-a", "Manual", "Local", "Completed", IDENTIFIER),
        shared_refs=1,
        bundle=bundle,
    )
    result = delete_backup_operation(operation_id="op-a", gateway=gateway)
    assert result.outcome == "record_only_shared_refs"
    assert result.files_deleted is False
    assert gateway.deleted_files is False
    assert gateway.marked_codes == []
    assert all(Path(artifact.path).exists() for artifact in bundle.artifacts)


def test_restore_protection_rejects_safety_delete() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-safety", "Safety", "Local", "Completed", IDENTIFIER),
        restore_protected=True,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_restore_protected"):
        delete_backup_operation(operation_id="op-safety", gateway=gateway)
    assert gateway.deleted_files is False
    assert gateway.deleted_record is False
    assert gateway.marked_codes == []


def test_active_restore_rejects_delete() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-src", "Scheduled", "Local", "Completed", IDENTIFIER),
        restore_protected=True,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_restore_protected"):
        delete_backup_operation(operation_id="op-src", gateway=gateway)


def test_busy_backup_or_export_rejects_delete() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-src", "Manual", "Local", "Completed", IDENTIFIER),
        busy=True,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_operation_busy"):
        delete_backup_operation(operation_id="op-src", gateway=gateway)


def test_external_deletes_record_only_never_remote() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-ext", "Scheduled", "External", "Completed", IDENTIFIER),
    )
    result = delete_backup_operation(operation_id="op-ext", gateway=gateway)
    assert result.outcome == "record_only_external"
    assert result.files_deleted is False
    assert result.remote_files_deleted is False
    assert gateway.deleted_record is True
    assert gateway.sftp_remove_calls == []
    assert gateway.marked_codes == []


def test_rejects_incomplete_operation() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-q", "Manual", "Local", "Queued", IDENTIFIER),
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_not_eligible"):
        delete_backup_operation(operation_id="op-q", gateway=gateway)


def test_first_file_delete_failure_marks_files_failed(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "backups")
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-local", "Manual", "Local", "Completed", IDENTIFIER),
        bundle=bundle,
        fail_files_at=0,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_files_failed"):
        delete_backup_operation(operation_id="op-local", gateway=gateway)
    assert gateway.marked_codes == ["backup_delete_pending", "backup_delete_files_failed"]
    assert gateway.status == "Failed"
    assert gateway.error_summary == "backup_delete_files_failed"
    assert gateway.deleted_record is False
    assert all(Path(artifact.path).exists() for artifact in bundle.artifacts)


def test_mid_bundle_file_delete_failure_marks_files_failed(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "backups")
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-local", "Manual", "Local", "Completed", IDENTIFIER),
        bundle=bundle,
        fail_files_at=2,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_files_failed"):
        delete_backup_operation(operation_id="op-local", gateway=gateway)
    assert gateway.marked_codes == ["backup_delete_pending", "backup_delete_files_failed"]
    assert gateway.status == "Failed"
    assert gateway.deleted_record is False
    assert not Path(bundle.artifacts[0].path).exists()
    assert not Path(bundle.artifacts[1].path).exists()
    assert Path(bundle.artifacts[2].path).exists()
    assert Path(bundle.artifacts[3].path).exists()


def test_record_failure_after_files_surfaces_distinct_code(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "backups")
    gateway = FakeDeleteGateway(
        DeletableBackupOperation("op-local", "Manual", "Local", "Completed", IDENTIFIER),
        bundle=bundle,
        fail_record_after_files=True,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_record_failed_after_files"):
        delete_backup_operation(operation_id="op-local", gateway=gateway)
    assert gateway.deleted_files is True
    assert gateway.marked_codes[-1] == "backup_delete_record_failed_after_files"
    assert gateway.status == "Failed"
    assert gateway.error_summary == "backup_delete_record_failed_after_files"


def test_orphan_retry_deletes_record_when_files_already_absent() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation(
            "op-orphan",
            "Manual",
            "Local",
            "Failed",
            IDENTIFIER,
            error_summary="backup_delete_record_failed_after_files",
        ),
        artifacts_absent=True,
    )
    result = delete_backup_operation(operation_id="op-orphan", gateway=gateway)
    assert result.outcome == "record_only_orphan_cleanup"
    assert result.files_deleted is False
    assert gateway.deleted_record is True
    assert "prepare" not in gateway.events
    assert gateway.marked_codes == []


def test_ordinary_failed_operation_is_not_retryable_for_delete() -> None:
    gateway = FakeDeleteGateway(
        DeletableBackupOperation(
            "op-fail",
            "Manual",
            "Local",
            "Failed",
            IDENTIFIER,
            error_summary="external_sftp_timeout",
        ),
        artifacts_absent=True,
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_not_eligible"):
        delete_backup_operation(operation_id="op-fail", gateway=gateway)
    assert gateway.deleted_record is False
    assert "external_sftp_timeout" not in DELETE_ORPHAN_ERROR_CODES


def test_delete_endpoint_requires_manage_backups_before_work(monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []

    def deny(capability: str, **_kwargs: Any) -> None:
        checked.append(capability)
        raise PermissionError("denied")

    monkeypatch.setattr(service, "require_doctype_capability", deny)
    with pytest.raises(PermissionError):
        service.delete_backup("op-1")
    assert checked == [Capability.MANAGE_BACKUPS]


def test_delete_endpoint_external_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "require_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "_", lambda message: message)

    class Gateway:
        pass

    monkeypatch.setattr(service, "FrappeBackupDeleteGateway", Gateway)
    monkeypatch.setattr(
        service,
        "run_delete_backup_operation",
        lambda **_kwargs: BackupDeleteResult(
            operation_id="op-ext",
            backup_identifier=IDENTIFIER,
            target="External",
            operation_type="Scheduled",
            files_deleted=False,
            record_deleted=True,
            remote_files_deleted=False,
            outcome="record_only_external",
        ),
    )
    payload = service.delete_backup("op-ext")
    assert payload["remote_files_deleted"] is False
    assert "Remote external files were not removed" in str(payload["message"])


def test_history_mark_failed_excludes_from_restorable_and_downloadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove real History/annotate contracts after Failed delete markers."""

    store: dict[str, dict[str, Any]] = {
        "op-pending": {
            "operation_id": "op-pending",
            "operation_type": "Manual",
            "target": "Local",
            "status": "Completed",
            "backup_identifier": IDENTIFIER,
            "retry_log": "[]",
            "started_on": "2026-11-08 12:00:00",
            "attempt_count": 1,
            "error_summary": "",
            "requested_on": "2026-11-08 12:00:00",
            "total_size": 10,
            "checksum": "c" * 64,
            "artifact_manifest": "[]",
        }
    }

    def exists(_doctype: str, name: str) -> bool:
        return name in store

    def get_value(_doctype: str, name: str, fields: Any, **kwargs: Any) -> Any:
        row = store.get(str(name))
        if not row:
            return None
        if isinstance(fields, str):
            return row.get(fields)
        payload = {field: row.get(field) for field in fields}
        if kwargs.get("as_dict"):
            return payload
        return SimpleNamespace(**payload)

    def set_value(_doctype: str, name: str, values: dict[str, Any], **_kwargs: Any) -> None:
        store[str(name)].update(values)

    def get_all(_doctype: str, *, filters: dict[str, Any] | None = None, fields: list[str], **_kwargs: Any):
        rows = []
        for row in store.values():
            if filters:
                if filters.get("target") and row.get("target") != filters["target"]:
                    continue
                if filters.get("status") and row.get("status") != filters["status"]:
                    continue
                op_types = filters.get("operation_type")
                if isinstance(op_types, list) and op_types and op_types[0] == "in":
                    if row.get("operation_type") not in op_types[1]:
                        continue
            rows.append({field: row.get(field) for field in fields})
        return rows

    history_mod = __import__(
        "almdina_erp.almdina_erp.infrastructure.backups.history",
        fromlist=["frappe"],
    )
    monkeypatch.setattr(
        history_mod.frappe,
        "db",
        SimpleNamespace(exists=exists, get_value=get_value, set_value=set_value),
        raising=False,
    )
    monkeypatch.setattr(history_mod.frappe, "get_all", get_all, raising=False)
    monkeypatch.setattr(history_mod, "now", lambda: "2026-11-08 12:30:00")
    monkeypatch.setattr(history_mod, "cint", int)

    history = FrappeBackupHistory()
    assert any(row["operation_id"] == "op-pending" for row in history.restorable())

    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    gateway = delete_mod.FrappeBackupDeleteGateway(history=history)
    gateway.mark_operation_failed("op-pending", "backup_delete_pending")

    assert store["op-pending"]["status"] == "Failed"
    assert store["op-pending"]["error_summary"] == "backup_delete_pending"
    assert history.restorable() == []

    monkeypatch.setattr(
        "almdina_erp.almdina_erp.infrastructure.backups.export_zip.frappe",
        SimpleNamespace(local=SimpleNamespace(site="site.local")),
        raising=False,
    )
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.infrastructure.backups.export_zip._local_backup_identifiers_present",
        lambda _slug: {IDENTIFIER},
    )
    annotated = annotate_downloadable(
        [
            {
                "operation_id": "op-pending",
                "status": store["op-pending"]["status"],
                "target": "Local",
                "operation_type": "Manual",
                "backup_identifier": IDENTIFIER,
                "artifact_manifest": "[]",
            }
        ]
    )
    assert annotated[0]["can_download"] is False


def test_infra_mid_file_unlink_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    backups = tmp_path / "backups"
    bundle = _write_bundle(backups)
    unlink_calls = {"count": 0}
    real_unlink = Path.unlink

    def counting_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        unlink_calls["count"] += 1
        if unlink_calls["count"] == 3:
            raise OSError("simulated mid-delete failure")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", counting_unlink)
    monkeypatch.setattr(delete_mod.frappe, "local", SimpleNamespace(site="site.local"), raising=False)
    monkeypatch.setattr("frappe.utils.backups.get_backup_path", lambda: str(backups))

    gateway = delete_mod.FrappeBackupDeleteGateway(
        history=SimpleNamespace()  # type: ignore[arg-type]
    )
    with pytest.raises(BackupDeleteError, match="backup_delete_files_failed"):
        gateway.delete_prepared_local_files(bundle)
    assert Path(bundle.artifacts[0].path).exists() is False
    assert Path(bundle.artifacts[1].path).exists() is False
    assert Path(bundle.artifacts[2].path).exists() is True


def test_infra_local_artifacts_absent_and_remaining(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    backups = tmp_path / "backups"
    bundle = _write_bundle(backups)
    manifest = _manifest_json(bundle)
    store = {
        "op-1": {
            "backup_identifier": IDENTIFIER,
            "artifact_manifest": manifest,
        }
    }

    monkeypatch.setattr(
        delete_mod.frappe,
        "db",
        SimpleNamespace(
            get_value=lambda _d, name, fields, **_k: SimpleNamespace(
                **{field: store[str(name)][field] for field in fields}
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(delete_mod.frappe, "local", SimpleNamespace(site="site.local"), raising=False)
    monkeypatch.setattr("frappe.utils.backups.get_backup_path", lambda: str(backups))
    gateway = delete_mod.FrappeBackupDeleteGateway(history=SimpleNamespace())  # type: ignore[arg-type]
    assert gateway.local_artifacts_absent("op-1") is False
    for artifact in bundle.artifacts:
        Path(artifact.path).unlink()
    assert gateway.local_artifacts_absent("op-1") is True


def test_infra_rejects_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    backups = tmp_path / "backups"
    bundle = _write_bundle(backups)
    sym_name = KINDS[0][1]
    target = backups / sym_name
    target.unlink()
    real = backups / f"real-{sym_name}"
    real.write_bytes(KINDS[0][2])
    (backups / sym_name).symlink_to(real.name)

    artifacts = []
    for kind, filename, payload in KINDS:
        path = backups / filename
        artifacts.append(
            BackupArtifact(
                kind=kind,
                path=str(path),
                filename=filename,
                size=len(payload),
                checksum=_sha(payload if filename != sym_name else KINDS[0][2]),
            )
        )
    sym_bundle = BackupBundle(identifier=IDENTIFIER, artifacts=tuple(artifacts))

    monkeypatch.setattr(delete_mod.frappe, "local", SimpleNamespace(site="site.local"), raising=False)
    monkeypatch.setattr("frappe.utils.backups.get_backup_path", lambda: str(backups))
    gateway = delete_mod.FrappeBackupDeleteGateway(history=SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(BackupDeleteError, match="backup_delete_symlink_rejected"):
        gateway.delete_prepared_local_files(sym_bundle)


def test_infra_rejects_symlink_escaping_backup_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    backups = tmp_path / "backups"
    backups.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    payload = b"escaped"
    outside_file = outside / "secret.bin"
    outside_file.write_bytes(payload)
    artifacts = []
    for kind, filename, data in KINDS:
        path = backups / filename
        if kind == "database":
            path.symlink_to(outside_file)
        else:
            path.write_bytes(data)
        artifacts.append(
            BackupArtifact(
                kind=kind,
                path=str(path),
                filename=filename,
                size=len(payload if kind == "database" else data),
                checksum=_sha(payload if kind == "database" else data),
            )
        )
    bundle = BackupBundle(identifier=IDENTIFIER, artifacts=tuple(artifacts))

    monkeypatch.setattr(delete_mod.frappe, "local", SimpleNamespace(site="site.local"), raising=False)
    monkeypatch.setattr("frappe.utils.backups.get_backup_path", lambda: str(backups))
    gateway = delete_mod.FrappeBackupDeleteGateway(history=SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(BackupDeleteError, match="backup_delete_symlink_rejected"):
        gateway.delete_prepared_local_files(bundle)


def test_infra_restore_request_protects_identifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    req = tmp_path / "private" / "backup_restore_requests"
    req.mkdir(parents=True)
    (req / "restore-1.json").write_text(
        json.dumps(
            {
                "source_operation_id": "other",
                "safety_operation_id": "safety-1",
                "target": {"identifier": IDENTIFIER},
                "safety": {"identifier": "other-id"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        delete_mod.frappe,
        "get_site_path",
        lambda *parts: str(tmp_path.joinpath(*parts)) if parts else str(tmp_path),
    )
    monkeypatch.setattr(
        delete_mod.frappe,
        "db",
        SimpleNamespace(
            get_value=lambda *_a, **_k: None,
            exists=lambda *_a, **_k: False,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        delete_mod.frappe,
        "get_all",
        lambda *_a, **_k: [],
        raising=False,
    )
    gateway = delete_mod.FrappeBackupDeleteGateway()
    assert gateway.is_protected_by_active_restore(operation_id="op-x", backup_identifier=IDENTIFIER) is True


def test_infra_never_exposes_sftp_remove() -> None:
    from almdina_erp.almdina_erp.infrastructure.backups import delete_backup as delete_mod

    source = Path(delete_mod.__file__).read_text(encoding="utf-8")
    assert "sftp.remove" not in source.lower()
    assert "SFTPBackupGateway" not in source
    assert ".remove(" not in source
