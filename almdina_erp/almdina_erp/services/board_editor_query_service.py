"""Read-only Board Editor projection query.

Opens no write path: no plan mutation, no approval change, no CUT_PATH
generation, and no client-supplied file_url authority.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.cutting.board_editor_projection import (
    project_board_editor,
)
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_layer_catalog import (
    CUT_PATH_LAYER,
    GEOMETRY_LAYER,
    HANDLE_RECESS_LAYER,
    LINER_LAYER,
    OFFCUT_LAYER,
    REAR_GROOVE_LAYER,
    SHEET_OUTLINE_LAYER,
    TEXT_LAYER_EXPORT_NAME,
    canonical_layer_match_keys,
    layer_match_key,
)
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    DxfReadError,
    read_dxf_geometry_bytes,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    plan_fingerprint_compatibility,
)
from almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service import (
    overlay_background_recalculation,
)

# Snapshot-owned manufacturing/display layers: their DXF segments are not re-added
# as unbound references when the operational snapshot already carries geometry.
_SNAPSHOT_OWNED_LAYER_KEYS = frozenset(
    {
        layer_match_key(SHEET_OUTLINE_LAYER),
        layer_match_key(GEOMETRY_LAYER),
        layer_match_key(OFFCUT_LAYER),
        layer_match_key(LINER_LAYER),
        layer_match_key(REAR_GROOVE_LAYER),
        layer_match_key(HANDLE_RECESS_LAYER),
        layer_match_key(TEXT_LAYER_EXPORT_NAME),
    }
)


def _authorized_order(order_name: str) -> Any:
    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("Order name is required."), frappe.ValidationError)
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_cutting_plan_capability(
        order,
        Capability.VIEW_CUTTING_PLAN,
        message=_("You do not have permission to view the cutting plan for this order."),
    )
    return order


def _capabilities(order: Any) -> dict[str, bool]:
    return {
        "view_system": cutting_plan_capability_allowed(
            order, Capability.VIEW_SYSTEM_CUTTING_PLAN
        ),
        "view_uploaded": cutting_plan_capability_allowed(
            order, Capability.VIEW_UPLOADED_CUTTING_PLAN
        ),
        "view_approved": cutting_plan_capability_allowed(
            order, Capability.VIEW_APPROVED_CUTTING_PLAN
        ),
    }


def _load_plan_for_order(order: Any, plan_name: str) -> Any:
    name = str(plan_name or "").strip()
    if not name:
        frappe.throw(_("Cutting plan name is required."), frappe.ValidationError)
    if not frappe.db.exists("Cutting Plan", name):
        frappe.throw(_("The selected cutting plan is not available."), frappe.DoesNotExistError)
    plan = frappe.get_doc("Cutting Plan", name)
    if str(getattr(plan, "door_cutting_order", "") or "") != str(order.name):
        frappe.throw(
            _("The selected cutting plan does not belong to this order."),
            frappe.PermissionError,
        )
    if str(getattr(plan, "plan_kind", "Order") or "Order") != "Order":
        frappe.throw(_("The selected cutting plan is not available."), frappe.ValidationError)
    return plan


def _plan_view_allowed(order: Any, plan: Any, capabilities: dict[str, bool]) -> bool:
    source = str(getattr(plan, "source_type", "") or "").strip()
    status = str(getattr(plan, "status", "") or "").strip()
    approved_name = str(getattr(order, "approved_plan", "") or "").strip()
    plan_name = str(getattr(plan, "name", "") or "").strip()

    if plan_name and approved_name and plan_name == approved_name and status == APPROVED:
        return bool(capabilities["view_approved"])
    if status == APPROVED:
        return bool(capabilities["view_approved"])
    if source == SYSTEM:
        return bool(capabilities["view_system"])
    if source == UPLOADED_DXF:
        return bool(capabilities["view_uploaded"])
    return False


def _parse_snapshot(plan: Any) -> dict[str, Any]:
    raw = getattr(plan, "snapshot_json", None)
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return sanitize_plan_snapshot(raw)
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return sanitize_plan_snapshot(parsed)


def _order_allow_rotation_by_instance(order: Any) -> dict[str, bool]:
    """Trusted allow_rotation flags from the order detail (not invented by the client)."""

    mapping: dict[str, bool] = {}
    for row in (order.get("pieces") if hasattr(order, "get") else None) or []:
        instance_id = str(getattr(row, "piece_instance_id", "") or "").strip()
        if not instance_id:
            continue
        mapping[instance_id] = bool(cint(getattr(row, "allow_rotation", 0)))
    return mapping


def _enrich_snapshot_allow_rotation(
    snapshot: dict[str, Any], order: Any
) -> dict[str, Any]:
    """Attach proven allow_rotation onto placed/unplaced pieces without mutating order rows."""

    flags = _order_allow_rotation_by_instance(order)
    if not flags:
        return snapshot

    def _apply(piece: Any) -> None:
        if not isinstance(piece, dict):
            return
        instance_id = str(piece.get("piece_instance_id") or "").strip()
        if not instance_id or instance_id not in flags:
            return
        # Do not overwrite an already-proven snapshot value with a weaker signal.
        if "allow_rotation" in piece:
            piece["allow_rotation_proven"] = True
            return
        piece["allow_rotation"] = flags[instance_id]
        piece["allow_rotation_proven"] = True

    for sheet in snapshot.get("sheets") or []:
        if not isinstance(sheet, dict):
            continue
        for piece in sheet.get("pieces") or []:
            _apply(piece)
    for piece in snapshot.get("unplaced") or []:
        _apply(piece)
    return snapshot


def _source_kind_for_plan(order: Any, plan: Any) -> str:
    status = str(getattr(plan, "status", "") or "").strip()
    source = str(getattr(plan, "source_type", "") or "").strip()
    approved_name = str(getattr(order, "approved_plan", "") or "").strip()
    if (
        approved_name
        and str(plan.name) == approved_name
        and status == APPROVED
    ):
        return "approved"
    if source == UPLOADED_DXF:
        return "uploaded"
    if source == SYSTEM:
        return "system"
    return "unknown"


def _display_context_for_plan(order: Any, plan: Any) -> str:
    status = str(getattr(plan, "status", "") or "").strip()
    approved_name = str(getattr(order, "approved_plan", "") or "").strip()
    if status == DRAFT:
        return "current_draft"
    if status == APPROVED and approved_name and str(plan.name) == approved_name:
        return "current_approved"
    return "historical"


def _snapshot_json_text(plan: Any) -> str:
    raw = getattr(plan, "snapshot_json", None)
    if raw in (None, ""):
        return ""
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return str(raw)


def _plan_freshness_payload(order: Any, plan: Any) -> dict[str, Any]:
    """Read-only freshness for the explicit plan. Never mutates the plan."""

    display_context = _display_context_for_plan(order, plan)
    stored_fingerprint = str(getattr(plan, "input_fingerprint", "") or "")
    persisted_stale = bool(cint(getattr(plan, "plan_needs_recalculation", 0)))
    modified = getattr(plan, "modified", None)
    modified_text = str(modified) if modified not in (None, "") else ""
    revision = cint(getattr(plan, "revision", 0))
    background = overlay_background_recalculation(order.name)
    snapshot_json = _snapshot_json_text(plan)

    freshness_state = "PERSISTED_STALE" if persisted_stale else "UNKNOWN"
    freshness_reason = "plan_needs_recalculation" if persisted_stale else ""
    fingerprint_contract = ""
    expected_fingerprint = ""
    try:
        compatibility = plan_fingerprint_compatibility(
            order,
            plan,
            stored_fingerprint,
            snapshot_json=snapshot_json,
        )
        freshness_state = (
            "PERSISTED_STALE"
            if persisted_stale and compatibility.compatible
            else str(compatibility.state or freshness_state)
        )
        freshness_reason = str(
            compatibility.reason or freshness_reason or ""
        )
        fingerprint_contract = str(compatibility.contract or "")
        expected_fingerprint = str(compatibility.expected_fingerprint or "")
        needs_recalculation = persisted_stale or not compatibility.compatible
    except (ManufacturingRequirementsError, frappe.ValidationError):
        freshness_state = "REVIEW_REQUIRED"
        freshness_reason = "manufacturing_requirements_unavailable"
        needs_recalculation = True

    job_status = str((background or {}).get("status") or "idle").strip().lower()
    job_active = job_status in {"queued", "running", "enqueue"}
    immutable_snapshot = display_context == "historical" or (
        display_context == "current_approved"
    )
    reflects_current_order = (
        display_context in {"current_draft", "current_approved"}
        and not needs_recalculation
        and not job_active
    )
    content_revision_token = "|".join(
        [
            str(plan.name),
            modified_text,
            str(revision),
            stored_fingerprint or expected_fingerprint or "",
            "1" if needs_recalculation else "0",
            job_status,
        ]
    )
    return {
        "needs_recalculation": bool(needs_recalculation),
        "freshness_state": freshness_state,
        "freshness_reason": freshness_reason,
        "fingerprint_contract": fingerprint_contract,
        "input_fingerprint": stored_fingerprint,
        "expected_fingerprint": expected_fingerprint,
        "background_recalculation": background,
        "job_active": bool(job_active),
        "display_context": display_context,
        "immutable_snapshot": bool(immutable_snapshot),
        "reflects_current_order": bool(reflects_current_order),
        "content_revision_token": content_revision_token,
        "modified": modified_text,
        "revision": revision,
    }


def _reference_entities_from_dxf_read(
    dxf_read: dict[str, Any],
    *,
    snapshot_has_geometry: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    for row in dxf_read.get("unsupported") or []:
        if not isinstance(row, dict):
            continue
        diagnostics.append(
            {
                "code": "UNSUPPORTED_DXF_ENTITY",
                "layer": row.get("layer"),
                "entity_type": row.get("entity_type"),
                "message": _(
                    "An unsupported DXF entity type was skipped for display."
                ),
            }
        )

    for segment in dxf_read.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        key = layer_match_key(segment.get("layer"))
        if snapshot_has_geometry and key in _SNAPSHOT_OWNED_LAYER_KEYS:
            continue
        # CUT_PATH may span many pieces; never bind it by guessing.
        if key == layer_match_key(CUT_PATH_LAYER) or key not in canonical_layer_match_keys():
            references.append(
                {
                    "entity_id": segment.get("entity_id"),
                    "entity_type": segment.get("entity_type"),
                    "layer": segment.get("layer"),
                    "kind": "reference",
                    "reason": (
                        "cut_path_unbound"
                        if key == layer_match_key(CUT_PATH_LAYER)
                        else "designer_or_unaffiliated_layer"
                    ),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "color_source": segment.get("color_source"),
                    "aci_color": segment.get("aci_color"),
                    "linetype_source": segment.get("linetype_source"),
                    "linetype": segment.get("linetype"),
                    "geometry": {
                        "path": [segment.get("start"), segment.get("end")],
                        "closed": False,
                    },
                }
            )
    return references, diagnostics


def _load_scoped_plan_dxf_bytes(order: Any, plan: Any) -> bytes | None:
    """Read DXF bytes only when the File row is scoped to this exact plan.

    The client never supplies ``file_url``. Resolution uses the Cutting Plan row
    already authorized for this order.
    """

    from almdina_erp.almdina_erp.services import dxf_export_service as dxf_export

    if str(getattr(plan, "door_cutting_order", "") or "") != str(order.name):
        return None
    file_url = str(getattr(plan, "dxf_file", "") or "").strip()
    if (
        not file_url.startswith("/private/files/")
        or ".." in file_url
        or not file_url.lower().split("?", 1)[0].endswith(".dxf")
    ):
        return None
    file_row = dxf_export._dxf_file_row(file_url)
    if not file_row:
        return None
    if not cint(file_row.is_private):
        return None
    if (
        str(file_row.attached_to_doctype or "") != "Cutting Plan"
        or str(file_row.attached_to_name or "") != str(plan.name)
        or str(file_row.attached_to_field or "") != "dxf_file"
    ):
        return None
    path = dxf_export._existing_dxf_disk_path(file_url)
    if not path:
        return None
    from pathlib import Path

    return Path(path).read_bytes()


def _uploaded_dxf_enrichment(order: Any, plan: Any) -> dict[str, Any]:
    """Load LAYER table + unbound reference segments from the plan's own file."""

    result: dict[str, Any] = {
        "layer_table": [],
        "reference_entities": [],
        "diagnostics": [],
        "dxf_read": False,
    }
    if not str(getattr(plan, "dxf_file", "") or "").strip():
        result["diagnostics"].append(
            {
                "code": "UPLOADED_DXF_MISSING",
                "message": _("This uploaded plan has no attached DXF file."),
            }
        )
        return result

    content = _load_scoped_plan_dxf_bytes(order, plan)
    if content is None:
        result["diagnostics"].append(
            {
                "code": "UPLOADED_DXF_UNAVAILABLE",
                "message": _(
                    "The original DXF could not be opened for layer display."
                ),
            }
        )
        return result

    try:
        dxf_read = read_dxf_geometry_bytes(content, include_all_layers=True)
    except DxfReadError as exc:
        result["diagnostics"].append(
            {
                "code": str(getattr(exc, "code", "") or "DXF_UNREADABLE"),
                "message": _(
                    "The original DXF could not be parsed for board-editor display."
                ),
                "params": dict(getattr(exc, "params", None) or {}),
            }
        )
        return result

    snapshot = _parse_snapshot(plan)
    snapshot_has_geometry = any(
        isinstance(piece, dict) and isinstance(piece.get("geometry"), dict)
        for sheet in (snapshot.get("sheets") or [])
        if isinstance(sheet, dict)
        for piece in (sheet.get("pieces") or [])
    )
    references, ref_diagnostics = _reference_entities_from_dxf_read(
        dxf_read,
        snapshot_has_geometry=snapshot_has_geometry,
    )
    result["layer_table"] = list(dxf_read.get("layer_defs") or [])
    result["reference_entities"] = references
    result["diagnostics"] = ref_diagnostics
    result["dxf_read"] = True
    return result


