from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable

SUPPORTED_DXF_ENTITY_TYPES = frozenset({
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "ARC",
    "CIRCLE",
    "SPLINE",
    "ELLIPSE",
})
CURVE_FLATTENING_TOLERANCE_MM = 0.25
MAX_INSERT_DEPTH = 32
MAX_EXPANDED_ENTITIES = 100_000


class DxfReadError(ValueError):
    pass


def _segments_from_points(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [(points[index], points[index + 1]) for index in range(len(points) - 1) if points[index] != points[index + 1]]


def _normalize_layer(value: Any) -> str:
    """Normalize only case and surrounding whitespace; never infer aliases."""
    return str(value or "0").strip().upper()


def _effective_layer(raw_layer: Any, inherited_layer: str | None) -> str:
    layer = _normalize_layer(raw_layer)
    if layer == "0" and inherited_layer:
        return inherited_layer
    return layer


def _is_minsert(entity: Any) -> bool:
    return int(getattr(entity.dxf, "row_count", 1) or 1) > 1 or int(
        getattr(entity.dxf, "column_count", 1) or 1
    ) > 1


def _diagnostics(
    *,
    detected_layers: set[str],
    relevant_layers: set[str],
    entity_counts: Counter[str],
    has_inserts: bool,
    block_names: set[str],
    expanded_entities: int,
) -> dict[str, Any]:
    return {
        "detected_layers": sorted(detected_layers),
        "relevant_layers": sorted(detected_layers & relevant_layers),
        "entity_counts": dict(sorted(entity_counts.items())),
        "has_inserts": has_inserts,
        "block_names": sorted(block_names),
        "expanded_entities": expanded_entities,
    }


def _import_ezdxf():
    import ezdxf
    from ezdxf import path as ezpath

    return ezdxf, ezpath


def _load_ezdxf_document(ezdxf: Any, file_path: str) -> Any:
    try:
        return ezdxf.readfile(file_path)
    except Exception:
        try:
            from ezdxf import recover

            document, _auditor = recover.readfile(file_path)
        except Exception as exc:
            raise DxfReadError(
                "تعذر قراءة بنية ملف DXF. تأكد أن الملف DXF صالح وغير تالف."
            ) from exc
        return document


def _geometry_from_legacy_rows(
    rows: list[dict[str, Any]],
    *,
    relevant_layers: set[str],
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    detected_layers: set[str] = set()
    entity_counts: Counter[str] = Counter()
    for row in rows:
        layer = _normalize_layer(row.get("layer"))
        detected_layers.add(layer)
        entity_type = str(row.get("entity_type") or row.get("type") or "LINE").upper()
        entity_counts[entity_type] += 1
        if layer not in relevant_layers:
            continue
        segments.append(
            {
                "layer": layer,
                "entity_type": entity_type,
                "start": (float(row.get("x1") or 0), float(row.get("y1") or 0)),
                "end": (float(row.get("x2") or 0), float(row.get("y2") or 0)),
            }
        )
    return {
        "segments": segments,
        "unsupported": [],
        "diagnostics": _diagnostics(
            detected_layers=detected_layers,
            relevant_layers=relevant_layers,
            entity_counts=entity_counts,
            has_inserts=False,
            block_names=set(),
            expanded_entities=len(rows),
        ),
    }


def read_dxf_geometry(
    file_path: str,
    *,
    relevant_layers: set[str],
    legacy_line_parser: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Read DXF geometry and normalize curves to validation-only segments.

    Modelspace and nested INSERT/BLOCK contents are read through ezdxf virtual
    entities so INSERT translation, rotation and scaling are applied by the DXF
    library. AutoCAD layer-0 inheritance is resolved explicitly after expansion.
    The source DXF is never rewritten.
    """
    normalized_relevant_layers = {_normalize_layer(layer) for layer in relevant_layers}
    try:
        ezdxf, ezpath = _import_ezdxf()
    except ImportError:
        if legacy_line_parser is None:
            raise DxfReadError("مكتبة قراءة DXF غير متوفرة على الخادم.")
        return _geometry_from_legacy_rows(
            legacy_line_parser(),
            relevant_layers=normalized_relevant_layers,
        )

    doc = _load_ezdxf_document(ezdxf, file_path)

    segments: list[dict[str, Any]] = []
    unsupported: list[dict[str, str]] = []
    detected_layers: set[str] = set()
    entity_counts: Counter[str] = Counter()
    block_names: set[str] = set()
    has_inserts = False
    expanded_entities = 0

    def visit(entities: Iterable[Any], *, inherited_layer: str | None, depth: int) -> None:
        nonlocal expanded_entities, has_inserts
        if depth > MAX_INSERT_DEPTH:
            raise DxfReadError(
                "ملف DXF يحتوي على تداخل BLOCK/INSERT أعمق من الحد الآمن المسموح. بسّط البلوكات ثم أعد الرفع."
            )

        for entity in entities:
            expanded_entities += 1
            if expanded_entities > MAX_EXPANDED_ENTITIES:
                raise DxfReadError(
                    "ملف DXF يحتوي على عدد كبير جدًا من العناصر بعد توسيع BLOCK/INSERT. بسّط الرسم ثم أعد الرفع."
                )

            entity_type = entity.dxftype().upper()
            layer = _effective_layer(getattr(entity.dxf, "layer", "0"), inherited_layer)
            detected_layers.add(layer)
            entity_counts[entity_type] += 1

            if entity_type == "INSERT":
                has_inserts = True
                block_name = str(getattr(entity.dxf, "name", "") or "").strip()
                if block_name:
                    block_names.add(block_name)
                if _is_minsert(entity):
                    raise DxfReadError(
                        f"البلوك {block_name or '؟'} يستخدم MINSERT متعدد الصفوف/الأعمدة، وهذا الشكل غير مدعوم بأمان. "
                        "حوّله إلى INSERT منفصلة ثم أعد الرفع."
                    )
                try:
                    virtual_entities = entity.virtual_entities()
                    visit(virtual_entities, inherited_layer=layer, depth=depth + 1)
                except DxfReadError:
                    raise
                except Exception as exc:
                    raise DxfReadError(
                        f"تعذر تطبيق تحويلات BLOCK/INSERT للبلوك {block_name or '؟'}. "
                        "تحقق من البلوك ومقياسه ودورانه ثم أعد حفظ DXF."
                    ) from exc
                continue

            if layer not in normalized_relevant_layers:
                continue
            if entity_type not in SUPPORTED_DXF_ENTITY_TYPES:
                unsupported.append({"layer": layer, "entity_type": entity_type})
                continue
            try:
                path = ezpath.make_path(entity)
                flattened = [
                    (float(vertex.x), float(vertex.y))
                    for vertex in path.flattening(
                        distance=CURVE_FLATTENING_TOLERANCE_MM,
                        segments=8,
                    )
                ]
            except Exception as exc:
                raise DxfReadError(
                    f"تعذر تحليل عنصر {entity_type} على الطبقة {layer}. أعد حفظ الرسم كـ DXF قياسي ثم حاول مجددًا."
                ) from exc
            for start, end in _segments_from_points(flattened):
                segments.append(
                    {
                        "layer": layer,
                        "entity_type": entity_type,
                        "start": start,
                        "end": end,
                    }
                )

    visit(doc.modelspace(), inherited_layer=None, depth=0)
    return {
        "segments": segments,
        "unsupported": unsupported,
        "diagnostics": _diagnostics(
            detected_layers=detected_layers,
            relevant_layers=normalized_relevant_layers,
            entity_counts=entity_counts,
            has_inserts=has_inserts,
            block_names=block_names,
            expanded_entities=expanded_entities,
        ),
    }
