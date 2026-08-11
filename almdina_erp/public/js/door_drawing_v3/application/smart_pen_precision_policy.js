(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before smart pen precision policy");

    const ANGLE_STEP_DEG = 45;
    const SOFT_ANGLE_TOLERANCE_DEG = 4.5;
    const MAX_BUFFER = 24;

    function normalizeBuffer(value) {
        return String(value ?? "").trim().replace(/,/g, ".").replace(/\s+/g, "");
    }

    function isLengthCharacter(key) {
        return /^[0-9]$/.test(String(key || "")) || key === "." || key === ",";
    }

    function isAngleCharacter(key) {
        return isLengthCharacter(key) || key === "-" || key === "+";
    }

    function append(buffer, key, angle = false) {
        const current = normalizeBuffer(buffer);
        if (current.length >= MAX_BUFFER) return current;
        const char = key === "," ? "." : String(key || "");
        if (!(angle ? isAngleCharacter(char) : isLengthCharacter(char))) return current;
        if ((char === "-" || char === "+") && current.length) return current;
        if (char === "." && current.includes(".")) return current;
        return current + char;
    }

    function backspace(buffer) {
        return normalizeBuffer(buffer).slice(0, -1);
    }

    function parseLength(buffer) {
        const value = Number(normalizeBuffer(buffer));
        return Number.isFinite(value) && value >= G.EPSILON_MM ? G.roundMm(value) : null;
    }

    function parseAngle(buffer) {
        const normalized = normalizeBuffer(buffer);
        if (!normalized || normalized === "+" || normalized === "-") return null;
        const value = Number(normalized);
        return Number.isFinite(value) ? G.roundMm(value) : null;
    }

    function normalizeAngle(angleDeg) {
        let value = Number(angleDeg) || 0;
        while (value <= -180) value += 360;
        while (value > 180) value -= 360;
        return value;
    }

    function angularDistance(a, b) {
        return Math.abs(normalizeAngle(Number(a) - Number(b)));
    }

    function pointerAngle(start, pointer) {
        if (!pointer || G.distance(start, pointer) < G.EPSILON_MM) return 0;
        return G.angleDeg(start, pointer);
    }

    function nearestSmartAngle(angleDeg) {
        return Math.round(Number(angleDeg || 0) / ANGLE_STEP_DEG) * ANGLE_STEP_DEG;
    }

    function softAngle(start, pointer, options = {}) {
        const anchor = G.point(start && start.x, start && start.y);
        const raw = G.point(pointer && pointer.x, pointer && pointer.y);
        const lengthMm = G.distance(anchor, raw);
        if (lengthMm < G.EPSILON_MM) return Object.freeze({ point: raw, angleDeg: 0, snapped: false, forced: false });
        const rawAngle = pointerAngle(anchor, raw);
        const snappedAngle = nearestSmartAngle(rawAngle);
        const toleranceDeg = Math.max(0, Number(options.toleranceDeg ?? SOFT_ANGLE_TOLERANCE_DEG));
        const forced = Boolean(options.force);
        const snapped = forced || angularDistance(rawAngle, snappedAngle) <= toleranceDeg;
        return Object.freeze({
            point: snapped ? G.pointAt(anchor, lengthMm, snappedAngle) : raw,
            angleDeg: G.roundMm(snapped ? snappedAngle : rawAngle),
            rawAngleDeg: G.roundMm(rawAngle),
            snapped,
            forced,
            lengthMm: G.roundMm(lengthMm),
        });
    }

    function exactPoint(start, pointer, lengthBuffer, angleBuffer) {
        const anchor = G.point(start && start.x, start && start.y);
        const reference = G.point(pointer && pointer.x, pointer && pointer.y);
        const lengthMm = parseLength(lengthBuffer);
        if (lengthMm == null) return null;
        const typedAngle = parseAngle(angleBuffer);
        const angleDeg = typedAngle == null ? pointerAngle(anchor, reference) : typedAngle;
        return Object.freeze({
            point: G.pointAt(anchor, lengthMm, angleDeg),
            lengthMm,
            angleDeg: G.roundMm(angleDeg),
            angleTyped: typedAngle != null,
        });
    }

    root.SmartPenPrecisionPolicy = Object.freeze({
        ANGLE_STEP_DEG,
        SOFT_ANGLE_TOLERANCE_DEG,
        normalizeBuffer,
        isLengthCharacter,
        isAngleCharacter,
        append,
        backspace,
        parseLength,
        parseAngle,
        normalizeAngle,
        angularDistance,
        pointerAngle,
        nearestSmartAngle,
        softAngle,
        exactPoint,
    });
})();
