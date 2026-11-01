(() => {
    "use strict";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        return replacements === undefined ? __(message) : __(message, replacements);
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") return locale.direction();
        return (frappe.boot && frappe.boot.lang === "ar") ? "rtl" : "ltr";
    }

    function isEditableTarget(target) {
        if (!target || !target.tagName) return false;
        const tag = String(target.tagName).toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return true;
        return Boolean(target.isContentEditable);
    }

    function mount(wrapper) {
        const Api = window.AlmdinaBoardEditor.Api;
        const createStore = window.AlmdinaBoardEditor.createStore;
        const CanvasRenderer = window.AlmdinaBoardEditor.CanvasRenderer;
        const SidebarRenderer = window.AlmdinaBoardEditor.SidebarRenderer;
        const SessionDocument = window.AlmdinaBoardEditor.SessionDocument;
        const History = window.AlmdinaBoardEditor.History;
        const createMoveInteraction = window.AlmdinaBoardEditor.createMoveInteraction;
        const createRotationInteraction = window.AlmdinaBoardEditor.createRotationInteraction;
        const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        const Distribution = window.AlmdinaBoardEditor.Distribution;
        const frontend = window.AlmdinaFrontend;
        const requestGate = frontend && frontend.createLatestRequestGate
            ? frontend.createLatestRequestGate()
            : { begin() { return 1; }, isCurrent() { return true; }, invalidate() {} };
        const lifecycle = frontend && frontend.createLifecycleScope
            ? frontend.createLifecycleScope()
            : { listen() {}, dispose() {} };

        let store = null;
        let unsubscribe = null;
        let suspended = false;
        let generation = 0;
        let main = null;
        let moveInteraction = null;
        let rotationInteraction = null;
        let lastCanvasApi = null;

        function ensureShell() {
            main = wrapper.querySelector(".layout-main-section");
            if (!main) throw new Error("Board editor page scaffold is unavailable");
            return main;
        }

        function renderState(kind, title, detail, actionsHtml) {
            ensureShell().innerHTML = `<div class="almdina-ui alm-page--workbench abe-page" dir="${esc(uiDirection())}">
                <div class="abe-state alm-state is-${esc(kind)}" role="status">
                    <strong>${esc(title)}</strong>
                    <span>${esc(detail || "")}</span>
                    ${actionsHtml || ""}
                </div>
            </div>`;
            syncEditorHeight();
        }

        function backToOrder(orderName) {
            if (!orderName) return;
            frappe.set_route("Form", "Door Cutting Order", orderName);
        }

        function bindStateActions(orderName, context) {
            const shell = ensureShell();
            const back = shell.querySelector(".abe-back");
            if (back) back.onclick = () => backToOrder(orderName);
            const retry = shell.querySelector(".abe-retry");
            if (retry) {
                retry.onclick = () => open(context);
            }
        }

        function recoveryActions() {
            return `<button type="button" class="alm-btn-secondary abe-retry">${esc(translate("Retry"))}</button>
                <button type="button" class="alm-btn-secondary abe-back">${esc(translate("Back to order"))}</button>`;
        }

        function syncEditorHeight() {
            const section = ensureShell();
            const page = section.querySelector(".abe-page");
            if (!page) return 0;
            const top = page.getBoundingClientRect().top;
            if (top < 1) return 0;
            const height = Math.max(320, Math.round(window.innerHeight - top));
            page.style.height = `${height}px`;
            page.style.maxHeight = `${height}px`;
            page.style.overflow = "hidden";
            const pageBody = section.closest(".page-body");
            [section, section.parentElement, pageBody].forEach((node) => {
                if (!node || node === document.body) return;
                node.style.minHeight = "0";
                node.style.overflow = "hidden";
            });
            if (pageBody) {
                const bodyTop = pageBody.getBoundingClientRect().top;
                pageBody.style.height = `${Math.max(0, Math.round(window.innerHeight - bodyTop))}px`;
            }
            return height;
        }

        function stageSize() {
            const stage = ensureShell().querySelector("[data-abe-stage]");
            return {
                width: stage ? stage.clientWidth : 0,
                height: stage ? stage.clientHeight : 0,
            };
        }

        let openPending = false;
        let cameraSerial = 0;
        let appliedCamera = 0;
        let liveScroll = { x: 0, y: 0 };
        let spaceHeld = false;
        let altHeld = false;
        let activeOrderName = "";
        let scrollOwned = false;
        let loadedRevisionToken = "";
        let loadedPlanName = "";
        let freshnessRetryTimer = null;
        let freshnessRetryCount = 0;
        let pendingSourceConflict = null;

        const ACTIVE_JOB = new Set(["queued", "running", "enqueue"]);
        const MAX_FRESHNESS_RETRIES = 8;
        const FRESHNESS_RETRY_MS = 2000;

        function contentRevisionToken(payload) {
            const plan = (payload && payload.plan) || {};
            const freshness = (payload && payload.freshness) || {};
            return String(
                freshness.content_revision_token
                || plan.content_revision_token
                || [
                    plan.name || "",
                    plan.modified || "",
                    plan.revision || "",
                    plan.input_fingerprint || "",
                    freshness.needs_recalculation ? "1" : "0",
                ].join("|")
            );
        }

        function sessionIsDirty() {
            if (!store) return false;
            const view = store.snapshot();
            return Boolean(view.canUndo);
        }

        function clearFreshnessRetry() {
            if (freshnessRetryTimer) {
                window.clearTimeout(freshnessRetryTimer);
                freshnessRetryTimer = null;
            }
            freshnessRetryCount = 0;
        }

        function freshnessBannerHtml(payload) {
            const freshness = (payload && payload.freshness) || {};
            const plan = (payload && payload.plan) || {};
            const job = freshness.background_recalculation || {};
            const jobStatus = String(job.status || "").toLowerCase();
            if (ACTIVE_JOB.has(jobStatus) || freshness.job_active) {
                return `<div class="abe-freshness-banner is-calculating" role="status" data-abe-freshness="calculating">
                    <strong>${esc(translate("Cutting plan recalculation in progress"))}</strong>
                    <span>${esc(translate("This editor still shows the previous plan snapshot. It will refresh when the calculation finishes — without running the optimizer from here."))}</span>
                    <button type="button" class="alm-btn-secondary abe-freshness-retry">${esc(translate("Check again"))}</button>
                </div>`;
            }
            if (String(plan.display_context || "") === "historical") {
                return `<div class="abe-freshness-banner is-historical" role="status" data-abe-freshness="historical">
                    <strong>${esc(translate("Historical cutting plan"))}</strong>
                    <span>${esc(translate("This snapshot is read-only history. Opening it does not change the approved or system plan."))}</span>
                </div>`;
            }
            if (freshness.needs_recalculation || freshness.reflects_current_order === false) {
                return `<div class="abe-freshness-banner is-stale" role="status" data-abe-freshness="stale">
                    <strong>${esc(translate("Cutting plan is out of date"))}</strong>
                    <span>${esc(translate("Order measurements changed after this plan. Recalculate the cutting plan on the order, then reopen the editor. This view is not the new layout."))}</span>
                    <button type="button" class="alm-btn-secondary abe-back">${esc(translate("Back to order"))}</button>
                </div>`;
            }
            return "";
        }

        function bindFreshnessActions(orderName, context) {
            const shell = ensureShell();
            const back = shell.querySelector(".abe-freshness-banner .abe-back");
            if (back) back.onclick = () => backToOrder(orderName);
            const retry = shell.querySelector(".abe-freshness-retry");
            if (retry) {
                retry.onclick = () => open(context, { forceReload: true, acceptSourceChange: true });
            }
        }

        function scheduleFreshnessRetry(context, openGeneration, requestToken) {
            clearFreshnessRetry();
            if (suspended) return;
            freshnessRetryCount = 0;
            const tick = async () => {
                if (isStale(openGeneration, requestToken) || suspended) return;
                freshnessRetryCount += 1;
                try {
                    const status = await Api.recalculationStatus(context.orderName);
                    if (isStale(openGeneration, requestToken) || suspended) return;
                    const jobStatus = String((status && status.status) || "").toLowerCase();
                    if (!ACTIVE_JOB.has(jobStatus)) {
                        open(context, { forceReload: true, acceptSourceChange: true });
                        return;
                    }
                } catch (_error) {
                    // Status read failures stay soft; the banner keeps Check again.
                }
                if (freshnessRetryCount >= MAX_FRESHNESS_RETRIES) return;
                freshnessRetryTimer = window.setTimeout(tick, FRESHNESS_RETRY_MS);
            };
            freshnessRetryTimer = window.setTimeout(tick, FRESHNESS_RETRY_MS);
        }

        function renderSourceConflict(orderName, context, nextToken) {
            pendingSourceConflict = { context, nextToken };
            renderState(
                "warning",
                translate("Plan source changed while editing"),
                translate("Local move/rotate changes are still in this session. Reload to take the updated plan and lose those edits, or go back to the order."),
                `<button type="button" class="alm-btn-secondary abe-accept-reload">${esc(translate("Reload and discard local edits"))}</button>
                <button type="button" class="alm-btn-secondary abe-back">${esc(translate("Back to order"))}</button>`
            );
            const shell = ensureShell();
            const accept = shell.querySelector(".abe-accept-reload");
            if (accept) {
                accept.onclick = () => {
                    pendingSourceConflict = null;
                    open(context, { forceReload: true, acceptSourceChange: true });
                };
            }
            bindStateActions(orderName, context);
        }

        function rememberCamera(partial) {
            cameraSerial += 1;
            liveScroll = {
                x: Number(partial.scrollX) || 0,
                y: Number(partial.scrollY) || 0,
            };
            scrollOwned = Boolean(partial.userAdjusted);
            store.setViewport({ ...partial, cameraToken: cameraSerial });
        }

        function currentLayout(viewportWidth) {
            const sheets = store.snapshot().projection.sheets || [];
            const widths = sheets.map((sheet) => (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10);
            const maxBoard = widths.length ? Math.max(...widths) : 1;
            const saved = store.snapshot().viewport.columns;
            const columns = saved || CanvasRenderer.columnCount(maxBoard, viewportWidth);
            let layout = CanvasRenderer.sheetLayout(sheets, columns);
            const session = store.snapshot().session;
            if (session) layout = CanvasRenderer.mergeSessionLayout(layout, session);
            return layout;
        }

        function syncSessionBoardGrid() {
            if (!store) return;
            const view = store.snapshot();
            if (!view.session) return;
            const size = stageSize();
            const sheets = view.projection.sheets || [];
            const widths = sheets.map((sheet) => (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10);
            const maxBoard = widths.length ? Math.max(...widths) : 1;
            const columns = view.viewport.columns
                || CanvasRenderer.columnCount(maxBoard, size.width || 1);
            const layout = CanvasRenderer.sheetLayout(sheets, columns);
            const next = SessionDocument.relayoutUnmovedBoards(view.session, layout);
            // Layout-only: do not push a history command for unmoved board grid.
            store.replaceWorkingSession(next);
        }

        function applyOpeningCamera() {
            if (!store) return false;
            const size = stageSize();
            if (size.width < 40) return false;
            const sheets = store.snapshot().projection.sheets || [];
            const widths = sheets.map((sheet) => (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10);
            const maxBoard = widths.length ? Math.max(...widths) : 1;
            const columns = CanvasRenderer.columnCount(maxBoard, size.width);
            const scale = CanvasRenderer.openingScale(maxBoard, columns, size.width);
            rememberCamera({
                scale,
                scrollX: 0,
                scrollY: 0,
                columns,
                opened: true,
                userAdjusted: false,
                fitted: false,
            });
            return true;
        }

        function scheduleOpeningCamera() {
            if (openPending || !store) return;
            const view = store.snapshot().viewport;
            if (view.opened || view.userAdjusted || scrollOwned) return;
            openPending = true;
            let remaining = 12;
            const attempt = () => {
                if (!store || suspended) {
                    openPending = false;
                    return;
                }
                const current = store.snapshot().viewport;
                if (current.opened || current.userAdjusted || scrollOwned) {
                    openPending = false;
                    return;
                }
                syncEditorHeight();
                if (applyOpeningCamera()) {
                    openPending = false;
                    return;
                }
                remaining -= 1;
                if (remaining <= 0) {
                    openPending = false;
                    return;
                }
                window.requestAnimationFrame(attempt);
            };
            window.requestAnimationFrame(attempt);
        }

        function fitCurrentBoards() {
            if (!store) return false;
            const size = stageSize();
            const layout = currentLayout(size.width);
            const camera = CanvasRenderer.fitBoards(layout.fitBounds, size.width, size.height);
            if (!camera) return false;
            rememberCamera({
                scale: camera.scale,
                scrollX: 0,
                scrollY: 0,
                columns: layout.columns,
                opened: true,
                userAdjusted: true,
                fitted: true,
            });
            return true;
        }

        function zoomByFactor(factor, client) {
            if (!store || !CanvasRenderer.zoomAroundFocal) return;
            const stage = ensureShell().querySelector("[data-abe-stage]");
            const current = store.snapshot().viewport;
            const scrollX = stage ? Number(stage.scrollLeft) || 0 : liveScroll.x;
            const scrollY = stage ? Number(stage.scrollTop) || 0 : liveScroll.y;
            const rect = stage && stage.getBoundingClientRect
                ? stage.getBoundingClientRect()
                : { left: 0, top: 0, width: stageSize().width, height: stageSize().height };
            const focalX = client ? client.x - rect.left : rect.width / 2;
            const focalY = client ? client.y - rect.top : rect.height / 2;
            const rendered = lastCanvasApi && lastCanvasApi.metrics && lastCanvasApi.metrics.scale;
            const next = CanvasRenderer.zoomAroundFocal({
                scale: Number(current.scale) || rendered || 1,
                scrollX,
                scrollY,
                pad: CanvasRenderer.SCENE_PAD_PX,
            }, { x: focalX, y: focalY }, factor);
            rememberCamera({
                scale: next.scale,
                scrollX: next.scrollX,
                scrollY: next.scrollY,
                columns: current.columns,
                opened: true,
                userAdjusted: true,
                fitted: false,
            });
        }

        function onCanvasWheel(event) {
            if (!store || suspended || !CanvasRenderer.shouldZoomWheel(event)) return;
            let stage = null;
            try {
                stage = ensureShell().querySelector("[data-abe-stage]");
            } catch (err) {
                stage = null;
            }
            if (!stage || !event.target || typeof stage.contains !== "function" || !stage.contains(event.target)) return;
            event.preventDefault();
            const factor = CanvasRenderer.wheelZoomFactor(
                event.deltaY,
                event.deltaMode,
                stage.clientHeight || stageSize().height
            );
            zoomByFactor(factor, { x: event.clientX, y: event.clientY });
        }

        function revealSheet(sheetNo) {
            if (!store || sheetNo == null || sheetNo === "") return;
            const size = stageSize();
            if (size.width < 40 || size.height < 40) return;
            const view = store.snapshot().viewport;
            const layout = currentLayout(size.width);
            const board = layout.positions[String(sheetNo)];
            if (!board) return;
            const scale = Number(view.scale) || 1;
            const pad = 12;
            const x0 = CanvasRenderer.SCENE_PAD_PX + board.originX * scale;
            const y0 = CanvasRenderer.SCENE_PAD_PX + (board.originY - CanvasRenderer.BOARD_TITLE_MM) * scale;
            const x1 = CanvasRenderer.SCENE_PAD_PX + (board.originX + board.widthMm) * scale;
            const y1 = CanvasRenderer.SCENE_PAD_PX + (board.originY + board.heightMm) * scale;
            let scrollX = liveScroll.x;
            let scrollY = liveScroll.y;
            if (x0 < scrollX + pad) scrollX = Math.max(0, x0 - pad);
            else if (x1 > scrollX + size.width - pad) scrollX = Math.max(0, x1 - size.width + pad);
            if (y0 < scrollY + pad) scrollY = Math.max(0, y0 - pad);
            else if (y1 > scrollY + size.height - pad) scrollY = Math.max(0, y1 - size.height + pad);
            rememberCamera({
                scale,
                scrollX,
                scrollY,
                columns: layout.columns,
                opened: true,
                userAdjusted: true,
                fitted: false,
            });
        }

        function ensureSession(payload) {
            const size = stageSize();
            const sheets = (payload.projection && payload.projection.sheets) || [];
            const widths = sheets.map((sheet) => (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10);
            const maxBoard = widths.length ? Math.max(...widths) : 1;
            const columns = CanvasRenderer.columnCount(maxBoard, size.width || 1100);
            const layout = CanvasRenderer.sheetLayout(sheets, columns);
            const session = SessionDocument.buildFromProjection(payload.projection, layout);
            const history = History.create(session);
            store.attachSession(history.get(), history);
        }

        function patchPreview(preview) {
            const host = ensureShell().querySelector("[data-abe-canvas]");
            if (!host) return;
            if (lastCanvasApi && lastCanvasApi.patchDragPreview) {
                lastCanvasApi.patchDragPreview(preview);
            } else {
                CanvasRenderer.patchDragPreview(host, preview);
            }
        }

        function commitRotation(pieceKey, rotationDeg) {
            if (!store || !RotationGeometry) return;
            const view = store.snapshot();
            if (!view.session) return;
            const next = RotationGeometry.applyPieceRotation(view.session, pieceKey, rotationDeg);
            store.commitSession(next);
        }

        function bindMoveInteraction() {
            moveInteraction = createMoveInteraction({
                store,
                getStageEl: () => ensureShell().querySelector("[data-abe-stage]"),
                getSvgEl: () => ensureShell().querySelector(".abe-svg"),
                getWorldMetrics: () => {
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    return (host && host.__abeWorldMetrics) || (lastCanvasApi && lastCanvasApi.metrics) || null;
                },
                isPanKey: () => spaceHeld,
                isAltKey: () => altHeld,
                getScale: () => {
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    const metrics = (host && host.__abeWorldMetrics)
                        || (lastCanvasApi && lastCanvasApi.metrics)
                        || null;
                    return (metrics && metrics.scale) || (store && store.snapshot().viewport.scale) || 1;
                },
                onPreview: patchPreview,
                onDropRejected: (reason) => {
                    if (window.frappe && frappe.show_alert) {
                        frappe.show_alert({ message: translate(reason || "Drop rejected."), indicator: "orange" }, 4);
                    }
                },
                onSelectPiece: (pieceId, elementId, pieceKey, meta) => {
                    if (!store || pieceId == null || pieceId === "") return;
                    const view = store.snapshot();
                    const piece = ((view.projection.pieces) || []).find((row) => Number(row.piece_id) === Number(pieceId));
                    const sessionPiece = view.session
                        && (
                            (pieceKey && view.session.pieces[pieceKey])
                            || Object.values(view.session.pieces || {}).find((row) => Number(row.piece_id) === Number(pieceId))
                        );
                    const resolvedKey = (sessionPiece && sessionPiece.piece_key) || pieceKey;
                    store.selectPiece(pieceId, {
                        mode: meta && meta.shiftKey ? "toggle" : "replace",
                        sheetNo: (sessionPiece && sessionPiece.sheet_no) || (piece && piece.sheet_no),
                        elementId,
                        pieceKey: resolvedKey,
                        expandSheet: true,
                    });
                },
                onSelectSheet: (sheetNo) => {
                    if (!store) return;
                    store.selectSheet(sheetNo);
                    revealSheet(sheetNo);
                },
            });
            rotationInteraction = createRotationInteraction({
                store,
                getStageEl: () => ensureShell().querySelector("[data-abe-stage]"),
                getSvgEl: () => ensureShell().querySelector(".abe-svg"),
                getWorldMetrics: () => {
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    return (host && host.__abeWorldMetrics) || (lastCanvasApi && lastCanvasApi.metrics) || null;
                },
                getScale: () => {
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    const metrics = (host && host.__abeWorldMetrics)
                        || (lastCanvasApi && lastCanvasApi.metrics)
                        || null;
                    return (metrics && metrics.scale) || (store && store.snapshot().viewport.scale) || 1;
                },
                isPanKey: () => spaceHeld,
                onPreview: patchPreview,
                onRejected: (reason) => {
                    if (window.frappe && frappe.show_alert) {
                        frappe.show_alert({ message: translate(reason || "Rotation rejected."), indicator: "orange" }, 4);
                    }
                },
                onCommitted: commitRotation,
            });
        }

        function finishActiveGesture() {
            if (moveInteraction && moveInteraction.cancel) moveInteraction.cancel();
            if (rotationInteraction && rotationInteraction.cancel) rotationInteraction.cancel();
            if (store) {
                store.setDragPreview(null);
                store.setDropMessage("");
            }
        }

        function applyDistribution(command) {
            if (!store || !Distribution || typeof command !== "function") return;
            finishActiveGesture();
            const result = command();
            if (!result || !result.ok) return;
            store.commitSession(result.session);
            store.selectSheet(null);
        }

        function paint() {
            if (!store || suspended) return;
            syncEditorHeight();
            const view = store.snapshot();
            const root = ensureShell().querySelector(".abe-root");
            if (!root) return;
            const sidebar = root.querySelector("[data-abe-sidebar]");
            const canvas = root.querySelector("[data-abe-canvas]");
            SidebarRenderer.render(sidebar, view, {
                setLayerVisible: (key, visible) => store.setLayerVisible(key, visible),
                setAllLayersVisible: (visible) => store.setAllLayersVisible(visible),
                showOnlyLayer: (key) => store.showOnlyLayer(key),
                toggleSheet: (sheetNo) => store.toggleSheetExpanded(sheetNo),
                selectSheet: (sheetNo) => {
                    store.selectSheet(sheetNo);
                    revealSheet(sheetNo);
                },
                returnPiece: (pieceKey) => {
                    if (!store || !Distribution) return;
                    finishActiveGesture();
                    const result = Distribution.returnPieceToStaging(store.snapshot().session, pieceKey);
                    if (!result || !result.ok) return;
                    store.commitSession(result.session);
                    const piece = result.session.pieces[result.piece_key];
                    store.selectSheet(null);
                    if (piece) {
                        store.selectPiece(piece.piece_id, {
                            pieceKey: piece.piece_key,
                            elementId: null,
                        });
                    }
                },
                selectPiece: (pieceId, sheetNo, meta) => {
                    const piece = ((view.projection.pieces) || []).find((row) => Number(row.piece_id) === Number(pieceId));
                    const sessionPiece = view.session
                        && (
                            (meta && meta.pieceKey && view.session.pieces[meta.pieceKey])
                            || Object.values(view.session.pieces || {}).find((row) => Number(row.piece_id) === Number(pieceId))
                        );
                    const targetSheet = sheetNo
                        || (sessionPiece && sessionPiece.sheet_no)
                        || (piece && piece.sheet_no);
                    store.selectPiece(pieceId, {
                        mode: meta && meta.shiftKey ? "toggle" : "replace",
                        sheetNo: targetSheet,
                        pieceKey: (sessionPiece && sessionPiece.piece_key) || (meta && meta.pieceKey),
                        expandSheet: true,
                    });
                    if (!(meta && meta.shiftKey) && targetSheet != null) revealSheet(targetSheet);
                },
                setSidebarSplit: (ratio, sidebarHeight) => store.setSidebarSplit(ratio, sidebarHeight),
            });
            lastCanvasApi = CanvasRenderer.render(canvas, view, {
                selectPiece: (pieceId, elementId) => {
                    const piece = ((view.projection.pieces) || []).find((row) => Number(row.piece_id) === Number(pieceId));
                    const sessionPiece = view.session
                        && Object.values(view.session.pieces || {}).find((row) => Number(row.piece_id) === Number(pieceId));
                    store.selectPiece(pieceId, {
                        sheetNo: (sessionPiece && sessionPiece.sheet_no) || (piece && piece.sheet_no),
                        elementId,
                        pieceKey: sessionPiece && sessionPiece.piece_key,
                        expandSheet: true,
                    });
                },
                selectSheet: (sheetNo) => store.selectSheet(sheetNo),
                clearSelection: () => {
                    if (!store) return;
                    store.selectPiece(null, { pieceKey: null, elementId: null });
                },
                toggleMagnet: () => {
                    store.toggleMagnet();
                    if (moveInteraction && moveInteraction.refreshPreviewFromPointer) {
                        moveInteraction.refreshPreviewFromPointer();
                    }
                },
                undo: () => store.undo(),
                redo: () => store.redo(),
                restoreEntry: () => store.restoreEntry(),
                removePiece: (pieceKey) => applyDistribution(() => {
                    const view = store.snapshot();
                    const key = pieceKey || view.selectedPieceKey;
                    return Distribution.excludePiece(view.session, key);
                }),
                removeBoard: (sheetNo) => applyDistribution(() => {
                    const view = store.snapshot();
                    return Distribution.removeBoard(view.session, sheetNo == null ? view.selectedSheetNo : sheetNo);
                }),
                beginPieceGesture: (pieceKey, event, meta) => {
                    if (rotationInteraction && rotationInteraction.isActive()) return false;
                    return moveInteraction && moveInteraction.beginPieceGesture(pieceKey, event, meta);
                },
                beginBoardGesture: (sheetNo, event) => (
                    moveInteraction && moveInteraction.beginBoardGesture(sheetNo, event)
                ),
                beginRotateGesture: (pieceKey, event) => {
                    if (moveInteraction && moveInteraction.onPanIntent) moveInteraction.onPanIntent();
                    return rotationInteraction && rotationInteraction.beginHandleGesture(pieceKey, event);
                },
                applyAngle: (pieceKey, value) => (
                    rotationInteraction && rotationInteraction.applyNumericAngle(pieceKey, value)
                ),
                onStagePointerMove: (event) => {
                    if (rotationInteraction && rotationInteraction.isActive()) {
                        rotationInteraction.onPointerMove(event);
                        return;
                    }
                    if (moveInteraction) moveInteraction.onPointerMove(event);
                },
                onStagePointerUp: (event) => {
                    if (rotationInteraction && rotationInteraction.isActive()) {
                        rotationInteraction.onPointerUp(event);
                        return;
                    }
                    if (moveInteraction) moveInteraction.onPointerUp(event);
                },
                onStagePointerCancel: (event) => {
                    if (rotationInteraction) rotationInteraction.onPointerCancel(event);
                    if (moveInteraction) moveInteraction.onPointerCancel(event);
                },
                onPanIntent: () => {
                    if (rotationInteraction) rotationInteraction.cancel();
                    if (moveInteraction) moveInteraction.onPanIntent();
                },
                consumeClickSuppression: () => (
                    moveInteraction ? moveInteraction.consumeClickSuppression() : false
                ),
                zoom: (factor) => zoomByFactor(factor, null),
                onBack: () => backToOrder(activeOrderName),
                readScroll: () => liveScroll,
                onScroll: (x, y) => {
                    liveScroll = { x: Number(x) || 0, y: Number(y) || 0 };
                    if (liveScroll.x > 1 || liveScroll.y > 1) scrollOwned = true;
                },
                takeCamera: (token) => {
                    if (token === appliedCamera) return false;
                    appliedCamera = token;
                    return true;
                },
                isPanKey: () => spaceHeld,
                fitAll: () => fitCurrentBoards(),
            });
            if (!view.viewport.opened && !view.viewport.userAdjusted) scheduleOpeningCamera();
        }

        function renderWorkspace(payload) {
            activeOrderName = payload.order_name || "";
            const banner = freshnessBannerHtml(payload);
            ensureShell().innerHTML = `
                <div class="almdina-ui alm-page--workbench abe-page abe-root" dir="${esc(uiDirection())}">
                    ${banner}
                    <div class="abe-body">
                        <aside data-abe-sidebar class="abe-sidebar-host"></aside>
                        <section data-abe-canvas class="abe-canvas-host"></section>
                    </div>
                </div>
            `;
            paint();
        }

        function isStale(openGeneration, requestToken) {
            return openGeneration !== generation
                || suspended
                || !requestGate.isCurrent(requestToken);
        }

        async function open(context, options) {
            const opts = options || {};
            const openGeneration = ++generation;
            suspended = false;
            clearFreshnessRetry();
            pendingSourceConflict = null;
            const requestToken = requestGate.begin();
            const orderName = String(context.orderName || "").trim();
            const planName = String(context.planName || "").trim();
            if (!orderName || !planName) {
                renderState(
                    "error",
                    translate("Incomplete board editor link"),
                    translate("Open the board editor from a cutting plan tab on the order.")
                );
                return;
            }
            // Same route names are not enough — always re-fetch. Keep the loading
            // shell only when we are not preserving a dirty conflict screen.
            if (!opts.keepCurrentWorkspace) {
                renderState(
                    "loading",
                    translate("Loading board editor…"),
                    translate("Preparing layers, boards, and pieces.")
                );
            }
            try {
                const payload = await Api.load(orderName, planName);
                if (isStale(openGeneration, requestToken)) return;
                if (!payload || !payload.projection) {
                    renderState(
                        "empty",
                        translate("No board editor data"),
                        translate("The selected cutting plan has no displayable geometry."),
                        recoveryActions()
                    );
                    bindStateActions(orderName, context);
                    return;
                }
                const nextToken = contentRevisionToken(payload);
                const responsePlan = String((payload.plan && payload.plan.name) || "").trim();
                // Never silently swap away from the explicitly requested plan name.
                if (responsePlan && responsePlan !== planName) {
                    renderState(
                        "error",
                        translate("Cutting plan mismatch"),
                        translate("The server returned a different cutting plan than the one requested. Return to the order and open the editor again."),
                        recoveryActions()
                    );
                    bindStateActions(orderName, context);
                    return;
                }
                if (
                    store
                    && sessionIsDirty()
                    && loadedRevisionToken
                    && nextToken
                    && nextToken !== loadedRevisionToken
                    && !opts.acceptSourceChange
                ) {
                    renderSourceConflict(orderName, context, nextToken);
                    return;
                }
                if (unsubscribe) unsubscribe();
                store = createStore(payload);
                ensureSession(payload);
                bindMoveInteraction();
                unsubscribe = store.subscribe(() => paint());
                loadedRevisionToken = nextToken;
                loadedPlanName = responsePlan || planName;
                try {
                    renderWorkspace(payload);
                    bindFreshnessActions(orderName, context);
                    const freshness = payload.freshness || {};
                    if (freshness.job_active) {
                        scheduleFreshnessRetry(context, openGeneration, requestToken);
                    }
                } catch (renderError) {
                    console.error("Board editor render failed", renderError);
                    if (isStale(openGeneration, requestToken)) return;
                    renderState(
                        "error",
                        translate("Could not load the board editor"),
                        translate("The board editor data arrived, but the layout could not be drawn."),
                        recoveryActions()
                    );
                    bindStateActions(orderName, context);
                }
            } catch (error) {
                if (isStale(openGeneration, requestToken)) return;
                const status = error && (error.httpStatus || error.status || (error.responseJSON && error.responseJSON.exc_type));
                const permission = String(status || "").includes("Permission")
                    || String((error && error.message) || "").toLowerCase().includes("permission");
                const missing = String(status || "").includes("DoesNotExist")
                    || String((error && error.message) || "").toLowerCase().includes("not available");
                renderState(
                    "error",
                    permission
                        ? translate("Permission denied")
                        : missing
                            ? translate("Cutting plan unavailable")
                            : translate("Could not load the board editor"),
                    permission
                        ? translate("You do not have permission to open this cutting plan in the board editor.")
                        : missing
                            ? translate("The selected cutting plan is not available for this order.")
                            : translate("Reload the page or return to the order and try again."),
                    recoveryActions()
                );
                bindStateActions(orderName, context);
            }
        }

        function suspend() {
            if (moveInteraction) moveInteraction.cancel();
            suspended = true;
            generation += 1;
            requestGate.invalidate();
            clearFreshnessRetry();
            pendingSourceConflict = null;
            if (unsubscribe) {
                unsubscribe();
                unsubscribe = null;
            }
            store = null;
            moveInteraction = null;
            lastCanvasApi = null;
            openPending = false;
            activeOrderName = "";
            loadedRevisionToken = "";
            loadedPlanName = "";
            spaceHeld = false;
            altHeld = false;
            scrollOwned = false;
            liveScroll = { x: 0, y: 0 };
            appliedCamera = 0;
            const section = main;
            if (section) {
                const pageBody = section.closest(".page-body");
                [section, section.parentElement, pageBody].forEach((node) => {
                    if (!node || node === document.body) return;
                    node.style.minHeight = "";
                    node.style.height = "";
                    node.style.overflow = "";
                });
            }
            lifecycle.dispose();
        }

        function onShellGeometryChange() {
            if (!store || suspended) return;
            syncEditorHeight();
            const view = store.snapshot().viewport;
            if (!view.userAdjusted && !scrollOwned) {
                store.setViewport({ opened: false, columns: null });
                scheduleOpeningCamera();
            } else {
                syncSessionBoardGrid();
            }
        }

        lifecycle.listen(window, "resize", onShellGeometryChange);
        lifecycle.listen(window, "wheel", onCanvasWheel, { capture: true, passive: false }, "abe-wheel-zoom");
        lifecycle.listen(window, "keydown", (event) => {
            if (event.code === "Space" && !isEditableTarget(event.target)) {
                spaceHeld = true;
                if (moveInteraction) moveInteraction.onPanIntent();
            }
            if (event.key === "Alt" || event.code === "AltLeft" || event.code === "AltRight") {
                altHeld = true;
                if (moveInteraction && moveInteraction.refreshPreviewFromPointer) {
                    moveInteraction.refreshPreviewFromPointer();
                }
            }
            if (event.code === "Escape" && moveInteraction && moveInteraction.isActive()) {
                moveInteraction.cancel();
                event.preventDefault();
                return;
            }
            if (isEditableTarget(event.target) || (Distribution && !Distribution.keyboardDeleteApplies(event.target))) return;
            if (event.key === "Delete" && store && Distribution) {
                const view = store.snapshot();
                const keys = Array.isArray(view.selectedPieceKeys) && view.selectedPieceKeys.length
                    ? view.selectedPieceKeys
                    : (view.selectedPieceKey ? [view.selectedPieceKey] : []);
                if (keys.length === 1) {
                    event.preventDefault();
                    applyDistribution(() => Distribution.excludePiece(view.session, keys[0]));
                }
                return;
            }
            const mod = event.metaKey || event.ctrlKey;
            if (mod && String(event.key).toLowerCase() === "z" && !event.shiftKey) {
                if (store) store.undo();
                event.preventDefault();
            } else if (mod && (String(event.key).toLowerCase() === "y" || (String(event.key).toLowerCase() === "z" && event.shiftKey))) {
                if (store) store.redo();
                event.preventDefault();
            }
        });
        lifecycle.listen(window, "keyup", (event) => {
            if (event.code === "Space") spaceHeld = false;
            if (event.key === "Alt" || event.code === "AltLeft" || event.code === "AltRight") {
                altHeld = false;
                if (moveInteraction && moveInteraction.refreshPreviewFromPointer) {
                    moveInteraction.refreshPreviewFromPointer();
                }
            }
        });
        lifecycle.listen(window, "blur", () => {
            altHeld = false;
            if (moveInteraction) moveInteraction.cancel();
        });
        lifecycle.listen(window, "pagehide", () => {
            altHeld = false;
            if (moveInteraction) moveInteraction.cancel();
        });
        if (window.jQuery) {
            const $doc = window.jQuery(document);
            $doc.off("sidebar-expand.abeBoardEditor");
            $doc.on("sidebar-expand.abeBoardEditor", onShellGeometryChange);
            if (typeof lifecycle.track === "function") {
                lifecycle.track(() => {
                    $doc.off("sidebar-expand.abeBoardEditor");
                }, "abe-desk-sidebar-expand");
            }
        }

        function showRouteError(message) {
            renderState("error", translate("Incomplete board editor link"), message);
        }

        return { open, suspend, showRouteError };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.WorkspaceController = Object.freeze({ mount });
})();
