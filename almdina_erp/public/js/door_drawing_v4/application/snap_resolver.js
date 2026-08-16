(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 domain must load before snap resolver");

    const DEFAULT_ANGLE_INCREMENT_DEG = 45;
    const DEFAULT_ANGLE_TOLERANCE_DEG = 4;

    function angleSemantic(angleDeg) {
        const normalized = Math.round(geometry.normalizeAngleDeg(angleDeg));
        if (normalized === 0 || normalized === 180) return "horizontal";
        if (normalized === 90 || normalized === 270) return "vertical";
        return "angle";
    }

    function nearestAngleCandidate(origin, rawPoint, options = {}) {
        if (!origin) return null;
        const lengthMm = geometry.distance(origin, rawPoint);
        if (lengthMm <= geometry.EPSILON_MM) return null;

        const incrementDeg = Math.max(1, geometry.finiteNumber(options.angleIncrementDeg, DEFAULT_ANGLE_INCREMENT_DEG));
        const toleranceDeg = Math.max(0, geometry.finiteNumber(options.angleToleranceDeg, DEFAULT_ANGLE_TOLERANCE_DEG));
        const rawAngleDeg = geometry.angleDeg(origin, rawPoint);
        const snappedAngleDeg = geometry.normalizeAngleDeg(Math.round(rawAngleDeg / incrementDeg) * incrementDeg);
        const deltaDeg = Math.abs(geometry.shortestAngleDeltaDeg(rawAngleDeg, snappedAngleDeg));
        if (deltaDeg > toleranceDeg) return null;

        return Object.freeze({
            type: "angle",
            semantic: angleSemantic(snappedAngleDeg),
            point: geometry.pointFromPolar(origin, lengthMm, snappedAngleDeg),
            nodeId: null,
            distanceMm: 0,
            angleDeg: snappedAngleDeg,
            score: 100 + deltaDeg / Math.max(1, toleranceDeg),
        });
    }

    function endpointCandidates(document, rawPoint, options = {}) {
        const toleranceMm = Math.max(0, geometry.finiteNumber(options.toleranceMm));
        const excluded = new Set((options.excludeNodeIds || []).map(String));
        if (!toleranceMm) return [];

        return (document.nodes || [])
            .filter(node => !excluded.has(node.id))
            .map(node => ({ node, distanceMm: geometry.distance(node, rawPoint) }))
            .filter(candidate => candidate.distanceMm <= toleranceMm)
            .map(candidate => Object.freeze({
                type: "endpoint",
                semantic: "endpoint",
                point: geometry.point(candidate.node.xMm, candidate.node.yMm),
                nodeId: candidate.node.id,
                distanceMm: candidate.distanceMm,
                angleDeg: null,
                score: candidate.distanceMm / Math.max(toleranceMm, geometry.EPSILON_MM),
            }));
    }

    function resolve(document, request = {}) {
        const rawPoint = geometry.clonePoint(request.rawPoint);
        const origin = request.origin ? geometry.clonePoint(request.origin) : null;
        const candidates = [
            ...endpointCandidates(document, rawPoint, request),
        ];
        const angle = nearestAngleCandidate(origin, rawPoint, request);
        if (angle) candidates.push(angle);

        if (!candidates.length) {
            return Object.freeze({
                type: "free",
                semantic: null,
                point: rawPoint,
                nodeId: null,
                angleDeg: null,
                candidates: Object.freeze([]),
            });
        }

        candidates.sort((a, b) => a.score - b.score);
        const winner = candidates[0];
        return Object.freeze({
            type: winner.type,
            semantic: winner.semantic,
            point: winner.point,
            nodeId: winner.nodeId,
            angleDeg: winner.angleDeg,
            candidates: Object.freeze([...candidates]),
        });
    }

    root.SnapResolver = Object.freeze({
        DEFAULT_ANGLE_INCREMENT_DEG,
        DEFAULT_ANGLE_TOLERANCE_DEG,
        resolve,
    });
})();