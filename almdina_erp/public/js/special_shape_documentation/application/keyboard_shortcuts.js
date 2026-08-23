(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);

    const TOOL_COMMANDS = Object.freeze({
        KeyV: "select",
        KeyP: "pen",
        KeyL: "line",
        KeyR: "rect",
        KeyO: "ellipse",
        KeyD: "dimension",
        KeyT: "text",
        KeyF: "fit-view",
        Digit1: "reset-zoom",
    });

    const CONTROL_COMMANDS = Object.freeze({
        KeyS: "save",
        KeyC: "copy",
        KeyV: "paste",
        KeyY: "redo",
    });

    function physicalCode(event = {}) {
        const code = String(event.code || "");
        if (code) return code;

        const key = String(event.key || "");
        if (/^[a-z]$/i.test(key)) return `Key${key.toUpperCase()}`;
        if (/^[0-9]$/.test(key)) return `Digit${key}`;
        if (key === " ") return "Space";
        return key;
    }

    function resolve(event = {}) {
        const code = physicalCode(event);
        const control = Boolean(event.ctrlKey || event.metaKey);

        if (control) {
            if (code === "KeyZ") return event.shiftKey ? "redo" : "undo";
            return CONTROL_COMMANDS[code] || null;
        }
        if (event.altKey) return null;
        if (code === "Delete" || code === "Backspace") return "delete";
        if (code === "Escape") return "escape";
        if (code === "Space") return "pan";
        return TOOL_COMMANDS[code] || null;
    }

    function isEditableTarget(target) {
        if (!target) return false;
        const tagName = String(target.tagName || "").toUpperCase();
        return ["INPUT", "TEXTAREA", "SELECT"].includes(tagName) || Boolean(target.isContentEditable);
    }

    root.KeyboardShortcuts = Object.freeze({ physicalCode, resolve, isEditableTarget });
})();
