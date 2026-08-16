(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    const commands = root.GeometryCommands;
    const snapResolver = root.SnapResolver;
    const toolMachine = root.ToolStateMachine;
    if (!geometry || !documentModel || !commands || !snapResolver || !toolMachine) {
        throw new Error("Drawing V4 dependencies must load before interaction engine");
    }

    function create(options = {}) {
        let document = options.document || documentModel.create(options.blank || {});
        let toolState = toolMachine.create(options.initialTool || toolMachine.TOOLS.SELECT);
        let activePathId = null;
        let preview = null;
        const idFactory = options.idFactory || commands.createIdFactory("v4");

        function currentPath() {
            return activePathId ? documentModel.pathById(document, activePathId) : null;
        }

        function currentAnchor() {
            if (!activePathId) return null;
            const nodeId = documentModel.pathEndNodeId(document, activePathId);
            return documentModel.nodeById(document, nodeId);
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

        function state() {
            return Object.freeze({
                document,
                toolState,
                activePathId,
                preview,
            });
        }

        function setTool(tool) {
            const previous = toolState.activeTool;
            toolState = toolMachine.activate(toolState, tool);
            if (previous === toolMachine.TOOLS.PEN && tool !== toolMachine.TOOLS.PEN) {
                activePathId = null;
                preview = null;
            }
            return state();
        }

        function pointerMove(rawPoint, snapOptions = {}) {
            if (toolState.activeTool !== toolMachine.TOOLS.PEN || !activePathId) {
                preview = null;
                return state();
            }
            preview = snap(rawPoint, snapOptions);
            return state();
        }

        function pointerDown(rawPoint, snapOptions = {}) {
            if (toolState.activeTool !== toolMachine.TOOLS.PEN) {
                return Object.freeze({ kind: "ignored", ...state() });
            }

            if (!activePathId) {
                const target = snapResolver.resolve(document, { ...snapOptions, rawPoint });
                const result = commands.startPath(document, target, { idFactory });
                document = result.document;
                activePathId = result.pathId;
                preview = null;
                return Object.freeze({ kind: "path-started", nodeId: result.nodeId, ...state() });
            }

            const target = snap(rawPoint, snapOptions);
            const path = currentPath();
            const anchor = currentAnchor();
            if (!path || !anchor) throw new Error("Drawing pen session is inconsistent");

            if (target.nodeId === path.startNodeId && path.segmentIds.length >= 2) {
                document = commands.closePath(document, activePathId, { idFactory }).document;
                const closedPathId = activePathId;
                activePathId = null;
                preview = null;
                return Object.freeze({ kind: "path-closed", pathId: closedPathId, ...state() });
            }

            if (geometry.distance(anchor, target.point) <= geometry.EPSILON_MM) {
                return Object.freeze({ kind: "ignored-zero-length", ...state() });
            }

            const result = commands.appendLine(document, activePathId, target, { idFactory });
            document = result.document;
            preview = null;
            return Object.freeze({
                kind: "segment-added",
                pathId: activePathId,
                nodeId: result.nodeId,
                segmentId: result.segmentId,
                ...state(),
            });
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
            const result = commands.appendLine(document, activePathId, {
                type: "numeric",
                label: `${geometry.roundMm(length)} mm`,
                point: exactPoint,
                nodeId: null,
            }, { idFactory });
            document = result.document;
            preview = null;
            return Object.freeze({
                kind: "segment-added",
                source: "numeric-length",
                pathId: activePathId,
                nodeId: result.nodeId,
                segmentId: result.segmentId,
                ...state(),
            });
        }

        function cancelPenSession() {
            activePathId = null;
            preview = null;
            return state();
        }

        function keyDown(key) {
            if (String(key) === "Escape") return cancelPenSession();
            const tool = toolMachine.toolForShortcut(key);
            return tool ? setTool(tool) : state();
        }

        function spaceDown() {
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
            inputLength,
            cancelPenSession,
            keyDown,
            spaceDown,
            spaceUp,
        });
    }

    root.InteractionEngine = Object.freeze({ create });
})();