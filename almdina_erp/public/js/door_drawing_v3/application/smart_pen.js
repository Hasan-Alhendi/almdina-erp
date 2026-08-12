(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const V = root.ShapeView;
    const F = root.SmartFreehandPolicy;
    const I = root.SmartStrokeIntelligence;
    const Editor = root.Editor;
    if (!G || !D || !S || !V || !F || !I || !Editor || !G.path) throw new Error("Door Drawing V3 intelligent freehand stack must load before smart pen");

    const CLOSE_CAPTURE_PX = 18;
    const INPUT_PROFILES = Object.freeze({
        mouse: Object.freeze({
            sampleSpacingPx: 2.6,
            simplifyTolerancePx: 2.5,
            straightTolerancePx: 4.2,
            smoothingPasses: 3,
            pathSmoothingPasses: 1,
            straightRatio: 1.06,
            circleResidualRatio: 0.055,
            arcResidualRatio: 0.05,
            collinearAngleToleranceDeg: 9,
            orthogonalAngleToleranceDeg: 10,
            stabilizerMotionPx: 16,
            minimumMixedSegmentPx: 18,
        }),
        pen: Object.freeze({
            sampleSpacingPx: 1.45,
            simplifyTolerancePx: 1.55,
            straightTolerancePx: 2.8,
            smoothingPasses: 2,
            pathSmoothingPasses: 1,
            straightRatio: 1.045,
            circleResidualRatio: 0.042,
            arcResidualRatio: 0.038,
            collinearAngleToleranceDeg: 7,
            orthogonalAngleToleranceDeg: 8,
            stabilizerMotionPx: 11,
            minimumMixedSegmentPx: 14,
        }),
        touch: Object.freeze({
            sampleSpacingPx: 3.2,
            simplifyTolerancePx: 3,
            straightTolerancePx: 5,
            smoothingPasses: 3,
            pathSmoothingPasses: 2,
            straightRatio: 1.075,
            circleResidualRatio: 0.065,
            arcResidualRatio: 0.055,
            collinearAngleToleranceDeg: 10,
            orthogonalAngleToleranceDeg: 11,
            stabilizerMotionPx: 18,
            minimumMixedSegmentPx: 22,
        }),
    });
    let sequence = 0;
    function nextId(type = "path") { sequence += 1; return `${type}-${Date.now()}-${sequence}`; }

    function inputProfile(pointerType) {
        const key = String(pointerType || "mouse").toLowerCase();
        return INPUT_PROFILES[key] || INPUT_PROFILES.mouse;
    }

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

    function clearFreehand(c) {
        c.penStroke = null;
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
        clearFreehand(c);
        c.tool = "pen";
        render(c);
        return true;
    }

    function pxToMm(c, px) {
        return S.worldTolerance(c.viewport.scale, px);
    }

    function resolveEndpoint(c, raw, stickyTarget = null) {
        return S.resolvePoint(c.history.current(), raw, {
            viewportScale: c.viewport.scale,
            stickyTarget,
        });
    }

    function closeToleranceMm(c) { return pxToMm(c, CLOSE_CAPTURE_PX); }

    function closeCandidate(c, point) {
        const stroke = c.penStroke;
        if (!stroke || stroke.rawPoints.length < 5) return false;
        const travelled = F.polylineLength(stroke.rawPoints);
        return travelled > closeToleranceMm(c) * 2.5 && G.distance(stroke.startPoint, point) <= closeToleranceMm(c);
    }

    function updateDraft(c, pointer, closeReady = false) {
        const stroke = c.penStroke;
        if (!stroke) return;
        const source = stroke.stablePoints && stroke.stablePoints.length ? stroke.stablePoints : stroke.rawPoints;
        const previewPoints = source.slice();
        if (pointer && (!previewPoints.length || G.distance(previewPoints[previewPoints.length - 1], pointer) >= G.EPSILON_MM)) previewPoints.push(pointer);
        c.penDraft = {
            points: previewPoints,
            pointer: pointer || previewPoints[previewPoints.length - 1] || stroke.startPoint,
            closeReady: Boolean(closeReady),
            freehand: true,
            stabilized: true,
            inputKind: stroke.pointerType,
        };
    }

    function beginFreehand(c, event) {
        if (c.tool !== "pen" || c.readOnly || c.spaceHeld || event.button !== 0) return false;
        const raw = V.eventWorld(c, event);
        const snap = resolveEndpoint(c, raw, c.snapState && c.snapState.target);
        const start = snap.point;
        const pointerType = String(event.pointerType || "mouse").toLowerCase();
        c.penStroke = {
            pointerId: event.pointerId,
            pointerType,
            profile: inputProfile(pointerType),
            stabilizer: I.createStabilizer(pointerType, start),
            rawPoints: [start],
            stablePoints: [start],
            startPoint: start,
            startTarget: snap.target || null,
            lastPoint: start,
            lastStablePoint: start,
        };
        c.snapState = snap;
        updateDraft(c, start, false);
        try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* pointer capture is optional */ }
        render(c);
        return true;
    }

    function appendEventSamples(c, event) {
        const stroke = c.penStroke;
        if (!stroke || stroke.pointerId !== event.pointerId) return null;
        const events = typeof event.getCoalescedEvents === "function" ? event.getCoalescedEvents() : [event];
        const profile = stroke.profile || inputProfile(stroke.pointerType);
        const minSampleMm = Math.max(G.EPSILON_MM, pxToMm(c, profile.sampleSpacingPx));
        const motionScaleMm = Math.max(G.EPSILON_MM, pxToMm(c, profile.stabilizerMotionPx));
        for (const sampleEvent of events.length ? events : [event]) {
            const point = V.eventWorld(c, sampleEvent);
            const before = stroke.rawPoints.length;
            stroke.rawPoints = F.appendSample(stroke.rawPoints, point, minSampleMm);
            if (stroke.rawPoints.length > before) {
                const stabilized = I.pushStabilized(stroke.stabilizer, point, { motionScaleMm });
                stroke.stablePoints = F.appendSample(stroke.stablePoints, stabilized, Math.max(G.EPSILON_MM, minSampleMm * 0.45));
                stroke.lastStablePoint = stabilized;
            }
            stroke.lastPoint = point;
        }
        return stroke.lastPoint || V.eventWorld(c, event);
    }

    function moveFreehand(c, event) {
        const stroke = c.penStroke;
        if (!stroke || stroke.pointerId !== event.pointerId) return false;
        const raw = appendEventSamples(c, event);
        const stable = stroke.lastStablePoint || raw;
        const snap = resolveEndpoint(c, raw, c.snapState && c.snapState.target);
        const shouldClose = closeCandidate(c, raw);
        const previewPoint = shouldClose ? stroke.startPoint : (snap.snapped ? snap.point : stable);
        c.snapState = shouldClose
            ? Object.freeze({ ...snap, point: stroke.startPoint, snapped: true, target: Object.freeze({ objectId: "__stroke__", role: "start", point: stroke.startPoint, priority: 1000, kind: "joint" }), kind: "joint" })
            : snap;
        updateDraft(c, previewPoint, shouldClose);
        render(c);
        return true;
    }

    function objectFromDescriptor(result) {
        if (!result || result.type === "none") return null;
        if (result.type === "line") return G.line(nextId("line"), result.start, result.end);
        if (result.type === "rectangle") return G.rectangle(nextId("rectangle"), result.origin, result.widthMm, result.heightMm);
        if (result.type === "circle") return G.circle(nextId("circle"), result.center, result.radiusMm);
        if (result.type === "arc") return G.arc(nextId("arc"), result.center, result.radiusMm, result.startAngleDeg, result.sweepAngleDeg);
        if (result.type === "path") return G.path(nextId("path"), result.points, Boolean(result.closed));
        return null;
    }

    function objectsFromRecognition(result) {
        if (!result) return [];
        if (result.type === "compound") {
            return (result.segments || []).map(objectFromDescriptor).filter(Boolean);
        }
        const object = objectFromDescriptor(result);
        return object ? [object] : [];
    }

    function finishFreehand(c, event) {
        const stroke = c.penStroke;
        if (!stroke || stroke.pointerId !== event.pointerId) return false;
        const rawEnd = appendEventSamples(c, event) || stroke.lastPoint || stroke.startPoint;
        const endSnap = resolveEndpoint(c, rawEnd, c.snapState && c.snapState.target);
        const closed = closeCandidate(c, rawEnd);
        let points = stroke.rawPoints.slice();
        if (points.length < 2) {
            clearFreehand(c);
            render(c);
            return true;
        }
        points[0] = stroke.startPoint;
        points[points.length - 1] = closed ? stroke.startPoint : endSnap.point;
        points = F.dedupe(points);
        if (points.length < 2) {
            clearFreehand(c);
            render(c);
            return true;
        }

        const profile = stroke.profile || inputProfile(stroke.pointerType);
        const recognitionOptions = {
            closed,
            simplifyToleranceMm: Math.max(G.EPSILON_MM, pxToMm(c, profile.simplifyTolerancePx)),
            straightToleranceMm: Math.max(G.EPSILON_MM, pxToMm(c, profile.straightTolerancePx)),
            smoothingPasses: profile.smoothingPasses,
            pathSmoothingPasses: profile.pathSmoothingPasses,
            straightRatio: profile.straightRatio,
            circleResidualRatio: profile.circleResidualRatio,
            arcResidualRatio: profile.arcResidualRatio,
            collinearAngleToleranceDeg: profile.collinearAngleToleranceDeg,
            orthogonalAngleToleranceDeg: profile.orthogonalAngleToleranceDeg,
            minimumSegmentMm: Math.max(G.EPSILON_MM, pxToMm(c, profile.minimumMixedSegmentPx)),
            preserveEndpoints: true,
            orthogonalize: true,
            inputKind: stroke.pointerType,
        };
        const result = I.interpret(points, recognitionOptions);
        let objects = [];
        try { objects = objectsFromRecognition(result); } catch (error) { objects = []; }
        clearFreehand(c);
        try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
        if (!objects.length) {
            render(c);
            return true;
        }
        let document = c.history.current();
        for (const object of objects) document = D.addObject(document, object);
        c.selectedId = objects[0].id;
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.tool = "pen";
        execute(c, document, objects.length > 1 ? `Smart mixed stroke (${objects.length})` : `Smart freehand ${objects[0].type}`);
        return true;
    }

    function cancelFreehandGesture(c, pointerId = null) {
        if (!c.penStroke || (pointerId != null && c.penStroke.pointerId !== pointerId)) return false;
        const activeId = c.penStroke.pointerId;
        clearFreehand(c);
        try { c.canvas.releasePointerCapture(activeId); } catch (error) { /* optional */ }
        render(c);
        return true;
    }

    function hoverSnap(c, event) {
        if (c.tool !== "pen" || c.penStroke || c.spaceHeld) return false;
        c.snapState = resolveEndpoint(c, V.eventWorld(c, event), c.snapState && c.snapState.target);
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
        clearFreehand(c);
        c.previewObject = null;
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
        if (next && JSON.stringify(next.geometry) !== JSON.stringify(gesture.object.geometry)) execute(c, D.replaceObject(c.history.current(), next), "Move path node");
        else render(c);
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
        c.selectedNodeIndex = Math.min(index, next.geometry.points.length - 1);
        execute(c, D.replaceObject(c.history.current(), next), "Delete path node");
        return true;
    }

    function toggleClosed(c) {
        const object = selectedPath(c);
        if (!object || c.readOnly) return false;
        if (!object.geometry.closed && object.geometry.points.length < 3) return true;
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
        execute(c, D.replaceObject(c.history.current(), G.setPathPoint(object, index, nextPoint)), "Edit path node");
        return true;
    }

    function install(c) {
        if (!c || !c.canvas || c.__smartPenInstalled) return c;
        c.__smartPenInstalled = true;
        c.penStroke = null;
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
            clearFreehand(c);
            leaveNodeEdit(c);
        };

        const onPointerDownCapture = event => {
            if (c.readOnly) return;
            const node = event.target.closest && event.target.closest("[data-ddv3-path-node]");
            if (node && c.nodeEditId && beginNodeDrag(c, event, node)) {
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if (beginFreehand(c, event)) {
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        const onPointerMoveCapture = event => {
            if (moveNode(c, event) || moveFreehand(c, event) || hoverSnap(c, event)) {
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        const onPointerUpCapture = event => {
            if (endNodeDrag(c, event) || finishFreehand(c, event)) {
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        const onPointerCancelCapture = event => {
            if (cancelFreehandGesture(c, event.pointerId)) {
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        const onCanvasClickCapture = event => {
            if (c.tool !== "pen" || c.readOnly) return;
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
            if (String(c.nodeEditId) === String(object.id) && segment) insertNodeAtEvent(c, object, Number(segment.dataset.ddv3PathSegment), event);
            else enterNodeEdit(c, object.id);
            event.preventDefault();
            event.stopImmediatePropagation();
        };

        const onInspectorClick = event => {
            const toggle = event.target.closest && event.target.closest("[data-ddv3-path-toggle]");
            if (toggle && toggleClosed(c)) {
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };
        const onInspectorChange = event => {
            const input = event.target.closest && event.target.closest("[data-ddv3-path-node-prop]");
            if (input && applyNodeInspector(c, input)) {
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        const onKeyDownCapture = event => {
            if (c.readOnly) return;
            const target = event.target;
            const editingText = target && ((target.matches && target.matches("input, textarea, select")) || target.isContentEditable);
            if (editingText) return;
            if ((event.key === "p" || event.key === "P") && !event.ctrlKey && !event.metaKey && !event.altKey) {
                activatePen(c);
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if (event.key === "Escape" && c.penStroke) {
                cancelFreehandGesture(c);
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if (event.key === "Escape" && c.tool === "pen") {
                clearFreehand(c); c.tool = "select"; render(c);
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if ((event.key === "Delete" || event.key === "Backspace") && deleteSelectedNode(c)) {
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if (event.key === "Escape" && c.nodeEditId) {
                leaveNodeEdit(c); render(c);
                event.preventDefault(); event.stopImmediatePropagation();
            }
        };

        c.root.addEventListener("click", onRootToolCapture, true);
        c.canvas.addEventListener("pointerdown", onPointerDownCapture, true);
        c.canvas.addEventListener("pointermove", onPointerMoveCapture, true);
        c.canvas.addEventListener("pointerup", onPointerUpCapture, true);
        c.canvas.addEventListener("pointercancel", onPointerCancelCapture, true);
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
                c.canvas.removeEventListener("pointercancel", onPointerCancelCapture, true);
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
    root.SmartPen = Object.freeze({ INPUT_PROFILES, inputProfile, activatePen, beginFreehand, moveFreehand, finishFreehand, cancelFreehandGesture, enterNodeEdit, insertNodeAtEvent, objectsFromRecognition, install });
})();
