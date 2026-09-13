from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting.offcut_policy import OffcutPolicyError
from almdina_erp.almdina_erp.domain.cutting.physical_execution_contract import (
    PHYSICAL_EXECUTION_CONTRACT,
    PHYSICAL_EXECUTION_CONTRACT_VERSION,
    is_legacy_physical_execution_snapshot,
    physical_execution_for_snapshot,
    with_physical_execution_contract,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    backfill_piece_instance_ids,
)


def _piece(identity: str = "piece:a:1") -> dict[str, object]:
    return {
        "piece_instance_id": identity,
        "resource_kind": "FULL_BOARD",
        "offcut_source_party": "UNASSIGNED",
        "offcut_execution_party": "UNASSIGNED",
        "source_piece_no": 1,
    }


def test_identity_free_historical_snapshot_is_legacy_and_is_not_mutated() -> None:
    snapshot = {"sheets": [{"pieces": [{"id": 1, "label": "1.1"}]}]}
    original = deepcopy(snapshot)

    assert is_legacy_physical_execution_snapshot(snapshot) is True
    assert physical_execution_for_snapshot(snapshot) is None
    assert snapshot == original


def test_new_snapshot_contract_requires_every_identity_and_rejects_duplicates() -> None:
    missing = with_physical_execution_contract({"sheets": [{"pieces": [{"id": 1}]}]})
    with pytest.raises(OffcutPolicyError, match="piece_instance_id_required"):
        physical_execution_for_snapshot(missing)

    duplicate = with_physical_execution_contract({"sheets": [{"pieces": [_piece(), _piece()]}]})
    with pytest.raises(OffcutPolicyError, match="duplicate_piece_instance_id"):
        physical_execution_for_snapshot(duplicate)


def test_pre_contract_mixed_id_snapshot_is_not_silently_treated_as_legacy() -> None:
    snapshot = {"sheets": [{"pieces": [_piece(), {"id": 2}]}]}
    assert is_legacy_physical_execution_snapshot(snapshot) is False
    with pytest.raises(OffcutPolicyError, match="piece_instance_id_required"):
        physical_execution_for_snapshot(snapshot)


def test_lazy_backfill_preserves_existing_ids_and_persists_only_missing_rows(monkeypatch) -> None:
    writes: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        "frappe.db.set_value",
        lambda doctype, name, field, value, **_kwargs: writes.append((doctype, name, field, value)),
    )
    monkeypatch.setattr("frappe.db.sql", lambda *_args, **_kwargs: None)
    existing = SimpleNamespace(name="ROW-1", piece_instance_id="piece:stable")
    missing = SimpleNamespace(name="ROW-2", piece_instance_id="")
    order = SimpleNamespace(pieces=[existing, missing])

    assert backfill_piece_instance_ids(order) is True
    assert existing.piece_instance_id == "piece:stable"
    assert missing.piece_instance_id.startswith("piece:")
    assert writes == [("Door Cutting Order Detail", "ROW-2", "piece_instance_id", missing.piece_instance_id)]
    assert backfill_piece_instance_ids(order) is False


def test_new_marker_is_explicit_and_does_not_mutate_the_input_mapping() -> None:
    raw = {"sheets": [{"pieces": [_piece()]}]}
    marked = with_physical_execution_contract(raw)
    assert raw.get(PHYSICAL_EXECUTION_CONTRACT) is None
    assert marked[PHYSICAL_EXECUTION_CONTRACT] == PHYSICAL_EXECUTION_CONTRACT_VERSION
    assert physical_execution_for_snapshot(marked).piece_instance_ids == ("piece:a:1",)
