from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIST_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)


def _source() -> str:
    return LIST_UX.read_text(encoding="utf-8")


def _function_block(source: str, name: str, next_name: str) -> str:
    start = source.index(f"function {name}")
    end = source.index(f"function {next_name}", start)
    return source[start:end]


def test_filter_exposes_intake_delivery_and_cancelled_states() -> None:
    source = _source()
    block = _function_block(source, "statusFilterOptions", "statusFilterConfig")

    assert 'const STATUS_FILTER_ALL_LABEL = "كل الأقسام";' in source
    assert 'const INTAKE_FILTER_DATA_ENTRY = "المسودة / إدخال البيانات";' in source
    assert 'const INTAKE_FILTER_READY_TO_DISPATCH = "جاهز للإرسال";' in source
    assert 'const DELIVERY_FILTER_READY = "جاهز للتسليم";' in source
    assert 'const DELIVERY_FILTER_DELIVERED = "تم التسليم";' in source
    assert 'const CANCELLED_FILTER = "الملغى";' in source

    assert "INTAKE_FILTER_DATA_ENTRY" in block
    assert "INTAKE_FILTER_READY_TO_DISPATCH" in block
    assert "...departmentStageOptions()" in block
    assert "DELIVERY_FILTER_READY" in block
    assert "DELIVERY_FILTER_DELIVERED" in block
    assert "CANCELLED_FILTER" in block


def test_filter_maps_each_non_production_state_to_authoritative_field() -> None:
    source = _source()
    block = _function_block(
        source,
        "departmentColumnQueryFilter",
        "rewriteDepartmentColumnFilters",
    )

    assert '[doctype, "workflow_stage", "=", "DATA_ENTRY"]' in block
    assert '[doctype, "workflow_stage", "=", "READY_TO_DISPATCH"]' in block
    assert '[doctype, "status", "=", "Ready for Delivery"]' in block
    assert '[doctype, "status", "=", "Delivered"]' in block
    assert '[doctype, "status", "=", "Cancelled"]' in block
    assert '[STATUS_FILTER_STAGE_FIELD, "=", resolveDepartmentFilterStageType(selected)]' in block


def test_all_departments_removes_only_the_workflow_filter() -> None:
    source = _source()
    query_block = _function_block(
        source,
        "departmentColumnQueryFilter",
        "rewriteDepartmentColumnFilters",
    )
    rewrite_block = _function_block(
        source,
        "rewriteDepartmentColumnFilters",
        "installCombinedSearch",
    )

    # The blank value behind «كل الأقسام» produces no workflow predicate.
    assert "if (!selected) return null;" in query_block

    # Other native/user filters remain untouched; only the synthetic department
    # filter is removed when its selected value is blank.
    assert "flatMap" in rewrite_block
    assert "if (!isDepartmentFilter(filter, doctype)) return [filter];" in rewrite_block
    assert "return rewritten ? [rewritten] : [];" in rewrite_block
