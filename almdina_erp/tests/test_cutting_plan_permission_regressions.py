from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import frappe
import pytest

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services import (
    cutting_plan_snapshot_service,
    drawing_approval_service,
    dual_plan_fields,
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
        raise AssertionError("A current valid System plan must not full-save the order")


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
        "require_document_capability",
        lambda _doc, capability, **_kwargs: capability_checks.append(capability),
    )

    applied = order_plan_permission_service._apply_optimizer_updates(
        old,
        {"kerf_mm": 4.0, "trim_margin_mm": 6.0},
    )

    assert applied == ["kerf_mm", "trim_margin_mm"]
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


def test_dxf_upload_authorizes_and_validates_before_attachment(monkeypatch):
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
        production_dxf="",
    )

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
        strict_dxf_import_service,
        "parse_production_dxf",
        lambda file_url, current: events.append("validated")
        or frappe.parse_json(VALID_PLAN_JSON),
    )
    monkeypatch.setattr(
        shop_floor_dxf_service,
        "_attach_validated_dxf_file",
        lambda current, staged: events.append("attached"),
    )
    monkeypatch.setattr(dual_plan_fields, "has_dual_plan_field", lambda _field: True)
    monkeypatch.setattr(
        shop_floor_dxf_service.frappe.db,
        "set_value",
        lambda *args, **kwargs: None,
    )

    result = shop_floor_dxf_service.upload_production_dxf(
        "DCO-TEST",
        "/private/files/production-plan.dxf",
    )

    assert events == ["staged", "authorized", "validated", "attached"]
    assert result["production_dxf"] == "/private/files/production-plan.dxf"


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


@pytest.mark.parametrize(
    ("needs_recalculation", "plan_json"),
    [(1, VALID_PLAN_JSON), (0, "")],
    ids=["stale", "missing"],
)
def test_approve_dxf_rejects_stale_or_missing_system_plan(
    monkeypatch,
    needs_recalculation,
    plan_json,
):
    order = _UploadOrder(
        name="DCO-TEST",
        status="At Drawing",
        production_path="Drawing",
        current_department="رسم",
        approved_plan="",
        production_dxf="",
        plan_needs_recalculation=needs_recalculation,
        cutting_plan_json=plan_json,
    )

    monkeypatch.setattr(
        drawing_approval_service,
        "_authorized_order",
        lambda _name: order,
    )
    monkeypatch.setattr(
        drawing_approval_service,
        "validate_plan_source",
        lambda *args, **kwargs: "System",
    )
    monkeypatch.setattr(
        dual_plan_fields,
        "get_system_plan_json",
        lambda _order: plan_json,
    )
    monkeypatch.setattr(dual_plan_fields, "get_custom_plan_json", lambda _order: "")
    monkeypatch.setattr(
        drawing_approval_service,
        "lock_order_for_production",
        lambda *args, **kwargs: pytest.fail(
            "stale or missing System plan must be rejected before locking"
        ),
    )

    with pytest.raises(frappe.ValidationError):
        drawing_approval_service.approve_production_dxf(
            "DCO-TEST",
            plan_source="System",
        )


def test_current_valid_system_plan_approval_does_not_full_save_order(monkeypatch):
    order = _ApprovalOrder(
        name="DCO-TEST",
        plan_needs_recalculation=0,
        cutting_plan_json=VALID_PLAN_JSON,
        system_plan_json=VALID_PLAN_JSON,
        drawing_dxf_status="Uploaded",
    )
    plan = SimpleNamespace(
        name="CUT-PLAN-TEST",
        revision=1,
        snapshot_json=VALID_PLAN_JSON,
        required_boards=1,
        waste_area_m2=0,
        waste_percent=0,
        mdf_cost_usd=0,
        cutting_cost_usd=0,
        edge_cost_usd=0,
        total_cost_usd=0,
        method_label="Auto",
    )

    monkeypatch.setattr(
        cutting_plan_snapshot_service,
        "create_plan_from_order",
        lambda *args, **kwargs: plan,
    )
    monkeypatch.setattr(
        cutting_plan_snapshot_service,
        "approve_plan",
        lambda current: current,
    )
    monkeypatch.setattr(
        dual_plan_fields,
        "get_system_plan_json",
        lambda _order: VALID_PLAN_JSON,
    )
    monkeypatch.setattr(dual_plan_fields, "has_dual_plan_field", lambda _field: True)
    monkeypatch.setattr(
        cutting_plan_snapshot_service.frappe.db,
        "set_value",
        lambda *args, **kwargs: None,
    )

    result = cutting_plan_snapshot_service.lock_order_for_production(
        order,
        preserve_status=True,
        plan_source="System",
    )

    assert result["cutting_plan"] == "CUT-PLAN-TEST"
