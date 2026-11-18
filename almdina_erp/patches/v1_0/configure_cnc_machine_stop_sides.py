"""Add stop-side columns without guessing a side for existing machines.

DocType sync adds ``width_stop_side`` and ``length_stop_side``. This patch
does not copy a side from the work zero or from a stored stop distance.
Blank sides stay blank. New NC generation asks for both sides before it
places a board. Historical stop distances remain on the machine and are
not rewritten.

The patch is idempotent: running it again does not write stop sides.
"""

from __future__ import annotations


def execute() -> None:
    return
