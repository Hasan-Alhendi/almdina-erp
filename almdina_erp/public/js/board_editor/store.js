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
            selectedPieceKeys: [],
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
            measureToolActive: false,
            // Visual-only edge-band preference for this open editor session.
            // Never enters History / draft fingerprint / manufacturing data.
            showEdgeBands: false,
            pieceEdgeBandOverrides: {},
            session: null,
            history: null,
            dragPreview: null,
            dropMessage: null,
            canUndo: false,
            canRedo: false,
            draftVersion: 0,
            savedFingerprint: "",
            saveState: "clean",
            saveConflictCode: null,
            saveInFlight: false,
            canSaveLayout: false,
            sourceOnly: false,
            review: null,
            reviewSerial: 0,
            reviewInFlight: false,
            reviewStale: false,
            createPlanInFlight: false,
            lastCreatedPlanName: "",
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
                selectedPieceKeys: state.selectedPieceKeys.slice(),
                selectedSheetNo: state.selectedSheetNo,
                selectedElementId: state.selectedElementId,
                expandedSheets: { ...state.expandedSheets },
                viewport: { ...state.viewport },
                sidebarSplit: state.sidebarSplit,
                magnetEnabled: state.magnetEnabled !== false,
                measureToolActive: state.measureToolActive === true,
                showEdgeBands: state.showEdgeBands === true,
                pieceEdgeBandOverrides: { ...state.pieceEdgeBandOverrides },
                session: state.session,
                dragPreview: state.dragPreview,
                dropMessage: state.dropMessage,
                canUndo: state.canUndo,
                canRedo: state.canRedo,
                draftVersion: state.draftVersion,
                savedFingerprint: state.savedFingerprint,
                saveInFlight: state.saveInFlight,
                canSaveLayout: state.canSaveLayout,
                sourceOnly: state.sourceOnly,
                distributionDirty: distributionDirty(),
                saveState: derivedSaveState(),
                saveConflictCode: state.saveConflictCode,
                review: state.review,
                reviewSerial: state.reviewSerial,
                reviewInFlight: state.reviewInFlight,
                reviewStale: state.reviewStale,
                createPlanInFlight: state.createPlanInFlight,
                lastCreatedPlanName: state.lastCreatedPlanName,
            };
        }

        function sessionFingerprint() {
            const api = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.SessionDocument;
            if (!api || !state.session) return "";
            return api.distributionFingerprint(state.session);
        }

        function distributionDirty() {
            if (!state.session || !state.savedFingerprint) return false;
            return sessionFingerprint() !== state.savedFingerprint;
        }

        function derivedSaveState() {
            if (state.saveInFlight) return "saving";
            if (!distributionDirty()) return state.draftVersion > 0 ? "saved" : "clean";
            if (state.saveState === "failed" || state.saveState === "conflict") return state.saveState;
            return "dirty";
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

        function setMeasureToolActive(enabled) {
            // Transient UI mode only — never enters History or draft layout.
            state.measureToolActive = Boolean(enabled);
            emit();
        }

        function toggleMeasureTool() {
            setMeasureToolActive(!state.measureToolActive);
        }

        function edgesPayloadHasBands(edges) {
            if (!edges || typeof edges !== "object") return false;
            if (edges.edge_width_top || edges.edge_width_bottom
                || edges.edge_long_left || edges.edge_long_right
                || edges.edge_break || edges.edge_break_only) {
                return true;
            }
            return ["top", "bottom", "left", "right"].some((side) => (
                edges[side] && (edges[side].selected || edges[side].custom)
            ));
        }

        function displayEdgesForPieceKey(pieceKey) {
            const key = String(pieceKey || "").trim();
            const sessionPiece = key && state.session && state.session.pieces
                ? state.session.pieces[key]
                : null;
            if (!sessionPiece || sessionPiece.distribution === "excluded") return null;
            if (edgesPayloadHasBands(sessionPiece.display_edges)) return sessionPiece.display_edges;
            const projection = (state.payload && state.payload.projection) || {};
            const instanceId = sessionPiece.piece_instance_id;
            const pieceId = sessionPiece.piece_id;
            const fromPieces = (projection.pieces || []).find((row) => (
                (instanceId && String(row.piece_instance_id) === String(instanceId))
                || (!instanceId && Number(row.piece_id) === Number(pieceId))
            ));
            if (edgesPayloadHasBands(fromPieces && fromPieces.display_edges)) {
                return fromPieces.display_edges;
            }
            const fromElement = (projection.elements || []).find((element) => {
                if (!(element && (element.kind === "placement_rect" || element.kind === "finished_outline"))) {
                    return false;
                }
                if (instanceId && String(element.piece_instance_id) === String(instanceId)) return true;
                return !instanceId && Number(element.piece_id) === Number(pieceId);
            });
            const payloadEdges = fromElement && fromElement.payload && fromElement.payload.display_edges;
            return edgesPayloadHasBands(payloadEdges) ? payloadEdges : null;
        }

        function pieceHasEdgeBands(pieceOrKey) {
            if (pieceOrKey && typeof pieceOrKey === "object") {
                if (pieceOrKey.distribution === "excluded") return false;
                if (edgesPayloadHasBands(pieceOrKey.display_edges)) return true;
                if (pieceOrKey.piece_key) return Boolean(displayEdgesForPieceKey(pieceOrKey.piece_key));
                return false;
            }
            return Boolean(displayEdgesForPieceKey(pieceOrKey));
        }

        function isPieceEdgeBandVisible(pieceKey) {
            const key = String(pieceKey || "").trim();
            if (key && Object.prototype.hasOwnProperty.call(state.pieceEdgeBandOverrides, key)) {
                return Boolean(state.pieceEdgeBandOverrides[key]);
            }
            return state.showEdgeBands === true;
        }

        function edgeBandEligibleKeys() {
            const pieces = (state.session && state.session.pieces) || {};
            return Object.keys(pieces).filter((key) => Boolean(displayEdgesForPieceKey(key)));
        }

        function edgeBandGlobalUiState() {
            const keys = edgeBandEligibleKeys();
            if (!keys.length) {
                return {
                    checked: state.showEdgeBands === true,
                    indeterminate: false,
                };
            }
            let visible = 0;
            keys.forEach((key) => {
                if (isPieceEdgeBandVisible(key)) visible += 1;
            });
            if (visible === 0) return { checked: false, indeterminate: false };
            if (visible === keys.length) return { checked: true, indeterminate: false };
            return { checked: false, indeterminate: true };
        }

        function setShowEdgeBands(visible) {
            // Explicit global change resets every per-piece exception.
            state.showEdgeBands = Boolean(visible);
            state.pieceEdgeBandOverrides = {};
            emit();
        }

        function setPieceEdgeBandVisible(pieceKey, visible) {
            const key = String(pieceKey || "").trim();
            if (!key) return;
            state.pieceEdgeBandOverrides[key] = Boolean(visible);
            emit();
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

        function invalidateReview() {
            state.reviewSerial += 1;
            if (state.review || state.reviewInFlight) state.reviewStale = true;
            state.review = null;
            state.reviewInFlight = false;
        }

        function commitSession(nextDocument) {
            if (!state.history) return;
            const before = sessionFingerprint();
            state.history.commit(nextDocument);
            syncHistoryFlags();
            state.dragPreview = null;
            if (sessionFingerprint() !== before) invalidateReview();
            emit();
        }

        function undo() {
            if (!state.history) return;
            state.history.undo();
            syncHistoryFlags();
            invalidateReview();
            emit();
        }

        function redo() {
            if (!state.history) return;
            state.history.redo();
            syncHistoryFlags();
            invalidateReview();
            emit();
        }

        function restoreEntry() {
            if (!state.history) return;
            state.history.restoreEntry();
            syncHistoryFlags();
            invalidateReview();
            emit();
        }

        function noteDraftBaseline(baseline) {
            const next = baseline || {};
            state.draftVersion = Number(next.draftVersion) || 0;
            state.savedFingerprint = String(next.savedFingerprint || "");
            state.canSaveLayout = Boolean(next.canSaveLayout);
            state.sourceOnly = Boolean(next.sourceOnly);
            state.saveInFlight = false;
            state.saveState = "clean";
            emit();
        }

        function beginDraftSave() {
            if (state.saveInFlight || !state.canSaveLayout) return false;
            state.saveInFlight = true;
            state.saveState = "saving";
            state.saveConflictCode = null;
            emit();
            return true;
        }

        function settleDraftSave(sentFingerprint, response) {
            const api = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.SessionDocument;
            const settled = api
                ? api.settleDraftSave(snapshot(), sentFingerprint, response)
                : { saveState: "failed", saveInFlight: false, saveConflictCode: null };
            state.draftVersion = Number(settled.draftVersion) || 0;
            state.savedFingerprint = String(settled.savedFingerprint || "");
            state.saveState = settled.saveState || "failed";
            state.saveConflictCode = settled.saveConflictCode || null;
            state.saveInFlight = false;
            emit();
        }

        function beginReview() {
            if (state.reviewInFlight || !state.session) return null;
            state.reviewSerial += 1;
            state.reviewInFlight = true;
            state.reviewStale = false;
            const request = {
                serial: state.reviewSerial,
                fingerprint: sessionFingerprint(),
                draftVersion: state.draftVersion,
            };
            emit();
            return request;
        }

        function settleReview(request, response) {
            const api = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.SessionDocument;
            const settled = api
                ? api.settleReview(snapshot(), request, response)
                : { ignored: true, failed: false, review: state.review };
            state.reviewInFlight = false;
            if (!settled.ignored && !settled.failed) {
                state.review = settled.review;
                state.reviewStale = false;
            }
            emit();
            return settled;
        }

        function beginCreatePlan() {
            if (state.createPlanInFlight || !state.session || distributionDirty()) return null;
            if (!(Number(state.draftVersion) > 0)) return null;
            state.createPlanInFlight = true;
            const request = {
                draftVersion: state.draftVersion,
                fingerprint: sessionFingerprint(),
                requestId: (
                    (typeof crypto !== "undefined" && crypto.randomUUID)
                        ? crypto.randomUUID()
                        : `abe-create-${Date.now()}-${Math.random().toString(16).slice(2)}`
                ).slice(0, 64),
            };
            emit();
            return request;
        }

        function settleCreatePlan(response) {
            state.createPlanInFlight = false;
            if (response && response.ok && response.plan_name) {
                state.lastCreatedPlanName = String(response.plan_name || "");
            }
            emit();
            return response || null;
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

        function syncPrimaryPiece() {
            const keys = state.selectedPieceKeys;
            state.selectedPieceKey = keys.length ? keys[keys.length - 1] : null;
            if (!state.selectedPieceKey) {
                state.selectedPieceId = null;
                return;
            }
            const piece = state.session && state.session.pieces[state.selectedPieceKey];
            if (piece) state.selectedPieceId = piece.piece_id;
        }

        function selectPiece(pieceId, options) {
            const opts = options || {};
            if (pieceId == null || pieceId === "") {
                state.selectedPieceKeys = [];
                state.selectedPieceId = null;
                state.selectedPieceKey = null;
                if (opts.elementId !== undefined) state.selectedElementId = opts.elementId;
                emit();
                return;
            }
            const key = opts.pieceKey || null;
            if (opts.mode === "toggle" && key) {
                const next = state.selectedPieceKeys.filter((item) => item !== key);
                if (next.length === state.selectedPieceKeys.length) next.push(key);
                state.selectedPieceKeys = next;
                state.selectedSheetNo = null;
            } else {
                state.selectedPieceId = Number(pieceId);
                state.selectedPieceKeys = key ? [key] : [];
                state.selectedPieceKey = key;
                if (opts.sheetNo != null) state.selectedSheetNo = Number(opts.sheetNo);
            }
            if (opts.elementId !== undefined) state.selectedElementId = opts.elementId;
            if (opts.expandSheet && opts.sheetNo != null) {
                state.expandedSheets[String(opts.sheetNo)] = true;
            }
            syncPrimaryPiece();
            emit();
        }

        function selectSheet(sheetNo) {
            state.selectedSheetNo = sheetNo == null ? null : Number(sheetNo);
            state.selectedPieceId = null;
            state.selectedPieceKey = null;
            state.selectedPieceKeys = [];
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

        function patchViewport(next) {
            // Camera bookkeeping (min/trail/scroll compensation) without a paint cycle.
            state.viewport = { ...state.viewport, ...next };
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
            setMeasureToolActive,
            toggleMeasureTool,
            setShowEdgeBands,
            setPieceEdgeBandVisible,
            isPieceEdgeBandVisible,
            edgeBandGlobalUiState,
            pieceHasEdgeBands,
            setDragPreview,
            setDropMessage,
            commitSession,
            undo,
            redo,
            restoreEntry,
            noteDraftBaseline,
            beginDraftSave,
            settleDraftSave,
            beginReview,
            settleReview,
            beginCreatePlan,
            settleCreatePlan,
            setLayerVisible,
            setAllLayersVisible,
            showOnlyLayer,
            selectPiece,
            selectSheet,
            toggleSheetExpanded,
            setViewport,
            patchViewport,
            setSidebarSplit,
            isLayerVisible,
        };
    }

    function isPieceEdgeBandVisibleInView(storeView, pieceKey) {
        if (!storeView) return false;
        const key = String(pieceKey || "").trim();
        const overrides = storeView.pieceEdgeBandOverrides || {};
        if (key && Object.prototype.hasOwnProperty.call(overrides, key)) {
            return Boolean(overrides[key]);
        }
        return storeView.showEdgeBands === true;
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createStore = createStore;
    window.AlmdinaBoardEditor.isPieceEdgeBandVisibleInView = isPieceEdgeBandVisibleInView;
})();
