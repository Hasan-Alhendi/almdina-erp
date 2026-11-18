"""Real report adapter/API with an isolated Frappe cache and authorization facts."""

from types import SimpleNamespace
import json

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

import frappe
from almdina_erp.almdina_erp.services import cutting_search_report_service as service
from almdina_erp.almdina_erp.infrastructure.frappe import (
    cutting_plan_authorization as auth,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_search_report_store import (
    FrappeCuttingSearchReportStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_store import (
    FrappeCuttingPlanPreviewStore,
)
from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
    CuttingPlanPreviewSession,
)
from almdina_erp.almdina_erp.application.cutting.search_report import (
    SearchReport,
    fingerprint,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


@pytest.fixture
def runtime(monkeypatch):
    values = {}
    expiry = {}
    session = SimpleNamespace(user="Administrator")
    local = SimpleNamespace(site="isolated.test", response={})
    grants = set()
    visible = {"DCO-TEST"}

    def set_value(key, value, expires_in_sec):
        values[key] = value
        expiry[key] = expires_in_sec

    cache = SimpleNamespace(
        set_value=set_value,
        get_value=lambda key: values.get(key),
        delete_value=lambda key: values.pop(key, None),
    )

    def throw(message, error=ValueError):
        raise error(message)

    def order(name):
        def check_permission(permission):
            if name not in visible:
                raise frappe.PermissionError("outside document scope")

        return SimpleNamespace(
            name=name,
            doctype="Door Cutting Order",
            status="Draft",
            check_permission=check_permission,
            is_new=lambda: False,
        )

    monkeypatch.setattr(frappe, "cache", cache, raising=False)
    monkeypatch.setattr(frappe, "session", session, raising=False)
    monkeypatch.setattr(frappe, "local", local, raising=False)
    monkeypatch.setattr(frappe, "throw", throw)
    monkeypatch.setattr(
        frappe, "get_doc", lambda doctype, name: order(name), raising=False
    )
    monkeypatch.setattr(
        frappe,
        "has_permission",
        lambda doc, *args, **kwargs: doc.name in visible,
        raising=False,
    )
    monkeypatch.setattr(
        auth,
        "doctype_has_capability",
        lambda capability, **kwargs: capability in grants,
    )
    monkeypatch.setattr(service, "_git_sha", lambda: "test-sha")
    return SimpleNamespace(
        values=values,
        expiry=expiry,
        session=session,
        local=local,
        grants=grants,
        visible=visible,
        order=order,
    )


def saved_report(runtime):
    report = SearchReport()
    preview = CuttingPlanPreviewSession(
        "preview",
        "DCO-TEST",
        runtime.session.user,
        "CP",
        "v1",
        "input",
        "settings",
        {},
        dict(engine_version="test"),
        "now",
        search_report_id=report.metadata["report_id"],
    )
    data = report.export()
    FrappeCuttingSearchReportStore().put(
        data, order_name=preview.order_name, user=preview.user
    )
    FrappeCuttingPlanPreviewStore().put(preview)
    return data, preview


def test_administrator_downloads_same_data_after_exact_token_consumption(runtime):
    data, preview = saved_report(runtime)
    assert FrappeCuttingPlanPreviewStore().consume(preview.preview_id)
    for format in ("json", "html"):
        service.download_cutting_search_report("DCO-TEST", data["report_id"], format)
        content = runtime.local.response["filecontent"].decode("utf-8")
        assert data["data_fingerprint"] in content
        assert data["report_id"] in content
        assert runtime.local.response["display_content_as"] == "attachment"
    assert all(ttl in {900, 86400} for ttl in runtime.expiry.values())
    assert all("public" not in key for key in runtime.values)


def test_explicit_grant_is_required_on_every_direct_download(runtime):
    runtime.session.user = "operator"
    runtime.grants.update(
        {Capability.DOWNLOAD_CUTTING_SEARCH_REPORT, Capability.VIEW_SYSTEM_CUTTING_PLAN}
    )
    data, _ = saved_report(runtime)
    service.download_cutting_search_report("DCO-TEST", data["report_id"])
    runtime.grants.remove(Capability.DOWNLOAD_CUTTING_SEARCH_REPORT)
    with pytest.raises(frappe.PermissionError):
        service.download_cutting_search_report("DCO-TEST", data["report_id"])
    runtime.grants.add(Capability.DOWNLOAD_CUTTING_SEARCH_REPORT)
    runtime.grants.remove(Capability.VIEW_SYSTEM_CUTTING_PLAN)
    with pytest.raises(frappe.PermissionError):
        service.download_cutting_search_report("DCO-TEST", data["report_id"])


@pytest.mark.parametrize(
    "boundary", ["user", "site", "order", "scope", "format", "id", "expiry"]
)
def test_download_fails_closed_across_boundaries(runtime, monkeypatch, boundary):
    data, _ = saved_report(runtime)
    report_id = data["report_id"]
    order = "DCO-TEST"
    format = "json"
    if boundary == "user":
        runtime.session.user = "different"
        runtime.grants.update(
            {
                Capability.DOWNLOAD_CUTTING_SEARCH_REPORT,
                Capability.VIEW_SYSTEM_CUTTING_PLAN,
            }
        )
    elif boundary == "site":
        runtime.local.site = "other.test"
    elif boundary == "order":
        order = "OTHER"
        runtime.visible.add(order)
    elif boundary == "scope":
        runtime.visible.clear()
    elif boundary == "format":
        format = "../../public/files/report.html"
    elif boundary == "id":
        report_id = "../other"
    else:
        from almdina_erp.almdina_erp.infrastructure.frappe import (
            cutting_search_report_store,
        )

        monkeypatch.setattr(
            cutting_search_report_store.time, "time", lambda: float("inf")
        )
    with pytest.raises((frappe.PermissionError, frappe.ValidationError)):
        service.download_cutting_search_report(order, report_id, format)


def test_continuation_embeds_the_previous_round_and_keeps_parent_downloadable(runtime):
    data, previous = saved_report(runtime)
    report = service.create_search_report(
        runtime.order("DCO-TEST"), {}, previous=previous
    )
    child = report.export()
    assert child["parent_run_id"] == data["run_id"]
    assert child["round_id"] == 1
    assert child["previous_round"] == data
    assert (
        FrappeCuttingSearchReportStore().get(
            data["report_id"], order_name="DCO-TEST", user="Administrator"
        )
        == data
    )


def test_new_capability_has_no_default_grant_and_does_not_grant_recalculation():
    from almdina_erp.almdina_erp.application.security.permission_matrix import (
        normalize_capability_state,
    )

    state = normalize_capability_state(
        {Capability.DOWNLOAD_CUTTING_SEARCH_REPORT: True}
    )
    assert state[Capability.VIEW_SYSTEM_CUTTING_PLAN]
    assert not state[Capability.RECALCULATE_PLAN]
    assert not normalize_capability_state({})[Capability.DOWNLOAD_CUTTING_SEARCH_REPORT]


def test_corrupt_artifact_is_unavailable(runtime):
    data, _ = saved_report(runtime)
    key = FrappeCuttingSearchReportStore()._key(data["report_id"])
    runtime.values[key] = b"corrupt compressed content"
    with pytest.raises(frappe.PermissionError):
        service.download_cutting_search_report("DCO-TEST", data["report_id"])


def test_report_storage_failure_keeps_the_exact_preview_and_discloses_loss(
    runtime, monkeypatch
):
    _, session = saved_report(runtime)
    from dataclasses import replace

    session = replace(session, search_report_id="")
    messages = []
    monkeypatch.setattr(frappe, "log_error", lambda **kwargs: None, raising=False)
    monkeypatch.setattr(frappe, "msgprint", messages.append, raising=False)

    def fail(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(FrappeCuttingSearchReportStore, "put", fail)
    assert service.finish_search_report(SearchReport(), session) is session
    assert len(messages) == 1
    assert "preview is still available" in messages[0]


def test_finish_publishes_exact_preview_gallery_and_keeps_snapshot_clean(runtime):
    from dataclasses import replace
    from copy import deepcopy
    from almdina_erp.almdina_erp.domain.cutting import optimizer
    from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    from almdina_erp.almdina_erp.domain.cutting.search_trace import observe_search

    report = service.create_search_report(runtime.order("DCO-TEST"), {})
    with observe_search(report):
        plan = optimizer.auto_fast(
            expand_piece_groups([dict(width_cm=20, length_cm=30, qty=2)]), 100, 100, 0.3
        )
    _, session = saved_report(runtime)
    entry = dict(
        candidate_id="preview-candidate",
        snapshot=plan,
        geometry_fingerprint=geometry_signature(plan),
    )
    session = replace(session, snapshot=plan, candidates={"preview-candidate": entry})
    original = deepcopy(plan)
    updated = service.finish_search_report(report, session)
    data = FrappeCuttingSearchReportStore().get(
        updated.search_report_id, order_name="DCO-TEST", user="Administrator"
    )
    assert data["preview_gallery"] == [
        dict(
            preview_candidate_id="preview-candidate",
            geometry_fingerprint=geometry_signature(plan),
        )
    ]
    assert [c["geometry_fingerprint"] for c in data["final_gallery"]] == [
        geometry_signature(plan)
    ]
    assert plan == original
    assert "search_report_id" not in plan
