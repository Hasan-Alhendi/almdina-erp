from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.backups.export_format import EXPORT_FORMAT, EXPORT_FORMAT_VERSION
from almdina_erp.almdina_erp.domain.backups.import_format import (
    parse_import_manifest_json,
    validate_import_manifest,
)


SITE = "site.local"
SLUG = "site_local"
IDENTIFIER = "20261108_120000-site_local"


def _payload(**overrides):
    components = [
        {
            "name": "database",
            "path": f"{IDENTIFIER}-database.sql.gz",
            "size": 10,
            "sha256": "a" * 64,
            "required": True,
        },
        {
            "name": "public_files",
            "path": f"{IDENTIFIER}-files.tgz",
            "size": 11,
            "sha256": "b" * 64,
            "required": True,
        },
        {
            "name": "private_files",
            "path": f"{IDENTIFIER}-private-files.tgz",
            "size": 12,
            "sha256": "c" * 64,
            "required": True,
        },
        {
            "name": "site_config",
            "path": f"{IDENTIFIER}-site_config_backup.json",
            "size": 13,
            "sha256": "d" * 64,
            "required": True,
        },
    ]
    payload = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "backup_id": IDENTIFIER,
        "operation_id": "source-op",
        "site": SITE,
        "created_at": "2026-11-08 12:00:00",
        "database_type": "mariadb",
        "target": "Local",
        "operation_type": "Manual",
        "components": components,
    }
    payload.update(overrides)
    return payload


def test_validate_import_manifest_accepts_phase2_contract() -> None:
    result = validate_import_manifest(
        _payload(),
        expected_site=SITE,
        expected_database_type="MariaDB",
        site_slug=SLUG,
    )
    assert result["backup_id"] == IDENTIFIER
    assert len(result["components"]) == 4


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"format": "other"}, "backup_import_unsupported_format"),
        ({"format_version": 2}, "backup_import_unsupported_format"),
        ({"site": "other.site"}, "backup_import_site_mismatch"),
        ({"database_type": "postgres"}, "backup_import_database_type_mismatch"),
        ({"components": []}, "backup_import_incomplete_components"),
    ],
)
def test_validate_import_manifest_rejects_invalid_contracts(overrides: dict, code: str) -> None:
    with pytest.raises(ValueError, match=code):
        validate_import_manifest(
            _payload(**overrides),
            expected_site=SITE,
            expected_database_type="mariadb",
            site_slug=SLUG,
        )


def test_parse_import_manifest_json_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="backup_import_invalid_manifest"):
        parse_import_manifest_json("{not-json")
