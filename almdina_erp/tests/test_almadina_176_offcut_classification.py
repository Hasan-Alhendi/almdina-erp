from __future__ import annotations

import json
from types import SimpleNamespace

import frappe
import pytest

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services import offcut_service
from almdina_erp.almdina_erp.services import cutting_plan_command_service


@pytest.fixture(autouse=True)
def _stub_plan_row_lock(monkeypatch):
    monkeypatch.setattr(offcut_service.frappe.db, "sql", lambda *_args, **_kwargs: [])


def _piece(identity: str, kind: str = "OFFCUT", **values):
    return SimpleNamespace(
        name=f"ROW-{identity}",
        piece_instance_id=identity,
        resource_kind=kind,
        offcut_source_party=values.get("source", "UNASSIGNED"),
        offcut_execution_party=values.get("execution", "UNASSIGNED"),
        sheet_no=values.get("sheet_no", 3),
        x_mm=values.get("x_mm", 10),
        y_mm=values.get("y_mm", 20),
        width_mm=values.get("width_mm", 700),
        height_mm=values.get("height_mm", 800),
    )


def _snapshot(*pieces):
    return {
        "sheets": [{
            "sheet_no": 3,
            "resource_kind": "OFFCUT",
            "offcut_source_party": "UNASSIGNED",
            "offcut_execution_party": "UNASSIGNED",
            "pieces": [
                {
                    "piece_instance_id": piece.piece_instance_id,
                    "resource_kind": piece.resource_kind,
                    "offcut_source_party": piece.offcut_source_party,
                    "offcut_execution_party": piece.offcut_execution_party,
                    "x": piece.x_mm / 10,
                    "y": piece.y_mm / 10,
                    "w": piece.width_mm / 10,
                    "h": piece.height_mm / 10,
                }
                for piece in pieces
            ],
        }]
    }


def _plan(*pieces, status="Draft"):
    snapshot = _snapshot(*pieces)
    return SimpleNamespace(
        name="CP-176",
        plan_kind="Order",
        door_cutting_order="DCO-176",
        source_type="Uploaded DXF",
        status=status,
        plan_needs_recalculation=0,
        required_boards=0,
        offcut_price_usd=17,
        approved_by="designer@example.com",
        approved_on="2026-09-12 09:00:00",
        snapshot_json=frappe.as_json(snapshot),
        placed_pieces=list(pieces),
        sources=[SimpleNamespace(name="SOURCE-3", sheet_no=3)],
    )


def test_spoofed_resource_kind_is_rejected_before_any_write(monkeypatch):
    full_board = _piece("row:1", "FULL_BOARD")
    plan = _plan(full_board)
    writes = []
    monkeypatch.setattr(
        offcut_service,
        "_current_classifiable_plan",
        lambda *_args: (plan, SimpleNamespace(name="DCO-176")),
    )
    monkeypatch.setattr(offcut_service.frappe.db, "set_value", lambda *args, **kwargs: writes.append(args))

    with pytest.raises(frappe.ValidationError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [{
                "piece_instance_id": full_board.piece_instance_id,
                "resource_kind": "OFFCUT",
                "business_state": "CUSTOMER_FACTORY",
            }],
        )

    assert writes == []


def test_full_board_identity_cannot_be_classified_even_without_spoof(monkeypatch):
    full_board = _piece("row:1", "FULL_BOARD")
    plan = _plan(full_board)
    writes = []
    monkeypatch.setattr(
        offcut_service,
        "_current_classifiable_plan",
        lambda *_args: (plan, SimpleNamespace(name="DCO-176")),
    )
    monkeypatch.setattr(offcut_service.frappe.db, "set_value", lambda *args, **kwargs: writes.append(args))

    with pytest.raises(frappe.ValidationError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [{"piece_instance_id": "row:1", "business_state": "CUSTOMER_FACTORY"}],
        )

    assert writes == []


def test_duplicate_piece_assignment_is_rejected_atomically(monkeypatch):
    piece = _piece("row:3")
    plan = _plan(piece)
    writes = []
    monkeypatch.setattr(
        offcut_service,
        "_current_classifiable_plan",
        lambda *_args: (plan, SimpleNamespace(name="DCO-176")),
    )
    monkeypatch.setattr(offcut_service.frappe.db, "set_value", lambda *args, **kwargs: writes.append(args))

    with pytest.raises(frappe.ValidationError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [
                {"piece_instance_id": "row:3", "business_state": "CUSTOMER_FACTORY"},
                {"piece_instance_id": "row:3", "business_state": "FACTORY_FACTORY"},
            ],
        )

    assert writes == []


