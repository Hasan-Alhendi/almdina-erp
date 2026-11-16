from __future__ import annotations

import time
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.infrastructure.backups import restore_state


def test_claim_is_site_scoped_and_blocks_second_restore(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    restore_state.claim(first, "first.local", "one")
    with pytest.raises(ValueError, match="restore_in_progress"):
        restore_state.claim(first, "first.local", "two")
    restore_state.claim(second, "second.local", "other")
    assert restore_state.public_status(first, "other.local") == {}
    restore_state.advance(first, "one", "COMPLETED")
    restore_state.claim(first, "first.local", "two")


def test_stopped_runner_is_not_reported_as_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    restore_state.claim(tmp_path, "site.local", "one")
    restore_state.advance(tmp_path, "one", "RESTORING", runner_pid=99999999)
    assert restore_state.public_status(tmp_path, "site.local")["phase"] == "MANUAL_INTERVENTION_REQUIRED"
    with pytest.raises(ValueError):
        restore_state.advance(tmp_path, "other", "COMPLETED")


def test_worker_handoff_does_not_mark_the_starting_runner_as_dead(tmp_path: Path) -> None:
    restore_state.claim(tmp_path, "site.local", "one")
    restore_state.advance(tmp_path, "one", "PREFLIGHT", runner_pid=99999999)
    restore_state.advance(tmp_path, "one", "SAFETY_BACKUP", runner_pid=0)
    assert restore_state.public_status(tmp_path, "site.local")["phase"] == "SAFETY_BACKUP"


def test_stale_preparation_requires_intervention(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    restore_state.claim(tmp_path, "site.local", "one")
    future = time.time() + restore_state.QUEUE_STALE_SECONDS + 1
    monkeypatch.setattr(restore_state.time, "time", lambda: future)
    assert restore_state.public_status(tmp_path, "site.local")["phase"] == "MANUAL_INTERVENTION_REQUIRED"


def test_jobs_are_blocked_only_on_the_restoring_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import frappe

    first, second = tmp_path / "first", tmp_path / "second"
    restore_state.claim(first, "first.local", "one")
    monkeypatch.setattr(frappe, "get_site_path", lambda: str(first), raising=False)
    with pytest.raises(RuntimeError, match="paused"):
        restore_state.block_job_during_restore("some.other.job")
    restore_state.block_job_during_restore(
        "almdina_erp.almdina_erp.services.backup_restore_service.prepare_restore_job")
    monkeypatch.setattr(frappe, "get_site_path", lambda: str(second))
    restore_state.block_job_during_restore("some.other.job")
