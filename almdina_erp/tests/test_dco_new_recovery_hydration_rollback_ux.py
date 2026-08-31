from pathlib import Path


SOURCE = Path(
    "almdina_erp/public/js/door_cutting_order/recovery/presentation/"
    "door_cutting_order_local_checkpoint.js"
)


def source_text() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_failed_new_recovery_hydration_restores_pre_hydration_form_snapshot() -> None:
    source = source_text()

    assert "function captureHydrationSnapshot(frm)" in source
    assert "function restoreHydrationSnapshot(frm, snapshot)" in source
    assert 'pieces: Array.isArray(doc.pieces)' in source
    assert '["recovery_creation_token", "__unsaved"]' in source
    assert "doc.pieces = restoredPieces;" in source
    assert "localRegistry[doctype][name] = row;" in source


def test_hydration_snapshot_is_taken_before_provisional_recovery_state_mutates_form() -> None:
    source = source_text()

    capture = source.index("const hydrationSnapshot = captureHydrationSnapshot(frm);")
    create_state = source.index(
        "const state = createState(frm, { record: selected });",
        capture,
    )
    assert capture < create_state


def test_failed_or_incomplete_hydration_uses_the_same_rollback_snapshot() -> None:
    source = source_text()

    assert source.count(
        "discardFailedHydration(frm, state, hydrationSnapshot);"
    ) >= 2
    assert "if (hydrationSnapshot && restoreHydrationSnapshot(frm, hydrationSnapshot)) return;" in source


def test_rollback_restores_absent_fields_instead_of_leaking_recovered_values() -> None:
    source = source_text()

    assert "else delete doc[fieldname];" in source
    assert 'frm.refresh_fields(root.Projection.HEADER_FIELDS)' in source
    assert 'frm.refresh_field("pieces")' in source
