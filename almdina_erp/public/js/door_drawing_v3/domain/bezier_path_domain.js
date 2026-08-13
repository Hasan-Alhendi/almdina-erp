(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const BaseG = root.Geometry;
    const BaseD = root.DocumentModel;
    if (!BaseG || !BaseD || !BaseG.path) throw new Error("Door Drawing V3 smart path domain must load before Bezier path domain");

    const PATH_TYPE = BaseG.PATH_TYPE || "path";
    const NODE_CORNER = "corner";
    const NODE_SMOOTH = "smooth";
    const NODE_SYMMETRIC = "symmetric";
    const NODE_TYPES = Object.freeze([NODE_CORNER, NODE_SMOOTH, NODE_SYMMETRIC]);
    const ZERO = Object.freeze({ x: 0, y: 0 });

    function finite(value) { const number = Number(value); return Number.isFinite(number) ? number : 0; }
    function vector(value) {
        if (!value || (!Number.isFinite(Number(value.x)) && !Number.isFinite(Number(value.y)))) return null;
        const x = finite(value.x), y = finite(value.y);
        if (Math.hypot(x, y) < BaseG.EPSILON_MM) return null;
        return Object.freeze({ x: BaseG.roundMm(x), y: BaseG.roundMm(y) });
    }
    function vectorLength(value) { return value ? Math.hypot(finite(value.x), finite(value.y)) : 0; }
    function normalizeType(value) { return NODE_TYPES.includes(String(value || "").toLowerCase()) ? String(value).toLowerCase() : NODE_CORNER; }
    function cloneNode(raw = {}) {
        return Object.freeze({ type: normalizeType(raw.type), in: vector(raw.in), out: vector(raw.out) });
    }
    function defaultNode() { return cloneNode(); }
    function normalizeNodes(points, rawNodes) {
        const nodes = Array.isArray(rawNodes) ? rawNodes : [];
        return Object.freeze((points || []).map((_, index) => cloneNode(nodes[index] || {})));
    }
    function path(id, points, closed = false, style = {}, nodes = null) {
        const base = BaseG.path(id, points, closed, style);
        const normalized = normalizeNodes(base.geometry.points, nodes);
        return Object.freeze({
            ...base,
            geometry: Object.freeze({ ...base.geometry, nodes: normalized }),
        });
    }
    function pathNodes(object) {
        if (!object || object.type !== PATH_TYPE) return Object.freeze([]);
        return normalizeNodes(object.geometry.points || [], object.geometry.nodes);
    }
    function pathNode(object, index) {
        const nodes = pathNodes(object);
        return nodes[Number(index)] || null;
    }
    function withNodes(object, nodes) {
        if (!object || object.type !== PATH_TYPE) throw new Error("Expected a path object");
        return path(object.id, object.geometry.points, object.geometry.closed, object.style, nodes);
    }
    function withPoints(object, points, nodes = object && object.geometry && object.geometry.nodes) {
        if (!object || object.type !== PATH_TYPE) throw new Error("Expected a path object");
        return path(object.id, points, object.geometry.closed, object.style, nodes);
    }
    function absoluteHandle(object, index, role) {
        const point = object && object.geometry && object.geometry.points && object.geometry.points[Number(index)];
        const node = pathNode(object, index);
        const handle = node && node[role];
        return point && handle ? BaseG.point(point.x + handle.x, point.y + handle.y) : null;
    }
    function oppositeRole(role) { return role === "in" ? "out" : "in"; }
    function unit(value) {
        const length = vectorLength(value);
        return length > BaseG.EPSILON_MM ? { x: value.x / length, y: value.y / length } : { ...ZERO };
    }
    function relatedHandle(type, active, opposite) {
        const activeLength = vectorLength(active);
        if (activeLength <= BaseG.EPSILON_MM) return opposite;
        const direction = unit(active);
        if (type === NODE_SYMMETRIC) return vector({ x: -direction.x * activeLength, y: -direction.y * activeLength });
        if (type === NODE_SMOOTH) {
            const oppositeLength = vectorLength(opposite);
            return oppositeLength <= BaseG.EPSILON_MM ? opposite : vector({ x: -direction.x * oppositeLength, y: -direction.y * oppositeLength });
        }
        return opposite;
    }
    function setPathNodeType(object, index, nextType) {
        const nodeIndex = Number(index), type = normalizeType(nextType), nodes = pathNodes(object).map(cloneNode);
        if (!nodes[nodeIndex]) return object;
        let current = nodes[nodeIndex];
        let incoming = current.in, outgoing = current.out;
        if (type !== NODE_CORNER) {
            if (!incoming && !outgoing) {
                const points = object.geometry.points, point = points[nodeIndex];
                const previous = points[(nodeIndex - 1 + points.length) % points.length];
                const next = points[(nodeIndex + 1) % points.length];
                const hasPrevious = object.geometry.closed || nodeIndex > 0;
                const hasNext = object.geometry.closed || nodeIndex < points.length - 1;
                let tangent = null;
                if (hasPrevious && hasNext) tangent = { x: next.x - previous.x, y: next.y - previous.y };
                else if (hasNext) tangent = { x: next.x - point.x, y: next.y - point.y };
                else if (hasPrevious) tangent = { x: point.x - previous.x, y: point.y - previous.y };
                const direction = unit(tangent || { x: 1, y: 0 });
                const previousLength = hasPrevious ? BaseG.distance(previous, point) : 0;
                const nextLength = hasNext ? BaseG.distance(point, next) : 0;
                const fallback = Math.max(previousLength, nextLength, 30) / 3;
                if (hasPrevious) incoming = vector({ x: -direction.x * (previousLength ? previousLength / 3 : fallback), y: -direction.y * (previousLength ? previousLength / 3 : fallback) });
                if (hasNext) outgoing = vector({ x: direction.x * (nextLength ? nextLength / 3 : fallback), y: direction.y * (nextLength ? nextLength / 3 : fallback) });
            }
            if (outgoing) incoming = relatedHandle(type, outgoing, incoming);
            else if (incoming) outgoing = relatedHandle(type, incoming, outgoing);
        }
        nodes[nodeIndex] = cloneNode({ type, in: incoming, out: outgoing });
        return withNodes(object, nodes);
    }
    function setPathHandle(object, index, role, absolutePoint, options = {}) {
        if (!object || object.type !== PATH_TYPE || !["in", "out"].includes(role)) return object;
        const nodeIndex = Number(index), anchor = object.geometry.points[nodeIndex];
        if (!anchor) return object;
        const nodes = pathNodes(object).map(cloneNode), current = nodes[nodeIndex] || defaultNode();
        const active = vector({ x: finite(absolutePoint && absolutePoint.x) - anchor.x, y: finite(absolutePoint && absolutePoint.y) - anchor.y });
        const next = { type: options.breakTangency ? NODE_CORNER : current.type, in: current.in, out: current.out };
        next[role] = active;
        if (!options.breakTangency && next.type !== NODE_CORNER && active) next[oppositeRole(role)] = relatedHandle(next.type, active, next[oppositeRole(role)]);
        nodes[nodeIndex] = cloneNode(next);
        return withNodes(object, nodes);
    }
    function clearPathHandle(object, index, role) {
        const nodes = pathNodes(object).map(cloneNode), nodeIndex = Number(index), current = nodes[nodeIndex];
        if (!current || !["in", "out"].includes(role)) return object;
        nodes[nodeIndex] = cloneNode({ ...current, [role]: null });
        return withNodes(object, nodes);
    }
    function pathSegment(object, index) {
        if (!object || object.type !== PATH_TYPE) return null;
        const points = object.geometry.points || [], count = points.length, segmentIndex = Number(index);
        const segmentCount = object.geometry.closed ? count : Math.max(0, count - 1);
        if (!Number.isInteger(segmentIndex) || segmentIndex < 0 || segmentIndex >= segmentCount) return null;
        const endIndex = (segmentIndex + 1) % count;
        const start = points[segmentIndex], end = points[endIndex];
        const startNode = pathNode(object, segmentIndex) || defaultNode(), endNode = pathNode(object, endIndex) || defaultNode();
        const c1 = startNode.out ? BaseG.point(start.x + startNode.out.x, start.y + startNode.out.y) : start;
        const c2 = endNode.in ? BaseG.point(end.x + endNode.in.x, end.y + endNode.in.y) : end;
        const curved = Boolean(startNode.out || endNode.in);
        return Object.freeze({ index: segmentIndex, startIndex: segmentIndex, endIndex, start, end, c1, c2, curved });
    }
    function pathSegments(object) {
        if (!object || object.type !== PATH_TYPE) return Object.freeze([]);
        const count = object.geometry.points.length, segmentCount = object.geometry.closed ? count : Math.max(0, count - 1);
        return Object.freeze(Array.from({ length: segmentCount }, (_, index) => pathSegment(object, index)));
    }
    function lerpPoint(a, b, t) { return BaseG.point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t); }
    function cubicPoint(segment, t) {
        const u = 1 - t;
        const x = u * u * u * segment.start.x + 3 * u * u * t * segment.c1.x + 3 * u * t * t * segment.c2.x + t * t * t * segment.end.x;
        const y = u * u * u * segment.start.y + 3 * u * u * t * segment.c1.y + 3 * u * t * t * segment.c2.y + t * t * t * segment.end.y;
        return BaseG.point(x, y);
    }
    function pathPointAtSegment(object, index, t = 0.5) {
        const segment = pathSegment(object, index); if (!segment) return null;
        const parameter = Math.max(0, Math.min(1, finite(t)));
        return segment.curved ? cubicPoint(segment, parameter) : lerpPoint(segment.start, segment.end, parameter);
    }
    function pathDerivativeAtSegment(object, index, t = 0.5) {
        const segment = pathSegment(object, index); if (!segment) return null;
        const parameter = Math.max(0, Math.min(1, finite(t))), u = 1 - parameter;
        return Object.freeze({
            x: 3 * u * u * (segment.c1.x - segment.start.x) + 6 * u * parameter * (segment.c2.x - segment.c1.x) + 3 * parameter * parameter * (segment.end.x - segment.c2.x),
            y: 3 * u * u * (segment.c1.y - segment.start.y) + 6 * u * parameter * (segment.c2.y - segment.c1.y) + 3 * parameter * parameter * (segment.end.y - segment.c2.y),
        });
    }
    function cubicExtrema(p0, p1, p2, p3) {
        const a = -p0 + 3 * p1 - 3 * p2 + p3;
        const b = 2 * (p0 - 2 * p1 + p2);
        const c = p1 - p0;
        const roots = [];
        if (Math.abs(a) <= 1e-12) {
            if (Math.abs(b) > 1e-12) roots.push(-c / b);
        } else {
            const discriminant = b * b - 4 * a * c;
            if (discriminant >= 0) {
                const sqrt = Math.sqrt(discriminant);
                roots.push((-b + sqrt) / (2 * a), (-b - sqrt) / (2 * a));
            }
        }
        return roots.filter(t => t > 0 && t < 1);
    }
    function pathBounds(object) {
        const segments = pathSegments(object); if (!segments.length) return null;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        function include(point) { minX = Math.min(minX, point.x); minY = Math.min(minY, point.y); maxX = Math.max(maxX, point.x); maxY = Math.max(maxY, point.y); }
        segments.forEach(segment => {
            include(segment.start); include(segment.end);
            if (!segment.curved) return;
            const candidates = new Set([
                ...cubicExtrema(segment.start.x, segment.c1.x, segment.c2.x, segment.end.x),
                ...cubicExtrema(segment.start.y, segment.c1.y, segment.c2.y, segment.end.y),
            ]);
            candidates.forEach(t => include(cubicPoint(segment, t)));
        });
        return Object.freeze({ left: minX, top: minY, right: maxX, bottom: maxY, width: maxX - minX, height: maxY - minY, centerX: (minX + maxX) / 2, centerY: (minY + maxY) / 2 });
    }
    function convertPathSegment(object, segmentIndex, mode) {
        const segment = pathSegment(object, segmentIndex); if (!segment) return object;
        const nodes = pathNodes(object).map(cloneNode), start = nodes[segment.startIndex], end = nodes[segment.endIndex];
        if (mode === "line") {
            nodes[segment.startIndex] = cloneNode({ ...start, out: null });
            nodes[segment.endIndex] = cloneNode({ ...end, in: null });
        } else if (mode === "curve") {
            const dx = segment.end.x - segment.start.x, dy = segment.end.y - segment.start.y;
            nodes[segment.startIndex] = cloneNode({ ...start, out: start.out || { x: dx / 3, y: dy / 3 } });
            nodes[segment.endIndex] = cloneNode({ ...end, in: end.in || { x: -dx / 3, y: -dy / 3 } });
        } else return object;
        return withNodes(object, nodes);
    }
    function splitSegment(object, segmentIndex, t = 0.5) {
        const segment = pathSegment(object, segmentIndex); if (!segment) return object;
        const parameter = Math.max(0.001, Math.min(0.999, finite(t)));
        const points = object.geometry.points.slice(), nodes = pathNodes(object).map(cloneNode);
        if (!segment.curved) {
            const point = lerpPoint(segment.start, segment.end, parameter);
            points.splice(segment.endIndex === 0 ? points.length : segment.endIndex, 0, point);
            const insertIndex = segment.endIndex === 0 ? points.length - 1 : segment.endIndex;
            nodes.splice(insertIndex, 0, defaultNode());
            return path(object.id, points, object.geometry.closed, object.style, nodes);
        }
        const q0 = lerpPoint(segment.start, segment.c1, parameter), q1 = lerpPoint(segment.c1, segment.c2, parameter), q2 = lerpPoint(segment.c2, segment.end, parameter);
        const r0 = lerpPoint(q0, q1, parameter), r1 = lerpPoint(q1, q2, parameter), s = lerpPoint(r0, r1, parameter);
        const startNode = { ...nodes[segment.startIndex], out: vector({ x: q0.x - segment.start.x, y: q0.y - segment.start.y }) };
        const endNode = { ...nodes[segment.endIndex], in: vector({ x: q2.x - segment.end.x, y: q2.y - segment.end.y }) };
        const middleNode = cloneNode({
            type: NODE_SMOOTH,
            in: { x: r0.x - s.x, y: r0.y - s.y },
            out: { x: r1.x - s.x, y: r1.y - s.y },
        });
        nodes[segment.startIndex] = cloneNode(startNode);
        nodes[segment.endIndex] = cloneNode(endNode);
        if (segment.endIndex === 0) { points.push(s); nodes.push(middleNode); }
        else { points.splice(segment.endIndex, 0, s); nodes.splice(segment.endIndex, 0, middleNode); }
        return path(object.id, points, object.geometry.closed, object.style, nodes);
    }
    function nearestPathSegment(object, candidate) {
        const point = BaseG.point(candidate && candidate.x, candidate && candidate.y);
        let best = null;
        pathSegments(object).forEach(segment => {
            if (!segment.curved) {
                const projected = BaseG.nearestPointOnSegment(point, segment.start, segment.end);
                const result = { ...projected, segmentIndex: segment.index };
                if (!best || result.distanceMm < best.distanceMm) best = result;
                return;
            }
            let bestT = 0, bestDistance = Infinity;
            const samples = 32;
            for (let i = 0; i <= samples; i += 1) {
                const t = i / samples, curvePoint = cubicPoint(segment, t), distance = BaseG.distance(point, curvePoint);
                if (distance < bestDistance) { bestDistance = distance; bestT = t; }
            }
            let span = 1 / samples;
            for (let iteration = 0; iteration < 5; iteration += 1) {
                const left = Math.max(0, bestT - span), right = Math.min(1, bestT + span);
                for (let i = 0; i <= 8; i += 1) {
                    const t = left + (right - left) * (i / 8), curvePoint = cubicPoint(segment, t), distance = BaseG.distance(point, curvePoint);
                    if (distance < bestDistance) { bestDistance = distance; bestT = t; }
                }
                span /= 4;
            }
            const result = { point: cubicPoint(segment, bestT), t: bestT, distanceMm: BaseG.roundMm(bestDistance), segmentIndex: segment.index };
            if (!best || result.distanceMm < best.distanceMm) best = result;
        });
        return best ? Object.freeze(best) : null;
    }
    function flattenPath(object, toleranceMm = 0.25) {
        if (!object || object.type !== PATH_TYPE) return Object.freeze([]);
        const tolerance = Math.max(0.01, finite(toleranceMm) || 0.25), output = [];
        function distanceToChord(point, start, end) {
            const projection = BaseG.nearestPointOnSegment(point, start, end); return projection.distanceMm;
        }
        function flattenSegment(segment, t0, p0, t1, p1, depth) {
            const span = t1 - t0;
            const tOneThird = t0 + span / 3, tm = (t0 + t1) / 2, tTwoThirds = t0 + span * 2 / 3;
            const pOneThird = cubicPoint(segment, tOneThird), pm = cubicPoint(segment, tm), pTwoThirds = cubicPoint(segment, tTwoThirds);
            const flatness = Math.max(distanceToChord(pOneThird, p0, p1), distanceToChord(pm, p0, p1), distanceToChord(pTwoThirds, p0, p1));
            if (depth >= 12 || flatness <= tolerance) { output.push(p1); return; }
            flattenSegment(segment, t0, p0, tm, pm, depth + 1);
            flattenSegment(segment, tm, pm, t1, p1, depth + 1);
        }
        const segments = pathSegments(object);
        if (!segments.length) return Object.freeze([]);
        output.push(segments[0].start);
        segments.forEach(segment => {
            if (segment.curved) flattenSegment(segment, 0, segment.start, 1, segment.end, 0);
            else output.push(segment.end);
        });
        if (object.geometry.closed && output.length > 1 && BaseG.distance(output[0], output[output.length - 1]) < BaseG.EPSILON_MM) output.pop();
        return Object.freeze(output.map(item => BaseG.point(item.x, item.y)));
    }
    function pathLength(object) {
        const points = flattenPath(object, 0.1); if (points.length < 2) return 0;
        let total = 0;
        for (let index = 1; index < points.length; index += 1) total += BaseG.distance(points[index - 1], points[index]);
        if (object.geometry.closed) total += BaseG.distance(points[points.length - 1], points[0]);
        return BaseG.roundMm(total);
    }
    function setPathPoint(object, index, nextPoint) {
        const nodeIndex = Number(index); if (!object || object.type !== PATH_TYPE || !object.geometry.points[nodeIndex]) return object;
        const points = object.geometry.points.slice(); points[nodeIndex] = BaseG.point(nextPoint.x, nextPoint.y);
        return withPoints(object, points);
    }
    function movePathNodes(object, indices, dxMm, dyMm) {
        if (!object || object.type !== PATH_TYPE) return object;
        const selected = new Set((indices || []).map(Number)), dx = finite(dxMm), dy = finite(dyMm);
        const points = object.geometry.points.map((point, index) => selected.has(index) ? BaseG.point(point.x + dx, point.y + dy) : point);
        return withPoints(object, points);
    }
    function insertPathPoint(object, segmentIndex, nextPoint) {
        const nearest = nearestPathSegment(object, nextPoint);
        const t = nearest && nearest.segmentIndex === Number(segmentIndex) ? nearest.t : 0.5;
        return splitSegment(object, Number(segmentIndex), t);
    }
    function removePathPoint(object, index) {
        if (!object || object.type !== PATH_TYPE) return object;
        const minimum = object.geometry.closed ? 3 : 2;
        if (object.geometry.points.length <= minimum) return object;
        const nodeIndex = Number(index), points = object.geometry.points.slice(), nodes = pathNodes(object).map(cloneNode);
        if (!points[nodeIndex]) return object;
        points.splice(nodeIndex, 1); nodes.splice(nodeIndex, 1);
        if (nodes.length) {
            const previousIndex = (nodeIndex - 1 + nodes.length) % nodes.length;
            const nextIndex = nodeIndex % nodes.length;
            if (!object.geometry.closed && nodeIndex === 0) nodes[0] = cloneNode({ ...nodes[0], in: null });
            else if (!object.geometry.closed && nodeIndex >= nodes.length) nodes[nodes.length - 1] = cloneNode({ ...nodes[nodes.length - 1], out: null });
            else {
                nodes[previousIndex] = cloneNode({ ...nodes[previousIndex], out: null });
                nodes[nextIndex] = cloneNode({ ...nodes[nextIndex], in: null });
            }
        }
        return path(object.id, points, object.geometry.closed, object.style, nodes);
    }
    function translateObject(object, dxMm, dyMm) {
        if (object && object.type === PATH_TYPE) {
            const dx = finite(dxMm), dy = finite(dyMm);
            return path(object.id, object.geometry.points.map(point => BaseG.point(point.x + dx, point.y + dy)), object.geometry.closed, object.style, object.geometry.nodes);
        }
        return BaseG.translateObject(object, dxMm, dyMm);
    }
    function cloneObject(object, id = object && object.id) {
        if (object && object.type === PATH_TYPE) return path(id, object.geometry.points, object.geometry.closed, object.style, object.geometry.nodes);
        return BaseG.cloneObject(object, id);
    }

    const Geometry = Object.freeze({
        ...BaseG,
        PATH_TYPE,
        NODE_CORNER,
        NODE_SMOOTH,
        NODE_SYMMETRIC,
        NODE_TYPES,
        path,
        pathNodes,
        pathNode,
        withPathNodes: withNodes,
        withPathPoints: withPoints,
        absolutePathHandle: absoluteHandle,
        setPathNodeType,
        setPathHandle,
        clearPathHandle,
        pathSegment,
        pathSegments,
        pathPointAtSegment,
        pathDerivativeAtSegment,
        pathBounds,
        convertPathSegment,
        splitPathSegment: splitSegment,
        nearestPathSegment,
        flattenPath,
        pathLength,
        setPathPoint,
        movePathNodes,
        insertPathPoint,
        removePathPoint,
        translateObject,
        cloneObject,
    });

    const SUPPORTED_TYPES = Object.freeze([...BaseD.SUPPORTED_TYPES.filter(type => type !== PATH_TYPE), PATH_TYPE]);
    function cloneObjectForDocument(object) { return Geometry.cloneObject(object); }
    function freezeDocument(document) {
        return Object.freeze({
            schema: BaseD.SCHEMA,
            version: BaseD.VERSION,
            units: BaseD.UNITS,
            blank: Object.freeze({ widthMm: Geometry.roundMm(document.blank && document.blank.widthMm), heightMm: Geometry.roundMm(document.blank && document.blank.heightMm) }),
            objects: Object.freeze((document.objects || []).map(cloneObjectForDocument)),
        });
    }
    function create(options = {}) {
        return freezeDocument({ blank: { widthMm: Math.max(0, Geometry.number(options.widthMm)), heightMm: Math.max(0, Geometry.number(options.heightMm)) }, objects: Array.isArray(options.objects) ? options.objects : [] });
    }
    function normalizeObject(item) {
        if (!item || !SUPPORTED_TYPES.includes(item.type) || !item.geometry) return null;
        if (item.type === PATH_TYPE) return Geometry.path(item.id, item.geometry.points, item.geometry.closed, item.style || {}, item.geometry.nodes);
        const temp = BaseD.normalize({ schema: BaseD.SCHEMA, version: BaseD.VERSION, units: BaseD.UNITS, blank: { widthMm: 1, heightMm: 1 }, objects: [item] });
        return temp.objects[0] || null;
    }
    function normalize(raw, fallback = {}) {
        if (!raw || typeof raw !== "object") return create(fallback);
        if (raw.schema !== BaseD.SCHEMA || Number(raw.version) !== BaseD.VERSION || raw.units !== BaseD.UNITS) return create(fallback);
        const objects = [];
        for (const item of Array.isArray(raw.objects) ? raw.objects : []) {
            try { const object = normalizeObject(item); if (object) objects.push(object); } catch (error) { /* isolate corrupt geometry */ }
        }
        return create({ widthMm: raw.blank && raw.blank.widthMm, heightMm: raw.blank && raw.blank.heightMm, objects });
    }
    function objectById(document, id) { return (document && document.objects || []).find(object => String(object.id) === String(id || "")) || null; }
    function addObject(document, object) {
        if (objectById(document, object && object.id)) throw new Error("Duplicate drawing object id");
        return freezeDocument({ ...document, objects: [...document.objects, cloneObjectForDocument(object)] });
    }
    function replaceObject(document, object) {
        let found = false;
        const objects = document.objects.map(item => {
            if (String(item.id) !== String(object.id)) return item;
            found = true;
            return cloneObjectForDocument(object);
        });
        if (!found) throw new Error("Drawing object not found");
        return freezeDocument({ ...document, objects });
    }
    function removeObject(document, id) { return freezeDocument({ ...document, objects: document.objects.filter(object => String(object.id) !== String(id)) }); }
    function serialize(document) { return JSON.stringify(document); }

    root.Geometry = Geometry;
    root.DocumentModel = Object.freeze({ ...BaseD, SUPPORTED_TYPES, create, normalize, objectById, addObject, replaceObject, removeObject, serialize });
    root.BezierPathDomain = Object.freeze({ PATH_TYPE, NODE_CORNER, NODE_SMOOTH, NODE_SYMMETRIC, NODE_TYPES });
})();
