(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before intelligent freehand policy");

    const DEFAULTS = Object.freeze({
        minSampleMm: 0.8,
        simplifyToleranceMm: 1.2,
        straightToleranceMm: 1.6,
        straightRatio: 1.035,
        circleResidualRatio: 0.035,
        arcResidualRatio: 0.03,
        minimumArcSweepDeg: 20,
        maximumArcSweepDeg: 335,
    });

    function p(value) { return G.point(value && value.x, value && value.y); }
    function dedupe(points, minimumMm = G.EPSILON_MM) {
        const result = [];
        for (const raw of Array.isArray(points) ? points : []) {
            const point = p(raw);
            if (!result.length || G.distance(result[result.length - 1], point) >= minimumMm) result.push(point);
        }
        return result;
    }

    function appendSample(points, point, minSampleMm = DEFAULTS.minSampleMm) {
        const result = Array.isArray(points) ? points.slice() : [];
        const next = p(point);
        if (!result.length || G.distance(result[result.length - 1], next) >= Math.max(G.EPSILON_MM, Number(minSampleMm) || 0)) result.push(next);
        return result;
    }

    function polylineLength(points) {
        let total = 0;
        for (let index = 1; index < points.length; index += 1) total += G.distance(points[index - 1], points[index]);
        return total;
    }

    function distanceToSegment(point, start, end) {
        const px = point.x, py = point.y, ax = start.x, ay = start.y, bx = end.x, by = end.y;
        const dx = bx - ax, dy = by - ay;
        const length2 = dx * dx + dy * dy;
        if (length2 <= G.EPSILON_MM * G.EPSILON_MM) return G.distance(point, start);
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length2));
        return Math.hypot(px - (ax + dx * t), py - (ay + dy * t));
    }

    function smooth(points, passes = 2) {
        let current = dedupe(points);
        const count = Math.max(0, Math.min(4, Number(passes) || 0));
        for (let pass = 0; pass < count && current.length > 2; pass += 1) {
            const next = [current[0]];
            for (let index = 1; index < current.length - 1; index += 1) {
                const a = current[index - 1], b = current[index], c = current[index + 1];
                next.push(G.point(a.x * 0.2 + b.x * 0.6 + c.x * 0.2, a.y * 0.2 + b.y * 0.6 + c.y * 0.2));
            }
            next.push(current[current.length - 1]);
            current = next;
        }
        return current;
    }

    function simplifyRdp(points, toleranceMm = DEFAULTS.simplifyToleranceMm) {
        const input = dedupe(points);
        if (input.length <= 2) return input;
        const tolerance = Math.max(G.EPSILON_MM, Number(toleranceMm) || DEFAULTS.simplifyToleranceMm);
        let maxDistance = -1;
        let splitIndex = -1;
        const start = input[0], end = input[input.length - 1];
        for (let index = 1; index < input.length - 1; index += 1) {
            const distance = distanceToSegment(input[index], start, end);
            if (distance > maxDistance) { maxDistance = distance; splitIndex = index; }
        }
        if (maxDistance <= tolerance || splitIndex < 0) return [start, end];
        const left = simplifyRdp(input.slice(0, splitIndex + 1), tolerance);
        const right = simplifyRdp(input.slice(splitIndex), tolerance);
        return [...left.slice(0, -1), ...right];
    }

    function lineQuality(points) {
        const input = dedupe(points);
        if (input.length < 2) return Object.freeze({ eligible: false, maxDeviationMm: Infinity, ratio: Infinity, chordMm: 0 });
        const start = input[0], end = input[input.length - 1];
        const chordMm = G.distance(start, end);
        if (chordMm < G.EPSILON_MM) return Object.freeze({ eligible: false, maxDeviationMm: Infinity, ratio: Infinity, chordMm });
        let maxDeviationMm = 0;
        for (const point of input) maxDeviationMm = Math.max(maxDeviationMm, distanceToSegment(point, start, end));
        const ratio = polylineLength(input) / chordMm;
        return Object.freeze({ eligible: true, maxDeviationMm, ratio, chordMm });
    }

    function circumcircle(a, b, c) {
        const ax = a.x, ay = a.y, bx = b.x, by = b.y, cx = c.x, cy = c.y;
        const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
        if (Math.abs(d) <= G.EPSILON_MM) return null;
        const a2 = ax * ax + ay * ay, b2 = bx * bx + by * by, c2 = cx * cx + cy * cy;
        const ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d;
        const uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d;
        const center = G.point(ux, uy);
        const radiusMm = G.distance(center, a);
        return radiusMm >= G.EPSILON_MM ? Object.freeze({ center, radiusMm: G.roundMm(radiusMm) }) : null;
    }

    function radialResidual(points, circle) {
        if (!circle || !points.length) return Infinity;
        let sum = 0;
        for (const point of points) {
            const delta = G.distance(circle.center, point) - circle.radiusMm;
            sum += delta * delta;
        }
        return Math.sqrt(sum / points.length);
    }

    function fittedCircle(points, closed = false) {
        const input = dedupe(points);
        if (input.length < 5) return null;
        const first = input[0];
        const a = first;
        const b = input[Math.floor((input.length - 1) / 3)];
        const c = input[Math.floor((input.length - 1) * 2 / 3)];
        let circle = circumcircle(a, b, c);
        if (!circle && !closed) circle = circumcircle(first, input[Math.floor(input.length / 2)], input[input.length - 1]);
        if (!circle) return null;
        return Object.freeze({ ...circle, residualMm: G.roundMm(radialResidual(input, circle)) });
    }

    function unwrapSweep(points, center) {
        if (points.length < 2) return Object.freeze({ sweepDeg: 0, consistency: 0 });
        let sweep = 0;
        let positive = 0;
        let negative = 0;
        let previous = G.angleDeg(center, points[0]);
        for (let index = 1; index < points.length; index += 1) {
            const angle = G.angleDeg(center, points[index]);
            const delta = G.normalizeAngle(angle - previous);
            sweep += delta;
            if (delta > 0.05) positive += 1;
            if (delta < -0.05) negative += 1;
            previous = angle;
        }
        const directional = positive + negative;
        const consistency = directional ? Math.max(positive, negative) / directional : 0;
        return Object.freeze({ sweepDeg: G.roundMm(sweep), consistency });
    }

    function recognize(points, options = {}) {
        const raw = dedupe(points);
        if (raw.length < 2) return Object.freeze({ type: "none", points: raw, confidence: 0 });
        const simplifyToleranceMm = Math.max(G.EPSILON_MM, Number(options.simplifyToleranceMm) || DEFAULTS.simplifyToleranceMm);
        const straightToleranceMm = Math.max(G.EPSILON_MM, Number(options.straightToleranceMm) || DEFAULTS.straightToleranceMm);
        const closed = Boolean(options.closed);
        const prepared = smooth(raw, options.smoothingPasses == null ? 2 : options.smoothingPasses);
        const quality = lineQuality(prepared);
        if (!closed && quality.eligible && quality.maxDeviationMm <= straightToleranceMm && quality.ratio <= (Number(options.straightRatio) || DEFAULTS.straightRatio)) {
            return Object.freeze({ type: "line", start: raw[0], end: raw[raw.length - 1], confidence: Math.max(0, 1 - quality.maxDeviationMm / Math.max(straightToleranceMm, G.EPSILON_MM)), rawPoints: raw });
        }

        const circle = fittedCircle(prepared, closed);
        if (circle) {
            const residualLimit = Math.max(straightToleranceMm, circle.radiusMm * (closed ? DEFAULTS.circleResidualRatio : DEFAULTS.arcResidualRatio));
            const sweep = unwrapSweep(prepared, circle.center);
            if (closed && circle.residualMm <= residualLimit && Math.abs(sweep.sweepDeg) >= 280 && sweep.consistency >= 0.82) {
                return Object.freeze({ type: "circle", center: circle.center, radiusMm: circle.radiusMm, confidence: Math.max(0, 1 - circle.residualMm / residualLimit), rawPoints: raw });
            }
            const absSweep = Math.abs(sweep.sweepDeg);
            if (!closed && circle.residualMm <= residualLimit && absSweep >= DEFAULTS.minimumArcSweepDeg && absSweep <= DEFAULTS.maximumArcSweepDeg && sweep.consistency >= 0.9) {
                return Object.freeze({
                    type: "arc",
                    center: circle.center,
                    radiusMm: circle.radiusMm,
                    startAngleDeg: G.angleDeg(circle.center, raw[0]),
                    sweepAngleDeg: sweep.sweepDeg,
                    confidence: Math.max(0, 1 - circle.residualMm / residualLimit),
                    rawPoints: raw,
                });
            }
        }

        let cleaned = simplifyRdp(prepared, simplifyToleranceMm);
        if (cleaned.length < 2) cleaned = [raw[0], raw[raw.length - 1]];
        cleaned[0] = raw[0];
        cleaned[cleaned.length - 1] = closed ? raw[0] : raw[raw.length - 1];
        if (closed && cleaned.length > 2 && G.distance(cleaned[0], cleaned[cleaned.length - 1]) < G.EPSILON_MM) cleaned = cleaned.slice(0, -1);
        return Object.freeze({ type: "path", points: cleaned.map(p), closed, confidence: 1, rawPoints: raw });
    }

    root.SmartFreehandPolicy = Object.freeze({
        DEFAULTS,
        dedupe,
        appendSample,
        polylineLength,
        distanceToSegment,
        smooth,
        simplifyRdp,
        lineQuality,
        circumcircle,
        radialResidual,
        fittedCircle,
        unwrapSweep,
        recognize,
    });
})();
