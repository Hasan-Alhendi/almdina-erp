from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDGE_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "edge_banding_type" / "edge_banding_type.json"
ORDER_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_defaults.js"
LOOKUP = ROOT / "almdina_erp" / "services" / "edge_banding_lookup_service.py"
MASTER_DATA = ROOT / "almdina_erp" / "services" / "master_data_service.py"

RETIRED_FIELDS = {"edge_color", "finish_type", "application_method"}


def test_edge_banding_master_contains_only_operational_and_pricing_attributes() -> None:
    metadata = json.loads(EDGE_DOCTYPE.read_text(encoding="utf-8"))
    fieldnames = {field["fieldname"] for field in metadata["fields"]}

    assert RETIRED_FIELDS.isdisjoint(fieldnames)
    assert RETIRED_FIELDS.isdisjoint(metadata["field_order"])
    for required in ("edge_type_name", "width_cm", "thickness_mm", "rate_usd_per_meter", "disabled"):
        assert required in fieldnames


def test_order_keeps_required_manual_edge_color() -> None:
    metadata = json.loads(ORDER_DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in metadata["fields"]}
    edge_color = fields["edge_color"]

    assert edge_color["fieldtype"] == "Data"
    assert edge_color["reqd"] == 1
    assert "manually" in edge_color["description"].lower()

    defaults = DEFAULTS.read_text(encoding="utf-8")
    assert "أدخل لون القشاط يدويًا لهذا الطلب." in defaults
    assert "apply_edge_color_default" not in defaults
    assert 'frm.set_value("edge_color"' not in defaults


def test_order_lookup_no_longer_fetches_retired_master_attributes() -> None:
    source = LOOKUP.read_text(encoding="utf-8")
    operational = source.split("_OPERATIONAL_FIELDS = (", 1)[1].split(")", 1)[0]
    serializer = source.split("def _serialize_row", 1)[1].split("def _piece", 1)[0]

    for fieldname in RETIRED_FIELDS:
        assert fieldname not in operational
        assert fieldname not in serializer


def test_master_console_no_longer_queries_retired_edge_attributes() -> None:
    source = MASTER_DATA.read_text(encoding="utf-8")
    edge_rows = source.split("def _edge_rows", 1)[1].split("def _audit_rows", 1)[0]

    for fieldname in RETIRED_FIELDS:
        assert fieldname not in edge_rows
