from __future__ import annotations

from typing import Any

from .primitives import num, rect_intersects, rects_have_clearance


def evaluate_plan(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    method_label: str,
    method_key: str,
    complexity: int = 1,
) -> dict[str, Any]:
    used_area = sum(num(piece.get("area_m2")) for piece in pieces)
    total_board_area = len(plan["sheets"]) * (board_w_cm * board_h_cm / 10000)
    waste_area = max(0.0, total_board_area - used_area)
    score = (
        len(plan["unplaced"]) * 1_000_000_000
        + len(plan["sheets"]) * 1_000_000
        + waste_area * 1000
        + complexity
    )
    return {
        "method_key": method_key,
        "method_label": method_label,
        "sheets": plan["sheets"],
        "unplaced": plan["unplaced"],
        "used_area_m2": used_area,
        "total_board_area_m2": total_board_area,
        "waste_area_m2": waste_area,
        "score": score,
        "complexity": complexity,
    }


def validate_plan(
    plan: dict[str, Any],
    requested_pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    tolerance: float = 1e-7,
    *,
    kerf_cm: float = 0.0,
) -> list[str]:
    """Independent geometry validator required before a plan can be approved."""

    errors: list[str] = []
    expected = {int(piece["id"]): piece for piece in requested_pieces}
    seen: dict[int, int] = {}
    required_kerf_cm = max(0.0, num(kerf_cm))

    for sheet in plan.get("sheets", []):
        pieces = sheet.get("pieces", [])
        for placed in pieces:
            piece_id = int(placed["id"])
            seen[piece_id] = seen.get(piece_id, 0) + 1
            x, y, w, h = map(
                num,
                (
                    placed.get("x"),
                    placed.get("y"),
                    placed.get("w"),
                    placed.get("h"),
                ),
            )
            if (
                x < -tolerance
                or y < -tolerance
                or x + w > board_w_cm + tolerance
                or y + h > board_h_cm + tolerance
            ):
                errors.append(
                    f"Piece {placed.get('label')} exceeds usable board bounds "
                    f"on sheet {sheet.get('sheet_no')}."
                )
            source = expected.get(piece_id)
            if not source:
                errors.append(f"Unknown piece id {piece_id} exists in plan.")
                continue
            allowed = {
                (
                    num(source["width_cm"]),
                    num(source["length_cm"]),
                    False,
                )
            }
            if source.get("allow_rotation") and num(source["width_cm"]) != num(
                source["length_cm"]
            ):
                allowed.add(
                    (
                        num(source["length_cm"]),
                        num(source["width_cm"]),
                        True,
                    )
                )
            actual = (w, h, bool(placed.get("rotated")))
            if not any(
                abs(actual[0] - allowed_value[0]) <= tolerance
                and abs(actual[1] - allowed_value[1]) <= tolerance
                and actual[2] == allowed_value[2]
                for allowed_value in allowed
            ):
                errors.append(
                    f"Piece {placed.get('label')} has invalid dimensions or rotation state."
                )

        for index, first in enumerate(pieces):
            first_rect = {
                "x": num(first["x"]),
                "y": num(first["y"]),
                "w": num(first["w"]),
                "h": num(first["h"]),
            }
            for second in pieces[index + 1 :]:
                second_rect = {
                    "x": num(second["x"]),
                    "y": num(second["y"]),
                    "w": num(second["w"]),
                    "h": num(second["h"]),
                }
                if rect_intersects(first_rect, second_rect):
                    errors.append(
                        f"Pieces {first.get('label')} and {second.get('label')} overlap "
                        f"on sheet {sheet.get('sheet_no')}."
                    )
                elif required_kerf_cm and not rects_have_clearance(
                    first_rect,
                    second_rect,
                    required_kerf_cm,
                    tolerance,
                ):
                    errors.append(
                        f"Pieces {first.get('label')} and {second.get('label')} do not preserve "
                        f"the required {required_kerf_cm:g} cm kerf clearance on sheet "
                        f"{sheet.get('sheet_no')}."
                    )

    for piece_id, piece in expected.items():
        count = seen.get(piece_id, 0)
        if count != 1:
            errors.append(
                f"Piece {piece.get('label')} appears {count} times; expected exactly once."
            )

    if plan.get("unplaced"):
        errors.append(f"Plan contains {len(plan['unplaced'])} unplaced piece(s).")
    return errors


__all__ = ["evaluate_plan", "validate_plan"]
