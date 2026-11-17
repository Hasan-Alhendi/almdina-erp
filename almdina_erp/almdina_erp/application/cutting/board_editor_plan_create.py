"""Create one viewable Cutting Plan Draft from a saved board-editor draft.

Review and create share one locked draft version. The client ready flag is
ignored. Source plans are never mutated. Approval and manufacturing CUT_PATH
use the normal Cutting Plan lifecycle after this draft is created.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_compile import (
    compile_manufacturing_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_copy import (
    DrawingCopyError,
    build_copied_drawing_rows,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    BoardEditorMaterializeError,
    METHOD_KEY,
    METHOD_LABEL,
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    geometry_reserves_blank,
    material_outline_cm,
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


class DrawingCopyStore(Protocol):
    def insert(self, row: Mapping[str, Any]) -> dict[str, Any]: ...

    def delete(self, key: str) -> None: ...


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


def compile_saved_drawings(
    records: Sequence[Mapping[str, Any]],
    pieces_by_instance: Mapping[str, Mapping[str, Any]],
    expected_versions: Mapping[str, Any] | None = None,
    source_input_fingerprint: str = "",
) -> dict[str, Any]:
    """Compile trusted saved drawings. Client geometry is not an input.

    ``expected_versions is None`` means the caller sent no version map. That is
    allowed only when this plan has no saved drawings. ``{}`` is a real claim
    that the set is empty. Any other non-map is invalid. A map must equal the
    stored piece/version set exactly, including drawings the editor never opened.
    """

    stored = _stored_drawing_versions(records)
    if stored is None:
        return {"ok": False, "code": "drawing_versions_invalid"}
    parsed = _expected_drawing_versions(expected_versions)
    if parsed is None:
        return {"ok": False, "code": "drawing_versions_invalid"}
    if parsed is _ABSENT_DRAWING_VERSIONS:
        if stored:
            return {"ok": False, "code": "drawing_versions_missing"}
    elif parsed != stored:
        return {"ok": False, "code": "drawing_version_conflict"}
    adopted: dict[str, str] = {}
    for record in records:
        instance = str(record.get("piece_instance_id") or "")
        piece = pieces_by_instance.get(instance)
        if piece is None or str(piece.get("piece_type") or "") != "Special":
            continue
        stored_fingerprint = str(record.get("source_input_fingerprint") or "")
        if source_input_fingerprint and stored_fingerprint and stored_fingerprint != source_input_fingerprint:
            return {"ok": False, "code": "source_changed", "piece_instance_id": instance}
        document = record.get("document")
        if not isinstance(document, Mapping):
            document = record.get("drawing_json")
        if not isinstance(document, Mapping):
            return {"ok": False, "code": "geometry_rejected", "reason": "invalid_document", "piece_instance_id": instance}
        width_cm = _blank_cm(piece, "original_w", "w")
        length_cm = _blank_cm(piece, "original_h", "h")
        result = compile_manufacturing_geometry(
            document,
            blank_width_mm=width_cm * 10.0,
            blank_length_mm=length_cm * 10.0,
        )
        if result["status"] == "rejected":
            return {
                "ok": False,
                "code": "geometry_rejected",
                "reason": result["code"],
                "piece_instance_id": instance,
                "path_id": result.get("path_id") or "",
            }
        if result["status"] == "ready":
            if _machining_conflicts_with_new_outline(piece):
                return {
                    "ok": False,
                    "code": "geometry_rejected",
                    "reason": "addon_unproven",
                    "piece_instance_id": instance,
                }
            adopted[instance] = json.dumps(result["geometry"], separators=(",", ":"), sort_keys=True)
    return {"ok": True, "adopted": adopted}


def projection_with_adopted_geometry(
    projection: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    adopted: Mapping[str, str],
) -> dict[str, Any]:
    """Review the new outline without changing the source snapshot object."""

    patched = deepcopy(dict(projection))
    if not adopted:
        return patched
    pieces = _snapshot_pieces(source_snapshot)
    outers: dict[str, list[list[float]]] = {}
    for instance, payload in adopted.items():
        piece = dict(pieces.get(instance) or {})
        piece["special_shape_geometry_json"] = payload
        piece.pop("placement_outline_cm", None)
        piece["piece_type"] = "Special"
        outline = material_outline_cm(piece)
        if outline is None:
            raise BoardEditorMaterializeError(
                "geometry_rejected",
                detail={"piece_instance_id": instance, "reason": "outline_unplaced"},
            )
        outers[instance] = [[point[0] * 10.0, point[1] * 10.0] for point in outline]
    for piece in patched.get("pieces") or []:
        if not isinstance(piece, dict):
            continue
        instance = str(piece.get("piece_instance_id") or "")
        if instance not in adopted:
            continue
        piece["special_shape_geometry_json"] = adopted[instance]
        piece["piece_type"] = "Special"
        piece["reserves_blank"] = geometry_reserves_blank(piece)
        piece["exact_geometry"] = True
    for element in patched.get("elements") or []:
        instance = str(element.get("piece_instance_id") or "")
        if element.get("kind") != "finished_outline" or instance not in outers:
            continue
        geometry = element.get("geometry") if isinstance(element.get("geometry"), Mapping) else {}
        element["geometry"] = {**dict(geometry), "outer": outers[instance], "holes": []}
    return patched


class _AbsentDrawingVersions:
    """Sentinel: the request did not include a version map."""


_ABSENT_DRAWING_VERSIONS = _AbsentDrawingVersions()


def _stored_drawing_versions(records: Sequence[Mapping[str, Any]]) -> dict[str, int] | None:
    stored: dict[str, int] = {}
    for record in records:
        instance = str(record.get("piece_instance_id") or "")
        if not instance or instance in stored:
            return None
        version = _whole_version(record.get("drawing_version"))
        if version is None:
            return None
        stored[instance] = version
    return stored


def _expected_drawing_versions(expected: Mapping[str, Any] | None) -> dict[str, int] | _AbsentDrawingVersions | None:
    if expected is None:
        return _ABSENT_DRAWING_VERSIONS
    if not isinstance(expected, Mapping):
        return None
    parsed: dict[str, int] = {}
    for key, value in expected.items():
        instance = str(key or "")
        if not instance or instance in parsed:
            return None
        version = _whole_version(value)
        if version is None:
            return None
        parsed[instance] = version
    return parsed


def _whole_version(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        return None
    if number < 0:
        return None
    return number


def _machining_conflicts_with_new_outline(piece: Mapping[str, Any]) -> bool:
    """Liner, rear groove, and recessed handle are not proven on a new contour."""

    for field in ("extra_liner", "extra_back_groove", "extra_recessed_handle_cutout"):
        value = piece.get(field)
        if value in (1, True, "1"):
            return True
    return False


def geometry_rejection_parts(piece: Mapping[str, Any] | None) -> tuple[str, str, str]:
    """Door label and centimetre size for a geometry message. No technical id."""

    row = piece or {}
    label = str(row.get("label") or "").strip()
    return label, _cm_label(row.get("original_w")), _cm_label(row.get("original_h"))


def format_geometry_rejection(detail: str, piece: Mapping[str, Any] | None) -> str:
    """English sentence. The service translates the same placeholders."""

    label, width, height = geometry_rejection_parts(piece)
    if label and width and height:
        return f"Door {label}. Size {width} × {height} cm. {detail}"
    if label:
        return f"Door {label}. {detail}"
    return detail


def _cm_label(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number != number:
        return ""
    if number.is_integer():
        return str(int(number))
    return str(round(number, 3))


def _blank_cm(piece: Mapping[str, Any], primary: str, fallback: str) -> float:
    placement = piece.get("placement_cm") if isinstance(piece.get("placement_cm"), Mapping) else {}
    raw = piece.get(primary)
    if raw in (None, ""):
        raw = piece.get(fallback)
    if raw in (None, ""):
        raw = placement.get("w" if fallback == "w" else "h")
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _piece_catalog(projection: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    catalog = dict(_snapshot_pieces(snapshot))
    for piece in projection.get("pieces") or []:
        if not isinstance(piece, Mapping):
            continue
        instance = str(piece.get("piece_instance_id") or "")
        if not instance:
            continue
        catalog[instance] = {**dict(catalog.get(instance) or {}), **dict(piece)}
    return catalog


def _snapshot_pieces(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for sheet in snapshot.get("sheets") or []:
        if not isinstance(sheet, Mapping):
            continue
        for piece in sheet.get("pieces") or []:
            if isinstance(piece, Mapping):
                found[str(piece.get("piece_instance_id") or "")] = piece
    return found


def _copy_drawings_onto_plan(
    *,
    drawing_store: DrawingCopyStore,
    plan_port: CuttingPlanCreatePort,
    records: Sequence[Mapping[str, Any]],
    source_snapshot: Mapping[str, Any],
    copied_snapshot: Mapping[str, Any],
    order_name: str,
    plan_name: str,
    applied: Mapping[str, Any],
    source_input_fingerprint: str,
    revision: int,
) -> dict[str, Any] | None:
    """Insert independent drawings. On failure the new plan is discarded."""

    fingerprint = str(applied.get("input_fingerprint") or source_input_fingerprint or "")
    token = str(applied.get("content_revision_token") or "")
    if not token:
        token = "|".join([plan_name, "", str(revision), fingerprint, "0", "0"])
    try:
        rows = build_copied_drawing_rows(
            records=records,
            source_snapshot=source_snapshot,
            copied_snapshot=copied_snapshot,
            order_name=order_name,
            plan_name=plan_name,
            source_content_revision=token,
            source_input_fingerprint=fingerprint,
        )
    except DrawingCopyError:
        plan_port.discard_incomplete_plan(plan_name)
        return {"ok": False, "code": "drawing_copy_failed"}
    inserted: list[str] = []
    try:
        for row in rows:
            drawing_store.insert(row)
            inserted.append(str(row["drawing_key"]))
    except Exception:
        delete_failed = False
        for key in inserted:
            try:
                drawing_store.delete(key)
            except Exception:
                delete_failed = True
        plan_port.discard_incomplete_plan(plan_name)
        if delete_failed:
            raise
        return {"ok": False, "code": "drawing_copy_failed"}
    return None


def execute_create(
    command: CreateBoardEditorPlanCommand,
    *,
    order_status: str,
    projection: Mapping[str, Any],
    machine_type: str,
    draft_store: BoardEditorPlanCreateStore,
    plan_port: CuttingPlanCreatePort,
    drawing_records: Sequence[Mapping[str, Any]] | None = None,
    expected_drawing_versions: Mapping[str, Any] | None = None,
    drawing_store: DrawingCopyStore | None = None,
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

    # The draft row is already locked. Read drawings under that same lock so a
    # drawing inserted after an earlier snapshot cannot enter this copy.
    verified_records: Sequence[Mapping[str, Any]] = list(drawing_records or [])
    if drawing_store is not None:
        lock_for_plan = getattr(drawing_store, "lock_for_plan", None)
        if callable(lock_for_plan):
            verified_records = list(lock_for_plan(command.order_name, command.source_plan_name) or [])

    source = plan_port.load_source_plan(command.order_name, command.source_plan_name)
    if not source:
        return {"ok": False, "code": "source_plan_missing"}
    if str(source.get("order_name") or "") != str(command.order_name):
        return {"ok": False, "code": "order_scope"}

    compiled = compile_saved_drawings(
        verified_records,
        _piece_catalog(projection, source.get("snapshot") or {}),
        expected_drawing_versions,
        source_input_fingerprint=str(command.source_input_fingerprint or ""),
    )
    if not compiled.get("ok"):
        return compiled
    try:
        review_projection = projection_with_adopted_geometry(
            projection,
            source.get("snapshot") or {},
            compiled.get("adopted") or {},
        )
    except BoardEditorMaterializeError as exc:
        return {"ok": False, "code": exc.code, "reason": "outline_unplaced", **(exc.detail or {})}

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
            projection=review_projection,
            source_snapshot=source.get("snapshot") or {},
            machine_type=machine_type or str(source.get("machine_type") or "Auto"),
            source_plan_name=str(command.source_plan_name),
            expected_draft_version=int(command.expected_draft_version),
            source_content_revision=str(command.source_content_revision or ""),
            source_input_fingerprint=str(command.source_input_fingerprint or ""),
            adopted_geometry=compiled.get("adopted") or None,
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
    if drawing_store is not None and verified_records:
        copied = _copy_drawings_onto_plan(
            drawing_store=drawing_store,
            plan_port=plan_port,
            records=verified_records,
            source_snapshot=source.get("snapshot") or {},
            copied_snapshot=snapshot,
            order_name=command.order_name,
            plan_name=created_name,
            applied=applied,
            source_input_fingerprint=str(command.source_input_fingerprint or ""),
            revision=int(applied.get("revision") or revision),
        )
        if copied is not None:
            return copied
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
