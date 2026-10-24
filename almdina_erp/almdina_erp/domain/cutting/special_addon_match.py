"""Match interchangeable Special doors by add-on combination.

The order sketch is not a geometric identity. Special doors that share a
manufacturing envelope are distinguished only by the add-on paths actually
bound to each contour. Double and full-door double have no DXF layer, so they
do not split a group. A deterministic assignment is enough when every
constraint is satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

OVERLAY_KINDS = ("liner", "back_groove", "recessed_handle_cutout")
_OVERLAY_KIND_SET = frozenset(OVERLAY_KINDS)


@dataclass(frozen=True, slots=True)
class SpecialContourRecord:
    key: int
    width_cm: float
    height_cm: float
    signature: frozenset[str]
    current_expected_index: int | None = None


@dataclass(frozen=True, slots=True)
class SpecialExpectedRecord:
    index: int
    width_cm: float
    height_cm: float
    allow_rotation: bool
    signature: frozenset[str]
    source_piece_no: int | None = None
    copy_no: int | None = None


@dataclass(frozen=True, slots=True)
class SpecialAddonAssignment:
    ok: bool
    mapping: dict[int, int] = field(default_factory=dict)
    code: str = ""
    params: dict[str, object] = field(default_factory=dict)


def overlay_signature(codes: Sequence[str]) -> frozenset[str]:
    """Keep only the three DXF overlay add-ons, in a comparable set."""

    return frozenset(code for code in codes if code in _OVERLAY_KIND_SET)


def _direct(
    actual_width: float,
    actual_height: float,
    expected_width: float,
    expected_height: float,
    tolerance_cm: float,
) -> bool:
    return (
        abs(actual_width - expected_width) <= tolerance_cm
        and abs(actual_height - expected_height) <= tolerance_cm
    )


def _dimensions_compatible(
    contour: SpecialContourRecord,
    expected: SpecialExpectedRecord,
    *,
    tolerance_cm: float,
    force_rotation: bool,
) -> bool:
    if _direct(
        contour.width_cm,
        contour.height_cm,
        expected.width_cm,
        expected.height_cm,
        tolerance_cm,
    ):
        return True
    if not (force_rotation or expected.allow_rotation):
        return False
    return _direct(
        contour.width_cm,
        contour.height_cm,
        expected.height_cm,
        expected.width_cm,
        tolerance_cm,
    )


def _edges(
    contours: Sequence[SpecialContourRecord],
    expected: Sequence[SpecialExpectedRecord],
    *,
    tolerance_cm: float,
    force_rotation: bool,
    require_signature: bool,
) -> list[list[int]]:
    by_index = {item.index: item for item in expected}
    edges: list[list[int]] = []
    for contour in contours:
        options: list[int] = []
        for item in expected:
            if require_signature and contour.signature != item.signature:
                continue
            if _dimensions_compatible(
                contour,
                item,
                tolerance_cm=tolerance_cm,
                force_rotation=force_rotation,
            ):
                options.append(item.index)
        current = contour.current_expected_index
        if current in by_index and current in options:
            options = [current, *[index for index in options if index != current]]
        edges.append(options)
    return edges


def _assign(edges: Sequence[Sequence[int]]) -> list[int] | None:
    """Deterministic injective assignment. Earlier options are tried first."""

    if any(not options for options in edges):
        return None
    used: set[int] = set()
    chosen = [-1] * len(edges)

    def visit(contour_index: int) -> bool:
        if contour_index == len(edges):
            return True
        for expected_index in edges[contour_index]:
            if expected_index in used:
                continue
            used.add(expected_index)
            chosen[contour_index] = expected_index
            if visit(contour_index + 1):
                return True
            used.remove(expected_index)
        return False

    if not visit(0):
        return None
    if len(used) != len(edges):
        return None
    return chosen


def _size_params(expected: Sequence[SpecialExpectedRecord]) -> dict[str, object]:
    sizes: list[tuple[float, float]] = []
    for item in expected:
        pair = (float(item.width_cm), float(item.height_cm))
        if pair not in sizes:
            sizes.append(pair)
    if not sizes:
        return {}
    params: dict[str, object] = {
        "width_cm": sizes[0][0],
        "height_cm": sizes[0][1],
        "identity_unproven": True,
    }
    if len(sizes) > 1:
        params["sizes"] = [
            {"width_cm": width, "height_cm": height}
            for width, height in sizes
        ]
    return params


def _diagnose(
    contours: Sequence[SpecialContourRecord],
    expected: Sequence[SpecialExpectedRecord],
    *,
    tolerance_cm: float,
) -> SpecialAddonAssignment:
    dimension_edges = _edges(
        contours,
        expected,
        tolerance_cm=tolerance_cm,
        force_rotation=False,
        require_signature=False,
    )
    parent = list(range(len(contours) + len(expected)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        parent[find(left)] = find(right)

    for contour_index, options in enumerate(dimension_edges):
        for expected_index in options:
            expected_slot = next(
                slot
                for slot, item in enumerate(expected)
                if item.index == expected_index
            )
            union(contour_index, len(contours) + expected_slot)

    groups: dict[int, tuple[list[int], list[int]]] = {}
    for contour_index in range(len(contours)):
        groups.setdefault(find(contour_index), ([], []))[0].append(contour_index)
    for slot in range(len(expected)):
        groups.setdefault(find(len(contours) + slot), ([], []))[1].append(slot)

    failing: tuple[list[SpecialContourRecord], list[SpecialExpectedRecord]] | None = None
    for contour_slots, expected_slots in groups.values():
        if not contour_slots or not expected_slots:
            continue
        group_contours = [contours[index] for index in contour_slots]
        group_expected = [expected[index] for index in expected_slots]
        if len(group_contours) != len(group_expected):
            failing = (group_contours, group_expected)
            break
        group_edges = _edges(
            group_contours,
            group_expected,
            tolerance_cm=tolerance_cm,
            force_rotation=False,
            require_signature=True,
        )
        if _assign(group_edges) is None:
            failing = (group_contours, group_expected)
            break
    if failing is None:
        failing = (list(contours), list(expected))

    group_contours, group_expected = failing
    params = _size_params(group_expected)
    actual_counts: dict[str, int] = {kind: 0 for kind in OVERLAY_KINDS}
    expected_counts: dict[str, int] = {kind: 0 for kind in OVERLAY_KINDS}
    for contour in group_contours:
        for kind in contour.signature:
            actual_counts[kind] = actual_counts.get(kind, 0) + 1
    for item in group_expected:
        for kind in item.signature:
            expected_counts[kind] = expected_counts.get(kind, 0) + 1

    actual_combinations = sorted(
        tuple(sorted(contour.signature)) for contour in group_contours
    )
    expected_combinations = sorted(
        tuple(sorted(item.signature)) for item in group_expected
    )
    extras = [kind for kind in OVERLAY_KINDS if actual_counts[kind] > expected_counts[kind]]
    missing = [kind for kind in OVERLAY_KINDS if actual_counts[kind] < expected_counts[kind]]
    counts_equal = not extras and not missing
    if counts_equal and actual_combinations != expected_combinations:
        split_kinds = [
            kind
            for kind in OVERLAY_KINDS
            if actual_counts[kind] or expected_counts[kind]
        ]
        # A required pair that is distributed across doors keeps every kind
        # that the order asked to share.
        shared = [
            kind
            for kind in OVERLAY_KINDS
            if any(len(item.signature) > 1 and kind in item.signature for item in group_expected)
        ]
        params["overlay_kinds"] = shared or split_kinds
        return SpecialAddonAssignment(False, code="SPECIAL_ADDON_GROUP_SPLIT", params=params)
    if missing:
        params["overlay_kind"] = missing[0]
        return SpecialAddonAssignment(False, code="SPECIAL_ADDON_GROUP_MISSING", params=params)
    if extras:
        params["overlay_kind"] = extras[0]
        return SpecialAddonAssignment(False, code="SPECIAL_ADDON_GROUP_EXTRA", params=params)
    return SpecialAddonAssignment(False, code="SPECIAL_ADDON_GROUP_SPLIT", params=params)


def _rotation_failure(
    contours: Sequence[SpecialContourRecord],
    expected: Sequence[SpecialExpectedRecord],
    *,
    tolerance_cm: float,
) -> SpecialAddonAssignment | None:
    relaxed = _assign(
        _edges(
            contours,
            expected,
            tolerance_cm=tolerance_cm,
            force_rotation=True,
            require_signature=True,
        )
    )
    if relaxed is None:
        return None
    blocked: list[tuple[SpecialContourRecord, SpecialExpectedRecord]] = []
    expected_by_index = {item.index: item for item in expected}
    for contour, expected_index in zip(contours, relaxed, strict=True):
        item = expected_by_index[expected_index]
        if _dimensions_compatible(
            contour,
            item,
            tolerance_cm=tolerance_cm,
            force_rotation=False,
        ):
            continue
        blocked.append((contour, item))
    if not blocked:
        return None
    contour, item = blocked[0]
    params: dict[str, object] = {
        "actual_width_cm": contour.width_cm,
        "actual_height_cm": contour.height_cm,
        "expected_width_cm": item.width_cm,
        "expected_height_cm": item.height_cm,
        "width_cm": item.width_cm,
        "height_cm": item.height_cm,
    }
    if len(blocked) == 1 and item.source_piece_no:
        params["source_piece_no"] = item.source_piece_no
        params["copy_no"] = item.copy_no or 1
    else:
        params["identity_unproven"] = True
    return SpecialAddonAssignment(False, code="FORBIDDEN_ROTATION", params=params)


def match_special_addon_group(
    contours: Sequence[SpecialContourRecord],
    expected: Sequence[SpecialExpectedRecord],
    *,
    tolerance_cm: float,
) -> SpecialAddonAssignment:
    """Return one complete assignment, or a structured reason there is none."""

    if not contours and not expected:
        return SpecialAddonAssignment(True, {})
    if len(contours) != len(expected):
        return _diagnose(contours, expected, tolerance_cm=tolerance_cm)

    assigned = _assign(
        _edges(
            contours,
            expected,
            tolerance_cm=tolerance_cm,
            force_rotation=False,
            require_signature=True,
        )
    )
    if assigned is not None:
        return SpecialAddonAssignment(
            True,
            {contour.key: expected_index for contour, expected_index in zip(contours, assigned, strict=True)},
        )
    rotation = _rotation_failure(contours, expected, tolerance_cm=tolerance_cm)
    if rotation is not None:
        return rotation
    return _diagnose(contours, expected, tolerance_cm=tolerance_cm)


__all__ = [
    "OVERLAY_KINDS",
    "SpecialAddonAssignment",
    "SpecialContourRecord",
    "SpecialExpectedRecord",
    "match_special_addon_group",
    "overlay_signature",
]