def test_mixed_source_is_rejected_before_any_write(monkeypatch):
    offcut = _piece("row:1", "OFFCUT")
    full_board = _piece("row:2", "FULL_BOARD")
    plan = _plan(offcut, full_board)
    writes = []
    monkeypatch.setattr(
        offcut_service,
        "_current_classifiable_plan",
        lambda *_args: (plan, SimpleNamespace(name="DCO-176")),
    )
    monkeypatch.setattr(
        offcut_service.frappe.db,
        "set_value",
        lambda *args, **kwargs: writes.append(args),
    )

    with pytest.raises(frappe.ValidationError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [{"piece_instance_id": "row:1", "business_state": "CUSTOMER_FACTORY"}],
        )

    assert writes == []


def test_classification_after_approval_changes_only_business_fields(monkeypatch):
    copy_3 = _piece("row:3", x_mm=33, y_mm=44)
    copy_5 = _piece("row:5", x_mm=55, y_mm=66)
    plan = _plan(copy_3, copy_5, status="Approved")
    original = {
        "status": plan.status,
        "approved_by": plan.approved_by,
        "approved_on": plan.approved_on,
        "required_boards": plan.required_boards,
        "offcut_price_usd": plan.offcut_price_usd,
        "geometry": [(piece.x_mm, piece.y_mm, piece.width_mm, piece.height_mm) for piece in plan.placed_pieces],
        "quantity": len(plan.placed_pieces),
    }
    writes = []
    written_snapshots = []
    monkeypatch.setattr(
        offcut_service,
        "_current_classifiable_plan",
        lambda *_args: (plan, SimpleNamespace(name="DCO-176", approved_plan=plan.name)),
    )

    def record_write(doctype, name, field, *args, **_kwargs):
        writes.append((doctype, name, field))
        if doctype == "Cutting Plan" and field == "snapshot_json":
            written_snapshots.append(frappe.parse_json(args[0]))

    monkeypatch.setattr(offcut_service.frappe.db, "set_value", record_write)

    result = offcut_service.set_offcut_execution_owner(
        plan.name,
        [
            {"piece_instance_id": "row:3", "business_state": "CUSTOMER_FACTORY"},
            {"piece_instance_id": "row:5", "business_state": "FACTORY_FACTORY"},
        ],
    )

    assert result["status"] == "Approved"
    assert result["approved_by"] == original["approved_by"]
    assert result["approved_on"] == original["approved_on"]
    assert plan.status == original["status"]
    assert plan.required_boards == original["required_boards"]
    assert plan.offcut_price_usd == original["offcut_price_usd"]
    assert len(plan.placed_pieces) == original["quantity"]
    assert [(piece.x_mm, piece.y_mm, piece.width_mm, piece.height_mm) for piece in plan.placed_pieces] == original["geometry"]
    assert all("resource_kind" not in field for _doctype, _name, field in writes if isinstance(field, dict))
    assert not any(field == "required_boards" for _doctype, _name, field in writes)
    assert not any(field == "offcut_price_usd" for _doctype, _name, field in writes)
    persisted_pieces = written_snapshots[0]["sheets"][0]["pieces"]
    assert [piece["resource_kind"] for piece in persisted_pieces] == ["OFFCUT", "OFFCUT"]
    assert [(piece["x"], piece["y"], piece["w"], piece["h"]) for piece in persisted_pieces] == [
        (3.3, 4.4, 70.0, 80.0),
        (5.5, 6.6, 70.0, 80.0),
    ]


