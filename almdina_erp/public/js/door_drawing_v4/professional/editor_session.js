(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const v4 = window.AlmdinaDoorDrawingV4;
    const geometry = v4.Geometry;
    const documentModel = v4.DocumentModel;
    const commands = v4.GeometryCommands;
    const dimensions = v4.DimensionCommands;
    const driving = v4.DrivingDimensionCommands;
    const inference = v4.ConstraintInference;
    const solver = v4.ConstraintSolver;
    const snapResolver = v4.SnapResolver;
    const strokeInterpreter = v4.StrokeInterpreter;
    const hitTest = v4.HitTest;
    const historyFactory = v4.CommandHistory;
    const tools = v4.ToolStateMachine;
    if (!geometry || !documentModel || !commands || !dimensions || !driving || !inference || !solver || !snapResolver || !strokeInterpreter || !hitTest || !historyFactory || !tools) {
        throw new Error("Door Drawing professional session dependencies are incomplete");
    }

    function create(options = {}) {
        let document = options.document || documentModel.create(options.blank || {});
        let toolState = tools.create(options.initialTool || tools.TOOLS.SELECT);
        let activePathId = null;
        let preview = null;
        let selection = null;
        let drag = null;
        let snapLock = null;
        const history = historyFactory.create({ limit: options.historyLimit || 200 });
        const idFactory = options.idFactory || commands.createIdFactory("pro");

        function path() { return activePathId ? documentModel.pathById(document, activePathId) : null; }
        function anchor() {
            if (!activePathId) return null;
            return documentModel.nodeById(document, documentModel.pathEndNodeId(document, activePathId));
        }
        function state() {
            const current = drag ? documentModel.nodeById(document, drag.nodeId) : null;
            return Object.freeze({
                document,
                toolState,
                activePathId,
                preview,
                selection,
                drag: drag && current ? Object.freeze({
                    kind: "node",
                    nodeId: drag.nodeId,
                    origin: drag.origin,
                    current,
                    delta: Object.freeze({
                        xMm: geometry.roundMm(current.xMm - drag.origin.xMm),
                        yMm: geometry.roundMm(current.yMm - drag.origin.yMm),
                    }),
                }) : null,
                history: history.snapshot(),
            });
        }
        function record(before, label) { history.record(before, document, label); }
        function resetSnap() { snapLock = null; preview = null; }
        function snapOptions(rawPoint, input = {}) {
            const currentPath = path();
            const currentAnchor = anchor();
            const canClose = Boolean(currentPath && !currentPath.closed && currentPath.segmentIds.length >= 2);
            const toleranceMm = Math.max(0, Number(input.toleranceMm) || 0);
            const result = snapResolver.resolve(document, {
                ...input,
                rawPoint,
                origin: currentAnchor,
                excludeNodeIds: currentAnchor ? [currentAnchor.id] : [],
                canClose,
                closeNodeId: canClose ? currentPath.startNodeId : null,
                previousSnap: snapLock,
                releaseToleranceMm: Math.max(
                    toleranceMm,
                    Number(input.releaseToleranceMm) || toleranceMm * snapResolver.DEFAULT_RELEASE_MULTIPLIER
                ),
            });
            snapLock = result.type === "free" ? null : result;
            return result;
        }
        function smartenSegment(segmentId) {
            const result = inference.inferSegmentAxis(document, segmentId, { idFactory, toleranceMm: 0.01 });
            document = result.document;
            return result;
        }
        function incidentSegments(nodeId, source = document) {
            return (source.segments || []).filter(segment => segment.startNodeId === nodeId || segment.endNodeId === nodeId);
        }
        function otherNode(segment, nodeId, source = document) {
            const otherId = segment.startNodeId === nodeId ? segment.endNodeId : segment.startNodeId;
            return documentModel.nodeById(source, otherId);
        }
        function fixedLengthConstraintsFor(nodeId) {
            const segmentIds = new Set(incidentSegments(nodeId).map(segment => segment.id));
            return (document.constraints || []).filter(constraint => (
                constraint.type === documentModel.CONSTRAINT_TYPES.FIXED_LENGTH
                && segmentIds.has(constraint.segmentId)
            ));
        }
        function setTool(tool) {
            if (drag) cancelDrag();
            activePathId = null;
            resetSnap();
            toolState = tools.activate(toolState, tool);
            if (tool === tools.TOOLS.PEN || tool === tools.TOOLS.SMART_PENCIL) selection = null;
            return state();
        }
        function pointerMove(rawPoint, input = {}) {
            if (drag) {
                const toleranceMm = Math.max(0, Number(input.toleranceMm) || 0);
                const target = snapResolver.resolve(document, {
                    ...input,
                    rawPoint,
                    origin: drag.referenceNode,
                    excludeNodeIds: [drag.nodeId],
                    canClose: false,
                    previousSnap: snapLock,
                    releaseToleranceMm: Math.max(
                        toleranceMm,
                        Number(input.releaseToleranceMm) || toleranceMm * snapResolver.DEFAULT_RELEASE_MULTIPLIER
                    ),
                });
                snapLock = target.type === "free" ? null : target;
                preview = target;
                const moved = documentModel.moveNode(document, drag.nodeId, target.point);
                const solved = solver.solve(moved, {
                    pinnedNodeIds: [drag.nodeId],
                    toleranceMm: 0.01,
                });
                if (solved.ok) {
                    document = solved.document;
                    drag.lastValid = document;
                } else {
                    document = drag.lastValid;
                }
                return state();
            }
            if (toolState.activeTool !== tools.TOOLS.PEN) {
                resetSnap();
                return state();
            }
            preview = snapOptions(rawPoint, input);
            return state();
        }
        function penDown(rawPoint, input = {}) {
            const target = snapOptions(rawPoint, input);
            if (!activePathId) {
                const before = document;
                const result = commands.startPath(document, target, { idFactory });
                document = result.document;
                activePathId = result.pathId;
                resetSnap();
                record(before, "start-path");
                return Object.freeze({ kind: "path-started", ...state() });
            }
            const currentPath = path();
            const currentAnchor = anchor();
            if (target.nodeId === currentPath.startNodeId && currentPath.segmentIds.length >= 2) {
                const before = document;
                document = commands.closePath(document, activePathId, { idFactory }).document;
                const closedPathId = activePathId;
                activePathId = null;
                resetSnap();
                record(before, "close-path");
                selection = Object.freeze({ kind: "path", id: closedPathId });
                return Object.freeze({ kind: "path-closed", pathId: closedPathId, ...state() });
            }
            if (geometry.distance(currentAnchor, target.point) <= geometry.EPSILON_MM) {
                return Object.freeze({ kind: "ignored-zero-length", ...state() });
            }
            const before = document;
            const result = commands.appendLine(document, activePathId, target, { idFactory });
            document = result.document;
            smartenSegment(result.segmentId);
            resetSnap();
            record(before, "add-segment");
            return Object.freeze({ kind: "segment-added", segmentId: result.segmentId, ...state() });
        }
        function smartStrokeTarget(rawPoint, origin, input = {}) {
            const toleranceMm = Math.max(0, Number(input.snapToleranceMm ?? input.toleranceMm) || 0);
            if (toleranceMm <= 0) {
                return Object.freeze({ type: "smart-stroke", semantic: "smart-stroke", point: geometry.clonePoint(rawPoint), nodeId: null });
            }
            return snapResolver.resolve(document, {
                rawPoint,
                origin: origin || null,
                toleranceMm,
                releaseToleranceMm: toleranceMm,
                excludeNodeIds: origin && origin.id ? [origin.id] : [],
                canClose: false,
                gridStepMm: 0,
            });
        }
        function commitSmartStroke(rawPoints, input = {}) {
            if (toolState.activeTool !== tools.TOOLS.SMART_PENCIL) {
                return Object.freeze({ kind: "ignored", ...state() });
            }
            const interpreted = strokeInterpreter.interpret(rawPoints, input);
            if (!interpreted.ok) {
                return Object.freeze({ kind: "smart-stroke-ignored", code: interpreted.code, ...state() });
            }

            const before = document;
            const firstTarget = smartStrokeTarget(interpreted.points[0], null, input);
            const started = commands.startPath(document, firstTarget, { idFactory });
            document = started.document;
            const strokePathId = started.pathId;
            const segmentIds = [];

            for (let index = 1; index < interpreted.points.length; index += 1) {
                const currentNodeId = documentModel.pathEndNodeId(document, strokePathId);
                const currentAnchor = documentModel.nodeById(document, currentNodeId);
                const isLast = index === interpreted.points.length - 1;
                const target = isLast && !interpreted.closed
                    ? smartStrokeTarget(interpreted.points[index], currentAnchor, input)
                    : Object.freeze({
                        type: "smart-stroke",
                        semantic: "smart-stroke",
                        point: geometry.clonePoint(interpreted.points[index]),
                        nodeId: null,
                    });
                if (geometry.distance(currentAnchor, target.point) <= geometry.EPSILON_MM) continue;
                const appended = commands.appendLine(document, strokePathId, target, { idFactory });
                document = appended.document;
                segmentIds.push(appended.segmentId);
                smartenSegment(appended.segmentId);
            }

            if (!segmentIds.length) {
                document = before;
                return Object.freeze({ kind: "smart-stroke-ignored", code: "too-short", ...state() });
            }
            if (interpreted.closed && segmentIds.length >= 2) {
                document = commands.closePath(document, strokePathId, { idFactory }).document;
            }
            activePathId = null;
            resetSnap();
            selection = Object.freeze({ kind: "path", id: strokePathId });
            record(before, "smart-stroke");
            return Object.freeze({
                kind: "smart-stroke-added",
                pathId: strokePathId,
                segmentIds: Object.freeze([...segmentIds]),
                sourcePointCount: interpreted.sourcePointCount,
                simplifiedPointCount: interpreted.simplifiedPointCount,
                closed: interpreted.closed,
                ...state(),
            });
        }
        function beginNodeDrag(rawPoint, input = {}) {
            const hit = hitTest.node(document, rawPoint, Math.max(0, Number(input.hitToleranceMm ?? input.toleranceMm) || 0));
            if (!hit) {
                selection = null;
                return Object.freeze({ kind: "selection-cleared", ...state() });
            }
            const node = documentModel.nodeById(document, hit.id);
            selection = Object.freeze({ kind: "node", id: hit.id });
            if (fixedLengthConstraintsFor(hit.id).length) {
                return Object.freeze({ kind: "fixed-length-protected-node", nodeId: hit.id, ...state() });
            }
            const incident = incidentSegments(hit.id);
            const referenceNode = incident.length ? otherNode(incident[0], hit.id) : null;
            drag = {
                nodeId: hit.id,
                origin: node,
                referenceNode,
                before: document,
                lastValid: document,
            };
            resetSnap();
            return Object.freeze({ kind: "node-drag-started", nodeId: hit.id, ...state() });
        }
        function finishDrag() {
            if (!drag) return Object.freeze({ kind: "ignored", ...state() });
            const dragSession = drag;
            drag = null;
            resetSnap();
            const current = documentModel.nodeById(document, dragSession.nodeId);
            if (geometry.distance(dragSession.origin, current) > geometry.EPSILON_MM) {
                record(dragSession.before, "move-node");
            }
            return Object.freeze({ kind: "node-drag-finished", nodeId: dragSession.nodeId, ...state() });
        }
        function cancelDrag() {
            if (!drag) return false;
            document = drag.before;
            drag = null;
            resetSnap();
            return true;
        }
        function dimensionDown(rawPoint, input = {}) {
            const hit = hitTest.segment(document, rawPoint, Math.max(0, Number(input.hitToleranceMm ?? input.toleranceMm) || 0));
            if (!hit) {
                selection = null;
                return Object.freeze({ kind: "selection-cleared", ...state() });
            }
            const before = document;
            const result = dimensions.ensureSegmentLength(document, hit.id, { idFactory });
            document = result.document;
            selection = Object.freeze({ kind: "dimension", id: result.dimensionId });
            if (result.created) record(before, "add-dimension");
            return Object.freeze({ kind: result.created ? "dimension-added" : "dimension-selected", ...state() });
        }
        function pointerDown(rawPoint, input = {}) {
            if (toolState.activeTool === tools.TOOLS.PEN) return penDown(rawPoint, input);
            if (toolState.activeTool === tools.TOOLS.NODE) return beginNodeDrag(rawPoint, input);
            if (toolState.activeTool === tools.TOOLS.DIMENSION) return dimensionDown(rawPoint, input);
            if (toolState.activeTool === tools.TOOLS.SELECT) {
                const hit = hitTest.selectPath(document, rawPoint, Math.max(0, Number(input.hitToleranceMm ?? input.toleranceMm) || 0));
                selection = hit ? Object.freeze({ kind: "path", id: hit.id }) : null;
                return Object.freeze({ kind: hit ? "path-selected" : "selection-cleared", ...state() });
            }
            return Object.freeze({ kind: "ignored", ...state() });
        }
        function pointerUp() {
            return drag ? finishDrag() : Object.freeze({ kind: "ignored", ...state() });
        }
        function inputLength(lengthMm) {
            if (toolState.activeTool !== tools.TOOLS.PEN || !activePathId || !preview) {
                return Object.freeze({ kind: "ignored", ...state() });
            }
            const length = geometry.finiteNumber(lengthMm);
            if (length <= geometry.EPSILON_MM) return Object.freeze({ kind: "invalid-length", ...state() });
            const currentAnchor = anchor();
            const angleDeg = geometry.angleDeg(currentAnchor, preview.point);
            const exactPoint = geometry.pointFromPolar(currentAnchor, length, angleDeg);
            const before = document;
            const result = commands.appendLine(document, activePathId, {
                type: "numeric",
                semantic: "numeric",
                point: exactPoint,
                nodeId: null,
            }, { idFactory });
            document = result.document;
            smartenSegment(result.segmentId);
            resetSnap();
            record(before, "add-segment");
            return Object.freeze({ kind: "segment-added", source: "numeric-length", segmentId: result.segmentId, ...state() });
        }
        function inputDimensionValue(valueMm) {
            if (toolState.activeTool !== tools.TOOLS.DIMENSION || !selection || selection.kind !== "dimension") {
                return Object.freeze({ kind: "ignored", ...state() });
            }
            const before = document;
            const result = driving.drive(document, selection.id, geometry.finiteNumber(valueMm), { idFactory });
            if (!result.ok) return Object.freeze({ kind: "dimension-drive-failed", code: result.code, ...state() });
            document = result.document;
            if (before !== document) record(before, "drive-dimension");
            return Object.freeze({ kind: "dimension-driven", ...state() });
        }
        function cancel() {
            if (cancelDrag()) return Object.freeze({ kind: "node-drag-cancelled", ...state() });
            if (activePathId) {
                activePathId = null;
                resetSnap();
                return Object.freeze({ kind: "pen-session-ended", ...state() });
            }
            if (selection) {
                selection = null;
                return Object.freeze({ kind: "selection-cleared", ...state() });
            }
            return Object.freeze({ kind: "ignored", ...state() });
        }
        function undo() {
            cancelDrag();
            activePathId = null;
            selection = null;
            resetSnap();
            const result = history.undo(document);
            document = result.document;
            return Object.freeze({ kind: result.changed ? "undo" : "ignored", ...state() });
        }
        function redo() {
            cancelDrag();
            activePathId = null;
            selection = null;
            resetSnap();
            const result = history.redo(document);
            document = result.document;
            return Object.freeze({ kind: result.changed ? "redo" : "ignored", ...state() });
        }
        function spaceDown() {
            if (drag) finishDrag();
            toolState = tools.activateTemporary(toolState, tools.TOOLS.HAND);
            resetSnap();
            return state();
        }
        function spaceUp() {
            toolState = tools.restoreTemporary(toolState);
            return state();
        }
        function selectPath(id) {
            selection = documentModel.pathById(document, id)
                ? Object.freeze({ kind: "path", id: String(id) })
                : null;
            return state();
        }

        return Object.freeze({
            state,
            setTool,
            pointerMove,
            pointerDown,
            pointerUp,
            commitSmartStroke,
            inputLength,
            inputDimensionValue,
            cancel,
            undo,
            redo,
            spaceDown,
            spaceUp,
            selectPath,
        });
    }

    root.EditorSession = Object.freeze({ create });
})();
