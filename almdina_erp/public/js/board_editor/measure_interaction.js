(() => {
    "use strict";

    function createMeasureInteraction(options) {
        const {
            store,
            getSvgEl,
            getWorldMetrics,
            isAltKey,
            isPanKey,
            isMeasureToolActive,
            onOverlay,
            onRejected,
        } = options || {};

        let toolGesture = null;
        let committedLine = null;
        let altOverlay = [];
        let lastPointer = null;

        function geometry() {
            return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MeasureGeometry;
        }

        function clientToWorld(clientX, clientY) {
            const svg = getSvgEl && getSvgEl();
            const metrics = getWorldMetrics && getWorldMetrics();
            if (!svg || !metrics) return null;
            const rect = svg.getBoundingClientRect();
            if (!(rect.width > 0) || !(rect.height > 0)) return null;
            const nx = (clientX - rect.left) / rect.width;
            const ny = (clientY - rect.top) / rect.height;
            return {
                x: metrics.minX + nx * metrics.width,
                y: metrics.minY + ny * metrics.height,
            };
        }

        function publish() {
            if (!onOverlay) return;
            const lines = [];
            if (toolGesture && toolGesture.preview) lines.push(toolGesture.preview);
            else if (committedLine) lines.push(committedLine);
            (altOverlay || []).forEach((row) => lines.push(row));
            onOverlay(lines);
        }

        function clearAltOverlay() {
            altOverlay = [];
            publish();
        }

        function clearToolLine() {
            toolGesture = null;
            committedLine = null;
            publish();
        }

        function clearAll() {
            toolGesture = null;
            committedLine = null;
            altOverlay = [];
            publish();
        }

        function refreshAltInspection(clientX, clientY) {
            const MG = geometry();
            const snap = store && store.snapshot();
            if (!MG || !snap || !snap.session) {
                clearAltOverlay();
                return;
            }
            // While dragging with Alt, snap-bypass owns Alt — do not show spacing.
            if (isMeasureToolActive && isMeasureToolActive()) {
                clearAltOverlay();
                return;
            }
            if (!(isAltKey && isAltKey())) {
                clearAltOverlay();
                return;
            }
            const selectedKey = snap.selectedPieceKey
                || (Array.isArray(snap.selectedPieceKeys) && snap.selectedPieceKeys.length === 1
                    ? snap.selectedPieceKeys[0]
                    : null);
            if (!selectedKey || (Array.isArray(snap.selectedPieceKeys) && snap.selectedPieceKeys.length > 1)) {
                clearAltOverlay();
                return;
            }
            const selected = snap.session.pieces[selectedKey];
            if (!selected || selected.distribution === "excluded") {
                clearAltOverlay();
                return;
            }

            const world = clientX != null ? clientToWorld(clientX, clientY) : (lastPointer ? { x: lastPointer[0], y: lastPointer[1] } : null);
            let hoverKey = null;
            if (world) {
                lastPointer = [world.x, world.y];
                hoverKey = MG.hitTestPieceKey(snap.session, [world.x, world.y], selected.sheet_no);
                if (hoverKey === selectedKey) hoverKey = null;
            }

            if (hoverKey) {
                const between = MG.shortestClearanceBetweenPieces(snap.session, selectedKey, hoverKey);
                altOverlay = between
                    ? [{
                        ...between,
                        label: MG.formatDistanceMm(between.distance),
                        style: "alt",
                    }]
                    : [];
                publish();
                return;
            }

            altOverlay = MG.edgeClearances(snap.session, selectedKey).map((row) => ({
                ...row,
                label: MG.formatDistanceMm(row.distance),
                style: "alt",
            }));
            publish();
        }

        function beginTool(event) {
            const MG = geometry();
            if (!MG || !store || !(isMeasureToolActive && isMeasureToolActive())) return false;
            if (isPanKey && isPanKey()) return false;
            const snap = store.snapshot();
            if (!snap.session) return false;
            const world = clientToWorld(event.clientX, event.clientY);
            if (!world) return false;
            const boardHit = MG.findBoardAtWorld(snap.session, [world.x, world.y]);
            if (!boardHit) {
                if (onRejected) onRejected(__("Start the measurement inside a board."));
                return false;
            }
            const start = MG.clampPointToRect([world.x, world.y], boardHit.outer);
            toolGesture = {
                sheetNo: boardHit.sheetNo,
                outer: boardHit.outer,
                start,
                preview: null,
            };
            committedLine = null;
            altOverlay = [];
            publish();
            if (event.preventDefault) event.preventDefault();
            return true;
        }

        function onPointerMove(event) {
            if (event && event.clientX != null) {
                const world = clientToWorld(event.clientX, event.clientY);
                if (world) lastPointer = [world.x, world.y];
            }
            if (toolGesture) {
                const MG = geometry();
                if (!MG) return;
                const world = clientToWorld(event.clientX, event.clientY);
                if (!world) return;
                const end = MG.clampPointToRect([world.x, world.y], toolGesture.outer);
                const line = MG.measureLine(toolGesture.start, end);
                toolGesture.preview = line
                    ? { ...line, style: "draft", dashed: false }
                    : null;
                publish();
                return;
            }
            refreshAltInspection(event.clientX, event.clientY);
        }

        function onPointerUp(event) {
            if (!toolGesture) {
                refreshAltInspection(event && event.clientX, event && event.clientY);
                return;
            }
            const MG = geometry();
            const world = event ? clientToWorld(event.clientX, event.clientY) : null;
            const end = MG && world
                ? MG.clampPointToRect([world.x, world.y], toolGesture.outer)
                : toolGesture.start;
            const line = MG ? MG.measureLine(toolGesture.start, end) : null;
            committedLine = line ? { ...line, style: "committed", dashed: true } : null;
            toolGesture = null;
            publish();
        }

        function onPointerCancel() {
            if (toolGesture) {
                toolGesture = null;
                publish();
            }
        }

        function cancel() {
            if (toolGesture) {
                toolGesture = null;
                publish();
                return true;
            }
            if (committedLine) {
                committedLine = null;
                publish();
                return true;
            }
            return false;
        }

        function isToolGestureActive() {
            return Boolean(toolGesture);
        }

        return Object.freeze({
            beginTool,
            onPointerMove,
            onPointerUp,
            onPointerCancel,
            cancel,
            clearAll,
            clearToolLine,
            clearAltOverlay,
            refreshAltInspection,
            isToolGestureActive,
            clientToWorld,
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createMeasureInteraction = createMeasureInteraction;
})();
