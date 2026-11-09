"""Per-site restore coordination outside the database being replaced."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

TERMINAL = {"COMPLETED", "RECOVERED_AFTER_FAILURE", "MANUAL_INTERVENTION_REQUIRED"}
RECLAIMABLE = {"COMPLETED", "RECOVERED_AFTER_FAILURE"}
PHASES = {"QUEUED", "PREFLIGHT", "SAFETY_BACKUP", "MAINTENANCE", "RESTORING",
          "MIGRATING", "VERIFYING", "RECOVERING", *TERMINAL}
STALE_SECONDS = 15 * 60
QUEUE_STALE_SECONDS = 6 * 60 * 60


def _paths(site_path: Path) -> tuple[Path, Path]:
    folder = site_path / "private" / "backup_restore_requests"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder / "state.json", folder / "state.lock"


@contextmanager
def _locked(site_path: Path) -> Iterator[Path]:
    state_path, lock_path = _paths(site_path)
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield state_path
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Restore status is invalid.")
    return data


def _write(path: Path, value: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".restore-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, separators=(",", ":"), sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read(site_path: Path) -> dict:
    with _locked(site_path) as path:
        return _read(path).copy()


def claim(site_path: Path, site: str, operation_id: str) -> None:
    with _locked(site_path) as path:
        previous = _read(path)
        if previous and previous.get("phase") not in RECLAIMABLE:
            raise ValueError("restore_in_progress")
        _write(path, {"version": 1, "site": site, "operation_id": operation_id,
                      "phase": "QUEUED", "updated_at": time.time()})


def advance(site_path: Path, operation_id: str, phase: str, *, runner_pid: int | None = None) -> None:
    if phase not in PHASES:
        raise ValueError("Unknown restore phase.")
    with _locked(site_path) as path:
        state = _read(path)
        if not state or state.get("operation_id") != operation_id:
            raise ValueError("Restore status belongs to another operation.")
        state.update(phase=phase, updated_at=time.time())
        if runner_pid is not None:
            state["runner_pid"] = runner_pid
        _write(path, state)


def active(site_path: Path) -> bool:
    state = read(site_path)
    return bool(state and state.get("phase") not in RECLAIMABLE)


def public_status(site_path: Path, site: str) -> dict:
    state = read(site_path)
    if not state or state.get("site") != site:
        return {}
    phase = state["phase"]
    # A stopped detached runner must never be presented as still progressing.
    pid = int(state.get("runner_pid") or 0)
    if phase not in TERMINAL and pid:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            phase = "MANUAL_INTERVENTION_REQUIRED"
            advance(site_path, state["operation_id"], phase)
        except PermissionError:
            pass
    elif phase not in TERMINAL and time.time() - float(state.get("updated_at") or 0) > (QUEUE_STALE_SECONDS if phase == "QUEUED" else STALE_SECONDS):
        phase = "MANUAL_INTERVENTION_REQUIRED"
        advance(site_path, state["operation_id"], phase)
    if phase != state["phase"]:
        state = read(site_path)
    return {"operation_id": state["operation_id"], "phase": phase,
            "updated_at": state["updated_at"]}


def block_job_during_restore(method: str, **_kwargs: object) -> None:
    """Frappe's before_job hook is scoped to the job's initialized site."""
    import frappe

    site_path = Path(frappe.get_site_path()).resolve()
    if not active(site_path):
        return
    prepare = "almdina_erp.almdina_erp.services.backup_restore_service.prepare_restore_job"
    if str(method) != prepare:
        raise RuntimeError("Site jobs are paused while a restore is in progress.")
