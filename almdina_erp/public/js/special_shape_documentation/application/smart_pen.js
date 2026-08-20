(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const distance = (a, b) => Math.hypot(b.xMm - a.xMm, b.yMm - a.yMm);
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
    function clean(rawPoints, options = {}) {
        const toleranceMm = Number(options.toleranceMm || 6);
        const joinToleranceMm = Number(options.joinToleranceMm || 24);
        const simplified = simplify(rawPoints, toleranceMm);
        const snapped = simplified.map((point, index) => index ? snapPoint(simplified[index - 1], point) : { ...point });
        const suggestClose = snapped.length > 2 && distance(snapped[0], snapped[snapped.length - 1]) <= joinToleranceMm;
        return Object.freeze({ points: snapped, suggestClose });
    }
    function close(points) {
        if (!points.length) return [];
        const next = points.map(point => ({ ...point }));
        next[next.length - 1] = { ...next[0] };
        return next;
    }
    root.SmartPen = Object.freeze({ distance, simplify, snapPoint, clean, close });
})();
