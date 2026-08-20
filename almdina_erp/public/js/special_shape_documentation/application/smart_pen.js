(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const distance = (a, b) => Math.hypot(b.xMm - a.xMm, b.yMm - a.yMm);
    const copy = point => ({ xMm: Number(point.xMm), yMm: Number(point.yMm) });
    function perpendicular(point, start, end) {
        const dx = end.xMm - start.xMm, dy = end.yMm - start.yMm;
        if (!dx && !dy) return distance(point, start);
        const t = Math.max(0, Math.min(1, ((point.xMm - start.xMm) * dx + (point.yMm - start.yMm) * dy) / (dx * dx + dy * dy)));
        return distance(point, { xMm: start.xMm + t * dx, yMm: start.yMm + t * dy });
    }
    function simplify(points, toleranceMm = 6) {
        if (!Array.isArray(points) || points.length <= 2) return (points || []).map(point => ({ ...point }));
        let max = 0, index = 0;
        for (let i = 1; i < points.length - 1; i += 1) {
            const current = perpendicular(points[i], points[0], points[points.length - 1]);
            if (current > max) { max = current; index = i; }
        }
        if (max <= toleranceMm) return [{ ...points[0] }, { ...points[points.length - 1] }];
        return [...simplify(points.slice(0, index + 1), toleranceMm).slice(0, -1), ...simplify(points.slice(index), toleranceMm)];
    }
    function snapPoint(start, end, toleranceDeg = 8) {
        const dx = end.xMm - start.xMm, dy = end.yMm - start.yMm;
        const length = Math.hypot(dx, dy);
        if (!length) return { ...end };
        const angle = Math.atan2(dy, dx) * 180 / Math.PI;
        const candidates = [-180, -135, -90, -45, 0, 45, 90, 135, 180];
        let best = angle, delta = Infinity;
        candidates.forEach(candidate => { const current = Math.abs(candidate - angle); if (current < delta) { delta = current; best = candidate; } });
        if (delta > toleranceDeg) return { ...end };
        const radians = best * Math.PI / 180;
        return { xMm: start.xMm + Math.cos(radians) * length, yMm: start.yMm + Math.sin(radians) * length };
    }
    function normalize(points, minimumGapMm = 0.35) {
        const clean = [];
        (Array.isArray(points) ? points : []).forEach(point => {
            if (!point || !Number.isFinite(Number(point.xMm)) || !Number.isFinite(Number(point.yMm))) return;
            const next = copy(point);
            if (!clean.length || distance(clean[clean.length - 1], next) >= minimumGapMm) clean.push(next);
        });
        return clean;
    }
    function smooth(points, passes = 2) {
        let current = (points || []).map(copy);
        for (let pass = 0; pass < Math.max(0, Number(passes) || 0) && current.length > 2; pass += 1) {
            const next = [{ ...current[0] }];
            for (let index = 1; index < current.length - 1; index += 1) {
                const before = current[index - 1], point = current[index], after = current[index + 1];
                next.push({
                    xMm: (before.xMm + point.xMm * 2 + after.xMm) / 4,
                    yMm: (before.yMm + point.yMm * 2 + after.yMm) / 4,
                });
            }
            next.push({ ...current[current.length - 1] });
            current = next;
        }
        return current;
    }
    function pathLength(points) {
        return (points || []).slice(1).reduce((total, point, index) => total + distance(points[index], point), 0);
    }
    function isStraight(points, options = {}) {
        if (!Array.isArray(points) || points.length < 2) return false;
        const chord = distance(points[0], points[points.length - 1]);
        if (chord < 1) return false;
        const maxDeviation = points.slice(1, -1).reduce((maximum, point) => Math.max(maximum, perpendicular(point, points[0], points[points.length - 1])), 0);
        const tolerance = Number(options.straightToleranceMm) || Math.max(2, Math.min(8, chord * 0.018));
        return maxDeviation <= tolerance && pathLength(points) / chord <= 1.04;
    }
    function resample(points, spacingMm = 3, maxPoints = 240) {
        if (!Array.isArray(points) || points.length <= 2) return (points || []).map(copy);
        const segmentLengths = points.slice(1).map((point, index) => distance(points[index], point));
        const total = segmentLengths.reduce((sum, value) => sum + value, 0);
        if (!total) return [{ ...points[0] }];
        const count = Math.max(2, Math.min(Math.max(2, Number(maxPoints) || 240), Math.ceil(total / Math.max(0.5, Number(spacingMm) || 3)) + 1));
        const sampled = [];
        let segment = 0, covered = 0;
        for (let index = 0; index < count; index += 1) {
            const target = total * index / (count - 1);
            while (segment < segmentLengths.length - 1 && covered + segmentLengths[segment] < target) {
                covered += segmentLengths[segment];
                segment += 1;
            }
            const length = segmentLengths[segment] || 1;
            const ratio = Math.max(0, Math.min(1, (target - covered) / length));
            sampled.push({
                xMm: points[segment].xMm + (points[segment + 1].xMm - points[segment].xMm) * ratio,
                yMm: points[segment].yMm + (points[segment + 1].yMm - points[segment].yMm) * ratio,
            });
        }
        return sampled;
    }
    function clean(rawPoints, options = {}) {
        const toleranceMm = Number(options.toleranceMm || 6);
        const joinToleranceMm = Number(options.joinToleranceMm || 24);
        const normalized = normalize(rawPoints);
        if (normalized.length < 2) return Object.freeze({ points: normalized, suggestClose: false, kind: "curve" });
        const smoothed = smooth(normalized, options.smoothingPasses ?? 2);
        const suggestClose = smoothed.length > 2 && distance(smoothed[0], smoothed[smoothed.length - 1]) <= joinToleranceMm;
        if (isStraight(smoothed, options)) {
            return Object.freeze({ points: [{ ...smoothed[0] }, snapPoint(smoothed[0], smoothed[smoothed.length - 1])], suggestClose, kind: "straight" });
        }

        const maximumPoints = Math.max(16, Math.min(500, Number(options.maxCurvePoints) || 240));
        const spacingMm = Number(options.curveSpacingMm) || Math.max(1.5, Math.min(6, toleranceMm * 0.55));
        const sampled = resample(smoothed, spacingMm, maximumPoints);
        const curveToleranceMm = Number(options.curveToleranceMm) || Math.max(0.45, Math.min(1.25, toleranceMm * 0.16));
        let curved = simplify(sampled, curveToleranceMm);
        const minimumCurvePoints = Math.min(sampled.length, Math.max(8, Math.ceil(pathLength(smoothed) / Math.max(14, toleranceMm * 2.5))));
        if (curved.length < minimumCurvePoints) curved = resample(smoothed, pathLength(smoothed) / Math.max(1, minimumCurvePoints - 1), minimumCurvePoints);
        return Object.freeze({ points: curved, suggestClose, kind: "curve" });
    }
    function close(points) {
        if (!points.length) return [];
        const next = points.map(point => ({ ...point }));
        next[next.length - 1] = { ...next[0] };
        return next;
    }
    root.SmartPen = Object.freeze({ distance, simplify, snapPoint, normalize, smooth, pathLength, isStraight, resample, clean, close });
})();
