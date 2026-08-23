from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRICT = ROOT / "almdina_erp" / "services" / "strict_dxf_import_service.py"
SHOP = ROOT / "almdina_erp" / "services" / "shop_floor_dxf_service.py"
DOMAIN = ROOT / "almdina_erp" / "domain" / "cutting" / "piece_cut_dimensions.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_upload_uses_strict_edge_adjusted_dimension_contract():
    shop = _source(SHOP)
    strict = _source(STRICT)
    assert "services.strict_dxf_import_service" in shop
    assert "build_order_piece_cut_specs" in strict
    assert "_apply_strict_dimension_contract" in strict
    assert '"mode": "exact-edge-adjusted"' in strict
    assert '"finished_dimensions_immutable": True' in strict


def test_piece_contract_is_exact_at_persisted_precision_not_plus_minus_two_mm():
    strict = _source(STRICT)
    domain = _source(DOMAIN)
    assert 'CUT_DIMENSION_QUANTUM_CM = Decimal("0.001")' in domain
    assert "dimensions_match_exact" in strict
    assert "لا توجد سماحية لتغيير مقاس الدرفة" in strict
    assert "DIMENSION_TOLERANCE_MM" not in strict


def test_strict_contract_records_finished_and_raw_cut_dimensions_separately():
    strict = _source(STRICT)
    for token in [
        'piece["finished_w"]',
        'piece["finished_h"]',
        'piece["cut_width_cm"]',
        'piece["cut_length_cm"]',
        'piece["edge_width_deduction_mm"]',
        'piece["edge_length_deduction_mm"]',
    ]:
        assert token in strict
