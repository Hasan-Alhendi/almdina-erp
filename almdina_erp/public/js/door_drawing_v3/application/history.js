(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);

    function create(initialDocument, onChange) {
        let current = initialDocument;
        const undoStack = [];
        const redoStack = [];

        function notify() {
            if (typeof onChange === "function") onChange(current);
            return current;
        }

        function execute(nextDocument, label = "edit") {
            if (!nextDocument || nextDocument === current) return current;
            undoStack.push(Object.freeze({ label, before: current, after: nextDocument }));
            redoStack.length = 0;
            current = nextDocument;
            return notify();
        }

        function undo() {
            const command = undoStack.pop();
            if (!command) return current;
            redoStack.push(command);
            current = command.before;
            return notify();
        }

        function redo() {
            const command = redoStack.pop();
            if (!command) return current;
            undoStack.push(command);
            current = command.after;
            return notify();
        }

        return Object.freeze({
            current: () => current,
            execute,
            undo,
            redo,
            canUndo: () => undoStack.length > 0,
            canRedo: () => redoStack.length > 0,
        });
    }

    root.History = Object.freeze({ create });
})();
