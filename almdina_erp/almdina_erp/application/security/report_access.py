from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.security.authorization import (
    Capability,
    normalize_capabilities,
)


@dataclass(frozen=True, slots=True)
class ReportAccess:
    operational: bool
    financial: bool


def build_report_access(
    capabilities: set[str] | frozenset[str] | tuple[str, ...] | list[str],
) -> ReportAccess:
    granted = normalize_capabilities(capabilities)
    financial = (
        Capability.VIEW_FINANCIAL_REPORTS in granted
        and Capability.VIEW_COSTS in granted
    )
    operational = Capability.VIEW_OPERATIONAL_REPORTS in granted or financial
    return ReportAccess(operational=operational, financial=financial)


__all__ = ["ReportAccess", "build_report_access"]
