from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "almdina_erp" / "domain" / "backups" / "policy.py"
APPLICATION = ROOT / "almdina_erp" / "application" / "backups" / "management.py"
FRAPPE_ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "backups" / "frappe_backup.py"
RESTORE_RUNNER = ROOT / "almdina_erp" / "infrastructure" / "backups" / "restore_runner.py"
SERVICE = ROOT / "almdina_erp" / "services" / "backup_restore_service.py"
SETTINGS = ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"
HISTORY = ROOT / "almdina_erp" / "doctype" / "almdina_backup_operation" / "almdina_backup_operation.json"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_domain_and_application_are_framework_free() -> None:
    for path in (DOMAIN, APPLICATION):
        dependencies = imports(path)
        assert not any(value == "frappe" or value.startswith("frappe.") for value in dependencies)
        assert not any("infrastructure" in value or ".services" in value for value in dependencies)


def test_frappe_engine_is_reused_without_custom_dump_or_restore_sql() -> None:
    adapter = FRAPPE_ADAPTER.read_text(encoding="utf-8")
    runner = RESTORE_RUNNER.read_text(encoding="utf-8")
    assert "BackupGenerator" in adapter
    assert "get_backup(ignore_files=False, force=True)" in adapter
    assert '"restore"' in runner
    assert '"migrate"' in runner
    combined = adapter + runner + SERVICE.read_text(encoding="utf-8")
    assert "mysqldump" not in combined
    assert "pg_dump" not in combined
    assert "restore_database(" not in combined
    assert "extract_files(" not in combined


def test_secrets_use_frappe_password_fields_and_history_has_no_credentials() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in settings["fields"]}
    for fieldname in ("ssh_password", "ssh_private_key", "ssh_private_key_passphrase"):
        assert fields[fieldname]["fieldtype"] == "Password"

    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    history_fields = {field["fieldname"] for field in history["fields"]}
    assert not history_fields.intersection({"ssh_password", "ssh_private_key", "credential", "secret"})


def test_restore_endpoint_accepts_operation_id_not_client_path() -> None:
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    request_restore = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "request_restore"
    )
    arguments = [argument.arg for argument in request_restore.args.args]
    assert arguments == ["operation_id", "confirmation"]
