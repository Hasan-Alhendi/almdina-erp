from __future__ import annotations

import csv
import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = APP_ROOT / "translations" / "ar.csv"


def _arabic_mapping() -> dict[str, str]:
    with TRANSLATIONS.open(encoding="utf-8", newline="") as handle:
        return {
            row[0].strip(): row[1].strip()
            for row in csv.reader(handle)
            if len(row) >= 2 and row[0].strip() and row[1].strip()
        }


def _contains_arabic(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in value)


def test_core_factory_operator_terms_have_meaningful_arabic_labels():
    mapping = _arabic_mapping()
    required = {
        "Almdina ERP": "إدارة المعمل",
        "Factory Operations": "التشغيل اليومي للمعمل",
        "Door Cutting Orders": "طلبات قص الدرف",
        "Production Stages": "مراحل تنفيذ الطلبات",
        "Board Remnants": "بقايا الألواح",
        "Replacement Pieces": "القطع التعويضية",
        "Material Reservations": "المواد المحجوزة للطلبات",
        "Production Incidents": "أخطاء ومشاكل الإنتاج",
        "Factory Settings": "إعدادات المعمل",
        "Stock & Control": "المواد والمخزون والمتابعة",
        "Factory Order Analysis": "تحليل طلبات القص",
        "Production Stage Performance": "أداء مراحل الإنتاج",
        "Remnant Inventory": "مخزون بقايا الألواح",
        "Order Stock Availability": "توفر مواد الطلبات",
        "Factory Approval Queue": "طلبات بانتظار الاعتماد",
        "Factory System Preflight": "فحص جاهزية إعدادات المعمل",
    }
    for source, expected in required.items():
        assert mapping.get(source) == expected, source


def test_factory_workflow_values_are_translated_for_non_english_operators():
    mapping = _arabic_mapping()
    values = [
        "Draft",
        "Pending Review",
        "Approved",
        "Cutting In Progress",
        "Cut Completed",
        "Edge Banding In Progress",
        "Quality Check",
        "Completed",
        "Rejected",
        "Cancelled",
        "Available",
        "Reserved",
        "Consumed",
        "Pending Approval",
        "In Progress",
        "Paused",
        "Measurement Error",
        "Cutting Error",
        "Edge Banding Error",
        "Damage",
        "Lost Piece",
        "Material Defect",
        "Review / Preparation",
        "Cutting",
        "Edge Banding",
    ]
    missing = [value for value in values if not _contains_arabic(mapping.get(value, ""))]
    assert not missing, f"Missing Arabic workflow values: {missing}"


def test_all_packing_modes_have_arabic_operator_labels():
    mapping = _arabic_mapping()
    modes = [
        "Auto",
        "MaxRects Best Short Side",
        "MaxRects Best Area",
        "MaxRects Bottom Left",
        "MaxRects Contact Point",
        "MaxRects Width",
        "MaxRects Length",
        "Shelf Horizontal",
        "Shelf Vertical",
        "Shelf First Fit",
        "Shelf Next Fit",
        "Guillotine Short Axis",
        "Guillotine Long Axis",
        "Guillotine Best Area Fit",
        "Guillotine Best Short Side Fit",
        "Guillotine Best Long Side Fit",
        "Skyline Bottom Left",
        "Skyline Best Fit",
    ]
    missing = [mode for mode in modes if not _contains_arabic(mapping.get(mode, ""))]
    assert not missing, f"Missing Arabic packing modes: {missing}"


def test_legacy_frozen_method_labels_have_arabic_display_fallbacks():
    js = (APP_ROOT / "public" / "js" / "arabic_operator_ui.js").read_text(encoding="utf-8")
    legacy_labels = [
        "MaxRects - Best Short Side",
        "MaxRects - Best Area",
        "MaxRects - Bottom Left",
        "MaxRects - Contact Point",
        "MaxRects - الأعرض أولاً",
        "MaxRects - الأطول أولاً",
        "Shelf Packing - صفوف أفقية",
        "Shelf Packing - أعمدة عمودية",
        "Shelf Packing - First Fit",
        "Shelf Packing - Next Fit",
        "Guillotine - Short Axis Split",
        "Guillotine - Long Axis Split",
        "Guillotine - Best Area Fit",
        "Guillotine - Best Short Side Fit",
        "Guillotine - Best Long Side Fit",
        "Skyline - Bottom Left",
        "Skyline - Best Fit",
        "Auto اختار: ",
        "Remnant First + ",
        "No full board required",
    ]
    missing = [label for label in legacy_labels if label not in js]
    assert not missing, f"Missing legacy display fallbacks: {missing}"


def test_factory_print_formats_are_arabic_first():
    paths = [
        APP_ROOT / "almdina_erp" / "print_format" / "door_cutting_measurements" / "door_cutting_measurements.json",
        APP_ROOT / "almdina_erp" / "print_format" / "door_cutting_plan_production_a4" / "door_cutting_plan_production_a4.json",
        APP_ROOT / "almdina_erp" / "print_format" / "door_cutting_plan_official" / "door_cutting_plan_official.json",
    ]
    forbidden_visible_phrases = [
        "Measurements Table",
        "Production Cutting Plan A4",
        "Official Cutting Plan",
        "Full Size MM",
        "Usable Size MM",
        "Edge Sides",
        "Long Right",
        "Long Left",
        "Width Top",
        "Width Bottom",
    ]
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        html = payload.get("html", "")
        assert _contains_arabic(html), path
        leaked = [phrase for phrase in forbidden_visible_phrases if phrase in html]
        assert not leaked, f"English operator text leaked in {path.name}: {leaked}"
