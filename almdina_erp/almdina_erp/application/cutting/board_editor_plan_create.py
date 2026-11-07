"""Create one viewable Cutting Plan Draft from a saved board-editor draft.

Review and create share one locked draft version. The client ready flag is
ignored. Source plans are never mutated. Approval and manufacturing CUT_PATH
use the normal Cutting Plan lifecycle after this draft is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    BoardEditorMaterializeError,
    METHOD_KEY,
    METHOD_LABEL,
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    BOARD_EDITOR,
    DRAFT,
    next_revision,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import LOCKED_ORDER_STATUSES


@dataclass(frozen=True, slots=True)
class CreateBoardEditorPlanCommand:
    order_name: str
    source_plan_name: str
    expected_draft_version: int
    source_content_revision: str
    source_input_fingerprint: str
    create_request_id: str
    draft_name: str = ""


class BoardEditorPlanCreateStore(Protocol):
    def lock_draft(self, order_name: str, plan_name: str) -> dict[str, Any] | None: ...

    def record_create(
        self,
        *,
        draft_name: str,
        request_id: str,
        plan_name: str,
        draft_version: int,
    ) -> None: ...


class CuttingPlanCreatePort(Protocol):
    def existing_revisions(self, order_name: str) -> list[int]: ...

    def create_board_editor_draft(
        self,
        *,
        order_name: str,
        revision: int,
        based_on_plan: str,
        settings: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def apply_snapshot(
        self,
        *,
        order_name: str,
        plan_name: str,
        snapshot: Mapping[str, Any],
        method_key: str,
        method_label: str,
    ) -> dict[str, Any]: ...

    def discard_incomplete_plan(self, plan_name: str) -> None: ...

    def load_source_plan(self, order_name: str, plan_name: str) -> dict[str, Any]: ...


def create_write_allowed(
    *,
    has_edit_capability: bool,
    has_plan_view: bool,
    order_status: str,
) -> bool:
    if str(order_status or "") in LOCKED_ORDER_STATUSES:
        return False
    return bool(has_edit_capability and has_plan_view)


def normalize_create_request_id(value: Any) -> str:
    token = str(value or "").strip()
    if not token or len(token) > 64:
        raise ValueError("invalid_create_request_id")
    return token


def execute_create(
    command: CreateBoardEditorPlanCommand,
    *,
    order_status: str,
    projection: Mapping[str, Any],
    machine_type: str,
    draft_store: BoardEditorPlanCreateStore,
    plan_port: CuttingPlanCreatePort,
) -> dict[str, Any]:
    request_id = normalize_create_request_id(command.create_request_id)
    locked = draft_store.lock_draft(command.order_name, command.source_plan_name)
    if locked is None:
        return {"ok": False, "code": "draft_missing"}
    expected_draft_name = str(command.draft_name or "").strip()
    if expected_draft_name and expected_draft_name != str(locked.get("name") or ""):
        return {"ok": False, "code": "draft_mismatch"}
    if str(order_status or "") in LOCKED_ORDER_STATUSES:
        return {"ok": False, "code": "order_locked"}

    previous_request = str(locked.get("last_create_request_id") or "")
    previous_plan = str(locked.get("last_created_plan") or "")
    previous_version = int(locked.get("last_created_draft_version") or 0)
    if previous_request and previous_request == request_id and previous_plan:
        if previous_version == int(command.expected_draft_version):
            return {
                "ok": True,
                "idempotent": True,
                "plan_name": previous_plan,
                "draft_version": previous_version,
                "source_type": BOARD_EDITOR,
                "status": DRAFT,
            }
        return {"ok": False, "code": "idempotency_version_conflict"}

    if int(locked.get("draft_version") or 0) != int(command.expected_draft_version):
        return {
            "ok": False,
            "code": "version_conflict",
            "draft_version": int(locked.get("draft_version") or 0),
        }

    source = plan_port.load_source_plan(command.order_name, command.source_plan_name)
    if not source:
        return {"ok": False, "code": "source_plan_missing"}
    if str(source.get("order_name") or "") != str(command.order_name):
        return {"ok": False, "code": "order_scope"}

    draft_payload = {
        "present": True,
        "compatible": True,
        "conflict": None,
        "draft_version": int(locked.get("draft_version") or 0),
        "source_content_revision": str(locked.get("source_content_revision") or ""),
        "source_input_fingerprint": str(locked.get("source_input_fingerprint") or ""),
        "distribution_fingerprint": str(locked.get("distribution_fingerprint") or ""),
        "layout": locked.get("layout_json"),
    }
    try:
        snapshot = materialize_plan_snapshot(
            draft=draft_payload,
            projection=projection,
            source_snapshot=source.get("snapshot") or {},
            machine_type=machine_type or str(source.get("machine_type") or "Auto"),
            source_plan_name=str(command.source_plan_name),
            expected_draft_version=int(command.expected_draft_version),
            source_content_revision=str(command.source_content_revision or ""),
            source_input_fingerprint=str(command.source_input_fingerprint or ""),
        )
    except BoardEditorMaterializeError as exc:
        payload: dict[str, Any] = {"ok": False, "code": exc.code}
        if isinstance(exc.detail, Mapping):
            payload["review"] = dict(exc.detail)
        return payload

    revision = next_revision(plan_port.existing_revisions(command.order_name))

    created = plan_port.create_board_editor_draft(
        order_name=command.order_name,
        revision=revision,
        based_on_plan=command.source_plan_name,
        settings={
            "optimization_mode": source.get("optimization_mode"),
            "machine_type": source.get("machine_type"),
            "optimization_time_limit_sec": source.get("optimization_time_limit_sec"),
            "kerf_mm": source.get("kerf_mm"),
            "preferred_trim_mm": source.get("trim_margin_mm"),
        },
    )
    created_name = str(created.get("name") or "")
    try:
        applied = plan_port.apply_snapshot(
            order_name=command.order_name,
            plan_name=created_name,
            snapshot=snapshot,
            method_key=METHOD_KEY,
            method_label=METHOD_LABEL,
        )
    except Exception:
        # Create must be atomic for the operator: a half-written Board Editor
        # plan must not linger, and the editor draft / source plan stay intact.
        if created_name:
            plan_port.discard_incomplete_plan(created_name)
        raise
    draft_store.record_create(
        draft_name=str(locked["name"]),
        request_id=request_id,
        plan_name=str(applied["name"]),
        draft_version=int(command.expected_draft_version),
    )
    return {
        "ok": True,
        "idempotent": False,
        "plan_name": str(applied["name"]),
        "revision": int(applied.get("revision") or revision),
        "draft_version": int(command.expected_draft_version),
        "source_type": BOARD_EDITOR,
        "status": DRAFT,
        "based_on_plan": command.source_plan_name,
        "prefer_plan_tab": "BoardEditor",
        # Materialize already baked posed geometry. Approval/export stay on the
        # normal Cutting Plan lifecycle; CUT_PATH remains post-approval only.
        "manufacturing_blocked": False,
        "manufacturing_block_reason": None,
    }


__all__ = [
    "CreateBoardEditorPlanCommand",
    "BoardEditorPlanCreateStore",
    "CuttingPlanCreatePort",
    "create_write_allowed",
    "execute_create",
    "normalize_create_request_id",
]