@frappe.whitelist()
def get_board_editor_projection(
    order_name: str,
    plan_name: str,
) -> dict[str, Any]:
    """Return the board-editor read model for one explicit order+plan pair.

    The client must pass the selected plan name. This endpoint never switches to
    another source's latest plan and never accepts a client ``file_url``.
    """

    order = _authorized_order(order_name)
    capabilities = _capabilities(order)
    plan = _load_plan_for_order(order, plan_name)
    if not _plan_view_allowed(order, plan, capabilities):
        frappe.throw(
            _("You do not have permission to open this cutting plan in the board editor."),
            frappe.PermissionError,
        )

    snapshot = _enrich_snapshot_allow_rotation(_parse_snapshot(plan), order)
    source_kind = _source_kind_for_plan(order, plan)
    enrichment = {
        "layer_table": [],
        "reference_entities": [],
        "diagnostics": [],
        "dxf_read": False,
    }
    if str(getattr(plan, "source_type", "") or "") == UPLOADED_DXF:
        # System plans derive layers from the operational snapshot only.
        # Uploaded originals may contribute LAYER table + unbound references.
        enrichment = _uploaded_dxf_enrichment(order, plan)

    projection = project_board_editor(
        snapshot,
        source_kind=source_kind,
        layer_table=enrichment["layer_table"],
        reference_entities=enrichment["reference_entities"],
        saw_center_status=str(getattr(plan, "saw_center_status", "") or "") or None,
        default_edge_type=str(getattr(order, "default_edge_type", "") or ""),
    )
    if enrichment["diagnostics"]:
        projection.setdefault("diagnostics", [])
        projection["diagnostics"] = list(projection.get("diagnostics") or []) + list(
            enrichment["diagnostics"]
        )

    freshness = _plan_freshness_payload(order, plan)
    return {
        "order_name": str(order.name),
        "plan": {
            "name": str(plan.name),
            "source_type": str(getattr(plan, "source_type", "") or ""),
            "status": str(getattr(plan, "status", "") or ""),
            "revision": freshness["revision"],
            "modified": freshness["modified"],
            "saw_center_status": str(getattr(plan, "saw_center_status", "") or ""),
            "display_context": freshness["display_context"],
            "input_fingerprint": freshness["input_fingerprint"],
            "content_revision_token": freshness["content_revision_token"],
            "immutable_snapshot": freshness["immutable_snapshot"],
        },
        "freshness": {
            "needs_recalculation": freshness["needs_recalculation"],
            "freshness_state": freshness["freshness_state"],
            "freshness_reason": freshness["freshness_reason"],
            "fingerprint_contract": freshness["fingerprint_contract"],
            "reflects_current_order": freshness["reflects_current_order"],
            "job_active": freshness["job_active"],
            "background_recalculation": freshness["background_recalculation"],
            "content_revision_token": freshness["content_revision_token"],
        },
        "capabilities": {
            "view_cutting_plan": True,
            "view_system": capabilities["view_system"],
            "view_uploaded": capabilities["view_uploaded"],
            "view_approved": capabilities["view_approved"],
        },
        "mode": "view_select_only",
        "projection": projection,
        "meta": {
            "dxf_enrichment_applied": bool(enrichment["dxf_read"]),
            "writes_on_open": False,
            "generates_cut_path_on_open": False,
            "runs_optimizer_on_open": False,
            "mutates_plan_on_read": False,
        },
    }


__all__ = ["get_board_editor_projection"]
