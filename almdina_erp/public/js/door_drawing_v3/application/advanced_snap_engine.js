(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    const G = root.Geometry;
    if (!Base || !G || typeof Base.collectSegments !== "function") throw new Error("Advanced snapping requires unified snapping");

    const INTERSECTION_CAPTURE_PX = 11;
    const PERPENDICULAR_CAPTURE_PX = 11;
    const PARALLEL_CAPTURE_PX = 9;
    const ANGLE_TOLERANCE_DEG = 3;
    const RANK = Object.freeze({ ...(Base.INTENT_RANK || {}), joint: 1000, intersection: 940, perpendicular: 900, "parallel-equal": 880, midpoint: 820, surface: 700, parallel: 650, "equal-length": 620, alignment: 500, fallback: 100 });

    const rank = kind => Number(RANK[String(kind || "fallback")]) || RANK.fallback;
    const score = (kind, distanceMm, priority = 0) => rank(kind) * 100000 + (Number(priority) || 0) * 100 - Math.max(0, Number(distanceMm) || 0);
    const angleDistance180 = (a, b) => { const d = Math.abs((((Number(a) || 0) - (Number(b) || 0)) % 180 + 180) % 180); return Math.min(d, 180 - d); };
    const cross = (ax, ay, bx, by) => ax * by - ay * bx;

    function segmentIntersection(first, second) {
        const p = first.start, q = second.start;
        const rx = first.end.x - p.x, ry = first.end.y - p.y;
        const sx = second.end.x - q.x, sy = second.end.y - q.y;
        const den = cross(rx, ry, sx, sy);
        if (Math.abs(den) <= G.EPSILON_MM) return null;
        const qx = q.x - p.x, qy = q.y - p.y;
        const t = cross(qx, qy, sx, sy) / den;
        const u = cross(qx, qy, rx, ry) / den;
        if (t < -1e-8 || t > 1 + 1e-8 || u < -1e-8 || u > 1 + 1e-8) return null;
        return G.point(p.x + rx * t, p.y + ry * t);
    }

    function collectIntersections(document, options = {}) {
        const segments = Base.collectSegments(document, options), out = [], seen = new Set();
        for (let i = 0; i < segments.length; i += 1) for (let j = i + 1; j < segments.length; j += 1) {
            const a = segments[i], b = segments[j];
            if (String(a.objectId) === String(b.objectId)) continue;
            const point = segmentIntersection(a, b);
            if (!point) continue;
            const key = `${G.roundMm(point.x, 3)}:${G.roundMm(point.y, 3)}`;
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(Object.freeze({ objectId: `${a.objectId}|${b.objectId}`, role: `intersection:${a.role}:${b.role}`, point, priority: Math.max(a.priority || 0, b.priority || 0), kind: "intersection", first: a, second: b }));
        }
        return Object.freeze(out);
    }

    function nearestPointFeature(features, candidate, toleranceMm, kind) {
        let best = null;
        for (const target of features || []) {
            const distanceMm = G.distance(candidate, target.point);
            if (distanceMm > toleranceMm) continue;
            const next = { target, point: target.point, distanceMm, kind };
            if (!best || score(kind, distanceMm, target.priority) > score(best.kind, best.distanceMm, best.target.priority)) best = next;
        }
        return best;
    }

    function projectInfinite(point, segment) {
        const a = segment.start, b = segment.end;
        const dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
        if (len2 <= G.EPSILON_MM * G.EPSILON_MM) return null;
        const t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / len2;
        return { point: G.point(a.x + dx * t, a.y + dy * t), t };
    }

    function axisCompatible(point, axis, reference) {
        if (!axis || !reference) return true;
        return axis === "horizontal" ? Math.abs(point.y - reference.y) <= Base.AXIS_EPSILON_MM : Math.abs(point.x - reference.x) <= Base.AXIS_EPSILON_MM;
    }

    function perpendicularCandidate(document, reference, candidate, toleranceMm, options, axis) {
        let best = null;
        for (const segment of Base.collectSegments(document, options)) {
            const foot = projectInfinite(reference, segment);
            if (!foot || foot.t < -1e-8 || foot.t > 1 + 1e-8 || !axisCompatible(foot.point, axis, reference)) continue;
            const distanceMm = G.distance(candidate, foot.point);
            if (distanceMm > toleranceMm) continue;
            const target = Object.freeze({ objectId: String(segment.objectId), role: String(segment.role), point: foot.point, priority: segment.priority || 0, kind: "perpendicular", segmentStart: segment.start, segmentEnd: segment.end });
            const next = { target, point: foot.point, distanceMm, kind: "perpendicular" };
            if (!best || score(next.kind, distanceMm, target.priority) > score(best.kind, best.distanceMm, best.target.priority)) best = next;
        }
        return best;
    }

    function parallelCandidate(document, reference, candidate, toleranceMm, equalToleranceMm, options, axis) {
        const length = G.distance(reference, candidate);
        if (length <= G.EPSILON_MM) return null;
        const requestedAngle = G.angleDeg(reference, candidate);
        let best = null;
        for (const segment of Base.collectSegments(document, options)) {
            const segmentAngle = G.angleDeg(segment.start, segment.end);
            if (angleDistance180(requestedAngle, segmentAngle) > ANGLE_TOLERANCE_DEG) continue;
            const segmentLength = G.distance(segment.start, segment.end);
            const equal = Math.abs(segmentLength - length) <= equalToleranceMm;
            const exactLength = equal ? segmentLength : length;
            const forward = G.pointAt(reference, exactLength, segmentAngle), backward = G.pointAt(reference, exactLength, segmentAngle + 180);
            const point = G.distance(candidate, forward) <= G.distance(candidate, backward) ? forward : backward;
            if (!axisCompatible(point, axis, reference)) continue;
            const distanceMm = G.distance(candidate, point);
            if (distanceMm > Math.max(toleranceMm, equal ? equalToleranceMm : 0)) continue;
            const kind = equal ? "parallel-equal" : "parallel";
            const target = Object.freeze({ objectId: String(segment.objectId), role: String(segment.role), point, priority: segment.priority || 0, kind, segmentStart: segment.start, segmentEnd: segment.end, lengthMm: exactLength });
            const next = { target, point, distanceMm, kind, lengthMm: exactLength };
            if (!best || score(kind, distanceMm, target.priority) > score(best.kind, best.distanceMm, best.target.priority)) best = next;
        }
        return best;
    }

    function resultScore(result) { return result && result.snapped ? score(result.kind, result.distanceMm, result.target && result.target.priority) : -Infinity; }

    function toResult(base, raw, reference, axis, candidate) {
        const intents = candidate.kind === "parallel-equal" ? Object.freeze(["parallel", "equal-length"]) : Object.freeze([candidate.kind]);
        return Object.freeze({ ...base, point: candidate.point, rawPoint: raw, snapped: true, target: candidate.target, distanceMm: G.roundMm(candidate.distanceMm), axis, anchor: reference, kind: candidate.kind, intents, smartGuide: Object.freeze({ type: candidate.kind, point: candidate.point, targetPoint: candidate.target.point, anchor: reference, segmentStart: candidate.target.segmentStart || null, segmentEnd: candidate.target.segmentEnd || null, lengthMm: candidate.lengthMm || candidate.target.lengthMm || null, intents }) });
    }

    function resolvePoint(document, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const base = Base.resolvePoint(document, raw, options);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const axis = base.axis || null;
        const probe = axis ? base.point : raw;
        const candidates = [];
        const intersectionMm = Base.worldTolerance(options.viewportScale, options.intersectionSnapPx || INTERSECTION_CAPTURE_PX);
        const intersection = nearestPointFeature(collectIntersections(document, options), probe, intersectionMm, "intersection");
        if (intersection && axisCompatible(intersection.point, axis, reference)) candidates.push(intersection);
        if (reference) {
            const perpendicularMm = Base.worldTolerance(options.viewportScale, options.perpendicularSnapPx || PERPENDICULAR_CAPTURE_PX);
            const parallelMm = Base.worldTolerance(options.viewportScale, options.parallelSnapPx || PARALLEL_CAPTURE_PX);
            const equalMm = Base.worldTolerance(options.viewportScale, options.equalLengthSnapPx || Base.EQUAL_LENGTH_SNAP_PX || 10);
            const perpendicular = perpendicularCandidate(document, reference, probe, perpendicularMm, options, axis);
            const parallel = parallelCandidate(document, reference, probe, parallelMm, equalMm, options, axis);
            if (perpendicular) candidates.push(perpendicular);
            if (parallel) candidates.push(parallel);
        }
        let best = null;
        for (const item of candidates) if (!best || score(item.kind, item.distanceMm, item.target.priority) > score(best.kind, best.distanceMm, best.target.priority)) best = item;
        return !best || resultScore(base) >= score(best.kind, best.distanceMm, best.target.priority) ? base : toResult(base, raw, reference, axis, best);
    }

    function resolveObjectMove(document, object, deltaX, deltaY, options = {}) {
        const base = Base.resolveObjectMove(document, object, deltaX, deltaY, options);
        const rawObject = G.translateObject(object, G.number(deltaX), G.number(deltaY));
        const sources = (Base.featuresForObject ? Base.featuresForObject(rawObject) : Base.objectAnchors(rawObject)).filter(feature => feature.kind === "joint" || (Base.isJoint && Base.isJoint(feature)));
        const targets = collectIntersections(document, { excludeId: object && object.id });
        const toleranceMm = Base.worldTolerance(options.viewportScale, options.intersectionSnapPx || INTERSECTION_CAPTURE_PX);
        let best = null;
        for (const source of sources) for (const target of targets) {
            const distanceMm = G.distance(source.point, target.point);
            if (distanceMm > toleranceMm) continue;
            const next = { source, target, distanceMm, kind: "intersection" };
            if (!best || score(next.kind, distanceMm, target.priority) > score(best.kind, best.distanceMm, best.target.priority)) best = next;
        }
        if (!best || resultScore(base) >= score(best.kind, best.distanceMm, best.target.priority)) return base;
        const objectResult = G.translateObject(rawObject, best.target.point.x - best.source.point.x, best.target.point.y - best.source.point.y);
        return Object.freeze({ ...base, object: objectResult, point: best.target.point, rawPoint: best.source.point, snapped: true, target: best.target, source: best.source, distanceMm: G.roundMm(best.distanceMm), kind: "intersection", sticky: false, smartGuide: Object.freeze({ type: "intersection", point: best.target.point, targetPoint: best.target.point, intents: Object.freeze(["intersection"]) }) });
    }

    root.Snapping = Object.freeze({ ...Base, INTERSECTION_CAPTURE_PX, PERPENDICULAR_CAPTURE_PX, PARALLEL_CAPTURE_PX, ANGLE_TOLERANCE_DEG, INTENT_RANK: RANK, segmentIntersection, collectIntersections, resolvePoint, resolveObjectMove });
    root.AdvancedSnapEngine = Object.freeze({ INTERSECTION_CAPTURE_PX, PERPENDICULAR_CAPTURE_PX, PARALLEL_CAPTURE_PX, ANGLE_TOLERANCE_DEG, INTENT_RANK: RANK, segmentIntersection, collectIntersections, resolvePoint, resolveObjectMove });
})();
