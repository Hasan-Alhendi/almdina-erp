(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const Editor = root.Editor;
    if (!G || !D || !Editor) throw new Error("Door Drawing V3 geometry, document model, and editor must load before editor shortcuts");

    const PASTE_OFFSET_MM = 20;
    const PHYSICAL_SHORTCUTS = Object.freeze({
        KeyA: "a",
        KeyC: "c",
        KeyD: "d",
        KeyV: "v",
        KeyX: "x",
        KeyY: "y",
        KeyZ: "z",
    });
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

    function shortcutKey(event) {
        const code = String(event && event.code || "");
        if (PHYSICAL_SHORTCUTS[code]) return PHYSICAL_SHORTCUTS[code];
        return String(event && event.key || "").toLowerCase();
    }

    function selectedObjectIds(c) {
        const selectedId = String(c && c.selectedId || "");
        const group = Array.isArray(c && c.selectedIds) ? c.selectedIds.filter(Boolean).map(String) : [];
        const candidates = selectedId && !group.includes(selectedId) ? [selectedId] : (group.length ? group : (selectedId ? [selectedId] : []));
        return [...new Set(candidates)].filter(id => D.objectById(c.history.current(), id));
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
        clipboard = { objects: objects.map(object => G.cloneObject(object)), pasteSerial: 0 };
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

    function cutSelection(c) {
        if (c.readOnly) return false;
        const ids = selectedObjectIds(c);
        if (!ids.length || !copySelection(c)) return false;
        let document = c.history.current();
        try { ids.forEach(id => { document = D.removeObject(document, id); }); }
        catch (error) { return false; }
        c.history.execute(document, ids.length > 1 ? `Cut ${ids.length} objects` : "Cut object");
        c.dirty = true;
        setSelection(c, []);
        render(c);
        return true;
    }

    function selectAll(c) {
        const ids = (c.history.current().objects || []).map(object => String(object.id));
        if (!ids.length) return false;
        setSelection(c, ids);
        render(c);
        return true;
    }

    function duplicateSelection(c) {
        if (!copySelection(c)) return false;
        return pasteSelection(c);
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
        const key = shortcutKey(event);

        if (key === "c") {
            if (!copySelection(c)) return false;
            stop(event);
            return true;
        }
        if (key === "x") {
            if (!cutSelection(c)) return false;
            stop(event);
            return true;
        }
        if (key === "v") {
            if (!pasteSelection(c)) return false;
            stop(event);
            return true;
        }
        if (key === "a") {
            if (!selectAll(c)) return false;
            stop(event);
            return true;
        }
        if (key === "d") {
            if (!duplicateSelection(c)) return false;
            stop(event);
            return true;
        }
        if (key === "z") {
            event.shiftKey ? redo(c) : undo(c);
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
        shortcutKey,
        editingTarget,
        focusCanvas,
        copySelection,
        cutSelection,
        pasteSelection,
        selectAll,
        duplicateSelection,
        undo,
        redo,
        selectedObjectIds,
    });
})();
