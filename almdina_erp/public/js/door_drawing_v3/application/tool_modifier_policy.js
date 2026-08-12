(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before tool modifier policy");

    const TOOLS = Object.freeze(["select", "line", "rectangle", "circle", "arc", "pen"]);
    const TOOL_SET = new Set(TOOLS);
    const PEN_CONSTRAINTS = Object.freeze({
        FREEHAND: "freehand",
        STRAIGHT: "straight",
        AXIS: "axis",
    });

    function normalizeTool(tool, fallback = "select") {
        const value = String(tool || "").toLowerCase();
        return TOOL_SET.has(value) ? value : (TOOL_SET.has(fallback) ? fallback : "select");
    }

    function penConstraint(modifiers = {}) {
        if (Boolean(modifiers.shiftKey)) return PEN_CONSTRAINTS.AXIS;
        if (Boolean(modifiers.altKey)) return PEN_CONSTRAINTS.STRAIGHT;
        return PEN_CONSTRAINTS.FREEHAND;
    }

    function constrainEndpoint(startPoint, candidatePoint, mode) {
        const start = G.point(startPoint && startPoint.x, startPoint && startPoint.y);
        const candidate = G.point(candidatePoint && candidatePoint.x, candidatePoint && candidatePoint.y);
        if (mode !== PEN_CONSTRAINTS.AXIS) return candidate;
        const dx = candidate.x - start.x;
        const dy = candidate.y - start.y;
        return Math.abs(dx) >= Math.abs(dy)
            ? G.point(candidate.x, start.y)
            : G.point(start.x, candidate.y);
    }

    function isDrawingTool(tool) {
        return ["line", "rectangle", "circle", "arc", "pen"].includes(normalizeTool(tool));
    }

    function effectiveTool(persistentTool, temporarySelect) {
        return temporarySelect ? "select" : normalizeTool(persistentTool);
    }

    root.ToolModifierPolicy = Object.freeze({
        TOOLS,
        PEN_CONSTRAINTS,
        normalizeTool,
        penConstraint,
        constrainEndpoint,
        isDrawingTool,
        effectiveTool,
    });
})();