def test_only_offcut_copies_three_and_five_receive_independent_states(monkeypatch):
    pieces = [
        _piece(f"row:{copy_no}", "OFFCUT" if copy_no in {3, 5} else "FULL_BOARD")
        for copy_no in range(1, 6)
    ]
    snapshot = {
        "sheets": [
            {
                "sheet_no": copy_no,
                "resource_kind": piece.resource_kind,
                "pieces": [{
                    "piece_instance_id": piece.piece_instance_id,
                    "resource_kind": piece.resource_kind,
                    "offcut_source_party": "UNASSIGNED",
                    "offcut_execution_party": "UNASSIGNED",
                }],
            }
            for copy_no, piece in enumerate(pieces, start=1)
        ]
    }
    for copy_no, piece in enumerate(pieces, start=1):
        piece.sheet_no = copy_no
    plan = _plan(*pieces)
    plan.snapshot_json = frappe.as_json(snapshot)
    plan.sources = [
        SimpleNamespace(name=f"SOURCE-{copy_no}", sheet_no=copy_no)
        for copy_no in range(1, 6)
    ]
    writes = []
    monkeypatch.setattr(
        offcut_service,
        "_current_classifiable_plan",
        lambda *_args: (plan, SimpleNamespace(name="DCO-176")),
    )
    monkeypatch.setattr(
        offcut_service.frappe.db,
        "set_value",
        lambda doctype, name, field, *args, **kwargs: writes.append((doctype, name, field)),
    )

    result = offcut_service.set_offcut_execution_owner(
        plan.name,
        [
            {"piece_instance_id": "row:3", "business_state": "CUSTOMER_CUSTOMER"},
            {"piece_instance_id": "row:5", "business_state": "FACTORY_FACTORY"},
        ],
    )

    assert [row["piece_instance_id"] for row in result["assignments"]] == ["row:3", "row:5"]
    piece_writes = [name for doctype, name, _field in writes if doctype == "Cutting Plan Piece"]
    assert piece_writes == ["ROW-row:3", "ROW-row:5"]
    assert len(plan.placed_pieces) == 5


def test_unauthorized_user_is_rejected_by_dedicated_capability(monkeypatch):
    piece = _piece("row:3")
    plan = _plan(piece)
    order = SimpleNamespace(name="DCO-176", approved_plan="")
    monkeypatch.setattr(
        offcut_service.frappe,
        "get_doc",
        lambda doctype, _name: plan if doctype == "Cutting Plan" else order,
    )

    def reject(_order, capability, **_kwargs):
        assert capability == Capability.SET_OFFCUT_EXECUTION_OWNER
        raise frappe.PermissionError

    monkeypatch.setattr(offcut_service, "require_cutting_plan_capability", reject)

    with pytest.raises(frappe.PermissionError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [{"piece_instance_id": "row:3", "business_state": "UNASSIGNED"}],
        )


def test_current_draft_accepts_dedicated_capability_without_other_plan_permissions(monkeypatch):
    piece = _piece("row:3")
    plan = _plan(piece)
    order = SimpleNamespace(name="DCO-176", approved_plan="")
    checked = []
    monkeypatch.setattr(
        offcut_service.frappe,
        "get_doc",
        lambda doctype, _name: plan if doctype == "Cutting Plan" else order,
    )
    monkeypatch.setattr(
        offcut_service,
        "require_cutting_plan_capability",
        lambda _order, capability, **_kwargs: checked.append(capability),
    )
    monkeypatch.setattr(offcut_service, "latest_plan", lambda *_args, **_kwargs: plan)

    resolved, resolved_order = offcut_service._current_classifiable_plan(
        plan.name,
        Capability.SET_OFFCUT_EXECUTION_OWNER,
    )

    assert resolved is plan
    assert resolved_order is order
    assert checked == [Capability.SET_OFFCUT_EXECUTION_OWNER]
    assert Capability.SET_OFFCUT_EXECUTION_OWNER not in {
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
        Capability.EDIT_ORDER,
    }


def test_current_approved_plan_is_classifiable_without_reapproval(monkeypatch):
    plan = _plan(_piece("row:3"), status="Approved")
    order = SimpleNamespace(name="DCO-176", approved_plan=plan.name)
    checked = []
    monkeypatch.setattr(
        offcut_service.frappe,
        "get_doc",
        lambda doctype, _name: plan if doctype == "Cutting Plan" else order,
    )
    monkeypatch.setattr(
        offcut_service,
        "require_cutting_plan_capability",
        lambda _order, capability, **_kwargs: checked.append(capability),
    )
    monkeypatch.setattr(
        offcut_service,
        "latest_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Approved classification must not resolve a Draft")
        ),
    )

    resolved, _ = offcut_service._current_classifiable_plan(
        plan.name,
        Capability.SET_OFFCUT_EXECUTION_OWNER,
    )

    assert resolved is plan
    assert checked == [Capability.SET_OFFCUT_EXECUTION_OWNER]


