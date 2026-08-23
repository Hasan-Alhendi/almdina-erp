from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import frappe
import pytest

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services import (
    cutting_plan_command_service,
    order_plan_permission_service,
    shop_floor_dxf_service,
    strict_dxf_import_service,
)


APP_ROOT = Path(__file__).resolve().parents[1]
VALID_PLAN_JSON = frappe.as_json(
    {
        "validation": {"is_valid": True, "errors": []},
        "sheets": [{"sheet_no": 1, "pieces": []}],
    }
)


class _PlanInputDoc:
    def __init__(self, **values):
        self._values = dict(values)
        self.current_production_stage = None
        self.production_path = None

    def get(self, fieldname):
        return self._values.get(fieldname)

    def set(self, fieldname, value):
        self._values[fieldname] = value


class _ApprovalOrder(SimpleNamespace):
    def ensure_special_shapes_documented(self):
        return None

    def ensure_special_prices_approved(self):
        return None

    def save(self, *args, **kwargs):
        raise AssertionError("Plan approval must never full-save Door Cutting Order")


class _UploadOrder(SimpleNamespace):
    def add_comment(self, *args, **kwargs):
        return None


def test_kerf_and_trim_are_backend_optimizer_settings(monkeypatch):
    old = _PlanInputDoc(kerf_mm=3.0, trim_margin_mm=5.0)
    current = _PlanInputDoc(kerf_mm=4.0, trim_margin_mm=6.0)

    changed = order_plan_permission_service._optimizer_changes(current, old)
    assert changed == ["kerf_mm", "trim_margin_mm"]

    capability_checks: list[str] = []
    monkeypatch.setattr(
        order_plan_permission_service,
        "require_cutting_plan_capability",
        lambda _doc, capability, **_kwargs: capability_checks.append(capability),
    )

    # Optimizer edits are applied to a transient preview object here. Persisted
    # settings are command-owned by Cutting Plan.
    for fieldname, value in {"kerf_mm": 4.0, "trim_margin_mm": 6.0}.items():
        old.set(fieldname, value)
    order_plan_permission_service.require_cutting_plan_capability(
        old,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        allow_new_order=True,
    )

    assert old.get("kerf_mm") == 4.0
    assert old.get("trim_margin_mm") == 6.0
    assert capability_checks == [Capability.EDIT_OPTIMIZER_SETTINGS]


def test_frontend_optimizer_access_includes_kerf_and_trim():
    source = (
        APP_ROOT
        / "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js"
    ).read_text(encoding="utf-8")
    optimizer_fields = source.split("const OPTIMIZER_FIELDS = [", 1)[1].split("]", 1)[0]

    assert '"kerf_mm"' in optimizer_fields
    assert '"trim_margin_mm"' in optimizer_fields
    assert 'can(frm, "edit_optimizer_settings")' in source


@pytest.mark.parametrize(
    "file_row",
    [
        SimpleNamespace(
            name="FILE-PUBLIC",
            file_size=100,
            is_private=0,
            attached_to_doctype=None,
            attached_to_name=None,
            attached_to_field=None,
        ),
        SimpleNamespace(
            name="FILE-ATTACHED",
            file_size=100,
            is_private=1,
            attached_to_doctype="Door Cutting Order",
            attached_to_name="DCO-TEST",
            attached_to_field="production_dxf",
        ),
    ],
    ids=["public", "already-attached"],
)
def test_dxf_staging_rejects_public_or_preattached_files(monkeypatch, file_row):
    monkeypatch.setattr(
        shop_floor_dxf_service.frappe.db,
        "get_value",
        lambda *args, **kwargs: file_row,
    )

    with pytest.raises(frappe.ValidationError):
        shop_floor_dxf_service._validate_dxf_file_metadata(
            "/private/files/production-plan.dxf"
        )


