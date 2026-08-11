(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before precision input");

    const MAX_BUFFER = 32;

    function state(tool, stage = "size", buffer = "") {
        return Object.freeze({
            tool: String(tool || ""),
            stage: String(stage || "size"),
            buffer: String(buffer || ""),
        });
    }

    function normalizeBuffer(value) {
        return String(value || "")
            .trim()
            .replace(/,/g, ".")
            .replace(/×/g, "x")
            .replace(/\*/g, "x")
            .replace(/\s+/g, "");
    }

    function isInputCharacter(key, context) {
        const char = String(key || "");
        if (/^[0-9]$/.test(char) || char === "." || char === ",") return true;
        if (context && context.tool === "rectangle" && ["x", "X", "×", "*"].includes(char)) return true;
        if (context && context.tool === "circle" && /^[rRdDØ]$/.test(char)) return true;
        if (context && context.tool === "arc" && context.stage === "sweep" && ["-", "+"].includes(char)) return true;
        return false;
    }

    function append(current, key) {
        const base = current || state("");
        if (base.buffer.length >= MAX_BUFFER) return base;
        let char = String(key || "");
        if (char === ",") char = ".";
        if (char === "×" || char === "*") char = "x";
        if (/^[Rr]$/.test(char)) char = "r";
        if (/^[DdØ]$/.test(char)) char = "d";
        if ((char === "r" || char === "d") && base.tool === "circle") {
            const numeric = base.buffer.replace(/^[rd]/, "");
            return state(base.tool, base.stage, char + numeric);
        }
        return state(base.tool, base.stage, base.buffer + char);
    }

    function backspace(current) {
        const base = current || state("");
        return state(base.tool, base.stage, base.buffer.slice(0, -1));
    }

    function positive(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) && parsed >= G.EPSILON_MM ? parsed : null;
    }

    function signed(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function parseLine(buffer) {
        const lengthMm = positive(normalizeBuffer(buffer));
        return lengthMm == null ? null : Object.freeze({ lengthMm: G.roundMm(lengthMm) });
    }

    function parseRectangle(buffer) {
        const normalized = normalizeBuffer(buffer);
        if (!normalized) return null;
        const parts = normalized.split("x");
        if (parts.length > 2) return null;
        const widthMm = positive(parts[0]);
        if (widthMm == null) return null;
        const heightMm = parts.length === 2 && parts[1] !== "" ? positive(parts[1]) : null;
        if (parts.length === 2 && parts[1] !== "" && heightMm == null) return null;
        return Object.freeze({ widthMm: G.roundMm(widthMm), heightMm: heightMm == null ? null : G.roundMm(heightMm) });
    }

    function parseCircle(buffer) {
        const normalized = normalizeBuffer(buffer).toLowerCase();
        if (!normalized) return null;
        const prefix = normalized[0] === "r" || normalized[0] === "d" ? normalized[0] : "d";
        const value = positive(prefix === normalized[0] ? normalized.slice(1) : normalized);
        if (value == null) return null;
        const radiusMm = prefix === "r" ? value : value / 2;
        if (radiusMm < G.EPSILON_MM) return null;
        return Object.freeze({
            mode: prefix === "r" ? "radius" : "diameter",
            valueMm: G.roundMm(value),
            radiusMm: G.roundMm(radiusMm),
        });
    }

    function parseArc(buffer, stageName) {
        const normalized = normalizeBuffer(buffer);
        if (stageName === "sweep") {
            const sweepAngleDeg = signed(normalized);
            if (sweepAngleDeg == null || Math.abs(sweepAngleDeg) < G.MIN_ARC_SWEEP_DEG) return null;
            const limited = Math.max(-G.MAX_ARC_SWEEP_DEG, Math.min(G.MAX_ARC_SWEEP_DEG, sweepAngleDeg));
            return Object.freeze({ sweepAngleDeg: G.roundMm(limited) });
        }
        const radiusMm = positive(normalized);
        return radiusMm == null ? null : Object.freeze({ radiusMm: G.roundMm(radiusMm) });
    }

    function directionAngle(start, pointer) {
        if (!pointer || G.distance(start, pointer) < G.EPSILON_MM) return 0;
        return G.angleDeg(start, pointer);
    }

    function lineFromInput(start, pointer, buffer, style = {}) {
        const parsed = parseLine(buffer);
        if (!parsed) return null;
        return G.line("draft", start, G.pointAt(start, parsed.lengthMm, directionAngle(start, pointer)), style);
    }

    function rectangleFromInput(start, pointer, buffer, style = {}) {
        const parsed = parseRectangle(buffer);
        if (!parsed) return null;
        const dx = G.number(pointer && pointer.x) - G.number(start && start.x);
        const dy = G.number(pointer && pointer.y) - G.number(start && start.y);
        const width = parsed.widthMm;
        const fallbackHeight = Math.max(G.EPSILON_MM, Math.abs(dy));
        const height = parsed.heightMm == null ? fallbackHeight : parsed.heightMm;
        const end = G.point(
            G.number(start && start.x) + (dx < 0 ? -width : width),
            G.number(start && start.y) + (dy < 0 ? -height : height)
        );
        return G.rectangleFromPoints("draft", start, end, false, style);
    }

    function circleFromInput(center, buffer, style = {}) {
        const parsed = parseCircle(buffer);
        if (!parsed) return null;
        return G.circle("draft", center, parsed.radiusMm, style);
    }

    function arcFromSweep(center, radiusMm, startAngleDeg, buffer, style = {}) {
        const parsed = parseArc(buffer, "sweep");
        if (!parsed) return null;
        return G.arc("draft", center, radiusMm, startAngleDeg, parsed.sweepAngleDeg, style);
    }

    function display(current) {
        const base = current || state("");
        const raw = base.buffer || "—";
        if (base.tool === "line") return `L  ${raw} mm`;
        if (base.tool === "rectangle") return `W × H   ${raw} mm`;
        if (base.tool === "circle") {
            const normalized = normalizeBuffer(base.buffer).toLowerCase();
            return normalized.startsWith("r") ? `R  ${normalized.slice(1) || "—"} mm` : `Ø  ${normalized.replace(/^d/, "") || "—"} mm`;
        }
        if (base.tool === "arc") return base.stage === "sweep" ? `∠  ${raw}°` : `R  ${raw} mm`;
        return raw;
    }

    root.PrecisionInput = Object.freeze({
        state,
        normalizeBuffer,
        isInputCharacter,
        append,
        backspace,
        parseLine,
        parseRectangle,
        parseCircle,
        parseArc,
        lineFromInput,
        rectangleFromInput,
        circleFromInput,
        arcFromSweep,
        display,
    });
})();
