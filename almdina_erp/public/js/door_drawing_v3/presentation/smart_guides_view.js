(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const G = root.Geometry;
    if (!Base || !G) throw new Error("Door Drawing V3 shape view must load before smart guide view");

    function lineMarkup(c, a, b, cls = "") {
        const p1 = Base.worldToScreen(c, a), p2 = Base.worldToScreen(c, b);
        return `<line class="ddv3-smart-guide ${cls}" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"/>`;
    }

    function labelMarkup(c, point, text, cls = "") {
        const p = Base.worldToScreen(c, point);
        return `<g class="ddv3-smart-guide-label ${cls}" transform="translate(${p.x + 10} ${p.y - 10})"><rect x="0" y="-14" width="${Math.max(28, String(text).length * 7 + 12)}" height="20" rx="4"/><text x="6" y="0">${String(text)}</text></g>`;
    }

    function markerMarkup(c, point, type, symbol) {
        const p = Base.worldToScreen(c, point);
        if (type === "endpoint" || type === "surface") {
            return `<g class="ddv3-smart-guide-marker is-${type}" transform="translate(${p.x} ${p.y})"><circle r="5"/><circle r="2"/></g>`;
        }
        if (type === "midpoint") {
            return `<g class="ddv3-smart-guide-marker is-midpoint" transform="translate(${p.x} ${p.y}) rotate(45)"><rect x="-4" y="-4" width="8" height="8"/></g>`;
        }
        if (type === "intersection") {
            return `<g class="ddv3-smart-guide-marker is-intersection" transform="translate(${p.x} ${p.y})"><path d="M -5 -5 L 5 5 M 5 -5 L -5 5"/></g>`;
        }
        if (symbol) return labelMarkup(c, point, symbol, `is-${type}`);
        return "";
    }

    function alignmentMarkup(c, guide) {
        const point = guide.point;
        const target = guide.targetPoint;
        if (!point || !target) return "";
        if (guide.type === "horizontal-alignment") {
            return lineMarkup(c, G.point(Math.min(point.x, target.x), point.y), G.point(Math.max(point.x, target.x), point.y), "is-alignment");
        }
        if (guide.type === "vertical-alignment") {
            return lineMarkup(c, G.point(point.x, Math.min(point.y, target.y)), G.point(point.x, Math.max(point.y, target.y)), "is-alignment");
        }
        if (guide.type === "xy-alignment") {
            const parts = [];
            if (guide.xAnchor && guide.xAnchor.point) {
                const p = guide.xAnchor.point;
                parts.push(lineMarkup(c, G.point(point.x, Math.min(point.y, p.y)), G.point(point.x, Math.max(point.y, p.y)), "is-alignment"));
            }
            if (guide.yAnchor && guide.yAnchor.point) {
                const p = guide.yAnchor.point;
                parts.push(lineMarkup(c, G.point(Math.min(point.x, p.x), point.y), G.point(Math.max(point.x, p.x), point.y), "is-alignment"));
            }
            return parts.join("");
        }
        return "";
    }

    function guideMarkup(c) {
        const state = c && c.snapState;
        const guide = state && state.smartGuide;
        if (!guide || !guide.point) return "";
        if (["surface", "endpoint", "midpoint", "intersection"].includes(guide.type)) {
            return markerMarkup(c, guide.point, guide.type, guide.symbol);
        }
        if (guide.type === "perpendicular") {
            return `${guide.targetPoint ? lineMarkup(c, guide.point, guide.targetPoint, "is-angle") : ""}${markerMarkup(c, guide.point, guide.type, guide.symbol || "⊥")}`;
        }
        if (guide.type === "parallel" || guide.type === "collinear") {
            return `${guide.targetPoint ? lineMarkup(c, guide.point, guide.targetPoint, "is-angle") : ""}${markerMarkup(c, guide.point, guide.type, guide.symbol || "∥")}`;
        }
        if (guide.type === "equal-length") {
            return `${guide.targetPoint ? lineMarkup(c, guide.point, guide.targetPoint, "is-equal-length") : ""}${labelMarkup(c, guide.point, "=", "is-equal-length")}`;
        }
        return alignmentMarkup(c, guide);
    }

    function render(c) {
        const result = Base.render(c);
        const markup = guideMarkup(c);
        if (markup && c && c.canvas) c.canvas.insertAdjacentHTML("beforeend", `<g class="ddv3-smart-guides-layer">${markup}</g>`);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render, smartGuideMarkup: guideMarkup });
    root.SmartGuidesView = Object.freeze({ guideMarkup, alignmentMarkup, markerMarkup });
})();