def test_dxf_upload_authorizes_and_validates_before_canonical_plan_attachment(monkeypatch):
    events: list[str] = []
    file_row = SimpleNamespace(name="FILE-STAGED")
    order = _UploadOrder(
        name="DCO-TEST",
        doctype="Door Cutting Order",
        status="At Drawing",
        production_path="Drawing",
        current_department="رسم",
        current_assignee="designer@example.com",
        approved_plan="",
    )
    plan = SimpleNamespace(
        name="CUT-PLAN-DXF",
        snapshot_json=VALID_PLAN_JSON,
    )
    settings = SimpleNamespace(kerf_mm=4.0, trim_margin_mm=5.0)

    monkeypatch.setattr(
        shop_floor_dxf_service,
        "_validate_dxf_file_metadata",
        lambda file_url: (
            events.append("staged") or str(file_url),
            file_row,
        ),
    )
    monkeypatch.setattr(
        shop_floor_dxf_service.shop_floor_gateway,
        "get_order",
        lambda _name: order,
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "current_uploaded_dxf_file",
        lambda _order_name: "",
    )
    monkeypatch.setattr(
        shop_floor_dxf_service,
        "required_upload_capability",
        lambda _state: Capability.UPLOAD_DXF,
    )
    monkeypatch.setattr(
        shop_floor_dxf_service,
        "_authorize_order",
        lambda current, capability, **kwargs: events.append("authorized") or current,
    )
    monkeypatch.setattr(
        shop_floor_dxf_service,
        "seed_plan_settings",
        lambda _order_name: settings,
    )
    monkeypatch.setattr(
        strict_dxf_import_service,
        "parse_production_dxf",
        lambda file_url, current, *, settings: events.append("validated")
        or frappe.parse_json(VALID_PLAN_JSON),
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "save_uploaded_dxf_plan",
        lambda current, snapshot, file_url, *, capability: events.append("persisted")
        or plan,
    )
    monkeypatch.setattr(
        shop_floor_dxf_service,
        "_attach_validated_dxf_file",
        lambda current_plan, staged: events.append("attached"),
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "finalize_uploaded_dxf_order_state",
        lambda current, current_plan: events.append("finalized"),
    )

    result = shop_floor_dxf_service.upload_production_dxf(
        "DCO-TEST",
        "/private/files/production-plan.dxf",
    )

    assert events == [
        "staged",
        "authorized",
        "validated",
        "persisted",
        "attached",
        "finalized",
    ]
    assert result["cutting_plan"] == "CUT-PLAN-DXF"
    assert result["production_dxf"] == "/private/files/production-plan.dxf"
    assert result["drawing_dxf_status"] == "Uploaded"


def test_frontend_dxf_uploader_is_private_and_unattached():
    uploader_source = (
        APP_ROOT
        / "public/js/door_cutting_order/cutting_plan/secure_dxf_upload.js"
    ).read_text(encoding="utf-8")
    uploader_config = uploader_source.split("new frappe.ui.FileUploader({", 1)[1].split(
        "on_success(file)", 1
    )[0]

    assert "is_private: 1" in uploader_config
    assert "doctype:" not in uploader_config
    assert "docname:" not in uploader_config

    manifest = (APP_ROOT / "frontend_assets.py").read_text(encoding="utf-8")
    assert manifest.index("secure_dxf_upload.js") < manifest.index(
        "door_cutting_order_plan_ux.js"
    )


@pytest.mark.parametrize("case", ["stale", "missing"])
def test_approve_dxf_rejects_stale_or_missing_canonical_system_plan(monkeypatch, case):
    order = _ApprovalOrder(name="DCO-TEST", approved_plan="")
    stale_plan = SimpleNamespace(
        name="CUT-PLAN-STALE",
        status="Draft",
        validation_status="Valid",
        snapshot_json=VALID_PLAN_JSON,
        plan_needs_recalculation=1,
        cost_snapshot_version=999,
        source_type="System",
    )

    class _Repository:
        def latest_document(self, *args, **kwargs):
            return None if case == "missing" else stale_plan

    monkeypatch.setattr(
        cutting_plan_command_service,
        "require_cutting_plan_capability",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "FrappeCuttingPlanCommandRepository",
        lambda _capability: _Repository(),
    )

    with pytest.raises(frappe.ValidationError):
        cutting_plan_command_service.approve_order_plan(order, "System")


def test_current_valid_system_plan_approval_does_not_full_save_order(monkeypatch):
    order = _ApprovalOrder(name="DCO-TEST", approved_plan="")
    plan = SimpleNamespace(
        name="CUT-PLAN-TEST",
        revision=1,
        source_type="System",
        status="Draft",
        validation_status="Valid",
        snapshot_json=VALID_PLAN_JSON,
        plan_needs_recalculation=0,
        cost_snapshot_version=999,
    )
    saved: list[tuple[str, bool]] = []

    class _Repository:
        def latest_document(self, *args, **kwargs):
            return plan

        def approved_documents(self, *args, **kwargs):
            return []

        def save_document(self, current, *, allow_status_transition=False):
            saved.append((current.name, allow_status_transition))
            return current

    monkeypatch.setattr(
        cutting_plan_command_service,
        "require_cutting_plan_capability",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "FrappeCuttingPlanCommandRepository",
        lambda _capability: _Repository(),
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "_assert_plan_ready_for_approval",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "_set_approved_plan_relation",
        lambda current_order, current_plan: setattr(
            current_order, "approved_plan", current_plan.name
        ),
    )
    monkeypatch.setattr(
        cutting_plan_command_service,
        "refresh_order_commercial_totals",
        lambda *args, **kwargs: None,
    )

    result = cutting_plan_command_service.approve_order_plan(order, "System")

    assert result["cutting_plan"] == "CUT-PLAN-TEST"
    assert result["approved_plan_source"] == "System"
    assert order.approved_plan == "CUT-PLAN-TEST"
    assert plan.status == "Approved"
    assert saved == [("CUT-PLAN-TEST", True)]
