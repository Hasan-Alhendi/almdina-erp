from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UX_PATH = ROOT / "public" / "js" / "production_routing_ux.js"
SCHEMA_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "production_routing_stage"
    / "production_routing_stage.json"
)


def test_every_route_row_is_visible_and_requires_roles() -> None:
    source = UX_PATH.read_text(encoding="utf-8")
    assert '.filter(row => Number(row.required || 0))' not in source
    assert 'reqd: 1' in source
    assert 'row => !rowRoles(row).length' in source
    assert 'حدد الأدوار المؤهلة لجميع مراحل المسار' in source
    assert 'required(frm, cdt, cdn)' not in source


def test_new_rows_normalize_hidden_execution_flags() -> None:
    source = UX_PATH.read_text(encoding="utf-8")
    assert '"required", 1' in source
    assert '"auto_complete_if_not_applicable", 0' in source

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in schema["fields"]}
    assert fields["required"]["hidden"] == 1
    assert fields["required"]["read_only"] == 1
    assert fields["required"]["default"] == "1"
    assert fields["auto_complete_if_not_applicable"]["hidden"] == 1
    assert fields["auto_complete_if_not_applicable"]["read_only"] == 1
    assert fields["auto_complete_if_not_applicable"]["default"] == "0"
