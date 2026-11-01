(() => {
    "use strict";

    function createStore(initialPayload) {
        const projection = (initialPayload && initialPayload.projection) || {};
        const layers = Array.isArray(projection.layers) ? projection.layers : [];
        const layerVisibility = {};
        layers.forEach((layer) => {
            const key = String(layer.match_key || "").trim();
            if (!key) return;
            layerVisibility[key] = true;
        });

        const state = {
            payload: initialPayload || null,
            layerVisibility,
            selectedPieceId: null,
            selectedPieceKey: null,
            selectedSheetNo: null,
            selectedElementId: null,
            expandedSheets: {},
            viewport: {
                scale: 0,
                scrollX: 0,
                scrollY: 0,
                columns: null,
                opened: false,
                userAdjusted: false,
                fitted: false,
                cameraToken: 0,
            },
            sidebarSplit: 0.45,
            magnetEnabled: true,
            session: null,
            history: null,
            dragPreview: null,
            dropMessage: null,
            canUndo: false,
            canRedo: false,
        };

        (projection.sheets || []).forEach((sheet) => {
            state.expandedSheets[String(sheet.sheet_no)] = true;
        });

        const listeners = new Set();

        function syncHistoryFlags() {
            if (!state.history) {
                state.canUndo = false;
                state.canRedo = false;
                return;
            }
            const hist = state.history.state();
            state.canUndo = hist.canUndo;
            state.canRedo = hist.canRedo;
            state.session = hist.document;
        }

        function snapshot() {
            return {
                payload: state.payload,
                projection: (state.payload && state.payload.projection) || {},
                layerVisibility: { ...state.layerVisibility },
                selectedPieceId: state.selectedPieceId,
                selectedPieceKey: state.selectedPieceKey,
                selectedSheetNo: state.selectedSheetNo,
                selectedElementId: state.selectedElementId,
                expandedSheets: { ...state.expandedSheets },
                viewport: { ...state.viewport },
                sidebarSplit: state.sidebarSplit,
                magnetEnabled: state.magnetEnabled !== false,
                session: state.session,
                dragPreview: state.dragPreview,
                dropMessage: state.dropMessage,
                canUndo: state.canUndo,
                canRedo: state.canRedo,
            };
        }

        function emit() {
            const view = snapshot();
            listeners.forEach((listener) => listener(view));
        }

        function subscribe(listener) {
            listeners.add(listener);
            return () => listeners.delete(listener);
        }

        function attachSession(sessionDocument, historyApi) {
            state.session = sessionDocument;
            state.history = historyApi;
            syncHistoryFlags();
            emit();
        }

        function replaceWorkingSession(nextDocument) {
            if (!state.history || typeof state.history.replacePresent !== "function") {
                state.session = nextDocument;
                emit();
                return;
            }
            state.history.replacePresent(nextDocument);
            syncHistoryFlags();
            emit();
        }

        function setMagnetEnabled(enabled) {
            // Session display preference only — never enters History.
            state.magnetEnabled = Boolean(enabled);
            emit();
        }

        function toggleMagnet() {
            setMagnetEnabled(!state.magnetEnabled);
        }

        function setDragPreview(preview) {
            // Preview updates must not rebuild the sidebar/SVG tree on every
            // pointermove. Canvas patches the ghost through onPreview instead.
            state.dragPreview = preview;
        }

        function setDropMessage(message) {
            state.dropMessage = message || null;
            emit();
        }

        function commitSession(nextDocument) {
            if (!state.history) return;
            state.history.commit(nextDocument);
            syncHistoryFlags();
            state.dragPreview = null;
            emit();
        }

        function undo() {
            if (!state.history) return;
            state.history.undo();
            syncHistoryFlags();
            emit();
        }

        function redo() {
            if (!state.history) return;
            state.history.redo();
            syncHistoryFlags();
            emit();
        }

        function restoreEntry() {
            if (!state.history) return;
            state.history.restoreEntry();
            syncHistoryFlags();
            emit();
        }

        function setLayerVisible(matchKey, visible) {
            const key = String(matchKey || "").trim();
            if (!key) return;
            state.layerVisibility[key] = Boolean(visible);
            emit();
        }

        function setAllLayersVisible(visible) {
            Object.keys(state.layerVisibility).forEach((key) => {
                state.layerVisibility[key] = Boolean(visible);
            });
            emit();
        }

        function showOnlyLayer(matchKey) {
            const wanted = String(matchKey || "").trim();
            Object.keys(state.layerVisibility).forEach((key) => {
                state.layerVisibility[key] = key === wanted;
            });
            emit();
        }

        function selectPiece(pieceId, options) {
            const opts = options || {};
            state.selectedPieceId = pieceId == null || pieceId === "" ? null : Number(pieceId);
            state.selectedPieceKey = opts.pieceKey || null;
            if (opts.sheetNo != null) state.selectedSheetNo = Number(opts.sheetNo);
            if (opts.elementId !== undefined) state.selectedElementId = opts.elementId;
            if (opts.expandSheet && state.selectedSheetNo != null) {
                state.expandedSheets[String(state.selectedSheetNo)] = true;
            }
            emit();
        }

        function selectSheet(sheetNo) {
            state.selectedSheetNo = sheetNo == null ? null : Number(sheetNo);
            state.selectedPieceId = null;
            state.selectedPieceKey = null;
            state.selectedElementId = null;
            if (state.selectedSheetNo != null) {
                state.expandedSheets[String(state.selectedSheetNo)] = true;
            }
            emit();
        }

        function toggleSheetExpanded(sheetNo) {
            const key = String(sheetNo);
            state.expandedSheets[key] = !state.expandedSheets[key];
            emit();
        }

        function setViewport(next) {
            state.viewport = { ...state.viewport, ...next };
            emit();
        }

        function setSidebarSplit(ratio, sidebarHeight) {
            const value = Number(ratio);
            if (!Number.isFinite(value)) return;
            const height = Number(sidebarHeight);
            const minSection = 120;
            const handle = 8;
            if (height > minSection * 2 + handle) {
                const minRatio = minSection / height;
                const maxRatio = (height - minSection - handle) / height;
                state.sidebarSplit = Math.min(maxRatio, Math.max(minRatio, value));
            } else {
                state.sidebarSplit = Math.min(0.7, Math.max(0.3, value));
            }
            emit();
        }

        function isLayerVisible(matchKey) {
            const key = String(matchKey || "").trim();
            if (!key) return true;
            return state.layerVisibility[key] !== false;
        }

        return {
            subscribe,
            snapshot,
            attachSession,
            replaceWorkingSession,
            setMagnetEnabled,
            toggleMagnet,
            setDragPreview,
            setDropMessage,
            commitSession,
            undo,
            redo,
            restoreEntry,
            setLayerVisible,
            setAllLayersVisible,
            showOnlyLayer,
            selectPiece,
            selectSheet,
            toggleSheetExpanded,
            setViewport,
            setSidebarSplit,
            isLayerVisible,
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createStore = createStore;
})();
