"""CNC machine bed/travel schema and safe legacy initialization."""

from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
META = APP_ROOT / "almdina_erp" / "doctype" / "cnc_machine" / "cnc_machine.json"
PATCH = APP_ROOT / "patches" / "v1_0" / "backfill_cnc_machine_travel_extensions.py"
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


FIELDS = (
    "cutter_travel_left_extension_mm",
    "cutter_travel_right_extension_mm",
    "cutter_travel_bottom_extension_mm",
    "cutter_travel_top_extension_mm",
)


def test_cnc_machine_separates_bed_dimensions_from_mm_travel_extensions():
    metadata = json.loads(META.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in metadata["fields"]}
    assert fields["width_cm"]["label"] == "Machine Width (cm)"
    assert "machine bed" in fields["width_cm"]["description"].lower()
    assert fields["length_cm"]["label"] == "Machine Length (cm)"
    assert "machine bed" in fields["length_cm"]["description"].lower()
    assert fields["cutter_travel_extensions_section"]["label"] == "Cutter Travel Extensions"
    for fieldname in FIELDS:
        field = fields[fieldname]
        assert field["fieldtype"] == "Float"
        assert field["default"] == "0"
        assert field["non_negative"] == 1
        assert field["reqd"] == 1
        assert field["label"].endswith("(mm)")


def test_legacy_extension_backfill_is_registered_and_idempotent():
    source = PATCH.read_text(encoding="utf-8")
    patches = PATCHES.read_text(encoding="utf-8")
    assert patches.count("backfill_cnc_machine_travel_extensions") == 1
    assert "where `{fieldname}` is null" in source
    assert "set `{fieldname}` = 0" in source
    assert "width_cm" not in source
    assert "length_cm" not in source
    assert "CNC Operational File" not in source


def test_machine_repository_and_arabic_catalog_include_all_travel_extensions():
    repository = REPOSITORY.read_text(encoding="utf-8")
    translations = TRANSLATIONS.read_text(encoding="utf-8")
    for fieldname in FIELDS:
        assert repository.count(fieldname) >= 2
    for key in (
        "Cutter Travel Extensions,امتدادات حركة الريشة",
        "Left Extension (mm),الامتداد يسارًا (مم)",
        "Right Extension (mm),الامتداد يمينًا (مم)",
        "Bottom Extension (mm),الامتداد أسفلًا (مم)",
        "Top Extension (mm),الامتداد أعلى (مم)",
        "The dashed line shows the configured cutter travel bounds.",
    ):
        assert key in translations


def test_generation_error_formats_machine_path_axis_bounds_and_overrun():
    source = SERVICE.read_text(encoding="utf-8")
    formatter = source.split("def _failure_message", 1)[1].split("def _issue_message", 1)[0]
    assert 'code == "toolpath_exceeds_machine"' in formatter
    assert 'getattr(cause, "details", {})' in formatter
    for key in (
        "machine_name",
        "path_key",
        "axis",
        "coordinate_mm",
        "minimum_mm",
        "maximum_mm",
        "overrun_mm",
    ):
        assert key in formatter
