"""Use case for saving one board-editor draft.

Framework-free. The caller authorizes, loads the trusted catalog, and supplies
a store. This module never approves a plan, writes a snapshot, or emits CUT_PATH.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    DraftLayoutError,
    build_prior_draft_archive,
    decide_draft_write,
    distribution_fingerprint,
    draft_key,
    identity_layout_from_projection,
    normalize_layout,
    tokens_operationally_equivalent,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import LOCKED_ORDER_STATUSES


class DraftInsertConflict(Exception):
    """The unique order+plan draft already exists."""


class DraftStore(Protocol):
    def lock(self, key: str) -> Mapping[str, Any] | None: ...

    def insert(self, row: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def update_if_version(
        self,
        key: str,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> bool: ...


def draft_write_allowed(
    *,
    has_edit_capability: bool,
    has_plan_view: bool,
    order_status: str,
) -> bool:
    """Edit capability plus plan view. View alone and locked orders fail closed."""

    if str(order_status or "").strip() in LOCKED_ORDER_STATUSES:
        return False
    return bool(has_edit_capability and has_plan_view)


def execute_save(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DraftStore,
) -> dict[str, Any]:
    """Validate one save and create or update the single draft row."""

    order_name = str(request.get("order_name") or "").strip()
    plan_name = str(request.get("plan_name") or "").strip()
    if order_name != str(context.get("order_name") or "") or plan_name != str(
        context.get("plan_name") or ""
    ):
        return _failure("order_plan_mismatch")
    if str(context.get("order_status") or "") in LOCKED_ORDER_STATUSES:
        return _failure("order_locked")

    try:
        layout = normalize_layout(request.get("layout"), context.get("catalog") or {})
    except DraftLayoutError as exc:
        return _failure("invalid_layout", exc.code)

    fingerprint = distribution_fingerprint(layout)
    key = draft_key(order_name, plan_name)
    expected = _expected_version(request.get("expected_draft_version"))
    live_revision = str(context.get("source_content_revision") or "")
    request_revision = str(request.get("source_content_revision") or "")

    existing = store.lock(key)
    decision = _decision(
        existing,
        expected,
        fingerprint,
        live_revision,
        request_revision,
    )
    if decision == "source_conflict":
        return _failure(
            "source_conflict",
            current_draft_version=None if existing is None else int(existing["draft_version"]),
        )
    if decision == "version_conflict":
        return _failure(
            "version_conflict",
            current_draft_version=None if existing is None else int(existing["draft_version"]),
        )
    if decision == "idempotent" and existing is not None:
        return _success(existing)
    if decision == "create":
        row = {
            "draft_key": key,
            "door_cutting_order": order_name,
            "source_plan": plan_name,
            "source_input_fingerprint": str(context.get("source_input_fingerprint") or ""),
            "source_content_revision": live_revision,
            "draft_version": 1,
            "layout_json": layout,
            "distribution_fingerprint": fingerprint,
        }
        try:
            stored = store.insert(row)
        except DraftInsertConflict:
            existing = store.lock(key)
            decision = _decision(
                existing,
                0,
                fingerprint,
                live_revision,
                request_revision,
            )
            if decision == "idempotent" and existing is not None:
                return _success(existing)
            return _failure(
                "version_conflict",
                current_draft_version=None if existing is None else int(existing["draft_version"]),
            )
        return _success(stored)
    if decision == "update" and existing is not None:
        changes = {
            "draft_version": int(existing["draft_version"]) + 1,
            "layout_json": layout,
            "distribution_fingerprint": fingerprint,
            "source_input_fingerprint": str(context.get("source_input_fingerprint") or ""),
            "source_content_revision": live_revision,
        }
        wrote = store.update_if_version(key, int(existing["draft_version"]), changes)
        if not wrote:
            return _failure(
                "version_conflict",
                current_draft_version=int(existing["draft_version"]),
            )
        updated = dict(existing)
        updated.update(changes)
        return _success(updated)
    return _failure("version_conflict")


def execute_begin_from_current_source(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    store: DraftStore,
) -> dict[str, Any]:
    """Archive an incompatible draft and bind a fresh layout to the live source.

    Does not copy prior poses onto the new source. expected_draft_version must
    match the stored row (never 0 against an existing row). Request source
    tokens must match live. Approved cutting plans are never touched here.
    """

    order_name = str(request.get("order_name") or "").strip()
    plan_name = str(request.get("plan_name") or "").strip()
    if order_name != str(context.get("order_name") or "") or plan_name != str(
        context.get("plan_name") or ""
    ):
        return _failure("order_plan_mismatch")
    if str(context.get("order_status") or "") in LOCKED_ORDER_STATUSES:
        return _failure("order_locked")

    live_revision = str(context.get("source_content_revision") or "")
    request_revision = str(request.get("source_content_revision") or "")
    if not tokens_operationally_equivalent(request_revision, live_revision):
        return _failure("source_conflict")

    try:
        layout = normalize_layout(
            identity_layout_from_projection(context.get("projection") or {}),
            context.get("catalog") or {},
        )
    except DraftLayoutError as exc:
        return _failure("invalid_layout", exc.code)

    fingerprint = distribution_fingerprint(layout)
    key = draft_key(order_name, plan_name)
    expected = _expected_version(request.get("expected_draft_version"))
    existing = store.lock(key)

    if existing is None:
        if expected != 0:
            return _failure("version_conflict")
        row = {
            "draft_key": key,
            "door_cutting_order": order_name,
            "source_plan": plan_name,
            "source_input_fingerprint": str(context.get("source_input_fingerprint") or ""),
            "source_content_revision": live_revision,
            "draft_version": 1,
            "layout_json": layout,
            "distribution_fingerprint": fingerprint,
            "prior_draft_archive_json": None,
        }
        try:
            stored = store.insert(row)
        except DraftInsertConflict:
            return _failure("version_conflict")
        return _begin_success(stored, archived=False)

    # Existing row: expected must match stored version (never 0 overwrite).
    if expected != int(existing["draft_version"]):
        return _failure(
            "version_conflict",
            current_draft_version=int(existing["draft_version"]),
        )

    stored_revision = str(existing.get("source_content_revision") or "")
    if tokens_operationally_equivalent(stored_revision, live_revision):
        # Already bound to live — return current row without wiping layout.
        return _begin_success(existing, archived=False)

    archive = build_prior_draft_archive(existing)
    prior = existing.get("prior_draft_archive_json")
    archive_stack = []
    if isinstance(prior, list):
        archive_stack = list(prior)
    elif isinstance(prior, Mapping) and prior:
        archive_stack = [dict(prior)]
    archive_stack.append(archive)

    changes = {
        "draft_version": int(existing["draft_version"]) + 1,
        "layout_json": layout,
        "distribution_fingerprint": fingerprint,
        "source_input_fingerprint": str(context.get("source_input_fingerprint") or ""),
        "source_content_revision": live_revision,
        "prior_draft_archive_json": archive_stack,
    }
    wrote = store.update_if_version(key, int(existing["draft_version"]), changes)
    if not wrote:
        return _failure(
            "version_conflict",
            current_draft_version=int(existing["draft_version"]),
        )
    updated = dict(existing)
    updated.update(changes)
    return _begin_success(updated, archived=True)


def _decision(
    existing: Mapping[str, Any] | None,
    expected: int,
    fingerprint: str,
    live_revision: str,
    request_revision: str,
) -> str:
    return decide_draft_write(
        stored_version=None if existing is None else int(existing["draft_version"]),
        stored_fingerprint=None if existing is None else str(existing.get("distribution_fingerprint") or ""),
        stored_source_revision=None if existing is None else str(existing.get("source_content_revision") or ""),
        expected_version=expected,
        layout_fingerprint=fingerprint,
        live_source_revision=live_revision,
        request_source_revision=request_revision,
    )


def _begin_success(row: Mapping[str, Any], *, archived: bool) -> dict[str, Any]:
    payload = _success(row)
    payload["code"] = "begun"
    payload["archived_prior_draft"] = bool(archived)
    return payload


def _expected_version(value: Any) -> int:
    if isinstance(value, bool) or value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _success(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "code": "saved",
        "draft_version": int(row["draft_version"]),
        "distribution_fingerprint": str(row["distribution_fingerprint"]),
        "source_content_revision": str(row.get("source_content_revision") or ""),
        "layout": row.get("layout_json"),
    }


def _failure(
    code: str,
    reason: str | None = None,
    *,
    current_draft_version: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "code": code}
    if reason:
        payload["reason"] = reason
    if current_draft_version is not None:
        payload["current_draft_version"] = int(current_draft_version)
    return payload
