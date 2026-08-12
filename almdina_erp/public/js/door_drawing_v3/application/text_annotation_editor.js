(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Editor = root.Editor;
    const G = root.Geometry;
    const D = root.DocumentModel;
    const V = root.ShapeView;
    if (!Editor || !G || !D || !V || !G.TEXT_TYPE) throw new Error("Door Drawing V3 editor and text domain must load before text editing");

    let sequence = 0;
    function nextId() { sequence += 1; return `text-${Date.now()}-${sequence}`; }

    function execute(c, nextDocument, label) {
        c.history.execute(nextDocument, label);
        c.dirty = true;
        V.render(c);
    }

    function setTextTool(c) {
        if (!c || c.readOnly) return;
        if (c.__textEditor) commitInline(c);
        c.tool = G.TEXT_TYPE;
        c.draftStart = null;
        c.draftObject = null;
        c.arcDraft = null;
        c.clickDraft = null;
        c.precision = null;
        c.snapState = null;
        V.render(c);
    }

    function positionEditor(c, editor, point) {
        const screen = V.worldToScreen(c, point);
        editor.style.left = `${Math.max(8, Math.min(c.viewport.widthPx - 220, screen.x))}px`;
        editor.style.top = `${Math.max(8, Math.min(c.viewport.heightPx - 90, screen.y - 28))}px`;
    }

    function closeInline(c) {
        const state = c && c.__textEditor;
        if (!state) return;
        state.element.remove();
        c.__textEditor = null;
    }

    function commitInline(c) {
        const state = c && c.__textEditor;
        if (!state || state.committing) return false;
        state.committing = true;
        const value = String(state.element.value || "").trimEnd();
        const current = c.history.current();
        try {
            if (!value.trim()) {
                if (state.object) {
                    c.selectedId = "";
                    closeInline(c);
                    execute(c, D.removeObject(current, state.object.id), "Delete text");
                    return true;
                }
                closeInline(c);
                V.render(c);
                return false;
            }
            const object = state.object
                ? G.setText(state.object, { text: value })
                : G.text(nextId(), state.position, value, { fontSizeMm: G.DEFAULT_TEXT_FONT_SIZE_MM });
            c.selectedId = object.id;
            closeInline(c);
            execute(c, state.object ? D.replaceObject(current, object) : D.addObject(current, object), state.object ? "Edit text" : "Add text");
            return true;
        } catch (error) {
            state.committing = false;
            return false;
        }
    }

    function startInline(c, position, object = null) {
        if (!c || c.readOnly) return null;
        if (c.__textEditor) commitInline(c);
        const workspace = c.root.querySelector(".ddv3-workspace");
        if (!workspace) return null;
        const point = object ? object.geometry.position : G.point(position && position.x, position && position.y);
        const textarea = document.createElement("textarea");
        textarea.className = "ddv3-inline-text-editor";
        textarea.rows = 1;
        textarea.dir = "auto";
        textarea.placeholder = "اكتب الملاحظة…";
        textarea.value = object ? object.text : "";
        textarea.style.fontSize = `${Math.max(12, (object ? object.style.fontSizeMm : G.DEFAULT_TEXT_FONT_SIZE_MM) * c.viewport.scale)}px`;
        positionEditor(c, textarea, point);
        workspace.appendChild(textarea);
        c.__textEditor = { element: textarea, position: point, object, committing: false };
        if (object) c.selectedId = object.id;

        textarea.addEventListener("keydown", event => {
            if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                closeInline(c);
                V.render(c);
                return;
            }
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                commitInline(c);
            }
        });
        textarea.addEventListener("blur", () => window.setTimeout(() => commitInline(c), 0), { once: true });
        window.requestAnimationFrame(() => {
            textarea.focus();
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);
        });
        return textarea;
    }

    function applyInspector(c, input) {
        if (!input || c.readOnly) return false;
        const object = D.objectById(c.history.current(), c.selectedId);
        if (!object || object.type !== G.TEXT_TYPE) return false;
        const key = input.dataset.ddv3TextProp;
        let patch = null;
        if (key === "text") patch = { text: String(input.value || "") };
        else {
            const value = G.number(input.value, NaN);
            if (!Number.isFinite(value)) return false;
            if (key === "x" || key === "y" || key === "fontSizeMm") patch = { [key]: value };
        }
        if (!patch) return false;
        try {
            const next = G.setText(object, patch);
            execute(c, D.replaceObject(c.history.current(), next), `Edit text ${key}`);
            return true;
        } catch (error) {
            V.render(c);
            return false;
        }
    }

    function install(c) {
        if (!c || !c.canvas || c.__textAnnotationInstalled) return c;
        c.__textAnnotationInstalled = true;

        const toolCapture = event => {
            const button = event.target.closest && event.target.closest('[data-ddv3-tool="text"]');
            if (!button) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            setTextTool(c);
        };
        const pointerCapture = event => {
            if (c.tool !== G.TEXT_TYPE || event.button !== 0 || c.readOnly) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            startInline(c, V.eventWorld(c, event));
        };
        const doubleClick = event => {
            const target = event.target.closest && event.target.closest("[data-ddv3-object]");
            if (!target || c.readOnly) return;
            const object = D.objectById(c.history.current(), target.dataset.ddv3Object);
            if (!object || object.type !== G.TEXT_TYPE) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            c.tool = G.TEXT_TYPE;
            startInline(c, object.geometry.position, object);
        };
        const inspectorChange = event => {
            const input = event.target.closest && event.target.closest("[data-ddv3-text-prop]");
            if (input) applyInspector(c, input);
        };
        const keyDown = event => {
            if (!c.dialog.$wrapper.is(":visible")) return;
            const target = event.target;
            if (target && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)) return;
            if (!(event.ctrlKey || event.metaKey || event.altKey) && String(event.key || "").toLowerCase() === "t") {
                setTextTool(c);
                event.preventDefault();
            }
        };

        c.root.addEventListener("click", toolCapture, true);
        c.canvas.addEventListener("pointerdown", pointerCapture, true);
        c.canvas.addEventListener("dblclick", doubleClick, true);
        c.inspector.addEventListener("change", inspectorChange, true);
        document.addEventListener("keydown", keyDown, true);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-text-cleanup", () => {
                closeInline(c);
                c.root.removeEventListener("click", toolCapture, true);
                c.canvas.removeEventListener("pointerdown", pointerCapture, true);
                c.canvas.removeEventListener("dblclick", doubleClick, true);
                c.inspector.removeEventListener("change", inspectorChange, true);
                document.removeEventListener("keydown", keyDown, true);
            });
        }
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.TextAnnotationEditor = Object.freeze({ install, setTextTool, startInline, commitInline, applyInspector });
})();
