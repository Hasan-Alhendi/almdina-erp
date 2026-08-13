(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const View = root.BezierPathView;
    const VectorView = root.VectorEditingView;
    const Editor = root.Editor;
    if (!G || !D || !S || !View || !Editor || !G.setPathHandle || !G.splitPathSegment) throw new Error("Door Drawing V3 Bezier editing dependencies must load first");

    const PATH_TOOL = "path";
    const HANDLE_ANGLE_STEP_DEG = 45;
    const DRAG_THRESHOLD_PX = 3;
    const NUDGE_MM = 1;
    const FAST_NUDGE_MM = 10;
    let sequence = 0;

    function nextId() { sequence += 1; return `path-${Date.now()}-${sequence}`; }
    function render(c) {
        root.ShapeView.render(c);
        if (VectorView) VectorView.schedule(c);
        View.schedule(c);
    }
    function execute(c, document, label) {
        c.history.execute(document, label);
        c.dirty = true;
        render(c);
    }
    function pathObject(c, id = c.nodeEditId || c.selectedId) {
        const object = D.objectById(c.history.current(), id);
        return object && object.type === G.PATH_TYPE ? object : null;
    }
    function setPathSelection(c, object, nodeIndices = []) {
        if (!object) return;
        c.selectedId = String(object.id);
        c.selectedIds = [String(object.id)];
        c.nodeEditId = String(object.id);
        const clean = [...new Set((nodeIndices || []).map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < object.geometry.points.length))].sort((a, b) => a - b);
        c.selectedNodeIndices = clean;
        c.selectedNodeIndex = clean.length === 1 ? clean[0] : null;
        c.selectedSegmentIndices = [];
        render(c);
    }
    function toggleNode(c, object, index) {
        const current = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.map(Number) : [];
        const target = Number(index), next = current.includes(target) ? current.filter(item => item !== target) : [...current, target];
        setPathSelection(c, object, next);
    }
    function localCanvasEvent(c, event) { return Boolean(event && event.target && c.canvas && c.canvas.contains(event.target)); }
    function eventWorld(c, event) { return root.ShapeView.eventWorld(c, event); }
    function capture(c, event) { try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function release(c, event) { try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function stop(event) { event.preventDefault(); event.stopPropagation(); if (event.stopImmediatePropagation) event.stopImmediatePropagation(); }
    function editingTarget(event) {
        const element = event.target && event.target.closest ? event.target.closest("input, textarea, select, [contenteditable='true']") : null;
        return Boolean(element);
    }
    function temporaryDocument(c, excludedId) {
        const current = c.history.current();
        return { ...current, objects: (current.objects || []).filter(object => String(object.id) !== String(excludedId || "")) };
    }
    function snapPoint(c, raw, excludedId = "", anchor = null) {
        return S.resolvePoint(temporaryDocument(c, excludedId), raw, {
            viewportScale: c.viewport.scale,
            stickyTarget: c.vectorSnapState && c.vectorSnapState.target,
            anchor,
        });
    }
    function closeTolerance(c) { return Math.max(G.EPSILON_MM * 10, 10 / Math.max(0.05, Number(c.viewport && c.viewport.scale || 1))); }
    function screenDistance(c, first, second) {
        const a = root.ShapeView.worldToScreen(c, first), b = root.ShapeView.worldToScreen(c, second);
        return Math.hypot(a.x - b.x, a.y - b.y);
    }
    function constrainHandle(anchor, target, event) {
        if (!event.shiftKey) return target;
        const dx = target.x - anchor.x, dy = target.y - anchor.y, length = Math.hypot(dx, dy);
        if (length < G.EPSILON_MM) return target;
        const step = HANDLE_ANGLE_STEP_DEG * Math.PI / 180;
        const angle = Math.round(Math.atan2(dy, dx) / step) * step;
        return G.point(anchor.x + Math.cos(angle) * length, anchor.y + Math.sin(angle) * length);
    }

    function selectedNodes(c, object) {
        const values = Array.isArray(c.selectedNodeIndices) && c.selectedNodeIndices.length ? c.selectedNodeIndices : (Number.isInteger(c.selectedNodeIndex) ? [c.selectedNodeIndex] : []);
        return [...new Set(values.map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < object.geometry.points.length))].sort((a, b) => a - b);
    }
    function beginNodeDrag(c, event, object, index) {
        if (event.shiftKey || event.ctrlKey || event.metaKey) { toggleNode(c, object, index); stop(event); return true; }
        let indices = selectedNodes(c, object);
        if (!indices.includes(index)) { indices = [index]; setPathSelection(c, object, indices); }
        c.bezierGesture = {
            type: "nodes",
            pointerId: event.pointerId,
            object,
            indices,
            primaryIndex: index,
            startPrimary: object.geometry.points[index],
        };
        c.previewObject = object;
        c.vectorSnapState = null;
        capture(c, event);
        stop(event);
        return true;
    }
    function moveNodeDrag(c, event) {
        const gesture = c.bezierGesture;
        if (!gesture || gesture.type !== "nodes" || gesture.pointerId !== event.pointerId) return false;
        const raw = eventWorld(c, event), snap = snapPoint(c, raw, gesture.object.id, gesture.startPrimary);
        c.vectorSnapState = snap;
        const dx = G.roundMm(snap.point.x - gesture.startPrimary.x), dy = G.roundMm(snap.point.y - gesture.startPrimary.y);
        c.previewObject = G.movePathNodes(gesture.object, gesture.indices, dx, dy);
        render(c); stop(event); return true;
    }
    function endNodeDrag(c, event) {
        const gesture = c.bezierGesture;
        if (!gesture || gesture.type !== "nodes" || gesture.pointerId !== event.pointerId) return false;
        const next = c.previewObject;
        c.bezierGesture = null; c.previewObject = null; c.vectorSnapState = null; release(c, event);
        if (next && JSON.stringify(next.geometry) !== JSON.stringify(gesture.object.geometry)) {
            execute(c, D.replaceObject(c.history.current(), next), `Move ${gesture.indices.length} path node${gesture.indices.length === 1 ? "" : "s"}`);
        } else render(c);
        stop(event); return true;
    }

    function beginHandleDrag(c, event, object, index, role) {
        c.bezierGesture = { type: "handle", pointerId: event.pointerId, object, index, role };
        c.previewObject = object;
        c.vectorSnapState = null;
        setPathSelection(c, object, [index]);
        capture(c, event);
        stop(event);
        return true;
    }
    function moveHandleDrag(c, event) {
        const gesture = c.bezierGesture;
        if (!gesture || gesture.type !== "handle" || gesture.pointerId !== event.pointerId) return false;
        const anchor = gesture.object.geometry.points[gesture.index], raw = constrainHandle(anchor, eventWorld(c, event), event);
        c.previewObject = G.setPathHandle(gesture.object, gesture.index, gesture.role, raw, { breakTangency: event.altKey });
        render(c); stop(event); return true;
    }
    function endHandleDrag(c, event) {
        const gesture = c.bezierGesture;
        if (!gesture || gesture.type !== "handle" || gesture.pointerId !== event.pointerId) return false;
        const next = c.previewObject;
        c.bezierGesture = null; c.previewObject = null; release(c, event);
        if (next && JSON.stringify(next.geometry) !== JSON.stringify(gesture.object.geometry)) {
            execute(c, D.replaceObject(c.history.current(), next), `Adjust ${gesture.role} Bezier handle`);
        } else render(c);
        stop(event); return true;
    }

    function anchorFromNode(point, node) {
        return { point: G.point(point.x, point.y), type: node && node.type || G.NODE_CORNER, in: node && node.in || null, out: node && node.out || null };
    }
    function newAnchor(point) { return { point: G.point(point.x, point.y), type: G.NODE_CORNER, in: null, out: null }; }
    function reverseAnchor(anchor) { return { point: anchor.point, type: anchor.type, in: anchor.out || null, out: anchor.in || null }; }
    function endpointCandidate(c, point) {
        const tolerance = closeTolerance(c);
        let best = null;
        (c.history.current().objects || []).forEach(object => {
            if (object.type !== G.PATH_TYPE || object.geometry.closed || object.geometry.points.length < 2) return;
            const nodes = G.pathNodes(object), endpoints = [
                { role: "start", index: 0, point: object.geometry.points[0], node: nodes[0], opposite: object.geometry.points[object.geometry.points.length - 1] },
                { role: "end", index: object.geometry.points.length - 1, point: object.geometry.points[object.geometry.points.length - 1], node: nodes[nodes.length - 1], opposite: object.geometry.points[0] },
            ];
            endpoints.forEach(endpoint => {
                const distance = G.distance(point, endpoint.point);
                if (distance <= tolerance && (!best || distance < best.distance)) best = { object, ...endpoint, distance };
            });
        });
        return best;
    }
    function beginPenDraft(c, point) {
        const endpoint = endpointCandidate(c, point);
        if (endpoint) {
            c.bezierPathDraft = {
                anchors: [anchorFromNode(endpoint.point, endpoint.node)],
                hover: endpoint.point,
                closeReady: false,
                baseObject: endpoint.object,
                extendAt: endpoint.role,
                oppositeEndpoint: endpoint.opposite,
            };
            setPathSelection(c, endpoint.object, [endpoint.index]);
            return;
        }
        c.bezierPathDraft = { anchors: [newAnchor(point)], hover: point, closeReady: false, baseObject: null, extendAt: null, oppositeEndpoint: null };
    }
    function nodesFromAnchors(anchors) { return anchors.map(anchor => ({ type: anchor.type, in: anchor.in, out: anchor.out })); }
    function buildExtendedPath(draft, closed) {
        const base = draft.baseObject, oldPoints = base.geometry.points.slice(), oldNodes = G.pathNodes(base).map(node => ({ ...node }));
        const additions = draft.anchors.slice(1);
        if (draft.extendAt === "end") {
            const first = draft.anchors[0];
            oldNodes[oldNodes.length - 1] = { ...oldNodes[oldNodes.length - 1], type: first.type, in: first.in, out: first.out };
            return G.path(base.id, [...oldPoints, ...additions.map(anchor => anchor.point)], closed, base.style, [...oldNodes, ...nodesFromAnchors(additions)]);
        }
        const reversed = additions.slice().reverse().map(reverseAnchor);
        const first = draft.anchors[0];
        oldNodes[0] = { ...oldNodes[0], type: first.type, in: first.out || oldNodes[0].in, out: oldNodes[0].out };
        return G.path(base.id, [...reversed.map(anchor => anchor.point), ...oldPoints], closed, base.style, [...nodesFromAnchors(reversed), ...oldNodes]);
    }
    function commitPenDraft(c, closed = false) {
        const draft = c.bezierPathDraft;
        if (!draft) return false;
        const minimum = closed ? 3 : 2;
        const additionCount = draft.baseObject ? draft.anchors.length - 1 : draft.anchors.length;
        if ((!draft.baseObject && draft.anchors.length < minimum) || (draft.baseObject && additionCount < 1 && !closed)) return false;
        let document = c.history.current(), object;
        if (draft.baseObject) {
            object = buildExtendedPath(draft, closed);
            document = D.replaceObject(document, object);
        } else {
            object = G.path(nextId(), draft.anchors.map(anchor => anchor.point), closed, {}, nodesFromAnchors(draft.anchors));
            document = D.addObject(document, object);
        }
        c.bezierPathDraft = null; c.vectorPathDraft = null; c.vectorSnapState = null;
        execute(c, document, closed ? "Close Bezier path" : "Create Bezier path");
        setPathSelection(c, object, [Math.max(0, object.geometry.points.length - 1)]);
        return true;
    }
    function cancelPenDraft(c) {
        c.bezierPathDraft = null; c.vectorPathDraft = null; c.bezierPenGesture = null; c.vectorSnapState = null;
        render(c);
    }
    function penPointerDown(c, event) {
        if (c.tool !== PATH_TOOL || !localCanvasEvent(c, event) || c.readOnly || c.spaceHeld || event.button !== 0) return false;
        const raw = eventWorld(c, event), draft = c.bezierPathDraft, excluded = draft && draft.baseObject ? draft.baseObject.id : "";
        const snap = snapPoint(c, raw, excluded), point = snap.point; c.vectorSnapState = snap;
        if (draft) {
            const tolerance = closeTolerance(c);
            if (!draft.baseObject && draft.anchors.length >= 3 && G.distance(point, draft.anchors[0].point) <= tolerance) {
                commitPenDraft(c, true); stop(event); return true;
            }
            if (draft.baseObject && draft.anchors.length >= 2 && draft.oppositeEndpoint && G.distance(point, draft.oppositeEndpoint) <= tolerance) {
                commitPenDraft(c, true); stop(event); return true;
            }
        }
        if (!c.bezierPathDraft) beginPenDraft(c, point);
        else c.bezierPathDraft.anchors.push(newAnchor(point));
        const activeDraft = c.bezierPathDraft, index = activeDraft.anchors.length - 1;
        c.bezierPenGesture = { pointerId: event.pointerId, index, start: activeDraft.anchors[index].point, dragged: false };
        activeDraft.hover = activeDraft.anchors[index].point; activeDraft.closeReady = false;
        capture(c, event); render(c); stop(event); return true;
    }
    function penPointerMove(c, event) {
        if (c.tool !== PATH_TOOL || !localCanvasEvent(c, event)) return false;
        const draft = c.bezierPathDraft;
        if (!draft) return false;
        const raw = eventWorld(c, event), excluded = draft.baseObject ? draft.baseObject.id : "", snap = snapPoint(c, raw, excluded);
        c.vectorSnapState = snap;
        const gesture = c.bezierPenGesture;
        if (gesture && gesture.pointerId === event.pointerId) {
            const anchor = draft.anchors[gesture.index], constrained = constrainHandle(anchor.point, raw, event);
            if (screenDistance(c, anchor.point, constrained) >= DRAG_THRESHOLD_PX) {
                const out = { x: G.roundMm(constrained.x - anchor.point.x), y: G.roundMm(constrained.y - anchor.point.y) };
                anchor.type = event.altKey ? G.NODE_CORNER : G.NODE_SYMMETRIC;
                anchor.out = out;
                anchor.in = { x: G.roundMm(-out.x), y: G.roundMm(-out.y) };
                gesture.dragged = true;
            }
            draft.hover = anchor.point;
        } else {
            draft.hover = snap.point;
            const tolerance = closeTolerance(c);
            draft.closeReady = Boolean(
                (!draft.baseObject && draft.anchors.length >= 3 && G.distance(snap.point, draft.anchors[0].point) <= tolerance) ||
                (draft.baseObject && draft.anchors.length >= 2 && draft.oppositeEndpoint && G.distance(snap.point, draft.oppositeEndpoint) <= tolerance)
            );
        }
        render(c); stop(event); return true;
    }
    function penPointerUp(c, event) {
        const gesture = c.bezierPenGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        c.bezierPenGesture = null; release(c, event);
        const draft = c.bezierPathDraft; if (draft) draft.hover = draft.anchors[draft.anchors.length - 1].point;
        render(c); stop(event); return true;
    }

    function splitSegment(c, event) {
        if (c.readOnly || c.tool !== "select") return false;
        const element = event.target && event.target.closest ? event.target.closest("[data-ddv3-path-segment]") : null;
        if (!element || !c.canvas.contains(element)) return false;
        const object = pathObject(c, element.dataset.ddv3Object), segmentIndex = Number(element.dataset.ddv3PathSegment);
        if (!object || !Number.isInteger(segmentIndex) || String(c.nodeEditId || "") !== String(object.id)) return false;
        const nearest = G.nearestPathSegment(object, eventWorld(c, event));
        if (!nearest || nearest.segmentIndex !== segmentIndex) return false;
        const next = G.splitPathSegment(object, segmentIndex, nearest.t);
        const insertIndex = segmentIndex === object.geometry.points.length - 1 && object.geometry.closed ? next.geometry.points.length - 1 : segmentIndex + 1;
        execute(c, D.replaceObject(c.history.current(), next), "Insert Bezier path node");
        setPathSelection(c, next, [insertIndex]);
        stop(event); return true;
    }

    function setNodeTypes(c, type) {
        const object = pathObject(c), indices = object ? selectedNodes(c, object) : [];
        if (!object || !indices.length) return false;
        let next = object; indices.forEach(index => { next = G.setPathNodeType(next, index, type); });
        execute(c, D.replaceObject(c.history.current(), next), `Set ${indices.length} node${indices.length === 1 ? "" : "s"} ${type}`);
        setPathSelection(c, next, indices); return true;
    }
    function setSegmentTypes(c, mode) {
        const object = pathObject(c), indices = object && Array.isArray(c.selectedSegmentIndices) ? [...new Set(c.selectedSegmentIndices.map(Number).filter(Number.isInteger))] : [];
        if (!object || !indices.length) return false;
        let next = object; indices.forEach(index => { next = G.convertPathSegment(next, index, mode); });
        execute(c, D.replaceObject(c.history.current(), next), `Convert ${indices.length} segment${indices.length === 1 ? "" : "s"} to ${mode}`);
        c.selectedSegmentIndices = indices; c.selectedNodeIndices = []; c.selectedNodeIndex = null; render(c); return true;
    }
    function contextAction(c, event) {
        const button = event.target && event.target.closest ? event.target.closest("[data-ddv3-bezier-action]") : null;
        if (!button || !c.root.contains(button)) return false;
        const action = button.dataset.ddv3BezierAction;
        const handled = action === "node-type" ? setNodeTypes(c, button.dataset.ddv3NodeType) : action === "segment-type" ? setSegmentTypes(c, button.dataset.ddv3SegmentType) : false;
        if (handled) stop(event);
        return handled;
    }

    function deleteNodes(c, object, indices) {
        let next = object;
        [...indices].sort((a, b) => b - a).forEach(index => { next = G.removePathPoint(next, index); });
        if (JSON.stringify(next.geometry) === JSON.stringify(object.geometry)) return false;
        execute(c, D.replaceObject(c.history.current(), next), `Delete ${indices.length} path node${indices.length === 1 ? "" : "s"}`);
        const fallback = Math.min(indices[0] || 0, next.geometry.points.length - 1);
        setPathSelection(c, next, fallback >= 0 ? [fallback] : []);
        return true;
    }
    function nudgeNodes(c, object, indices, dx, dy) {
        const next = G.movePathNodes(object, indices, dx, dy);
        execute(c, D.replaceObject(c.history.current(), next), `Nudge ${indices.length} path node${indices.length === 1 ? "" : "s"}`);
        setPathSelection(c, next, indices); return true;
    }
    function keyDown(c, event) {
        if (c.readOnly || editingTarget(event)) return false;
        if (c.tool === PATH_TOOL && c.bezierPathDraft) {
            if (event.key === "Enter") { commitPenDraft(c, false); stop(event); return true; }
            if (event.key === "Escape") { cancelPenDraft(c); stop(event); return true; }
            if (event.key === "Backspace" || event.key === "Delete") {
                const draft = c.bezierPathDraft;
                if (draft.anchors.length > 1) draft.anchors.pop(); else cancelPenDraft(c);
                render(c); stop(event); return true;
            }
        }
        const object = pathObject(c), indices = object ? selectedNodes(c, object) : [];
        if (!object || !indices.length || String(c.nodeEditId || "") !== String(object.id)) return false;
        if (event.key === "Backspace" || event.key === "Delete") { if (deleteNodes(c, object, indices)) { stop(event); return true; } return false; }
        const amount = event.shiftKey ? FAST_NUDGE_MM : NUDGE_MM;
        let dx = 0, dy = 0;
        if (event.key === "ArrowLeft") dx = -amount;
        else if (event.key === "ArrowRight") dx = amount;
        else if (event.key === "ArrowUp") dy = amount;
        else if (event.key === "ArrowDown") dy = -amount;
        else return false;
        nudgeNodes(c, object, indices, dx, dy); stop(event); return true;
    }

    function pointerDown(c, event) {
        if (penPointerDown(c, event)) return true;
        if (!localCanvasEvent(c, event) || c.readOnly || c.spaceHeld || event.button !== 0 || c.tool !== "select") return false;
        const handle = event.target && event.target.closest ? event.target.closest("[data-ddv3-path-handle]") : null;
        if (handle) {
            const object = pathObject(c, handle.dataset.ddv3Object), index = Number(handle.dataset.ddv3PathNode), role = handle.dataset.ddv3PathHandle;
            if (object && Number.isInteger(index) && ["in", "out"].includes(role)) return beginHandleDrag(c, event, object, index, role);
        }
        const node = event.target && event.target.closest ? event.target.closest("[data-ddv3-path-node]") : null;
        if (node && String(c.nodeEditId || "") === String(node.dataset.ddv3Object || "")) {
            const object = pathObject(c, node.dataset.ddv3Object), index = Number(node.dataset.ddv3PathNode);
            if (object && Number.isInteger(index)) return beginNodeDrag(c, event, object, index);
        }
        return false;
    }
    function pointerMove(c, event) {
        if (moveHandleDrag(c, event) || moveNodeDrag(c, event)) return true;
        if (c.tool === PATH_TOOL && c.bezierPathDraft) return penPointerMove(c, event);
        return false;
    }
    function pointerUp(c, event) {
        if (endHandleDrag(c, event) || endNodeDrag(c, event) || penPointerUp(c, event)) return true;
        return false;
    }
    function doubleClick(c, event) {
        if (c.tool === PATH_TOOL && c.bezierPathDraft) {
            const draft = c.bezierPathDraft;
            if (draft.anchors.length >= 2) {
                const last = draft.anchors[draft.anchors.length - 1], previous = draft.anchors[draft.anchors.length - 2];
                if (G.distance(last.point, previous.point) <= closeTolerance(c)) draft.anchors.pop();
            }
            if (commitPenDraft(c, false)) { stop(event); return true; }
        }
        return splitSegment(c, event);
    }

    function pointerCancel(c, event) {
        const gesture = c.bezierGesture;
        if (gesture && gesture.pointerId === event.pointerId) {
            c.bezierGesture = null; c.previewObject = null; c.vectorSnapState = null; release(c, event); render(c); stop(event); return true;
        }
        if (c.bezierPenGesture && c.bezierPenGesture.pointerId === event.pointerId) {
            c.bezierPenGesture = null; release(c, event); render(c); stop(event); return true;
        }
        return false;
    }

    function install(c) {
        if (!c || !c.root || !c.canvas || c.__bezierEditingInstalled) return c;
        c.__bezierEditingInstalled = true;
        c.bezierGesture = null; c.bezierPenGesture = null; c.bezierPathDraft = null;
        const onPointerDown = event => pointerDown(c, event);
        const onPointerMove = event => pointerMove(c, event);
        const onPointerUp = event => pointerUp(c, event);
        const onPointerCancel = event => pointerCancel(c, event);
        const onClick = event => contextAction(c, event);
        const onDoubleClick = event => doubleClick(c, event);
        const onKeyDown = event => keyDown(c, event);

        // This module intentionally installs before vector_editing.js. Window capture gives
        // Bezier node/handle gestures first right of refusal while leaving all other gestures untouched.
        window.addEventListener("pointerdown", onPointerDown, true);
        window.addEventListener("pointermove", onPointerMove, true);
        window.addEventListener("pointerup", onPointerUp, true);
        window.addEventListener("pointercancel", onPointerCancel, true);
        window.addEventListener("keydown", onKeyDown, true);
        c.root.addEventListener("click", onClick, true);
        c.root.addEventListener("dblclick", onDoubleClick, true);
        View.schedule(c);

        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-bezier-editing-cleanup", () => {
            window.removeEventListener("pointerdown", onPointerDown, true);
            window.removeEventListener("pointermove", onPointerMove, true);
            window.removeEventListener("pointerup", onPointerUp, true);
            window.removeEventListener("pointercancel", onPointerCancel, true);
            window.removeEventListener("keydown", onKeyDown, true);
            c.root.removeEventListener("click", onClick, true);
            c.root.removeEventListener("dblclick", onDoubleClick, true);
        });
        return c;
    }

    const originalOpen = Editor.open.bind(Editor), originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        ...Editor,
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.BezierPathEditing = Object.freeze({ install, setNodeTypes, setSegmentTypes, commitPenDraft, cancelPenDraft });
})();
