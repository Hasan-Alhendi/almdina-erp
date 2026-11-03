"""Pure helpers for Simulation NC persistence metadata.

Framework-free. File I/O stays in infrastructure; authorization stays in services.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any


def nc_content_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def simulation_nc_filename(
    *,
    order_name: str,
    cutting_plan: str,
    plan_revision: int,
    sheet_no: int,
    content_sha256: str,
) -> str:
    """Build a unique private simulation NC filename."""

    digest = str(content_sha256 or "")[:12] or "empty"
    parts = [
        _safe_token(order_name, "order"),
        _safe_token(cutting_plan, "plan"),
        f"r{int(plan_revision)}",
        f"sheet{int(sheet_no)}",
        digest,
    ]
    return f"{'_'.join(parts)}.sim.nc"


def freeze_preset(values: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(values or {})
    return {
        "preset_name": str(raw.get("preset_name") or raw.get("name") or ""),
        "tool_name": str(raw.get("tool_name") or ""),
        "tool_number": str(raw.get("tool_number") or ""),
        "tool_diameter_mm": raw.get("tool_diameter_mm"),
        "final_depth_mm": raw.get("final_depth_mm"),
        "spindle_speed_rpm": raw.get("spindle_speed_rpm"),
        "feed_rate_mm_min": raw.get("feed_rate_mm_min"),
        "plunge_rate_mm_min": raw.get("plunge_rate_mm_min"),
        "pass_depth_mm": raw.get("pass_depth_mm"),
        "enabled": bool(raw.get("enabled", True)),
    }


def build_generation_snapshot(
    *,
    order_name: str,
    cutting_plan: str,
    plan_revision: int,
    plan_source_type: str,
    sheet_no: int,
    settings_fingerprint: str,
    operation_presets: Mapping[str, Any],
    path_overrides: Mapping[str, Any],
    operation_order: Sequence[str],
    cut_path_early_confirmed: bool,
    known_presets: Mapping[str, Mapping[str, Any]],
    machine_profile: Mapping[str, Any],
    package: Mapping[str, Any],
    program: Mapping[str, Any] | None = None,
    previous_generated_file: str = "",
    generated_by: str = "",
    generated_on: str = "",
    perimeter_join_mode: str = "separate",
    cut_path_sequence: Sequence[str] | None = None,
    perimeter_cut_early_confirmed: bool = False,
) -> dict[str, Any]:
    """Freeze the machining setup that produced a Simulation NC file."""

    layers: dict[str, Any] = {}
    for key, preset_name in dict(operation_presets or {}).items():
        name = str(preset_name or "").strip()
        layers[str(key)] = {
            "tool_preset": name,
            "values": freeze_preset(known_presets.get(name)),
        }
    paths: dict[str, Any] = {}
    for key, preset_name in dict(path_overrides or {}).items():
        name = str(preset_name or "").strip()
        if not name:
            continue
        paths[str(key)] = {
            "tool_preset": name,
            "values": freeze_preset(known_presets.get(name)),
        }
    verification = dict(package.get("verification") or {})
    text = str(package.get("text") or "")
    content_hash = str(package.get("content_sha256") or nc_content_sha256(text))
    tool_number = str(package.get("tool_number") or "")
    tool_diameter = None
    for layer in layers.values():
        values = layer.get("values") or {}
        if values.get("tool_number") == tool_number or not tool_number:
            tool_diameter = values.get("tool_diameter_mm")
            if tool_diameter is not None:
                break
    return {
        "door_cutting_order": str(order_name),
        "cutting_plan": str(cutting_plan),
        "plan_revision": int(plan_revision),
        "plan_source_type": str(plan_source_type or ""),
        "sheet_no": int(sheet_no),
        "settings_fingerprint": str(settings_fingerprint),
        "operation_order": [str(item) for item in operation_order],
        "cut_path_early_confirmed": bool(cut_path_early_confirmed),
        "perimeter_join_mode": str(perimeter_join_mode or "separate"),
        "cut_path_sequence": [str(item) for item in (cut_path_sequence or ())],
        "perimeter_cut_early_confirmed": bool(perimeter_cut_early_confirmed),
        "layer_presets": layers,
        "path_overrides": paths,
        "machine_profile": dict(machine_profile or {}),
        "post_processor_version": str(package.get("post_processor_version") or ""),
        "dialect": str(package.get("dialect") or ""),
        "file_kind": "simulation",
        "production": False,
        "tool_number": tool_number,
        "tool_diameter_mm": tool_diameter,
        "content_sha256": content_hash,
        "verification_ok": bool(verification.get("ok")),
        "verification": verification,
        "geometry_ready": bool((program or {}).get("geometry_ready", True)),
        "machine_ready": False,
        "path_count": package.get("path_count"),
        "pass_count": package.get("pass_count"),
        "previous_generated_file": str(previous_generated_file or ""),
        "generated_by": str(generated_by or ""),
        "generated_on": str(generated_on or ""),
    }


def _safe_token(value: Any, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    text = text.strip("-._")
    return text[:48] or fallback


__all__ = [
    "build_generation_snapshot",
    "freeze_preset",
    "nc_content_sha256",
    "simulation_nc_filename",
]
