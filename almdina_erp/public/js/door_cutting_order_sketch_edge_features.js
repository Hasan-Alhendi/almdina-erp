(() => {
    "use strict";

    const engine = window.AlmdinaSketchEngine;
    const edgeModel = window.AlmdinaSketchEdgeModel;
    if (!engine || !edgeModel) {
        console.error("Sketch engine and edge model must load before edge features");
        return;
    }

    const MIN_FEATURE_WIDTH = 12;
    const MIN_FEATURE_DEPTH = 8;
    const MAX_FEATURE_RATIO = 0.82;

    function clonePoint(point) {
        return [Number(point[0]), Number(point[1])];
    }

    function signedArea(points) {
        const source = edgeModel.uniqueClosedPoints(points);
        if (source.length < 3) return 0;
        let area = 0;
        source.forEach((point, index) => {
            const next = source[(index + 1) % source.length];
            area += point[0] * next[1] - next[0] * point[1];
        });
        return area / 2;
    }

    function unitVector(start, end) {
        const dx = Number(end[0]) - Number(start[0]);
        const dy = Number(end[1]) - Number(start[1]);
        const length = Math.hypot(dx, dy);
        if (length < 0.001) return null;
        return { x: dx / length, y: dy / length, length };
    }

    function inwardNormal(points, edgeIndex) {
        const value = edgeModel.edge(points, edgeIndex);
        if (!value) return null;
        const tangent = unitVector(value.start, value.end);
        if (!tangent) return null;
        const area = signedArea(points);
        const normal = area >= 0
            ? { x: -tangent.y, y: tangent.x }
            : { x: tangent.y, y: -tangent.x };
        return { ...normal, tangent, edge: value };
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

    function fitDepthToCanvas(entry, exit, normal, depth, canvas) {
        const width = Number(canvas && canvas.width) > 0
            ? Number(canvas.width)
            : engine.DEFAULT_CANVAS.width;
        const height = Number(canvas && canvas.height) > 0
            ? Number(canvas.height)
            : engine.DEFAULT_CANVAS.height;
        let safeDepth = Number(depth) || MIN_FEATURE_DEPTH;
        for (let attempt = 0; attempt < 12; attempt += 1) {
            const first = offsetPoint(entry, normal, safeDepth);
            const second = offsetPoint(exit, normal, safeDepth);
            if (insideCanvas(first, width, height) && insideCanvas(second, width, height)) {
                return safeDepth;
            }
            safeDepth *= 0.78;
        }
        return Math.max(2, safeDepth);
    }

    function createRectangularFeature(points, edgeIndex, options = {}) {
        const source = edgeModel.uniqueClosedPoints(points);
        const value = edgeModel.edge(source, edgeIndex);
        const frame = inwardNormal(source, edgeIndex);
        if (!value || !frame || value.length < MIN_FEATURE_WIDTH * 1.6) {
            return {
                changed: false,
                points: edgeModel.closePoints(source),
                reason: "edge-too-short",
            };
        }

        const size = clampFeatureSize(value.length, options.width, options.depth);
        const margin = (value.length - size.width) / 2;
        const entry = pointAlong(value.start, frame.tangent, margin);
        const exit = pointAlong(value.start, frame.tangent, margin + size.width);
        const direction = String(options.direction || "inward") === "outward" ? -1 : 1;
        const normal = {
            x: frame.x * direction,
            y: frame.y * direction,
        };
        const depth = fitDepthToCanvas(
            entry,
            exit,
            normal,
            size.depth,
            options.canvas || engine.DEFAULT_CANVAS
        );
        const innerEntry = offsetPoint(entry, normal, depth);
        const innerExit = offsetPoint(exit, normal, depth);

        const insertionIndex = value.nextIndex === 0 ? source.length : value.nextIndex;
        source.splice(
            insertionIndex,
            0,
            clonePoint(entry),
            clonePoint(innerEntry),
            clonePoint(innerExit),
            clonePoint(exit)
        );

        return {
            changed: true,
            points: edgeModel.closePoints(source),
            feature: {
                type: direction > 0 ? "notch" : "protrusion",
                source_edge_index: value.index,
                width: size.width,
                depth,
                orientation: edgeModel.orientation(points, edgeIndex),
            },
        };
    }

    function createNotch(points, edgeIndex, options = {}) {
        return createRectangularFeature(points, edgeIndex, {
            ...options,
            direction: "inward",
        });
    }

    function createProtrusion(points, edgeIndex, options = {}) {
        return createRectangularFeature(points, edgeIndex, {
            ...options,
            direction: "outward",
        });
    }

    window.AlmdinaSketchEdgeFeatures = Object.freeze({
        MIN_FEATURE_WIDTH,
        MIN_FEATURE_DEPTH,
        MAX_FEATURE_RATIO,
        signedArea,
        inwardNormal,
        clampFeatureSize,
        createRectangularFeature,
        createNotch,
        createProtrusion,
    });
})();
