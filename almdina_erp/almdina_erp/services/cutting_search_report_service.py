"""Authorized creation/download boundary for disposable search evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.search_report import (
    SearchReport,
    canonical_json,
    json_value,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_store import (
    FrappeCuttingPlanPreviewStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_search_report_store import (
    FrappeCuttingSearchReportStore,
    REPORT_TTL_SECONDS,
)


def require_search_report_access(order):
    order.check_permission("read")
    require_cutting_plan_capability(order, Capability.DOWNLOAD_CUTTING_SEARCH_REPORT)
    require_cutting_plan_capability(order, Capability.VIEW_SYSTEM_CUTTING_PLAN)


def _git_sha():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def create_search_report(order, settings, *, previous=None):
    require_search_report_access(order)
    parent = None
    if previous and previous.search_report_id:
        parent = FrappeCuttingSearchReportStore().get(
            previous.search_report_id, order_name=order.name, user=frappe.session.user
        )
    report = SearchReport(
        parent_run_id=parent["run_id"] if parent else None,
        round_id=previous.search_round + 1 if previous else 0,
        git_sha=_git_sha(),
    )
    report.metadata["effective_settings"] = json_value(settings)
    if not report.metadata["git_sha"]:
        report.coverage["limitations"].append(
            "The deployed Git revision could not be resolved."
        )
    if previous:
        report.metadata["previous_report_id"] = previous.search_report_id
        if parent:
            report.metadata["previous_round"] = parent
        else:
            report.coverage["limitations"].append(
                "Previous round evidence was not recorded or has expired."
            )
    return report


def finish_search_report(report, session):
    if report is None:
        return session
    try:
        return _store_finished_report(report, session)
    except Exception:
        # Diagnostics are disposable. A failed observer/store cannot discard an
        # already validated preview; disclose failure and keep its exact token.
        frappe.log_error(title="Cutting search report persistence failed")
        frappe.msgprint(
            _(
                "The search report could not be stored. The cutting plan preview is still available."
            )
        )
        return session


def _store_finished_report(report, session):
    report.metadata.update(
        preview_id=session.preview_id,
        input_fingerprint=session.input_fingerprint,
        settings_fingerprint=session.settings_fingerprint,
        engine_version=str(session.snapshot.get("engine_version") or ""),
    )
    report.gallery(
        [],
        [c["snapshot"] for c in session.candidates.values()],
        "published_preview",
        preview_candidate_ids=list(session.candidates),
    )
    # Exact server-owned geometry identities, in the visible preview order.
    report.metadata["preview_gallery"] = [
        dict(
            preview_candidate_id=c["candidate_id"],
            geometry_fingerprint=c["geometry_fingerprint"],
        )
        for c in session.candidates.values()
    ]
    data = report.export()
    FrappeCuttingSearchReportStore().put(
        data, order_name=session.order_name, user=session.user
    )
    updated = replace(session, search_report_id=data["report_id"])
    FrappeCuttingPlanPreviewStore().put(updated)
    return updated


@frappe.whitelist()
def download_cutting_search_report(
    order_name: str, report_id: str, format: str = "json"
):
    order = frappe.get_doc("Door Cutting Order", str(order_name or "").strip())
    require_search_report_access(order)
    if format not in {"json", "html"}:
        frappe.throw(_("Invalid search report format."), frappe.ValidationError)
    data = FrappeCuttingSearchReportStore().get(
        report_id, order_name=order.name, user=frappe.session.user
    )
    if data is None:
        frappe.throw(
            _("The search report is unavailable or has expired."),
            frappe.PermissionError,
        )
    if format == "html":
        from almdina_erp.almdina_erp.presentation.cutting.search_report_html import (
            render_search_report,
        )

        content = render_search_report(data)
    else:
        content = canonical_json(data)
    frappe.local.response.update(
        type="download",
        filename=f'cutting-search-{data["report_id"]}.{format}',
        filecontent=content.encode("utf-8"),
        display_content_as="attachment",
        content_type=(
            "text/html; charset=utf-8"
            if format == "html"
            else "application/json; charset=utf-8"
        ),
    )
