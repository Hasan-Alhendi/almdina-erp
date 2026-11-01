"""Build a simulation NC package from a geometry-ready sheet program."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.nc_interpreter import (
    verification_payload,
    verify_nc_against_program,
)
from almdina_erp.almdina_erp.domain.cnc.post_processor import (
    POST_PROCESSOR_VERSION,
    PostProcessorError,
    emit_nc,
    nc_payload,
)


def build_simulation_nc(
    program: Mapping[str, Any],
    *,
    machine_profile: Mapping[str, Any] | None = None,
    sheet_no: int | None = None,
    settings_fingerprint: str = "",
) -> dict[str, Any]:
    """Return NC text plus an independent verification result."""

    if not program.get("geometry_ready", program.get("ready")):
        raise PostProcessorError("geometry_not_ready")
    if not program.get("nc_export_ready", program.get("geometry_ready", program.get("ready"))):
        raise PostProcessorError("geometry_not_ready")
    document = emit_nc(
        program,
        machine_profile=machine_profile,
        sheet_label=str(sheet_no or program.get("sheet_no") or ""),
    )
    safe_z = 20.0
    if isinstance(machine_profile, Mapping):
        try:
            safe_z = float(
                machine_profile.get("retract_z_mm", machine_profile.get("cnc_machine_retract_z_mm", 20.0))
            )
        except (TypeError, ValueError):
            safe_z = 20.0
    verification = verify_nc_against_program(document.text, program, safe_z_mm=safe_z)
    if not verification.ok:
        raise PostProcessorError("nc_verification_failed")
    payload = nc_payload(document)
    payload["verification"] = verification_payload(verification)
    payload["geometry_ready"] = True
    payload["machine_ready"] = False
    payload["nc_export_ready"] = True
    payload["production"] = False
    payload["settings_fingerprint"] = str(settings_fingerprint or "")
    payload["post_processor_version"] = POST_PROCESSOR_VERSION
    return payload


__all__ = ["build_simulation_nc"]
