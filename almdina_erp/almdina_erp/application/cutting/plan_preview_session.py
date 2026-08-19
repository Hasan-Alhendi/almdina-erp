from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload


PREVIEW_SESSION_VERSION = 1


def optimizer_settings_fingerprint(settings: Mapping[str, Any]) -> str:
    """Fingerprint one normalized optimizer-settings draft deterministically."""

    return fingerprint_payload(
        {
            "version": 1,
            "settings": {
                "packing_mode": str(settings.get("packing_mode") or "").strip(),
                "cutting_machine_type": str(
                    settings.get("cutting_machine_type") or ""
                ).strip(),
                "kerf_mm": float(settings.get("kerf_mm") or 0),
                "trim_margin_mm": float(settings.get("trim_margin_mm") or 0),
                "optimization_time_limit_sec": float(
                    settings.get("optimization_time_limit_sec") or 0
                ),
            },
        }
    )


@dataclass(frozen=True, slots=True)
class CuttingPlanPreviewSession:
    """Trusted, temporary result of one optimizer preview.

    The browser receives only ``preview_id`` plus a safe presentation DTO. The
    exact snapshot kept here is the server-owned artifact that can later be
    committed without running the optimizer a second time.
    """

    preview_id: str
    order_name: str
    user: str
    source_plan_name: str
    source_plan_modified: str
    input_fingerprint: str
    settings_fingerprint: str
    settings: dict[str, Any]
    snapshot: dict[str, Any]
    created_at: str
    version: int = PREVIEW_SESSION_VERSION

    def as_cache_value(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_cache_value(cls, value: Mapping[str, Any]) -> "CuttingPlanPreviewSession":
        return cls(
            version=int(value.get("version") or PREVIEW_SESSION_VERSION),
            preview_id=str(value.get("preview_id") or ""),
            order_name=str(value.get("order_name") or ""),
            user=str(value.get("user") or ""),
            source_plan_name=str(value.get("source_plan_name") or ""),
            source_plan_modified=str(value.get("source_plan_modified") or ""),
            input_fingerprint=str(value.get("input_fingerprint") or ""),
            settings_fingerprint=str(value.get("settings_fingerprint") or ""),
            settings=dict(value.get("settings") or {}),
            snapshot=dict(value.get("snapshot") or {}),
            created_at=str(value.get("created_at") or ""),
        )


__all__ = [
    "PREVIEW_SESSION_VERSION",
    "CuttingPlanPreviewSession",
    "optimizer_settings_fingerprint",
]
