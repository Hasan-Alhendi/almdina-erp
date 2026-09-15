"""Pure DXF normalization primitives for the AutoCAD export boundary."""

from __future__ import annotations

import io
from typing import Any


AUTOCAD_DXF_VERSION = "AC1024"


def canonical_dxf_text(raw: bytes) -> str:
    """Decode the bounded ASCII DXF and normalize all line endings."""
    text = raw.decode("ascii")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def assert_single_dxf_document(content: str) -> None:
    lines = content.splitlines()
    header_sections = sum(
        1
        for index, value in enumerate(lines[:-2])
        if value.strip() == "SECTION" and lines[index + 2].strip() == "HEADER"
    )
    eof_markers = sum(1 for value in lines if value.strip() == "EOF")
    if header_sections != 1 or eof_markers != 1:
        raise ValueError("DXF serialization produced multiple document bodies.")


def rebuild_autocad_dxf(raw: bytes, ezdxf_module: Any | None = None) -> bytes:
    """Rebuild LINE-only client geometry as a canonical AutoCAD 2010 document."""
    if ezdxf_module is None:
        import ezdxf as ezdxf_module

    source_document = ezdxf_module.read(io.StringIO(canonical_dxf_text(raw)))
    source_entities = list(source_document.modelspace())
    if not source_entities or any(entity.dxftype() != "LINE" for entity in source_entities):
        raise ValueError("The client DXF must contain LINE entities only.")

    target_document = ezdxf_module.new("R2010", setup=True)
    target_document.units = 4
    target_modelspace = target_document.modelspace()

    used_layers = {str(entity.dxf.layer or "0") for entity in source_entities}
    for layer_name in sorted(used_layers):
        if layer_name == "0" or layer_name in target_document.layers:
            continue
        source_layer = source_document.layers.get(layer_name)
        target_document.layers.add(
            name=layer_name,
            color=int(source_layer.dxf.color or 7),
            linetype="CONTINUOUS",
        )

    for entity in source_entities:
        target_modelspace.add_line(
            entity.dxf.start,
            entity.dxf.end,
            dxfattribs={"layer": str(entity.dxf.layer or "0")},
        )

    target = io.StringIO()
    target_document.write(target)
    normalized = target.getvalue()
    assert_single_dxf_document(normalized)

    verification = ezdxf_module.read(io.StringIO(normalized))
    if verification.dxfversion != AUTOCAD_DXF_VERSION:
        raise ValueError("DXF output version is not AutoCAD 2010.")
    if len(list(verification.modelspace())) != len(source_entities):
        raise ValueError("DXF output geometry is incomplete.")
    if verification.audit().has_errors:
        raise ValueError("DXF output failed the ezdxf audit.")

    return normalized.encode("utf-8")


__all__ = ["AUTOCAD_DXF_VERSION", "canonical_dxf_text", "assert_single_dxf_document", "rebuild_autocad_dxf"]
