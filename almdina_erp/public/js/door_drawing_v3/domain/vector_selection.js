(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G || !G.pathSegments) throw new Error("Door Drawing V3 geometry must load before vector selection domain");

    const EPS = G.EPSILON_MM || 0.001;

    function bounds(left, top, right, bottom) {
        const l = Math.min(G.number(left), G.number(right));
        const r = Math.max(G.number(left), G.number(right));
        const t = Math.min(G.number(top), G.number(bottom));
        const b = Math.max(G.number(top), G.number(bottom));
        return Object.freeze({
            left: G.roundMm(l), top: G.roundMm(t), right: G.roundMm(r), bottom: G.roundMm(b),
            width: G.roundMm(r - l), height: G.roundMm(b - t),
            cx: G.roundMm((l + r) / 2), cy: G.roundMm((t + b) / 2),
        });
    }

    function angleOnArc(angle, start, sweep) {
        const positive = value => ((G.number(value) % 360) + 360) % 360;
        const a = positive(angle), s = positive(start);
        if (sweep >= 0) return positive(a - s) <= Math.abs(sweep) + 1e-7;
        return positive(s - a) <= Math.abs(sweep) + 1e-7;
    }

    function boundsOfObject(object) {
        if (!object || !object.geometry) return null;
        if (object.type === "line") {
            const { start, end } = object.geometry;
            return bounds(start.x, start.y, end.x, end.y);
        }
        if (object.type === "rectangle") {
            const { origin, widthMm, heightMm } = object.geometry;
            return bounds(origin.x, origin.y, origin.x + widthMm, origin.y + heightMm);
        }
        if (object.type === "circle") {
            const { center, radiusMm } = object.geometry;
            return bounds(center.x - radiusMm, center.y - radiusMm, center.x + radiusMm, center.y + radiusMm);
        }
        if (object.type === "arc") {
            const points = [G.arcStart(object), G.arcEnd(object)];
            for (const angle of [0, 90, 180, 270]) {
                if (angleOnArc(angle, object.geometry.startAngleDeg, object.geometry.sweepAngleDeg)) {
                    points.push(G.arcPoint(object, angle));
                }
            }
            return bounds(
                Math.min(...points.map(p => p.x)), Math.min(...points.map(p => p.y)),
                Math.max(...points.map(p => p.x)), Math.max(...points.map(p => p.y))
            );
        }
        if (object.type === G.PATH_TYPE) {
            const points = object.geometry.points || [];
            if (!points.length) return null;
            return bounds(
                Math.min(...points.map(p => p.x)), Math.min(...points.map(p => p.y)),
                Math.max(...points.map(p => p.x)), Math.max(...points.map(p => p.y))
            );
        }
        return null;
    }

    function unionBounds(objects) {
        const items = (objects || []).map(boundsOfObject).filter(Boolean);
        if (!items.length) return null;
        return bounds(
            Math.min(...items.map(item => item.left)),
            Math.min(...items.map(item => item.top)),
            Math.max(...items.map(item => item.right)),
            Math.max(...items.map(item => item.bottom))
        );
    }

    function normalizeRect(first, second) {
        return bounds(first && first.x, first && first.y, second && second.x, second && second.y);
    }

    function intersects(first, second) {
        return Boolean(first && second && !(
            first.right < second.left - EPS || first.left > second.right + EPS ||
            first.bottom < second.top - EPS || first.top > second.bottom + EPS
        ));
    }

    function contains(container, child) {
        return Boolean(container && child &&
            child.left >= container.left - EPS && child.right <= container.right + EPS &&
            child.top >= container.top - EPS && child.bottom <= container.bottom + EPS);
    }

    function idsInRect(document, rect, mode = "intersect") {
        const predicate = mode === "contain" ? contains : intersects;
        return Object.freeze((document && document.objects || [])
            .filter(object => predicate(rect, boundsOfObject(object)))
            .map(object => String(object.id)));
    }

    function alignOffsets(objects, alignment) {
        const items = (objects || []).map(object => ({ object, box: boundsOfObject(object) })).filter(item => item.box);
        const group = unionBounds(items.map(item => item.object));
        const result = Object.create(null);
        if (!group || items.length < 2) return Object.freeze(result);
        for (const { object, box } of items) {
            let dx = 0, dy = 0;
            if (alignment === "left") dx = group.left - box.left;
            else if (alignment === "hcenter") dx = group.cx - box.cx;
            else if (alignment === "right") dx = group.right - box.right;
            // World Y grows upward; visual top is the maximum Y edge.
            else if (alignment === "top") dy = group.bottom - box.bottom;
            else if (alignment === "vcenter") dy = group.cy - box.cy;
            else if (alignment === "bottom") dy = group.top - box.top;
            result[String(object.id)] = Object.freeze({ dx: G.roundMm(dx), dy: G.roundMm(dy) });
        }
        return Object.freeze(result);
    }

    function distributeOffsets(objects, axis) {
        const horizontal = axis === "horizontal";
        const items = (objects || []).map(object => ({ object, box: boundsOfObject(object) })).filter(item => item.box);
        if (items.length < 3) return Object.freeze(Object.create(null));
        items.sort((a, b) => (horizontal ? a.box.left - b.box.left : a.box.top - b.box.top));
        const first = items[0].box;
        const last = items[items.length - 1].box;
        const totalSize = items.reduce((sum, item) => sum + (horizontal ? item.box.width : item.box.height), 0);
        const span = horizontal ? last.right - first.left : last.bottom - first.top;
        const gap = (span - totalSize) / (items.length - 1);
        let cursor = horizontal ? first.left : first.top;
        const result = Object.create(null);
        items.forEach((item, index) => {
            if (index === 0 || index === items.length - 1) {
                result[String(item.object.id)] = Object.freeze({ dx: 0, dy: 0 });
            } else {
                const current = horizontal ? item.box.left : item.box.top;
                const delta = cursor - current;
                result[String(item.object.id)] = Object.freeze({ dx: horizontal ? G.roundMm(delta) : 0, dy: horizontal ? 0 : G.roundMm(delta) });
            }
            cursor += (horizontal ? item.box.width : item.box.height) + gap;
        });
        return Object.freeze(result);
    }

    function segmentNodeIndices(object, segmentIndices) {
        if (!object || object.type !== G.PATH_TYPE) return Object.freeze([]);
        const points = object.geometry.points || [];
        const selected = new Set();
        for (const raw of segmentIndices || []) {
            const index = Number(raw);
            if (!Number.isInteger(index) || index < 0 || index >= G.pathSegments(object).length) continue;
            selected.add(index);
            if (index === points.length - 1 && object.geometry.closed) selected.add(0);
            else selected.add(index + 1);
        }
        return Object.freeze([...selected].sort((a, b) => a - b));
    }

    function midpointOfSegment(object, segmentIndex) {
        if (!object || object.type !== G.PATH_TYPE) return null;
        const segment = G.pathSegments(object).find(item => item.index === Number(segmentIndex));
        if (!segment) return null;
        return G.point((segment.start.x + segment.end.x) / 2, (segment.start.y + segment.end.y) / 2);
    }

    root.VectorSelectionGeometry = Object.freeze({
        bounds, boundsOfObject, unionBounds, normalizeRect, intersects, contains, idsInRect,
        alignOffsets, distributeOffsets, segmentNodeIndices, midpointOfSegment,
    });
})();
