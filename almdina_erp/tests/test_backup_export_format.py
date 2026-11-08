from __future__ import annotations

import json

import pytest

from almdina_erp.almdina_erp.domain.backups.export_format import (
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    ExportComponent,
    archive_member_name,
    build_export_manifest,
    is_exportable_operation,
    parse_stored_artifact_manifest,
)


def _components() -> list[ExportComponent]:
    return [
        ExportComponent("database", "20261108_120000-site_local-database.sql.gz", 10, "a" * 64),
        ExportComponent("public_files", "20261108_120000-site_local-files.tgz", 11, "b" * 64),
        ExportComponent("private_files", "20261108_120000-site_local-private-files.tgz", 12, "c" * 64),
        ExportComponent("site_config", "20261108_120000-site_local-site_config_backup.json", 13, "d" * 64),
    ]


def test_manifest_json_is_valid_and_versioned() -> None:
    manifest = build_export_manifest(
        backup_id="20261108_120000-site_local",
        operation_id="op-1",
        site="site.local",
        created_at="2026-11-08 12:00:00",
        database_type="MariaDB",
        target="Local",
        operation_type="Manual",
        components=_components(),
    )
    payload = json.loads(manifest.to_json())
    assert payload["format"] == EXPORT_FORMAT
    assert payload["format_version"] == EXPORT_FORMAT_VERSION
    assert payload["database_type"] == "mariadb"
    assert {item["name"] for item in payload["components"]} == {
        "database",
        "public_files",
        "private_files",
        "site_config",
    }
    assert all("/" not in item["path"] and "\\" not in item["path"] for item in payload["components"])
    assert "password" not in manifest.to_json().lower()
    assert "ssh" not in manifest.to_json().lower()


def test_archive_member_name_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        archive_member_name("../etc/passwd")
    with pytest.raises(ValueError):
        archive_member_name("/tmp/evil.sql.gz")
    with pytest.raises(ValueError):
        archive_member_name("..\\windows")
    assert archive_member_name("20261108_120000-site_local-database.sql.gz").endswith(".sql.gz")


@pytest.mark.parametrize(
    ("status", "target", "operation_type", "backup_identifier", "expected"),
    [
        ("Completed", "Local", "Manual", "id-1", True),
        ("Completed", "External", "Scheduled", "id-1", True),
        ("Completed", "Local", "Safety", "id-1", True),
        ("Completed", "Local", "Imported", "id-1", True),
        ("Queued", "Local", "Manual", "id-1", False),
        ("Running", "Local", "Manual", "id-1", False),
        ("Failed", "Local", "Manual", "id-1", False),
        ("Completed", "Restore", "Restore", "id-1", False),
        ("Completed", "Local", "Manual", "", False),
    ],
)
def test_export_eligibility(
    status: str,
    target: str,
    operation_type: str,
    backup_identifier: str,
    expected: bool,
) -> None:
    assert (
        is_exportable_operation(
            status=status,
            target=target,
            operation_type=operation_type,
            backup_identifier=backup_identifier,
        )
        is expected
    )


def test_parse_stored_artifact_manifest_from_legacy_history() -> None:
    raw = json.dumps(
        [
            {
                "kind": "database",
                "filename": "20261108_120000-site_local-database.sql.gz",
                "size": 10,
                "checksum": "A" * 64,
            },
            {
                "kind": "public_files",
                "filename": "20261108_120000-site_local-files.tgz",
                "size": 11,
                "checksum": "b" * 64,
            },
            {
                "kind": "private_files",
                "filename": "20261108_120000-site_local-private-files.tgz",
                "size": 12,
                "checksum": "c" * 64,
            },
            {
                "kind": "site_config",
                "filename": "20261108_120000-site_local-site_config_backup.json",
                "size": 13,
                "checksum": "d" * 64,
            },
        ]
    )
    components = parse_stored_artifact_manifest(raw)
    assert components[0]["sha256"] == "a" * 64
    assert components[0]["path"] == "20261108_120000-site_local-database.sql.gz"


def test_incomplete_components_rejected() -> None:
    with pytest.raises(ValueError):
        build_export_manifest(
            backup_id="20261108_120000-site_local",
            operation_id="op-1",
            site="site.local",
            created_at="2026-11-08 12:00:00",
            database_type="mariadb",
            target="Local",
            operation_type="Manual",
            components=_components()[:3],
        )
