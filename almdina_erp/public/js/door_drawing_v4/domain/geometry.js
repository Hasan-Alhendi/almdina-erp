(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);

    const MM_PRECISION = 3;
    const EPSILON_MM = 0.001;

    function finiteNumber(value, fallback = 0) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function roundMm(value) {
        return Number(finiteNumber(value).toFixed(MM_PRECISION));
    }

    function point(xMm, yMm) {
        return Object.freeze({
            xMm: roundMm(xMm),
            yMm: roundMm(yMm),
        });
    }

    function clonePoint(value) {
        return point(value && value.xMm, value && value.yMm);
    }

    function distance(a, b) {
        const dx = finiteNumber(b && b.xMm) - finiteNumber(a && a.xMm);
        const dy = finiteNumber(b && b.yMm) - finiteNumber(a && a.yMm);
        return Math.hypot(dx, dy);
    }

    function angleDeg(origin, target) {
        const dx = finiteNumber(target && target.xMm) - finiteNumber(origin && origin.xMm);
        const dy = finiteNumber(target && target.yMm) - finiteNumber(origin && origin.yMm);
        return normalizeAngleDeg(Math.atan2(dy, dx) * 180 / Math.PI);
    }

    function normalizeAngleDeg(value) {
        const normalized = finiteNumber(value) % 360;
        return normalized < 0 ? normalized + 360 : normalized;
    }

    function shortestAngleDeltaDeg(a, b) {
        let delta = normalizeAngleDeg(a) - normalizeAngleDeg(b);
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        return delta;
    }

    function pointFromPolar(origin, lengthMm, angleDegrees) {
        const radians = normalizeAngleDeg(angleDegrees) * Math.PI / 180;
        return point(
            finiteNumber(origin && origin.xMm) + Math.cos(radians) * finiteNumber(lengthMm),
            finiteNumber(origin && origin.yMm) + Math.sin(radians) * finiteNumber(lengthMm)
        );
    }

    function isSamePoint(a, b, toleranceMm = EPSILON_MM) {
        return distance(a, b) <= Math.max(EPSILON_MM, finiteNumber(toleranceMm, EPSILON_MM));
    }

    function assertPositiveLength(start, end) {
        if (distance(start, end) <= EPSILON_MM) {
            throw new Error("Drawing segment length must be greater than zero");
        }
    }

    root.Geometry = Object.freeze({
        MM_PRECISION,
        EPSILON_MM,
        finiteNumber,
        roundMm,
        point,
        clonePoint,
        distance,
        angleDeg,
        normalizeAngleDeg,
        shortestAngleDeltaDeg,
        pointFromPolar,
        isSamePoint,
        assertPositiveLength,
    });
})();