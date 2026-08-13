(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.VectorSelectionGeometry;
    const G = root.Geometry;
    if (!Base || !G || !G.pathBounds || !G.pathPointAtSegment) throw new Error("Door Drawing V3 Bezier domain and vector selection must load first");

    const EPS = G.EPSILON_MM || 0.001;

    function boundsOfObject(object) {
        if (object && object.type === G.PATH_TYPE) {
            const box = G.pathBounds(object);
            return box ? Base.bounds(box.left, box.top, box.right, box.bottom) : null;
        }
        return Base.boundsOfObject(object);
    }
    function unionBounds(objects) {
        const items = (objects || []).map(boundsOfObject).filter(Boolean);
        if (!items.length) return null;
        return Base.bounds(
            Math.min(...items.map(item => item.left)),
            Math.min(...items.map(item => item.top)),
            Math.max(...items.map(item => item.right)),
            Math.max(...items.map(item => item.bottom))
        );
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
        items.sort((a, b) => horizontal ? a.box.left - b.box.left : a.box.top - b.box.top);
        const first = items[0].box, last = items[items.length - 1].box;
        const totalSize = items.reduce((sum, item) => sum + (horizontal ? item.box.width : item.box.height), 0);
        const span = horizontal ? last.right - first.left : last.bottom - first.top;
        const gap = (span - totalSize) / (items.length - 1);
        let cursor = horizontal ? first.left : first.top;
        const result = Object.create(null);
        items.forEach((item, index) => {
            if (index === 0 || index === items.length - 1) result[String(item.object.id)] = Object.freeze({ dx: 0, dy: 0 });
            else {
                const current = horizontal ? item.box.left : item.box.top, delta = cursor - current;
                result[String(item.object.id)] = Object.freeze({ dx: horizontal ? G.roundMm(delta) : 0, dy: horizontal ? 0 : G.roundMm(delta) });
            }
            cursor += (horizontal ? item.box.width : item.box.height) + gap;
        });
        return Object.freeze(result);
    }
    function midpointOfSegment(object, segmentIndex) {
        if (object && object.type === G.PATH_TYPE) return G.pathPointAtSegment(object, Number(segmentIndex), 0.5);
        return Base.midpointOfSegment(object, segmentIndex);
    }

    root.VectorSelectionGeometry = Object.freeze({
        ...Base,
        boundsOfObject,
        unionBounds,
        intersects,
        contains,
        idsInRect,
        alignOffsets,
        distributeOffsets,
        midpointOfSegment,
    });
    root.BezierSelectionDomain = Object.freeze({ boundsOfObject, unionBounds, midpointOfSegment });
})();
