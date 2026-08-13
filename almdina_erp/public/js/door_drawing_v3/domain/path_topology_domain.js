(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G || !G.path || !G.pathNodes || !G.splitPathSegment) {
        throw new Error("Door Drawing V3 Bezier path domain must load before path topology");
    }

    function isPath(object) {
        return Boolean(object && object.type === G.PATH_TYPE && object.geometry && Array.isArray(object.geometry.points));
    }
    function cloneNode(node = {}) {
        return { type: node.type || G.NODE_CORNER, in: node.in ? { ...node.in } : null, out: node.out ? { ...node.out } : null };
    }
    function cloneNodes(object) { return G.pathNodes(object).map(cloneNode); }
    function rotate(values, index) {
        const list = values.slice();
        if (!list.length) return list;
        const normalized = ((Number(index) % list.length) + list.length) % list.length;
        return [...list.slice(normalized), ...list.slice(0, normalized)];
    }
    function reverseNode(node) {
        const current = cloneNode(node);
        return { type: current.type, in: current.out, out: current.in };
    }
    function pathFrom(object, points, closed, nodes) {
        if (!isPath(object)) throw new Error("Expected a path object");
        return G.path(object.id, points, Boolean(closed), object.style || {}, nodes);
    }

    function reversePath(object, options = {}) {
        if (!isPath(object)) throw new Error("Expected a path object");
        let points = object.geometry.points.slice().reverse();
        let nodes = cloneNodes(object).reverse().map(reverseNode);
        if (object.geometry.closed && options.preserveStart !== false && points.length > 1) {
            const originalStart = object.geometry.points[0];
            const startIndex = points.findIndex(point => G.distance(point, originalStart) <= G.EPSILON_MM);
            if (startIndex > 0) {
                points = rotate(points, startIndex);
                nodes = rotate(nodes, startIndex);
            }
        }
        return pathFrom(object, points, object.geometry.closed, nodes);
    }

    function closePath(object) {
        if (!isPath(object)) throw new Error("Expected a path object");
        if (object.geometry.closed || object.geometry.points.length < 3) return object;
        return pathFrom(object, object.geometry.points, true, cloneNodes(object));
    }

    function openPath(object, breakIndex = 0) {
        if (!isPath(object)) throw new Error("Expected a path object");
        if (!object.geometry.closed) return object;
        const points = rotate(object.geometry.points, breakIndex);
        const nodes = rotate(cloneNodes(object), breakIndex);
        nodes[0] = { ...nodes[0], in: null };
        nodes[nodes.length - 1] = { ...nodes[nodes.length - 1], out: null };
        return pathFrom(object, points, false, nodes);
    }

    function togglePathClosed(object, breakIndex = 0) {
        return object.geometry.closed ? openPath(object, breakIndex) : closePath(object);
    }

    function splitPathAtNode(object, nodeIndex, newId) {
        if (!isPath(object)) throw new Error("Expected a path object");
        const index = Number(nodeIndex);
        const points = object.geometry.points;
        const nodes = cloneNodes(object);
        if (!Number.isInteger(index) || index < 0 || index >= points.length) return null;

        if (object.geometry.closed) {
            const rotatedPoints = rotate(points, index);
            const rotatedNodes = rotate(nodes, index);
            const splitPoint = rotatedPoints[0];
            const splitNode = cloneNode(rotatedNodes[0]);
            return Object.freeze([G.path(
                object.id,
                [...rotatedPoints, splitPoint],
                false,
                object.style || {},
                [{ ...splitNode, in: null }, ...rotatedNodes.slice(1), { ...splitNode, out: null }]
            )]);
        }

        if (index <= 0 || index >= points.length - 1 || !newId) return null;
        const leftNodes = nodes.slice(0, index + 1);
        const rightNodes = nodes.slice(index);
        leftNodes[leftNodes.length - 1] = { ...leftNodes[leftNodes.length - 1], out: null };
        rightNodes[0] = { ...rightNodes[0], in: null };
        return Object.freeze([
            G.path(object.id, points.slice(0, index + 1), false, object.style || {}, leftNodes),
            G.path(newId, points.slice(index), false, object.style || {}, rightNodes),
        ]);
    }

    function splitPathAtSegmentMidpoint(object, segmentIndex, newId) {
        if (!isPath(object)) throw new Error("Expected a path object");
        const segment = G.pathSegment(object, Number(segmentIndex));
        if (!segment) return null;
        const before = object.geometry.points.length;
        const divided = G.splitPathSegment(object, segment.index, 0.5);
        if (divided.geometry.points.length !== before + 1) return null;
        const insertedIndex = object.geometry.closed && segment.endIndex === 0
            ? divided.geometry.points.length - 1
            : segment.endIndex;
        return splitPathAtNode(divided, insertedIndex, newId);
    }

    function endpoint(object, role) {
        const index = role === "start" ? 0 : object.geometry.points.length - 1;
        return object.geometry.points[index];
    }

    function nearestEndpointPair(first, second) {
        if (!isPath(first) || !isPath(second) || first.geometry.closed || second.geometry.closed) return null;
        const pairs = [];
        ["start", "end"].forEach(firstRole => {
            ["start", "end"].forEach(secondRole => {
                const firstPoint = endpoint(first, firstRole);
                const secondPoint = endpoint(second, secondRole);
                pairs.push({ firstRole, secondRole, firstPoint, secondPoint, distanceMm: G.distance(firstPoint, secondPoint) });
            });
        });
        pairs.sort((a, b) => a.distanceMm - b.distanceMm);
        return Object.freeze(pairs[0]);
    }

    function joinOpenPaths(first, second) {
        if (!isPath(first) || !isPath(second) || first.geometry.closed || second.geometry.closed || String(first.id) === String(second.id)) return null;
        const pair = nearestEndpointPair(first, second);
        if (!pair) return null;
        const left = pair.firstRole === "start" ? reversePath(first) : first;
        const right = pair.secondRole === "end" ? reversePath(second) : second;
        const leftPoints = left.geometry.points.slice();
        const rightPoints = right.geometry.points.slice();
        const leftNodes = cloneNodes(left);
        const rightNodes = cloneNodes(right);
        const last = leftPoints.length - 1;
        let points;
        let nodes;

        if (G.distance(leftPoints[last], rightPoints[0]) <= G.EPSILON_MM) {
            const a = cloneNode(leftNodes[last]);
            const b = cloneNode(rightNodes[0]);
            const merged = { type: a.type === b.type ? a.type : G.NODE_CORNER, in: a.in, out: b.out };
            points = [...leftPoints.slice(0, -1), leftPoints[last], ...rightPoints.slice(1)];
            nodes = [...leftNodes.slice(0, -1), merged, ...rightNodes.slice(1)];
        } else {
            leftNodes[last] = { ...leftNodes[last], out: null };
            rightNodes[0] = { ...rightNodes[0], in: null };
            points = [...leftPoints, ...rightPoints];
            nodes = [...leftNodes, ...rightNodes];
        }

        return Object.freeze({
            object: G.path(first.id, points, false, first.style || {}, nodes),
            consumedId: second.id,
            gapMm: G.roundMm(pair.distanceMm),
            pair,
        });
    }

    root.PathTopologyDomain = Object.freeze({
        isPath,
        reversePath,
        closePath,
        openPath,
        togglePathClosed,
        splitPathAtNode,
        splitPathAtSegmentMidpoint,
        nearestEndpointPair,
        joinOpenPaths,
    });
})();
