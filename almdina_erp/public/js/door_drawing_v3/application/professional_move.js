(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const Selection = root.VectorSelectionGeometry;
    const Policy = root.ProfessionalMovePolicy;
    const View = root.ProfessionalMoveView;
    const Editor = root.Editor;
    if (!G || !D || !Selection || !Policy || !View || !Editor) throw new Error("Door Drawing V3 professional move dependencies must load first");

    const DRAG_PX = 4;
    let sequence = 0;

    function nextId(type) { sequence += 1; return `${type || "object"}-${Date.now()}-${sequence}`; }
    function stop(event) {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    }
    function capture(c, event) { try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function release(c, event) { try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function selectedIds(c) {
        const ids = Array.isArray(c.selectedIds) && c.selectedIds.length ? c.selectedIds : (c.selectedId ? [c.selectedId] : []);
        return [...new Set(ids.filter(Boolean).map(String))];
    }
    function selectedObjects(c, ids = selectedIds(c)) {
        const wanted = new Set(ids.map(String));
        return (c.history.current().objects || []).filter(object => wanted.has(String(object.id)) && Selection.boundsOfObject(object));
    }
    function selectableTarget(c, event) {
        if (!event.target || !event.target.closest || !c.canvas.contains(event.target)) return null;
        if (event.target.closest("[data-ddv3-transform-handle], [data-ddv3-oriented-transform-handle], [data-ddv3-path-node], [data-ddv3-path-handle], [data-ddv3-handle]")) return null;
        const element = event.target.closest("[data-ddv3-object]");
        if (!element) return null;
        const object = D.objectById(c.history.current(), element.dataset.ddv3Object);
        return object && Selection.boundsOfObject(object) ? object : null;
    }
    function setSelection(c, ids, primary) {
        c.selectedIds = [...new Set(ids.map(String))];
        c.selectedId = primary && c.selectedIds.includes(String(primary)) ? String(primary) : (c.selectedIds[c.selectedIds.length - 1] || "");
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.selectedNodeIndices = [];
        c.selectedSegmentIndices = [];
    }
    function moveDistancePx(c, start, current) {
        return G.distance(start, current) * Math.max(0.000001, Number(c.viewport.scale || 1));
    }
    function axisFor(gesture, dx, dy, shiftKey) {
        if (!shiftKey) { gesture.lockedAxis = null; return null; }
        if (!gesture.lockedAxis) gesture.lockedAxis = Math.abs(dx) >= Math.abs(dy) ? "x" : "y";
        return gesture.lockedAxis;
    }
    function schedule(c) {
        if (root.VectorEditingView) root.VectorEditingView.schedule(c);
        if (root.TransformBoxView) root.TransformBoxView.schedule(c);
        View.schedule(c);
    }
    function fullRender(c) { root.ShapeView.render(c); schedule(c); }

    function begin(c, event) {
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || c.transformGesture || c.orientedTransformGesture || event.button !== 0) return false;
        const target = selectableTarget(c, event);
        if (!target) return false;

        const currentIds = selectedIds(c);
        const targetId = String(target.id);
        let ids;
        if (currentIds.includes(targetId)) ids = currentIds;
        else if (event.shiftKey && currentIds.length) ids = [...currentIds, targetId];
        else if (event.ctrlKey || event.metaKey) return false;
        else ids = [targetId];
        setSelection(c, ids, targetId);
        const objects = selectedObjects(c, ids);
        const bounds = Selection.unionBounds(objects);
        if (!objects.length || !bounds) return false;

        c.professionalMoveGesture = {
            pointerId: event.pointerId,
            startWorld: root.ShapeView.eventWorld(c, event),
            objects,
            ids: objects.map(object => String(object.id)),
            sourceBounds: bounds,
            duplicateMode: Boolean(event.altKey),
            moved: false,
            lockedAxis: null,
            stickyCandidate: null,
        };
        c.professionalMoveDuplicate = Boolean(event.altKey);
        c.professionalMoveGuideState = null;
        c.vectorActiveTranslation = { ids: c.professionalMoveGesture.ids, dx: 0, dy: 0 };
        c.vectorSnapState = null;
        capture(c, event);
        schedule(c);
        stop(event);
        return true;
    }

    function move(c, event) {
        const gesture = c.professionalMoveGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        const current = root.ShapeView.eventWorld(c, event);
        let dx = current.x - gesture.startWorld.x;
        let dy = current.y - gesture.startWorld.y;
        if (!gesture.moved && moveDistancePx(c, gesture.startWorld, current) >= DRAG_PX) gesture.moved = true;
        if (event.altKey) gesture.duplicateMode = true;
        c.professionalMoveDuplicate = Boolean(gesture.duplicateMode);
        const lockedAxis = axisFor(gesture, dx, dy, Boolean(event.shiftKey));
        if (lockedAxis === "x") dy = 0;
        if (lockedAxis === "y") dx = 0;

        const resolved = Policy.resolve(c.history.current(), gesture.objects, dx, dy, {
            viewportScale: c.viewport.scale,
            lockedAxis,
            includeSourceTargets: Boolean(gesture.duplicateMode),
            stickyCandidate: gesture.stickyCandidate,
        });
        gesture.stickyCandidate = resolved.stickyCandidate || null;
        c.professionalMoveGuideState = resolved;
        c.vectorActiveTranslation = { ids: gesture.ids, dx: resolved.dx, dy: resolved.dy };
        schedule(c);
        stop(event);
        return true;
    }

    function cloneTranslated(object, dx, dy) {
        const cloned = G.cloneObject(object, nextId(object.type));
        return G.translateObject(cloned, dx, dy);
    }
    function adjustPivotAfterMove(c, dx, dy, duplicated) {
        if (duplicated) {
            c.orientedTransformPivot = null;
            c.orientedTransformSelectionKey = "";
            return;
        }
        if (c.orientedTransformPivot) c.orientedTransformPivot = G.point(c.orientedTransformPivot.x + dx, c.orientedTransformPivot.y + dy);
    }
    function commit(c, gesture, translation) {
        const dx = G.number(translation && translation.dx), dy = G.number(translation && translation.dy);
        let document = c.history.current();
        let ids = gesture.ids.slice();
        if (gesture.duplicateMode) {
            ids = [];
            gesture.objects.forEach(object => {
                const clone = cloneTranslated(object, dx, dy);
                document = D.addObject(document, clone);
                ids.push(String(clone.id));
            });
            c.history.execute(document, `Duplicate and move ${gesture.objects.length} object${gesture.objects.length === 1 ? "" : "s"}`);
        } else {
            gesture.objects.forEach(object => { document = D.replaceObject(document, G.translateObject(object, dx, dy)); });
            c.history.execute(document, `Move ${gesture.objects.length} object${gesture.objects.length === 1 ? "" : "s"}`);
        }
        c.dirty = true;
        setSelection(c, ids, ids[ids.length - 1]);
        adjustPivotAfterMove(c, dx, dy, gesture.duplicateMode);
    }
    function clear(c) {
        c.professionalMoveGesture = null;
        c.professionalMoveDuplicate = false;
        c.professionalMoveGuideState = null;
        c.vectorActiveTranslation = null;
        c.vectorSnapState = null;
    }
    function end(c, event) {
        const gesture = c.professionalMoveGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        const translation = c.vectorActiveTranslation || { dx: 0, dy: 0 };
        release(c, event);
        if (gesture.moved && (Math.abs(translation.dx) >= G.EPSILON_MM || Math.abs(translation.dy) >= G.EPSILON_MM)) commit(c, gesture, translation);
        clear(c);
        fullRender(c);
        stop(event);
        return true;
    }
    function cancel(c, event = null) {
        const gesture = c.professionalMoveGesture;
        if (!gesture) return false;
        if (event && event.pointerId != null && gesture.pointerId !== event.pointerId) return false;
        if (event && event.pointerId != null) release(c, event);
        clear(c);
        fullRender(c);
        if (event) stop(event);
        return true;
    }
    function keyDown(c, event) {
        if (event.key !== "Escape" || !c.professionalMoveGesture) return false;
        cancel(c);
        stop(event);
        return true;
    }

    function install(c) {
        if (!c || !c.canvas || c.__professionalMoveInstalled) return c;
        c.__professionalMoveInstalled = true;
        c.professionalMoveGesture = null;
        c.professionalMoveDuplicate = false;
        c.professionalMoveGuideState = null;

        const onPointerDown = event => begin(c, event);
        const onPointerMove = event => move(c, event);
        const onPointerUp = event => end(c, event);
        const onPointerCancel = event => cancel(c, event);
        const onKeyDown = event => keyDown(c, event);
        window.addEventListener("pointerdown", onPointerDown, true);
        window.addEventListener("pointermove", onPointerMove, true);
        window.addEventListener("pointerup", onPointerUp, true);
        window.addEventListener("pointercancel", onPointerCancel, true);
        window.addEventListener("keydown", onKeyDown, true);

        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-professional-move-cleanup", () => {
            window.removeEventListener("pointerdown", onPointerDown, true);
            window.removeEventListener("pointermove", onPointerMove, true);
            window.removeEventListener("pointerup", onPointerUp, true);
            window.removeEventListener("pointercancel", onPointerCancel, true);
            window.removeEventListener("keydown", onKeyDown, true);
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
    root.ProfessionalMove = Object.freeze({ install, begin, move, end, cancel, axisFor, cloneTranslated });
})();
