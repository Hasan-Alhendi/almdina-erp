(() => {
    "use strict";

    const engine = window.AlmdinaSketchEngine;
    if (!engine) {
        console.error("AlmdinaSketchEngine must load before smart edge model");
        return;
    }

    const AXIS_EPSILON = 1.5;

    function clonePoints(points) {
        return engine.sanitizePoints(points).map(point => [point[0], point[1]]);
    }

    function samePoint(first, second, epsilon = 0.001) {
        return Boolean(first && second)
            && Math.abs(Number(first[0]) - Number(second[0])) <= epsilon
            && Math.abs(Number(first[1]) - Number(second[1])) <= epsilon;
    }

    function uniqueClosedPoints(points) {
        const source = clonePoints(points);
        if (source.length > 2 && samePoint(source[0], source[source.length - 1])) source.pop();
        return source;
    }

    function closePoints(points) {
        const source = uniqueClosedPoints(points);
        if (!source.length) return [];
        return [...source, source[0].slice()];
    }

    function normalizeIndex(points, index) {
        const count = uniqueClosedPoints(points).length;
        if (!count) return -1;
        const numeric = Math.floor(Number(index));
        if (!Number.isFinite(numeric)) return -1;
        return ((numeric % count) + count) % count;
    }

    function edge(points, index) {
        const source = uniqueClosedPoints(points);
        const safeIndex = normalizeIndex(source, index);
        if (safeIndex < 0 || source.length < 2) return null;
        const nextIndex = (safeIndex + 1) % source.length;
        const start = source[safeIndex].slice();
        const end = source[nextIndex].slice();
        return {
            index: safeIndex,
            nextIndex,
            start,
            end,
            midpoint: [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
            length: Math.hypot(end[0] - start[0], end[1] - start[1]),
        };
    }

    function orientation(points, index, epsilon = AXIS_EPSILON) {
        const value = edge(points, index);
        if (!value) return "";
        const dx = Math.abs(value.end[0] - value.start[0]);
        const dy = Math.abs(value.end[1] - value.start[1]);
        if (dy <= epsilon && dx > epsilon) return "horizontal";
        if (dx <= epsilon && dy > epsilon) return "vertical";
        return "angled";
    }

    function clampDelta(source, indexes, dx, dy, width, height) {
        const xs = indexes.map(index => source[index][0]);
        const ys = indexes.map(index => source[index][1]);
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        return {
            dx: Math.max(-minX, Math.min(Number(width) - maxX, Number(dx) || 0)),
            dy: Math.max(-minY, Math.min(Number(height) - maxY, Number(dy) || 0)),
        };
    }

    function moveEdge(points, index, dx, dy, options = {}) {
        const source = uniqueClosedPoints(points);
        const value = edge(source, index);
        if (!value) return closePoints(source);
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        const delta = clampDelta(source, [value.index, value.nextIndex], dx, dy, width, height);
        source[value.index] = [
            source[value.index][0] + delta.dx,
            source[value.index][1] + delta.dy,
        ];
        source[value.nextIndex] = [
            source[value.nextIndex][0] + delta.dx,
            source[value.nextIndex][1] + delta.dy,
        ];
        return closePoints(source);
    }

    function clampSegmentToCanvas(start, end, width, height) {
        let dx = 0;
        let dy = 0;
        const minX = Math.min(start[0], end[0]);
        const maxX = Math.max(start[0], end[0]);
        const minY = Math.min(start[1], end[1]);
        const maxY = Math.max(start[1], end[1]);
        if (minX < 0) dx = -minX;
        else if (maxX > width) dx = width - maxX;
        if (minY < 0) dy = -minY;
        else if (maxY > height) dy = height - maxY;
        return [
            [start[0] + dx, start[1] + dy],
            [end[0] + dx, end[1] + dy],
        ];
    }

    function alignEdge(points, index, axis, options = {}) {
        const source = uniqueClosedPoints(points);
        const value = edge(source, index);
        if (!value || !["horizontal", "vertical"].includes(axis)) return closePoints(source);
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        const half = value.length / 2;
        let start;
        let end;
        if (axis === "horizontal") {
            start = [value.midpoint[0] - half, value.midpoint[1]];
            end = [value.midpoint[0] + half, value.midpoint[1]];
        } else {
            start = [value.midpoint[0], value.midpoint[1] - half];
            end = [value.midpoint[0], value.midpoint[1] + half];
        }
        [start, end] = clampSegmentToCanvas(start, end, width, height);
        source[value.index] = start;
        source[value.nextIndex] = end;
        return closePoints(source);
    }

    function setEdgeLength(points, index, targetLength, options = {}) {
        const source = uniqueClosedPoints(points);
        const value = edge(source, index);
        const length = Number(targetLength);
        if (!value || !Number.isFinite(length) || length < 4) return closePoints(source);
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        const current = Math.max(0.001, value.length);
        const ux = (value.end[0] - value.start[0]) / current;
        const uy = (value.end[1] - value.start[1]) / current;
        const mode = String(options.anchor || "center");
        let start;
        let end;
        if (mode === "start") {
            start = value.start.slice();
            end = [start[0] + ux * length, start[1] + uy * length];
        } else if (mode === "end") {
            end = value.end.slice();
            start = [end[0] - ux * length, end[1] - uy * length];
        } else {
            start = [value.midpoint[0] - ux * length / 2, value.midpoint[1] - uy * length / 2];
            end = [value.midpoint[0] + ux * length / 2, value.midpoint[1] + uy * length / 2];
        }
        [start, end] = clampSegmentToCanvas(start, end, width, height);
        source[value.index] = start;
        source[value.nextIndex] = end;
        return closePoints(source);
    }

    function insertMidpoint(points, index) {
        const source = uniqueClosedPoints(points);
        const value = edge(source, index);
        if (!value) return closePoints(source);
        source.splice(value.nextIndex === 0 ? source.length : value.nextIndex, 0, [
            (value.start[0] + value.end[0]) / 2,
            (value.start[1] + value.end[1]) / 2,
        ]);
        return closePoints(source);
    }

    function perpendicularDragDelta(points, index, dx, dy, shiftKey = false) {
        const axis = orientation(points, index);
        if (axis === "horizontal") return { dx: 0, dy: Number(dy) || 0 };
        if (axis === "vertical") return { dx: Number(dx) || 0, dy: 0 };
        if (shiftKey) {
            return Math.abs(Number(dx) || 0) >= Math.abs(Number(dy) || 0)
                ? { dx: Number(dx) || 0, dy: 0 }
                : { dx: 0, dy: Number(dy) || 0 };
        }
        return { dx: Number(dx) || 0, dy: Number(dy) || 0 };
    }

    window.AlmdinaSketchEdgeModel = Object.freeze({
        AXIS_EPSILON,
        samePoint,
        uniqueClosedPoints,
        closePoints,
        normalizeIndex,
        edge,
        orientation,
        moveEdge,
        alignEdge,
        setEdgeLength,
        insertMidpoint,
        perpendicularDragDelta,
    });
})();
