"""Destructive restore acceptance on an ephemeral CI site only."""
from __future__ import annotations

import json
import os
from pathlib import Path

import frappe

from almdina_erp.almdina_erp.infrastructure.backups import restore_state
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import FrappeBackupEngine
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory
from almdina_erp.almdina_erp.services.backup_restore_service import prepare_restore_job


def _case_path() -> Path:
    return Path(frappe.get_site_path("private", "backup_restore_requests", "ci-restore-check.json"))


def _require_ci_site() -> None:
    if (os.environ.get("CI") != "true" or not frappe.conf.get("allow_tests")
            or frappe.local.site != os.environ.get("ALMADINA_DISPOSABLE_RESTORE_SITE")):
        raise RuntimeError("Destructive restore check is restricted to a test-enabled CI site.")


def begin() -> None:
    _require_ci_site()
    if _case_path().exists():
        raise RuntimeError("Restore check already started on this site.")
    from frappe.utils.password import get_encryption_key

    get_encryption_key()

    note = frappe.get_doc({"doctype": "Note", "title": "Backup restore CI check", "content": "before"})
    note.insert(ignore_permissions=True)
    frappe.db.commit()

    history = FrappeBackupHistory()
    source = FrappeBackupEngine().create()
    source_id = history.create(operation_type="Manual", target="Local", requested_by="Administrator")
    history.mark_completed(source_id, source, source.identifier)
    frappe.db.commit()

    frappe.db.set_value("Note", note.name, "content", "after")
    restore_id = history.create(operation_type="Restore", target="Restore", requested_by="Administrator",
                                source_operation_id=source_id)
    path = _case_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps({"note": note.name, "restore": restore_id}), encoding="utf-8")
    os.chmod(path, 0o600)
    restore_state.claim(Path(frappe.get_site_path()), str(frappe.local.site), restore_id)
    frappe.db.commit()
    prepare_restore_job(restore_id)


def verify() -> None:
    _require_ci_site()
    path = _case_path()
    case = json.loads(path.read_text(encoding="utf-8"))
    state = restore_state.public_status(Path(frappe.get_site_path()), str(frappe.local.site))
    assert state["operation_id"] == case["restore"] and state["phase"] == "COMPLETED", state
    assert frappe.db.get_value("Note", case["note"], "content") == "before"
    row = FrappeBackupHistory().get(case["restore"])
    assert row and row["status"] == "Completed"
    assert not frappe.conf.get("maintenance_mode")
    path.unlink()
