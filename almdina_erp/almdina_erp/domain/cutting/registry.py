from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .evaluation import evaluate_plan
from .primitives import normalize_mode, sort_pieces
from .strategies.guillotine import pack_guillotine
from .strategies.maxrects import pack_maxrects
from .strategies.shelf import (
    pack_shelf_first_fit,
    pack_shelf_horizontal,
    pack_shelf_next_fit,
    pack_shelf_vertical,
)
from .strategies.skyline import pack_skyline


Packer = Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PackingStrategy:
    key: str
    sort_method: str
    label: str
    packer: Packer
    args: tuple[Any, ...] = ()
    complexity: int = 1

    def execute(
        self,
        pieces: list[dict[str, Any]],
        board_w_cm: float,
        board_h_cm: float,
        kerf_cm: float,
    ) -> dict[str, Any]:
        ordered = sort_pieces(pieces, self.sort_method)
        raw = self.packer(
            ordered,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            *self.args,
        )
        return evaluate_plan(
            raw,
            pieces,
            board_w_cm,
            board_h_cm,
            self.label,
            self.key,
            self.complexity,
        )


STRATEGIES = (
    PackingStrategy(
        "MaxRects Best Short Side",
        "area_desc",
        "MaxRects - Best Short Side",
        pack_maxrects,
        ("best_short_side",),
        3,
    ),
    PackingStrategy(
        "MaxRects Best Area",
        "area_desc",
        "MaxRects - Best Area",
        pack_maxrects,
        ("best_area",),
        4,
    ),
    PackingStrategy(
        "MaxRects Bottom Left",
        "long_side_desc",
        "MaxRects - Bottom Left",
        pack_maxrects,
        ("bottom_left",),
        5,
    ),
    PackingStrategy(
        "MaxRects Contact Point",
        "area_desc",
        "MaxRects - Contact Point",
        pack_maxrects,
        ("contact_point",),
        4,
    ),
    PackingStrategy(
        "MaxRects Width",
        "width_desc",
        "MaxRects - الأعرض أولاً",
        pack_maxrects,
        ("best_short_side",),
        3,
    ),
    PackingStrategy(
        "MaxRects Length",
        "length_desc",
        "MaxRects - الأطول أولاً",
        pack_maxrects,
        ("best_short_side",),
        3,
    ),
    PackingStrategy(
        "Shelf Horizontal",
        "long_side_desc",
        "Shelf Packing - صفوف أفقية",
        pack_shelf_horizontal,
        complexity=20,
    ),
    PackingStrategy(
        "Shelf Vertical",
        "long_side_desc",
        "Shelf Packing - أعمدة عمودية",
        pack_shelf_vertical,
        complexity=20,
    ),
    PackingStrategy(
        "Shelf First Fit",
        "long_side_desc",
        "Shelf Packing - First Fit",
        pack_shelf_first_fit,
        complexity=18,
    ),
    PackingStrategy(
        "Shelf Next Fit",
        "long_side_desc",
        "Shelf Packing - Next Fit",
        pack_shelf_next_fit,
        complexity=22,
    ),
    PackingStrategy(
        "Guillotine Short Axis",
        "area_desc",
        "Guillotine - Short Axis Split",
        pack_guillotine,
        ("short_axis", "best_area"),
        10,
    ),
    PackingStrategy(
        "Guillotine Long Axis",
        "area_desc",
        "Guillotine - Long Axis Split",
        pack_guillotine,
        ("long_axis", "best_area"),
        10,
    ),
    PackingStrategy(
        "Guillotine Best Area Fit",
        "area_desc",
        "Guillotine - Best Area Fit",
        pack_guillotine,
        ("short_axis", "best_area"),
        9,
    ),
    PackingStrategy(
        "Guillotine Best Short Side Fit",
        "long_side_desc",
        "Guillotine - Best Short Side Fit",
        pack_guillotine,
        ("short_axis", "best_short_side"),
        9,
    ),
    PackingStrategy(
        "Guillotine Best Long Side Fit",
        "long_side_desc",
        "Guillotine - Best Long Side Fit",
        pack_guillotine,
        ("long_axis", "best_long_side"),
        9,
    ),
    PackingStrategy(
        "Skyline Bottom Left",
        "long_side_desc",
        "Skyline - Bottom Left",
        pack_skyline,
        ("bottom_left",),
        12,
    ),
    PackingStrategy(
        "Skyline Best Fit",
        "area_desc",
        "Skyline - Best Fit",
        pack_skyline,
        ("best_fit",),
        12,
    ),
)

STRATEGY_BY_KEY = {strategy.key: strategy for strategy in STRATEGIES}
PACKING_OPTIONS = ("Auto", *(strategy.key for strategy in STRATEGIES))

# Compatibility shape retained for advanced search and any old imports.
METHOD_CONFIGS: dict[str, tuple[str, Packer, tuple[Any, ...], int]] = {
    strategy.key: (
        strategy.label,
        strategy.packer,
        strategy.args,
        strategy.complexity,
    )
    for strategy in STRATEGIES
}


def get_strategy(method_key: str) -> PackingStrategy:
    normalized = normalize_mode(method_key)
    return STRATEGY_BY_KEY.get(
        normalized,
        STRATEGY_BY_KEY["MaxRects Best Short Side"],
    )


def run_single_method(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    method_key: str,
) -> dict[str, Any]:
    return get_strategy(method_key).execute(
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
    )


def choose_best_plan(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    selected_mode: str | None = "Auto",
) -> dict[str, Any]:
    mode = normalize_mode(selected_mode)
    if mode != "Auto":
        return run_single_method(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mode,
        )
    best = None
    for strategy in STRATEGIES:
        result = strategy.execute(pieces, board_w_cm, board_h_cm, kerf_cm)
        if best is None or result["score"] < best["score"]:
            best = result
    assert best is not None
    best["method_label"] = "Auto اختار: " + best["method_label"]
    return best


__all__ = [
    "METHOD_CONFIGS",
    "PACKING_OPTIONS",
    "STRATEGIES",
    "STRATEGY_BY_KEY",
    "PackingStrategy",
    "choose_best_plan",
    "get_strategy",
    "run_single_method",
]
