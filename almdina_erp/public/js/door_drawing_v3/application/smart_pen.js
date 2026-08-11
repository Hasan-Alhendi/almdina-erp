(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const V = root.ShapeView;
    const Editor = root.Editor;
    if (!G || !D || !S || !V || !Editor || !G.path) throw new Error("Door Drawing V3 smart path stack must load before smart pen");

    const CLOSE_CAPTURE_PX = 18;
    let sequence = 0;
    function nextId() { sequence += 1; return `path-${Date.now()}-${sequence}`; }

    function selectedPath(c) {
        const object = D.objectById(c.history.current(), c.selectedId);
        return object && object.type === G.PATH_TYPE ? object : null;
    }

    function render(c) { V.render(c); }
    function execute(c, document, label) {
        c.history.execute(document, label);
        c.dirty = true;
        render(c);
    }

    function cancelBaseDrafts(c) {
        c.draftStart = null;
        c.draftObject = null;
        c.arcDraft = null;
        c.clickDraft = null;
        c.precision = null;
        c.snapState = null;
    }

    function cancelPenDraft(c) {
        c.penDraft = null;
        c.snapState = null;
    }

    function leaveNodeEdit(c) {
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.smartNodeGesture = null;
        c.previewObject = null;
    }

    function activatePen(c) {
        if (!c || c.readOnly) return false;
        cancelBaseDrafts(c);
        leaveNodeEdit(c);
        c.tool = "pen";
        c.penDraft = null;
        render(c);
        return true;
    }

    function finishPath(c, closed) {
        const draft = c.penDraft;
        if (!draft || draft.points.length < (closed ? 3 : 2)) return false;
        const object = G.path(nextId(), draft.points, Boolean(closed));
        const document = D.addObject(c.history.current(), object);
        c.selectedId = object.id;
        c.tool = "select";
        c.penDraft = null;
        c.snapState = null;
        c.nodeEditId = object.id;
        c.selectedNodeIndex = null;
        execute(c, document, closed ? "Add closed smart path" : "Add smart path");
        return true;
    }

    function closeToleranceMm(c) { return S.worldTolerance(c.viewport.scale, CLOSE_CAPTURE_PX); }

    function resolvePenCandidate(c, event) {
        const raw = V.eventWorld(c, event);
        const draft = c.penDraft;
        const last = draft && draft.points.length ? draft.points[draft.points.length - 1] : null;
        let candidate = raw;
        let state = null;

        if (last && event.shiftKey) {
            const length = G.distance(last, raw);
            const angle = G.angleDeg(last, raw);
            const snappedAngle = Math.round(angle / 45) * 45;
            candidate = G.pointAt(last, length, snappedAngle);
            state = Object.freeze({ point: candidate, rawPoint: raw, snapped: false, target: null, distanceMm: null, toleranceMm: 0, joinToleranceMm: 0, axis: `angle-${snappedAngle}`, anchor: last, kind: "angle" });
        } else {
            state = S.resolvePoint(c.history.current(), raw, {
                viewportScale: c.viewport.scale,
                stickyTarget: c.snapState && c.snapState.target,
            });
            candidate = state.point;
        }

        let closeReady = false;
        if (draft && draft.points.length >= 3) {
            const first = draft.points[0];
            if (G.distance(candidate, first) <= closeToleranceMm(c)) {
                candidate = first;
                closeReady = true;
                state = Object.freeze({ ...(state || {}), point: first, rawPoint: raw, snapped: true, target: Object.freeze({ objectId: "__draft__", role: "start", point: first, priority: 999, kind: "joint" }), kind: "joint" });
            }
        }
        c.snapState = state;
        return Object.freeze({ point: candidate, closeReady, state });
    }

    function addPenPoint(c, event) {
        const resolved = resolvePenCandidate(c, event);
        if (!c.penDraft) {
            c.penDraft = { points: [resolved.point], pointer: resolved.point, closeReady: false };
            render(c);
            return true;
        }
        if (resolved.closeReady) return finishPath(c, true);
        const points = c.penDraft.points.slice();
        const last = points[points.length - 1];
        if (G.distance(last, resolved.point) < G.EPSILON_MM) return false;
        points.push(resolved.point);
        c.penDraft = { points, pointer: resolved.point, closeReady: false };
        render(c);
        return true;
    }

    function updatePenPointer(c, event) {
        if (c.tool !== "pen" || !c.penDraft || c.spaceHeld) return false;
        const resolved = resolvePenCandidate(c, event);
        c.penDraft = { ...c.penDraft, pointer: resolved.point, closeReady: resolved.closeReady };
        render(c);
        return true;
    }

    function enterNodeEdit(c, objectId, nodeIndex = null) {
        const object = D.objectById(c.history.current(), objectId);
        if (!object || object.type !== G.PATH_TYPE) return false;
        c.tool = "select";
        c.selectedId = object.id;
        c.nodeEditId = object.id;
        c.selectedNodeIndex = Number.isInteger(nodeIndex) ? nodeIndex : null;
        c.penDraft = null;
        c.previewObject = null;
        c.snapState = null;
        render(c);
        return true;
    }

    function insertNodeAtEvent(c, object, segmentIndex, event) {
        const projection = G.nearestPathSegment(object, V.eventWorld(c, event));
        if (!projection || Number(projection.segmentIndex) !== Number(segmentIndex)) return false;
        const next = G.insertPathPoint(object, segmentIndex, projection.point);
        const document = D.replaceObject(c.history.current(), next);
        c.selectedId = next.id;
        c.nodeEditId = next.id;
        c.selectedNodeIndex = Math.min(next.geometry.points.length - 1, Number(segmentIndex) + 1);
        execute(c, document, "Insert path node");
        return true;
    }

    function beginNodeDrag(c, event, nodeElement) {
        const object = selectedPath(c);
        const index = Number(nodeElement.dataset.ddv3PathNode);
        if (!object || String(c.nodeEditId) !== String(object.id) || !Number.isInteger(index) || index < 0 || index >= object.geometry.points.length) return false;
        c.selectedNodeIndex = index;
        c.smartNodeGesture = { pointerId: event.pointerId, object, index };
        c.previewObject = object;
        c.snapState = null;
        try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
        render(c);
        return true;
    }

    function moveNode(c, event) {
        const gesture = c.smartNodeGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        const result = S.resolvePoint(c.history.current(), V.eventWorld(c, event), {
            viewportScale: c.viewport.scale,
            excludeId: gesture.object.id,
            stickyTarget: c.snapState && c.snapState.target,
        });
        c.snapState = result;
        c.previewObject = G.setPathPoint(gesture.object, gesture.index, result.point);
        render(c);
        return true;
    }

    function endNodeDrag(c, event) {
        const gesture = c.smartNodeGesture;
        if (!gesture || gesture.pointerId !== event.pointerId) return false;
        const next = c.previewObject;
        c.smartNodeGesture = null;
        c.previewObject = null;
        c.snapState = null;
        try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
        if (next && JSON.stringify(next.geometry) !== JSON.stringify(gesture.object.geometry)) {
            execute(c, D.replaceObject(c.history.current(), next), "Move path node");
        } else {
            render(c);
        }
        return true;
    }

    function deleteSelectedNode(c) {
        const object = selectedPath(c);
        const index = c.selectedNodeIndex;
        if (!object || String(c.nodeEditId) !== String(object.id) || !Number.isInteger(index)) return false;
        const next = G.removePathPoint(object, index);
        if (next === object) {
            if (window.frappe && frappe.show_alert) frappe.show_alert({ message: "لا يمكن حذف نقطة إضافية من هذا المسار", indicator: "orange" });
            return true;
        }
        const document = D.replaceObject(c.history.current(), next);
        c.selectedNodeIndex = Math.min(index, next.geometry.points.length - 1);
        execute(c, document, "Delete path node");
        return true;
    }

    function toggleClosed(c) {
        const object = selectedPath(c);
        if (!object || c.readOnly) return false;
        if (!object.geometry.closed && object.geometry.points.length < 3) {
            if (window.frappe && frappe.show_alert) frappe.show_alert({ message: "يلزم ثلاث نقاط على الأقل لإغلاق المسار", indicator: "orange" });
            return true;
        }
        const next = G.path(object.id, object.geometry.points, !object.geometry.closed, object.style);
        execute(c, D.replaceObject(c.history.current(), next), object.geometry.closed ? "Open path" : "Close path");
        return true;
    }

    function applyNodeInspector(c, input) {
        const object = selectedPath(c);
        const index = c.selectedNodeIndex;
        if (!object || !Number.isInteger(index) || !input) return false;
        const point = object.geometry.points[index];
        const value = G.number(input.value, input.dataset.ddv3PathNodeProp === "x" ? point.x : point.y);
        const nextPoint = input.dataset.ddv3PathNodeProp === "x" ? G.point(value, point.y) : G.point(point.x, value);
        const next = G.setPathPoint(object, index, nextPoint);
        execute(c, D.replaceObject(c.history.current(), next), "Edit path node");
        return true;
    }

    function install(c) {
        if (!c || !c.canvas || c.__smartPenInstalled) return c;
        c.__smartPenInstalled = true;
        c.penDraft = null;
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.smartNodeGesture = null;

        const penButton = V.ensurePenButton(c);
        if (penButton) penButton.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            activatePen(c);
        }, true);

        const onRootToolCapture = event => {
            const button = event.target.closest && event.target.closest("[data-ddv3-tool]");
            if (!button || button.dataset.ddv3Tool === "pen") return;
            cancelPenDraft(c);
            leaveNodeEdit(c);
        };

        const onPointerDownCapture = event => {
            if (c.readOnly) return;
            const node = event.target.closest && event.target.closest("[data-ddv3-path-node]");
            if (node && c.nodeEditId) {
                if (beginNodeDrag(c, event, node)) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                }
                return;
            }
            if (c.tool !== "pen") return;
            if (c.spaceHeld || event.button === 1) { c.smartPenSuppressClick = true; return; }
            if (event.button !== 0) return;
            event.preventDefault();
            event.stopImmediatePropagation();
        };

        const onPointerMoveCapture = event => {
            if (moveNode(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            if (updatePenPointer(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };

        const onPointerUpCapture = event => {
            if (endNodeDrag(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };

        const onCanvasClickCapture = event => {
            if (c.tool !== "pen" || c.readOnly) return;
            if (c.smartPenSuppressClick) { c.smartPenSuppressClick = false; return; }
            if (event.detail >= 2) {
                finishPath(c, false);
            } else {
                addPenPoint(c, event);
            }
            event.preventDefault();
            event.stopImmediatePropagation();
        };

        const onDoubleClickCapture = event => {
            if (c.readOnly || c.tool === "pen") return;
            const target = event.target.closest && event.target.closest("[data-ddv3-object]");
            if (!target) return;
            const object = D.objectById(c.history.current(), target.dataset.ddv3Object);
            if (!object || object.type !== G.PATH_TYPE) return;
            const segment = event.target.closest && event.target.closest("[data-ddv3-path-segment]");
            if (String(c.nodeEditId) === String(object.id) && segment) {
                insertNodeAtEvent(c, object, Number(segment.dataset.ddv3PathSegment), event);
            } else {
                enterNodeEdit(c, object.id);
            }
            event.preventDefault();
            event.stopImmediatePropagation();
        };

        const onInspectorClick = event => {
            const toggle = event.target.closest && event.target.closest("[data-ddv3-path-toggle]");
            if (!toggle) return;
            if (toggleClosed(c)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onInspectorChange = event => {
            const input = event.target.closest && event.target.closest("[data-ddv3-path-node-prop]");
            if (!input) return;
            if (applyNodeInspector(c, input)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };

        const onKeyDownCapture = event => {
            if (c.readOnly) return;
            const target = event.target;
            const editingText = target && (target.matches && target.matches("input, textarea, select") || target.isContentEditable);
            if (editingText) return;
            if ((event.key === "p" || event.key === "P") && !event.ctrlKey && !event.metaKey && !event.altKey) {
                activatePen(c);
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            if (c.tool === "pen") {
                if (event.key === "Enter" && finishPath(c, false)) {
                    event.preventDefault(); event.stopImmediatePropagation(); return;
                }
                if (event.key === "Backspace" && c.penDraft) {
                    const points = c.penDraft.points.slice(0, -1);
                    c.penDraft = points.length ? { points, pointer: points[points.length - 1], closeReady: false } : null;
                    c.snapState = null;
                    render(c);
                    event.preventDefault(); event.stopImmediatePropagation(); return;
                }
                if (event.key === "Escape") {
                    if (c.penDraft) cancelPenDraft(c); else c.tool = "select";
                    render(c);
                    event.preventDefault(); event.stopImmediatePropagation(); return;
                }
            }
            if ((event.key === "Delete" || event.key === "Backspace") && deleteSelectedNode(c)) {
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if (event.key === "Escape" && c.nodeEditId) {
                leaveNodeEdit(c);
                render(c);
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        c.root.addEventListener("click", onRootToolCapture, true);
        c.canvas.addEventListener("pointerdown", onPointerDownCapture, true);
        c.canvas.addEventListener("pointermove", onPointerMoveCapture, true);
        c.canvas.addEventListener("pointerup", onPointerUpCapture, true);
        c.canvas.addEventListener("click", onCanvasClickCapture, true);
        c.canvas.addEventListener("dblclick", onDoubleClickCapture, true);
        c.inspector.addEventListener("click", onInspectorClick, true);
        c.inspector.addEventListener("change", onInspectorChange, true);
        window.addEventListener("keydown", onKeyDownCapture, true);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-smart-pen-cleanup", () => {
                c.root.removeEventListener("click", onRootToolCapture, true);
                c.canvas.removeEventListener("pointerdown", onPointerDownCapture, true);
                c.canvas.removeEventListener("pointermove", onPointerMoveCapture, true);
                c.canvas.removeEventListener("pointerup", onPointerUpCapture, true);
                c.canvas.removeEventListener("click", onCanvasClickCapture, true);
                c.canvas.removeEventListener("dblclick", onDoubleClickCapture, true);
                c.inspector.removeEventListener("click", onInspectorClick, true);
                c.inspector.removeEventListener("change", onInspectorChange, true);
                window.removeEventListener("keydown", onKeyDownCapture, true);
            });
        }
        render(c);
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.SmartPen = Object.freeze({ activatePen, finishPath, resolvePenCandidate, enterNodeEdit, insertNodeAtEvent, install });
})();
