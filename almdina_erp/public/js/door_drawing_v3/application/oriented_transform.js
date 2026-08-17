(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const T = root.TransformDomain;
    const O = root.OrientedTransformDomain;
    const View = root.OrientedTransformView;
    const Editor = root.Editor;
    if (!G || !D || !S || !T || !O || !View || !Editor) throw new Error("Door Drawing V3 oriented transform dependencies must load first");

    function stop(event) {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    }
    function capture(c, event) { try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function release(c, event) { try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function selectedObjects(c) { return View.selectedObjects(c); }
    function selectedIds(c) { return selectedObjects(c).map(object => String(object.id)); }
    function render(c) {
        root.ShapeView.render(c);
        if (root.VectorEditingView) root.VectorEditingView.schedule(c);
        if (root.TransformBoxView) root.TransformBoxView.schedule(c);
        View.schedule(c);
    }
    function clearPreview(c) {
        c.transformPreviewMatrix = null;
        c.transformPreviewBounds = null;
        c.orientedTransformPreviewFrame = null;
        c.vectorSnapState = null;
    }
    function previewFrameFromResize(source, matrix, sx, sy) {
        return Object.freeze({
            center: T.transformPoint(source.center, matrix),
            width: Math.max(G.EPSILON_MM, Math.abs(sx) * source.width),
            height: Math.max(G.EPSILON_MM, Math.abs(sy) * source.height),
            angleDeg: source.angleDeg,
            area: Math.abs(sx * sy) * source.width * source.height,
        });
    }
    function previewFrameFromRotation(source, matrix, delta) {
        return Object.freeze({
            center: T.transformPoint(source.center, matrix),
            width: source.width,
            height: source.height,
            angleDeg: O.normalize360(source.angleDeg + delta),
            area: source.width * source.height,
        });
    }
    function applyMatrix(c, objects, matrix, label, options = {}) {
        if (!objects.length || !matrix) return false;
        let document = c.history.current();
        try { objects.forEach(object => { document = D.replaceObject(document, T.transformObject(object, matrix)); }); }
        catch (error) { clearPreview(c); render(c); return false; }
        c.history.execute(document, label);
        c.dirty = true;
        c.selectedIds = objects.map(object => String(object.id));
        c.selectedId = c.selectedIds[c.selectedIds.length - 1] || "";
        if (Number.isFinite(Number(options.preferredAngle))) c.orientedTransformPreferredAngle = O.normalize360(Number(options.preferredAngle));
        if (options.transformPivot && c.orientedTransformPivot) c.orientedTransformPivot = T.transformPoint(c.orientedTransformPivot, matrix);
        clearPreview(c);
        render(c);
        return true;
    }

    function begin(c, event) {
        if (c.readOnly || c.tool !== "select" || c.nodeEditId || c.professionalMoveGesture || event.button !== 0) return false;
        if (!event.target || !event.target.closest || !c.canvas.contains(event.target)) return false;
        const handle = event.target.closest("[data-ddv3-oriented-transform-handle]");
        if (!handle) return false;
        const role = handle.dataset.ddv3OrientedTransformHandle;
        const objects = selectedObjects(c), frame = View.sourceFrame(c);
        if (!objects.length || !frame) return false;
        const pivot = View.pivot(c, frame) || frame.center;
        const pointer = root.ShapeView.eventWorld(c, event);
        c.orientedTransformGesture = {
            type: role === "rotate" ? "rotate" : role === "pivot" ? "pivot" : "resize",
            role,
            pointerId: event.pointerId,
            objects,
            ids: objects.map(object => String(object.id)),
            sourceFrame: frame,
            startPointer: pointer,
            pivot,
        };
        c.orientedTransformPreviewFrame = frame;
        c.transformPreviewMatrix = T.identity();
        c.vectorSnapState = null;
        capture(c, event);
        render(c);
        stop(event);
        return true;
    }

    function moveResize(c, gesture, event) {
        const pointer = root.ShapeView.eventWorld(c, event);
        const result = O.resizeMatrix(gesture.sourceFrame, gesture.role, pointer, {
            keepAspect: Boolean(event.shiftKey),
            fromCenter: Boolean(event.altKey),
        });
        c.transformPreviewMatrix = result.matrix;
        c.orientedTransformPreviewFrame = previewFrameFromResize(gesture.sourceFrame, result.matrix, result.sx, result.sy);
        gesture.previewAngle = gesture.sourceFrame.angleDeg;
        gesture.previewMatrix = result.matrix;
        gesture.previewScale = { sx: result.sx, sy: result.sy };
        render(c);
        return true;
    }
    function moveRotate(c, gesture, event) {
        const pointer = root.ShapeView.eventWorld(c, event);
        let delta = O.rotationDelta(gesture.pivot, gesture.startPointer, pointer);
        let absolute = O.normalize360(gesture.sourceFrame.angleDeg + delta);
        if (event.shiftKey) {
            absolute = O.snapAngle(absolute, 15);
            delta = O.normalize360(absolute - gesture.sourceFrame.angleDeg);
        }
        const matrix = T.rotateAround(gesture.pivot, delta);
        c.transformPreviewMatrix = matrix;
        c.orientedTransformPreviewFrame = previewFrameFromRotation(gesture.sourceFrame, matrix, delta);
        gesture.previewAngle = absolute;
        gesture.previewMatrix = matrix;
        render(c);
        return true;
    }
    function movePivot(c, gesture, event) {
        const raw = root.ShapeView.eventWorld(c, event);
        const snap = S.resolvePoint(c.history.current(), raw, { viewportScale: c.viewport.scale, stickyTarget: c.vectorSnapState && c.vectorSnapState.target });
        c.vectorSnapState = snap;
        c.orientedTransformPivot = snap.point;
        c.orientedTransformPreviewFrame = gesture.sourceFrame;
        render(c);
        return true;
    }
    function move(c, event) {
        const gesture = c.orientedTransformGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        if (gesture.type === "resize") moveResize(c, gesture, event);
        else if (gesture.type === "rotate") moveRotate(c, gesture, event);
        else movePivot(c, gesture, event);
        stop(event);
        return true;
    }

    function end(c, event) {
        const gesture = c.orientedTransformGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        release(c, event);
        c.orientedTransformGesture = null;
        if (gesture.type === "pivot") {
            clearPreview(c);
            render(c);
            stop(event);
            return true;
        }
        const matrix = gesture.previewMatrix || c.transformPreviewMatrix;
        const preferredAngle = Number.isFinite(Number(gesture.previewAngle)) ? gesture.previewAngle : gesture.sourceFrame.angleDeg;
        const transformPivot = gesture.type === "resize";
        applyMatrix(c, gesture.objects, matrix, gesture.type === "rotate" ? "Rotate selection" : "Resize selection", { preferredAngle, transformPivot });
        stop(event);
        return true;
    }
    function cancel(c, event = null) {
        const gesture = c.orientedTransformGesture;
        if (!gesture) return false;
        if (event && event.pointerId != null && gesture.pointerId !== event.pointerId) return false;
        if (event && event.pointerId != null) release(c, event);
        c.orientedTransformGesture = null;
        if (gesture.type === "pivot") c.orientedTransformPivot = gesture.pivot;
        clearPreview(c);
        render(c);
        if (event) stop(event);
        return true;
    }

    function localFlip(c, axis) {
        if (c.readOnly || c.nodeEditId) return false;
        const objects = selectedObjects(c), frame = View.sourceFrame(c);
        if (!objects.length || !frame) return false;
        const matrix = O.composeLocalScale(frame, G.point(0, 0), axis === "horizontal" ? -1 : 1, axis === "vertical" ? -1 : 1);
        return applyMatrix(c, objects, matrix, axis === "horizontal" ? "Flip horizontally" : "Flip vertically", { preferredAngle: frame.angleDeg, transformPivot: true });
    }
    function resetPivot(c) {
        const frame = View.sourceFrame(c);
        if (!frame) return false;
        c.orientedTransformPivot = frame.center;
        render(c);
        return true;
    }
    function action(c, event) {
        const button = event.target && event.target.closest ? event.target.closest("[data-ddv3-oriented-action]") : null;
        if (!button || !c.root.contains(button)) return false;
        const name = button.dataset.ddv3OrientedAction;
        const handled = name === "flip-horizontal" ? localFlip(c, "horizontal")
            : name === "flip-vertical" ? localFlip(c, "vertical")
                : name === "reset-pivot" ? resetPivot(c) : false;
        if (handled) stop(event);
        return handled;
    }

    function property(c, input) {
        if (!input || input.disabled || c.readOnly || c.nodeEditId) return false;
        const objects = selectedObjects(c), frame = View.sourceFrame(c);
        if (!objects.length || !frame) return false;
        const key = input.dataset.ddv3OrientedProp;
        const value = Number(input.value);
        if (!Number.isFinite(value)) return false;
        const origin = O.handleWorld(frame, "sw");
        if (key === "pivot-x" || key === "pivot-y") {
            const current = View.pivot(c, frame) || frame.center;
            c.orientedTransformPivot = key === "pivot-x" ? G.point(value, current.y) : G.point(current.x, value);
            render(c);
            return true;
        }
        let matrix = null, label = "Transform selection", preferredAngle = frame.angleDeg, transformPivot = true;
        if (key === "x") { matrix = T.translation(value - origin.x, 0); label = "Set selection X"; }
        else if (key === "y") { matrix = T.translation(0, value - origin.y); label = "Set selection Y"; }
        else if (key === "width" && value >= G.EPSILON_MM) {
            matrix = O.composeLocalScale(frame, O.handleLocal(frame, "sw"), value / frame.width, 1); label = "Set selection width";
        } else if (key === "height" && value >= G.EPSILON_MM) {
            matrix = O.composeLocalScale(frame, O.handleLocal(frame, "sw"), 1, value / frame.height); label = "Set selection height";
        } else if (key === "rotation") {
            const pivot = View.pivot(c, frame) || frame.center;
            const delta = O.normalize360(value - frame.angleDeg);
            matrix = T.rotateAround(pivot, delta); label = "Set selection rotation"; preferredAngle = O.normalize360(value); transformPivot = false;
        }
        return matrix ? applyMatrix(c, objects, matrix, label, { preferredAngle, transformPivot }) : false;
    }
    function change(c, event) {
        const input = event.target && event.target.closest ? event.target.closest("[data-ddv3-oriented-prop]") : null;
        if (!input || !c.inspector.contains(input)) return false;
        return property(c, input);
    }
    function inspectorKey(c, event) {
        if (event.key !== "Enter") return false;
        const input = event.target && event.target.closest ? event.target.closest("[data-ddv3-oriented-prop]") : null;
        if (!input || !c.inspector.contains(input)) return false;
        event.preventDefault();
        property(c, input);
        input.blur();
        return true;
    }
    function keyDown(c, event) {
        if (event.key !== "Escape" || !c.orientedTransformGesture) return false;
        cancel(c);
        stop(event);
        return true;
    }

    function install(c) {
        if (!c || !c.canvas || c.__orientedTransformInstalled) return c;
        c.__orientedTransformInstalled = true;
        c.orientedTransformGesture = null;
        c.orientedTransformPreviewFrame = null;
        c.orientedTransformPreferredAngle = null;
        c.orientedTransformPivot = null;
        c.orientedTransformSelectionKey = "";

        const onPointerDown = event => begin(c, event);
        const onPointerMove = event => move(c, event);
        const onPointerUp = event => end(c, event);
        const onPointerCancel = event => cancel(c, event);
        const onClick = event => action(c, event);
        const onChange = event => change(c, event);
        const onInspectorKey = event => inspectorKey(c, event);
        const onKeyDown = event => keyDown(c, event);
        window.addEventListener("pointerdown", onPointerDown, true);
        window.addEventListener("pointermove", onPointerMove, true);
        window.addEventListener("pointerup", onPointerUp, true);
        window.addEventListener("pointercancel", onPointerCancel, true);
        window.addEventListener("keydown", onKeyDown, true);
        c.root.addEventListener("click", onClick, true);
        c.inspector.addEventListener("change", onChange, true);
        c.inspector.addEventListener("keydown", onInspectorKey, true);
        View.decorate(c);

        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-oriented-transform-cleanup", () => {
            window.removeEventListener("pointerdown", onPointerDown, true);
            window.removeEventListener("pointermove", onPointerMove, true);
            window.removeEventListener("pointerup", onPointerUp, true);
            window.removeEventListener("pointercancel", onPointerCancel, true);
            window.removeEventListener("keydown", onKeyDown, true);
            c.root.removeEventListener("click", onClick, true);
            c.inspector.removeEventListener("change", onChange, true);
            c.inspector.removeEventListener("keydown", onInspectorKey, true);
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
    root.OrientedTransform = Object.freeze({ install, begin, move, end, cancel, applyMatrix, localFlip, resetPivot, property });
})();
