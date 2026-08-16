(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const commands = root.GeometryCommands;
    const snapResolver = root.SnapResolver;
    const toolMachine = root.ToolStateMachine;
    const hitTest = root.HitTest;
    const commandHistory = root.CommandHistory;
    if (!geometry || !documentModel || !commands || !snapResolver || !toolMachine || !hitTest || !commandHistory) {
        throw new Error("Drawing V4 dependencies must load before interaction engine");
    }

    function samePoint(left, right) {
        return Boolean(left && right)
            && geometry.distance(left, right) <= geometry.EPSILON_MM;
    }

    function create(options = {}) {
        let document = options.document || documentModel.create(options.blank || {});
        let toolState = toolMachine.create(options.initialTool || toolMachine.TOOLS.SELECT);
        let activePathId = null;
        let preview = null;
        let selection = null;
        let dragSession = null;
        const history = commandHistory.create({ limit: options.historyLimit });
        const idFactory = options.idFactory || commands.createIdFactory("v4");

        function currentPath() {
            return activePathId ? documentModel.pathById(document, activePathId) : null;
        }

        function currentAnchor() {
            if (!activePathId) return null;
            const nodeId = documentModel.pathEndNodeId(document, activePathId);
            return documentModel.nodeById(document, nodeId);
        }

        function dragView() {
            if (!dragSession) return null;
            const current = documentModel.nodeById(document, dragSession.nodeId);
            return Object.freeze({
                kind: "node",
                nodeId: dragSession.nodeId,
                origin: dragSession.origin,
                current,
                delta: current ? Object.freeze({
                    xMm: geometry.roundMm(current.xMm - dragSession.origin.xMm),
                    yMm: geometry.roundMm(current.yMm - dragSession.origin.yMm),
                }) : null,
            });
        }

        function state() {
            return Object.freeze({
                document,
                toolState,
                activePathId,
                preview,
                selection,
                drag: dragView(),
                history: history.snapshot(),
            });
        }

        function record(before, label) {
            history.record(before, document, label);
        }

        function snap(rawPoint, snapOptions = {}) {
            const anchor = currentAnchor();
            const excluded = anchor ? [anchor.id, ...(snapOptions.excludeNodeIds || [])] : (snapOptions.excludeNodeIds || []);
            return snapResolver.resolve(document, {
                ...snapOptions,
                rawPoint,
                origin: anchor,
                excludeNodeIds: excluded,
            });
        }

        function hitTolerance(options = {}) {
            return Math.max(0, Number(options.hitToleranceMm ?? options.toleranceMm) || 0);
        }

        function clearTransientState() {
            activePathId = null;
            preview = null;
            dragSession = null;
        }

        function setTool(tool) {
            if (dragSession) document = dragSession.beforeDocument;
            clearTransientState();
            toolState = toolMachine.activate(toolState, tool);
            if (tool === toolMachine.TOOLS.PEN) selection = null;
            return state();
        }

        function selectAt(rawPoint, options = {}) {
            const hit = hitTest.selectPath(document, rawPoint, hitTolerance(options));
            selection = hit ? Object.freeze({ kind: "path", id: hit.id }) : null;
            return Object.freeze({ kind: hit ? "path-selected" : "selection-cleared", ...state() });
        }

        function beginNodeDrag(rawPoint, options = {}) {
            const hit = hitTest.node(document, rawPoint, hitTolerance(options));
            if (!hit) {
                selection = null;
                dragSession = null;
                return Object.freeze({ kind: "selection-cleared", ...state() });
            }
            const origin = documentModel.nodeById(document, hit.id);
            selection = Object.freeze({ kind: "node", id: hit.id });
            dragSession = Object.freeze({
                nodeId: hit.id,
                origin,
                beforeDocument: document,
            });
            return Object.freeze({ kind: "node-drag-started", nodeId: hit.id, ...state() });
        }

        function moveNodeDrag(rawPoint) {
            if (!dragSession) return state();
            const current = documentModel.nodeById(document, dragSession.nodeId);
            if (samePoint(current, rawPoint)) return state();
            document = documentModel.moveNode(document, dragSession.nodeId, rawPoint);
            return state();
        }

        function finishNodeDrag() {
            if (!dragSession) return Object.freeze({ kind: "ignored", ...state() });
            const session = dragSession;
            const current = documentModel.nodeById(document, session.nodeId);
            dragSession = null;
            if (!samePoint(session.origin, current)) {
                history.record(session.beforeDocument, document, "move-node");
                return Object.freeze({ kind: "node-drag-committed", nodeId: session.nodeId, ...state() });
            }
            document = session.beforeDocument;
            return Object.freeze({ kind: "node-selected", nodeId: session.nodeId, ...state() });
        }

        function cancelNodeDrag() {
            if (!dragSession) return false;
            document = dragSession.beforeDocument;
            dragSession = null;
            return true;
        }

        function pointerMove(rawPoint, options = {}) {
            if (dragSession) return moveNodeDrag(rawPoint);
            if (toolState.activeTool !== toolMachine.TOOLS.PEN || !activePathId) {
                preview = null;
                return state();
            }
            preview = snap(rawPoint, options);
            return state();
        }

        function penPointerDown(rawPoint, options = {}) {
            if (!activePathId) {
                const target = snapResolver.resolve(document, { ...options, rawPoint });
                const before = document;
                const result = commands.startPath(document, target, { idFactory });
                document = result.document;
                activePathId = result.pathId;
                preview = null;
                record(before, "start-path");
                return Object.freeze({ kind: "path-started", nodeId: result.nodeId, ...state() });
            }

            const target = snap(rawPoint, options);
            const path = currentPath();
            const anchor = currentAnchor();
            if (!path || !anchor) throw new Error("Drawing pen session is inconsistent");

            if (target.nodeId === path.startNodeId && path.segmentIds.length >= 2) {
                const before = document;
                document = commands.closePath(document, activePathId, { idFactory }).document;
                const closedPathId = activePathId;
                activePathId = null;
                preview = null;
                record(before, "close-path");
                return Object.freeze({ kind: "path-closed", pathId: closedPathId, ...state() });
            }

            if (geometry.distance(anchor, target.point) <= geometry.EPSILON_MM) {
                return Object.freeze({ kind: "ignored-zero-length", ...state() });
            }

            const before = document;
            const result = commands.appendLine(document, activePathId, target, { idFactory });
            document = result.document;
            preview = null;
            record(before, "add-segment");
            return Object.freeze({
                kind: "segment-added",
                pathId: activePathId,
                nodeId: result.nodeId,
                segmentId: result.segmentId,
                ...state(),
            });
        }

        function pointerDown(rawPoint, options = {}) {
            if (toolState.activeTool === toolMachine.TOOLS.SELECT) return selectAt(rawPoint, options);
            if (toolState.activeTool === toolMachine.TOOLS.NODE) return beginNodeDrag(rawPoint, options);
            if (toolState.activeTool === toolMachine.TOOLS.PEN) return penPointerDown(rawPoint, options);
            return Object.freeze({ kind: "ignored", ...state() });
        }

        function pointerUp() {
            return dragSession ? finishNodeDrag() : Object.freeze({ kind: "ignored", ...state() });
        }

        function inputLength(lengthMm) {
            if (toolState.activeTool !== toolMachine.TOOLS.PEN || !activePathId || !preview) {
                return Object.freeze({ kind: "ignored", ...state() });
            }
            const length = geometry.finiteNumber(lengthMm);
            if (length <= geometry.EPSILON_MM) throw new Error("Drawing length must be greater than zero");

            const anchor = currentAnchor();
            const angleDeg = geometry.angleDeg(anchor, preview.point);
            const exactPoint = geometry.pointFromPolar(anchor, length, angleDeg);
            const before = document;
            const result = commands.appendLine(document, activePathId, {
                type: "numeric",
                semantic: "numeric",
                point: exactPoint,
                nodeId: null,
            }, { idFactory });
            document = result.document;
            preview = null;
            record(before, "add-segment");
            return Object.freeze({
                kind: "segment-added",
                source: "numeric-length",
                pathId: activePathId,
                nodeId: result.nodeId,
                segmentId: result.segmentId,
                ...state(),
            });
        }

        function cancel() {
            if (cancelNodeDrag()) return Object.freeze({ kind: "node-drag-cancelled", ...state() });
            if (activePathId) {
                activePathId = null;
                preview = null;
                return Object.freeze({ kind: "pen-session-ended", ...state() });
            }
            if (selection) {
                selection = null;
                return Object.freeze({ kind: "selection-cleared", ...state() });
            }
            return Object.freeze({ kind: "ignored", ...state() });
        }

        function undo() {
            cancelNodeDrag();
            clearTransientState();
            selection = null;
            const result = history.undo(document);
            document = result.document;
            return Object.freeze({ kind: result.changed ? "undo" : "ignored", label: result.label || null, ...state() });
        }

        function redo() {
            cancelNodeDrag();
            clearTransientState();
            selection = null;
            const result = history.redo(document);
            document = result.document;
            return Object.freeze({ kind: result.changed ? "redo" : "ignored", label: result.label || null, ...state() });
        }

        function keyDown(key) {
            if (String(key) === "Escape") return cancel();
            const tool = toolMachine.toolForShortcut(key);
            return tool ? setTool(tool) : state();
        }

        function spaceDown() {
            if (dragSession) finishNodeDrag();
            toolState = toolMachine.activateTemporary(toolState, toolMachine.TOOLS.HAND);
            preview = null;
            return state();
        }

        function spaceUp() {
            toolState = toolMachine.restoreTemporary(toolState);
            return state();
        }

        return Object.freeze({
            state,
            setTool,
            pointerMove,
            pointerDown,
            pointerUp,
            inputLength,
            cancel,
            undo,
            redo,
            keyDown,
            spaceDown,
            spaceUp,
        });
    }

    root.InteractionEngine = Object.freeze({ create });
})();