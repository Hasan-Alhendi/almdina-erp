(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const Editor = root.Editor;
    if (!G || !D || !Editor) throw new Error("Door Drawing V3 geometry, document model, and editor must load before editor shortcuts");

    const PASTE_OFFSET_MM = 20;
    let clipboard = null;
    let sequence = 0;

    function nextId(type = "object") {
        sequence += 1;
        return `${String(type || "object")}-${Date.now()}-${sequence}`;
    }

    function isEditableTarget(target) {
        return Boolean(target && ((target.matches && target.matches("input, textarea, select")) || target.isContentEditable));
    }

    function editingTarget(c, event) {
        const target = event && event.target;
        if (!isEditableTarget(target)) return false;
        // The drawing dialog owns keyboard shortcuts while it is open. A stale focus
        // left on the ERPNext form behind the modal must never disable Ctrl+C/V/Z/Y.
        // Native text editing is preserved only for an actual editor field inside DDV3.
        if (c && c.root && typeof c.root.contains === "function") return c.root.contains(target);
        return true;
    }

    function editorVisible(c) {
        if (!c || !c.root || !c.root.isConnected) return false;
        if (c.dialog && c.dialog.$wrapper && typeof c.dialog.$wrapper.is === "function") return c.dialog.$wrapper.is(":visible");
        return true;
    }

    function focusCanvas(c) {
        if (!c || !c.canvas) return false;
        try {
            if (typeof c.canvas.setAttribute === "function") {
                c.canvas.setAttribute("tabindex", "0");
                if (!c.canvas.getAttribute || !c.canvas.getAttribute("aria-label")) c.canvas.setAttribute("aria-label", "مساحة رسم الدرفة");
            }
            if (typeof c.canvas.focus === "function") {
                try { c.canvas.focus({ preventScroll: true }); }
                catch (error) { c.canvas.focus(); }
            }
            return true;
        } catch (error) {
            return false;
        }
    }

    function selectedObjectIds(c) {
        const candidates = Array.isArray(c.selectedIds) && c.selectedIds.length
            ? c.selectedIds
            : (c.selectedId ? [c.selectedId] : []);
        return [...new Set(candidates.filter(Boolean).map(String))]
            .filter(id => D.objectById(c.history.current(), id));
    }

    function selectedObjects(c) {
        return selectedObjectIds(c).map(id => D.objectById(c.history.current(), id)).filter(Boolean);
    }

    function render(c) {
        root.ShapeView.render(c);
        if (root.VectorEditingView) root.VectorEditingView.schedule(c);
        if (root.BezierPathView) root.BezierPathView.schedule(c);
    }

    function clearPathSubselection(c) {
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.selectedNodeIndices = [];
        c.selectedSegmentIndices = [];
        c.previewObject = null;
        c.vectorSnapState = null;
        c.snapState = null;
    }

    function setSelection(c, ids) {
        const clean = [...new Set((ids || []).filter(Boolean).map(String))]
            .filter(id => D.objectById(c.history.current(), id));
        c.selectedIds = clean;
        c.selectedId = clean[clean.length - 1] || "";
        clearPathSubselection(c);
    }

    function copySelection(c) {
        const objects = selectedObjects(c);
        if (!objects.length) return false;
        clipboard = {
            objects: objects.map(object => G.cloneObject(object)),
            pasteSerial: 0,
        };
        return true;
    }

    function pasteSelection(c) {
        if (c.readOnly || !clipboard || !clipboard.objects.length) return false;
        clipboard.pasteSerial += 1;
        const offset = PASTE_OFFSET_MM * clipboard.pasteSerial;
        let document = c.history.current();
        const ids = [];
        try {
            clipboard.objects.forEach(source => {
                const clone = G.cloneObject(source, nextId(source.type));
                // World Y grows upward, so negative Y produces the familiar visual down-right paste offset.
                const moved = G.translateObject(clone, offset, -offset);
                document = D.addObject(document, moved);
                ids.push(String(moved.id));
            });
        } catch (error) {
            return false;
        }
        c.history.execute(document, ids.length > 1 ? `Paste ${ids.length} objects` : "Paste object");
        c.dirty = true;
        setSelection(c, ids);
        render(c);
        return true;
    }

    function syncSelectionAfterHistory(c) {
        const current = c.history.current();
        const ids = selectedObjectIds(c).filter(id => D.objectById(current, id));
        c.selectedIds = ids;
        c.selectedId = ids.includes(String(c.selectedId || "")) ? String(c.selectedId) : (ids[ids.length - 1] || "");
        if (!c.nodeEditId || !D.objectById(current, c.nodeEditId)) clearPathSubselection(c);
    }

    function undo(c) {
        if (c.readOnly) return false;
        const before = c.history.current();
        const after = c.history.undo();
        if (after === before) return false;
        c.dirty = true;
        syncSelectionAfterHistory(c);
        render(c);
        return true;
    }

    function redo(c) {
        if (c.readOnly) return false;
        const before = c.history.current();
        const after = c.history.redo();
        if (after === before) return false;
        c.dirty = true;
        syncSelectionAfterHistory(c);
        render(c);
        return true;
    }

    function stop(event) {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    }

    function keyDown(c, event) {
        if (!editorVisible(c) || c.readOnly || editingTarget(c, event)) return false;
        const mod = Boolean(event.ctrlKey || event.metaKey);
        if (!mod || event.altKey) return false;
        const key = String(event.key || "").toLowerCase();

        if (key === "c") {
            if (!copySelection(c)) return false;
            stop(event);
            return true;
        }
        if (key === "v") {
            if (!pasteSelection(c)) return false;
            stop(event);
            return true;
        }
        if (key === "z") {
            event.shiftKey ? redo(c) : undo(c);
            // Keep the browser from interpreting Ctrl/Cmd+Z even when the history stack is empty.
            stop(event);
            return true;
        }
        if (key === "y") {
            redo(c);
            stop(event);
            return true;
        }
        return false;
    }

    function install(c) {
        if (!c || !c.root || c.__editorShortcutsInstalled) return c;
        c.__editorShortcutsInstalled = true;
        const onKeyDown = event => keyDown(c, event);
        const onRootPointerDown = event => {
            const target = event && event.target;
            if (!target || isEditableTarget(target)) return;
            if (c.canvas && typeof c.canvas.contains === "function" && c.canvas.contains(target)) focusCanvas(c);
        };

        // Window capture runs before the legacy document-level shortcut handler, giving one
        // authoritative implementation for copy/paste/undo/redo without duplicating commands.
        window.addEventListener("keydown", onKeyDown, true);
        c.root.addEventListener("pointerdown", onRootPointerDown, true);
        focusCanvas(c);

        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-editor-shortcuts-cleanup", () => {
            window.removeEventListener("keydown", onKeyDown, true);
            c.root.removeEventListener("pointerdown", onRootPointerDown, true);
        });
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        ...Editor,
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.EditorShortcuts = Object.freeze({
        install,
        keyDown,
        editingTarget,
        focusCanvas,
        copySelection,
        pasteSelection,
        undo,
        redo,
        selectedObjectIds,
    });
})();
