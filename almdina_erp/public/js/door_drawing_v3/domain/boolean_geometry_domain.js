(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G || !G.path || !G.flattenPath || !G.pathSegments) {
        throw new Error("Door Drawing V3 Bezier geometry must load before boolean geometry");
    }

    const DEFAULT_TOLERANCE_MM = 0.05;
    const OPERATIONS = Object.freeze(["union", "subtract", "intersect", "exclude"]);
    const CLOSED_TYPES = Object.freeze(["rectangle", "circle", G.PATH_TYPE]);

    function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
    function cross(ax, ay, bx, by) { return ax * by - ay * bx; }
    function dot(ax, ay, bx, by) { return ax * bx + ay * by; }
    function rawPoint(x, y) { return { x: Number(x), y: Number(y) }; }
    function interpolate(a, b, t) { return rawPoint(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t); }
    function keyPoint(point) { return `${G.roundMm(point.x).toFixed(3)},${G.roundMm(point.y).toFixed(3)}`; }
    function undirectedKey(a, b) {
        const first = keyPoint(a), second = keyPoint(b);
        return first < second ? `${first}|${second}` : `${second}|${first}`;
    }

    function isBooleanOperand(object) {
        if (!object || !CLOSED_TYPES.includes(object.type) || !object.geometry) return false;
        return object.type !== G.PATH_TYPE || Boolean(object.geometry.closed);
    }

    function rectanglePolygon(object) {
        const { origin, widthMm, heightMm } = object.geometry;
        return [
            G.point(origin.x, origin.y),
            G.point(origin.x + widthMm, origin.y),
            G.point(origin.x + widthMm, origin.y + heightMm),
            G.point(origin.x, origin.y + heightMm),
        ];
    }

    function circlePolygon(object, toleranceMm) {
        const radius = Math.max(G.EPSILON_MM, Number(object.geometry.radiusMm));
        const tolerance = clamp(Number(toleranceMm) || DEFAULT_TOLERANCE_MM, 0.01, Math.max(0.01, radius));
        const cosine = clamp(1 - tolerance / radius, -1, 1);
        const halfAngle = Math.max(0.001, Math.acos(cosine));
        const count = clamp(Math.ceil(Math.PI / halfAngle), 24, 1440);
        const output = [];
        for (let index = 0; index < count; index += 1) {
            const angle = index * Math.PI * 2 / count;
            output.push(G.point(
                object.geometry.center.x + Math.cos(angle) * radius,
                object.geometry.center.y + Math.sin(angle) * radius
            ));
        }
        return output;
    }

    function removeAdjacentDuplicates(points) {
        const output = [];
        (points || []).forEach(point => {
            const next = G.point(point.x, point.y);
            if (!output.length || G.distance(output[output.length - 1], next) > G.EPSILON_MM) output.push(next);
        });
        if (output.length > 1 && G.distance(output[0], output[output.length - 1]) <= G.EPSILON_MM) output.pop();
        return output;
    }

    function simplifyCollinear(points, toleranceMm) {
        let output = removeAdjacentDuplicates(points);
        if (output.length < 4) return output;
        const threshold = Math.max(G.EPSILON_MM * 2, Number(toleranceMm) * 0.2);
        let changed = true;
        while (changed && output.length > 3) {
            changed = false;
            const next = [];
            for (let index = 0; index < output.length; index += 1) {
                const previous = output[(index - 1 + output.length) % output.length];
                const current = output[index];
                const following = output[(index + 1) % output.length];
                const ax = current.x - previous.x, ay = current.y - previous.y;
                const bx = following.x - current.x, by = following.y - current.y;
                const chord = Math.max(G.distance(previous, following), G.EPSILON_MM);
                const height = Math.abs(cross(ax, ay, bx, by)) / chord;
                if (height <= threshold && dot(ax, ay, bx, by) >= 0) {
                    changed = true;
                    continue;
                }
                next.push(current);
            }
            if (next.length >= 3) output = next;
            else break;
        }
        return output;
    }

    function objectToPolygon(object, toleranceMm = DEFAULT_TOLERANCE_MM) {
        if (!isBooleanOperand(object)) return null;
        const tolerance = Math.max(0.01, Number(toleranceMm) || DEFAULT_TOLERANCE_MM);
        let points = [];
        let approximated = false;
        if (object.type === "rectangle") points = rectanglePolygon(object);
        else if (object.type === "circle") {
            points = circlePolygon(object, tolerance);
            approximated = true;
        } else if (object.type === G.PATH_TYPE) {
            points = G.flattenPath(object, tolerance);
            approximated = G.pathSegments(object).some(segment => Boolean(segment.curved));
        }
        points = simplifyCollinear(points, tolerance);
        if (points.length < 3) return null;
        return Object.freeze({
            points: Object.freeze(points.map(point => G.point(point.x, point.y))),
            approximated,
            sourceType: object.type,
        });
    }

    function signedArea(points) {
        let area = 0;
        for (let index = 0; index < (points || []).length; index += 1) {
            const current = points[index];
            const next = points[(index + 1) % points.length];
            area += current.x * next.y - next.x * current.y;
        }
        return area / 2;
    }

    function pointOnSegment(point, start, end, tolerance = G.EPSILON_MM * 2) {
        const dx = end.x - start.x, dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length <= G.EPSILON_MM) return G.distance(point, start) <= tolerance;
        const deviation = Math.abs(cross(point.x - start.x, point.y - start.y, dx, dy)) / length;
        if (deviation > tolerance) return false;
        const projection = dot(point.x - start.x, point.y - start.y, dx, dy) / (length * length);
        return projection >= -1e-9 && projection <= 1 + 1e-9;
    }

    function pointInPolygon(point, polygon) {
        let inside = false;
        for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
            const a = polygon[previous], b = polygon[index];
            if (pointOnSegment(point, a, b)) return true;
            const crosses = ((a.y > point.y) !== (b.y > point.y)) &&
                (point.x < (b.x - a.x) * (point.y - a.y) / ((b.y - a.y) || Number.EPSILON) + a.x);
            if (crosses) inside = !inside;
        }
        return inside;
    }

    function edgeList(polygon, source) {
        return polygon.map((start, index) => Object.seal({
            source,
            start: rawPoint(start.x, start.y),
            end: rawPoint(polygon[(index + 1) % polygon.length].x, polygon[(index + 1) % polygon.length].y),
            splits: [0, 1],
        }));
    }

    function parameterOnSegment(point, start, end) {
        const dx = end.x - start.x, dy = end.y - start.y;
        const denominator = dx * dx + dy * dy;
        return denominator <= 1e-18 ? 0 : ((point.x - start.x) * dx + (point.y - start.y) * dy) / denominator;
    }

    function pushSplit(edge, value) {
        const t = clamp(Number(value), 0, 1);
        if (!edge.splits.some(current => Math.abs(current - t) <= 1e-10)) edge.splits.push(t);
    }

    function splitAtIntersections(firstEdges, secondEdges) {
        firstEdges.forEach(first => {
            secondEdges.forEach(second => {
                const rx = first.end.x - first.start.x, ry = first.end.y - first.start.y;
                const sx = second.end.x - second.start.x, sy = second.end.y - second.start.y;
                const qpx = second.start.x - first.start.x, qpy = second.start.y - first.start.y;
                const denominator = cross(rx, ry, sx, sy);
                const scale = Math.max(1, Math.hypot(rx, ry) * Math.hypot(sx, sy));
                const parallelTolerance = 1e-10 * scale;

                if (Math.abs(denominator) > parallelTolerance) {
                    const t = cross(qpx, qpy, sx, sy) / denominator;
                    const u = cross(qpx, qpy, rx, ry) / denominator;
                    if (t >= -1e-10 && t <= 1 + 1e-10 && u >= -1e-10 && u <= 1 + 1e-10) {
                        pushSplit(first, t);
                        pushSplit(second, u);
                    }
                    return;
                }

                if (Math.abs(cross(qpx, qpy, rx, ry)) > parallelTolerance) return;
                [second.start, second.end].forEach(point => {
                    if (pointOnSegment(point, first.start, first.end, G.EPSILON_MM * 2)) {
                        pushSplit(first, parameterOnSegment(point, first.start, first.end));
                    }
                });
                [first.start, first.end].forEach(point => {
                    if (pointOnSegment(point, second.start, second.end, G.EPSILON_MM * 2)) {
                        pushSplit(second, parameterOnSegment(point, second.start, second.end));
                    }
                });
            });
        });
    }

    function fragmentEdges(edges) {
        const output = [];
        edges.forEach(edge => {
            edge.splits.sort((a, b) => a - b);
            for (let index = 1; index < edge.splits.length; index += 1) {
                const start = interpolate(edge.start, edge.end, edge.splits[index - 1]);
                const end = interpolate(edge.start, edge.end, edge.splits[index]);
                if (G.distance(start, end) > G.EPSILON_MM) output.push(Object.freeze({ start, end, source: edge.source }));
            }
        });
        return output;
    }

    function operationState(operation, insideFirst, insideSecond) {
        if (operation === "union") return Boolean(insideFirst || insideSecond);
        if (operation === "intersect") return Boolean(insideFirst && insideSecond);
        if (operation === "subtract") return Boolean(insideFirst && !insideSecond);
        throw new Error(`Unsupported boolean operation: ${operation}`);
    }

    function orientedBoundaryFragments(firstPolygon, secondPolygon, operation, toleranceMm) {
        const firstEdges = edgeList(firstPolygon, "first");
        const secondEdges = edgeList(secondPolygon, "second");
        splitAtIntersections(firstEdges, secondEdges);
        const fragments = [...fragmentEdges(firstEdges), ...fragmentEdges(secondEdges)];
        const unique = new Map();

        fragments.forEach(fragment => {
            const dx = fragment.end.x - fragment.start.x, dy = fragment.end.y - fragment.start.y;
            const length = Math.hypot(dx, dy);
            if (length <= G.EPSILON_MM) return;
            const midpoint = rawPoint((fragment.start.x + fragment.end.x) / 2, (fragment.start.y + fragment.end.y) / 2);
            const probe = Math.max(G.EPSILON_MM * 4, Math.min(Math.max(0.002, toleranceMm * 0.1), length * 0.05));
            const nx = -dy / length, ny = dx / length;
            const left = rawPoint(midpoint.x + nx * probe, midpoint.y + ny * probe);
            const right = rawPoint(midpoint.x - nx * probe, midpoint.y - ny * probe);
            const leftState = operationState(operation, pointInPolygon(left, firstPolygon), pointInPolygon(left, secondPolygon));
            const rightState = operationState(operation, pointInPolygon(right, firstPolygon), pointInPolygon(right, secondPolygon));
            if (leftState === rightState) return;
            const start = leftState ? fragment.start : fragment.end;
            const end = leftState ? fragment.end : fragment.start;
            const key = undirectedKey(start, end);
            if (!unique.has(key)) unique.set(key, Object.freeze({ start: G.point(start.x, start.y), end: G.point(end.x, end.y) }));
        });
        return [...unique.values()];
    }

    function booleanProbe(firstPolygon, secondPolygon, operation, point) {
        return operationState(operation, pointInPolygon(point, firstPolygon), pointInPolygon(point, secondPolygon));
    }

    function chooseNext(incomingStart, vertex, candidates, firstPolygon, secondPolygon, operation, toleranceMm) {
        if (candidates.length === 1) return candidates[0];
        const inX = vertex.x - incomingStart.x, inY = vertex.y - incomingStart.y;
        const inLength = Math.max(G.EPSILON_MM, Math.hypot(inX, inY));
        const nInX = -inY / inLength, nInY = inX / inLength;
        const probe = Math.max(G.EPSILON_MM * 6, toleranceMm * 0.12);
        const scored = candidates.map(candidate => {
            const outX = candidate.end.x - candidate.start.x, outY = candidate.end.y - candidate.start.y;
            const outLength = Math.max(G.EPSILON_MM, Math.hypot(outX, outY));
            const nOutX = -outY / outLength, nOutY = outX / outLength;
            let sampleX = nInX + nOutX, sampleY = nInY + nOutY;
            const sampleLength = Math.hypot(sampleX, sampleY);
            if (sampleLength <= 1e-9) { sampleX = nOutX; sampleY = nOutY; }
            else { sampleX /= sampleLength; sampleY /= sampleLength; }
            const sample = rawPoint(vertex.x + sampleX * probe, vertex.y + sampleY * probe);
            const interior = booleanProbe(firstPolygon, secondPolygon, operation, sample);
            const turn = Math.abs(Math.atan2(cross(inX, inY, outX, outY), dot(inX, inY, outX, outY)));
            return { candidate, interior, turn };
        });
        scored.sort((a, b) => Number(b.interior) - Number(a.interior) || a.turn - b.turn);
        return scored[0].candidate;
    }

    function fragmentsToContours(fragments, firstPolygon, secondPolygon, operation, toleranceMm) {
        const outgoing = new Map();
        fragments.forEach((fragment, index) => {
            const key = keyPoint(fragment.start);
            if (!outgoing.has(key)) outgoing.set(key, []);
            outgoing.get(key).push({ ...fragment, index });
        });
        const visited = new Set();
        const contours = [];

        fragments.forEach((fragment, startIndex) => {
            if (visited.has(startIndex)) return;
            visited.add(startIndex);
            const startKey = keyPoint(fragment.start);
            const points = [fragment.start, fragment.end];
            let previous = fragment.start;
            let current = fragment.end;
            let guard = fragments.length + 4;

            while (keyPoint(current) !== startKey && guard > 0) {
                guard -= 1;
                const candidates = (outgoing.get(keyPoint(current)) || []).filter(candidate => !visited.has(candidate.index));
                if (!candidates.length) break;
                const next = chooseNext(previous, current, candidates, firstPolygon, secondPolygon, operation, toleranceMm);
                visited.add(next.index);
                previous = current;
                current = next.end;
                points.push(current);
            }

            if (keyPoint(current) !== startKey) return;
            points.pop();
            const cleaned = simplifyCollinear(points, toleranceMm);
            if (cleaned.length >= 3 && Math.abs(signedArea(cleaned)) > toleranceMm * toleranceMm) {
                contours.push(Object.freeze(cleaned.map(point => G.point(point.x, point.y))));
            }
        });
        return contours;
    }

    function selfIntersects(polygon) {
        const edges = edgeList(polygon, "self");
        for (let firstIndex = 0; firstIndex < edges.length; firstIndex += 1) {
            for (let secondIndex = firstIndex + 1; secondIndex < edges.length; secondIndex += 1) {
                if (secondIndex === firstIndex + 1) continue;
                if (firstIndex === 0 && secondIndex === edges.length - 1) continue;
                const first = edges[firstIndex], second = edges[secondIndex];
                const rx = first.end.x - first.start.x, ry = first.end.y - first.start.y;
                const sx = second.end.x - second.start.x, sy = second.end.y - second.start.y;
                const denominator = cross(rx, ry, sx, sy);
                const qpx = second.start.x - first.start.x, qpy = second.start.y - first.start.y;
                if (Math.abs(denominator) <= 1e-10) {
                    if (Math.abs(cross(qpx, qpy, rx, ry)) > 1e-8) continue;
                    if ([second.start, second.end].some(point => pointOnSegment(point, first.start, first.end)) ||
                        [first.start, first.end].some(point => pointOnSegment(point, second.start, second.end))) return true;
                    continue;
                }
                const t = cross(qpx, qpy, sx, sy) / denominator;
                const u = cross(qpx, qpy, rx, ry) / denominator;
                if (t > 1e-9 && t < 1 - 1e-9 && u > 1e-9 && u < 1 - 1e-9) return true;
            }
        }
        return false;
    }

    function coreContours(firstPolygon, secondPolygon, operation, toleranceMm) {
        const fragments = orientedBoundaryFragments(firstPolygon, secondPolygon, operation, toleranceMm);
        return fragmentsToContours(fragments, firstPolygon, secondPolygon, operation, toleranceMm);
    }

    function resultArea(contours) {
        return G.roundMm((contours || []).reduce((sum, contour) => sum + signedArea(contour), 0));
    }

    function booleanContours(first, second, operation, options = {}) {
        const mode = String(operation || "").toLowerCase();
        if (!OPERATIONS.includes(mode)) return Object.freeze({ ok: false, reason: "unsupported_operation", contours: Object.freeze([]) });
        if (!isBooleanOperand(first) || !isBooleanOperand(second)) return Object.freeze({ ok: false, reason: "unsupported_operand", contours: Object.freeze([]) });
        const toleranceMm = Math.max(0.01, Number(options.toleranceMm) || DEFAULT_TOLERANCE_MM);
        const firstData = objectToPolygon(first, toleranceMm);
        const secondData = objectToPolygon(second, toleranceMm);
        if (!firstData || !secondData) return Object.freeze({ ok: false, reason: "invalid_geometry", contours: Object.freeze([]) });
        if (selfIntersects(firstData.points) || selfIntersects(secondData.points)) {
            return Object.freeze({ ok: false, reason: "self_intersection", contours: Object.freeze([]), toleranceMm });
        }

        let contours;
        if (mode === "exclude") {
            contours = [
                ...coreContours(firstData.points, secondData.points, "subtract", toleranceMm),
                ...coreContours(secondData.points, firstData.points, "subtract", toleranceMm),
            ];
        } else {
            contours = coreContours(firstData.points, secondData.points, mode, toleranceMm);
        }
        return Object.freeze({
            ok: true,
            operation: mode,
            contours: Object.freeze(contours),
            toleranceMm: G.roundMm(toleranceMm),
            approximated: Boolean(firstData.approximated || secondData.approximated),
            areaMm2: resultArea(contours),
        });
    }

    root.BooleanGeometryDomain = Object.freeze({
        DEFAULT_TOLERANCE_MM,
        OPERATIONS,
        CLOSED_TYPES,
        isBooleanOperand,
        objectToPolygon,
        signedArea,
        resultArea,
        pointInPolygon,
        selfIntersects,
        booleanContours,
    });
})();
