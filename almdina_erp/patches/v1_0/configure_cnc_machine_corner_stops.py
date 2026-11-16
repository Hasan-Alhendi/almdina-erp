"""Keep corner stops from being copied across edges.

DocType sync adds ``right_stop_cm`` and ``top_stop_cm``. This patch does not
fill them from ``left_stop_cm`` or ``bottom_stop_cm``. A Bottom Left machine
keeps the left and bottom stops it already has. A machine whose work zero is
still Center stays Center until someone chooses Bottom Left, Bottom Right,
Top Left, or Top Right. New NC generation rejects Center and rejects a corner
whose two stops are still empty.

The patch is idempotent: running it again does not write stop values.
"""

from __future__ import annotations


def execute() -> None:
    return
