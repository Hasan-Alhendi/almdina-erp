from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
CONTROLLER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"


def test_packing_score_uses_text_storage_instead_of_140_character_data_field():
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["packing_score"]["fieldtype"] == "Small Text"
    assert fields["packing_score"]["read_only"] == 1


def test_packing_score_keeps_full_optimizer_summary_components():
    source = CONTROLLER.read_text(encoding="utf-8")
    for token in (
        "ألواح:",
        "هدر:",
        "قصات تقديرية:",
        "أكبر بقايا مفيدة:",
        "محاولات:",
        "الخوارزمية:",
    ):
        assert token in source
