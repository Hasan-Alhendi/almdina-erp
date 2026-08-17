(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const TOOL_SHORTCUTS = Object.freeze({ v: "select", a: "node", p: "pen", d: "dimension" });

    function isTextEditingTarget(target) {
        if (!target || target === document.body) return false;
        if (target.isContentEditable) return true;
        const tag = String(target.tagName || "").toLowerCase();
        if (tag === "textarea" || tag === "select") return true;
        if (tag !== "input") return false;
        const type = String(target.type || "text").toLowerCase();
        return !["button", "checkbox", "radio", "range", "color"].includes(type);
    }

    function visible(scope) {
        return Boolean(scope && scope.isConnected && scope.getClientRects && scope.getClientRects().length);
    }

    function mount(scope, handlers = {}) {
        if (!scope) throw new Error("Keyboard controller requires a workspace scope");
        let spaceHeld = false;
        let destroyed = false;

        function keydown(event) {
            if (destroyed || !visible(scope) || event.isComposing || isTextEditingTarget(event.target)) return;
            const key = String(event.key || "").toLowerCase();
            const command = event.ctrlKey || event.metaKey;
            if (command && !event.altKey && key === "z") {
                event.preventDefault();
                if (event.shiftKey) handlers.redo && handlers.redo();
                else handlers.undo && handlers.undo();
                return;
            }
            if (command && !event.altKey && key === "y") {
                event.preventDefault();
                handlers.redo && handlers.redo();
                return;
            }
            if (event.code === "Space") {
                event.preventDefault();
                if (!spaceHeld && !event.repeat) {
                    spaceHeld = true;
                    handlers.spaceDown && handlers.spaceDown();
                }
                return;
            }
            if (TOOL_SHORTCUTS[key]) {
                event.preventDefault();
                handlers.tool && handlers.tool(TOOL_SHORTCUTS[key], key);
                return;
            }
            if (event.key === "Escape") {
                event.preventDefault();
                handlers.escape && handlers.escape();
                return;
            }
            if (event.key === "Enter") {
                if (handlers.enter && handlers.enter()) event.preventDefault();
                return;
            }
            if (/^[0-9.,]$/.test(event.key)) {
                if (handlers.numeric && handlers.numeric(event.key)) event.preventDefault();
                return;
            }
            if (event.key === "Delete" || event.key === "Backspace") {
                if (handlers.remove && handlers.remove()) event.preventDefault();
            }
        }

        function keyup(event) {
            if (destroyed || event.code !== "Space" || !spaceHeld) return;
            event.preventDefault();
            spaceHeld = false;
            handlers.spaceUp && handlers.spaceUp();
        }

        window.addEventListener("keydown", keydown, true);
        window.addEventListener("keyup", keyup, true);
        return Object.freeze({
            destroy() {
                if (destroyed) return;
                destroyed = true;
                window.removeEventListener("keydown", keydown, true);
                window.removeEventListener("keyup", keyup, true);
                if (spaceHeld) handlers.spaceUp && handlers.spaceUp();
                spaceHeld = false;
            },
        });
    }

    root.KeyboardController = Object.freeze({ TOOL_SHORTCUTS, isTextEditingTarget, mount });
})();
