"""Build a simulation NC package from a geometry-ready sheet program."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.nc_interpreter import (
    verification_payload,
    verify_nc_against_program,
)
from almdina_erp.almdina_erp.domain.cnc.placement import (
    PlacementError,
    SheetPlacement,
    apply_placement_to_program,
)
from almdina_erp.almdina_erp.domain.cnc.post_processor import (
    POST_PROCESSOR_VERSION,
    PostProcessorError,
    emit_nc,
    nc_payload,
)
from almdina_erp.almdina_erp.domain.cnc.post_processors import (
    IMA_WH_ID,
    emit_ima_wh,
    resolve_post_processor,
)


def build_simulation_nc(
    program: Mapping[str, Any],
    *,
    machine_profile: Mapping[str, Any] | None = None,
    sheet_no: int | None = None,
    settings_fingerprint: str = "",
    sheet_placement: SheetPlacement | None = None,
) -> dict[str, Any]:
    """Return NC text plus an independent verification result.

    Sheet-local geometry stays unchanged on ``program``. When placement is
    supplied, XY is translated once into G54: physical stops, then the
    work-zero origin. The post processor does not apply that shift again.
    """

    if not program.get("geometry_ready", program.get("ready")):
        raise PostProcessorError("geometry_not_ready")
    if not program.get("nc_export_ready", program.get("geometry_ready", program.get("ready"))):
        raise PostProcessorError("geometry_not_ready")
    emit_program: Mapping[str, Any] = program
    placement_payload: dict[str, Any] = {}
    if sheet_placement is not None:
        try:
            emit_program = apply_placement_to_program(program, sheet_placement)
            placement_payload = dict(emit_program.get("placement") or {})
        except PlacementError as exc:
            raise PostProcessorError(exc.code) from exc
    document = emit_nc(
        emit_program,
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
    verification = verify_nc_against_program(document.text, emit_program, safe_z_mm=safe_z)
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
    payload["sheet_placement"] = placement_payload
    payload["coordinate_space"] = str(emit_program.get("coordinate_space") or "")
    return payload


def build_post_processed_nc(
    program: Mapping[str, Any],
    *,
    post_processor_id: str,
    sheet_placement: SheetPlacement | None,
    sheet_no: int | None = None,
    settings_fingerprint: str = "",
) -> dict[str, Any]:
    """Post a sheet with the selected processor and verify the cutter motions.

    The simulation emitter is not used when the processor is missing or unknown.
    Sheet settings and the NC text are not stored by this function.
    """

    processor = resolve_post_processor(post_processor_id, required=True)
    if not program.get("geometry_ready", program.get("ready")):
        raise PostProcessorError("geometry_not_ready")
    if not program.get("nc_export_ready", program.get("geometry_ready", program.get("ready"))):
        raise PostProcessorError("geometry_not_ready")
    if sheet_placement is None:
        raise PostProcessorError("placement_incomplete")
    try:
        emit_program = apply_placement_to_program(program, sheet_placement)
    except PlacementError as exc:
        raise PostProcessorError(exc.code) from exc
    if processor == IMA_WH_ID:
        document = emit_ima_wh(
            emit_program,
            machine_width_mm=sheet_placement.machine_width_mm,
            machine_length_mm=sheet_placement.machine_length_mm,
        )
    else:
        raise PostProcessorError("post_processor_unsupported")
    verification = verify_nc_against_program(document.text, emit_program, safe_z_mm=20.0)
    if not verification.ok:
        raise PostProcessorError("nc_verification_failed")
    payload = nc_payload(document)
    payload["verification"] = verification_payload(verification)
    payload["geometry_ready"] = True
    payload["machine_ready"] = False
    payload["nc_export_ready"] = True
    payload["production"] = False
    payload["machine_coordinate_transform_unverified"] = True
    payload["settings_fingerprint"] = str(settings_fingerprint or "")
    payload["post_processor"] = processor
    payload["post_processor_version"] = document.post_processor_version
    payload["sheet_no"] = sheet_no
    payload["sheet_placement"] = dict(emit_program.get("placement") or {})
    payload["coordinate_space"] = str(emit_program.get("coordinate_space") or "")
    return payload


__all__ = ["build_post_processed_nc", "build_simulation_nc"]
