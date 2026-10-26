from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services import (
    backup_restore_service as service,
    production_settings_service as settings_service,
)


class FakeSettings:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = values or {}
        self.password_reads = 0

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.values.get(fieldname, default)

    def get_password(self, _fieldname: str, raise_exception: bool = False) -> str:
        assert raise_exception is False
        self.password_reads += 1
        return "super-secret"


@pytest.mark.parametrize(
    ("local_enabled", "external_enabled", "expected"),
    [
        (0, 0, []),
        (1, 0, ["local"]),
        (0, 1, ["external"]),
        (1, 1, ["local", "external"]),
    ],
)
def test_scheduler_respects_independent_enabled_flags(
    monkeypatch: pytest.MonkeyPatch,
    local_enabled: int,
    external_enabled: int,
    expected: list[str],
) -> None:
    settings = FakeSettings(
        {
            "local_backup_enabled": local_enabled,
            "external_backup_enabled": external_enabled,
            "local_backup_frequency": "Daily",
            "external_backup_frequency": "Daily",
            "local_backup_time": "02:00",
            "external_backup_time": "02:00",
        }
    )
    created: list[tuple[str, str]] = []
    enqueued: list[str] = []

    class History:
        def exists_for_schedule(self, _schedule_key: str) -> bool:
            return False

        def create(self, **values: Any) -> str:
            created.append((values["target"], values["schedule_key"]))
            return f"op-{values['target'].lower()}"

    monkeypatch.setattr(service, "_settings", lambda: settings)
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 10, 8, 2, 0))
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_enqueue_backup", lambda _operation_id, target: enqueued.append(target))

    service.scheduled_backup_tick()

    assert enqueued == expected
    assert [target.lower() for target, _key in created] == expected


def test_manual_local_backup_runs_when_automatic_local_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class History:
        def get(self, _operation_id: str) -> dict[str, str]:
            return {"status": "Queued", "target": "Local", "operation_type": "Manual"}

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({"local_backup_enabled": 0}))
    monkeypatch.setattr(service, "FrappeBackupEngine", lambda: object())
    monkeypatch.setattr(service, "FrappeLocalRetention", lambda: object())
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))
    monkeypatch.setattr(service, "run_backup", lambda **values: captured.update(values))

    service.run_backup_job("manual-op", "local")

    assert captured["operation_id"] == "manual-op"
    assert captured["target"] == "local"
    assert captured["keep_last"] == 7


@pytest.mark.parametrize("target", ["local", "external"])
def test_disabled_automatic_target_rejects_queued_scheduled_job(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    expected_target = target.title()

    class History:
        def get(self, _operation_id: str) -> dict[str, str]:
            return {"status": "Queued", "target": expected_target, "operation_type": "Scheduled"}

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({f"{target}_backup_enabled": 0}))
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    with pytest.raises(ValueError, match="disabled"):
        service.run_backup_job("scheduled-op", target)


@pytest.mark.parametrize(
    ("endpoint", "required"),
    [
        ("create_backup_now", Capability.MANAGE_BACKUPS),
        ("test_ssh_connection", Capability.MANAGE_BACKUPS),
        ("request_restore", Capability.RESTORE_BACKUPS),
    ],
)
def test_mutating_endpoints_fail_before_work_without_capability(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    required: str,
) -> None:
    checked: list[str] = []

    def deny(capability: str, **_kwargs: Any) -> None:
        checked.append(capability)
        raise PermissionError("denied")

    monkeypatch.setattr(service, "require_doctype_capability", deny)
    monkeypatch.setattr(service, "_", lambda message: message)
    with pytest.raises(PermissionError, match="denied"):
        if endpoint == "request_restore":
            service.request_restore("untrusted-operation", "RESTORE anything")
        else:
            getattr(service, endpoint)()
    assert checked == [required]


def test_settings_response_never_contains_secret_values() -> None:
    settings = FakeSettings(
        {
            "ssh_host": "backup.internal",
            "ssh_username": "backup",
            "whatsapp_measurements_text": "measurements",
            "whatsapp_measurement_amendments_text": "amendments",
            "whatsapp_invoice_text": "invoice",
            "whatsapp_stage_messages": {"Cutting": "done"},
        }
    )

    privileged = settings_service._settings_values(settings, include_backups=True)
    unprivileged = settings_service._settings_values(settings, include_backups=False)

    assert "super-secret" not in json.dumps(privileged)
    assert privileged["ssh_password_configured"] is True
    assert privileged["ssh_private_key_configured"] is True
    assert "ssh_host" not in unprivileged
    assert "ssh_password_configured" not in unprivileged
