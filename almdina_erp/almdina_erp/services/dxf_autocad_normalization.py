"""Pure DXF normalization primitives for the AutoCAD export boundary."""

from __future__ import annotations

import io
import re
from typing import Any


AUTOCAD_DXF_VERSION = "AC1024"
_ALLOWED_ENTITY_TYPES = frozenset({"LINE", "TEXT"})
_TEXT_STYLE_NAME = "Tahoma"
_TEXT_STYLE_FONT = "tahoma.ttf"
_DXF_UNICODE_ESCAPE = re.compile(r"\\U\+([0-9A-Fa-f]{4})")


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


def _decode_dxf_text(value: str) -> str:
    return _DXF_UNICODE_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), value)


def _ensure_text_style(document: Any) -> None:
    if _TEXT_STYLE_NAME in document.styles:
        return
    document.styles.add(_TEXT_STYLE_NAME, font=_TEXT_STYLE_FONT)


def _copy_text_entity(target_modelspace: Any, entity: Any) -> None:
    insert = entity.dxf.insert
    attribs = {
        "layer": str(entity.dxf.layer or "0"),
        "style": _TEXT_STYLE_NAME,
        "insert": (float(insert.x), float(insert.y), float(getattr(insert, "z", 0.0) or 0.0)),
        "height": max(0.001, float(entity.dxf.height or 1.0)),
        "rotation": float(entity.dxf.rotation or 0.0),
        "halign": int(entity.dxf.halign or 0),
        "valign": int(entity.dxf.valign or 0),
    }
    text = target_modelspace.add_text(_decode_dxf_text(str(entity.dxf.text or "")), dxfattribs=attribs)
    if attribs["halign"] or attribs["valign"]:
        align = getattr(entity.dxf, "align_point", None) or insert
        text.dxf.align_point = (
            float(align.x),
            float(align.y),
            float(getattr(align, "z", 0.0) or 0.0),
        )


def rebuild_autocad_dxf(raw: bytes, ezdxf_module: Any | None = None) -> bytes:
    """Rebuild LINE and TEXT client geometry as a canonical AutoCAD 2010 document."""
    if ezdxf_module is None:
        import ezdxf as ezdxf_module

    source_document = ezdxf_module.read(io.StringIO(canonical_dxf_text(raw)))
    source_entities = list(source_document.modelspace())
    if not source_entities or any(
        entity.dxftype() not in _ALLOWED_ENTITY_TYPES for entity in source_entities
    ):
        raise ValueError("The client DXF must contain LINE and TEXT entities only.")

    target_document = ezdxf_module.new("R2010", setup=True)
    target_document.units = 4
    target_modelspace = target_document.modelspace()
    _ensure_text_style(target_document)

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
        layer = str(entity.dxf.layer or "0")
        if entity.dxftype() == "TEXT":
            _copy_text_entity(target_modelspace, entity)
            continue
        target_modelspace.add_line(
            entity.dxf.start,
            entity.dxf.end,
            dxfattribs={"layer": layer},
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
