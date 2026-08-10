(() => {
    "use strict";

    const engine = window.AlmdinaSketchEngine;
    if (!engine) {
        console.error("AlmdinaSketchEngine must load before the exact-line model");
        return;
    }

    const VERSION = 1;
    const UNITS = "cm";
    const DEFAULT_PADDING = 58;
    const MIN_LENGTH_CM = 0.1;
    const ENDPOINT_SNAP_CM = 0.6;
    const EPSILON = 0.001;

    function num(value) {
        const result = Number(String(value ?? "").trim().replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function rounded(value, precision = 3) {
        const factor = 10 ** precision;
        return Math.round(num(value) * factor) / factor;
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, num(value)));
    }

    function pieceDimensions(row) {
        return {
            width: Math.max(0, num(row && row.width_cm)),
            length: Math.max(0, num(row && row.length_cm)),
        };
    }

    function createTransform(widthCm, lengthCm, options = {}) {
        const width = Math.max(0, num(widthCm));
        const length = Math.max(0, num(lengthCm));
        const canvasWidth = Number(options.canvasWidth) > 0
            ? Number(options.canvasWidth)
            : engine.DEFAULT_CANVAS.width;
        const canvasHeight = Number(options.canvasHeight) > 0
            ? Number(options.canvasHeight)
            : engine.DEFAULT_CANVAS.height;
        const requestedPadding = Number(options.padding);
        const padding = Number.isFinite(requestedPadding)
            ? clamp(requestedPadding, 12, Math.min(canvasWidth, canvasHeight) * 0.28)
            : DEFAULT_PADDING;
        if (!width || !length) return null;
        const availableWidth = Math.max(1, canvasWidth - padding * 2);
        const availableHeight = Math.max(1, canvasHeight - padding * 2);
        const scale = Math.min(availableWidth / width, availableHeight / length);
        const drawnWidth = width * scale;
        const drawnHeight = length * scale;
        return Object.freeze({
            version: VERSION,
            units: UNITS,
            widthCm: width,
            lengthCm: length,
            canvasWidth,
            canvasHeight,
            padding,
            scale,
            offsetX: (canvasWidth - drawnWidth) / 2,
            offsetY: (canvasHeight - drawnHeight) / 2,
            drawnWidth,
            drawnHeight,
        });
    }

    function cmToCanvas(transform, point) {
        if (!transform || !Array.isArray(point)) return [0, 0];
        return [
            rounded(transform.offsetX + num(point[0]) * transform.scale, 4),
            rounded(transform.offsetY + num(point[1]) * transform.scale, 4),
        ];
    }

    function canvasToCm(transform, point) {
        if (!transform || !Array.isArray(point) || !transform.scale) return [0, 0];
        return [
            rounded((num(point[0]) - transform.offsetX) / transform.scale),
            rounded((num(point[1]) - transform.offsetY) / transform.scale),
        ];
    }

    function insidePiece(transform, point, tolerance = EPSILON) {
        if (!transform || !Array.isArray(point)) return false;
        const x = num(point[0]);
        const y = num(point[1]);
        return x >= -tolerance
            && x <= transform.widthCm + tolerance
            && y >= -tolerance
            && y <= transform.lengthCm + tolerance;
    }

    function clampPointToPiece(transform, point) {
        if (!transform || !Array.isArray(point)) return [0, 0];
        return [
            rounded(clamp(point[0], 0, transform.widthCm)),
            rounded(clamp(point[1], 0, transform.lengthCm)),
        ];
    }

    function normalizeAngle(angle) {
        let value = num(angle) % 360;
        if (value > 180) value -= 360;
        if (value <= -180) value += 360;
        return rounded(value, 3);
    }

    function angleBetween(start, end) {
        if (!Array.isArray(start) || !Array.isArray(end)) return 0;
        return normalizeAngle(
            Math.atan2(num(end[1]) - num(start[1]), num(end[0]) - num(start[0]))
            * 180 / Math.PI
        );
    }

    function axisLockedAngle(start, pointer) {
        const dx = num(pointer && pointer[0]) - num(start && start[0]);
        const dy = num(pointer && pointer[1]) - num(start && start[1]);
        if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? 0 : 180;
        return dy >= 0 ? 90 : -90;
    }

    function pointAt(start, lengthCm, angleDeg) {
        const length = Math.max(0, num(lengthCm));
        const radians = normalizeAngle(angleDeg) * Math.PI / 180;
        return [
            rounded(num(start && start[0]) + Math.cos(radians) * length),
            rounded(num(start && start[1]) + Math.sin(radians) * length),
        ];
    }

    function maxLengthFrom(transform, start, angleDeg) {
        if (!transform || !insidePiece(transform, start, 0.01)) return 0;
        const radians = normalizeAngle(angleDeg) * Math.PI / 180;
        const dx = Math.cos(radians);
        const dy = Math.sin(radians);
        const candidates = [];
        const x = num(start[0]);
        const y = num(start[1]);
        if (dx > EPSILON) candidates.push((transform.widthCm - x) / dx);
        else if (dx < -EPSILON) candidates.push((0 - x) / dx);
        if (dy > EPSILON) candidates.push((transform.lengthCm - y) / dy);
        else if (dy < -EPSILON) candidates.push((0 - y) / dy);
        const positive = candidates.filter(value => Number.isFinite(value) && value >= -EPSILON);
        return positive.length ? rounded(Math.max(0, Math.min(...positive))) : 0;
    }

    function exactMeta(element) {
        const meta = element && element.exact_line;
        if (
            !meta
            || Number(meta.version) !== VERSION
            || meta.units !== UNITS
            || !Array.isArray(meta.start_cm)
            || !Array.isArray(meta.end_cm)
        ) return null;
        return meta;
    }

    function exactEndpoints(elements) {
        const result = [];
        (Array.isArray(elements) ? elements : []).forEach(element => {
            const meta = exactMeta(element);
            if (!meta) return;
            result.push({ elementId: String(element.id || ""), role: "start", point: [num(meta.start_cm[0]), num(meta.start_cm[1])] });
            result.push({ elementId: String(element.id || ""), role: "end", point: [num(meta.end_cm[0]), num(meta.end_cm[1])] });
        });
        return result;
    }

    function nearestEndpoint(point, elements, radiusCm = ENDPOINT_SNAP_CM) {
        const radius = Math.max(0, num(radiusCm));
        let nearest = null;
        let distance = radius;
        exactEndpoints(elements).forEach(candidate => {
            const nextDistance = Math.hypot(
                num(candidate.point[0]) - num(point && point[0]),
                num(candidate.point[1]) - num(point && point[1])
            );
            if (nextDistance <= distance) {
                distance = nextDistance;
                nearest = candidate;
            }
        });
        return nearest ? { ...nearest, point: nearest.point.slice(), distance: rounded(distance) } : null;
    }

    function buildElement(options = {}) {
        const transform = options.transform;
        const start = clampPointToPiece(transform, options.startCm || [0, 0]);
        const length = Math.max(0, num(options.lengthCm));
        const angle = normalizeAngle(options.angleDeg);
        if (!transform) return { valid: false, reason: "missing-transform", element: null };
        if (length < MIN_LENGTH_CM) return { valid: false, reason: "length-too-small", element: null };
        const maximum = maxLengthFrom(transform, start, angle);
        if (length > maximum + 0.001) {
            return {
                valid: false,
                reason: "outside-piece",
                maximumLengthCm: maximum,
                element: null,
            };
        }
        const end = pointAt(start, length, angle);
        if (!insidePiece(transform, end, 0.01)) {
            return { valid: false, reason: "outside-piece", maximumLengthCm: maximum, element: null };
        }
        const startCanvas = cmToCanvas(transform, start);
        const endCanvas = cmToCanvas(transform, end);
        return {
            valid: true,
            reason: "",
            maximumLengthCm: maximum,
            element: {
                id: String(options.id || `exact-line-${Date.now()}`),
                type: "line",
                x1: startCanvas[0],
                y1: startCanvas[1],
                x2: endCanvas[0],
                y2: endCanvas[1],
                color: String(options.color || "#172033"),
                exact_line: {
                    version: VERSION,
                    units: UNITS,
                    start_cm: start,
                    end_cm: end,
                    length_cm: rounded(length),
                    angle_deg: angle,
                    blank_width_cm: rounded(transform.widthCm),
                    blank_length_cm: rounded(transform.lengthCm),
                },
            },
        };
    }

    function syncElementFromCanvas(element, transform) {
        const meta = exactMeta(element);
        if (!meta || !transform) return element;
        const start = clampPointToPiece(transform, canvasToCm(transform, [element.x1, element.y1]));
        const end = clampPointToPiece(transform, canvasToCm(transform, [element.x2, element.y2]));
        const length = Math.hypot(end[0] - start[0], end[1] - start[1]);
        element.exact_line = {
            ...meta,
            start_cm: start,
            end_cm: end,
            length_cm: rounded(length),
            angle_deg: angleBetween(start, end),
            blank_width_cm: rounded(transform.widthCm),
            blank_length_cm: rounded(transform.lengthCm),
        };
        return element;
    }

    function command(value) {
        const text = String(value ?? "").trim();
        if (!text) return { valid: false, lengthCm: 0, angleDeg: null };
        const parts = text.split(/[@;\/]/).map(item => item.trim()).filter(Boolean);
        const lengthCm = num(parts[0]);
        const angleDeg = parts.length > 1 ? normalizeAngle(parts[1]) : null;
        return {
            valid: lengthCm >= MIN_LENGTH_CM,
            lengthCm: rounded(lengthCm),
            angleDeg,
        };
    }

    window.AlmdinaExactLineModel = Object.freeze({
        VERSION,
        UNITS,
        DEFAULT_PADDING,
        MIN_LENGTH_CM,
        ENDPOINT_SNAP_CM,
        pieceDimensions,
        createTransform,
        cmToCanvas,
        canvasToCm,
        insidePiece,
        clampPointToPiece,
        normalizeAngle,
        angleBetween,
        axisLockedAngle,
        pointAt,
        maxLengthFrom,
        exactMeta,
        exactEndpoints,
        nearestEndpoint,
        buildElement,
        syncElementFromCanvas,
        command,
        rounded,
    });
})();
