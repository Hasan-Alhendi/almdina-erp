(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const EPSILON_MM = 0.001;
    const MIN_ARC_SWEEP_DEG = 0.1;
    const MAX_ARC_SWEEP_DEG = 359.999;

    function number(value, fallback = 0) {
        const parsed = Number(String(value ?? "").trim().replace(",", "."));
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function roundMm(value, precision = 3) {
        const factor = 10 ** precision;
        return Math.round(number(value) * factor) / factor;
    }

    function point(x = 0, y = 0) {
        return Object.freeze({ x: roundMm(x), y: roundMm(y) });
    }

    function distance(first, second) {
        return Math.hypot(
            number(second && second.x) - number(first && first.x),
            number(second && second.y) - number(first && first.y)
        );
    }

    function normalizeAngle(angleDeg) {
        let angle = number(angleDeg) % 360;
        if (angle > 180) angle -= 360;
        if (angle <= -180) angle += 360;
        return roundMm(angle);
    }

    function positiveAngle(angleDeg) {
        let angle = number(angleDeg) % 360;
        if (angle < 0) angle += 360;
        return roundMm(angle);
    }

    function angleDeg(first, second) {
        return normalizeAngle(
            Math.atan2(
                number(second && second.y) - number(first && first.y),
                number(second && second.x) - number(first && first.x)
            ) * 180 / Math.PI
        );
    }

    function pointAt(start, lengthMm, angleDegrees) {
        const length = Math.max(0, number(lengthMm));
        const radians = number(angleDegrees) * Math.PI / 180;
        return point(
            number(start && start.x) + Math.cos(radians) * length,
            number(start && start.y) + Math.sin(radians) * length
        );
    }

    function styleObject(style = {}) {
        return Object.freeze({
            stroke: String(style.stroke || "#1e1e1e"),
            strokeWidthMm: Math.max(0.05, roundMm(style.strokeWidthMm || 0.35)),
        });
    }

    function line(id, start, end, style = {}) {
        const safeStart = point(start && start.x, start && start.y);
        const safeEnd = point(end && end.x, end && end.y);
        if (distance(safeStart, safeEnd) < EPSILON_MM) throw new Error("A line must have a positive length");
        return Object.freeze({
            id: String(id || `line-${Date.now()}`),
            type: "line",
            geometry: Object.freeze({ start: safeStart, end: safeEnd }),
            style: styleObject(style),
        });
    }

    function rectangle(id, origin, widthMm, heightMm, style = {}) {
        const width = number(widthMm);
        const height = number(heightMm);
        if (!(width >= EPSILON_MM) || !(height >= EPSILON_MM)) throw new Error("Rectangle dimensions must be positive");
        return Object.freeze({
            id: String(id || `rectangle-${Date.now()}`),
            type: "rectangle",
            geometry: Object.freeze({
                origin: point(origin && origin.x, origin && origin.y),
                widthMm: roundMm(width),
                heightMm: roundMm(height),
            }),
            style: styleObject(style),
        });
    }

    function rectangleFromPoints(id, first, second, square = false, style = {}) {
        const a = point(first && first.x, first && first.y);
        let b = point(second && second.x, second && second.y);
        if (square) {
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const size = Math.max(Math.abs(dx), Math.abs(dy));
            b = point(a.x + (dx < 0 ? -size : size), a.y + (dy < 0 ? -size : size));
        }
        const x = Math.min(a.x, b.x);
        const y = Math.min(a.y, b.y);
        return rectangle(id, point(x, y), Math.abs(b.x - a.x), Math.abs(b.y - a.y), style);
    }

    function circle(id, center, radiusMm, style = {}) {
        const radius = number(radiusMm);
        if (!(radius >= EPSILON_MM)) throw new Error("Circle radius must be positive");
        return Object.freeze({
            id: String(id || `circle-${Date.now()}`),
            type: "circle",
            geometry: Object.freeze({
                center: point(center && center.x, center && center.y),
                radiusMm: roundMm(radius),
            }),
            style: styleObject(style),
        });
    }

    function arc(id, center, radiusMm, startAngleDeg, sweepAngleDeg, style = {}) {
        const radius = number(radiusMm);
        let sweep = number(sweepAngleDeg);
        if (!(radius >= EPSILON_MM)) throw new Error("Arc radius must be positive");
        if (Math.abs(sweep) < MIN_ARC_SWEEP_DEG) throw new Error("Arc sweep must be positive");
        sweep = Math.max(-MAX_ARC_SWEEP_DEG, Math.min(MAX_ARC_SWEEP_DEG, sweep));
        return Object.freeze({
            id: String(id || `arc-${Date.now()}`),
            type: "arc",
            geometry: Object.freeze({
                center: point(center && center.x, center && center.y),
                radiusMm: roundMm(radius),
                startAngleDeg: normalizeAngle(startAngleDeg),
                sweepAngleDeg: roundMm(sweep),
            }),
            style: styleObject(style),
        });
    }

    function lineLength(object) {
        if (!object || object.type !== "line") return 0;
        return roundMm(distance(object.geometry.start, object.geometry.end));
    }

    function lineAngle(object) {
        if (!object || object.type !== "line") return 0;
        return angleDeg(object.geometry.start, object.geometry.end);
    }

    function arcLength(object) {
        if (!object || object.type !== "arc") return 0;
        return roundMm(object.geometry.radiusMm * Math.abs(object.geometry.sweepAngleDeg) * Math.PI / 180);
    }

    function arcPoint(object, angleDegrees) {
        if (!object || object.type !== "arc") throw new Error("Expected an arc object");
        return pointAt(object.geometry.center, object.geometry.radiusMm, angleDegrees);
    }

    function arcStart(object) {
        return arcPoint(object, object.geometry.startAngleDeg);
    }

    function arcEnd(object) {
        return arcPoint(object, object.geometry.startAngleDeg + object.geometry.sweepAngleDeg);
    }

    function arcMid(object) {
        return arcPoint(object, object.geometry.startAngleDeg + object.geometry.sweepAngleDeg / 2);
    }

    function setLineEndpoint(object, role, nextPoint) {
        if (!object || object.type !== "line") throw new Error("Expected a line object");
        const start = role === "start" ? point(nextPoint.x, nextPoint.y) : object.geometry.start;
        const end = role === "end" ? point(nextPoint.x, nextPoint.y) : object.geometry.end;
        return line(object.id, start, end, object.style);
    }

    function resizeLine(object, lengthMm, angleDegrees = lineAngle(object), anchor = "start") {
        if (!object || object.type !== "line") throw new Error("Expected a line object");
        const length = number(lengthMm);
        if (!(length >= EPSILON_MM)) throw new Error("Line length must be positive");
        const angle = normalizeAngle(angleDegrees);
        if (anchor === "end") return line(object.id, pointAt(object.geometry.end, length, angle + 180), object.geometry.end, object.style);
        return line(object.id, object.geometry.start, pointAt(object.geometry.start, length, angle), object.style);
    }

    function translateObject(object, dxMm, dyMm) {
        if (!object) throw new Error("Expected a drawing object");
        const dx = number(dxMm);
        const dy = number(dyMm);
        if (object.type === "line") {
            return line(object.id,
                point(object.geometry.start.x + dx, object.geometry.start.y + dy),
                point(object.geometry.end.x + dx, object.geometry.end.y + dy), object.style);
        }
        if (object.type === "rectangle") {
            return rectangle(object.id,
                point(object.geometry.origin.x + dx, object.geometry.origin.y + dy),
                object.geometry.widthMm, object.geometry.heightMm, object.style);
        }
        if (object.type === "circle") {
            return circle(object.id,
                point(object.geometry.center.x + dx, object.geometry.center.y + dy),
                object.geometry.radiusMm, object.style);
        }
        if (object.type === "arc") {
            return arc(object.id,
                point(object.geometry.center.x + dx, object.geometry.center.y + dy),
                object.geometry.radiusMm, object.geometry.startAngleDeg, object.geometry.sweepAngleDeg, object.style);
        }
        throw new Error("Unsupported drawing object");
    }

    function dominantAxisPoint(anchor, candidate) {
        const dx = number(candidate && candidate.x) - number(anchor && anchor.x);
        const dy = number(candidate && candidate.y) - number(anchor && anchor.y);
        return Math.abs(dx) >= Math.abs(dy) ? point(candidate.x, anchor.y) : point(anchor.x, candidate.y);
    }

    function cloneObject(object, id = object && object.id) {
        if (!object) throw new Error("Unsupported drawing object");
        if (object.type === "line") return line(id, object.geometry.start, object.geometry.end, object.style);
        if (object.type === "rectangle") return rectangle(id, object.geometry.origin, object.geometry.widthMm, object.geometry.heightMm, object.style);
        if (object.type === "circle") return circle(id, object.geometry.center, object.geometry.radiusMm, object.style);
        if (object.type === "arc") return arc(id, object.geometry.center, object.geometry.radiusMm, object.geometry.startAngleDeg, object.geometry.sweepAngleDeg, object.style);
        throw new Error("Unsupported drawing object");
    }

    function setRectangle(object, patch = {}) {
        if (!object || object.type !== "rectangle") throw new Error("Expected a rectangle object");
        return rectangle(object.id,
            point(patch.x ?? object.geometry.origin.x, patch.y ?? object.geometry.origin.y),
            patch.widthMm ?? object.geometry.widthMm,
            patch.heightMm ?? object.geometry.heightMm,
            object.style);
    }

    function setCircle(object, patch = {}) {
        if (!object || object.type !== "circle") throw new Error("Expected a circle object");
        return circle(object.id,
            point(patch.cx ?? object.geometry.center.x, patch.cy ?? object.geometry.center.y),
            patch.radiusMm ?? object.geometry.radiusMm,
            object.style);
    }

    function setArc(object, patch = {}) {
        if (!object || object.type !== "arc") throw new Error("Expected an arc object");
        return arc(object.id,
            point(patch.cx ?? object.geometry.center.x, patch.cy ?? object.geometry.center.y),
            patch.radiusMm ?? object.geometry.radiusMm,
            patch.startAngleDeg ?? object.geometry.startAngleDeg,
            patch.sweepAngleDeg ?? object.geometry.sweepAngleDeg,
            object.style);
    }

    root.Geometry = Object.freeze({
        EPSILON_MM,
        MIN_ARC_SWEEP_DEG,
        MAX_ARC_SWEEP_DEG,
        number,
        roundMm,
        point,
        distance,
        normalizeAngle,
        positiveAngle,
        angleDeg,
        pointAt,
        line,
        rectangle,
        rectangleFromPoints,
        circle,
        arc,
        lineLength,
        lineAngle,
        arcLength,
        arcPoint,
        arcStart,
        arcEnd,
        arcMid,
        setLineEndpoint,
        resizeLine,
        translateObject,
        translateLine: translateObject,
        dominantAxisPoint,
        cloneObject,
        setRectangle,
        setCircle,
        setArc,
    });
})();
