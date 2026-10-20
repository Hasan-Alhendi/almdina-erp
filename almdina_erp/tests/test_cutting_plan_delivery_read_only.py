from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_authorization
from almdina_erp.almdina_erp.services import (
    cutting_plan_workspace_query_service,
    dxf_export_service,
)


def _order(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        name="DCO-2026-00018",
        doctype="Door Cutting Order",
        status=status,
        is_new=lambda: False,
    )


@pytest.mark.parametrize("actor", ["Administrator", "designer@example.test"])
def test_delivery_locks_all_plan_mutations_but_keeps_authorized_download(actor):
    permitted = cutting_plan_authorization.cutting_plan_capability_allowed
    with (
        patch.object(cutting_plan_authorization, "doctype_has_capability", return_value=True),
        patch.object(cutting_plan_authorization.frappe, "has_permission", return_value=True),
    ):
        for capability in cutting_plan_authorization._DELIVERED_PLAN_MUTATIONS:
            assert permitted(_order("Draft"), capability, user=actor)
            assert not permitted(_order("Delivered"), capability, user=actor)
        for capability in (
            Capability.EXPORT_DXF,
            Capability.VIEW_SYSTEM_CUTTING_PLAN,
            Capability.VIEW_UPLOADED_CUTTING_PLAN,
            Capability.VIEW_APPROVED_CUTTING_PLAN,
        ):
            assert permitted(_order("Delivered"), capability, user=actor)


def test_delivered_plan_download_does_not_bypass_read_permission():
    with (
        patch.object(cutting_plan_authorization, "doctype_has_capability", return_value=True),
        patch.object(cutting_plan_authorization.frappe, "has_permission", return_value=False),
    ):
        assert not cutting_plan_authorization.cutting_plan_capability_allowed(
            _order("Delivered"), Capability.EXPORT_DXF, user="unrelated@example.test"
        )


def test_system_plan_remains_selected_after_approval_or_supersession():
    rows = [
        {"name": "UPLOADED", "source_type": "Uploaded DXF", "status": "Approved"},
        {"name": "SYSTEM-2", "source_type": "System", "status": "Superseded"},
        {"name": "SYSTEM-1", "source_type": "System", "status": "Approved"},
    ]
    assert cutting_plan_workspace_query_service._system_plan(rows)["name"] == "SYSTEM-2"
    rows.insert(0, {"name": "SYSTEM-DRAFT", "source_type": "System", "status": "Draft"})
    assert cutting_plan_workspace_query_service._system_plan(rows)["name"] == "SYSTEM-DRAFT"


def test_export_uses_saved_system_revision_when_no_draft_remains():
    approved = SimpleNamespace(name="SYSTEM-APPROVED", source_type="System", status="Approved")
    with patch.object(dxf_export_service, "latest_plan", side_effect=[None, approved]) as fetch:
        selected = dxf_export_service._saved_plan_for_source(_order("Delivered"), "System")
    assert selected is approved
    assert fetch.call_count == 2
    assert fetch.call_args_list[0].kwargs["status"] == "Draft"
    assert "status" not in fetch.call_args_list[1].kwargs
