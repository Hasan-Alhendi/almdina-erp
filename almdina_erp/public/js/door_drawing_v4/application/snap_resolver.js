(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 domain must load before snap resolver");

    const DEFAULT_ANGLE_INCREMENT_DEG = 45;
    const DEFAULT_ANGLE_TOLERANCE_DEG = 4;
    const DEFAULT_RELEASE_MULTIPLIER = 1.4;
    const PRIORITY = Object.freeze({
        close: 0,
        endpoint: 10,
        intersection: 20,
        midpoint: 30,
        perpendicular: 40,
        edge: 45,
        parallel: 50,
        extension: 60,
        horizontal: 70,
        vertical: 71,
        angle: 80,
        grid: 90,
    });
    const segmentCache = new WeakMap();

    function stableId(value) {
        return String(value ?? "");
    }

    function angleSemantic(angleDeg) {
        const normalized = Math.round(geometry.normalizeAngleDeg(angleDeg));
        if (normalized === 0 || normalized === 180 || normalized === 360) return "horizontal";
        if (normalized === 90 || normalized === 270) return "vertical";
        return "angle";
    }

    function freezeGuide(kind, start, end, referenceSegmentId = null) {
        return Object.freeze({
            kind: String(kind),
            start: geometry.clonePoint(start),
            end: geometry.clonePoint(end),
            referenceSegmentId: referenceSegmentId ? stableId(referenceSegmentId) : null,
        });
    }

    function candidate(input) {
        const semantic = String(input.semantic || input.type || "");
        const priority = Number.isFinite(input.priority) ? input.priority : (PRIORITY[semantic] ?? 999);
        const distanceMm = Math.max(0, geometry.finiteNumber(input.distanceMm));
        return Object.freeze({
            key: String(input.key || `${input.type}:${semantic}`),
            type: String(input.type || semantic),
            semantic,
            point: geometry.clonePoint(input.point),
            nodeId: input.nodeId ? stableId(input.nodeId) : null,
            segmentId: input.segmentId ? stableId(input.segmentId) : null,
            referenceSegmentId: input.referenceSegmentId ? stableId(input.referenceSegmentId) : null,
            distanceMm,
            angleDeg: input.angleDeg === null || input.angleDeg === undefined ? null : geometry.normalizeAngleDeg(input.angleDeg),
            priority,
            score: priority * 1000 + distanceMm,
            guides: Object.freeze([...(input.guides || [])]),
        });
    }

    function segments(document) {
        if (segmentCache.has(document)) return segmentCache.get(document).segments;
        const records = (document.segments || []).map(segment => {
            if (segment.type !== "line") return null;
            const start = documentModel.nodeById(document, segment.startNodeId);
            const end = documentModel.nodeById(document, segment.endNodeId);
            if (!start || !end) return null;
            const dx = end.xMm - start.xMm;
            const dy = end.yMm - start.yMm;
            const lengthSquared = dx * dx + dy * dy;
            if (lengthSquared <= geometry.EPSILON_MM * geometry.EPSILON_MM) return null;
            return Object.freeze({
                id: stableId(segment.id),
                start,
                end,
                dx,
                dy,
                lengthSquared,
                lengthMm: Math.sqrt(lengthSquared),
            });
        }).filter(Boolean);
        const frozen = Object.freeze(records);
        segmentCache.set(document, { segments: frozen, intersections: null });
        return frozen;
    }

    function projection(record, sourcePoint) {
        const px = sourcePoint.xMm - record.start.xMm;
        const py = sourcePoint.yMm - record.start.yMm;
        const t = (px * record.dx + py * record.dy) / record.lengthSquared;
        return Object.freeze({
            t,
            point: geometry.point(
                record.start.xMm + record.dx * t,
                record.start.yMm + record.dy * t
            ),
        });
    }

    function lineIntersection(origin, dx, dy, record) {
        const denominator = dx * record.dy - dy * record.dx;
        if (Math.abs(denominator) <= 1e-9) return null;
        const qpx = record.start.xMm - origin.xMm;
        const qpy = record.start.yMm - origin.yMm;
        const t = (qpx * record.dy - qpy * record.dx) / denominator;
        const u = (qpx * dy - qpy * dx) / denominator;
        return Object.freeze({
            t,
            u,
            point: geometry.point(origin.xMm + dx * t, origin.yMm + dy * t),
        });
    }

    function interiorIntersection(first, second) {
        const hit = lineIntersection(first.start, first.dx, first.dy, second);
        const endpointGuard = 1e-8;
        if (!hit) return null;
        if (
            hit.t <= endpointGuard
            || hit.t >= 1 - endpointGuard
            || hit.u <= endpointGuard
            || hit.u >= 1 - endpointGuard
        ) return null;
        return hit.point;
    }

    function intersections(document) {
        segments(document);
        const cached = segmentCache.get(document);
        if (cached.intersections) return cached.intersections;
        const records = cached.segments;
        const result = [];
        for (let firstIndex = 0; firstIndex < records.length; firstIndex += 1) {
            for (let secondIndex = firstIndex + 1; secondIndex < records.length; secondIndex += 1) {
                const first = records[firstIndex];
                const second = records[secondIndex];
                const point = interiorIntersection(first, second);
                if (!point) continue;
                const ids = [first.id, second.id].sort();
                result.push(Object.freeze({
                    key: `intersection:${ids[0]}:${ids[1]}`,
                    point,
                    firstSegmentId: first.id,
                    secondSegmentId: second.id,
                }));
            }
        }
        cached.intersections = Object.freeze(result);
        return cached.intersections;
    }

    function withinTolerance(rawPoint, targetPoint, toleranceMm) {
        const distanceMm = geometry.distance(rawPoint, targetPoint);
        return distanceMm <= toleranceMm + geometry.EPSILON_MM ? distanceMm : null;
    }

    function notAnchor(origin, point) {
        return !origin || geometry.distance(origin, point) > geometry.EPSILON_MM;
    }

    function closeCandidates(document, rawPoint, request, toleranceMm) {
        if (!request.canClose || !request.closeNodeId) return [];
        const node = documentModel.nodeById(document, request.closeNodeId);
        if (!node) return [];
        const distanceMm = withinTolerance(rawPoint, node, toleranceMm);
        if (distanceMm === null) return [];
        return [candidate({
            key: `close:${node.id}`,
            type: "close",
            semantic: "close",
            point: node,
            nodeId: node.id,
            distanceMm,
            priority: PRIORITY.close,
        })];
    }

    function endpointCandidates(document, rawPoint, request, toleranceMm) {
        const excluded = new Set((request.excludeNodeIds || []).map(stableId));
        return (document.nodes || [])
            .filter(node => !excluded.has(stableId(node.id)))
            .map(node => ({ node, distanceMm: withinTolerance(rawPoint, node, toleranceMm) }))
            .filter(item => item.distanceMm !== null)
            .map(item => candidate({
                key: `endpoint:${item.node.id}`,
                type: "endpoint",
                semantic: "endpoint",
                point: item.node,
                nodeId: item.node.id,
                distanceMm: item.distanceMm,
                priority: PRIORITY.endpoint,
            }));
    }

    function storedIntersectionCandidates(document, rawPoint, request, toleranceMm) {
        return intersections(document)
            .map(item => ({ item, distanceMm: withinTolerance(rawPoint, item.point, toleranceMm) }))
            .filter(entry => entry.distanceMm !== null && notAnchor(request.origin, entry.item.point))
            .map(entry => candidate({
                key: entry.item.key,
                type: "intersection",
                semantic: "intersection",
                point: entry.item.point,
                nodeId: null,
                distanceMm: entry.distanceMm,
                priority: PRIORITY.intersection,
            }));
    }

    function liveIntersectionCandidates(document, rawPoint, request, toleranceMm) {
        if (!request.origin) return [];
        const dx = rawPoint.xMm - request.origin.xMm;
        const dy = rawPoint.yMm - request.origin.yMm;
        if (dx * dx + dy * dy <= geometry.EPSILON_MM * geometry.EPSILON_MM) return [];
        const endpointGuard = 1e-8;
        return segments(document).map(record => {
            const hit = lineIntersection(request.origin, dx, dy, record);
            if (
                !hit
                || hit.t <= endpointGuard
                || hit.t > 1 + endpointGuard
                || hit.u < -endpointGuard
                || hit.u > 1 + endpointGuard
            ) return null;
            if (!notAnchor(request.origin, hit.point)) return null;
            const distanceMm = withinTolerance(rawPoint, hit.point, toleranceMm);
            if (distanceMm === null) return null;
            return candidate({
                key: `intersection:live:${record.id}`,
                type: "intersection",
                semantic: "intersection",
                point: hit.point,
                nodeId: null,
                segmentId: record.id,
                referenceSegmentId: record.id,
                distanceMm,
                priority: PRIORITY.intersection,
                guides: [freezeGuide("intersection", request.origin, hit.point, record.id)],
            });
        }).filter(Boolean);
    }

    function intersectionCandidates(document, rawPoint, request, toleranceMm) {
        return [
            ...storedIntersectionCandidates(document, rawPoint, request, toleranceMm),
            ...liveIntersectionCandidates(document, rawPoint, request, toleranceMm),
        ];
    }

    function midpointCandidates(document, rawPoint, request, toleranceMm) {
        return segments(document).map(record => {
            const midpoint = geometry.point(
                (record.start.xMm + record.end.xMm) / 2,
                (record.start.yMm + record.end.yMm) / 2
            );
            return { record, midpoint, distanceMm: withinTolerance(rawPoint, midpoint, toleranceMm) };
        }).filter(entry => entry.distanceMm !== null && notAnchor(request.origin, entry.midpoint))
            .map(entry => candidate({
                key: `midpoint:${entry.record.id}`,
                type: "midpoint",
                semantic: "midpoint",
                point: entry.midpoint,
                nodeId: null,
                segmentId: entry.record.id,
                distanceMm: entry.distanceMm,
                priority: PRIORITY.midpoint,
            }));
    }

    function perpendicularCandidates(document, rawPoint, request, toleranceMm) {
        if (!request.origin) return [];
        return segments(document).map(record => {
            const foot = projection(record, request.origin);
            if (foot.t < -1e-8 || foot.t > 1 + 1e-8 || !notAnchor(request.origin, foot.point)) return null;
            const distanceMm = withinTolerance(rawPoint, foot.point, toleranceMm);
            if (distanceMm === null) return null;
            return candidate({
                key: `perpendicular:${record.id}`,
                type: "perpendicular",
                semantic: "perpendicular",
                point: foot.point,
                nodeId: null,
                segmentId: record.id,
                referenceSegmentId: record.id,
                distanceMm,
                priority: PRIORITY.perpendicular,
                guides: [freezeGuide("perpendicular", request.origin, foot.point, record.id)],
            });
        }).filter(Boolean);
    }

    function edgeCandidates(document, rawPoint, request, toleranceMm) {
        const endpointGuard = 1e-8;
        return segments(document).map(record => {
            const projected = projection(record, rawPoint);
            if (projected.t <= endpointGuard || projected.t >= 1 - endpointGuard) return null;
            if (!notAnchor(request.origin, projected.point)) return null;
            const distanceMm = withinTolerance(rawPoint, projected.point, toleranceMm);
            if (distanceMm === null) return null;
            return candidate({
                key: `edge:${record.id}`,
                type: "edge",
                semantic: "edge",
                point: projected.point,
                nodeId: null,
                segmentId: record.id,
                referenceSegmentId: record.id,
                distanceMm,
                priority: PRIORITY.edge,
            });
        }).filter(Boolean);
    }

    function parallelCandidates(document, rawPoint, request, toleranceMm) {
        if (!request.origin) return [];
        return segments(document).map(record => {
            const relativeX = rawPoint.xMm - request.origin.xMm;
            const relativeY = rawPoint.yMm - request.origin.yMm;
            const along = (relativeX * record.dx + relativeY * record.dy) / record.lengthMm;
            if (Math.abs(along) <= geometry.EPSILON_MM) return null;
            const unitX = record.dx / record.lengthMm;
            const unitY = record.dy / record.lengthMm;
            const point = geometry.point(
                request.origin.xMm + unitX * along,
                request.origin.yMm + unitY * along
            );
            const distanceMm = withinTolerance(rawPoint, point, toleranceMm);
            if (distanceMm === null) return null;
            return candidate({
                key: `parallel:${record.id}`,
                type: "parallel",
                semantic: "parallel",
                point,
                nodeId: null,
                segmentId: record.id,
                referenceSegmentId: record.id,
                distanceMm,
                priority: PRIORITY.parallel,
                guides: [freezeGuide("parallel", request.origin, point, record.id)],
            });
        }).filter(Boolean);
    }

    function extensionCandidates(document, rawPoint, request, toleranceMm) {
        return segments(document).map(record => {
            const projected = projection(record, rawPoint);
            if (projected.t >= -1e-8 && projected.t <= 1 + 1e-8) return null;
            if (!notAnchor(request.origin, projected.point)) return null;
            const distanceMm = withinTolerance(rawPoint, projected.point, toleranceMm);
            if (distanceMm === null) return null;
            const side = projected.t < 0 ? "start" : "end";
            const referenceEnd = side === "start" ? record.start : record.end;
            return candidate({
                key: `extension:${record.id}:${side}`,
                type: "extension",
                semantic: "extension",
                point: projected.point,
                nodeId: null,
                segmentId: record.id,
                referenceSegmentId: record.id,
                distanceMm,
                priority: PRIORITY.extension,
                guides: [freezeGuide("extension", referenceEnd, projected.point, record.id)],
            });
        }).filter(Boolean);
    }

    function nearestAngleCandidate(origin, rawPoint, request, toleranceMm) {
        if (!origin) return null;
        const lengthMm = geometry.distance(origin, rawPoint);
        if (lengthMm <= geometry.EPSILON_MM) return null;
        const incrementDeg = Math.max(1, geometry.finiteNumber(request.angleIncrementDeg, DEFAULT_ANGLE_INCREMENT_DEG));
        const angleToleranceDeg = Math.max(0, geometry.finiteNumber(request.angleToleranceDeg, DEFAULT_ANGLE_TOLERANCE_DEG));
        const rawAngleDeg = geometry.angleDeg(origin, rawPoint);
        const snappedAngleDeg = geometry.normalizeAngleDeg(Math.round(rawAngleDeg / incrementDeg) * incrementDeg);
        const deltaDeg = Math.abs(geometry.shortestAngleDeltaDeg(rawAngleDeg, snappedAngleDeg));
        if (deltaDeg > angleToleranceDeg) return null;
        const point = geometry.pointFromPolar(origin, lengthMm, snappedAngleDeg);
        const distanceMm = withinTolerance(rawPoint, point, toleranceMm);
        if (distanceMm === null) return null;
        const semantic = angleSemantic(snappedAngleDeg);
        return candidate({
            key: `angle:${geometry.roundMm(snappedAngleDeg)}`,
            type: "angle",
            semantic,
            point,
            nodeId: null,
            distanceMm,
            angleDeg: snappedAngleDeg,
            priority: PRIORITY[semantic] ?? PRIORITY.angle,
            guides: [freezeGuide(semantic, origin, point)],
        });
    }

    function gridCandidate(rawPoint, request, toleranceMm) {
        const stepMm = Math.max(0, geometry.finiteNumber(request.gridStepMm));
        if (stepMm <= geometry.EPSILON_MM) return null;
        const point = geometry.point(
            Math.round(rawPoint.xMm / stepMm) * stepMm,
            Math.round(rawPoint.yMm / stepMm) * stepMm
        );
        if (!notAnchor(request.origin, point)) return null;
        const distanceMm = withinTolerance(rawPoint, point, toleranceMm);
        if (distanceMm === null) return null;
        return candidate({
            key: `grid:${geometry.roundMm(point.xMm)}:${geometry.roundMm(point.yMm)}:${geometry.roundMm(stepMm)}`,
            type: "grid",
            semantic: "grid",
            point,
            nodeId: null,
            distanceMm,
            priority: PRIORITY.grid,
        });
    }

    function generate(document, rawPoint, request, toleranceMm) {
        if (toleranceMm <= 0) return [];
        const result = [
            ...closeCandidates(document, rawPoint, request, toleranceMm),
            ...endpointCandidates(document, rawPoint, request, toleranceMm),
            ...intersectionCandidates(document, rawPoint, request, toleranceMm),
            ...midpointCandidates(document, rawPoint, request, toleranceMm),
            ...perpendicularCandidates(document, rawPoint, request, toleranceMm),
            ...edgeCandidates(document, rawPoint, request, toleranceMm),
            ...parallelCandidates(document, rawPoint, request, toleranceMm),
            ...extensionCandidates(document, rawPoint, request, toleranceMm),
        ];
        const angle = nearestAngleCandidate(request.origin, rawPoint, request, toleranceMm);
        if (angle) result.push(angle);
        const grid = gridCandidate(rawPoint, request, toleranceMm);
        if (grid) result.push(grid);
        return result;
    }

    function compareCandidates(left, right) {
        if (left.priority !== right.priority) return left.priority - right.priority;
        if (Math.abs(left.distanceMm - right.distanceMm) > geometry.EPSILON_MM) return left.distanceMm - right.distanceMm;
        return left.key.localeCompare(right.key);
    }

    function asResult(winner, candidates) {
        if (!winner) return null;
        return Object.freeze({
            key: winner.key,
            type: winner.type,
            semantic: winner.semantic,
            point: winner.point,
            nodeId: winner.nodeId,
            segmentId: winner.segmentId,
            referenceSegmentId: winner.referenceSegmentId,
            distanceMm: winner.distanceMm,
            angleDeg: winner.angleDeg,
            priority: winner.priority,
            guides: winner.guides,
            candidates: Object.freeze([...candidates]),
        });
    }

    function resolve(document, request = {}) {
        const rawPoint = geometry.clonePoint(request.rawPoint);
        const origin = request.origin ? geometry.clonePoint(request.origin) : null;
        const toleranceMm = Math.max(0, geometry.finiteNumber(request.toleranceMm));
        const releaseToleranceMm = Math.max(
            toleranceMm,
            geometry.finiteNumber(request.releaseToleranceMm, toleranceMm * DEFAULT_RELEASE_MULTIPLIER)
        );
        const normalizedRequest = { ...request, origin };
        const releaseCandidates = generate(document, rawPoint, normalizedRequest, releaseToleranceMm);
        const acquisitionCandidates = releaseCandidates
            .filter(item => item.distanceMm <= toleranceMm + geometry.EPSILON_MM)
            .sort(compareCandidates);
        const best = acquisitionCandidates[0] || null;
        const previousKey = request.previousSnap && request.previousSnap.key ? String(request.previousSnap.key) : "";
        const sticky = previousKey
            ? releaseCandidates.filter(item => item.key === previousKey).sort(compareCandidates)[0] || null
            : null;
        const winner = sticky && (!best || best.priority >= sticky.priority) ? sticky : best;

        if (!winner) {
            return Object.freeze({
                key: "free",
                type: "free",
                semantic: null,
                point: rawPoint,
                nodeId: null,
                segmentId: null,
                referenceSegmentId: null,
                distanceMm: 0,
                angleDeg: null,
                priority: 999,
                guides: Object.freeze([]),
                candidates: Object.freeze([]),
            });
        }
        return asResult(winner, acquisitionCandidates);
    }

    root.SnapResolver = Object.freeze({
        DEFAULT_ANGLE_INCREMENT_DEG,
        DEFAULT_ANGLE_TOLERANCE_DEG,
        DEFAULT_RELEASE_MULTIPLIER,
        PRIORITY,
        resolve,
    });
})();