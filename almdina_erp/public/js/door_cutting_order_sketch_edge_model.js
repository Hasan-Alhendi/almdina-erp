(() => {
    "use strict";

    const engine = window.AlmdinaSketchEngine;
    if (!engine) {
        console.error("AlmdinaSketchEngine must load before smart edge model");
        return;
    }

    const AXIS_EPSILON = 1.5;
    const MIN_FEATURE_WIDTH = 12;
    const MIN_FEATURE_DEPTH = 8;
    const MAX_FEATURE_RATIO = 0.82;

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

    function signedArea(points) {
        const source = uniqueClosedPoints(points);
        if (source.length < 3) return 0;
        let area = 0;
        source.forEach((point, index) => {
            const next = source[(index + 1) % source.length];
            area += point[0] * next[1] - next[0] * point[1];
        });
        return area / 2;
    }

    function edgeFrame(points, index) {
        const value = edge(points, index);
        if (!value || value.length < 0.001) return null;
        const tx = (value.end[0] - value.start[0]) / value.length;
        const ty = (value.end[1] - value.start[1]) / value.length;
        const area = signedArea(points);
        const inward = area >= 0
            ? { x: -ty, y: tx }
            : { x: ty, y: -tx };
        return {
            edge: value,
            tangent: { x: tx, y: ty },
            inward,
        };
    }

    function clampFeatureSize(edgeLength, width, depth) {
        const safeLength = Math.max(0, Number(edgeLength) || 0);
        const maxWidth = Math.max(MIN_FEATURE_WIDTH, safeLength * MAX_FEATURE_RATIO);
        return {
            width: Math.max(
                MIN_FEATURE_WIDTH,
                Math.min(maxWidth, Number(width) || Math.min(90, maxWidth))
            ),
            depth: Math.max(MIN_FEATURE_DEPTH, Math.min(260, Number(depth) || 55)),
        };
    }

    function pointAlong(start, tangent, distance) {
        return [
            Number(start[0]) + tangent.x * distance,
            Number(start[1]) + tangent.y * distance,
        ];
    }

    function offsetPoint(point, normal, distance) {
        return [
            Number(point[0]) + normal.x * distance,
            Number(point[1]) + normal.y * distance,
        ];
    }

    function insideCanvas(point, width, height) {
        return point[0] >= 0 && point[0] <= width && point[1] >= 0 && point[1] <= height;
    }

    function fitFeatureDepth(entry, exit, normal, depth, options = {}) {
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        let safeDepth = Math.max(2, Number(depth) || MIN_FEATURE_DEPTH);
        for (let attempt = 0; attempt < 12; attempt += 1) {
            if (
                insideCanvas(offsetPoint(entry, normal, safeDepth), width, height)
                && insideCanvas(offsetPoint(exit, normal, safeDepth), width, height)
            ) {
                return safeDepth;
            }
            safeDepth *= 0.78;
        }
        return Math.max(2, safeDepth);
    }

    function createRectangularFeature(points, index, options = {}) {
        const source = uniqueClosedPoints(points);
        const frame = edgeFrame(source, index);
        if (!frame || frame.edge.length < MIN_FEATURE_WIDTH * 1.6) {
            return {
                changed: false,
                points: closePoints(source),
                reason: "edge-too-short",
            };
        }
        const size = clampFeatureSize(frame.edge.length, options.featureWidth, options.featureDepth);
        const margin = (frame.edge.length - size.width) / 2;
        const entry = pointAlong(frame.edge.start, frame.tangent, margin);
        const exit = pointAlong(frame.edge.start, frame.tangent, margin + size.width);
        const outward = String(options.direction || "inward") === "outward";
        const normal = outward
            ? { x: -frame.inward.x, y: -frame.inward.y }
            : frame.inward;
        const depth = fitFeatureDepth(entry, exit, normal, size.depth, options);
        const innerEntry = offsetPoint(entry, normal, depth);
        const innerExit = offsetPoint(exit, normal, depth);
        const insertionIndex = frame.edge.nextIndex === 0 ? source.length : frame.edge.nextIndex;
        source.splice(
            insertionIndex,
            0,
            entry,
            innerEntry,
            innerExit,
            exit
        );
        return {
            changed: true,
            points: closePoints(source),
            feature: {
                type: outward ? "protrusion" : "notch",
                width: size.width,
                depth,
                sourceEdgeIndex: frame.edge.index,
                orientation: orientation(points, index),
            },
        };
    }

    function createNotch(points, index, options = {}) {
        return createRectangularFeature(points, index, {
            ...options,
            direction: "inward",
        });
    }

    function createProtrusion(points, index, options = {}) {
        return createRectangularFeature(points, index, {
            ...options,
            direction: "outward",
        });
    }

    window.AlmdinaSketchEdgeModel = Object.freeze({
        AXIS_EPSILON,
        MIN_FEATURE_WIDTH,
        MIN_FEATURE_DEPTH,
        MAX_FEATURE_RATIO,
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
        signedArea,
        edgeFrame,
        clampFeatureSize,
        createRectangularFeature,
        createNotch,
        createProtrusion,
    });
})();
