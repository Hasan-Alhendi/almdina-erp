(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);

    const TOOLS = Object.freeze({
        SELECT: "select",
        NODE: "node",
        PEN: "pen",
        SMART_PENCIL: "smart-pencil",
        DIMENSION: "dimension",
        HAND: "hand",
    });
    const KNOWN_TOOLS = Object.freeze(Object.values(TOOLS));

    function assertTool(tool) {
        if (!KNOWN_TOOLS.includes(tool)) throw new Error(`Unknown drawing tool: ${tool}`);
        return tool;
    }

    function create(initialTool = TOOLS.SELECT) {
        const activeTool = assertTool(initialTool);
        return Object.freeze({
            activeTool,
            previousTool: null,
            temporaryTool: false,
        });
    }

    function activate(state, tool) {
        const activeTool = assertTool(tool);
        if (state.activeTool === activeTool && !state.temporaryTool) return state;
        return Object.freeze({
            activeTool,
            previousTool: null,
            temporaryTool: false,
        });
    }

    function activateTemporary(state, tool) {
        const activeTool = assertTool(tool);
        if (state.temporaryTool) return state;
        return Object.freeze({
            activeTool,
            previousTool: state.activeTool,
            temporaryTool: true,
        });
    }

    function restoreTemporary(state) {
        if (!state.temporaryTool) return state;
        return Object.freeze({
            activeTool: state.previousTool || TOOLS.SELECT,
            previousTool: null,
            temporaryTool: false,
        });
    }

    function toolForShortcut(key, options = {}) {
        const value = String(key || "").toLowerCase();
        if (value === "v") return TOOLS.SELECT;
        if (value === "a") return TOOLS.NODE;
        if (value === "p") return options.shiftKey ? TOOLS.SMART_PENCIL : TOOLS.PEN;
        if (value === "d") return TOOLS.DIMENSION;
        return null;
    }

    root.ToolStateMachine = Object.freeze({
        TOOLS,
        KNOWN_TOOLS,
        create,
        activate,
        activateTemporary,
        restoreTemporary,
        toolForShortcut,
    });
})();
