(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before shape-preserving stroke domain");

    const DEFAULTS = Object.freeze({
        smoothingPasses: 2,
        smoothingRadius: 2,
        smoothingStrength: 0.68,
        maxCurveDisplacementMm: 0.8,
        simplifyToleranceMm: 0.22,
        cornerAngleDeg: 32,
        cornerWindow: 2,
        cornerProtectionRadius: 1,
        minimumCornerArmMm: 3.5,
        minimumStraightSamples: 4,
        minimumStraightLengthMm: 14,
        straightRatio: 1.055,
        straightMinimumDeviationMm: 0.55,
        straightDeviationBaseMm: 0.35,
        straightDeviationSlope: 0.004,
        straightMaximumDeviationMm: 1.8,
        overallMaximumDeviationMm: 2.0,
    });

    function p(value) {
        return G.point(value && value.x, value && value.y);
    }

    function dedupe(points, minimumMm = G.EPSILON_MM) {
        const result = [];
        const minimum = Math.max(G.EPSILON_MM, Number(minimumMm) || G.EPSILON_MM);
        for (const raw of Array.isArray(points) ? points : []) {
            const point = p(raw);
            if (!result.length || G.distance(result[result.length - 1], point) >= minimum) result.push(point);
        }
        return result;
    }

    function polylineLength(points) {
        let total = 0;
        for (let index = 1; index < points.length; index += 1) {
            total += G.distance(points[index - 1], points[index]);
        }
        return total;
    }

    function distanceToSegment(point, start, end) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length2 = dx * dx + dy * dy;
        if (length2 <= G.EPSILON_MM * G.EPSILON_MM) return G.distance(point, start);
        const ratio = Math.max(0, Math.min(1,
            ((point.x - start.x) * dx + (point.y - start.y) * dy) / length2
        ));
        return Math.hypot(
            point.x - (start.x + dx * ratio),
            point.y - (start.y + dy * ratio)
        );
    }

    function maxSourceDeviation(source, target) {
        const from = dedupe(source);
        const to = dedupe(target);
        if (!from.length || !to.length) return 0;
        if (to.length === 1) return Math.max(...from.map(point => G.distance(point, to[0])));
        let maximum = 0;
        for (const point of from) {
            let nearest = Infinity;
            for (let index = 1; index < to.length; index += 1) {
                nearest = Math.min(nearest, distanceToSegment(point, to[index - 1], to[index]));
            }
            maximum = Math.max(maximum, nearest);
        }
        return G.roundMm(maximum);
    }

    function directionDeg(start, end) {
        return Math.atan2(end.y - start.y, end.x - start.x) * 180 / Math.PI;
    }

    function angleDifferenceDeg(first, second) {
        let delta = Number(second) - Number(first);
        while (delta <= -180) delta += 360;
        while (delta > 180) delta -= 360;
        return Math.abs(delta);
    }

    function turnAngleDeg(previous, current, next) {
        if (G.distance(previous, current) <= G.EPSILON_MM || G.distance(current, next) <= G.EPSILON_MM) return 0;
        return angleDifferenceDeg(directionDeg(previous, current), directionDeg(current, next));
    }

    function detectCorners(points, options = {}) {
        const input = dedupe(points);
        if (input.length < 5) return Object.freeze([]);
        const windowSize = Math.max(1, Math.floor(Number(options.cornerWindow) || DEFAULTS.cornerWindow));
        const threshold = Math.max(1, Number(options.cornerAngleDeg) || DEFAULTS.cornerAngleDeg);
        const minimumArmMm = Math.max(G.EPSILON_MM, Number(options.minimumCornerArmMm) || DEFAULTS.minimumCornerArmMm);
        const candidates = [];
        for (let index = windowSize; index < input.length - windowSize; index += 1) {
            const previous = input[index - windowSize];
            const current = input[index];
            const next = input[index + windowSize];
            if (G.distance(previous, current) < minimumArmMm || G.distance(current, next) < minimumArmMm) continue;
            const angleDeg = turnAngleDeg(previous, current, next);
            if (angleDeg >= threshold) candidates.push({ index, angleDeg });
        }

        // Keep only the strongest corner in a small local neighborhood. This stops
        // hand jitter around a real corner from producing several fake corners.
        const minimumIndexGap = Math.max(2, windowSize);
        const chosen = [];
        for (const candidate of candidates.sort((a, b) => b.angleDeg - a.angleDeg)) {
            if (chosen.some(item => Math.abs(item.index - candidate.index) < minimumIndexGap)) continue;
            chosen.push(candidate);
        }
        chosen.sort((a, b) => a.index - b.index);
        return Object.freeze(chosen.map(item => Object.freeze({ index: item.index, angleDeg: G.roundMm(item.angleDeg) })));
    }

    function clampDisplacement(origin, candidate, maximumMm) {
        const limit = Math.max(0, Number(maximumMm) || 0);
        if (limit <= G.EPSILON_MM) return p(origin);
        const distance = G.distance(origin, candidate);
        if (distance <= limit) return p(candidate);
        const ratio = limit / distance;
        return G.point(
            origin.x + (candidate.x - origin.x) * ratio,
            origin.y + (candidate.y - origin.y) * ratio
        );
    }

    function protectedIndices(points, corners, options = {}) {
        const result = new Set([0, Math.max(0, points.length - 1)]);
        const radius = Math.max(0, Math.floor(Number(options.cornerProtectionRadius) || DEFAULTS.cornerProtectionRadius));
        for (const corner of corners || []) {
            for (let offset = -radius; offset <= radius; offset += 1) {
                const index = corner.index + offset;
                if (index >= 0 && index < points.length) result.add(index);
            }
        }
        return result;
    }

    function smoothBounded(points, corners = [], options = {}) {
        const original = dedupe(points);
        if (original.length <= 2) return original;
        const protectedSet = protectedIndices(original, corners, options);
        const passes = Math.max(0, Math.min(4, Math.floor(Number(options.smoothingPasses) || DEFAULTS.smoothingPasses)));
        const radius = Math.max(1, Math.min(4, Math.floor(Number(options.smoothingRadius) || DEFAULTS.smoothingRadius)));
        const strength = Math.max(0, Math.min(1, Number(options.smoothingStrength) || DEFAULTS.smoothingStrength));
        const maximumMm = Math.max(0, Number(options.maxCurveDisplacementMm) || DEFAULTS.maxCurveDisplacementMm);
        let current = original.map(p);

        for (let pass = 0; pass < passes; pass += 1) {
            const next = current.map(p);
            for (let index = 1; index < current.length - 1; index += 1) {
                if (protectedSet.has(index)) {
                    next[index] = original[index];
                    continue;
                }
                let totalWeight = 0;
                let x = 0;
                let y = 0;
                for (let offset = -radius; offset <= radius; offset += 1) {
                    const sampleIndex = index + offset;
                    if (sampleIndex < 0 || sampleIndex >= current.length) continue;
                    const weight = radius + 1 - Math.abs(offset);
                    totalWeight += weight;
                    x += current[sampleIndex].x * weight;
                    y += current[sampleIndex].y * weight;
                }
                const average = G.point(x / totalWeight, y / totalWeight);
                const candidate = G.point(
                    current[index].x + (average.x - current[index].x) * strength,
                    current[index].y + (average.y - current[index].y) * strength
                );
                next[index] = clampDisplacement(original[index], candidate, maximumMm);
            }
            current = next;
        }
        current[0] = original[0];
        current[current.length - 1] = original[original.length - 1];
        return current.map(p);
    }

    function simplifyRdp(points, toleranceMm) {
        const input = dedupe(points);
        const tolerance = Math.max(G.EPSILON_MM, Number(toleranceMm) || DEFAULTS.simplifyToleranceMm);
        if (input.length <= 2) return input;
        const start = input[0];
        const end = input[input.length - 1];
        let maximum = -1;
        let split = -1;
        for (let index = 1; index < input.length - 1; index += 1) {
            const deviation = distanceToSegment(input[index], start, end);
            if (deviation > maximum) {
                maximum = deviation;
                split = index;
            }
        }
        if (maximum <= tolerance || split < 0) return [start, end];
        const left = simplifyRdp(input.slice(0, split + 1), tolerance);
        const right = simplifyRdp(input.slice(split), tolerance);
        return [...left.slice(0, -1), ...right];
    }

    function adaptiveStraightLimit(chordMm, options = {}) {
        const minimum = Math.max(0, Number(options.straightMinimumDeviationMm) || DEFAULTS.straightMinimumDeviationMm);
        const base = Math.max(0, Number(options.straightDeviationBaseMm) || DEFAULTS.straightDeviationBaseMm);
        const slope = Math.max(0, Number(options.straightDeviationSlope) || DEFAULTS.straightDeviationSlope);
        const maximum = Math.max(minimum, Number(options.straightMaximumDeviationMm) || DEFAULTS.straightMaximumDeviationMm);
        return Math.min(maximum, Math.max(minimum, base + Math.max(0, chordMm) * slope));
    }

    function straightQuality(points, options = {}) {
        const input = dedupe(points);
        if (input.length < 2) return Object.freeze({ eligible: false, chordMm: 0, maximumDeviationMm: Infinity, ratio: Infinity, limitMm: 0 });
        const start = input[0];
        const end = input[input.length - 1];
        const chordMm = G.distance(start, end);
        if (chordMm <= G.EPSILON_MM) return Object.freeze({ eligible: false, chordMm, maximumDeviationMm: Infinity, ratio: Infinity, limitMm: 0 });
        let maximumDeviationMm = 0;
        for (const point of input) maximumDeviationMm = Math.max(maximumDeviationMm, distanceToSegment(point, start, end));
        const ratio = polylineLength(input) / chordMm;
        const limitMm = adaptiveStraightLimit(chordMm, options);
        const minimumSamples = Math.max(3, Math.floor(Number(options.minimumStraightSamples) || DEFAULTS.minimumStraightSamples));
        const minimumLengthMm = Math.max(G.EPSILON_MM, Number(options.minimumStraightLengthMm) || DEFAULTS.minimumStraightLengthMm);
        const maximumRatio = Math.max(1, Number(options.straightRatio) || DEFAULTS.straightRatio);
        const eligible = input.length >= minimumSamples
            && chordMm >= minimumLengthMm
            && maximumDeviationMm <= limitMm
            && ratio <= maximumRatio;
        return Object.freeze({
            eligible,
            chordMm: G.roundMm(chordMm),
            maximumDeviationMm: G.roundMm(maximumDeviationMm),
            ratio,
            limitMm: G.roundMm(limitMm),
        });
    }

    function samePoints(first, second) {
        if (!Array.isArray(first) || !Array.isArray(second) || first.length !== second.length) return false;
        return first.every((point, index) => G.distance(point, second[index]) <= G.EPSILON_MM);
    }

    function appendSpan(target, span) {
        if (!span.length) return target;
        if (!target.length) return [...span];
        const start = G.distance(target[target.length - 1], span[0]) <= G.EPSILON_MM ? 1 : 0;
        return [...target, ...span.slice(start)];
    }

    function cleanStroke(points, options = {}) {
        const raw = dedupe(points);
        if (raw.length < 2) {
            return Object.freeze({
                points: Object.freeze(raw),
                changed: false,
                cornerIndices: Object.freeze([]),
                straightenedRuns: Object.freeze([]),
                maximumDeviationMm: 0,
            });
        }

        const corners = detectCorners(raw, options);
        const smoothed = smoothBounded(raw, corners, options);
        const boundaries = [0, ...corners.map(item => item.index), raw.length - 1]
            .filter((value, index, list) => index === 0 || value !== list[index - 1]);
        const straightenedRuns = [];
        let cleaned = [];
        const simplifyToleranceMm = Math.max(G.EPSILON_MM, Number(options.simplifyToleranceMm) || DEFAULTS.simplifyToleranceMm);
        const curveGuardMm = Math.max(
            G.EPSILON_MM,
            (Number(options.maxCurveDisplacementMm) || DEFAULTS.maxCurveDisplacementMm) + simplifyToleranceMm
        );

        for (let boundaryIndex = 1; boundaryIndex < boundaries.length; boundaryIndex += 1) {
            const startIndex = boundaries[boundaryIndex - 1];
            const endIndex = boundaries[boundaryIndex];
            if (endIndex <= startIndex) continue;
            const rawSpan = raw.slice(startIndex, endIndex + 1);
            const smoothSpan = smoothed.slice(startIndex, endIndex + 1);
            const quality = straightQuality(rawSpan, options);
            if (quality.eligible) {
                const exact = [rawSpan[0], rawSpan[rawSpan.length - 1]];
                cleaned = appendSpan(cleaned, exact);
                straightenedRuns.push(Object.freeze({
                    startIndex,
                    endIndex,
                    chordMm: quality.chordMm,
                    maximumDeviationMm: quality.maximumDeviationMm,
                    limitMm: quality.limitMm,
                }));
                continue;
            }

            let simplified = simplifyRdp(smoothSpan, simplifyToleranceMm);
            if (maxSourceDeviation(rawSpan, simplified) > curveGuardMm) simplified = smoothSpan;
            cleaned = appendSpan(cleaned, simplified);
        }

        if (cleaned.length < 2) cleaned = smoothed;
        const overallLimitMm = Math.max(
            curveGuardMm,
            Number(options.overallMaximumDeviationMm) || DEFAULTS.overallMaximumDeviationMm
        );
        let maximumDeviationMm = maxSourceDeviation(raw, cleaned);
        if (maximumDeviationMm > overallLimitMm) {
            cleaned = smoothed;
            straightenedRuns.length = 0;
            maximumDeviationMm = maxSourceDeviation(raw, cleaned);
        }

        cleaned[0] = raw[0];
        cleaned[cleaned.length - 1] = raw[raw.length - 1];
        cleaned = dedupe(cleaned);
        return Object.freeze({
            points: Object.freeze(cleaned.map(p)),
            changed: !samePoints(raw, cleaned),
            cornerIndices: Object.freeze(corners.map(item => item.index)),
            straightenedRuns: Object.freeze(straightenedRuns.slice()),
            maximumDeviationMm: G.roundMm(maximumDeviationMm),
        });
    }

    root.ShapePreservingStrokeDomain = Object.freeze({
        DEFAULTS,
        dedupe,
        polylineLength,
        distanceToSegment,
        maxSourceDeviation,
        turnAngleDeg,
        detectCorners,
        clampDisplacement,
        smoothBounded,
        simplifyRdp,
        adaptiveStraightLimit,
        straightQuality,
        samePoints,
        cleanStroke,
    });
})();
