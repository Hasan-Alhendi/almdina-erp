(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    if (!geometry) throw new Error("Drawing V4 geometry must load before stroke interpreter");

    const DEFAULTS = Object.freeze({
        minSampleDistanceMm: 0.8,
        simplificationToleranceMm: 2.5,
        closeToleranceMm: 8,
        angleIncrementDeg: 45,
        angleToleranceDeg: 7,
    });

    function pointLineDistance(point, start, end) {
        const dx = end.xMm - start.xMm;
        const dy = end.yMm - start.yMm;
        const lengthSquared = dx * dx + dy * dy;
        if (lengthSquared <= geometry.EPSILON_MM * geometry.EPSILON_MM) {
            return geometry.distance(point, start);
        }
        const px = point.xMm - start.xMm;
        const py = point.yMm - start.yMm;
        const t = Math.max(0, Math.min(1, (px * dx + py * dy) / lengthSquared));
        const projected = geometry.point(start.xMm + dx * t, start.yMm + dy * t);
        return geometry.distance(point, projected);
    }

    function dedupeSamples(rawPoints, minDistanceMm) {
        const source = Array.isArray(rawPoints) ? rawPoints : [];
        const result = [];
        source.forEach(raw => {
            if (!raw) return;
            const point = geometry.clonePoint(raw);
            if (!result.length || geometry.distance(result[result.length - 1], point) >= minDistanceMm) {
                result.push(point);
            }
        });
        if (source.length && result.length) {
            const last = geometry.clonePoint(source[source.length - 1]);
            if (geometry.distance(result[result.length - 1], last) > geometry.EPSILON_MM) result.push(last);
        }
        return result;
    }

    function simplifyRdp(points, epsilonMm) {
        if (!Array.isArray(points) || points.length <= 2) return [...(points || [])];
        let maxDistance = -1;
        let splitIndex = -1;
        const first = points[0];
        const last = points[points.length - 1];
        for (let index = 1; index < points.length - 1; index += 1) {
            const distance = pointLineDistance(points[index], first, last);
            if (distance > maxDistance) {
                maxDistance = distance;
                splitIndex = index;
            }
        }
        if (maxDistance <= epsilonMm || splitIndex < 0) return [first, last];
        const left = simplifyRdp(points.slice(0, splitIndex + 1), epsilonMm);
        const right = simplifyRdp(points.slice(splitIndex), epsilonMm);
        return [...left.slice(0, -1), ...right];
    }

    function snapAngle(start, end, incrementDeg, toleranceDeg) {
        const lengthMm = geometry.distance(start, end);
        if (lengthMm <= geometry.EPSILON_MM) return end;
        const rawAngle = geometry.angleDeg(start, end);
        const snappedAngle = Math.round(rawAngle / incrementDeg) * incrementDeg;
        const delta = Math.abs(geometry.shortestAngleDeltaDeg(rawAngle, snappedAngle));
        if (delta > toleranceDeg) return end;
        return geometry.pointFromPolar(start, lengthMm, snappedAngle);
    }

    function cleanAngles(points, options) {
        if (points.length <= 1) return [...points];
        const result = [geometry.clonePoint(points[0])];
        for (let index = 1; index < points.length; index += 1) {
            const previous = result[result.length - 1];
            const snapped = snapAngle(
                previous,
                points[index],
                options.angleIncrementDeg,
                options.angleToleranceDeg
            );
            if (geometry.distance(previous, snapped) > geometry.EPSILON_MM) result.push(snapped);
        }
        return result;
    }

    function interpret(rawPoints, input = {}) {
        const options = Object.freeze({
            minSampleDistanceMm: Math.max(geometry.EPSILON_MM, geometry.finiteNumber(input.minSampleDistanceMm, DEFAULTS.minSampleDistanceMm)),
            simplificationToleranceMm: Math.max(geometry.EPSILON_MM, geometry.finiteNumber(input.simplificationToleranceMm, DEFAULTS.simplificationToleranceMm)),
            closeToleranceMm: Math.max(0, geometry.finiteNumber(input.closeToleranceMm, DEFAULTS.closeToleranceMm)),
            angleIncrementDeg: Math.max(1, geometry.finiteNumber(input.angleIncrementDeg, DEFAULTS.angleIncrementDeg)),
            angleToleranceDeg: Math.max(0, geometry.finiteNumber(input.angleToleranceDeg, DEFAULTS.angleToleranceDeg)),
        });
        const sampled = dedupeSamples(rawPoints, options.minSampleDistanceMm);
        if (sampled.length < 2) {
            return Object.freeze({ ok: false, code: "too-short", points: Object.freeze([]), closed: false, sourcePointCount: sampled.length });
        }

        const sourceClosed = sampled.length >= 4
            && geometry.distance(sampled[0], sampled[sampled.length - 1]) <= options.closeToleranceMm;
        const simplificationSource = sourceClosed ? [...sampled.slice(0, -1), sampled[0]] : sampled;
        let simplified = simplifyRdp(simplificationSource, options.simplificationToleranceMm);
        if (sourceClosed && simplified.length > 1 && geometry.distance(simplified[0], simplified[simplified.length - 1]) <= options.closeToleranceMm) {
            simplified = simplified.slice(0, -1);
        }
        let cleaned = cleanAngles(simplified, options);
        cleaned = cleaned.filter((point, index) => index === 0 || geometry.distance(cleaned[index - 1], point) > geometry.EPSILON_MM);

        const minimumPoints = sourceClosed ? 3 : 2;
        if (cleaned.length < minimumPoints) {
            return Object.freeze({ ok: false, code: "too-simple", points: Object.freeze(cleaned), closed: false, sourcePointCount: sampled.length });
        }
        return Object.freeze({
            ok: true,
            code: "ok",
            points: Object.freeze(cleaned.map(geometry.clonePoint)),
            closed: sourceClosed,
            sourcePointCount: sampled.length,
            simplifiedPointCount: cleaned.length,
        });
    }

    root.StrokeInterpreter = Object.freeze({
        DEFAULTS,
        pointLineDistance,
        dedupeSamples,
        simplifyRdp,
        interpret,
    });
})();
