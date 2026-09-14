from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.cutting.system_plan_recalculation_job import (
    JobState,
)


CACHE_PREFIX = "almdina:system-plan-recalc"
DEFAULT_TTL_SECONDS = 30 * 60
REALTIME_EVENT = "almdina_system_plan_recalculation"


class FrappeSystemPlanRecalculationJobStore:
    """Redis/cache adapter for one in-flight System plan recalculation per order."""

    def __init__(self, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds or DEFAULT_TTL_SECONDS))

    @staticmethod
    def key(order_name: str) -> str:
        return f"{CACHE_PREFIX}:{str(order_name or '').strip()}"

    def get(self, order_name: str) -> JobState | None:
        name = str(order_name or "").strip()
        if not name:
            return None
        raw: Any = frappe.cache.get_value(self.key(name))
        if not raw or not isinstance(raw, dict):
            return None
        return JobState.from_cache_value(raw)

    def put(self, state: JobState) -> None:
        frappe.cache.set_value(
            self.key(state.order_name),
            state.as_cache_value(),
            expires_in_sec=self.ttl_seconds,
        )

    def publish(self, state: JobState) -> None:
        frappe.publish_realtime(
            REALTIME_EVENT,
            {
                "order_name": state.order_name,
                "status": state.status,
                "generation": int(state.generation or 0),
            },
            doctype="Door Cutting Order",
            docname=state.order_name,
            after_commit=True,
        )


__all__ = [
    "CACHE_PREFIX",
    "DEFAULT_TTL_SECONDS",
    "FrappeSystemPlanRecalculationJobStore",
    "REALTIME_EVENT",
]
