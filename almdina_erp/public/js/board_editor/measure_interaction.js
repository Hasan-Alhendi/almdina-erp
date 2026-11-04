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
        let altCache = null;
        let geometryComputeCount = 0;

        function geometry() {
            return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MeasureGeometry;
        }

        function altActive(event) {
            // Pointer events carry live modifier state; prefer them so overlay
            // tracks the real Alt key even if a keyup was missed or delayed.
            if (event && typeof event.altKey === "boolean") {
                return Boolean(event.altKey);
            }
            return Boolean(isAltKey && isAltKey());
        }

        function matrixTransformPoint(matrix, x, y) {
            return {
                x: matrix.a * x + matrix.c * y + matrix.e,
                y: matrix.b * x + matrix.d * y + matrix.f,
            };
        }

        function clientToWorldViaCtm(svg, clientX, clientY) {
            if (!svg) return null;
            const worldGroup = typeof svg.querySelector === "function"
                ? svg.querySelector(".abe-world")
                : null;
            const target = worldGroup || svg;
            if (!target || typeof target.getScreenCTM !== "function") return null;
            const ctm = target.getScreenCTM();
            if (!ctm || typeof ctm.inverse !== "function") return null;
            let inverse = null;
            try {
                inverse = ctm.inverse();
            } catch (err) {
                return null;
            }
            if (!inverse) return null;

            const root = (svg.ownerSVGElement && svg.ownerSVGElement.createSVGPoint)
                ? svg.ownerSVGElement
                : (typeof svg.createSVGPoint === "function" ? svg : null);
            if (root) {
                try {
                    const point = root.createSVGPoint();
                    point.x = clientX;
                    point.y = clientY;
                    const local = point.matrixTransform(inverse);
                    if (local && Number.isFinite(local.x) && Number.isFinite(local.y)) {
                        return { x: local.x, y: local.y };
                    }
                } catch (err) {
                    /* fall through to manual multiply */
                }
            }
            const local = matrixTransformPoint(inverse, clientX, clientY);
            if (!Number.isFinite(local.x) || !Number.isFinite(local.y)) return null;
            return local;
        }

        function clientToWorldViaMetrics(svg, metrics, clientX, clientY) {
            if (!svg || !metrics || !(metrics.width > 0) || !(metrics.height > 0)) return null;
            if (typeof svg.getBoundingClientRect !== "function") return null;
            const rect = svg.getBoundingClientRect();
            if (!(rect.width > 0) || !(rect.height > 0)) return null;

            const scale = Math.max(Number(metrics.scale) || 1, 1e-9);
            const pad = metrics.pad != null ? Number(metrics.pad) || 0 : 0;
            const minX = Number(metrics.minX) || 0;
            const minY = Number(metrics.minY) || 0;
            const attrW = Number(svg.getAttribute && svg.getAttribute("width"));
            const attrH = Number(svg.getAttribute && svg.getAttribute("height"));
            const contentW = Number(metrics.contentWidth) > 0
                ? Number(metrics.contentWidth)
                : (attrW > 0 ? attrW : rect.width);
            const contentH = Number(metrics.contentHeight) > 0
                ? Number(metrics.contentHeight)
                : (attrH > 0 ? attrH : rect.height);

            const nx = (clientX - rect.left) / rect.width;
            const ny = (clientY - rect.top) / rect.height;
            // Match canvas_renderer viewBox + .abe-world translate(pad - min*scale) scale(scale).
            const svgX = minX * scale + nx * contentW;
            const svgY = minY * scale + ny * contentH;
            return {
                x: (svgX - pad) / scale + minX,
                y: (svgY - pad) / scale + minY,
            };
        }

        function clientToWorld(clientX, clientY) {
            const svg = getSvgEl && getSvgEl();
            if (!svg) return null;
            const viaCtm = clientToWorldViaCtm(svg, clientX, clientY);
            if (viaCtm) return viaCtm;
            const metrics = getWorldMetrics && getWorldMetrics();
            return clientToWorldViaMetrics(svg, metrics, clientX, clientY);
        }

        function publish() {
            if (!onOverlay) return;
            const lines = [];
            if (toolGesture && toolGesture.preview) lines.push(toolGesture.preview);
            else if (committedLine) lines.push(committedLine);
            (altOverlay || []).forEach((row) => lines.push(row));
            onOverlay(lines);
        }

        function invalidateAltCache() {
            altCache = null;
        }

        function clearAltOverlay() {
            altOverlay = [];
            invalidateAltCache();
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
            invalidateAltCache();
            publish();
        }

        function geometryRevision(session, selectedKey) {
            if (!session) return "";
            const pieces = session.pieces || {};
            const boards = session.boards || {};
            const selected = pieces[selectedKey];
            const sheetNo = selected ? selected.sheet_no : null;
            const parts = [
                `k:${selectedKey}`,
                `kerf:${session.kerf_mm}`,
            ];
            Object.keys(boards).forEach((key) => {
                const board = boards[key];
                if (!board) return;
                if (sheetNo != null && Number(board.sheet_no) !== Number(sheetNo)) return;
                parts.push([
                    "b",
                    key,
                    board.origin_x_mm,
                    board.origin_y_mm,
                    board.trim_x_mm,
                    board.trim_y_mm,
                    board.width_mm,
                    board.height_mm,
                    board.usable_width_mm,
                    board.usable_length_mm,
                ].join(":"));
            });
            Object.keys(pieces).forEach((key) => {
                const piece = pieces[key];
                if (!piece) return;
                if (sheetNo != null && Number(piece.sheet_no) !== Number(sheetNo)) return;
                const outlineLen = Array.isArray(piece.outline_mm) ? piece.outline_mm.length : 0;
                parts.push([
                    "p",
                    key,
                    piece.distribution,
                    piece.local_x_mm,
                    piece.local_y_mm,
                    piece.rotation_deg,
                    piece.flip_h ? 1 : 0,
                    piece.flip_v ? 1 : 0,
                    outlineLen,
                    piece.outline_mm && piece.outline_mm[0] ? piece.outline_mm[0][0] : "",
                    piece.outline_mm && piece.outline_mm[0] ? piece.outline_mm[0][1] : "",
                ].join(":"));
            });
            return parts.join("|");
        }

        function refreshAltInspection(clientX, clientY, event) {
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
            if (!altActive(event)) {
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

            const world = clientX != null
                ? clientToWorld(clientX, clientY)
                : (lastPointer ? { x: lastPointer[0], y: lastPointer[1] } : null);
            let hoverKey = null;
            if (world) {
                lastPointer = [world.x, world.y];
                hoverKey = MG.hitTestPieceKey(snap.session, [world.x, world.y], selected.sheet_no);
                if (hoverKey === selectedKey) hoverKey = null;
            }

            const revision = geometryRevision(snap.session, selectedKey);
            const cacheKey = `${selectedKey}::${hoverKey || ""}::${revision}`;
            if (altCache && altCache.key === cacheKey) {
                // Same hover target and geometry: keep the published overlay as-is.
                return;
            }

            geometryComputeCount += 1;
            if (hoverKey) {
                const between = MG.shortestClearanceBetweenPieces(snap.session, selectedKey, hoverKey);
                altOverlay = between
                    ? [{
                        ...between,
                        label: MG.formatDistanceMm(between.distance),
                        style: "alt",
                    }]
                    : [];
            } else {
                altOverlay = MG.edgeClearances(snap.session, selectedKey).map((row) => ({
                    ...row,
                    label: MG.formatDistanceMm(row.distance),
                    style: "alt",
                }));
            }
            altCache = { key: cacheKey, lines: altOverlay.slice() };
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
            invalidateAltCache();
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
            refreshAltInspection(event.clientX, event.clientY, event);
        }

        function onPointerUp(event) {
            if (!toolGesture) {
                refreshAltInspection(
                    event && event.clientX,
                    event && event.clientY,
                    event
                );
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

        function getGeometryComputeCount() {
            return geometryComputeCount;
        }

        function resetGeometryComputeCount() {
            geometryComputeCount = 0;
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
            getGeometryComputeCount,
            resetGeometryComputeCount,
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createMeasureInteraction = createMeasureInteraction;
})();
