"""Save and recover board-editor drawings without touching distribution layout.

Framework-free. The caller authorizes, supplies the trusted piece catalog, and
passes a store. Reference images are accepted only when their file ids are in
the caller-provided trusted set. This phase's service passes an empty set.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import (
    draft_write_allowed,
    execute_save as execute_distribution_save,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    tokens_operationally_equivalent,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    DrawingDocumentError,
    document_fingerprint,
    empty_document,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import (
    DRAWABLE_PIECE_TYPE,
    archive_stack_exceeds_limit,
    blank_matches,
    build_prior_drawing_archive,
    decide_drawing_write,
    drawing_key,
    untrusted_reference_ids,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import LOCKED_ORDER_STATUSES


class DrawingInsertConflict(Exception):
    """The unique order+plan+piece drawing already exists."""


class DrawingStore(Protocol):
    def lock(self, key: str) -> Mapping[str, Any] | None: ...

    def read(self, key: str) -> Mapping[str, Any] | None: ...

    def read_for_plan(self, order_name: str, plan_name: str) -> Sequence[Mapping[str, Any]]: ...

    def insert(self, row: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def update_if_version(
        self,
        key: str,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> bool: ...

    def archive_many(self, updates: Sequence[Mapping[str, Any]]) -> bool: ...


def drawing_read_allowed(*, has_edit_capability: bool, has_plan_view: bool) -> bool:
    """Read uses the board-editor capability, not documentation-edit permission."""

    return bool(has_edit_capability and has_plan_view)


def drawing_write_allowed(
    *,
    has_edit_capability: bool,
    has_plan_view: bool,
    order_status: str,
) -> bool:
    return draft_write_allowed(
        has_edit_capability=has_edit_capability,
        has_plan_view=has_plan_view,
        order_status=order_status,
    )


def execute_save_drawing(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DrawingStore,
) -> dict[str, Any]:
    """Create or update one piece drawing. Distribution fingerprint is not an input."""

    denied = _scope_and_permission(request, context, write=True)
    if denied is not None:
        return denied
    piece_id = str(request.get("piece_instance_id") or "").strip()
    catalog = context.get("catalog") or {}
    piece = catalog.get(piece_id) if isinstance(catalog, Mapping) else None
    if not isinstance(piece, Mapping):
        return _failure("unknown_piece")
    if str(piece.get("piece_type") or "") != DRAWABLE_PIECE_TYPE:
        return _failure("piece_not_drawable")
    trusted_width = piece.get("blank_width_mm")
    trusted_length = piece.get("blank_length_mm")
    if trusted_width is None or trusted_length is None:
        return _failure("blank_unproven")

    try:
        document = normalize_document(request.get("drawing"))
    except DrawingDocumentError as exc:
        return _failure("invalid_drawing", exc.code)
    if str(document.get("piece_instance_id") or "") != piece_id:
        return _failure("piece_mismatch")
    blank = document.get("blank") or {}
    if not blank_matches(
        float(blank.get("width_mm") or 0),
        float(blank.get("length_mm") or 0),
        trusted_width_mm=float(trusted_width),
        trusted_length_mm=float(trusted_length),
    ):
        return _failure("blank_mismatch")
    if untrusted_reference_ids(document, context.get("trusted_file_ids")):
        return _failure("untrusted_reference")

    order_name = str(context.get("order_name") or "")
    plan_name = str(context.get("plan_name") or "")
    fingerprint = document_fingerprint(document)
    key = drawing_key(order_name, plan_name, piece_id)
    expected = _expected_version(request.get("expected_drawing_version"))
    live_revision = str(context.get("source_content_revision") or "")
    request_revision = str(request.get("source_content_revision") or "")
    existing = store.lock(key)
    decision = decide_drawing_write(
        stored_version=None if existing is None else int(existing["drawing_version"]),
        stored_fingerprint=None if existing is None else str(existing.get("document_fingerprint") or ""),
        stored_source_revision=None if existing is None else str(existing.get("source_content_revision") or ""),
        expected_version=expected,
        document_fingerprint=fingerprint,
        live_source_revision=live_revision,
        request_source_revision=request_revision,
    )
    if decision == "source_conflict":
        return _failure(
            "source_conflict",
            current_drawing_version=None if existing is None else int(existing["drawing_version"]),
        )
    if decision == "version_conflict":
        return _failure(
            "version_conflict",
            current_drawing_version=None if existing is None else int(existing["drawing_version"]),
        )
    if decision == "idempotent" and existing is not None:
        return _success(existing, idempotent=True)
    if decision == "create":
        row = _new_row(
            key=key,
            order_name=order_name,
            plan_name=plan_name,
            piece_id=piece_id,
            document=document,
            fingerprint=fingerprint,
            live_revision=live_revision,
            source_input_fingerprint=str(context.get("source_input_fingerprint") or ""),
            version=1,
        )
        try:
            stored = store.insert(row)
        except DrawingInsertConflict:
            existing = store.lock(key)
            decision = decide_drawing_write(
                stored_version=None if existing is None else int(existing["drawing_version"]),
                stored_fingerprint=None if existing is None else str(existing.get("document_fingerprint") or ""),
                stored_source_revision=None
                if existing is None
                else str(existing.get("source_content_revision") or ""),
                expected_version=0,
                document_fingerprint=fingerprint,
                live_source_revision=live_revision,
                request_source_revision=request_revision,
            )
            if decision == "idempotent" and existing is not None:
                return _success(existing, idempotent=True)
            return _failure(
                "version_conflict",
                current_drawing_version=None if existing is None else int(existing["drawing_version"]),
            )
        return _success(stored, idempotent=False)
    if decision == "update" and existing is not None:
        changes = {
            "drawing_version": int(existing["drawing_version"]) + 1,
            "drawing_json": document,
            "document_fingerprint": fingerprint,
            "source_input_fingerprint": str(context.get("source_input_fingerprint") or ""),
            "source_content_revision": live_revision,
        }
        wrote = store.update_if_version(key, int(existing["drawing_version"]), changes)
        if not wrote:
            return _failure(
                "version_conflict",
                current_drawing_version=int(existing["drawing_version"]),
            )
        updated = dict(existing)
        updated.update(changes)
        return _success(updated, idempotent=False)
    return _failure("version_conflict")


def execute_get_drawing(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DrawingStore,
) -> dict[str, Any]:
    """Return one active drawing. An incompatible source does not return its geometry."""

    denied = _scope_and_permission(request, context, write=False)
    if denied is not None:
        return denied
    piece_id = str(request.get("piece_instance_id") or "").strip()
    catalog = context.get("catalog") or {}
    piece = catalog.get(piece_id) if isinstance(catalog, Mapping) else None
    if not isinstance(piece, Mapping):
        return _failure("unknown_piece")
    if str(piece.get("piece_type") or "") != DRAWABLE_PIECE_TYPE:
        return _failure("piece_not_drawable")
    order_name = str(context.get("order_name") or "")
    plan_name = str(context.get("plan_name") or "")
    row = store.read(drawing_key(order_name, plan_name, piece_id))
    return _view(row, context, piece_id)


def execute_list_drawings(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DrawingStore,
) -> dict[str, Any]:
    """Metadata for special pieces. Full documents stay on get."""

    denied = _scope_and_permission(request, context, write=False)
    if denied is not None:
        return denied
    order_name = str(context.get("order_name") or "")
    plan_name = str(context.get("plan_name") or "")
    catalog = context.get("catalog") if isinstance(context.get("catalog"), Mapping) else {}
    stored = {
        str(row.get("piece_instance_id") or ""): row
        for row in store.read_for_plan(order_name, plan_name)
    }
    summaries = []
    for piece_id in sorted(catalog):
        piece = catalog[piece_id]
        if not isinstance(piece, Mapping) or str(piece.get("piece_type") or "") != DRAWABLE_PIECE_TYPE:
            continue
        view = _view(stored.get(piece_id), context, piece_id)
        view.pop("drawing", None)
        view["blank_width_mm"] = piece.get("blank_width_mm")
        view["blank_length_mm"] = piece.get("blank_length_mm")
        view["drawable"] = piece.get("blank_width_mm") is not None and piece.get("blank_length_mm") is not None
        summaries.append(view)
    return {
        "ok": True,
        "code": "listed",
        "can_edit": _can_edit(context),
        "source_content_revision": str(context.get("source_content_revision") or ""),
        "drawings": summaries,
    }


def execute_get_drawing_archive(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DrawingStore,
) -> dict[str, Any]:
    """Return retained drawings for one in-catalog special piece. They are not active."""

    denied = _scope_and_permission(request, context, write=False)
    if denied is not None:
        return denied
    piece_id = str(request.get("piece_instance_id") or "").strip()
    catalog = context.get("catalog") or {}
    piece = catalog.get(piece_id) if isinstance(catalog, Mapping) else None
    if not isinstance(piece, Mapping):
        return _failure("unknown_piece")
    if str(piece.get("piece_type") or "") != DRAWABLE_PIECE_TYPE:
        return _failure("piece_not_drawable")
    row = store.read(
        drawing_key(str(context.get("order_name") or ""), str(context.get("plan_name") or ""), piece_id)
    )
    entries = []
    if row is not None and isinstance(row.get("prior_drawing_archive_json"), list):
        entries = list(row.get("prior_drawing_archive_json") or [])
    return {
        "ok": True,
        "code": "archive",
        "piece_instance_id": piece_id,
        "active": False,
        "entries": entries,
    }


def execute_archive_drawings_for_new_source(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DrawingStore,
) -> dict[str, Any]:
    """Move incompatible drawings into their own archive and start an empty active document.

    Rows already bound to the live source are left unchanged. Rows whose piece
    is no longer a proven special piece are also left unchanged, so an old
    drawing is never rebound onto a new source by rewriting only its token.
    The whole batch is planned before any write.
    """

    denied = _scope_and_permission(request, context, write=True)
    if denied is not None:
        return denied
    live_revision = str(context.get("source_content_revision") or "")
    request_revision = str(request.get("source_content_revision") or "")
    if not tokens_operationally_equivalent(request_revision, live_revision):
        return _failure("source_conflict")

    order_name = str(context.get("order_name") or "")
    plan_name = str(context.get("plan_name") or "")
    catalog = context.get("catalog") if isinstance(context.get("catalog"), Mapping) else {}
    rows = list(store.read_for_plan(order_name, plan_name))
    updates: list[dict[str, Any]] = []
    for row in rows:
        if tokens_operationally_equivalent(str(row.get("source_content_revision") or ""), live_revision):
            continue
        piece_id = str(row.get("piece_instance_id") or "")
        piece = catalog.get(piece_id)
        if (
            not isinstance(piece, Mapping)
            or str(piece.get("piece_type") or "") != DRAWABLE_PIECE_TYPE
            or piece.get("blank_width_mm") is None
            or piece.get("blank_length_mm") is None
        ):
            continue
        stack = []
        prior = row.get("prior_drawing_archive_json")
        if isinstance(prior, list):
            stack = list(prior)
        elif isinstance(prior, Mapping) and prior:
            stack = [dict(prior)]
        stack.append(build_prior_drawing_archive(row))
        if archive_stack_exceeds_limit(stack):
            return _failure("archive_limit")
        document = empty_document(piece_id, float(piece["blank_width_mm"]), float(piece["blank_length_mm"]))
        updates.append(
            {
                "drawing_key": drawing_key(order_name, plan_name, piece_id),
                "expected_version": int(row.get("drawing_version") or 0),
                "changes": {
                    "drawing_version": int(row.get("drawing_version") or 0) + 1,
                    "drawing_json": document,
                    "document_fingerprint": document_fingerprint(document),
                    "source_input_fingerprint": str(context.get("source_input_fingerprint") or ""),
                    "source_content_revision": live_revision,
                    "prior_drawing_archive_json": stack,
                },
            }
        )
    if not updates:
        return {"ok": True, "code": "unchanged", "archived_count": 0}
    if not store.archive_many(updates):
        return _failure("version_conflict")
    return {"ok": True, "code": "archived", "archived_count": len(updates)}


def execute_coordinated_editor_save(
    distribution_request: Mapping[str, Any],
    drawing_requests: Sequence[Mapping[str, Any]],
    distribution_context: Mapping[str, Any],
    drawing_context: Mapping[str, Any],
    distribution_store: Any,
    drawing_store: DrawingStore,
) -> dict[str, Any]:
    """Save distribution first, then each drawing.

    The two contexts stay separate: distribution membership is not the drawing
    catalog. There is no single client transaction. A distribution conflict
    skips the drawings. A later drawing conflict does not roll back the
    distribution row and does not change its fingerprint.
    """

    distribution = execute_distribution_save(
        distribution_request,
        distribution_context,
        distribution_store,
    )
    if not distribution.get("ok"):
        return {
            "ok": False,
            "code": str(distribution.get("code") or "distribution_failed"),
            "distribution": distribution,
            "drawings": [],
        }
    drawings = [
        execute_save_drawing(request, drawing_context, drawing_store)
        for request in drawing_requests
    ]
    ok = all(item.get("ok") for item in drawings)
    return {
        "ok": ok,
        "code": "saved" if ok else "partial",
        "distribution": distribution,
        "drawings": drawings,
    }


def _view(row: Mapping[str, Any] | None, context: Mapping[str, Any], piece_id: str) -> dict[str, Any]:
    can_edit = _can_edit(context)
    if row is None:
        return {
            "ok": True,
            "code": "loaded",
            "piece_instance_id": piece_id,
            "present": False,
            "compatible": True,
            "active": False,
            "conflict": None,
            "drawing_version": 0,
            "document_fingerprint": "",
            "can_edit": can_edit,
            "drawing": None,
        }
    live_revision = str(context.get("source_content_revision") or "")
    compatible = tokens_operationally_equivalent(
        str(row.get("source_content_revision") or ""),
        live_revision,
    )
    return {
        "ok": True,
        "code": "loaded",
        "piece_instance_id": piece_id,
        "present": True,
        "compatible": compatible,
        "active": compatible,
        "conflict": None if compatible else "source",
        "drawing_version": int(row.get("drawing_version") or 0),
        "document_fingerprint": str(row.get("document_fingerprint") or ""),
        "can_edit": can_edit,
        "drawing": row.get("drawing_json") if compatible else None,
    }


def _new_row(
    *,
    key: str,
    order_name: str,
    plan_name: str,
    piece_id: str,
    document: Mapping[str, Any],
    fingerprint: str,
    live_revision: str,
    source_input_fingerprint: str,
    version: int,
) -> dict[str, Any]:
    return {
        "drawing_key": key,
        "door_cutting_order": order_name,
        "source_plan": plan_name,
        "piece_instance_id": piece_id,
        "source_input_fingerprint": source_input_fingerprint,
        "source_content_revision": live_revision,
        "drawing_version": version,
        "document_fingerprint": fingerprint,
        "drawing_json": document,
        "prior_drawing_archive_json": [],
    }


def _scope_and_permission(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    write: bool,
) -> dict[str, Any] | None:
    order_name = str(request.get("order_name") or "").strip()
    plan_name = str(request.get("plan_name") or "").strip()
    if order_name != str(context.get("order_name") or "") or plan_name != str(context.get("plan_name") or ""):
        return _failure("order_plan_mismatch")
    status = str(context.get("order_status") or "")
    if write and status in LOCKED_ORDER_STATUSES:
        return _failure("order_locked")
    allowed = (
        drawing_write_allowed(
            has_edit_capability=bool(context.get("has_edit_capability")),
            has_plan_view=bool(context.get("has_plan_view")),
            order_status=status,
        )
        if write
        else drawing_read_allowed(
            has_edit_capability=bool(context.get("has_edit_capability")),
            has_plan_view=bool(context.get("has_plan_view")),
        )
    )
    if not allowed:
        return _failure("permission_denied")
    return None


def _can_edit(context: Mapping[str, Any]) -> bool:
    return drawing_write_allowed(
        has_edit_capability=bool(context.get("has_edit_capability")),
        has_plan_view=bool(context.get("has_plan_view")),
        order_status=str(context.get("order_status") or ""),
    )


def _expected_version(value: Any) -> int:
    if isinstance(value, bool) or value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _success(row: Mapping[str, Any], *, idempotent: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "code": "saved",
        "idempotent": idempotent,
        "piece_instance_id": str(row.get("piece_instance_id") or ""),
        "drawing_version": int(row["drawing_version"]),
        "document_fingerprint": str(row.get("document_fingerprint") or ""),
        "source_content_revision": str(row.get("source_content_revision") or ""),
        "drawing": row.get("drawing_json"),
    }


def _failure(
    code: str,
    reason: str | None = None,
    *,
    current_drawing_version: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "code": code}
    if reason:
        payload["reason"] = reason
    if current_drawing_version is not None:
        payload["current_drawing_version"] = int(current_drawing_version)
    return payload


__all__ = [
    "DrawingInsertConflict",
    "DrawingStore",
    "drawing_read_allowed",
    "drawing_write_allowed",
    "execute_archive_drawings_for_new_source",
    "execute_coordinated_editor_save",
    "execute_get_drawing",
    "execute_get_drawing_archive",
    "execute_list_drawings",
    "execute_save_drawing",
]
