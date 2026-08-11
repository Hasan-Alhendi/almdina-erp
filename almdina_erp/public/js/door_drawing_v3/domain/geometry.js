(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const EPSILON_MM = 0.001;

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
        const radians = normalizeAngle(angleDegrees) * Math.PI / 180;
        return point(
            number(start && start.x) + Math.cos(radians) * length,
            number(start && start.y) + Math.sin(radians) * length
        );
    }

    function line(id, start, end, style = {}) {
        const safeStart = point(start && start.x, start && start.y);
        const safeEnd = point(end && end.x, end && end.y);
        if (distance(safeStart, safeEnd) < EPSILON_MM) {
            throw new Error("A line must have a positive length");
        }
        return Object.freeze({
            id: String(id || `line-${Date.now()}`),
            type: "line",
            geometry: Object.freeze({ start: safeStart, end: safeEnd }),
            style: Object.freeze({
                stroke: String(style.stroke || "#1e1e1e"),
                strokeWidthMm: Math.max(0.05, roundMm(style.strokeWidthMm || 0.35)),
            }),
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
        if (anchor === "end") {
            const start = pointAt(object.geometry.end, length, angle + 180);
            return line(object.id, start, object.geometry.end, object.style);
        }
        return line(
            object.id,
            object.geometry.start,
            pointAt(object.geometry.start, length, angle),
            object.style
        );
    }

    function translateLine(object, dxMm, dyMm) {
        if (!object || object.type !== "line") throw new Error("Expected a line object");
        const dx = number(dxMm);
        const dy = number(dyMm);
        return line(
            object.id,
            point(object.geometry.start.x + dx, object.geometry.start.y + dy),
            point(object.geometry.end.x + dx, object.geometry.end.y + dy),
            object.style
        );
    }

    function dominantAxisPoint(anchor, candidate) {
        const dx = number(candidate && candidate.x) - number(anchor && anchor.x);
        const dy = number(candidate && candidate.y) - number(anchor && anchor.y);
        return Math.abs(dx) >= Math.abs(dy)
            ? point(candidate.x, anchor.y)
            : point(anchor.x, candidate.y);
    }

    function cloneObject(object) {
        if (!object || object.type !== "line") throw new Error("Unsupported drawing object");
        return line(
            object.id,
            object.geometry.start,
            object.geometry.end,
            object.style
        );
    }

    root.Geometry = Object.freeze({
        EPSILON_MM,
        number,
        roundMm,
        point,
        distance,
        normalizeAngle,
        angleDeg,
        pointAt,
        line,
        lineLength,
        lineAngle,
        setLineEndpoint,
        resizeLine,
        translateLine,
        dominantAxisPoint,
        cloneObject,
    });
})();
