"""Independent cutting strategy implementations."""

from .guillotine import (
    find_best_position_guillotine,
    pack_guillotine,
    place_piece_guillotine,
)
from .maxrects import (
    contact_point_score,
    find_best_position_maxrects,
    maxrects_score,
    pack_maxrects,
    place_piece_maxrects,
)
from .shelf import (
    pack_shelf_first_fit,
    pack_shelf_horizontal,
    pack_shelf_next_fit,
    pack_shelf_vertical,
)
from .skyline import (
    create_skyline_sheet,
    pack_skyline,
    skyline_add_level,
    skyline_find_position,
    skyline_merge,
    skyline_rect_fits,
)

__all__ = [
    "contact_point_score",
    "create_skyline_sheet",
    "find_best_position_guillotine",
    "find_best_position_maxrects",
    "maxrects_score",
    "pack_guillotine",
    "pack_maxrects",
    "pack_shelf_first_fit",
    "pack_shelf_horizontal",
    "pack_shelf_next_fit",
    "pack_shelf_vertical",
    "pack_skyline",
    "place_piece_guillotine",
    "place_piece_maxrects",
    "skyline_add_level",
    "skyline_find_position",
    "skyline_merge",
    "skyline_rect_fits",
]
