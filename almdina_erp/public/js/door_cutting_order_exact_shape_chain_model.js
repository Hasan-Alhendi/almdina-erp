(() => {
    "use strict";

    const lineModel = window.AlmdinaExactLineModel;
    const geometry = window.AlmdinaSpecialShapeGeometry;
    if (!lineModel || !geometry) {
        console.error("Exact-line and exact-geometry models must load before shape-chain model");
        return;
    }

    const TEMPLATE = "exact-line-chain";
    const POINT_PRECISION = 3;
    const EPSILON = 0.001;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function rounded(value) {
        return lineModel.rounded(value, POINT_PRECISION);
    }

    function point(value) {
        return [rounded(value && value[0]), rounded(value && value[1])];
    }

    function pointKey(value) {
        const next = point(value);
        return `${next[0].toFixed(POINT_PRECISION)}:${next[1].toFixed(POINT_PRECISION)}`;
    }

    function distance(first, second) {
        return rounded(Math.hypot(
            Number(second && second[0]) - Number(first && first[0]),
            Number(second && second[1]) - Number(first && first[1])
        ));
    }

    function exactLines(elements) {
        return (Array.isArray(elements) ? elements : []).flatMap(element => {
            const meta = lineModel.exactMeta(element);
            if (!meta) return [];
            const start = point(meta.start_cm);
            const end = point(meta.end_cm);
            return [{
                id: String(element.id || ""),
                element,
                start,
                end,
                startKey: pointKey(start),
                endKey: pointKey(end),
                lengthCm: distance(start, end),
            }];
        });
    }

    function graph(lines) {
        const nodes = new Map();
        const addNode = (key, value) => {
            if (!nodes.has(key)) nodes.set(key, { key, point: point(value), edges: [] });
            return nodes.get(key);
        };
        lines.forEach((edge, index) => {
            addNode(edge.startKey, edge.start).edges.push(index);
            addNode(edge.endKey, edge.end).edges.push(index);
        });
        return nodes;
    }

    function connectedNodeCount(lines, nodes) {
        if (!lines.length || !nodes.size) return 0;
        const firstKey = lines[0].startKey;
        const visited = new Set([firstKey]);
        const queue = [firstKey];
        while (queue.length) {
            const key = queue.shift();
            const node = nodes.get(key);
            (node && node.edges || []).forEach(edgeIndex => {
                const edge = lines[edgeIndex];
                const nextKey = edge.startKey === key ? edge.endKey : edge.startKey;
                if (visited.has(nextKey)) return;
                visited.add(nextKey);
                queue.push(nextKey);
            });
        }
        return visited.size;
    }

    function orderedPath(lines, nodes, startKey) {
        if (!lines.length || !startKey) return { points: [], edgeIds: [], closed: false, complete: false };
        const used = new Set();
        const points = [clone(nodes.get(startKey).point)];
        const edgeIds = [];
        let currentKey = startKey;
        let guard = 0;
        while (used.size < lines.length && guard < lines.length + 2) {
            guard += 1;
            const node = nodes.get(currentKey);
            if (!node) break;
            const edgeIndex = node.edges.find(index => !used.has(index));
            if (edgeIndex === undefined) break;
            used.add(edgeIndex);
            const edge = lines[edgeIndex];
            edgeIds.push(edge.id);
            const nextKey = edge.startKey === currentKey ? edge.endKey : edge.startKey;
            currentKey = nextKey;
            if (currentKey !== startKey || used.size < lines.length) {
                points.push(clone(nodes.get(currentKey).point));
            }
        }
        return {
            points,
            edgeIds,
            closed: currentKey === startKey,
            complete: used.size === lines.length,
        };
    }

    function polygonArea(points) {
        if (!Array.isArray(points) || points.length < 3) return 0;
        const signed = points.reduce((sum, current, index) => {
            const next = points[(index + 1) % points.length];
            return sum + Number(current[0]) * Number(next[1]) - Number(next[0]) * Number(current[1]);
        }, 0) / 2;
        return rounded(Math.abs(signed));
    }

    function dimensionsOf(rowOrDimensions) {
        const source = rowOrDimensions || {};
        return {
            width: Math.max(0, Number(source.width ?? source.width_cm) || 0),
            length: Math.max(0, Number(source.length ?? source.length_cm) || 0),
        };
    }

    function analyze(elements, rowOrDimensions) {
        const lines = exactLines(elements);
        const dimensions = dimensionsOf(rowOrDimensions);
        const result = {
            state: "empty",
            exactLineCount: lines.length,
            closed: false,
            simple: false,
            canAutoClose: false,
            openEnds: [],
            closeGapCm: 0,
            points: [],
            edgeIds: [],
            perimeterCm: rounded(lines.reduce((sum, edge) => sum + edge.lengthCm, 0)),
            areaCm2: 0,
            geometry: null,
            geometryValid: false,
            geometryErrors: [],
        };
        if (!lines.length) return result;

        const nodes = graph(lines);
        const nodeList = Array.from(nodes.values());
        const connectedCount = connectedNodeCount(lines, nodes);
        if (connectedCount !== nodes.size) {
            return { ...result, state: "disconnected" };
        }
        if (nodeList.some(node => node.edges.length > 2)) {
            return { ...result, state: "branched" };
        }

        const loose = nodeList.filter(node => node.edges.length === 1);
        if (loose.length === 2 && nodeList.every(node => node.edges.length === 1 || node.edges.length === 2)) {
            const ordered = orderedPath(lines, nodes, loose[0].key);
            const openEnds = [clone(loose[0].point), clone(loose[1].point)];
            return {
                ...result,
                state: "open",
                simple: ordered.complete,
                canAutoClose: ordered.complete && lines.length >= 2 && distance(openEnds[0], openEnds[1]) > EPSILON,
                openEnds,
                closeGapCm: distance(openEnds[0], openEnds[1]),
                points: ordered.points,
                edgeIds: ordered.edgeIds,
            };
        }

        if (
            loose.length !== 0
            || lines.length < 3
            || !nodeList.every(node => node.edges.length === 2)
        ) {
            return { ...result, state: "invalid" };
        }

        const ordered = orderedPath(lines, nodes, lines[0].startKey);
        if (!ordered.complete || !ordered.closed || ordered.points.length < 3) {
            return { ...result, state: "invalid" };
        }

        const candidate = geometry.create(
            TEMPLATE,
            dimensions.width,
            dimensions.length,
            ordered.points
        );
        const validation = geometry.validate(candidate, dimensions.width, dimensions.length);
        return {
            ...result,
            state: validation.valid ? "exact-closed" : "closed-invalid",
            closed: true,
            simple: true,
            points: ordered.points,
            edgeIds: ordered.edgeIds,
            areaCm2: polygonArea(ordered.points),
            geometry: validation.valid ? validation.geometry : candidate,
            geometryValid: validation.valid,
            geometryErrors: validation.errors.slice(),
        };
    }

    function createClosingElement(analysis, transform, options = {}) {
        if (!analysis || !analysis.canAutoClose || !transform || analysis.openEnds.length !== 2) {
            return { valid: false, reason: "cannot-close", element: null };
        }
        const start = analysis.openEnds[1];
        const end = analysis.openEnds[0];
        return lineModel.buildElement({
            transform,
            startCm: start,
            lengthCm: distance(start, end),
            angleDeg: lineModel.angleBetween(start, end),
            color: options.color || "#172033",
            id: options.id || `exact-close-${Date.now()}`,
        });
    }

    function isGeneratedGeometry(raw) {
        const parsed = geometry.parse(raw);
        return Boolean(parsed && parsed.template === TEMPLATE);
    }

    function serializeGenerated(analysis) {
        return analysis && analysis.geometryValid && analysis.geometry
            ? geometry.serialize(analysis.geometry)
            : "";
    }

    window.AlmdinaExactShapeChainModel = Object.freeze({
        TEMPLATE,
        EPSILON,
        pointKey,
        distance,
        exactLines,
        polygonArea,
        analyze,
        createClosingElement,
        isGeneratedGeometry,
        serializeGenerated,
    });
})();
