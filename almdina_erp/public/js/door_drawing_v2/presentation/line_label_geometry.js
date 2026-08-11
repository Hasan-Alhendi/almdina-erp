(() => {
    "use strict";

    const rootV2 = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const EPSILON = 0.000001;

    function finite(value, fallback = 0) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function normalizedAngle(angleDeg) {
        let angle = finite(angleDeg) % 360;
        if (angle > 180) angle -= 360;
        if (angle <= -180) angle += 360;
        return angle;
    }

    function uprightAngle(angleDeg) {
        let angle = normalizedAngle(angleDeg);
        if (angle > 90) angle -= 180;
        if (angle < -90) angle += 180;
        return angle;
    }

    function placement(start, end, options = {}) {
        const x1 = finite(start && start[0]);
        const y1 = finite(start && start[1]);
        const x2 = finite(end && end[0]);
        const y2 = finite(end && end[1]);
        const dx = x2 - x1;
        const dy = y2 - y1;
        const lengthPx = Math.hypot(dx, dy);
        if (lengthPx <= EPSILON) {
            return Object.freeze({
                valid: false,
                x: x1,
                y: y1,
                angleDeg: 0,
                lengthPx: 0,
                midpoint: Object.freeze({ x: x1, y: y1 }),
                normal: Object.freeze({ x: 0, y: 1 }),
            });
        }

        let normalX = -dy / lengthPx;
        let normalY = dx / lengthPx;

        // Prefer the visually lower side of the segment. For near-vertical
        // segments, prefer the screen-right side so the badge never sits on
        // top of the line and remains predictable when direction is reversed.
        if (Math.abs(normalY) > 0.25) {
            if (normalY < 0) {
                normalX *= -1;
                normalY *= -1;
            }
        } else if (normalX < 0) {
            normalX *= -1;
            normalY *= -1;
        }

        const offset = Math.max(10, finite(options.offsetPx, 18));
        const midpointX = (x1 + x2) / 2;
        const midpointY = (y1 + y2) / 2;
        const angleDeg = Math.atan2(dy, dx) * 180 / Math.PI;

        return Object.freeze({
            valid: true,
            x: midpointX + normalX * offset,
            y: midpointY + normalY * offset,
            angleDeg: uprightAngle(angleDeg),
            lengthPx,
            midpoint: Object.freeze({ x: midpointX, y: midpointY }),
            normal: Object.freeze({ x: normalX, y: normalY }),
        });
    }

    rootV2.LineLabelGeometry = Object.freeze({
        EPSILON,
        normalizedAngle,
        uprightAngle,
        placement,
    });
})();
