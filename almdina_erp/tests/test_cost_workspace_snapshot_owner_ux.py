from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
COST_PERMISSIONS = (
    PUBLIC / "costing" / "door_cutting_order_cost_permissions_ux.js"
)
COST_STATE = PUBLIC / "costing" / "door_cutting_order_cost_workspace_state.js"
COST_API = PUBLIC / "costing" / "door_cutting_order_cost_workspace_api.js"
STORE = PUBLIC / "core" / "door_cutting_order_workspace_store.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cost_permissions_is_not_a_second_financial_snapshot_owner() -> None:
    permissions = source(COST_PERMISSIONS)
    state = source(COST_STATE)
    api = source(COST_API)

    assert "AlmdinaCostWorkspaceState" in permissions
    assert 'owner.load(frm, { force: true })' in permissions

    # The read transport belongs exclusively to CostWorkspaceAPI/State. The
    # permission layer may still send focused special-price commands, but it must
    # never issue or merge a second order-cost snapshot request.
    assert "get_order_cost_snapshot" in api
    assert "get_order_cost_snapshot" not in permissions
    assert "function loadCostSnapshot" not in permissions
    assert "function mergeSnapshot" not in permissions
    assert "__almdinaCostSnapshotPromise" not in permissions
    assert "__almdinaCostSnapshotContext" not in permissions

    assert "AlmdinaCostWorkspaceAPI" in state
    assert "api.load(orderName)" in state
    assert "resolveLoad(currentIdentity, requestId, payload)" in state


def test_authoritative_workspace_commit_invalidates_older_reads() -> None:
    store = source(STORE)
    commit_body = store.split("function commit(data)", 1)[1].split(
        "function subscribe", 1
    )[0]

    assert "state.requestId += 1;" in commit_body
    assert "return emit();" in commit_body
    assert "state.data = clone(data);" in commit_body


def test_cost_permissions_preserves_security_and_piece_price_commands() -> None:
    permissions = source(COST_PERMISSIONS)

    assert 'can(frm, "view_costs")' in permissions
    assert 'can(frm, "edit_cost_settings")' in permissions
    assert "scrubCostData" in permissions
    assert "update_clipped_corner_edge_price" in permissions
    assert "approve_special_piece_price" in permissions
    assert "flushPendingPriceEdits" in permissions