def test_stale_or_non_current_draft_is_rejected(monkeypatch):
    piece = _piece("row:3")
    plan = _plan(piece)
    plan.plan_needs_recalculation = 1
    order = SimpleNamespace(name="DCO-176", approved_plan="")
    monkeypatch.setattr(
        offcut_service.frappe,
        "get_doc",
        lambda doctype, _name: plan if doctype == "Cutting Plan" else order,
    )
    monkeypatch.setattr(offcut_service, "require_cutting_plan_capability", lambda *_args, **_kwargs: None)

    with pytest.raises(frappe.ValidationError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [{"piece_instance_id": "row:3", "business_state": "UNASSIGNED"}],
        )


def test_historical_draft_revision_is_rejected(monkeypatch):
    piece = _piece("row:3")
    plan = _plan(piece)
    order = SimpleNamespace(name="DCO-176", approved_plan="")
    monkeypatch.setattr(
        offcut_service.frappe,
        "get_doc",
        lambda doctype, _name: plan if doctype == "Cutting Plan" else order,
    )
    monkeypatch.setattr(offcut_service, "require_cutting_plan_capability", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        offcut_service,
        "latest_plan",
        lambda *_args, **_kwargs: SimpleNamespace(name="CP-NEWER"),
    )

    with pytest.raises(frappe.ValidationError):
        offcut_service.set_offcut_execution_owner(
            plan.name,
            [{"piece_instance_id": "row:3", "business_state": "UNASSIGNED"}],
        )


def test_unassigned_offcut_does_not_block_existing_approval_rules(monkeypatch):
    snapshot = _snapshot(_piece("row:3"))
    plan = SimpleNamespace(
        status="Draft",
        validation_status="Valid",
        snapshot_json=frappe.as_json(snapshot),
        plan_needs_recalculation=0,
        cost_snapshot_version=999,
        input_fingerprint="same-fingerprint",
        source_type="System",
    )
    order = SimpleNamespace(name="DCO-176")
    monkeypatch.setattr(
        cutting_plan_command_service,
        "plan_input_fingerprint",
        lambda *_args: "same-fingerprint",
    )

    cutting_plan_command_service._assert_plan_ready_for_approval(order, plan)


def test_dxf_replacement_preserves_classification_only_by_exact_identity(monkeypatch):
    existing = _piece(
        "row:3",
        source="CUSTOMER",
        execution="FACTORY",
    )
    plan = _plan(existing)
    incoming = {
        "sheets": [{
            "sheet_no": 3,
            "resource_kind": "OFFCUT",
            "pieces": [
                {"piece_instance_id": "row:3", "resource_kind": "OFFCUT"},
                {"piece_instance_id": "row:new", "resource_kind": "OFFCUT"},
            ],
        }]
    }
    captured = {}

    class Repository:
        def __init__(self, capability):
            assert capability == Capability.REPLACE_DXF

        def ensure_uploaded_dxf_draft(self, _order):
            return plan

        def save_document(self, saved):
            return saved

    monkeypatch.setattr(cutting_plan_command_service, "require_cutting_plan_capability", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cutting_plan_command_service, "FrappeCuttingPlanCommandRepository", Repository)
    monkeypatch.setattr(cutting_plan_command_service, "initialize_draft_plan_cost_snapshot", lambda *_args: False)
    monkeypatch.setattr(
        cutting_plan_command_service,
        "apply_validated_dxf_snapshot",
        lambda _order, _plan, snapshot: captured.update(snapshot),
    )
    monkeypatch.setattr(cutting_plan_command_service, "apply_plan_costs", lambda *_args, **_kwargs: {})

    cutting_plan_command_service.save_uploaded_dxf_plan(
        SimpleNamespace(name="DCO-176", edge_cost_usd=0),
        incoming,
        "/private/files/replacement.dxf",
        capability=Capability.REPLACE_DXF,
    )

    matched, new = captured["sheets"][0]["pieces"]
    assert (matched["offcut_source_party"], matched["offcut_execution_party"]) == (
        "CUSTOMER",
        "FACTORY",
    )
    assert (new["offcut_source_party"], new["offcut_execution_party"]) == (
        "UNASSIGNED",
        "UNASSIGNED",
    )
