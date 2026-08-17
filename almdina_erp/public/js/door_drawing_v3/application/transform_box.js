(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const Selection = root.VectorSelectionGeometry;
    const T = root.TransformDomain;
    const View = root.TransformBoxView;
    const Editor = root.Editor;
    if (!G || !D || !S || !Selection || !T || !View || !Editor) throw new Error("Door Drawing V3 transform dependencies must load before transform box application");

    const MIN_SCALE = 0.001;

    function render(c) {
        root.ShapeView.render(c);
        if (root.VectorEditingView) root.VectorEditingView.schedule(c);
        View.schedule(c);
    }
    function stop(event) {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    }
    function capture(c, event) { try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function release(c, event) { try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function selectedObjects(c) { return View.selectedObjects(c); }
    function selectedIds(c) { return selectedObjects(c).map(object => String(object.id)); }
    function temporaryDocument(c, ids) {
        const excluded = new Set((ids || []).map(String));
        const current = c.history.current();
        return { ...current, objects: (current.objects || []).filter(object => !excluded.has(String(object.id))) };
    }
    function snapPoint(c, raw, ids) {
        const result = S.resolvePoint(temporaryDocument(c, ids), raw, {
            viewportScale: c.viewport.scale,
            stickyTarget: c.vectorSnapState && c.vectorSnapState.target,
        });
        c.vectorSnapState = result;
        return result.point;
    }
    function safeScale(value) {
        if (!Number.isFinite(value)) return 1;
        if (Math.abs(value) >= MIN_SCALE) return value;
        return value < 0 ? -MIN_SCALE : MIN_SCALE;
    }
    function pivotFor(box, role, fromCenter) {
        if (fromCenter) return G.point(box.cx, box.cy);
        const x = role.includes("w") ? box.right : role.includes("e") ? box.left : box.cx;
        const y = role.includes("n") ? box.top : role.includes("s") ? box.bottom : box.cy;
        return G.point(x, y);
    }
    function resizeMatrix(gesture, point, event) {
        const box = gesture.sourceBounds, role = gesture.role;
        const pivot = pivotFor(box, role, Boolean(event.altKey));
        const start = View.handleWorld(box, role);
        const useX = role.includes("e") || role.includes("w");
        const useY = role.includes("n") || role.includes("s");
        let sx = 1, sy = 1;
        if (useX && Math.abs(start.x - pivot.x) >= G.EPSILON_MM) sx = safeScale((point.x - pivot.x) / (start.x - pivot.x));
        if (useY && Math.abs(start.y - pivot.y) >= G.EPSILON_MM) sy = safeScale((point.y - pivot.y) / (start.y - pivot.y));
        if (event.shiftKey) {
            if (useX && useY) {
                const xChange = Math.abs(Math.abs(sx) - 1), yChange = Math.abs(Math.abs(sy) - 1);
                const magnitude = xChange >= yChange ? Math.abs(sx) : Math.abs(sy);
                sx = (sx < 0 ? -1 : 1) * magnitude;
                sy = (sy < 0 ? -1 : 1) * magnitude;
            } else if (useX) sy = Math.abs(sx);
            else if (useY) sx = Math.abs(sy);
        }
        return T.scaleAround(pivot, sx, sy);
    }
    function transformedBounds(box, matrix) {
        const points = [
            T.transformPoint(G.point(box.left, box.top), matrix),
            T.transformPoint(G.point(box.right, box.top), matrix),
            T.transformPoint(G.point(box.right, box.bottom), matrix),
            T.transformPoint(G.point(box.left, box.bottom), matrix),
        ];
        return Selection.bounds(
            Math.min(...points.map(point => point.x)),
            Math.min(...points.map(point => point.y)),
            Math.max(...points.map(point => point.x)),
            Math.max(...points.map(point => point.y))
        );
    }
    function beginResize(c, event, role) {
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || event.button !== 0) return false;
        const objects = selectedObjects(c), sourceBounds = Selection.unionBounds(objects);
        if (!objects.length || !sourceBounds || !View.HANDLE_ROLES.includes(role)) return false;
        c.transformGesture = { type: "resize", pointerId: event.pointerId, role, objects, ids: objects.map(object => String(object.id)), sourceBounds };
        c.transformPreviewMatrix = T.identity();
        c.transformPreviewBounds = sourceBounds;
        c.vectorSnapState = null;
        capture(c, event);
        render(c);
        stop(event);
        return true;
    }
    function moveResize(c, event) {
        const gesture = c.transformGesture;
        if (!gesture || gesture.type !== "resize" || gesture.pointerId !== event.pointerId) return false;
        const raw = root.ShapeView.eventWorld(c, event);
        const point = snapPoint(c, raw, gesture.ids);
        const matrix = resizeMatrix(gesture, point, event);
        c.transformPreviewMatrix = matrix;
        c.transformPreviewBounds = transformedBounds(gesture.sourceBounds, matrix);
        render(c);
        stop(event);
        return true;
    }
    function applyMatrix(c, objects, matrix, label) {
        if (!objects.length) return false;
        let document = c.history.current();
        try {
            objects.forEach(object => { document = D.replaceObject(document, T.transformObject(object, matrix)); });
        } catch (error) {
            c.transformPreviewMatrix = null;
            c.transformPreviewBounds = null;
            render(c);
            return false;
        }
        c.history.execute(document, label);
        c.dirty = true;
        c.selectedIds = objects.map(object => String(object.id));
        c.selectedId = c.selectedIds[c.selectedIds.length - 1] || "";
        c.transformPreviewMatrix = null;
        c.transformPreviewBounds = null;
        c.vectorSnapState = null;
        render(c);
        return true;
    }
    function endResize(c, event) {
        const gesture = c.transformGesture;
        if (!gesture || gesture.type !== "resize" || gesture.pointerId !== event.pointerId) return false;
        const matrix = c.transformPreviewMatrix;
        c.transformGesture = null;
        release(c, event);
        if (!matrix) { render(c); stop(event); return true; }
        applyMatrix(c, gesture.objects, matrix, `Resize ${gesture.objects.length} object${gesture.objects.length === 1 ? "" : "s"}`);
        stop(event);
        return true;
    }
    function cancelResize(c, event) {
        const gesture = c.transformGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        c.transformGesture = null;
        c.transformPreviewMatrix = null;
        c.transformPreviewBounds = null;
        c.vectorSnapState = null;
        release(c, event);
        render(c);
        stop(event);
        return true;
    }
    function flip(c, axis) {
        if (c.readOnly || c.nodeEditId) return false;
        const objects = selectedObjects(c), box = Selection.unionBounds(objects);
        if (!objects.length || !box) return false;
        const matrix = axis === "horizontal" ? T.flipHorizontal(box) : T.flipVertical(box);
        return applyMatrix(c, objects, matrix, axis === "horizontal" ? "Flip horizontally" : "Flip vertically");
    }
    function transformProperty(c, input) {
        if (!input || input.disabled || c.readOnly || c.nodeEditId) return false;
        const objects = selectedObjects(c), box = Selection.unionBounds(objects);
        if (!objects.length || !box) return false;
        const key = input.dataset.ddv3TransformProp;
        const value = G.number(input.value, NaN);
        if (!Number.isFinite(value)) return false;
        let matrix = null, label = "Transform selection";
        if (key === "x") { matrix = T.translation(value - box.left, 0); label = "Set selection X"; }
        else if (key === "y") { matrix = T.translation(0, value - box.bottom); label = "Set selection Y"; }
        else if (key === "width" && value >= G.EPSILON_MM && box.width >= G.EPSILON_MM) {
            matrix = T.scaleAround(G.point(box.left, box.bottom), value / box.width, 1); label = "Set selection width";
        } else if (key === "height" && value >= G.EPSILON_MM && box.height >= G.EPSILON_MM) {
            matrix = T.scaleAround(G.point(box.left, box.bottom), 1, value / box.height); label = "Set selection height";
        }
        return matrix ? applyMatrix(c, objects, matrix, label) : false;
    }
    function pointerDown(c, event) {
        const handle = event.target && event.target.closest ? event.target.closest("[data-ddv3-transform-handle]") : null;
        if (!handle || !c.canvas.contains(handle)) return false;
        return beginResize(c, event, handle.dataset.ddv3TransformHandle);
    }
    function click(c, event) {
        const action = event.target && event.target.closest ? event.target.closest("[data-ddv3-transform-action]") : null;
        if (!action || !c.root.contains(action)) return false;
        const handled = action.dataset.ddv3TransformAction === "flip-horizontal" ? flip(c, "horizontal")
            : action.dataset.ddv3TransformAction === "flip-vertical" ? flip(c, "vertical") : false;
        if (handled) stop(event);
        return handled;
    }
    function change(c, event) {
        const input = event.target && event.target.closest ? event.target.closest("[data-ddv3-transform-prop]") : null;
        if (!input || !c.inspector.contains(input)) return false;
        return transformProperty(c, input);
    }
    function inspectorKeyDown(c, event) {
        if (event.key !== "Enter") return false;
        const input = event.target && event.target.closest ? event.target.closest("[data-ddv3-transform-prop]") : null;
        if (!input || !c.inspector.contains(input)) return false;
        event.preventDefault();
        transformProperty(c, input);
        input.blur();
        return true;
    }

    function install(c) {
        if (!c || !c.root || !c.canvas || c.__transformBoxInstalled) return c;
        c.__transformBoxInstalled = true;
        c.transformGesture = null;
        c.transformPreviewMatrix = null;
        c.transformPreviewBounds = null;
        const onPointerDown = event => pointerDown(c, event);
        const onPointerMove = event => moveResize(c, event);
        const onPointerUp = event => endResize(c, event);
        const onPointerCancel = event => cancelResize(c, event);
        const onClick = event => click(c, event);
        const onChange = event => change(c, event);
        const onInspectorKeyDown = event => inspectorKeyDown(c, event);

        window.addEventListener("pointerdown", onPointerDown, true);
        window.addEventListener("pointermove", onPointerMove, true);
        window.addEventListener("pointerup", onPointerUp, true);
        window.addEventListener("pointercancel", onPointerCancel, true);
        c.root.addEventListener("click", onClick, true);
        c.inspector.addEventListener("change", onChange, true);
        c.inspector.addEventListener("keydown", onInspectorKeyDown, true);
        View.decorate(c);

        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-transform-box-cleanup", () => {
            window.removeEventListener("pointerdown", onPointerDown, true);
            window.removeEventListener("pointermove", onPointerMove, true);
            window.removeEventListener("pointerup", onPointerUp, true);
            window.removeEventListener("pointercancel", onPointerCancel, true);
            c.root.removeEventListener("click", onClick, true);
            c.inspector.removeEventListener("change", onChange, true);
            c.inspector.removeEventListener("keydown", onInspectorKeyDown, true);
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
    root.TransformBox = Object.freeze({ install, resizeMatrix, transformedBounds, applyMatrix, flip, transformProperty });
})();
