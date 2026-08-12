(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const Selection = root.VectorSelectionGeometry;
    const View = root.VectorEditingView;
    const Editor = root.Editor;
    if (!G || !D || !S || !Selection || !View || !Editor || !G.path) throw new Error("Door Drawing V3 vector editing dependencies must load first");

    const PATH_TOOL = "path";
    const NUDGE_MM = 1;
    const FAST_NUDGE_MM = 10;
    let sequence = 0;

    function nextId(prefix = "path") { sequence += 1; return `${prefix}-${Date.now()}-${sequence}`; }
    function render(c) { root.ShapeView.render(c); View.schedule(c); }
    function execute(c, document, label) { c.history.execute(document, label); c.dirty = true; render(c); }
    function unique(values) { return [...new Set((values || []).filter(value => value !== null && value !== undefined && String(value)).map(String))]; }
    function supportedObject(c, id) { const object = D.objectById(c.history.current(), id); return object && Selection.boundsOfObject(object) ? object : null; }
    function selectedIds(c) {
        if (!Array.isArray(c.selectedIds)) c.selectedIds = c.selectedId ? [String(c.selectedId)] : [];
        const existing = unique(c.selectedIds).filter(id => supportedObject(c, id));
        c.selectedIds = existing;
        if (c.selectedId && !existing.includes(String(c.selectedId))) c.selectedId = existing[existing.length - 1] || "";
        return existing;
    }
    function selectedObjects(c) { return selectedIds(c).map(id => supportedObject(c, id)).filter(Boolean); }
    function setObjectSelection(c, ids, primary = null, options = {}) {
        const clean = unique(ids).filter(id => supportedObject(c, id));
        c.selectedIds = clean;
        const preferred = primary && clean.includes(String(primary)) ? String(primary) : (clean[clean.length - 1] || "");
        c.selectedId = preferred;
        c.previewObject = null;
        c.vectorActiveTranslation = null;
        if (!options.keepPathSubselection || clean.length !== 1 || String(c.nodeEditId || "") !== preferred) {
            c.selectedNodeIndices = [];
            c.selectedSegmentIndices = [];
            if (clean.length !== 1) { c.nodeEditId = ""; c.selectedNodeIndex = null; }
        }
        View.schedule(c);
    }
    function syncFromLegacySelection(c) {
        const id = c.selectedId && supportedObject(c, c.selectedId) ? String(c.selectedId) : "";
        if (!id) setObjectSelection(c, []);
        else setObjectSelection(c, [id], id, { keepPathSubselection: true });
        if (Number.isInteger(c.selectedNodeIndex)) c.selectedNodeIndices = [Number(c.selectedNodeIndex)];
        View.schedule(c);
    }
    function deferLegacySync(c) { const run = () => syncFromLegacySelection(c); if (typeof queueMicrotask === "function") queueMicrotask(run); else Promise.resolve().then(run); }
    function hasModifier(event) { return Boolean(event.shiftKey || event.ctrlKey || event.metaKey); }
    function localCanvasEvent(c, event) { return Boolean(event && event.target && c.canvas && c.canvas.contains(event.target)); }
    function targetObjectElement(event) { return event.target && event.target.closest ? event.target.closest("[data-ddv3-object]") : null; }
    function targetNodeElement(event) { return event.target && event.target.closest ? event.target.closest("[data-ddv3-path-node]") : null; }
    function targetSegmentElement(event) { return event.target && event.target.closest ? event.target.closest("[data-ddv3-path-segment]") : null; }
    function targetHandleElement(event) { return event.target && event.target.closest ? event.target.closest("[data-ddv3-handle]") : null; }
    function pointerCapture(c, event) { try { c.canvas.setPointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function pointerRelease(c, event) { try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ } }
    function temporarySnapDocument(c, excludedIds) {
        const excluded = new Set((excludedIds || []).map(String));
        const current = c.history.current();
        return { ...current, objects: (current.objects || []).filter(object => !excluded.has(String(object.id))) };
    }
    function snapPoint(c, raw, excludedIds = [], anchor = null) {
        return S.resolvePoint(temporarySnapDocument(c, excludedIds), raw, { viewportScale: c.viewport.scale, stickyTarget: c.vectorSnapState && c.vectorSnapState.target, anchor });
    }
    function objectToggle(c, id) {
        const ids = selectedIds(c), target = String(id);
        if (ids.includes(target)) setObjectSelection(c, ids.filter(item => item !== target));
        else setObjectSelection(c, [...ids, target], target);
    }
    function beginGroupMove(c, event) {
        const objects = selectedObjects(c);
        if (objects.length < 2) return false;
        const box = Selection.unionBounds(objects);
        if (!box) return false;
        c.vectorGesture = { type: "group-move", pointerId: event.pointerId, startWorld: root.ShapeView.eventWorld(c, event), anchor: G.point(box.left, box.top), objects, ids: objects.map(object => String(object.id)) };
        c.vectorActiveTranslation = { ids: c.vectorGesture.ids, dx: 0, dy: 0 };
        c.vectorSnapState = null;
        pointerCapture(c, event); View.schedule(c); return true;
    }
    function moveGroup(c, event) {
        const gesture = c.vectorGesture;
        if (!gesture || gesture.type !== "group-move" || gesture.pointerId !== event.pointerId) return false;
        const current = root.ShapeView.eventWorld(c, event);
        const desiredAnchor = G.point(gesture.anchor.x + current.x - gesture.startWorld.x, gesture.anchor.y + current.y - gesture.startWorld.y);
        const snap = snapPoint(c, desiredAnchor, gesture.ids); c.vectorSnapState = snap;
        c.vectorActiveTranslation = { ids: gesture.ids, dx: G.roundMm(snap.point.x - gesture.anchor.x), dy: G.roundMm(snap.point.y - gesture.anchor.y) };
        View.schedule(c); return true;
    }
    function endGroupMove(c, event) {
        const gesture = c.vectorGesture;
        if (!gesture || gesture.type !== "group-move" || gesture.pointerId !== event.pointerId) return false;
        const translation = c.vectorActiveTranslation || { dx: 0, dy: 0 };
        c.vectorGesture = null; c.vectorActiveTranslation = null; c.vectorSnapState = null; pointerRelease(c, event);
        if (Math.abs(translation.dx) < G.EPSILON_MM && Math.abs(translation.dy) < G.EPSILON_MM) { render(c); return true; }
        let document = c.history.current();
        gesture.objects.forEach(object => { document = D.replaceObject(document, G.translateObject(object, translation.dx, translation.dy)); });
        execute(c, document, `Move ${gesture.objects.length} objects`); return true;
    }
    function beginMarquee(c, event) {
        const start = root.ShapeView.eventWorld(c, event);
        c.vectorGesture = { type: "marquee", pointerId: event.pointerId, additive: hasModifier(event), initialIds: selectedIds(c).slice() };
        c.vectorMarquee = { start, current: start }; pointerCapture(c, event); View.schedule(c); return true;
    }
    function moveMarquee(c, event) {
        const gesture = c.vectorGesture;
        if (!gesture || gesture.type !== "marquee" || gesture.pointerId !== event.pointerId) return false;
        c.vectorMarquee.current = root.ShapeView.eventWorld(c, event); View.schedule(c); return true;
    }
    function endMarquee(c, event) {
        const gesture = c.vectorGesture, marquee = c.vectorMarquee;
        if (!gesture || gesture.type !== "marquee" || gesture.pointerId !== event.pointerId || !marquee) return false;
        const mode = marquee.current.x >= marquee.start.x ? "contain" : "intersect";
        const found = Selection.idsInRect(c.history.current(), Selection.normalizeRect(marquee.start, marquee.current), mode).filter(id => supportedObject(c, id));
        const next = gesture.additive ? unique([...gesture.initialIds, ...found]) : found;
        c.vectorGesture = null; c.vectorMarquee = null; pointerRelease(c, event); setObjectSelection(c, next, next[next.length - 1]); render(c); return true;
    }
    function selectedPath(c) { const object = D.objectById(c.history.current(), c.nodeEditId || c.selectedId); return object && object.type === G.PATH_TYPE ? object : null; }
    function setNodeSelection(c, indices, primary = null) {
        const object = selectedPath(c); if (!object) return;
        const max = object.geometry.points.length - 1;
        const clean = [...new Set((indices || []).map(Number).filter(index => Number.isInteger(index) && index >= 0 && index <= max))].sort((a, b) => a - b);
        c.selectedNodeIndices = clean; c.selectedSegmentIndices = []; c.selectedNodeIndex = clean.length === 1 ? clean[0] : null;
        if (primary != null && clean.length === 1) c.selectedNodeIndex = Number(primary); View.schedule(c);
    }
    function toggleNode(c, index) { const current = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.map(Number) : [], target = Number(index); setNodeSelection(c, current.includes(target) ? current.filter(item => item !== target) : [...current, target], target); }
    function setSegmentSelection(c, indices) {
        const object = selectedPath(c); if (!object) return;
        const max = G.pathSegments(object).length - 1;
        c.selectedSegmentIndices = [...new Set((indices || []).map(Number).filter(index => Number.isInteger(index) && index >= 0 && index <= max))].sort((a, b) => a - b);
        c.selectedNodeIndices = []; c.selectedNodeIndex = null; View.schedule(c);
    }
    function toggleSegment(c, index) { const current = Array.isArray(c.selectedSegmentIndices) ? c.selectedSegmentIndices.map(Number) : [], target = Number(index); setSegmentSelection(c, current.includes(target) ? current.filter(item => item !== target) : [...current, target]); }
    function beginMultiNodeMove(c, event, object, clickedIndex) {
        const indices = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.map(Number) : [];
        if (indices.length < 2 || !indices.includes(clickedIndex)) return false;
        c.vectorGesture = { type: "nodes-move", pointerId: event.pointerId, object, indices, primaryIndex: clickedIndex, originalPoints: object.geometry.points.slice() };
        c.previewObject = object; c.vectorSnapState = null; pointerCapture(c, event); return true;
    }
    function moveMultiNodes(c, event) {
        const gesture = c.vectorGesture;
        if (!gesture || gesture.type !== "nodes-move" || gesture.pointerId !== event.pointerId) return false;
        const raw = root.ShapeView.eventWorld(c, event), originalPrimary = gesture.originalPoints[gesture.primaryIndex];
        const snap = snapPoint(c, raw, [gesture.object.id], originalPrimary); c.vectorSnapState = snap;
        const dx = G.roundMm(snap.point.x - originalPrimary.x), dy = G.roundMm(snap.point.y - originalPrimary.y), selected = new Set(gesture.indices);
        const points = gesture.originalPoints.map((point, index) => selected.has(index) ? G.point(point.x + dx, point.y + dy) : point);
        c.previewObject = G.path(gesture.object.id, points, gesture.object.geometry.closed, gesture.object.style); render(c); return true;
    }
    function endMultiNodes(c, event) {
        const gesture = c.vectorGesture;
        if (!gesture || gesture.type !== "nodes-move" || gesture.pointerId !== event.pointerId) return false;
        const next = c.previewObject; c.vectorGesture = null; c.previewObject = null; c.vectorSnapState = null; pointerRelease(c, event);
        if (next && JSON.stringify(next.geometry) !== JSON.stringify(gesture.object.geometry)) execute(c, D.replaceObject(c.history.current(), next), `Move ${gesture.indices.length} path nodes`);
        else render(c); return true;
    }
    function replaceTranslated(c, offsets, label) {
        let document = c.history.current(), changed = 0;
        selectedObjects(c).forEach(object => { const offset = offsets[String(object.id)]; if (!offset || (Math.abs(offset.dx) < G.EPSILON_MM && Math.abs(offset.dy) < G.EPSILON_MM)) return; document = D.replaceObject(document, G.translateObject(object, offset.dx, offset.dy)); changed += 1; });
        if (!changed) return false; execute(c, document, label); return true;
    }
    function alignObjects(c, alignment) { const objects = selectedObjects(c); return objects.length >= 2 && replaceTranslated(c, Selection.alignOffsets(objects, alignment), `Align ${objects.length} objects ${alignment}`); }
    function distributeObjects(c, axis) { const objects = selectedObjects(c); return objects.length >= 3 && replaceTranslated(c, Selection.distributeOffsets(objects, axis), `Distribute ${objects.length} objects ${axis}`); }
    function addSegmentMidpoints(c) {
        const object = selectedPath(c), indices = Array.isArray(c.selectedSegmentIndices) ? c.selectedSegmentIndices.slice().map(Number).sort((a, b) => b - a) : [];
        if (!object || !indices.length) return false;
        let next = object; const inserted = [];
        indices.forEach(segmentIndex => { const midpoint = Selection.midpointOfSegment(next, segmentIndex); if (!midpoint) return; next = G.insertPathPoint(next, segmentIndex, midpoint); inserted.push(Math.min(next.geometry.points.length - 1, segmentIndex + 1)); });
        c.selectedSegmentIndices = []; setNodeSelection(c, inserted); execute(c, D.replaceObject(c.history.current(), next), `Insert ${inserted.length} segment midpoint nodes`); return true;
    }
    function transformSelectedNodes(c, axis, distribute = false) {
        const object = selectedPath(c), indices = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.map(Number) : [];
        if (!object || indices.length < 2) return false;
        const selected = indices.map(index => ({ index, point: object.geometry.points[index] })).filter(item => item.point); if (selected.length < 2) return false;
        const points = object.geometry.points.slice();
        if (distribute) {
            if (selected.length < 3) return false;
            selected.sort((a, b) => axis === "x" ? a.point.x - b.point.x : a.point.y - b.point.y);
            const first = axis === "x" ? selected[0].point.x : selected[0].point.y, last = axis === "x" ? selected[selected.length - 1].point.x : selected[selected.length - 1].point.y, step = (last - first) / (selected.length - 1);
            selected.forEach((item, order) => { const value = first + step * order; points[item.index] = axis === "x" ? G.point(value, item.point.y) : G.point(item.point.x, value); });
        } else {
            const primaryIndex = indices.includes(c.selectedNodeIndex) ? c.selectedNodeIndex : indices[0], primary = object.geometry.points[primaryIndex];
            selected.forEach(item => { points[item.index] = axis === "x" ? G.point(primary.x, item.point.y) : G.point(item.point.x, primary.y); });
        }
        execute(c, D.replaceObject(c.history.current(), G.path(object.id, points, object.geometry.closed, object.style)), `${distribute ? "Distribute" : "Align"} ${selected.length} nodes ${axis}`); return true;
    }
    function nudgeObjects(c, dx, dy) { const objects = selectedObjects(c); if (!objects.length) return false; let document = c.history.current(); objects.forEach(object => { document = D.replaceObject(document, G.translateObject(object, dx, dy)); }); execute(c, document, `Nudge ${objects.length} objects`); return true; }
    function nudgeNodes(c, dx, dy) {
        const object = selectedPath(c), indices = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.map(Number) : [];
        if (!object || indices.length < 2) return false;
        const selected = new Set(indices), points = object.geometry.points.map((point, index) => selected.has(index) ? G.point(point.x + dx, point.y + dy) : point);
        execute(c, D.replaceObject(c.history.current(), G.path(object.id, points, object.geometry.closed, object.style)), `Nudge ${indices.length} path nodes`); return true;
    }
    function deleteMultiObjects(c) { const ids = selectedIds(c); if (ids.length < 2) return false; let document = c.history.current(); ids.forEach(id => { document = D.removeObject(document, id); }); setObjectSelection(c, []); execute(c, document, `Delete ${ids.length} objects`); return true; }
    function deleteMultiNodes(c) {
        const object = selectedPath(c), indices = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.slice().map(Number).sort((a, b) => b - a) : [];
        if (!object || indices.length < 2) return false;
        let next = object; indices.forEach(index => { next = G.removePathPoint(next, index); });
        if (next === object || JSON.stringify(next.geometry) === JSON.stringify(object.geometry)) return false;
        setNodeSelection(c, []); execute(c, D.replaceObject(c.history.current(), next), `Delete ${indices.length} path nodes`); return true;
    }
    function activatePathTool(c) {
        if (!c || c.readOnly) return false;
        c.tool = PATH_TOOL; c.vectorPathDraft = null; c.vectorSnapState = null; c.nodeEditId = ""; c.selectedNodeIndex = null; c.selectedNodeIndices = []; c.selectedSegmentIndices = []; c.previewObject = null; render(c); return true;
    }
    function cancelPathDraft(c, keepTool = true) { c.vectorPathDraft = null; c.vectorSnapState = null; if (!keepTool) c.tool = "select"; render(c); }
    function closeTolerance(c) { return S.worldTolerance ? S.worldTolerance(c.viewport.scale, 14) : Math.max(0.8, 14 / Math.max(0.1, c.viewport.scale || 1)); }
    function endpointContinuation(c, point) {
        const tolerance = closeTolerance(c); let best = null;
        for (const object of c.history.current().objects || []) {
            if (object.type !== G.PATH_TYPE || object.geometry.closed || object.geometry.points.length < 2) continue;
            const first = object.geometry.points[0], last = object.geometry.points[object.geometry.points.length - 1];
            [["start", first, last], ["end", last, first]].forEach(([role, endpoint, opposite]) => { const distance = G.distance(point, endpoint); if (distance <= tolerance && (!best || distance < best.distance)) best = { object, role, endpoint, opposite, distance }; });
        }
        return best;
    }
    function beginPathDraft(c, point) {
        const continuation = endpointContinuation(c, point);
        if (continuation) {
            setObjectSelection(c, [continuation.object.id], continuation.object.id);
            c.vectorPathDraft = { points: [continuation.endpoint], hover: continuation.endpoint, closeReady: false, baseObject: continuation.object, extendAt: continuation.role, oppositeEndpoint: continuation.opposite };
        } else c.vectorPathDraft = { points: [point], hover: point, closeReady: false, baseObject: null, extendAt: null, oppositeEndpoint: null };
        View.schedule(c);
    }
    function pathDraftClick(c, event) {
        const raw = root.ShapeView.eventWorld(c, event), draft = c.vectorPathDraft, excluded = draft && draft.baseObject ? [draft.baseObject.id] : [];
        const snap = snapPoint(c, raw, excluded); c.vectorSnapState = snap; const point = snap.point;
        if (!draft) { beginPathDraft(c, point); return true; }
        if (draft.baseObject && draft.oppositeEndpoint && draft.points.length >= 2 && G.distance(point, draft.oppositeEndpoint) <= closeTolerance(c)) return commitPathDraft(c, true);
        if (!draft.baseObject && draft.points.length >= 3 && G.distance(point, draft.points[0]) <= closeTolerance(c)) return commitPathDraft(c, true);
        const last = draft.points[draft.points.length - 1]; if (G.distance(last, point) >= G.EPSILON_MM) draft.points.push(point);
        draft.hover = point; draft.closeReady = false; View.schedule(c); return true;
    }
    function pathDraftHover(c, event) {
        const draft = c.vectorPathDraft; if (c.tool !== PATH_TOOL || !draft) return false;
        const snap = snapPoint(c, root.ShapeView.eventWorld(c, event), draft.baseObject ? [draft.baseObject.id] : []); c.vectorSnapState = snap; draft.hover = snap.point;
        draft.closeReady = draft.baseObject ? Boolean(draft.oppositeEndpoint && draft.points.length >= 2 && G.distance(snap.point, draft.oppositeEndpoint) <= closeTolerance(c)) : Boolean(draft.points.length >= 3 && G.distance(snap.point, draft.points[0]) <= closeTolerance(c));
        View.schedule(c); return true;
    }
    function commitPathDraft(c, closed = false) {
        const draft = c.vectorPathDraft; if (!draft) return false;
        if (draft.baseObject) {
            const additions = draft.points.slice(1); if (!additions.length && !closed) return false;
            const basePoints = draft.baseObject.geometry.points.slice(), merged = draft.extendAt === "start" ? [...additions.slice().reverse(), ...basePoints] : [...basePoints, ...additions];
            if (merged.length < (closed ? 3 : 2)) return false;
            const next = G.path(draft.baseObject.id, merged, Boolean(closed), draft.baseObject.style);
            c.vectorPathDraft = null; c.vectorSnapState = null; c.tool = PATH_TOOL; c.selectedId = next.id; c.selectedIds = [next.id]; c.nodeEditId = next.id; c.selectedNodeIndices = []; c.selectedSegmentIndices = []; c.selectedNodeIndex = null;
            execute(c, D.replaceObject(c.history.current(), next), closed ? "Extend and close path" : "Extend path"); return true;
        }
        if (draft.points.length < (closed ? 3 : 2)) return false;
        const object = G.path(nextId("path"), draft.points, Boolean(closed));
        c.vectorPathDraft = null; c.vectorSnapState = null; c.tool = PATH_TOOL; c.selectedId = object.id; c.selectedIds = [object.id]; c.nodeEditId = object.id; c.selectedNodeIndices = []; c.selectedSegmentIndices = []; c.selectedNodeIndex = null;
        execute(c, D.addObject(c.history.current(), object), closed ? "Add closed vector path" : "Add vector path"); return true;
    }
    function backspacePathDraft(c) { const draft = c.vectorPathDraft; if (!draft) return false; if (draft.points.length > 1) draft.points.pop(); else c.vectorPathDraft = null; View.schedule(c); return true; }
    function handleAction(c, action) {
        if (!action || c.readOnly) return false;
        const alignMap = { "align-left": "left", "align-hcenter": "hcenter", "align-right": "right", "align-top": "top", "align-vcenter": "vcenter", "align-bottom": "bottom" };
        if (alignMap[action]) return alignObjects(c, alignMap[action]);
        if (action === "distribute-horizontal") return distributeObjects(c, "horizontal");
        if (action === "distribute-vertical") return distributeObjects(c, "vertical");
        if (action === "segment-midpoints") return addSegmentMidpoints(c);
        if (action === "nodes-align-x") return transformSelectedNodes(c, "x", false);
        if (action === "nodes-align-y") return transformSelectedNodes(c, "y", false);
        if (action === "nodes-distribute-x") return transformSelectedNodes(c, "x", true);
        if (action === "nodes-distribute-y") return transformSelectedNodes(c, "y", true);
        return false;
    }
    function pointerDown(c, event) {
        if (!localCanvasEvent(c, event) || c.readOnly || c.spaceHeld || event.button !== 0) return false;
        if (c.tool === PATH_TOOL) { pathDraftClick(c, event); event.preventDefault(); event.stopPropagation(); return true; }
        if (c.tool !== "select") return false;
        const node = targetNodeElement(event);
        if (node && String(c.nodeEditId || "") === String(node.dataset.ddv3Object || "")) {
            const object = selectedPath(c), index = Number(node.dataset.ddv3PathNode); if (!object || !Number.isInteger(index)) return false;
            if (hasModifier(event)) { toggleNode(c, index); event.preventDefault(); event.stopPropagation(); return true; }
            const nodeIds = Array.isArray(c.selectedNodeIndices) ? c.selectedNodeIndices.map(Number) : [];
            if (nodeIds.length > 1 && nodeIds.includes(index) && beginMultiNodeMove(c, event, object, index)) { event.preventDefault(); event.stopPropagation(); return true; }
            setNodeSelection(c, [index], index); deferLegacySync(c); return false;
        }
        const segment = targetSegmentElement(event);
        if (segment && String(c.nodeEditId || "") === String(segment.dataset.ddv3Object || "")) {
            const index = Number(segment.dataset.ddv3PathSegment);
            if (Number.isInteger(index)) { if (hasModifier(event)) toggleSegment(c, index); else setSegmentSelection(c, [index]); event.preventDefault(); event.stopPropagation(); return true; }
        }
        const handle = targetHandleElement(event), target = targetObjectElement(event);
        if (handle && target) { const id = String(target.dataset.ddv3Object || c.selectedId || ""); if (selectedIds(c).length > 1 && id) setObjectSelection(c, [id], id); deferLegacySync(c); return false; }
        if (target) {
            const id = String(target.dataset.ddv3Object || ""); if (!supportedObject(c, id)) return false;
            if (hasModifier(event)) { objectToggle(c, id); event.preventDefault(); event.stopPropagation(); return true; }
            const ids = selectedIds(c);
            if (ids.length > 1 && ids.includes(id) && beginGroupMove(c, event)) { event.preventDefault(); event.stopPropagation(); return true; }
            setObjectSelection(c, [id], id); deferLegacySync(c); return false;
        }
        beginMarquee(c, event); event.preventDefault(); event.stopPropagation(); return true;
    }
    function pointerMove(c, event) {
        if (!localCanvasEvent(c, event) || c.readOnly) return false;
        if (c.tool === PATH_TOOL && pathDraftHover(c, event)) { event.preventDefault(); event.stopPropagation(); return true; }
        if (moveGroup(c, event) || moveMarquee(c, event) || moveMultiNodes(c, event)) { event.preventDefault(); event.stopPropagation(); return true; }
        return false;
    }
    function pointerUp(c, event) {
        if (!localCanvasEvent(c, event) || c.readOnly) return false;
        if (endGroupMove(c, event) || endMarquee(c, event) || endMultiNodes(c, event)) { event.preventDefault(); event.stopPropagation(); return true; }
        deferLegacySync(c); return false;
    }
    function pointerCancel(c, event) {
        const gesture = c.vectorGesture; if (!gesture || gesture.pointerId !== event.pointerId) return false;
        c.vectorGesture = null; c.vectorMarquee = null; c.vectorActiveTranslation = null; c.previewObject = null; c.vectorSnapState = null; pointerRelease(c, event); render(c); event.preventDefault(); event.stopPropagation(); return true;
    }
    function rootClick(c, event) {
        const tool = event.target && event.target.closest ? event.target.closest('[data-ddv3-vector-tool="path"]') : null;
        if (tool) { activatePathTool(c); event.preventDefault(); event.stopPropagation(); return true; }
        const action = event.target && event.target.closest ? event.target.closest("[data-ddv3-vector-action]") : null;
        if (action) { handleAction(c, action.dataset.ddv3VectorAction); event.preventDefault(); event.stopPropagation(); return true; }
        return false;
    }
    function doubleClick(c, event) { if (!localCanvasEvent(c, event) || c.tool !== PATH_TOOL || !c.vectorPathDraft) return false; if (commitPathDraft(c, false)) { event.preventDefault(); event.stopPropagation(); return true; } return false; }
    function selectAll(c) { const ids = (c.history.current().objects || []).filter(object => Selection.boundsOfObject(object)).map(object => String(object.id)); setObjectSelection(c, ids, ids[ids.length - 1]); render(c); return true; }
    function editingInput(event) { const target = event && event.target; return Boolean(target && ((target.matches && target.matches("input, textarea, select")) || target.isContentEditable)); }
    function keyDown(c, event) {
        if (c.readOnly || editingInput(event)) return false;
        const mod = event.ctrlKey || event.metaKey, key = String(event.key || "").toLowerCase();
        if (mod && key === "a") { selectAll(c); event.preventDefault(); event.stopPropagation(); return true; }
        if (!mod && !event.altKey && key === "b") { activatePathTool(c); event.preventDefault(); event.stopPropagation(); return true; }
        if (c.tool === PATH_TOOL) {
            if (event.key === "Enter" && commitPathDraft(c, false)) { event.preventDefault(); event.stopPropagation(); return true; }
            if (event.key === "Backspace" && backspacePathDraft(c)) { event.preventDefault(); event.stopPropagation(); return true; }
            if (event.key === "Escape") { cancelPathDraft(c, false); event.preventDefault(); event.stopPropagation(); return true; }
        }
        if ((event.key === "Delete" || event.key === "Backspace") && deleteMultiNodes(c)) { event.preventDefault(); event.stopPropagation(); return true; }
        if ((event.key === "Delete" || event.key === "Backspace") && deleteMultiObjects(c)) { event.preventDefault(); event.stopPropagation(); return true; }
        const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
        if (arrows[event.key]) { const step = event.shiftKey ? FAST_NUDGE_MM : NUDGE_MM, [x, y] = arrows[event.key]; if (nudgeNodes(c, x * step, y * step) || (selectedIds(c).length > 1 && nudgeObjects(c, x * step, y * step))) { event.preventDefault(); event.stopPropagation(); return true; } }
        return false;
    }
    function install(c) {
        if (!c || !c.root || !c.canvas || c.__vectorEditingInstalled) return c;
        c.__vectorEditingInstalled = true; c.selectedIds = c.selectedId ? [String(c.selectedId)] : []; c.selectedNodeIndices = Number.isInteger(c.selectedNodeIndex) ? [Number(c.selectedNodeIndex)] : []; c.selectedSegmentIndices = []; c.vectorGesture = null; c.vectorMarquee = null; c.vectorActiveTranslation = null; c.vectorPathDraft = null; c.vectorSnapState = null;
        const onPointerDown = event => pointerDown(c, event), onPointerMove = event => pointerMove(c, event), onPointerUp = event => pointerUp(c, event), onPointerCancel = event => pointerCancel(c, event), onRootClick = event => rootClick(c, event), onDoubleClick = event => doubleClick(c, event), onKeyDown = event => keyDown(c, event);
        // Root capture runs before the existing canvas-level Smart Pen handlers.
        c.root.addEventListener("pointerdown", onPointerDown, true); c.root.addEventListener("pointermove", onPointerMove, true); c.root.addEventListener("pointerup", onPointerUp, true); c.root.addEventListener("pointercancel", onPointerCancel, true); c.root.addEventListener("click", onRootClick, true); c.root.addEventListener("dblclick", onDoubleClick, true);
        // Window capture runs before the base editor's document-level keyboard handler.
        window.addEventListener("keydown", onKeyDown, true);
        View.observe(c); View.decorate(c);
        if (c.dialog && c.dialog.$wrapper) c.dialog.$wrapper.one("hidden.bs.modal.ddv3-vector-editing-cleanup", () => {
            c.root.removeEventListener("pointerdown", onPointerDown, true); c.root.removeEventListener("pointermove", onPointerMove, true); c.root.removeEventListener("pointerup", onPointerUp, true); c.root.removeEventListener("pointercancel", onPointerCancel, true); c.root.removeEventListener("click", onRootClick, true); c.root.removeEventListener("dblclick", onDoubleClick, true); window.removeEventListener("keydown", onKeyDown, true); if (c.__vectorMutationObserver) c.__vectorMutationObserver.disconnect();
        });
        return c;
    }

    const originalOpen = Editor.open.bind(Editor), originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({ open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); }, view(frm, row) { return install(originalView(frm, row)); } });
    root.VectorEditing = Object.freeze({ PATH_TOOL, install, activatePathTool, commitPathDraft, setObjectSelection, alignObjects, distributeObjects, addSegmentMidpoints, transformSelectedNodes });
})();
