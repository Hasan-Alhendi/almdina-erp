"""Numeric-only SVG for the affected pair in a rejected DXF. No file access."""

from __future__ import annotations

from html import escape

from frappe import _

from almdina_erp.almdina_erp.domain.cutting.layout_diagnostics import public_layout_preview


def render_layout_preview(value) -> str:
    preview = public_layout_preview(value)
    if preview is None:
        return ""
    left, bottom, right, top = preview["bounds"]
    padding = max(5.0, (right - left) * 0.04, (top - bottom) * 0.04)
    box = (left - padding, bottom - padding, right - left + 2 * padding, top - bottom + 2 * padding)
    view_box = " ".join(f"{value:.6f}" for value in box)
    paths = []
    for index, rings in enumerate(preview["paths"]):
        commands = []
        for ring in rings:
            commands.append("M " + " L ".join(f"{x:.6f} {y:.6f}" for x, y in ring) + " Z")
        color = "#b42318" if index == 0 else "#175cd3"
        paths.append(
            f'<path d="{" ".join(commands)}" fill="{color}" fill-opacity="0.16" '
            f'stroke="{color}" stroke-width="2" vector-effect="non-scaling-stroke" fill-rule="evenodd"/>'
        )
    title = escape(_("Affected cut paths (read-only detail)"))
    return (
        f'<details class="alm-error-preview"><summary>{title}</summary>'
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}" '
        f'viewBox="{view_box}" width="100%" height="280">'
        f'<title>{title}</title><g transform="translate(0 {bottom + top:.6f}) scale(1 -1)">'
        f'{"".join(paths)}</g></svg></details>'
    )
