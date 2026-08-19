from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
    CuttingPlanPreviewSession,
)


DEFAULT_PREVIEW_TTL_SECONDS = 15 * 60
_CACHE_PREFIX = "almdina:cutting-plan-preview"


class FrappeCuttingPlanPreviewStore:
    """Short-lived persistence adapter for trusted optimizer previews.

    Preview sessions deliberately live outside MariaDB: they are disposable UI
    experiments, not Cutting Plan revisions. A successful or rejected commit
    consumes the token, making it single-use and preventing replay.
    """

    def __init__(self, *, ttl_seconds: int = DEFAULT_PREVIEW_TTL_SECONDS):
        self.ttl_seconds = max(60, int(ttl_seconds or DEFAULT_PREVIEW_TTL_SECONDS))

    @staticmethod
    def _key(preview_id: str) -> str:
        return f"{_CACHE_PREFIX}:{str(preview_id or '').strip()}"

    def put(self, session: CuttingPlanPreviewSession) -> None:
        frappe.cache.set_value(
            self._key(session.preview_id),
            session.as_cache_value(),
            expires_in_sec=self.ttl_seconds,
        )

    def get(self, preview_id: str) -> CuttingPlanPreviewSession | None:
        raw: Any = frappe.cache.get_value(self._key(preview_id))
        if not raw or not isinstance(raw, dict):
            return None
        return CuttingPlanPreviewSession.from_cache_value(raw)

    def consume(self, preview_id: str) -> CuttingPlanPreviewSession | None:
        key = self._key(preview_id)
        raw: Any = frappe.cache.get_value(key)
        # Delete before committing. Even a stale or rejected token must not be
        # replayable; the operator can always generate a fresh preview.
        frappe.cache.delete_value(key)
        if not raw or not isinstance(raw, dict):
            return None
        return CuttingPlanPreviewSession.from_cache_value(raw)

    def discard(self, preview_id: str) -> None:
        frappe.cache.delete_value(self._key(preview_id))


__all__ = [
    "DEFAULT_PREVIEW_TTL_SECONDS",
    "FrappeCuttingPlanPreviewStore",
]
