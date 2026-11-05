(() => {
    "use strict";

    const ALT_CACHE_MAX_ENTRIES = 32;

    function createMeasureInteraction(options) {
        const {
            store,
            getSvgEl,
            getWorldMetrics,
            isAltKey,
            isPanKey,
            isMeasureToolActive,
            isDragActive,
            onOverlay,
            onRejected,
        } = options || {};

        let toolGesture = null;
        let committedLine = null;
        let altOverlay = [];
        let lastPointer = null;
        let altCacheSession = null;
        let altCacheEntries = new Map();
        let publishedCacheKey = null;
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
            const metrics = getWorldMetrics && getWorldMetrics();
            const CanvasRenderer = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.CanvasRenderer;
            if (CanvasRenderer && typeof CanvasRenderer.clientToWorld === "function") {
                return CanvasRenderer.clientToWorld(svg, metrics, clientX, clientY);
            }
            const viaCtm = clientToWorldViaCtm(svg, clientX, clientY);
            if (viaCtm) return viaCtm;
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
            altCacheSession = null;
            altCacheEntries = new Map();
            publishedCacheKey = null;
        }

        function hideAltOverlay() {
            if (!(altOverlay && altOverlay.length) && publishedCacheKey == null) {
                return;
            }
            altOverlay = [];
            publishedCacheKey = null;
            publish();
        }

        function clearAltOverlay() {
            // Hide displayed Alt lines; keep multi-target cache for the current session.
            hideAltOverlay();
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
            publishedCacheKey = null;
            invalidateAltCache();
            publish();
        }

        function hasAltOverlay() {
            return Boolean(altOverlay && altOverlay.length);
        }

        function ensureCacheScope(session) {
            // History/store replace the session document object on every geometry
            // commit, undo, redo, replace, and reload — object identity is the revision.
            if (altCacheSession !== session) {
                altCacheEntries = new Map();
                altCacheSession = session;
                publishedCacheKey = null;
            }
        }

        function cacheEntryKey(selectedKey, hoverKey) {
            if (hoverKey) return `${selectedKey}::piece::${hoverKey}`;
            return `${selectedKey}::edge`;
        }

        function readCache(entryKey) {
            if (!altCacheEntries.has(entryKey)) return null;
            const lines = altCacheEntries.get(entryKey);
            // Refresh LRU order.
            altCacheEntries.delete(entryKey);
            altCacheEntries.set(entryKey, lines);
            return lines;
        }

        function writeCache(entryKey, lines) {
            if (altCacheEntries.has(entryKey)) altCacheEntries.delete(entryKey);
            altCacheEntries.set(entryKey, lines.slice());
            while (altCacheEntries.size > ALT_CACHE_MAX_ENTRIES) {
                const oldest = altCacheEntries.keys().next().value;
                altCacheEntries.delete(oldest);
            }
        }

        function presentGeomLines(MG, session, geomLines, world) {
            const rows = Array.isArray(geomLines) ? geomLines : [];
            if (!world || !MG || typeof MG.presentPieceClearanceNearPointer !== "function") {
                return rows.map((row) => ({ ...row }));
            }
            const pointer = [world.x, world.y];
            return rows.map((row) => {
                if (!row || row.kind !== "piece") return { ...row };
                const presented = MG.presentPieceClearanceNearPointer(row, pointer, session);
                return presented ? { ...presented } : { ...row };
            });
        }

        function presentationFingerprint(lines) {
            return (Array.isArray(lines) ? lines : []).map((row) => {
                if (!row) return "";
                return [
                    row.kind || "",
                    row.distance,
                    row.start && row.start[0],
                    row.start && row.start[1],
                    row.end && row.end[0],
                    row.end && row.end[1],
                    row.label || "",
                ].join(":");
            }).join("|");
        }

        function publishPresented(entryKey, presented) {
            altOverlay = presented.slice();
            publishedCacheKey = entryKey;
            publish();
        }

        function refreshAltInspection(clientX, clientY, event) {
            const MG = geometry();
            const snap = store && store.snapshot();
            if (!MG || !snap || !snap.session) {
                hideAltOverlay();
                invalidateAltCache();
                return;
            }
            // Measure tool mode owns the pointer; Alt spacing stays off.
            if (isMeasureToolActive && isMeasureToolActive()) {
                hideAltOverlay();
                return;
            }
            // Drag/rotate owns Alt for snap-bypass — do not compete with spacing overlay.
            if (isDragActive && isDragActive()) {
                hideAltOverlay();
                return;
            }
            if (!altActive(event)) {
                hideAltOverlay();
                return;
            }
            const selectedKey = snap.selectedPieceKey
                || (Array.isArray(snap.selectedPieceKeys) && snap.selectedPieceKeys.length === 1
                    ? snap.selectedPieceKeys[0]
                    : null);
            if (!selectedKey || (Array.isArray(snap.selectedPieceKeys) && snap.selectedPieceKeys.length > 1)) {
                hideAltOverlay();
                return;
            }
            const selected = snap.session.pieces[selectedKey];
            if (!selected || selected.distribution === "excluded") {
                hideAltOverlay();
                return;
            }

            ensureCacheScope(snap.session);

            const world = clientX != null
                ? clientToWorld(clientX, clientY)
                : (lastPointer ? { x: lastPointer[0], y: lastPointer[1] } : null);
            let hoverKey = null;
            if (world) {
                lastPointer = [world.x, world.y];
                hoverKey = MG.hitTestPieceKey(snap.session, [world.x, world.y], selected.sheet_no);
                if (hoverKey === selectedKey) hoverKey = null;
            }

            const entryKey = cacheEntryKey(selectedKey, hoverKey);
            let geomLines = readCache(entryKey);
            if (!geomLines) {
                geometryComputeCount += 1;
                if (hoverKey) {
                    const between = MG.shortestClearanceBetweenPieces(snap.session, selectedKey, hoverKey);
                    geomLines = between
                        ? [{
                            ...between,
                            label: MG.formatDistanceMm(between.distance),
                            style: "alt",
                        }]
                        : [];
                } else {
                    geomLines = MG.edgeClearances(snap.session, selectedKey).map((row) => ({
                        ...row,
                        label: MG.formatDistanceMm(row.distance),
                        style: "alt",
                    }));
                }
                writeCache(entryKey, geomLines);
            }

            const presented = presentGeomLines(MG, snap.session, geomLines, world);
            if (
                publishedCacheKey === entryKey
                && presentationFingerprint(altOverlay) === presentationFingerprint(presented)
            ) {
                return;
            }
            publishPresented(entryKey, presented);
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
            publishedCacheKey = null;
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

        function getAltCacheSize() {
            return altCacheEntries.size;
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
            hideAltOverlay,
            hasAltOverlay,
            refreshAltInspection,
            isToolGestureActive,
            clientToWorld,
            getGeometryComputeCount,
            resetGeometryComputeCount,
            getAltCacheSize,
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createMeasureInteraction = createMeasureInteraction;
})();
