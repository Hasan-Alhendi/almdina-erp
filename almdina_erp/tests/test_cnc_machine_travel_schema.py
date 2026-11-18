"""CNC machine bed stays a sheet surface, without cutter-travel extension fields."""

from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
META = APP_ROOT / "almdina_erp" / "doctype" / "cnc_machine" / "cnc_machine.json"
PATCH = APP_ROOT / "patches" / "v1_0" / "drop_cnc_machine_travel_extensions.py"
PATCHES = APP_ROOT / "patches.txt"
REPOSITORY = (
    APP_ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "cnc_operational_file_repository.py"
)
SERVICE = APP_ROOT / "almdina_erp" / "services" / "cnc_operational_file_service.py"
TRANSLATIONS = APP_ROOT / "translations" / "ar.csv"
PLACEMENT = APP_ROOT / "almdina_erp" / "domain" / "cnc" / "placement.py"
POST = APP_ROOT / "almdina_erp" / "domain" / "cnc" / "post_processors.py"

REMOVED_FIELDS = (
    "cutter_travel_left_extension_mm",
    "cutter_travel_right_extension_mm",
    "cutter_travel_bottom_extension_mm",
    "cutter_travel_top_extension_mm",
    "cutter_travel_extensions_section",
    "cutter_travel_extensions_column",
)


def test_cnc_machine_bed_has_no_cutter_travel_extension_fields():
    metadata = json.loads(META.read_text(encoding="utf-8"))
    fieldnames = [row["fieldname"] for row in metadata["fields"]]
    assert fieldnames == [
        "machine_name",
        "width_cm",
        "length_cm",
        "work_zero_position",
        "left_stop_cm",
        "right_stop_cm",
        "bottom_stop_cm",
        "top_stop_cm",
        "post_processor",
        "enabled",
    ]
    assert metadata["field_order"] == fieldnames
    assert metadata["quick_entry"] == 1
    fields = {row["fieldname"]: row for row in metadata["fields"]}
    assert fields["post_processor"]["fieldtype"] == "Select"
    assert fields["post_processor"]["reqd"] == 1
    assert fields["post_processor"]["options"] == "ima_wh_ncstudio"
    assert fields["post_processor"]["default"] == "ima_wh_ncstudio"
    assert "Section Break" not in {row["fieldtype"] for row in metadata["fields"]}
    assert fields["work_zero_position"]["fieldtype"] == "Select"
    assert fields["work_zero_position"]["options"] == "Bottom Left\nBottom Right\nTop Left\nTop Right"
    assert "Center" not in fields["work_zero_position"]["options"]
    assert fields["work_zero_position"]["reqd"] == 1
    for fieldname in ("left_stop_cm", "right_stop_cm", "bottom_stop_cm", "top_stop_cm"):
        assert fields[fieldname]["fieldtype"] == "Float"
        assert fields[fieldname].get("reqd", 0) == 0
        assert "default" not in fields[fieldname]
        assert fields[fieldname]["allow_in_quick_entry"] == 1
    assert all(row.get("fieldtype") not in {"Section Break", "Column Break"} for row in metadata["fields"])
    assert fields["width_cm"]["label"] == "Machine Width (cm)"
    assert "machine bed" in fields["width_cm"]["description"].lower()
    assert fields["length_cm"]["label"] == "Machine Length (cm)"
    assert "machine bed" in fields["length_cm"]["description"].lower()
    for fieldname in REMOVED_FIELDS:
        assert fieldname not in fieldnames
        assert fieldname not in metadata["field_order"]


def test_travel_extension_columns_are_dropped_idempotently_and_not_backfilled():
    source = PATCH.read_text(encoding="utf-8")
    patches = PATCHES.read_text(encoding="utf-8")
    assert patches.count("drop_cnc_machine_travel_extensions") == 1
    assert "backfill_cnc_machine_travel_extensions" not in patches
    assert "has_column" in source
    assert "drop column" in source
    assert "width_cm" not in source
    assert "length_cm" not in source
    assert "CNC Operational File" not in source
    for fieldname in REMOVED_FIELDS[:4]:
        assert source.count(fieldname) == 1


def test_machine_repository_and_catalog_do_not_ask_for_travel_extensions():
    repository = REPOSITORY.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    translations = TRANSLATIONS.read_text(encoding="utf-8")
    placement = PLACEMENT.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    for fieldname in REMOVED_FIELDS:
        assert fieldname not in repository
        assert fieldname not in service
        assert fieldname not in placement
        assert fieldname not in post
    for key in (
        "Cutter Travel Extensions",
        "Left Extension (mm)",
        "Right Extension (mm)",
        "Bottom Extension (mm)",
        "Top Extension (mm)",
        "The dashed line shows the configured cutter travel bounds.",
    ):
        assert key not in translations
    assert "cutter_travel_x_min_mm" not in post
    assert "profile_home_outside_machine" not in post
    assert "machine_parking_outside_limits" in post
    assert "home_move_unsafe" in post
    corner_patch = (APP_ROOT / "patches" / "v1_0" / "configure_cnc_machine_corner_stops.py").read_text(encoding="utf-8")
    assert "right_stop_cm = left_stop_cm" not in corner_patch
    assert "top_stop_cm = bottom_stop_cm" not in corner_patch
    assert "frappe.db.set_value" not in corner_patch
    assert PATCHES.read_text(encoding="utf-8").count("configure_cnc_machine_corner_stops") == 1
