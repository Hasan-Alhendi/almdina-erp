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
        const RightSidebarRenderer = window.AlmdinaBoardEditor.RightSidebarRenderer;
        const SessionDocument = window.AlmdinaBoardEditor.SessionDocument;
        const History = window.AlmdinaBoardEditor.History;
        const createMoveInteraction = window.AlmdinaBoardEditor.createMoveInteraction;
        const createRotationInteraction = window.AlmdinaBoardEditor.createRotationInteraction;
        const createMeasureInteraction = window.AlmdinaBoardEditor.createMeasureInteraction;
        const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
        const TransformGeometry = window.AlmdinaBoardEditor.TransformGeometry;
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
        let measureInteraction = null;
        let lastCanvasApi = null;
        let beforeUnloadHandler = null;
        let routeGuardOriginal = null;
        let leaveConfirmed = false;

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

        function distributionDirty() {
            if (!store) return false;
            return Boolean(store.snapshot().distributionDirty);
        }

        function editorDirty() {
            return distributionDirty() || Boolean(drawingSession && drawingSession.anyDirty());
        }

        function savedDrawingReady(view) {
            const listed = (view && view.payload && view.payload.saved_drawings) || {};
            const fromPayload = Object.keys(listed).some((key) => Number(listed[key]) > 0);
            const fromSession = Boolean(
                drawingSession
                && typeof drawingSession.loadedRecords === "function"
                && drawingSession.loadedRecords().some((record) => Number(record.drawingVersion) > 0)
            );
            return fromPayload || fromSession;
        }

        function confirmLeave() {
            if (leaveConfirmed || !editorDirty()) return true;
            const accepted = window.confirm(translate(
                "Board editor changes are not saved. Leave without saving?"
            ));
            if (accepted) leaveConfirmed = true;
            return accepted;
        }

        function installLeaveGuards() {
            removeLeaveGuards();
            beforeUnloadHandler = (event) => {
                if (!editorDirty()) return;
                event.preventDefault();
                event.returnValue = "";
            };
            window.addEventListener("beforeunload", beforeUnloadHandler);
            if (window.frappe && typeof frappe.set_route === "function") {
                routeGuardOriginal = frappe.set_route;
                const guarded = function abeRouteGuard() {
                    if (!confirmLeave()) return Promise.resolve(false);
                    return routeGuardOriginal.apply(this, arguments);
                };
                guarded.__abeGuarded = true;
                frappe.set_route = guarded;
            }
        }

        function removeLeaveGuards() {
            if (beforeUnloadHandler) {
                window.removeEventListener("beforeunload", beforeUnloadHandler);
                beforeUnloadHandler = null;
            }
            if (
                window.frappe
                && routeGuardOriginal
                && frappe.set_route
                && frappe.set_route.__abeGuarded
            ) {
                frappe.set_route = routeGuardOriginal;
            }
            routeGuardOriginal = null;
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
            // Remaining viewport is visual; .abe-page uses transform:scale(uiZoom)
            // with compensated layout size (visual / zoom) so the scaled box fills.
            const uiZoom = CanvasRenderer.declaredUiZoom
                ? CanvasRenderer.declaredUiZoom(page)
                : (Number(CanvasRenderer.UI_ZOOM) || 0.9);
            const visualHeight = Math.max(320, Math.round(window.innerHeight - top));
            const height = Math.max(320, Math.round(visualHeight / Math.max(uiZoom, 1e-6)));
            page.style.height = `${height}px`;
            page.style.maxHeight = `${height}px`;
            page.style.overflow = "hidden";
            const pageBody = section.closest(".page-body");
            // RTL Frappe hosts + overflow:hidden clip the physical left of a
            // width-compensated child. Force LTR on the clip hosts only.
            [section, section.parentElement, pageBody].forEach((node) => {
                if (!node || node === document.body) return;
                node.classList.add("abe-shell-host");
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
        let lastCanvasPointerClient = null;
        let spaceHeld = false;
        let altHeld = false;
        let activeOrderName = "";
        let scrollOwned = false;
        let measureArmedBeforeDrawing = false;
        let drawingTool = "select";
        let drawingShapeKind = "rectangle";
        let penSmoothing = "low";
        let penGesture = null;
        let penCapture = null;
        let penLostHandler = null;
        let penWindowUp = null;
        let penWindowCancel = null;
        let penReleasing = false;
        let penCommitting = false;
        let penClosePathId = null;
        let snapSettings = null;
        let snapMenuOpen = false;
        let snapHold = null;
        let snapOverlay = null;
        let snapIndex = null;
        let snapRevisionKey = "";
        let referenceMenuOpen = false;
        let referenceAspectLock = true;
        let referenceCalibration = null;
        let referenceDrag = null;
        const referenceLoads = {};
        let shapeAnchor = null;
        let shapeEntry = {};
        let vectorGesture = null;
        let pendingCutPieceId = "";
        let pendingCutPathId = "";
        let vectorCapture = null;
        let vectorLostHandler = null;
        let vectorWindowMove = null;
        let vectorWindowUp = null;
        let vectorWindowCancel = null;
        let vectorReleasing = false;
        let drawingPointer = null;
        let drawingEntry = { lengthLocked: false, angleLocked: false, lengthText: "", angleText: "" };
        let pendingMeasureFocus = null;
        let committingMeasure = false;

        function resetDrawingEntry() {
            drawingEntry = { lengthLocked: false, angleLocked: false, lengthText: "", angleText: "" };
        }

        function rememberMeasureInput(field, value) {
            const text = value == null ? "" : String(value);
            const locked = text.trim() !== "";
            if (field === "angle") {
                drawingEntry.angleLocked = locked;
                drawingEntry.angleText = locked ? text : "";
                return;
            }
            drawingEntry.lengthLocked = locked;
            drawingEntry.lengthText = locked ? text : "";
        }

        function restoreDrawingMeasureFocus(canvas) {
            if (!pendingMeasureFocus || !canvas || typeof canvas.querySelector !== "function") return;
            const field = pendingMeasureFocus;
            pendingMeasureFocus = null;
            const input = canvas.querySelector(
                field === "angle"
                    ? "[data-abe-drawing-measure] [data-abe-drawing-angle]"
                    : "[data-abe-drawing-measure] [data-abe-drawing-length]"
            );
            if (input && !input.disabled && typeof input.focus === "function") input.focus();
        }
        let drawingPartialMessage = "";
        const drawingSession = window.AlmdinaBoardEditor.DrawingModel
            ? window.AlmdinaBoardEditor.DrawingModel.createSession()
            : null;
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
            // Prefer the server token. Fallback must not use the DocType row
            // clock; that field is not operational source identity.
            return String(
                freshness.content_revision_token
                || plan.content_revision_token
                || [
                    plan.name || "",
                    plan.saved_layout_sha256 || "",
                    plan.revision || "",
                    plan.input_fingerprint || "",
                    freshness.needs_recalculation ? "1" : "0",
                    freshness.job_active ? "1" : "0",
                ].join("|")
            );
        }

        function sessionIsDirty() {
            return editorDirty();
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

        function sourceViewBanner() {
            if (!store || !store.snapshot().sourceOnly) return "";
            return `<div class="abe-freshness-banner is-historical" role="status" data-abe-draft="source-view">
                <strong>${esc(translate("This view shows the source plan."))}</strong>
                <span>${esc(translate("The saved draft is unchanged. Open the editor without the source route to continue that draft."))}</span>
            </div>`;
        }

        function draftBannerHtml(payload) {
            const draft = (payload && payload.editor_draft) || {};
            if (draft.conflict === "source") {
                // Red top-of-editor alert (abe-freshness-banner.is-stale). The
                // begin action must stay inside this banner — not in the sidebar.
                return `<div class="abe-freshness-banner is-stale abe-draft-source-conflict" role="status" data-abe-draft="source-conflict">
                    <strong>${esc(translate("Saved draft does not match this plan source."))}</strong>
                    <span>${esc(translate("It was not applied. The cutting plan itself was not changed. Start a new draft from the current source to continue editing and saving. The previous draft is archived first; local unsaved moves on this screen are discarded on start."))}</span>
                    <div class="abe-freshness-actions">
                        <button type="button" class="btn alm-btn-primary abe-begin-from-source">${esc(translate("Start draft from current source"))}</button>
                    </div>
                </div>`;
            }
            return "";
        }

        function confirmBeginFromCurrentSource() {
            return new Promise((resolve) => {
                if (typeof frappe === "undefined" || !frappe.confirm) {
                    resolve(window.confirm(translate(
                        "Start a new draft from the current plan source? The previous saved draft will be archived. Unsaved local moves on this screen will be discarded. The cutting plan itself will not be changed."
                    )));
                    return;
                }
                frappe.confirm(
                    translate(
                        "Start a new draft from the current plan source? The previous saved draft will be archived. Unsaved local moves on this screen will be discarded. The cutting plan itself will not be changed."
                    ),
                    () => resolve(true),
                    () => resolve(false),
                );
            });
        }

        async function beginDraftFromCurrentSource(orderName, context) {
            if (!store || !activeOrderName || !loadedPlanName) return;
            const view = store.snapshot();
            const draft = (view.payload && view.payload.editor_draft) || {};
            if (draft.conflict !== "source") return;
            const confirmed = await confirmBeginFromCurrentSource();
            if (!confirmed) return;
            try {
                const response = await Api.beginDraftFromCurrentSource({
                    orderName: activeOrderName,
                    planName: loadedPlanName,
                    expectedDraftVersion: Number(draft.draft_version) || 0,
                    sourceContentRevision: contentRevisionToken(view.payload || {}),
                });
                if (!response || !response.ok) {
                    if (typeof frappe !== "undefined" && frappe.msgprint) {
                        const code = String((response && response.code) || "");
                        frappe.msgprint({
                            title: translate("Could not start draft"),
                            message: code === "version_conflict"
                                ? translate("Another tab updated this draft. Reload and try again.")
                                : translate("The draft could not be started from the current source. Your previous draft is unchanged."),
                            indicator: "orange",
                        });
                    }
                    return;
                }
                await open(context, { forceReload: true, acceptSourceChange: true });
            } catch (_error) {
                if (typeof frappe !== "undefined" && frappe.msgprint) {
                    frappe.msgprint({
                        title: translate("Could not start draft"),
                        message: translate("The draft could not be started from the current source. Your previous draft is unchanged."),
                        indicator: "red",
                    });
                }
            }
        }

        function bindFreshnessActions(orderName, context) {
            const shell = ensureShell();
            const back = shell.querySelector(".abe-freshness-banner .abe-back");
            if (back) back.onclick = () => backToOrder(orderName);
            const retry = shell.querySelector(".abe-freshness-retry");
            if (retry) {
                retry.onclick = () => open(context, { forceReload: true, acceptSourceChange: true });
            }
            const begin = shell.querySelector(".abe-begin-from-source");
            if (begin) {
                begin.onclick = () => beginDraftFromCurrentSource(orderName, context);
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

        function persistCamera(partial) {
            // Silent camera geometry sync (trail/min/scroll compensation) — no paint loop.
            if (!store || !partial) return;
            if (partial.scrollX != null || partial.scrollY != null) {
                liveScroll = {
                    x: partial.scrollX != null ? Number(partial.scrollX) || 0 : liveScroll.x,
                    y: partial.scrollY != null ? Number(partial.scrollY) || 0 : liveScroll.y,
                };
            }
            if (typeof store.patchViewport === "function") {
                store.patchViewport(partial);
            } else {
                store.setViewport(partial);
            }
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
            if (size.width < 40 || size.height < 40) return false;
            const view = store.snapshot();
            const sheets = view.projection.sheets || [];
            const widths = sheets.map((sheet) => (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10);
            const maxBoard = widths.length ? Math.max(...widths) : 1;
            const columns = CanvasRenderer.columnCount(maxBoard, size.width);
            const scale = CanvasRenderer.openingScale(maxBoard, columns, size.width);
            let layout = CanvasRenderer.sheetLayout(sheets, columns);
            if (view.session) layout = CanvasRenderer.mergeSessionLayout(layout, view.session);
            const camera = CanvasRenderer.frameCamera(
                layout.fitBounds,
                scale,
                size.width,
                size.height,
                {
                    minX: Number(layout.worldMinX) || 0,
                    minY: Number(layout.worldMinY) || 0,
                    width: Math.max(
                        layout.fitBounds.width + ((layout.staging && layout.staging.width) || 0),
                        1
                    ),
                    height: Math.max(layout.fitBounds.height, 1),
                }
            );
            if (!camera) return false;
            rememberCamera({
                scale: camera.scale,
                scrollX: camera.scrollX,
                scrollY: camera.scrollY,
                padX: camera.padX,
                padY: camera.padY,
                trailX: CanvasRenderer.SCENE_PAD_PX,
                trailY: CanvasRenderer.SCENE_PAD_PX,
                minX: Number(layout.worldMinX) || 0,
                minY: Number(layout.worldMinY) || 0,
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
                scrollX: camera.scrollX,
                scrollY: camera.scrollY,
                padX: camera.padX,
                padY: camera.padY,
                trailX: CanvasRenderer.SCENE_PAD_PX,
                trailY: CanvasRenderer.SCENE_PAD_PX,
                minX: Number(layout.worldMinX) || Number(layout.fitBounds && layout.fitBounds.x) || 0,
                minY: Number(layout.worldMinY) || Number(layout.fitBounds && layout.fitBounds.y) || 0,
                columns: layout.columns,
                opened: true,
                userAdjusted: true,
                fitted: true,
            });
            return true;
        }

        function zoomFocalClient(client) {
            if (client && Number.isFinite(client.x) && Number.isFinite(client.y)) return client;
            if (
                lastCanvasPointerClient
                && Number.isFinite(lastCanvasPointerClient.x)
                && Number.isFinite(lastCanvasPointerClient.y)
            ) {
                return lastCanvasPointerClient;
            }
            return null;
        }

        function zoomByFactor(factor, client) {
            if (!store || !CanvasRenderer.zoomAroundFocal) return;
            const stage = ensureShell().querySelector("[data-abe-stage]");
            const current = store.snapshot().viewport;
            const scrollX = stage ? Number(stage.scrollLeft) || 0 : liveScroll.x;
            const scrollY = stage ? Number(stage.scrollTop) || 0 : liveScroll.y;
            const layoutSize = stageSize();
            const pointer = zoomFocalClient(client);
            if (pointer) {
                lastCanvasPointerClient = { x: pointer.x, y: pointer.y };
            }
            // Focal must be in stage layout units (same as scrollLeft), not visual
            // getBoundingClientRect space under CSS zoom.
            let focalX = layoutSize.width / 2;
            let focalY = layoutSize.height / 2;
            if (pointer && stage && CanvasRenderer.clientPointToLocal) {
                const local = CanvasRenderer.clientPointToLocal(stage, pointer.x, pointer.y);
                focalX = local.x;
                focalY = local.y;
            } else if (pointer && stage && stage.getBoundingClientRect) {
                const rect = stage.getBoundingClientRect();
                focalX = pointer.x - rect.left;
                focalY = pointer.y - rect.top;
            }
            const metrics = lastCanvasApi && lastCanvasApi.metrics;
            // Prefer live rendered metrics so pad/min match the SVG currently on screen.
            const scale = Number(metrics && metrics.scale) || Number(current.scale) || 1;
            const padX = metrics && metrics.padX != null
                ? Number(metrics.padX)
                : (current.padX != null ? Number(current.padX) : CanvasRenderer.SCENE_PAD_PX);
            const padY = metrics && metrics.padY != null
                ? Number(metrics.padY)
                : (current.padY != null ? Number(current.padY) : CanvasRenderer.SCENE_PAD_PX);
            const trailX = metrics && metrics.trailX != null
                ? Number(metrics.trailX)
                : (current.trailX != null ? Number(current.trailX) : CanvasRenderer.SCENE_PAD_PX);
            const trailY = metrics && metrics.trailY != null
                ? Number(metrics.trailY)
                : (current.trailY != null ? Number(current.trailY) : CanvasRenderer.SCENE_PAD_PX);
            const minX = Number(metrics && metrics.minX) || 0;
            const minY = Number(metrics && metrics.minY) || 0;
            const worldW = Number(metrics && metrics.width) || 0;
            const worldH = Number(metrics && metrics.height) || 0;
            const viewSize = {
                width: Math.max(1, layoutSize.width || 1),
                height: Math.max(1, layoutSize.height || 1),
            };
            const next = CanvasRenderer.zoomAroundFocal({
                scale,
                scrollX,
                scrollY,
                padX,
                padY,
                trailX,
                trailY,
                minX,
                minY,
            }, { x: focalX, y: focalY }, factor, viewSize, {
                width: worldW,
                height: worldH,
            });
            if (next.changed === false) return;
            rememberCamera({
                scale: next.scale,
                scrollX: next.scrollX,
                scrollY: next.scrollY,
                padX: next.padX,
                padY: next.padY,
                trailX: next.trailX,
                trailY: next.trailY,
                minX: next.minX,
                minY: next.minY,
                columns: current.columns,
                opened: true,
                userAdjusted: true,
                fitted: false,
            });
        }

        function onCanvasWheel(event) {
            if (!store || suspended || !CanvasRenderer.shouldZoomWheel(event)) return;
            const target = event.target;
            if (target && target.closest && target.closest(".abe-float-tools, .abe-float-stack, .abe-right-sidebar, .abe-angle-field, .abe-angle-input, .abe-pos-input, .abe-drawing-measure, .abe-drawing-cursor")) {
                event.preventDefault();
                return;
            }
            let stage = null;
            try {
                stage = ensureShell().querySelector("[data-abe-stage]");
            } catch (err) {
                stage = null;
            }
            if (!stage || !event.target || typeof stage.contains !== "function" || !stage.contains(event.target)) return;
            event.preventDefault();
            lastCanvasPointerClient = { x: event.clientX, y: event.clientY };
            const factor = CanvasRenderer.wheelZoomFactor(
                event.deltaY,
                event.deltaMode,
                stage.clientHeight || stageSize().height
            );
            zoomByFactor(factor, lastCanvasPointerClient);
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

        function revealPiece(pieceKey) {
            if (!store || !pieceKey) return;
            const view = store.snapshot();
            const piece = view.session && view.session.pieces && view.session.pieces[pieceKey];
            if (!piece) return;
            if (piece.distribution === "excluded" || piece.sheet_no == null || piece.sheet_no === "") {
                const root = ensureShell().querySelector(".abe-root");
                const row = root && root.querySelector(`.abe-excluded [data-piece-key="${pieceKey}"]`);
                if (row && typeof row.scrollIntoView === "function") {
                    row.scrollIntoView({ block: "nearest", inline: "nearest" });
                }
                return;
            }
            const size = stageSize();
            if (size.width < 40 || size.height < 40) return;
            const layout = currentLayout(size.width);
            const board = layout.positions[String(piece.sheet_no)];
            if (!board) {
                revealSheet(piece.sheet_no);
                return;
            }
            const scale = Number(view.viewport.scale) || 1;
            const pad = 12;
            const ox = board.originX + (Number(board.trimX) || 0);
            const oy = board.originY + (Number(board.trimY) || 0);
            const localX = Number(piece.local_x_mm) || 0;
            const localY = Number(piece.local_y_mm) || 0;
            const width = Number((piece.placement_cm && piece.placement_cm.w) || 0) * 10 || 40;
            const height = Number((piece.placement_cm && piece.placement_cm.h) || 0) * 10 || 40;
            const x0 = CanvasRenderer.SCENE_PAD_PX + (ox + localX) * scale;
            const y0 = CanvasRenderer.SCENE_PAD_PX + (oy + localY) * scale;
            const x1 = CanvasRenderer.SCENE_PAD_PX + (ox + localX + width) * scale;
            const y1 = CanvasRenderer.SCENE_PAD_PX + (oy + localY + height) * scale;
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

        function closeReviewDialog() {
            const root = ensureShell().querySelector(".abe-root");
            const dialog = root && root.querySelector("[data-abe-review]");
            if (!dialog) return;
            dialog.setAttribute("hidden", "hidden");
            dialog.innerHTML = "";
        }

        function reviewIssueKey(issue) {
            const ids = ((issue && issue.piece_instance_ids) || []).slice().sort().join(",");
            const sheets = ((issue && issue.sheet_nos) || []).slice().sort().join(",");
            return `${(issue && issue.code) || ""}:${ids}:${sheets}`;
        }

        function syncReviewDialog(view) {
            const root = ensureShell().querySelector(".abe-root");
            if (!root) return;
            let dialog = root.querySelector("[data-abe-review]");
            if (!view || (!view.review && !view.reviewInFlight && !view.reviewStale)) {
                if (dialog) {
                    dialog.setAttribute("hidden", "hidden");
                    dialog.innerHTML = "";
                }
                return;
            }
            if (!dialog) {
                dialog = document.createElement("div");
                dialog.className = "abe-review-dialog";
                dialog.setAttribute("data-abe-review", "1");
                dialog.setAttribute("role", "dialog");
                dialog.setAttribute("aria-modal", "false");
                root.appendChild(dialog);
            }
            dialog.removeAttribute("hidden");
            if (view.reviewStale && !view.reviewInFlight) {
                dialog.innerHTML = `
                    <div class="abe-review-card">
                        <header class="abe-review-header">
                            <strong>${esc(__("Review distribution"))}</strong>
                            <button type="button" class="abe-review-close" aria-label="${esc(__("Close"))}">×</button>
                        </header>
                        <p class="abe-review-note">${esc(__("The distribution changed. Review it again."))}</p>
                    </div>
                `;
                const close = dialog.querySelector(".abe-review-close");
                if (close) close.onclick = () => closeReviewDialog();
                return;
            }
            if (view.reviewInFlight) {
                dialog.innerHTML = `
                    <div class="abe-review-card">
                        <header class="abe-review-header">
                            <strong>${esc(__("Review distribution"))}</strong>
                            <button type="button" class="abe-review-close" aria-label="${esc(__("Close"))}">×</button>
                        </header>
                        <p class="abe-review-note">${esc(__("Reviewing the saved distribution…"))}</p>
                    </div>
                `;
                const close = dialog.querySelector(".abe-review-close");
                if (close) close.onclick = () => closeReviewDialog();
                return;
            }
            const review = view.review || {};
            const issues = Array.isArray(review.issues) ? review.issues : [];
            const seen = new Set();
            const unique = [];
            issues.forEach((issue) => {
                const key = reviewIssueKey(issue);
                if (seen.has(key)) return;
                seen.add(key);
                unique.push(issue);
            });
            const errors = unique.filter((issue) => issue.severity !== "warning");
            const warnings = unique.filter((issue) => issue.severity === "warning");
            const ready = review.ready === true;
            const renderIssue = (issue) => {
                const pieceIds = (issue.piece_instance_ids || []).join(" ");
                const sheetNos = (issue.sheet_nos || []).join(" ");
                return `<button type="button" class="abe-review-issue" data-abe-issue-code="${esc(issue.code || "")}" data-abe-piece-instances="${esc(pieceIds)}" data-abe-sheet-nos="${esc(sheetNos)}">
                    <span class="abe-review-issue-code">${esc(issue.code || "")}</span>
                    <span class="abe-review-issue-msg">${esc(issue.message || __("The distribution is not ready."))}</span>
                </button>`;
            };
            dialog.innerHTML = `
                <div class="abe-review-card">
                    <header class="abe-review-header">
                        <strong>${esc(ready ? __("Distribution ready") : __("Distribution not ready"))}</strong>
                        <button type="button" class="abe-review-close" aria-label="${esc(__("Close"))}">×</button>
                    </header>
                    <p class="abe-review-meta">${esc(__("Draft version"))}: ${esc(String(review.draft_version || 0))}</p>
                    <p class="abe-review-note">${esc(__("This review does not approve or export the plan."))}</p>
                    ${errors.length ? `<section class="abe-review-section"><h3>${esc(__("Blocking issues"))}</h3>${errors.map(renderIssue).join("")}</section>` : ""}
                    ${warnings.length ? `<section class="abe-review-section"><h3>${esc(__("Warnings"))}</h3>${warnings.map(renderIssue).join("")}</section>` : ""}
                    ${!errors.length && !warnings.length ? `<p class="abe-review-empty">${esc(__("No distribution issues were found."))}</p>` : ""}
                </div>
            `;
            const close = dialog.querySelector(".abe-review-close");
            if (close) close.onclick = () => closeReviewDialog();
            dialog.querySelectorAll(".abe-review-issue").forEach((button) => {
                button.onclick = () => {
                    const instances = String(button.getAttribute("data-abe-piece-instances") || "")
                        .split(/\s+/)
                        .filter(Boolean);
                    if (!instances.length || !store) return;
                    const session = store.snapshot().session;
                    if (!session) return;
                    const byInstance = {};
                    Object.keys(session.pieces || {}).forEach((key) => {
                        const piece = session.pieces[key];
                        byInstance[String(piece.piece_instance_id)] = piece;
                    });
                    const piece = byInstance[instances[0]];
                    if (!piece) return;
                    store.selectPiece(piece.piece_id, {
                        pieceKey: piece.piece_key,
                        sheetNo: piece.sheet_no,
                        expandSheet: true,
                        elementId: null,
                    });
                    revealPiece(piece.piece_key);
                };
            });
        }

        function ensureSession(payload, options) {
            const size = stageSize();
            const sheets = (payload.projection && payload.projection.sheets) || [];
            const widths = sheets.map((sheet) => (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10);
            const maxBoard = widths.length ? Math.max(...widths) : 1;
            const columns = CanvasRenderer.columnCount(maxBoard, size.width || 1100);
            const layout = CanvasRenderer.sheetLayout(sheets, columns);
            let session = SessionDocument.buildFromProjection(payload.projection, layout);
            const draft = payload.editor_draft || {};
            const applySaved = !options || options.applySavedDraft !== false;
            const sourceOnly = applySaved === false && Boolean(draft.present);
            if (applySaved && draft.compatible && draft.layout) {
                const applied = SessionDocument.applySavedLayout(session, draft.layout);
                if (applied.ok) {
                    session = applied.session;
                }
            }
            const history = History.create(session);
            store.attachSession(history.get(), history);
            store.noteDraftBaseline({
                // Compatible drafts always expose their real version for the next
                // save — even when layout apply fails. Incompatible drafts stay at 0
                // so expected=0 cannot silently rebase over a different source.
                draftVersion: draft.compatible ? (Number(draft.draft_version) || 0) : 0,
                savedFingerprint: SessionDocument.distributionFingerprint(session),
                canSaveLayout: Boolean(payload.capabilities && payload.capabilities.edit_layout) && !sourceOnly,
                sourceOnly,
            });
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
            if (!layoutCommandsAllowed() || !store || !RotationGeometry) return;
            const view = store.snapshot();
            if (!view.session) return;
            const next = RotationGeometry.applyPieceRotation(view.session, pieceKey, rotationDeg);
            store.commitSession(next);
        }

        function ensurePageActionsHost() {
            const pageHead = wrapper.querySelector(".page-head");
            const pageRoot = pageHead || wrapper;
            let host = pageRoot.querySelector("[data-abe-page-actions]");
            if (host) return host;
            host = document.createElement("div");
            host.className = "abe-page-actions-host";
            host.setAttribute("data-abe-page-actions", "1");
            // Prefer .page-actions so the title row can grow full editor width and
            // pin this group at inline-end. Avoid nesting under the narrow title-area.
            const actions = pageRoot.querySelector(".page-actions");
            if (actions) {
                actions.appendChild(host);
            } else if (pageHead) {
                pageHead.appendChild(host);
            } else {
                pageRoot.appendChild(host);
            }
            return host;
        }

        function paintPageActions(view) {
            if (!CanvasRenderer || typeof CanvasRenderer.renderPageActions !== "function") return;
            const host = ensurePageActionsHost();
            CanvasRenderer.renderPageActions(host, view, {
                saveDraft: () => saveDraft(),
                reviewDraft: () => reviewDraft(),
                createPlanCopy: () => createPlanCopy(),
                onBack: () => backToOrder(activeOrderName),
            });
        }

        function rejectTransform(code) {
            if (window.frappe && frappe.show_alert) {
                frappe.show_alert({
                    message: translate(
                        (TransformGeometry && TransformGeometry.reasonMessage(code))
                        || code
                        || "Transform rejected."
                    ),
                    indicator: "orange",
                }, 4);
            }
        }

        function commitTransform(result, pieceKey) {
            if (!layoutCommandsAllowed()) return;
            if (!store || !result || !result.ok) {
                rejectTransform(result && result.code);
                return;
            }
            const view = store.snapshot();
            store.commitSession(result.session);
            const piece = result.session.pieces[pieceKey];
            if (piece) {
                store.selectPiece(piece.piece_id, {
                    pieceKey,
                    sheetNo: piece.sheet_no,
                    mode: "replace",
                });
            } else {
                store.selectPiece(view.selectedPieceId, { pieceKey, mode: "replace" });
            }
        }

        function nextAnglePairTarget(currentDeg, firstDeg, secondDeg) {
            const current = RotationGeometry.normalizeAngleDeg(currentDeg);
            if (RotationGeometry.anglesEquivalent(current, firstDeg)) {
                return RotationGeometry.normalizeAngleDeg(secondDeg);
            }
            if (RotationGeometry.anglesEquivalent(current, secondDeg)) {
                return RotationGeometry.normalizeAngleDeg(firstDeg);
            }
            return RotationGeometry.normalizeAngleDeg(firstDeg);
        }

        function applyAngleViaField(pieceKey, targetDeg) {
            if (!store || !RotationGeometry || !pieceKey) return;
            const view = store.snapshot();
            if (!view.session || !view.session.pieces[pieceKey]) return;
            const target = RotationGeometry.normalizeAngleDeg(targetDeg);
            if (rotationInteraction && typeof rotationInteraction.applyNumericAngle === "function") {
                rotationInteraction.applyNumericAngle(pieceKey, target);
                return;
            }
            commitRotation(pieceKey, target);
        }

        function toggleAnglePair(pieceKey, firstDeg, secondDeg) {
            if (!store || !RotationGeometry || !pieceKey) return;
            const view = store.snapshot();
            const piece = view.session && view.session.pieces[pieceKey];
            if (!piece) return;
            const target = nextAnglePairTarget(piece.rotation_deg, firstDeg, secondDeg);
            applyAngleViaField(pieceKey, target);
        }

        function toggleAngle0_180(pieceKey) {
            toggleAnglePair(pieceKey, 0, 180);
        }

        function toggleAngle90_270(pieceKey) {
            toggleAnglePair(pieceKey, 90, 270);
        }

        function rotateByDegrees(pieceKey, deltaDeg) {
            if (!store || !RotationGeometry || !pieceKey) return;
            const view = store.snapshot();
            if (!view.session || !view.session.pieces[pieceKey]) return;
            const current = Number(view.session.pieces[pieceKey].rotation_deg) || 0;
            const target = RotationGeometry.normalizeAngleDeg(current + Number(deltaDeg || 0));
            applyAngleViaField(pieceKey, target);
        }

        function mirrorAngle(pieceKey) {
            if (!store || !TransformGeometry || !pieceKey) return;
            const view = store.snapshot();
            if (!view.session) return;
            commitTransform(
                TransformGeometry.applyAngleMirror(view.session, pieceKey),
                pieceKey
            );
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
            measureInteraction = typeof createMeasureInteraction === "function"
                ? createMeasureInteraction({
                    store,
                    getSvgEl: () => ensureShell().querySelector(".abe-svg"),
                    getWorldMetrics: () => {
                        const host = ensureShell().querySelector("[data-abe-canvas]");
                        return (host && host.__abeWorldMetrics) || (lastCanvasApi && lastCanvasApi.metrics) || null;
                    },
                    isAltKey: () => altHeld,
                    isPanKey: () => spaceHeld,
                    isMeasureToolActive: () => Boolean(store && store.snapshot().measureToolActive),
                    isDragActive: () => Boolean(
                        (moveInteraction && moveInteraction.isActive && moveInteraction.isActive())
                        || (rotationInteraction && rotationInteraction.isActive && rotationInteraction.isActive())
                    ),
                    onOverlay: (lines) => {
                        const host = ensureShell().querySelector("[data-abe-canvas]");
                        if (!host) return;
                        host.__abeMeasureLines = Array.isArray(lines) ? lines : [];
                        if (lastCanvasApi && typeof lastCanvasApi.patchMeasureOverlay === "function") {
                            lastCanvasApi.patchMeasureOverlay(host.__abeMeasureLines);
                        } else if (CanvasRenderer && typeof CanvasRenderer.patchMeasureOverlay === "function") {
                            CanvasRenderer.patchMeasureOverlay(host, host.__abeMeasureLines);
                        }
                    },
                    onRejected: (reason) => {
                        if (window.frappe && frappe.show_alert) {
                            frappe.show_alert({
                                message: translate(reason || "Measurement rejected."),
                                indicator: "orange",
                            }, 4);
                        }
                    },
                })
                : null;
        }

        function finishActiveGesture() {
            endVectorGesture("cancel");
            if (moveInteraction && moveInteraction.cancel) moveInteraction.cancel();
            if (rotationInteraction && rotationInteraction.cancel) rotationInteraction.cancel();
            if (measureInteraction && measureInteraction.cancel) measureInteraction.cancel();
            if (store) {
                store.setDragPreview(null);
                store.setDropMessage("");
            }
        }

        function releaseVectorPointer(pointerId) {
            vectorReleasing = true;
            try {
                if (vectorCapture && pointerId != null && vectorCapture.releasePointerCapture) {
                    vectorCapture.releasePointerCapture(pointerId);
                }
            } catch (err) {
                void err;
            }
            if (vectorCapture && vectorLostHandler && vectorCapture.removeEventListener) {
                vectorCapture.removeEventListener("lostpointercapture", vectorLostHandler);
            }
            if (vectorWindowMove) window.removeEventListener("pointermove", vectorWindowMove, true);
            if (vectorWindowUp) window.removeEventListener("pointerup", vectorWindowUp, true);
            if (vectorWindowCancel) window.removeEventListener("pointercancel", vectorWindowCancel, true);
            vectorCapture = null;
            vectorLostHandler = null;
            vectorWindowMove = null;
            vectorWindowUp = null;
            vectorWindowCancel = null;
            vectorReleasing = false;
        }

        function ownVectorPointer(event) {
            const shell = ensureShell();
            const pointerId = event.pointerId;
            vectorCapture = shell;
            vectorLostHandler = () => {
                if (!vectorReleasing) endVectorGesture("cancel");
            };
            if (shell && shell.addEventListener) shell.addEventListener("lostpointercapture", vectorLostHandler);
            if (shell && shell.setPointerCapture) {
                try { shell.setPointerCapture(pointerId); } catch (err) { void err; }
            }
            vectorWindowMove = (moveEvent) => {
                if (!vectorGesture || !moveEvent || moveEvent.pointerId !== pointerId) return;
                try {
                    if (vectorGesture.kind === "node") updateNodeGesture(moveEvent);
                    else updateSelectGesture(moveEvent);
                } catch (error) {
                    endVectorGesture("cancel");
                    throw error;
                }
            };
            vectorWindowUp = (upEvent) => {
                if (!upEvent || upEvent.pointerId !== pointerId) return;
                endVectorGesture("commit");
            };
            vectorWindowCancel = (cancelEvent) => {
                if (!cancelEvent || cancelEvent.pointerId !== pointerId) return;
                endVectorGesture("cancel");
            };
            window.addEventListener("pointermove", vectorWindowMove, true);
            window.addEventListener("pointerup", vectorWindowUp, true);
            window.addEventListener("pointercancel", vectorWindowCancel, true);
        }

        function endVectorGesture(mode) {
            const gesture = vectorGesture;
            if (!gesture || gesture.ending) return;
            gesture.ending = true;
            const pointerId = gesture.pointerId;
            const undo = mode !== "commit" && gesture.history === true;
            vectorGesture = null;
            releaseVectorPointer(pointerId);
            if (undo && drawingSession) drawingSession.undo();
            if (mode === "commit") refreshCutValidation();
            syncDrawing();
        }

        function refreshCutValidation() {
            const Compile = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingCompile;
            const Space = drawingSpaceApi();
            if (!drawingSession || !Compile || typeof drawingSession.loadedRecords !== "function") return;
            const view = store && store.snapshot();
            const target = view && view.drawingTarget;
            drawingSession.loadedRecords().forEach((record) => {
                if (!record || !record.document) return;
                let width = Number(record.document.blank && record.document.blank.width_mm);
                let length = Number(record.document.blank && record.document.blank.length_mm);
                if (target && String(target.pieceInstanceId) === String(record.pieceInstanceId) && Space) {
                    const targetWidth = Space.cmToMm(target.widthCm);
                    const targetLength = Space.cmToMm(target.lengthCm);
                    if (targetWidth) width = targetWidth;
                    if (targetLength) length = targetLength;
                }
                const result = Compile.compile(record.document, width, length);
                const rejected = result && result.status === "rejected";
                record.manufacturingIssue = rejected ? result : null;
                const active = target && String(target.pieceInstanceId) === String(record.pieceInstanceId);
                if (!active) return;
                const known = Compile.messages || {};
                const knownText = Object.keys(known).map((key) => known[key]);
                if (rejected) record.messageKey = result.messageKey || "";
                else if (knownText.indexOf(record.messageKey) >= 0) record.messageKey = "";
            });
        }

        function markGestureHistory() {
            if (!vectorGesture || !drawingSession || typeof drawingSession.documentCanonical !== "function") return;
            if (vectorGesture.beforeCanonical !== drawingSession.documentCanonical()) {
                vectorGesture.history = true;
            }
        }

        function layoutCommandsAllowed() {
            if (!store) return false;
            const mode = store.snapshot().editorMode;
            const EditorMode = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.EditorMode;
            if (EditorMode && typeof EditorMode.layoutCommandsAllowed === "function") {
                return EditorMode.layoutCommandsAllowed(mode);
            }
            return mode !== "drawing";
        }

        function setEditorMode(mode) {
            if (!store) return;
            cancelPenStroke(false);
            const EditorMode = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.EditorMode;
            const next = EditorMode && typeof EditorMode.normalize === "function"
                ? EditorMode.normalize(mode)
                : (mode === "drawing" ? "drawing" : "board");
            if ((store.snapshot().editorMode || "board") === next) return;
            const measureWasActive = store.snapshot().measureToolActive === true;
            finishActiveGesture();
            if (next === "drawing") {
                measureArmedBeforeDrawing = measureWasActive;
                if (measureWasActive) store.setMeasureToolActive(false);
            }
            store.setEditorMode(next);
            if (next === "board" && measureArmedBeforeDrawing) {
                measureArmedBeforeDrawing = false;
                store.setMeasureToolActive(true);
            }
            syncDrawing();
        }

        function drawingSpaceApi() {
            return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        }

        function activeDrawingRecord() {
            return drawingSession && drawingSession.current && drawingSession.current();
        }

        function doorPointFromEvent(view, event) {
            const Space = drawingSpaceApi();
            const frame = drawingFrame(view);
            const svg = ensureShell().querySelector("[data-abe-canvas] .abe-svg");
            const metrics = (svg && svg.closest("[data-abe-canvas]") && svg.closest("[data-abe-canvas]").__abeWorldMetrics)
                || (lastCanvasApi && lastCanvasApi.metrics);
            if (!Space || !frame || !svg || !CanvasRenderer || !event) return null;
            const world = CanvasRenderer.clientToWorld(svg, metrics, event.clientX, event.clientY);
            if (!world) return null;
            const door = Space.worldToDoor(frame, world.x, world.y);
            return { door, world, frame };
        }

        function drawingFrame(view) {
            const Space = drawingSpaceApi();
            const target = view && view.drawingTarget;
            const piece = target && view.session && view.session.pieces[target.pieceKey];
            if (!Space || !piece || target.widthCm == null || target.lengthCm == null) return null;
            return Space.pieceFrame(piece, view.session.boards || {}, {
                widthMm: Space.cmToMm(target.widthCm),
                lengthMm: Space.cmToMm(target.lengthCm),
            });
        }

        let syncingDrawing = false;

        function syncDrawing() {
            if (!store || !drawingSession || syncingDrawing) return;
            if (penGesture && penGesture.active() && !penCommitting) cancelPenStroke(false);
            syncingDrawing = true;
            try {
            if (!store || !drawingSession) return;
            const view = store.snapshot();
            const Space = drawingSpaceApi();
            const target = view.drawingTarget;
            if (view.editorMode !== "drawing" || !target || target.status !== "special" || !Space) {
                if (view.drawingView) store.setDrawingView(null);
                return;
            }
            const widthMm = Space.cmToMm(target.widthCm);
            const lengthMm = Space.cmToMm(target.lengthCm);
            const record = drawingSession.activate({
                pieceInstanceId: target.pieceInstanceId,
                widthMm,
                lengthMm,
            });
            if (record && !record.ready && record.loadToken === 0) {
                const ticket = drawingSession.beginLoad();
                if (ticket && Api && Api.getDrawing) {
                    Api.getDrawing({
                        orderName: activeOrderName,
                        planName: loadedPlanName,
                        pieceInstanceId: ticket.pieceInstanceId,
                    }).then((response) => {
                        if (drawingSession.applyLoaded(ticket.pieceInstanceId, ticket.token, response || { ok: false })) {
                            syncDrawing();
                        }
                    }).catch(() => {
                        if (drawingSession.applyLoaded(ticket.pieceInstanceId, ticket.token, { ok: false, code: "load_failed" })) {
                            syncDrawing();
                        }
                    });
                } else if (ticket) {
                    drawingSession.applyLoaded(ticket.pieceInstanceId, ticket.token, { ok: true, drawing: null, drawing_version: 0 });
                }
            }
            refreshCutValidation();
            if (
                pendingCutPathId
                && record
                && record.ready
                && String(record.pieceInstanceId) === pendingCutPieceId
            ) {
                const problemPath = (record.document.paths || []).find((row) => row.id === pendingCutPathId);
                if (problemPath) {
                    record.selection = { pathId: problemPath.id };
                    drawingTool = "select";
                }
                pendingCutPathId = "";
                pendingCutPieceId = "";
            }
            store.setDrawingView(buildDrawingView(view, record, Space));
            ensureReferenceMedia(record);
            } finally {
                syncingDrawing = false;
            }
        }

        function worldPoint(frame, Space, point) {
            if (!point) return null;
            const world = frame ? Space.doorToWorld(frame, point.x, point.y) : point;
            return { x: world.x, y: world.y, role: point.role || "" };
        }

        function drawingShapes(record, frame, Space) {
            if (!Space.normalizeShape) return [];
            return (record.document.shapes || []).filter((shape) => shape && !shape.exploded).map((shape) => {
                const built = Space.normalizeShape(shape.kind, shape.params);
                if (!built.ok) return null;
                return {
                    id: shape.id,
                    kind: shape.kind,
                    closed: built.figure.closed !== false,
                    selected: Boolean(record.selection && record.selection.shapeId === shape.id),
                    points: built.figure.points.map((point) => worldPoint(frame, Space, point)),
                    handles: (built.figure.handles || []).map((point) => worldPoint(frame, Space, point)),
                };
            }).filter(Boolean);
        }

        function shapeFieldValue(key, params) {
            if (shapeEntry[key] != null) return shapeEntry[key];
            if (!params || params[key] == null) return "";
            return String(params[key]);
        }

        function shapeFormState(record, Space) {
            if (!Space.shapeFieldDefs) return null;
            if (drawingTool === "node_edit" && record.selection && record.selection.nodeId && String(record.selection.nodeId).indexOf("control:") !== 0) {
                const path = (record.document.paths || []).find((row) => row.id === record.selection.pathId);
                const node = path && path.nodes.find((row) => row.id === record.selection.nodeId);
                if (!node) return null;
                return {
                    mode: "node",
                    fields: [
                        { key: "x_mm", labelKey: "Drawing X (mm)", value: shapeFieldValue("x_mm", { x_mm: node.x_mm }) },
                        { key: "y_mm", labelKey: "Drawing Y (mm)", value: shapeFieldValue("y_mm", { y_mm: node.y_mm }) },
                    ],
                    errorKey: record.measureError && record.measureError.messageKey,
                    actions: { copy: true, paste: Boolean(record.clipboard), remove: true, insert: true },
                };
            }
            const editing = (drawingTool === "select" || drawingTool === "node_edit")
                && record.selection && record.selection.shapeId && !record.selection.pathId
                ? (record.document.shapes || []).find((shape) => shape.id === record.selection.shapeId && !shape.exploded)
                : null;
            if (!editing && drawingTool !== "shapes") {
                if (drawingTool === "select" && record.selection && record.selection.pathId && !record.selection.shapeId) {
                    return {
                        mode: "path",
                        fields: [],
                        actions: { copy: true, paste: Boolean(record.clipboard), remove: true },
                    };
                }
                if (!record.clipboard) return null;
                return { mode: "create", kind: drawingShapeKind, fields: [], actions: { paste: true } };
            }
            const kind = editing ? editing.kind : drawingShapeKind;
            return {
                mode: editing ? "edit" : "create",
                kind,
                fields: Space.shapeFieldDefs(kind).map((field) => ({
                    key: field.key,
                    labelKey: field.labelKey,
                    value: shapeFieldValue(field.key, editing && editing.params),
                })),
                errorKey: record.measureError && record.measureError.messageKey,
                actions: editing
                    ? { convert: true, copy: true, paste: Boolean(record.clipboard), remove: true }
                    : { paste: Boolean(record.clipboard) },
            };
        }

        function buildDrawingView(view, record, Space) {
            if (!record) return null;
            const frame = drawingFrame(view);
            const paths = (record.document.paths || []).map((path) => ({
                id: path.id,
                role: path.role || "construction",
                problem: Boolean(record.manufacturingIssue && record.manufacturingIssue.pathId === path.id),
                closed: path.closed === true,
                selected: Boolean(record.selection && record.selection.pathId === path.id && !record.selection.shapeId),
                active: Boolean(record.cursor && record.cursor.pathId === path.id),
                markup: Space.pathMarkup ? Space.pathMarkup(frame, path) : "",
                points: (path.nodes || []).map((node) => {
                    const world = frame ? Space.doorToWorld(frame, node.x_mm, node.y_mm) : { x: node.x_mm, y: node.y_mm };
                    return {
                        id: node.id,
                        x: world.x,
                        y: world.y,
                        selected: Boolean(record.selection && record.selection.nodeId === node.id),
                    };
                }),
                controls: drawingTool === "node_edit" && record.selection && record.selection.pathId === path.id
                    ? (path.segments || []).reduce((list, segment) => {
                        if (segment.kind !== "bezier" || !segment.controls) return list;
                        segment.controls.forEach((control, index) => {
                            const world = frame
                                ? Space.doorToWorld(frame, control.x_mm, control.y_mm)
                                : { x: control.x_mm, y: control.y_mm };
                            list.push({ segmentId: segment.id, index, x: world.x, y: world.y });
                        });
                        return list;
                    }, [])
                    : [],
            }));
            if (record.cursor && !record.cursor.pathId && frame) {
                const world = Space.doorToWorld(frame, record.cursor.x, record.cursor.y);
                paths.push({
                    id: "draft-start",
                    closed: false,
                    selected: true,
                    active: true,
                    points: [{ id: record.cursor.nodeId, x: world.x, y: world.y }],
                });
            }
            return {
                tool: drawingTool,
                dragging: Boolean(vectorGesture),
                ready: record.ready === true,
                dirty: drawingSession.documentDirty(record),
                canUndo: Boolean(record.past && record.past.length),
                canRedo: Boolean(record.future && record.future.length),
                messageKey: drawingPartialMessage || record.messageKey || "",
                canFinish: Boolean(record.cursor && record.cursor.pathId),
                canClose: Boolean(record.cursor && record.cursor.pathId),
                canCancel: Boolean(record.cursor),
                paths,
                shapes: drawingShapes(record, frame, Space),
                shapeKind: drawingShapeKind,
                shapeForm: shapeFormState(record, Space),
                pen: drawingTool === "pen" ? { smoothing: penSmoothing, canClose: Boolean(penClosePathId) } : null,
                preview: drawingPointer && drawingPointer.preview,
                snap: snapOverlay || (drawingPointer && drawingPointer.snap),
                snapSettings: snapState(),
                snapMenuOpen: snapMenuOpen === true,
                references: drawingReferenceViews(record, frame, Space),
                referenceMenuOpen: referenceMenuOpen === true,
                referenceForm: referenceFormState(record),
                pathForm: pathFormState(record),
                measure: drawingMeasureState(record),
                cutProblem: record.manufacturingIssue ? {
                    pathId: record.manufacturingIssue.pathId,
                    messageKey: record.manufacturingIssue.messageKey,
                    label: view.drawingTarget && view.drawingTarget.label,
                    widthCm: view.drawingTarget && view.drawingTarget.widthCm,
                    lengthCm: view.drawingTarget && view.drawingTarget.lengthCm,
                } : null,
            };
        }

        function validateSelectedCut() {
            refreshCutValidation();
        }

        function proposedCutsFor(view) {
            const Compile = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingCompile;
            const Space = drawingSpaceApi();
            if (!Compile || !Space || !drawingSession || !view || view.editorMode === "drawing" || !view.session) return [];
            const cuts = [];
            drawingSession.loadedRecords().forEach((record) => {
                if (!record || !record.document) return;
                const piece = Object.values(view.session.pieces || {}).find((row) => row.piece_instance_id === record.pieceInstanceId);
                const width = Number(record.document.blank && record.document.blank.width_mm);
                const length = Number(record.document.blank && record.document.blank.length_mm);
                const result = Compile.compile(record.document, width, length);
                if (!piece || result.status !== "ready" || !result.geometry) return;
                const frame = Space.pieceFrame(piece, view.session.boards || {}, { widthMm: width, lengthMm: length });
                cuts.push({
                    pieceInstanceId: record.pieceInstanceId,
                    points: result.geometry.points.map((point) => Space.doorToWorld(frame, point[0] * 10, point[1] * 10)),
                });
            });
            return cuts;
        }

        function pathFormState(record) {
            if (!record || !record.selection || !record.selection.pathId || record.selection.shapeId) return null;
            const path = (record.document.paths || []).find((row) => row.id === record.selection.pathId);
            if (!path) return null;
            return { pathId: path.id, role: path.role || "construction" };
        }

        function drawingMeasureState(record) {
            if (drawingTool === "polyline") {
            const measureError = record && record.measureError;
            return {
                mode: "draw",
                enabled: Boolean(record && record.cursor),
                lengthMm: drawingPointer ? drawingPointer.lengthMm : null,
                angleDeg: drawingPointer ? drawingPointer.angleDeg : null,
                lengthText: drawingEntry.lengthText,
                angleText: drawingEntry.angleText,
                lengthLocked: drawingEntry.lengthLocked,
                angleLocked: drawingEntry.angleLocked,
                errorKey: measureError && measureError.messageKey,
                errorField: measureError && measureError.field,
            };
            }
            if ((drawingTool !== "select" && drawingTool !== "node_edit") || !record || !record.selection || !record.selection.segmentId || record.selection.nodeId) return null;
            const path = (record.document.paths || []).find((row) => row.id === record.selection.pathId);
            if (!path) return null;
            if (path.closed) {
                const measured = drawingSession.metrics(record.selection.pathId, record.selection.segmentId);
                if (!measured) return null;
                return {
                    mode: "edit",
                    enabled: true,
                    hintKey: "This edit moves only the segment end and keeps the path closed.",
                    lengthMm: measured.lengthMm,
                    angleDeg: measured.angleDeg,
                    lengthText: drawingEntry.lengthText,
                    angleText: drawingEntry.angleText,
                    lengthLocked: drawingEntry.lengthLocked,
                    angleLocked: drawingEntry.angleLocked,
                    errorKey: record.measureError && record.measureError.messageKey,
                    errorField: record.measureError && record.measureError.field,
                };
            }
            const measured = drawingSession.metrics(record.selection.pathId, record.selection.segmentId);
            if (!measured) return null;
            const measureError = record.measureError;
            return {
                mode: "edit",
                enabled: true,
                lengthMm: measured.lengthMm,
                angleDeg: measured.angleDeg,
                lengthText: drawingEntry.lengthText,
                angleText: drawingEntry.angleText,
                lengthLocked: drawingEntry.lengthLocked,
                angleLocked: drawingEntry.angleLocked,
                errorKey: measureError && measureError.messageKey,
                errorField: measureError && measureError.field,
            };
        }

        function drawingSnapApi() {
            return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSnap;
        }

        function snapState() {
            const Snap = drawingSnapApi();
            const defaults = Snap && Snap.defaultSettings ? Snap.defaultSettings() : {
                enabled: true, endpoint: true, midpoint: true, intersection: true, alignment: true, grid: false, spacing: 10,
            };
            return Object.assign({}, defaults, snapSettings || {});
        }

        function rememberSnapRevision(record) {
            const paths = (record && record.document && record.document.paths) || [];
            const shapes = (record && record.document && record.document.shapes) || [];
            let signature = `${paths.length}:${shapes.length}`;
            paths.forEach((path) => {
                let sum = 0;
                (path.nodes || []).forEach((node) => { sum += Number(node.x_mm) + Number(node.y_mm); });
                signature += `|${path.id}:${path.closed ? 1 : 0}:${(path.nodes || []).length}:${(path.segments || []).length}:${Math.round(sum * 1000)}`;
            });
            shapes.forEach((shape) => {
                signature += `|${shape.id}:${shape.exploded ? 1 : 0}:${JSON.stringify(shape.params || {})}`;
            });
            return signature;
        }

        function indexForSnap(record) {
            const Snap = drawingSnapApi();
            if (!Snap || !record) return null;
            const revision = rememberSnapRevision(record);
            if (!snapIndex || snapRevisionKey !== revision) {
                snapIndex = Snap.buildIndex(record.document);
                snapRevisionKey = revision;
            }
            return snapIndex;
        }

        function showSnapOverlay(frame, Space, snap) {
            snapHold = snap;
            if (!snap || !frame || !Space) {
                snapOverlay = null;
                return;
            }
            const origin = Space.doorToWorld(frame, snap.point.x, snap.point.y);
            let guide = null;
            if (snap.guide) {
                const from = Space.doorToWorld(frame, snap.guide.x1, snap.guide.y1);
                const to = Space.doorToWorld(frame, snap.guide.x2, snap.guide.y2);
                guide = { x1: from.x, y1: from.y, x2: to.x, y2: to.y };
            }
            snapOverlay = { x: origin.x, y: origin.y, type: snap.type, labelKey: snap.labelKey, guide };
        }

        function resolveSmartPoint(door, options) {
            const input = options || {};
            const Snap = drawingSnapApi();
            const Space = drawingSpaceApi();
            const record = activeDrawingRecord();
            if (!door) return { x: 0, y: 0, snap: null };
            if (!Snap || !record || input.alt) {
                showSnapOverlay(input.frame, Space, null);
                return { x: door.x, y: door.y, snap: null };
            }
            const scale = store ? (Number(store.snapshot().viewport.scale) || 1) : 1;
            const result = Snap.resolve({
                index: indexForSnap(record),
                pointer: door,
                settings: snapState(),
                scale,
                anchor: input.anchor || null,
                shift: input.shift === true,
                alt: false,
                hold: snapHold,
                exclude: input.exclude || null,
                blockPoints: input.blockPoints || null,
            });
            showSnapOverlay(input.frame, Space, result.snap);
            return {
                x: result.point.x,
                y: result.point.y,
                snap: result.snap,
                angle: result.angle,
            };
        }

        function resolvedDoorPoint(mapped, shiftKey, altKey) {
            const Space = drawingSpaceApi();
            const record = activeDrawingRecord();
            if (!Space || !mapped || !mapped.door) return null;
            const anchor = record && record.cursor ? { x: record.cursor.x, y: record.cursor.y } : null;
            const exclude = record && record.cursor && record.cursor.pathId
                ? { pathId: record.cursor.pathId, nodeId: record.cursor.nodeId }
                : null;
            const resolved = resolveSmartPoint(mapped.door, {
                shift: shiftKey === true && Boolean(anchor),
                alt: altKey === true,
                anchor,
                exclude,
                frame: mapped.frame,
            });
            if (!anchor || resolved.snap) return resolved;
            const angle = Space.snapAngleDeg(Space.angleDeg(anchor.x, anchor.y, mapped.door.x, mapped.door.y), shiftKey);
            const length = Space.lengthMm(anchor.x, anchor.y, resolved.x, resolved.y);
            if (!shiftKey) return resolved;
            const end = Space.polarPoint(anchor, length, angle);
            return { x: end.x, y: end.y, snap: null, angle, length };
        }

        function updateDrawingPointer(event) {
            if (!store || !drawingSession || drawingTool !== "polyline") return;
            const view = store.snapshot();
            if (view.editorMode !== "drawing") return;
            const mapped = doorPointFromEvent(view, event);
            const record = activeDrawingRecord();
            if (!mapped || !record || !record.cursor) {
                drawingPointer = null;
                return;
            }
            const Space = drawingSpaceApi();
            const resolved = resolvedDoorPoint(mapped, Boolean(event && event.shiftKey), Boolean(event && event.altKey));
            const from = Space.doorToWorld(mapped.frame, record.cursor.x, record.cursor.y);
            const to = Space.doorToWorld(mapped.frame, resolved.x, resolved.y);
            const pointerLength = Space.lengthMm(record.cursor.x, record.cursor.y, resolved.x, resolved.y);
            const pointerAngle = resolved.angle != null
                ? resolved.angle
                : Space.angleDeg(record.cursor.x, record.cursor.y, resolved.x, resolved.y);
            drawingPointer = {
                pointerLength,
                pointerAngle,
                lengthMm: pointerLength,
                angleDeg: pointerAngle,
                preview: { x1: from.x, y1: from.y, x2: to.x, y2: to.y },
                snap: snapOverlay,
                door: resolved,
                clientX: event.clientX,
                clientY: event.clientY,
            };
            applyTypedSegmentPreview(record, mapped.frame, Space);
            patchLiveDrawingPreview();
        }

        function applyTypedSegmentPreview(record, frame, Space) {
            if (!drawingPointer || !record || !record.cursor || !frame || !Space) return;
            if (!drawingEntry.lengthLocked && !drawingEntry.angleLocked) return;
            const Model = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingModel;
            if (!Model || typeof Model.resolveNumericSegment !== "function" || typeof Space.segmentEnd !== "function") return;
            const decision = Model.resolveNumericSegment({
                lengthText: drawingEntry.lengthLocked ? drawingEntry.lengthText : "",
                angleText: drawingEntry.angleLocked ? drawingEntry.angleText : "",
                previewLength: drawingPointer.pointerLength,
                previewAngle: drawingPointer.pointerAngle,
            });
            if (!decision.ok) return;
            const end = Space.segmentEnd(record.cursor, decision.lengthMm, decision.angleDeg);
            if (!end) return;
            const from = Space.doorToWorld(frame, record.cursor.x, record.cursor.y);
            const to = Space.doorToWorld(frame, end.x, end.y);
            drawingPointer.lengthMm = end.lengthMm;
            drawingPointer.angleDeg = decision.angleDeg;
            drawingPointer.preview = { x1: from.x, y1: from.y, x2: to.x, y2: to.y };
            drawingPointer.snap = null;
            snapOverlay = null;
        }

        function patchLiveDrawingPreview() {
            const host = ensureShell().querySelector("[data-abe-canvas]");
            if (!host || !CanvasRenderer || !CanvasRenderer.patchDrawingPreview || !drawingPointer) return;
            CanvasRenderer.patchDrawingPreview(host, drawingPointer.preview, drawingPointer.snap, {
                lengthMm: drawingPointer.lengthMm,
                angleDeg: drawingPointer.angleDeg,
                clientX: drawingPointer.clientX,
                clientY: drawingPointer.clientY,
            });
        }

        function refreshTypedPreviewFromEntry() {
            if (!store || drawingTool !== "polyline") return;
            const record = activeDrawingRecord();
            const Space = drawingSpaceApi();
            const frame = drawingFrame(store.snapshot());
            if (!record || !record.cursor || !Space || !frame) return;
            if (!drawingPointer) {
                drawingPointer = {
                    pointerLength: null,
                    pointerAngle: null,
                    lengthMm: null,
                    angleDeg: null,
                    preview: null,
                    snap: null,
                    door: null,
                    clientX: null,
                    clientY: null,
                };
            }
            applyTypedSegmentPreview(record, frame, Space);
            if (drawingPointer.preview) patchLiveDrawingPreview();
        }

        function drawingReferenceApi() {
            return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingReference;
        }

        function selectedReference(record) {
            const id = record && record.selection && record.selection.referenceId;
            return id ? (record.document.references || []).find((row) => row.id === id) || null : null;
        }

        function drawingReferenceViews(record, frame, Space) {
            const Reference = drawingReferenceApi();
            const selectedId = record.selection && record.selection.referenceId;
            return (record.document.references || []).map((reference) => {
                const source = referenceDrag && referenceDrag.id === reference.id && referenceDrag.live
                    ? Object.assign({}, reference, referenceDrag.live)
                    : reference;
                const project = Reference && frame
                    ? Reference.project(source, (x, y) => Space.doorToWorld(frame, x, y))
                    : null;
                const media = record.referenceMedia && record.referenceMedia[reference.file_id];
                return {
                    id: reference.id,
                    hidden: reference.hidden === true,
                    locked: reference.locked === true,
                    selected: selectedId === reference.id,
                    interactive: drawingTool === "select" && reference.locked !== true,
                    opacity: source.opacity,
                    widthMm: source.width_mm,
                    heightMm: source.height_mm,
                    href: media || "",
                    world: project,
                };
            });
        }

        function referenceFormState(record) {
            const reference = selectedReference(record);
            if (!reference) return null;
            const live = referenceDrag && referenceDrag.id === reference.id && referenceDrag.live
                ? Object.assign({}, reference, referenceDrag.live)
                : reference;
            const calibrating = Boolean(referenceCalibration && referenceCalibration.id === reference.id);
            return {
                x_mm: live.x_mm,
                y_mm: live.y_mm,
                width_mm: live.width_mm,
                height_mm: live.height_mm,
                rotation_deg: live.rotation_deg,
                opacity: live.opacity,
                aspectLocked: referenceAspectLock !== false,
                calibrating,
                calibrationMessage: calibrating ? referenceCalibration.messageKey : "",
                currentDistance: calibrating ? referenceCalibration.currentDistance : null,
                knownText: calibrating ? referenceCalibration.knownText || "" : "",
                calibration: live.calibration,
            };
        }

        function drawingServerIdentity() {
            return {
                orderName: String(activeOrderName || "").trim(),
                planName: String(loadedPlanName || "").trim(),
            };
        }

        function ensureReferenceMedia(record) {
            const Api = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.Api;
            const identity = drawingServerIdentity();
            if (!Api || !record || !identity.orderName || !identity.planName || typeof Api.getReferenceImage !== "function") return;
            record.referenceMedia = record.referenceMedia || {};
            (record.document.references || []).forEach((reference) => {
                const fileId = reference.file_id;
                if (!fileId || record.referenceMedia[fileId] || referenceLoads[fileId]) return;
                referenceLoads[fileId] = true;
                const pieceId = record.pieceInstanceId;
                const token = record.loadToken;
                Api.getReferenceImage({
                    orderName: identity.orderName,
                    planName: identity.planName,
                    pieceInstanceId: pieceId,
                    fileId,
                }).then((response) => {
                    delete referenceLoads[fileId];
                    const current = drawingSession.current();
                    if (!current || current.pieceInstanceId !== pieceId || current.loadToken !== token) return;
                    current.referenceMedia = current.referenceMedia || {};
                    if (response && response.ok && response.content_base64) {
                        current.referenceMedia[fileId] = `data:image/png;base64,${response.content_base64}`;
                        if (current.referenceMissing) delete current.referenceMissing[fileId];
                    } else {
                        current.referenceMissing = current.referenceMissing || {};
                        current.referenceMissing[fileId] = true;
                        current.messageKey = "The reference image could not be loaded.";
                    }
                    syncDrawing();
                }).catch(() => {
                    delete referenceLoads[fileId];
                });
            });
        }

        function readReferenceFile(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || "").split(",").pop() || "");
                reader.onerror = () => reject(reader.error);
                reader.readAsDataURL(file);
            });
        }

        function uploadReferenceFiles(files) {
            const Api = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.Api;
            const Reference = drawingReferenceApi();
            const Space = drawingSpaceApi();
            const view = store && store.snapshot();
            const target = view && view.drawingTarget;
            const record = activeDrawingRecord();
            const identity = drawingServerIdentity();
            const file = files && files[0];
            if (!Api || !Reference || !Space || !view || !target || target.canEdit !== true || !record || !record.ready || !file) return;
            if (!identity.orderName || !identity.planName || !record.pieceInstanceId) {
                record.messageKey = "The reference image could not be loaded.";
                syncDrawing();
                return;
            }
            const pieceId = record.pieceInstanceId;
            const token = record.loadToken;
            readReferenceFile(file).then((contentBase64) => Api.uploadReferenceImage({
                orderName: identity.orderName,
                planName: identity.planName,
                pieceInstanceId: pieceId,
                fileName: file.name || "",
                contentBase64,
            })).then((response) => {
                if (!drawingSession.isCurrent(pieceId, token)) return;
                const current = drawingSession.current();
                if (!response || response.ok !== true) {
                    current.messageKey = referenceErrorKey(response && response.code);
                    syncDrawing();
                    return;
                }
                const placed = Reference.initialPlacement(
                    Space.cmToMm(target.widthCm),
                    Space.cmToMm(target.lengthCm),
                    response.width_px,
                    response.height_px
                );
                const id = drawingSession.addReference(Object.assign({ file_id: response.file_id }, placed));
                if (!id) {
                    syncDrawing();
                    return;
                }
                current.referenceMedia = current.referenceMedia || {};
                current.referenceMedia[response.file_id] = `data:image/png;base64,${response.content_base64}`;
                syncDrawing();
            }).catch(() => {
                if (!drawingSession.isCurrent(pieceId, token)) return;
                const current = drawingSession.current();
                current.messageKey = "The reference image could not be loaded.";
                syncDrawing();
            });
        }

        function referenceErrorKey(code) {
            if (code === "unsafe_svg") return "This SVG contains active content and was rejected.";
            if (code === "svg_not_supported") return "SVG reference images cannot be imported safely here.";
            if (code === "unsupported_image") return "This image format is not supported.";
            if (code === "image_too_large" || code === "image_too_many_pixels") return "The reference image is too large.";
            if (code === "image_corrupt") return "The reference image could not be read.";
            if (code === "piece_not_drawable") return "Select one editable special piece before uploading a reference image.";
            return "The reference image could not be loaded.";
        }

        function toggleReferenceMenu() {
            const view = store && store.snapshot();
            if (!view || view.editorMode !== "drawing" || !view.drawingTarget || view.drawingTarget.canEdit !== true) return;
            referenceMenuOpen = referenceMenuOpen !== true;
            syncDrawing();
        }

        function referenceAction(action, referenceId) {
            const record = activeDrawingRecord();
            if (!record) return;
            if (action === "calibrate") {
                const selected = selectedReference(record);
                if (!selected) return;
                referenceCalibration = { id: selected.id, messageKey: "Pick the first point on the image.", knownText: "" };
                syncDrawing();
                return;
            }
            if (action === "apply-calibration") return applyReferenceCalibration();
            const id = referenceId || (record.selection && record.selection.referenceId);
            const reference = (record.document.references || []).find((row) => row.id === id);
            if (!reference) return;
            if (action === "hide") drawingSession.updateReference(id, { hidden: reference.hidden !== true });
            else if (action === "lock") drawingSession.updateReference(id, { locked: reference.locked !== true });
            else if (action === "delete") drawingSession.deleteReference(id);
            syncDrawing();
        }

        function commitReferenceField(field, value) {
            const record = activeDrawingRecord();
            const reference = selectedReference(record);
            const Reference = drawingReferenceApi();
            if (!record || !reference || !field) return;
            if (field === "known") {
                if (referenceCalibration && referenceCalibration.id === reference.id) referenceCalibration.knownText = value;
                return;
            }
            if (field === "opacity") {
                drawingSession.updateReference(reference.id, { opacity: Number(value) / 100 });
                syncDrawing();
                return;
            }
            const number = Reference ? Reference.quantize(String(value).replace(",", ".")) : Number(value);
            if (number == null) return;
            const patch = {};
            patch[field] = number;
            if (field === "width_mm" && referenceAspectLock && reference.width_mm > 0) {
                patch.height_mm = number * reference.height_mm / reference.width_mm;
            }
            if (field === "height_mm" && referenceAspectLock && reference.height_mm > 0) {
                patch.width_mm = number * reference.width_mm / reference.height_mm;
            }
            drawingSession.updateReference(reference.id, patch);
            syncDrawing();
        }

        function applyReferenceCalibration() {
            const record = activeDrawingRecord();
            const reference = selectedReference(record);
            const Reference = drawingReferenceApi();
            const host = ensureShell().querySelector("[data-abe-canvas]");
            const knownInput = host && host.querySelector("[data-abe-reference-known]");
            if (!record || !reference || !Reference || !referenceCalibration || referenceCalibration.id !== reference.id) return;
            if (!referenceCalibration.start || !referenceCalibration.end) return;
            const known = Reference.quantize(String((knownInput && knownInput.value) || referenceCalibration.knownText || "").replace(",", "."));
            const result = Reference.applyCalibration(reference, referenceCalibration.start, referenceCalibration.end, known);
            if (!result.ok) {
                record.messageKey = result.code === "calibration_outside"
                    ? "Pick both calibration points on the image."
                    : "Enter a valid known distance.";
                syncDrawing();
                return;
            }
            drawingSession.updateReference(reference.id, result);
            referenceCalibration = null;
            syncDrawing();
        }

        function takeCalibrationPoint(door) {
            const record = activeDrawingRecord();
            const reference = selectedReference(record);
            const Reference = drawingReferenceApi();
            if (!referenceCalibration || !reference || referenceCalibration.id !== reference.id || !Reference) return false;
            if (!Reference.contains(reference, door)) {
                record.messageKey = "Pick both calibration points on the image.";
                syncDrawing();
                return true;
            }
            if (!referenceCalibration.start) {
                referenceCalibration.start = { x: door.x, y: door.y };
                referenceCalibration.messageKey = "Pick the second point on the image.";
            } else if (!referenceCalibration.end) {
                referenceCalibration.end = { x: door.x, y: door.y };
                referenceCalibration.currentDistance = Math.round(Math.hypot(door.x - referenceCalibration.start.x, door.y - referenceCalibration.start.y) * 1000) / 1000;
                referenceCalibration.messageKey = "Enter the known distance.";
            }
            syncDrawing();
            return true;
        }

        function beginReferenceDrag(reference, mode, door) {
            referenceDrag = {
                id: reference.id,
                mode,
                originDoor: { x: door.x, y: door.y },
                snapshot: {
                    id: reference.id,
                    x_mm: reference.x_mm,
                    y_mm: reference.y_mm,
                    width_mm: reference.width_mm,
                    height_mm: reference.height_mm,
                    rotation_deg: reference.rotation_deg,
                    opacity: reference.opacity,
                },
                live: null,
            };
        }

        function updateReferencePointer(event) {
            if (!referenceDrag || !store) return false;
            const Reference = drawingReferenceApi();
            const mapped = doorPointFromEvent(store.snapshot(), event);
            if (!Reference || !mapped) return true;
            const start = referenceDrag.snapshot;
            let live = null;
            if (referenceDrag.mode === "move") {
                live = {
                    x_mm: start.x_mm + (mapped.door.x - referenceDrag.originDoor.x),
                    y_mm: start.y_mm + (mapped.door.y - referenceDrag.originDoor.y),
                };
            } else if (referenceDrag.mode === "rotate") {
                const center = Reference.doorPoint(start, start.width_mm / 2, start.height_mm / 2);
                const angle = Math.atan2(mapped.door.y - center.y, mapped.door.x - center.x) * 180 / Math.PI;
                live = Reference.rotateAroundCenter(start, angle);
            } else {
                const local = Reference.toLocal(start, mapped.door);
                let factorX = referenceDrag.mode === "nw" || referenceDrag.mode === "sw"
                    ? (start.width_mm - local.x) / start.width_mm
                    : local.x / start.width_mm;
                let factorY = referenceDrag.mode === "nw" || referenceDrag.mode === "ne"
                    ? (start.height_mm - local.y) / start.height_mm
                    : local.y / start.height_mm;
                if (referenceAspectLock !== false) {
                    const factor = Math.max(Math.abs(factorX), Math.abs(factorY));
                    factorX = factor;
                    factorY = factor;
                }
                live = Reference.resizeReference(start, referenceDrag.mode, factorX, factorY);
            }
            if (live) referenceDrag.live = live;
            const host = ensureShell().querySelector("[data-abe-canvas]");
            if (host && CanvasRenderer && CanvasRenderer.patchReferenceFrame && referenceDrag.live) {
                CanvasRenderer.patchReferenceFrame(host, Object.assign({}, start, referenceDrag.live), mapped.frame, drawingSpaceApi());
            }
            return true;
        }

        function finishReferenceDrag() {
            if (!referenceDrag) return;
            const live = referenceDrag.live;
            const id = referenceDrag.id;
            referenceDrag = null;
            if (live) drawingSession.updateReference(id, live);
            syncDrawing();
        }

        function drawingPointerDown(event) {
            if (!store || !drawingSession || !event || event.button !== 0) return false;
            if (event.target && event.target.closest && event.target.closest("[data-abe-drawing-cursor], [data-abe-drawing-measure], [data-abe-shape-form], [data-abe-path-form], [data-abe-pen-settings], [data-abe-snap-menu], [data-abe-snap-toggle], [data-abe-reference-menu], [data-abe-reference-form], [data-abe-reference-toggle]")) {
                return false;
            }
            const view = store.snapshot();
            if (view.editorMode !== "drawing" || !view.drawingTarget || view.drawingTarget.canEdit !== true) return false;
            const record = activeDrawingRecord();
            if (!record || !record.ready) return false;
            const mapped = doorPointFromEvent(view, event);
            if (!mapped) return false;
            if (referenceCalibration && takeCalibrationPoint(mapped.door)) return true;
            if (drawingTool === "select") {
                const Space = drawingSpaceApi();
                const Reference = drawingReferenceApi();
                const scale = Number(view.viewport.scale) || 1;
                const hit = drawingSession.selectHit(mapped.door, Space.thresholdMm(scale));
                if (hit) {
                    drawingPointer = null;
                    shapeEntry = {};
                    resetDrawingEntry();
                    beginSelectGesture(record, mapped.door, event);
                    syncDrawing();
                    return true;
                }
                if (Reference) {
                    const references = (record.document.references || []).slice().reverse();
                    const image = references.find((row) => row.hidden !== true && row.locked !== true && Reference.contains(row, mapped.door));
                    if (image) {
                        drawingSession.selectReference(image.id);
                        beginReferenceDrag(image, "move", mapped.door);
                        syncDrawing();
                        return true;
                    }
                }
                return false;
            }
            if (drawingTool === "shapes") return placeShapePoint(mapped, event);
            if (drawingTool === "node_edit") return beginNodeEdit(mapped, view, event);
            if (drawingTool === "pen") return beginPenStroke(event, mapped);
            if (drawingTool !== "polyline") return false;
            const resolved = resolvedDoorPoint(mapped, event.shiftKey, event.altKey) || mapped.door;
            if (resolved.snap && resolved.snap.closes && record.cursor && record.cursor.pathId) {
                drawingSession.close();
            } else {
                drawingSession.placePoint(resolved.x, resolved.y);
            }
            drawingPointer = null;
            resetDrawingEntry();
            syncDrawing();
            return true;
        }

        function textOrEntry(text, field) {
            const live = text == null ? "" : String(text);
            if (live.trim() !== "") return live;
            if (field === "angle" && drawingEntry.angleLocked) return drawingEntry.angleText;
            if (field !== "angle" && drawingEntry.lengthLocked) return drawingEntry.lengthText;
            return live;
        }

        function selectMeasureError(length, angle) {
            if (length.invalid || length.empty) {
                return {
                    field: "length",
                    messageKey: length.invalid ? "Enter a valid length." : "Enter a length.",
                };
            }
            if (!(length.value > 0)) {
                return { field: "length", messageKey: "A zero-length segment was not created." };
            }
            if (angle.invalid || angle.empty) {
                return {
                    field: "angle",
                    messageKey: angle.invalid ? "Enter a valid angle." : "Enter a valid angle.",
                };
            }
            return null;
        }

        function commitDrawingHud(lengthText, angleText, sourceField) {
            if (committingMeasure) return;
            const record = activeDrawingRecord();
            const Space = drawingSpaceApi();
            const Model = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingModel;
            const target = store && store.snapshot().drawingTarget;
            if (!record || !Space || !Model || !target || target.canEdit !== true) return;
            const length = textOrEntry(lengthText, "length");
            const angle = textOrEntry(angleText, "angle");
            committingMeasure = true;
            try {
                let committed = false;
                if (drawingTool === "select" || drawingTool === "node_edit") {
                    const parsedLength = Model.parseMeasure(length);
                    const parsedAngle = Model.parseMeasure(angle);
                    const error = selectMeasureError(parsedLength, parsedAngle);
                    if (error) {
                        record.measureError = error;
                    } else {
                        committed = drawingSession.editSelected(parsedLength.value, parsedAngle.value) === true;
                        record.measureError = committed
                            ? null
                            : { field: "length", messageKey: record.messageKey || "Enter a valid length." };
                    }
                } else if (drawingTool === "polyline") {
                    const result = drawingSession.commitNumeric({
                        lengthText: length,
                        angleText: angle,
                        previewLength: drawingPointer ? drawingPointer.pointerLength : null,
                        previewAngle: drawingPointer ? drawingPointer.pointerAngle : null,
                    });
                    committed = Boolean(result && result.ok);
                } else {
                    return;
                }
                if (committed) {
                    resetDrawingEntry();
                    drawingPointer = null;
                }
                pendingMeasureFocus = sourceField === "angle" ? "angle" : "length";
                syncDrawing();
                if (pendingMeasureFocus) {
                    restoreDrawingMeasureFocus(ensureShell().querySelector("[data-abe-canvas]"));
                }
            } finally {
                committingMeasure = false;
            }
        }

        function applyDrawingHistory(direction) {
            if (!drawingSession) return;
            if (direction === "redo") drawingSession.redo();
            else drawingSession.undo();
            refreshCutValidation();
            syncDrawing();
        }

        function drawingAction(action) {
            const target = store && store.snapshot().drawingTarget;
            if (!drawingSession || !target || target.canEdit !== true) return;
            if (action === "finish") drawingSession.finish();
            else if (action === "close") drawingSession.close();
            else if (action === "cancel") drawingSession.cancelPath();
            else if (action === "close-pen" && penClosePathId) {
                if (drawingSession.closePenPath(penClosePathId)) penClosePathId = null;
            }
            else if (action === "convert") {
                const selected = activeDrawingRecord();
                if (selected && selected.selection && selected.selection.shapeId) {
                    drawingSession.convertShape(selected.selection.shapeId);
                }
            } else if (action === "copy") drawingSession.copySelection();
            else if (action === "paste") drawingSession.pasteClipboard();
            else if (action === "remove") drawingSession.deleteSelection();
            else if (action === "role-construction" || action === "role-annotation" || action === "role-manufacturing" || action === "role-clear") {
                const selected = activeDrawingRecord();
                const pathId = selected && selected.selection && selected.selection.pathId;
                const role = action === "role-annotation"
                    ? "annotation"
                    : (action === "role-manufacturing" ? "manufacturing_outer" : "construction");
                if (pathId) drawingSession.setPathRole(pathId, role);
            } else if (action === "select-problem" || action === "clear-problem") {
                const selected = activeDrawingRecord();
                const pathId = selected && selected.manufacturingIssue && selected.manufacturingIssue.pathId;
                if (action === "select-problem" && selected && pathId) {
                    selected.selection = { pathId };
                    drawingTool = "select";
                } else if (pathId) {
                    drawingSession.setPathRole(pathId, "construction");
                }
            } else if (action === "move-path") {
                const selected = activeDrawingRecord();
                const pathId = selected && selected.selection && selected.selection.pathId;
                const host = ensureShell();
                const dx = host && host.querySelector("[data-abe-path-dx]");
                const dy = host && host.querySelector("[data-abe-path-dy]");
                if (pathId && dx && dy) drawingSession.translatePath(pathId, dx.value, dy.value);
            } else if (action === "validate-path") {
                validateSelectedCut();
            } else if (action === "insert-node") {
                const selected = activeDrawingRecord();
                const path = selected && (selected.document.paths || []).find((row) => row.id === (selected.selection && selected.selection.pathId));
                const segment = path && (
                    path.segments.find((row) => row.id === selected.selection.segmentId && row.kind === "line")
                    || path.segments.find((row) => row.kind === "line" && (
                        row.from_node === selected.selection.nodeId || row.to_node === selected.selection.nodeId
                    ))
                );
                if (path && segment) {
                    const from = path.nodes.find((node) => node.id === segment.from_node);
                    const to = path.nodes.find((node) => node.id === segment.to_node);
                    if (from && to) drawingSession.insertNode(path.id, segment.id, (from.x_mm + to.x_mm) / 2, (from.y_mm + to.y_mm) / 2);
                }
            }
            drawingPointer = null;
            resetDrawingEntry();
            const record = activeDrawingRecord();
            if (record) record.measureError = null;
            syncDrawing();
        }

        function readShapeFields(host) {
            const fields = {};
            if (!host) return fields;
            host.querySelectorAll("[data-abe-shape-field]").forEach((input) => {
                fields[input.getAttribute("data-abe-shape-field")] = input.value;
            });
            return fields;
        }

        function placeShapePoint(mapped, event) {
            const Space = drawingSpaceApi();
            const door = mapped && mapped.frame
                ? resolveSmartPoint(mapped.door, { alt: event && event.altKey, anchor: shapeAnchor, frame: mapped.frame })
                : mapped && mapped.door;
            if (!Space || !door) return false;
            if (!shapeAnchor) {
                shapeAnchor = { x: door.x, y: door.y };
                drawingPointer = null;
                syncDrawing();
                return true;
            }
            const host = ensureShell().querySelector("[data-abe-canvas]");
            const fields = readShapeFields(host);
            const typed = Object.keys(fields).some((key) => {
                if (!fields[key] || !String(fields[key]).trim()) return false;
                return key !== "x_mm" && key !== "y_mm" && key !== "cx_mm" && key !== "cy_mm" && key !== "corner" && key !== "rotation_deg" && key !== "start_angle_deg";
            });
            let created = false;
            if (typed) created = drawingSession.commitShapeFields(drawingShapeKind, fields, shapeAnchor, "create").ok === true;
            else if (drawingShapeKind === "bezier") created = drawingSession.createBezier(shapeAnchor, door) === true;
            else {
                const built = Space.shapeFromDrag(drawingShapeKind, shapeAnchor, door);
                created = Boolean(built.ok && drawingSession.createShape(drawingShapeKind, built.params));
                if (!created && built && !built.ok) {
                    const record = activeDrawingRecord();
                    if (record) record.measureError = { field: "", messageKey: built.messageKey };
                }
            }
            shapeAnchor = null;
            shapeEntry = {};
            drawingPointer = null;
            syncDrawing();
            return created || true;
        }

        function beginSelectGesture(record, door, event) {
            const selection = record && record.selection;
            if (!selection || !event) return;
            const base = selectionBase(record, selection);
            if (!base) return;
            vectorGesture = {
                kind: "select",
                pointerId: event.pointerId,
                history: false,
                clientX: event.clientX,
                clientY: event.clientY,
                originDoor: { x: door.x, y: door.y },
                base,
            };
            ownVectorPointer(event);
        }

        function selectionBase(record, selection) {
            if (selection.shapeId && !selection.pathId) {
                const shape = (record.document.shapes || []).find((row) => row.id === selection.shapeId);
                if (!shape || shape.exploded) return null;
                return { kind: "shape", id: shape.id, params: JSON.parse(JSON.stringify(shape.params)) };
            }
            const path = (record.document.paths || []).find((row) => row.id === selection.pathId);
            if (!path) return null;
            const shape = path.source_shape_id
                ? (record.document.shapes || []).find((row) => row.id === path.source_shape_id)
                : null;
            return {
                kind: "path",
                id: path.id,
                nodes: JSON.parse(JSON.stringify(path.nodes || [])),
                segments: JSON.parse(JSON.stringify(path.segments || [])),
                shapeParams: shape ? JSON.parse(JSON.stringify(shape.params)) : null,
            };
        }

        function updateSelectGesture(event) {
            const gesture = vectorGesture;
            if (!gesture || gesture.kind !== "select" || !store || !drawingSession) return;
            const distance = Math.hypot(event.clientX - gesture.clientX, event.clientY - gesture.clientY);
            if (!gesture.history && distance < 4) return;
            const mapped = doorPointFromEvent(store.snapshot(), event);
            if (!mapped) return;
            const dx = mapped.door.x - gesture.originDoor.x;
            const dy = mapped.door.y - gesture.originDoor.y;
            const before = drawingSession.documentCanonical();
            const options = {
                history: gesture.history ? false : undefined,
                base: gesture.base.kind === "shape" ? gesture.base.params : gesture.base,
            };
            const moved = gesture.base.kind === "shape"
                ? drawingSession.moveShape(gesture.base.id, dx, dy, options)
                : drawingSession.translatePath(gesture.base.id, dx, dy, options);
            if (moved && drawingSession.documentCanonical() !== before) gesture.history = true;
            refreshCutValidation();
            syncDrawing();
        }

        function beginNodeEdit(mapped, view, event) {
            const Space = drawingSpaceApi();
            const door = mapped && mapped.door;
            const record = activeDrawingRecord();
            const scale = Number(view.viewport.scale) || 1;
            const hit = drawingSession.hitNode(door, Space.thresholdMm(scale));
            shapeEntry = {};
            if (hit && hit.kind === "control") {
                vectorGesture = {
                    kind: "node",
                    mode: "control",
                    pointerId: event && event.pointerId,
                    pathId: hit.pathId,
                    segmentId: hit.segmentId,
                    controlIndex: hit.controlIndex,
                    history: false,
                };
                if (event) ownVectorPointer(event);
                syncDrawing();
                return true;
            }
            if (hit && hit.kind === "node") {
                drawingSession.selectNode(hit.pathId, hit.nodeId);
                const path = record && (record.document.paths || []).find((row) => row.id === hit.pathId);
                const node = path && path.nodes.find((row) => row.id === hit.nodeId);
                vectorGesture = {
                    kind: "node",
                    mode: "node",
                    pointerId: event && event.pointerId,
                    pathId: hit.pathId,
                    nodeId: hit.nodeId,
                    history: false,
                    origin: node ? { x: node.x_mm, y: node.y_mm } : { x: door.x, y: door.y },
                };
                if (event) ownVectorPointer(event);
                syncDrawing();
                return true;
            }
            endVectorGesture("cancel");
            const selected = drawingSession.selectHit(door, Space.thresholdMm(scale));
            syncDrawing();
            return selected === true;
        }

        function updateNodeGesture(event) {
            const gesture = vectorGesture;
            if (!gesture || gesture.kind !== "node" || !store || !drawingSession) return;
            const record = activeDrawingRecord();
            if (!record) return;
            const view = store.snapshot();
            const mapped = doorPointFromEvent(view, event);
            if (!mapped) return;
            const options = { history: gesture.history ? false : undefined };
            let door = mapped.door;
            if (gesture.mode === "node") {
                const path = (record.document.paths || []).find((row) => row.id === gesture.pathId);
                const blockPoints = [];
                (path && path.segments || []).forEach((segment) => {
                    if (segment.from_node !== gesture.nodeId && segment.to_node !== gesture.nodeId) return;
                    const otherId = segment.from_node === gesture.nodeId ? segment.to_node : segment.from_node;
                    const other = path.nodes.find((row) => row.id === otherId);
                    if (other) blockPoints.push({ x: other.x_mm, y: other.y_mm });
                });
                door = resolveSmartPoint(mapped.door, {
                    alt: event && event.altKey,
                    frame: mapped.frame,
                    anchor: gesture.origin,
                    exclude: { pathId: gesture.pathId, nodeId: gesture.nodeId },
                    blockPoints,
                });
            }
            const before = drawingSession.documentCanonical();
            const moved = gesture.mode === "control"
                ? drawingSession.moveBezierControl(gesture.pathId, gesture.segmentId, gesture.controlIndex, door.x, door.y, options)
                : drawingSession.moveNode(gesture.pathId, gesture.nodeId, door.x, door.y, options);
            if (moved && drawingSession.documentCanonical() !== before) gesture.history = true;
            refreshCutValidation();
            syncDrawing();
        }

        function updateShapePointer(event) {
            if (drawingTool === "node_edit" && vectorGesture && vectorGesture.kind === "node") {
                updateNodeGesture(event);
                return;
            }
            if (drawingTool !== "shapes" || !shapeAnchor) return;
            const view = store.snapshot();
            const mapped = doorPointFromEvent(view, event);
            const Space = drawingSpaceApi();
            const host = ensureShell().querySelector("[data-abe-canvas]");
            if (!mapped || !Space || !host || !CanvasRenderer.patchShapePreview) return;
            const snapped = resolveSmartPoint(mapped.door, {
                alt: event && event.altKey,
                anchor: shapeAnchor,
                frame: mapped.frame,
            });
            mapped.door = { x: snapped.x, y: snapped.y };
            const frame = drawingFrame(view);
            let figure = null;
            if (drawingShapeKind === "bezier") {
                const built = Space.bezierFromPoints(shapeAnchor, mapped.door);
                if (built.ok) {
                    const start = built.parts.nodes[0];
                    const end = built.parts.nodes[1];
                    const controls = built.parts.segments[0].controls;
                    figure = {
                        closed: false,
                        points: [start, controls[0], controls[1], end].map((point) => ({ x: point.x_mm, y: point.y_mm })),
                    };
                }
            } else {
                const built = Space.shapeFromDrag(drawingShapeKind, shapeAnchor, mapped.door);
                if (built.ok) figure = built.figure;
            }
            if (!figure) {
                CanvasRenderer.patchShapePreview(host, null, false);
                return;
            }
            const points = figure.points.map((point) => (frame ? Space.doorToWorld(frame, point.x, point.y) : point));
            CanvasRenderer.patchShapePreview(host, points, figure.closed !== false);
            if (CanvasRenderer.patchDrawingPreview) {
                CanvasRenderer.patchDrawingPreview(host, null, snapOverlay, null);
            }
        }

        function commitShapeForm() {
            const record = activeDrawingRecord();
            const host = ensureShell().querySelector("[data-abe-canvas]");
            const form = host && host.querySelector("[data-abe-shape-form]");
            if (!record || !form || !drawingSession) return;
            const mode = form.getAttribute("data-abe-shape-mode") || "create";
            const fields = readShapeFields(host);
            if (mode === "node" && record.selection && record.selection.nodeId) {
                drawingSession.moveNode(record.selection.pathId, record.selection.nodeId, fields.x_mm, fields.y_mm);
            } else {
                const kind = mode === "edit" && record.selection && record.selection.shapeId
                    ? ((record.document.shapes || []).find((shape) => shape.id === record.selection.shapeId) || {}).kind
                    : drawingShapeKind;
                drawingSession.commitShapeFields(kind, fields, shapeAnchor || null, mode);
            }
            shapeAnchor = null;
            shapeEntry = {};
            drawingPointer = null;
            syncDrawing();
        }

        function releasePenCapture(pointerId) {
            penReleasing = true;
            try {
                if (penCapture && penCapture.releasePointerCapture && pointerId != null) {
                    penCapture.releasePointerCapture(pointerId);
                }
            } catch (err) {
                void err;
            }
            if (penCapture && penLostHandler && penCapture.removeEventListener) {
                penCapture.removeEventListener("lostpointercapture", penLostHandler);
            }
            if (penWindowUp) window.removeEventListener("pointerup", penWindowUp, true);
            if (penWindowCancel) window.removeEventListener("pointercancel", penWindowCancel, true);
            penCapture = null;
            penLostHandler = null;
            penWindowUp = null;
            penWindowCancel = null;
            penReleasing = false;
        }

        function clearPenPreview() {
            const host = ensureShell().querySelector("[data-abe-canvas]");
            if (host && CanvasRenderer && CanvasRenderer.patchPenPreview) CanvasRenderer.patchPenPreview(host, null);
        }

        function cancelPenStroke(sync) {
            const pointerId = penGesture && penGesture.pointerId();
            const active = Boolean(penGesture && penGesture.active());
            if (penGesture && penGesture.cancel) penGesture.cancel();
            penGesture = null;
            releasePenCapture(pointerId);
            clearPenPreview();
            if (sync && active) syncDrawing();
        }

        function paintPenPreview() {
            const host = ensureShell().querySelector("[data-abe-canvas]");
            const Space = drawingSpaceApi();
            if (!host || !store || !Space || !penGesture || !CanvasRenderer || !CanvasRenderer.patchPenPreview) return;
            const frame = drawingFrame(store.snapshot());
            const sampled = Space.penPreviewPoints ? Space.penPreviewPoints(penGesture.preview(), 480) : penGesture.preview();
            const points = sampled.map((point) => (frame ? Space.doorToWorld(frame, point.x, point.y) : point));
            CanvasRenderer.patchPenPreview(host, points);
        }

        function beginPenStroke(event, mapped) {
            const door = mapped && mapped.door;
            if (!event || event.button !== 0 || spaceHeld || event.isPrimary === false || !door) return false;
            if (penGesture && penGesture.active()) return event.pointerId === penGesture.pointerId();
            const Space = drawingSpaceApi();
            if (!Space || typeof Space.createPenGesture !== "function") return false;
            const snapped = mapped.frame
                ? resolveSmartPoint(door, { alt: event.altKey === true, frame: mapped.frame })
                : door;
            penGesture = Space.createPenGesture(penSmoothing);
            if (!penGesture.pointerDown({ pointerId: event.pointerId, x: snapped.x, y: snapped.y })) {
                penGesture = null;
                return false;
            }
            penClosePathId = null;
            const stage = ensureShell().querySelector("[data-abe-stage]");
            const captureNode = event.currentTarget && event.currentTarget.setPointerCapture ? event.currentTarget : stage;
            penCapture = captureNode;
            penLostHandler = () => {
                if (!penReleasing && penGesture && penGesture.active()) cancelPenStroke(true);
            };
            if (captureNode && captureNode.addEventListener) captureNode.addEventListener("lostpointercapture", penLostHandler);
            if (captureNode && captureNode.setPointerCapture) {
                try { captureNode.setPointerCapture(event.pointerId); } catch (err) { void err; }
            }
            const pointerId = event.pointerId;
            penWindowUp = (upEvent) => {
                if (!upEvent || upEvent.pointerId !== pointerId) return;
                finishPenStroke(upEvent);
            };
            penWindowCancel = (cancelEvent) => {
                if (!cancelEvent || cancelEvent.pointerId !== pointerId) return;
                cancelPenStroke(true);
            };
            window.addEventListener("pointerup", penWindowUp, true);
            window.addEventListener("pointercancel", penWindowCancel, true);
            paintPenPreview();
            return true;
        }

        function updatePenPointer(event) {
            if (drawingTool !== "pen" || !penGesture || !penGesture.active() || !event || !store) return false;
            if (event.pointerId !== penGesture.pointerId()) return true;
            if (spaceHeld) {
                cancelPenStroke(true);
                return true;
            }
            const mapped = doorPointFromEvent(store.snapshot(), event);
            if (mapped) {
                penGesture.pointerMove({ pointerId: event.pointerId, x: mapped.door.x, y: mapped.door.y });
                resolveSmartPoint(mapped.door, { alt: event.altKey === true, frame: mapped.frame });
                const host = ensureShell().querySelector("[data-abe-canvas]");
                if (host && CanvasRenderer && CanvasRenderer.patchDrawingPreview) {
                    CanvasRenderer.patchDrawingPreview(host, null, snapOverlay, null);
                }
            }
            paintPenPreview();
            return true;
        }

        function finishPenStroke(event) {
            if (!penGesture || !penGesture.active()) return;
            if (event && event.pointerId != null && penGesture.pointerId() !== event.pointerId) return;
            const mapped = event && store ? doorPointFromEvent(store.snapshot(), event) : null;
            const snapped = mapped && mapped.door
                ? resolveSmartPoint(mapped.door, { alt: event.altKey === true, frame: mapped.frame })
                : null;
            const sample = {
                pointerId: penGesture.pointerId(),
                x: snapped ? snapped.x : (mapped ? mapped.door.x : null),
                y: snapped ? snapped.y : (mapped ? mapped.door.y : null),
            };
            penCommitting = true;
            let built = null;
            try {
                built = penGesture.pointerUp(sample);
            } finally {
                const pointerId = penGesture && penGesture.pointerId();
                penGesture = null;
                releasePenCapture(pointerId);
                clearPenPreview();
                penCommitting = false;
            }
            if (!built || built.ok !== true || !drawingSession) {
                const record = activeDrawingRecord();
                if (record && built && built.messageKey) {
                    record.messageKey = built.messageKey;
                    record.errorCode = built.code || "";
                }
                penClosePathId = null;
                syncDrawing();
                return;
            }
            const created = drawingSession.createPenPath(built);
            const record = activeDrawingRecord();
            penClosePathId = created && built.suggestClose && record && record.selection ? record.selection.pathId : null;
            syncDrawing();
        }

        function toggleSnapMenu() {
            const view = store && store.snapshot();
            if (!view || view.editorMode !== "drawing" || !view.drawingTarget || view.drawingTarget.canEdit !== true) return;
            snapMenuOpen = snapMenuOpen !== true;
            syncDrawing();
        }

        function setSnapOption(name, value) {
            const Snap = drawingSnapApi();
            const next = snapState();
            if (name === "spacing") next.spacing = Number(value);
            else next[name] = value === true || value === "true" || value === "1";
            snapSettings = Snap && Snap.normalizeSettings ? Snap.normalizeSettings(next) : next;
            snapHold = null;
            if (!snapSettings.enabled) snapOverlay = null;
            syncDrawing();
        }

        function setPenSmoothing(level) {
            const Space = drawingSpaceApi();
            penSmoothing = Space && Space.penLevel ? Space.penLevel(level).id : "low";
            syncDrawing();
        }

        function setDrawingTool(tool) {
            if (tool !== "polyline" && tool !== "select" && tool !== "shapes" && tool !== "node_edit" && tool !== "pen") return;
            endVectorGesture("cancel");
            cancelPenStroke(false);
            const view = store && store.snapshot();
            if (!view || view.editorMode !== "drawing" || !view.drawingTarget || view.drawingTarget.canEdit !== true) return;
            drawingTool = tool;
            drawingPointer = null;
            shapeAnchor = null;
            shapeEntry = {};
            snapHold = null;
            snapOverlay = null;
            resetDrawingEntry();
            const record = activeDrawingRecord();
            if (record) record.measureError = null;
            syncDrawing();
        }

        function applyDistribution(command) {
            if (!layoutCommandsAllowed() || !store || !Distribution || typeof command !== "function") return;
            finishActiveGesture();
            const result = command();
            if (!result || !result.ok) return;
            store.commitSession(result.session);
            store.selectSheet(null);
        }

        let lastPositionRejectAt = 0;

        function readSelectionPositionModel(preferredKey) {
            const PositionGeometry = window.AlmdinaBoardEditor.PositionGeometry;
            if (!store || !PositionGeometry) return null;
            const view = store.snapshot();
            const keys = Array.isArray(view.selectedPieceKeys)
                ? view.selectedPieceKeys.filter(Boolean)
                : [];
            if (typeof PositionGeometry.selectionPositionModel === "function") {
                return PositionGeometry.selectionPositionModel(view.session, keys);
            }
            if (preferredKey) {
                return PositionGeometry.boardPositionForPiece(view.session, preferredKey);
            }
            return keys.length === 1
                ? PositionGeometry.boardPositionForPiece(view.session, keys[0])
                : null;
        }

        function applyPrecisionPosition(proposeFn, pieceKey) {
            // Shared path for X/Y fields, +/−, and keyboard nudges — validation only,
            // no magnet/snap (proposeGroupMove is exact millimetre deltas).
            const PositionGeometry = window.AlmdinaBoardEditor.PositionGeometry;
            const MoveGeometryLocal = window.AlmdinaBoardEditor.MoveGeometry;
            if (!layoutCommandsAllowed() || !store || !PositionGeometry || !MoveGeometryLocal || typeof proposeFn !== "function") {
                return { ok: false, reason: "Position controls unavailable." };
            }
            const snap = store.snapshot();
            const proposal = proposeFn();
            const readModel = () => {
                if (proposal && proposal.mixed) {
                    return readSelectionPositionModel(pieceKey);
                }
                if (pieceKey) {
                    return PositionGeometry.boardPositionForPiece(
                        store.snapshot().session,
                        pieceKey
                    );
                }
                return readSelectionPositionModel(pieceKey);
            };
            if (!proposal || !proposal.ok) {
                const now = Date.now();
                if (now - lastPositionRejectAt > 500) {
                    store.setDropMessage(__((proposal && proposal.reason) || "Position update rejected."));
                    lastPositionRejectAt = now;
                }
                return {
                    ok: false,
                    reason: proposal && proposal.reason,
                    model: readModel(),
                };
            }
            if (proposal.unchanged) {
                return { ok: true, unchanged: true, model: proposal.current || readModel() };
            }
            finishActiveGesture();
            let next = snap.session;
            (proposal.commands || []).forEach((command) => {
                next = MoveGeometryLocal.applyPieceMove(next, command);
            });
            store.commitSession(next);
            store.setDropMessage(null);
            // After commit, re-read from the live session. Mixed group models stay Mixed.
            return {
                ok: true,
                unchanged: false,
                model: readModel(),
            };
        }

        function applyAlignment(mode) {
            const AlignmentGeometry = window.AlmdinaBoardEditor.AlignmentGeometry;
            const MoveGeometryLocal = window.AlmdinaBoardEditor.MoveGeometry;
            if (!layoutCommandsAllowed() || !store || !AlignmentGeometry || !MoveGeometryLocal) return { ok: false };
            finishActiveGesture();
            const view = store.snapshot();
            const proposal = AlignmentGeometry.proposeAlignment(
                view.session,
                view.selectedPieceKeys || [],
                mode
            );
            if (!proposal || !proposal.ok) {
                store.setDropMessage(__((proposal && proposal.reason) || "Alignment rejected."));
                return { ok: false, reason: proposal && proposal.reason };
            }
            if (proposal.unchanged) {
                store.setDropMessage(null);
                return { ok: true, unchanged: true };
            }
            let next = view.session;
            (proposal.commands || []).forEach((command) => {
                next = MoveGeometryLocal.applyPieceMove(next, command);
            });
            store.commitSession(next);
            store.setDropMessage(null);
            return { ok: true, unchanged: false };
        }

        function inspectorHandlers() {
            return {
                setPieceClassification: (pieceKey, resourceKind, parties) => {
                    if (!layoutCommandsAllowed() || !store || !SessionDocument || typeof SessionDocument.classifyPiece !== "function") {
                        return { ok: false };
                    }
                    finishActiveGesture();
                    const result = SessionDocument.classifyPiece(
                        store.snapshot().session,
                        pieceKey,
                        resourceKind,
                        parties
                    );
                    if (!result || !result.ok) {
                        if (window.frappe && frappe.show_alert) {
                            frappe.show_alert({
                                message: translate("Could not change the piece classification."),
                                indicator: "orange",
                            }, 4);
                        }
                        return result || { ok: false };
                    }
                    store.commitSession(result.session);
                    return result;
                },
                applyPositionAxis: (pieceKey, axis, value, options) => {
                    const PositionGeometry = window.AlmdinaBoardEditor.PositionGeometry;
                    const opts = options || {};
                    const view = store.snapshot();
                    const keys = Array.isArray(view.selectedPieceKeys)
                        ? view.selectedPieceKeys.filter(Boolean)
                        : [];
                    if (opts.mixed || (keys.length > 1)) {
                        const propose = opts.step
                            ? () => PositionGeometry.proposeGroupAxisStep(
                                store.snapshot().session,
                                keys,
                                axis,
                                value
                            )
                            : () => PositionGeometry.proposeGroupAxisRelative(
                                store.snapshot().session,
                                keys,
                                axis,
                                value
                            );
                        return applyPrecisionPosition(propose, pieceKey || keys[0]);
                    }
                    return applyPrecisionPosition(
                        () => PositionGeometry.proposeAxisMove(
                            store.snapshot().session,
                            pieceKey || keys[0],
                            axis,
                            value
                        ),
                        pieceKey || keys[0]
                    );
                },
                readPositionModel: (pieceKey) => readSelectionPositionModel(pieceKey),
                onPositionRejected: (message) => {
                    if (!store) return;
                    store.setDropMessage(__(message || "Enter a valid millimetre value."));
                },
                applyAlignment: (mode) => applyAlignment(mode),
                setPieceEdgeBandVisible: (pieceKey, visible) => {
                    if (!store) return;
                    store.setPieceEdgeBandVisible(pieceKey, visible);
                },
            };
        }

        function nudgeSelectedPieceByArrow(event) {
            if (!layoutCommandsAllowed() || !store || suspended || !event) return false;
            if (isEditableTarget(event.target)) return false;
            if (event.metaKey || event.ctrlKey || event.altKey) return false;
            const key = event.key;
            if (key !== "ArrowUp" && key !== "ArrowDown" && key !== "ArrowLeft" && key !== "ArrowRight") {
                return false;
            }
            const PositionGeometry = window.AlmdinaBoardEditor.PositionGeometry;
            if (!PositionGeometry) return false;
            const view = store.snapshot();
            const keys = Array.isArray(view.selectedPieceKeys)
                ? view.selectedPieceKeys.filter(Boolean)
                : [];
            if (!keys.length) return false;

            if (keys.length === 1) {
                if (typeof PositionGeometry.proposeKeyboardNudge !== "function") return false;
                const model = PositionGeometry.boardPositionForPiece(view.session, keys[0]);
                if (!model || !model.editable) return false;
                event.preventDefault();
                applyPrecisionPosition(
                    () => PositionGeometry.proposeKeyboardNudge(store.snapshot().session, keys[0], key),
                    keys[0]
                );
                return true;
            }

            if (typeof PositionGeometry.proposeSelectionKeyboardNudge !== "function") return false;
            const groupModel = typeof PositionGeometry.selectionPositionModel === "function"
                ? PositionGeometry.selectionPositionModel(view.session, keys)
                : null;
            if (!groupModel || !groupModel.editable) {
                if (groupModel && groupModel.reason) {
                    const now = Date.now();
                    if (now - lastPositionRejectAt > 500) {
                        store.setDropMessage(__(groupModel.reason));
                        lastPositionRejectAt = now;
                    }
                }
                return false;
            }
            event.preventDefault();
            applyPrecisionPosition(
                () => PositionGeometry.proposeSelectionKeyboardNudge(
                    store.snapshot().session,
                    keys,
                    key
                ),
                keys[0]
            );
            return true;
        }

        function paint() {
            if (!store || suspended) return;
            syncEditorHeight();
            syncDrawing();
            const view = store.snapshot();
            view.drawingsDirty = Boolean(drawingSession && drawingSession.anyDirty());
            view.savedDrawingReady = savedDrawingReady(view);
            paintPageActions(view);
            const root = ensureShell().querySelector(".abe-root");
            if (!root) return;
            const sidebar = root.querySelector("[data-abe-sidebar]");
            const canvas = root.querySelector("[data-abe-canvas]");
            const rightSidebar = root.querySelector("[data-abe-right-sidebar-host]");
            SidebarRenderer.render(sidebar, view, {
                setLayerVisible: (key, visible) => store.setLayerVisible(key, visible),
                setAllLayersVisible: (visible) => store.setAllLayersVisible(visible),
                showOnlyLayer: (key) => store.showOnlyLayer(key),
                setShowEdgeBands: (visible) => store.setShowEdgeBands(visible),
                edgeBandGlobalUiState: () => store.edgeBandGlobalUiState(),
                toggleSheet: (sheetNo) => store.toggleSheetExpanded(sheetNo),
                selectSheet: (sheetNo) => {
                    store.selectSheet(sheetNo);
                    revealSheet(sheetNo);
                },
                returnPiece: (pieceKey) => {
                    if (!layoutCommandsAllowed() || !store || !Distribution) return;
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
                    endVectorGesture("cancel");
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
                addBoard: () => {
                    if (!layoutCommandsAllowed() || !store || !SessionDocument || typeof SessionDocument.addFullBoard !== "function") return;
                    finishActiveGesture();
                    const current = store.snapshot();
                    const result = SessionDocument.addFullBoard(current.session, current.projection);
                    if (!result || !result.ok) {
                        if (window.frappe && frappe.show_alert) {
                            frappe.show_alert({
                                message: translate(
                                    result && result.code === "standard_board_unavailable"
                                        ? "A new board cannot be created because the order's standard board dimensions are missing or invalid."
                                        : "Could not add a board."
                                ),
                                indicator: "orange",
                            }, 5);
                        }
                        return;
                    }
                    store.commitSession(result.session);
                    store.selectSheet(result.sheet_no);
                },
            });
            if (RightSidebarRenderer && typeof RightSidebarRenderer.render === "function") {
                RightSidebarRenderer.render(rightSidebar, view, inspectorHandlers());
            }
            view.proposedCuts = proposedCutsFor(view);
            lastCanvasApi = CanvasRenderer.render(canvas, view, {
                selectPiece: (pieceId, elementId) => {
                    endVectorGesture("cancel");
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
                setEditorMode: (mode) => setEditorMode(mode),
                setDrawingTool: (tool) => setDrawingTool(tool),
                toggleSnapMenu: () => toggleSnapMenu(),
                toggleReferenceMenu: () => toggleReferenceMenu(),
                uploadReferenceFiles: (files) => uploadReferenceFiles(files),
                selectReference: (id) => {
                    if (drawingSession.selectReference(id)) syncDrawing();
                },
                referenceAction: (action, id) => referenceAction(action, id),
                commitReferenceField: (field, value) => commitReferenceField(field, value),
                setReferenceAspect: (locked) => {
                    referenceAspectLock = locked !== false;
                },
                referencePointerDown: (event) => {
                    const handle = event.target && event.target.closest && event.target.closest("[data-abe-reference-handle]");
                    const record = activeDrawingRecord();
                    const mapped = store && doorPointFromEvent(store.snapshot(), event);
                    const id = handle && handle.getAttribute("data-abe-reference-id");
                    const reference = record && (record.document.references || []).find((row) => row.id === id);
                    if (!reference || reference.locked || !mapped) return;
                    drawingSession.selectReference(reference.id);
                    beginReferenceDrag(reference, handle.getAttribute("data-abe-reference-handle") || "move", mapped.door);
                },
                setSnapOption: (name, value) => setSnapOption(name, value),
                setPenSmoothing: (level) => setPenSmoothing(level),
                setShapeKind: (kind) => {
                    drawingShapeKind = kind || "rectangle";
                    shapeAnchor = null;
                    shapeEntry = {};
                    if (drawingTool !== "shapes") setDrawingTool("shapes");
                    else syncDrawing();
                },
                onShapeInput: (key, value) => {
                    if (key) shapeEntry[key] = value == null ? "" : String(value);
                },
                commitShapeForm: () => commitShapeForm(),
                drawingAction: (action) => drawingAction(action),
                drawingHistory: (direction) => applyDrawingHistory(direction),
                drawingPointerDown: (event) => drawingPointerDown(event),
                commitDrawingHud: (lengthText, angleText, sourceField) => commitDrawingHud(lengthText, angleText, sourceField),
                onDrawingMeasureInput: (field, value) => {
                    rememberMeasureInput(field, value);
                    const record = activeDrawingRecord();
                    if (record && record.measureError) record.measureError = null;
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    const error = host && host.querySelector("[data-abe-drawing-measure-error]");
                    if (error && error.remove) error.remove();
                    refreshTypedPreviewFromEntry();
                },
                cancelDrawingPreview: () => {
                    drawingPointer = null;
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    if (host && CanvasRenderer && CanvasRenderer.patchDrawingPreview) {
                        CanvasRenderer.patchDrawingPreview(host, null, null, null);
                    }
                    if (drawingSession && drawingSession.escape()) syncDrawing();
                },
                toggleMagnet: () => {
                    if (!layoutCommandsAllowed()) return;
                    store.toggleMagnet();
                    if (moveInteraction && moveInteraction.refreshPreviewFromPointer) {
                        moveInteraction.refreshPreviewFromPointer();
                    }
                },
                undo: () => {
                    if (!layoutCommandsAllowed()) return;
                    store.undo();
                },
                redo: () => {
                    if (!layoutCommandsAllowed()) return;
                    store.redo();
                },
                restoreEntry: () => {
                    if (!layoutCommandsAllowed()) return;
                    store.restoreEntry();
                },
                removePiece: (pieceKey) => applyDistribution(() => {
                    const view = store.snapshot();
                    const key = pieceKey || view.selectedPieceKey;
                    return Distribution.excludePiece(view.session, key);
                }),
                removeBoard: (sheetNo) => applyDistribution(() => {
                    const view = store.snapshot();
                    return Distribution.removeBoard(view.session, sheetNo == null ? view.selectedSheetNo : sheetNo);
                }),
                toggleMeasureTool: () => {
                    if (!layoutCommandsAllowed() || !store) return;
                    const next = !store.snapshot().measureToolActive;
                    store.setMeasureToolActive(next);
                    if (measureInteraction) {
                        if (next) {
                            measureInteraction.clearAltOverlay();
                            if (moveInteraction && moveInteraction.cancel) moveInteraction.cancel();
                            if (rotationInteraction && rotationInteraction.cancel) rotationInteraction.cancel();
                        } else {
                            measureInteraction.clearToolLine();
                        }
                    }
                },
                beginMeasureGesture: (event) => (
                    layoutCommandsAllowed()
                    && measureInteraction
                    && measureInteraction.beginTool(event)
                ),
                beginPieceGesture: (pieceKey, event, meta) => {
                    if (store && store.snapshot().measureToolActive) {
                        return measureInteraction && measureInteraction.beginTool(event);
                    }
                    if (rotationInteraction && rotationInteraction.isActive()) return false;
                    return moveInteraction && moveInteraction.beginPieceGesture(pieceKey, event, meta);
                },
                beginBoardGesture: (sheetNo, event) => {
                    if (store && store.snapshot().measureToolActive) {
                        return measureInteraction && measureInteraction.beginTool(event);
                    }
                    return moveInteraction && moveInteraction.beginBoardGesture(sheetNo, event);
                },
                beginRotateGesture: (pieceKey, event) => {
                    if (!layoutCommandsAllowed()) return false;
                    if (store && store.snapshot().measureToolActive) return false;
                    if (moveInteraction && moveInteraction.onPanIntent) moveInteraction.onPanIntent();
                    return rotationInteraction && rotationInteraction.beginHandleGesture(pieceKey, event);
                },
                applyAngle: (pieceKey, value) => (
                    rotationInteraction && rotationInteraction.applyNumericAngle(pieceKey, value)
                ),
                toggleAngle0_180: (pieceKey) => toggleAngle0_180(pieceKey),
                toggleAngle90_270: (pieceKey) => toggleAngle90_270(pieceKey),
                rotateByDegrees: (pieceKey, delta) => rotateByDegrees(pieceKey, delta),
                mirrorAngle: (pieceKey) => mirrorAngle(pieceKey),
                onStagePointerMove: (event) => {
                    if (vectorGesture) return;
                    if (updateReferencePointer(event)) return;
                    if (updatePenPointer(event)) return;
                    updateShapePointer(event);
                    updateDrawingPointer(event);
                    // Keep Alt latch aligned with live modifier state (keyup can be lost
                    // after focus changes). Drag snap-bypass still reads the same flag.
                    const wasAltHeld = altHeld;
                    if (event && typeof event.altKey === "boolean") {
                        altHeld = Boolean(event.altKey);
                    }
                    if (measureInteraction && (
                        measureInteraction.isToolGestureActive()
                        || (store && store.snapshot().measureToolActive)
                        || altHeld
                        || wasAltHeld
                        || (event && event.altKey)
                        || (measureInteraction.hasAltOverlay && measureInteraction.hasAltOverlay())
                    )) {
                        measureInteraction.onPointerMove(event);
                        if (measureInteraction.isToolGestureActive() || (store && store.snapshot().measureToolActive)) {
                            return;
                        }
                    }
                    if (rotationInteraction && rotationInteraction.isActive()) {
                        rotationInteraction.onPointerMove(event);
                        return;
                    }
                    if (moveInteraction) moveInteraction.onPointerMove(event);
                },
                onStagePointerUp: (event) => {
                    finishReferenceDrag();
                    finishPenStroke(event);
                    if (vectorGesture && event && event.pointerId === vectorGesture.pointerId) endVectorGesture("commit");
                    snapHold = null;
                    snapOverlay = null;
                    if (drawingPointer) drawingPointer.snap = null;
                    const snapHost = ensureShell().querySelector("[data-abe-canvas]");
                    if (snapHost && CanvasRenderer && CanvasRenderer.patchDrawingPreview && store && store.snapshot().editorMode === "drawing") {
                        CanvasRenderer.patchDrawingPreview(
                            snapHost,
                            drawingPointer && drawingPointer.preview,
                            null,
                            drawingPointer ? {
                                lengthMm: drawingPointer.lengthMm,
                                angleDeg: drawingPointer.angleDeg,
                                clientX: drawingPointer.clientX,
                                clientY: drawingPointer.clientY,
                            } : null
                        );
                    }
                    if (measureInteraction && (
                        measureInteraction.isToolGestureActive()
                        || (store && store.snapshot().measureToolActive)
                    )) {
                        measureInteraction.onPointerUp(event);
                        return;
                    }
                    if (rotationInteraction && rotationInteraction.isActive()) {
                        rotationInteraction.onPointerUp(event);
                        return;
                    }
                    if (moveInteraction) moveInteraction.onPointerUp(event);
                },
                onStagePointerCancel: (event) => {
                    if (vectorGesture && event && event.pointerId === vectorGesture.pointerId) endVectorGesture("cancel");
                    if (penGesture && event && event.pointerId === penGesture.pointerId()) cancelPenStroke(true);
                    if (measureInteraction) measureInteraction.onPointerCancel(event);
                    if (rotationInteraction) rotationInteraction.onPointerCancel(event);
                    if (moveInteraction) moveInteraction.onPointerCancel(event);
                },
                onPanIntent: () => {
                    cancelPenStroke(true);
                    if (measureInteraction && measureInteraction.cancel) measureInteraction.cancel();
                    if (rotationInteraction) rotationInteraction.cancel();
                    if (moveInteraction) moveInteraction.onPanIntent();
                },
                consumeClickSuppression: () => (
                    moveInteraction ? moveInteraction.consumeClickSuppression() : false
                ),
                zoom: (factor) => zoomByFactor(factor, zoomFocalClient(null)),
                onBack: () => backToOrder(activeOrderName),
                readScroll: () => liveScroll,
                onScroll: (x, y) => {
                    liveScroll = { x: Number(x) || 0, y: Number(y) || 0 };
                    if (liveScroll.x > 1 || liveScroll.y > 1) scrollOwned = true;
                },
                onCanvasPointerMove: (event) => {
                    if (!event) return;
                    lastCanvasPointerClient = { x: event.clientX, y: event.clientY };
                },
                takeCamera: (token) => {
                    if (token === appliedCamera) return false;
                    appliedCamera = token;
                    return true;
                },
                persistCamera,
                isPanKey: () => spaceHeld,
                fitAll: () => fitCurrentBoards(),
                saveDraft: () => saveDraft(),
                reviewDraft: () => reviewDraft(),
                createPlanCopy: () => createPlanCopy(),
            });
            restoreDrawingMeasureFocus(canvas);
            syncReviewDialog(view);
            if (!view.viewport.opened && !view.viewport.userAdjusted) scheduleOpeningCamera();
        }

        function renderWorkspace(payload) {
            activeOrderName = payload.order_name || "";
            const banner = `${freshnessBannerHtml(payload)}${draftBannerHtml(payload)}${sourceViewBanner()}`;
            ensureShell().innerHTML = `
                <div class="almdina-ui alm-page--workbench abe-page abe-root" dir="${esc(uiDirection())}">
                    ${banner}
                    <div class="abe-body">
                        <aside data-abe-sidebar class="abe-sidebar-host"></aside>
                        <section data-abe-canvas class="abe-canvas-host"></section>
                        <aside data-abe-right-sidebar-host class="abe-right-sidebar-host"></aside>
                    </div>
                    <div class="abe-review-dialog" data-abe-review hidden></div>
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
            const orderName = String(context.orderName || "").trim();
            const planName = String(context.planName || "").trim();
            if (
                store
                && !opts.acceptSourceChange
                && editorDirty()
                && (orderName !== activeOrderName || planName !== loadedPlanName)
            ) {
                if (!confirmLeave()) return;
            }
            const openGeneration = ++generation;
            suspended = false;
            clearFreshnessRetry();
            pendingSourceConflict = null;
            const requestToken = requestGate.begin();
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
                finishActiveGesture();
                measureArmedBeforeDrawing = false;
                if (drawingSession) drawingSession.reset();
                drawingTool = "select";
                drawingPointer = null;
                drawingPartialMessage = "";
                if (unsubscribe) unsubscribe();
                store = createStore(payload);
                ensureSession(payload, {
                    applySavedDraft: context.applySavedDraft !== false,
                });
                leaveConfirmed = false;
                installLeaveGuards();
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
                        ? translate("You do not have permission to use the board editor.")
                        : missing
                            ? translate("The selected cutting plan is not available for this order.")
                            : translate("Reload the page or return to the order and try again."),
                    recoveryActions()
                );
                bindStateActions(orderName, context);
            }
        }

        function suspend() {
            endVectorGesture("cancel");
            cancelPenStroke(false);
            if (moveInteraction) moveInteraction.cancel();
            if (measureInteraction) measureInteraction.clearAll();
            suspended = true;
            generation += 1;
            requestGate.invalidate();
            clearFreshnessRetry();
            pendingSourceConflict = null;
            closeReviewDialog();
            if (unsubscribe) {
                unsubscribe();
                unsubscribe = null;
            }
            store = null;
            if (drawingSession) drawingSession.reset();
            drawingTool = "select";
            drawingPointer = null;
            drawingPartialMessage = "";
            moveInteraction = null;
            rotationInteraction = null;
            measureInteraction = null;
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
                    node.classList.remove("abe-shell-host");
                    node.style.minHeight = "";
                    node.style.height = "";
                    node.style.overflow = "";
                });
            }
            removeLeaveGuards();
            lifecycle.dispose();
        }

        async function saveDraft(options) {
            const forceDistribution = Boolean(options && options.forceDistribution);
            if (!store || !activeOrderName || !loadedPlanName) return false;
            const view = store.snapshot();
            const drawings = drawingSession ? drawingSession.dirtyRecords() : [];
            const persistDistribution = Boolean(view.distributionDirty || forceDistribution);
            if (!view.canSaveLayout || view.saveInFlight || !view.session) return false;
            if (!persistDistribution && !drawings.length) return true;
            const sentFingerprint = SessionDocument.distributionFingerprint(view.session);
            const sourceContentRevision = contentRevisionToken(view.payload || {});
            if (!store.beginDraftSave()) return false;
            let distributionSaved = !persistDistribution;
            try {
                if (persistDistribution) {
                    const response = await Api.saveDraft({
                        orderName: activeOrderName,
                        planName: loadedPlanName,
                        expectedDraftVersion: view.draftVersion || 0,
                        sourceContentRevision,
                        layout: SessionDocument.exportLayout(view.session),
                    });
                    if (!store) return false;
                    store.settleDraftSave(sentFingerprint, response || { ok: false, code: "failed" });
                    distributionSaved = Boolean(response && response.ok !== false);
                    if (!distributionSaved) return false;
                    if (drawings.length && store && !store.snapshot().saveInFlight) store.beginDraftSave();
                }
                let failed = false;
                for (let index = 0; index < drawings.length; index += 1) {
                    const record = drawings[index];
                    let response = null;
                    try {
                        response = await Api.saveDrawing({
                            orderName: activeOrderName,
                            planName: loadedPlanName,
                            pieceInstanceId: record.pieceInstanceId,
                            expectedDrawingVersion: record.drawingVersion,
                            sourceContentRevision,
                            drawing: record.document,
                        });
                    } catch (error) {
                        response = { ok: false, code: "save_failed" };
                    }
                    if (!drawingSession.applySave(record.pieceInstanceId, response)) {
                        failed = true;
                        break;
                    }
                }
                if (failed) {
                    drawingPartialMessage = distributionSaved && persistDistribution
                        ? "The layout was saved. This drawing is still here and was not saved."
                        : "Could not save the drawing. Your lines are still here.";
                    if (typeof frappe !== "undefined" && frappe.msgprint) {
                        frappe.msgprint({
                            title: __("Save layout"),
                            message: __(drawingPartialMessage),
                            indicator: "orange",
                        });
                    }
                    return false;
                }
                drawingPartialMessage = "";
                return true;
            } catch (error) {
                if (store && !distributionSaved) store.settleDraftSave(sentFingerprint, null);
                return false;
            } finally {
                if (store && store.snapshot().saveInFlight) {
                    const current = store.snapshot();
                    store.settleDraftSave(current.savedFingerprint, {
                        ok: true,
                        draft_version: current.draftVersion,
                    });
                }
                syncDrawing();
            }
        }

        async function reviewDraft() {
            if (!store || !activeOrderName || !loadedPlanName) return;
            const view = store.snapshot();
            if (!view.session || view.reviewInFlight) return;
            if (view.distributionDirty) {
                if (typeof frappe !== "undefined" && frappe.msgprint) {
                    frappe.msgprint({
                        title: __("Review distribution"),
                        message: __("Save the current distribution before reviewing it. An older saved draft will not be shown as the current layout."),
                        indicator: "orange",
                    });
                }
                return;
            }
            const request = store.beginReview();
            if (!request) return;
            try {
                const response = await Api.reviewDraft({
                    orderName: activeOrderName,
                    planName: loadedPlanName,
                });
                if (!store) return;
                store.settleReview(request, response || null);
            } catch (error) {
                if (!store) return;
                store.settleReview(request, null);
                if (typeof frappe !== "undefined" && frappe.msgprint) {
                    frappe.msgprint({
                        title: __("Review distribution"),
                        message: __("Review failed. Your edits and selection are still here."),
                        indicator: "red",
                    });
                }
            }
        }

        function rememberApplyReturnContext(orderName, planName) {
            const key = String(orderName || "").trim();
            const plan = String(planName || "").trim();
            if (!key || !plan || typeof window === "undefined" || !window.sessionStorage) return;
            try {
                // Prefer the Edited plan tab once the matching board_editor_draft row
                // is authorized for display. The structured apply-return payload carries
                // the concrete plan_name so the order workspace can invalidate stale
                // reads instead of trusting a bare reload flag.
                window.sessionStorage.setItem(`almdina.dco.planTab.${key}`, "BoardEditor");
                window.sessionStorage.setItem(
                    `almdina.dco.planApplyReturn.${key}`,
                    JSON.stringify({
                        order_name: key,
                        plan_name: plan,
                        prefer_tab: "BoardEditor",
                    })
                );
            } catch (error) {
                // sessionStorage may be unavailable; returning to the order still works.
            }
        }

        function drawingVersionPayload() {
            const versions = {};
            if (!drawingSession || typeof drawingSession.loadedRecords !== "function") return "";
            drawingSession.loadedRecords().forEach((record) => {
                if (record && record.pieceInstanceId && Number(record.drawingVersion) > 0) {
                    versions[record.pieceInstanceId] = Number(record.drawingVersion);
                }
            });
            return JSON.stringify(versions);
        }

        function revealCutProblem(response) {
            if (!store || !response) return;
            pendingCutPieceId = String(response.piece_instance_id || "");
            pendingCutPathId = String(response.path_id || "");
            const session = store.snapshot().session;
            if (!session || !pendingCutPieceId) return;
            const piece = Object.values(session.pieces || {}).find((row) => (
                String(row.piece_instance_id || "") === pendingCutPieceId
            ));
            if (!piece) return;
            store.selectPiece(piece.piece_id, {
                pieceKey: piece.piece_key,
                sheetNo: piece.sheet_no,
                expandSheet: true,
                elementId: null,
            });
            setEditorMode("drawing");
            syncDrawing();
        }

        async function createPlanCopy() {
            if (!store || !activeOrderName || !loadedPlanName) return;
            const view = store.snapshot();
            if (!view.session || view.createPlanInFlight || view.sourceOnly || view.canSaveLayout === false) return;
            const needsDistribution = Boolean(view.distributionDirty || !(Number(view.draftVersion) > 0));
            const needsDrawings = Boolean(drawingSession && drawingSession.dirtyRecords().length);
            if (needsDistribution || needsDrawings) {
                const saved = await saveDraft({ forceDistribution: needsDistribution });
                const afterSave = store && store.snapshot();
                const distributionBlocked = !afterSave || afterSave.distributionDirty || !(Number(afterSave.draftVersion) > 0);
                if (!store || saved !== true || distributionBlocked || (drawingSession && drawingSession.dirtyRecords().length)) {
                    if (typeof frappe !== "undefined" && frappe.msgprint) {
                        frappe.msgprint({
                            title: __("Apply to cutting plan"),
                            message: distributionBlocked
                                ? __("Save the board editor distribution before applying it to the cutting plan.")
                                : __("Save the door drawings before copying the cutting plan."),
                            indicator: "orange",
                        });
                    }
                    return;
                }
            }
            const latest = store.snapshot();
            if (!latest.session || latest.distributionDirty || !(Number(latest.draftVersion) > 0)) {
                if (typeof frappe !== "undefined" && frappe.msgprint) {
                    frappe.msgprint({
                        title: __("Apply to cutting plan"),
                        message: __("Save the board editor distribution before applying it to the cutting plan."),
                        indicator: "orange",
                    });
                }
                return;
            }
            const request = store.beginCreatePlan();
            if (!request) return;
            const draft = (latest.payload && latest.payload.editor_draft) || {};
            const planMeta = (latest.payload && latest.payload.plan) || {};
            try {
                const response = await Api.createPlanCopy({
                    orderName: activeOrderName,
                    planName: loadedPlanName,
                    expectedDraftVersion: request.draftVersion,
                    sourceContentRevision: contentRevisionToken(latest.payload || {}),
                    sourceInputFingerprint: String(planMeta.input_fingerprint || ""),
                    createRequestId: request.requestId,
                    draftName: String(draft.name || ""),
                    drawingVersions: drawingVersionPayload(),
                });
                if (!store) return;
                store.settleCreatePlan(response || null);
                if (response && response.ok && response.plan_name && typeof frappe !== "undefined") {
                    const planName = String(response.plan_name);
                    const orderName = String(
                        (response.order_name && String(response.order_name).trim())
                        || activeOrderName
                    );
                    rememberApplyReturnContext(orderName, planName);
                    frappe.show_alert({
                        message: __(
                            "The edited layout was applied as cutting plan {0}. It is not approved."
                        ).replace("{0}", frappe.utils.escape_html(planName)),
                        indicator: "green",
                    }, 8);
                    leaveConfirmed = true;
                    backToOrder(orderName);
                } else if (typeof frappe !== "undefined" && frappe.msgprint) {
                    const code = String((response && response.code) || "");
                    const title = code === "geometry_rejected"
                        ? __("Invalid cut outline")
                        : ((code === "version_conflict" || code === "source_conflict" || code === "source_changed" || code === "drawing_version_conflict")
                            ? __("Could not apply layout")
                            : __("Apply to cutting plan"));
                    frappe.msgprint({
                        title,
                        message: (response && response.message)
                            || __("The layout could not be applied to a cutting plan."),
                        indicator: "orange",
                    });
                    if (code === "geometry_rejected") revealCutProblem(response);
                }
            } catch (error) {
                if (!store) return;
                store.settleCreatePlan(null);
                if (typeof frappe !== "undefined" && frappe.msgprint) {
                    frappe.msgprint({
                        title: __("Apply to cutting plan"),
                        message: __("Applying the layout to a cutting plan failed. The saved draft is unchanged."),
                        indicator: "red",
                    });
                }
            }
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
        function isMeasureEnter(event) {
            if (!event || event.isComposing) return false;
            if (event.key === "Enter" || event.code === "Enter" || event.code === "NumpadEnter") return true;
            return (event.keyCode || event.which) === 13;
        }

        function isDrawingMeasureField(target) {
            if (!target || !target.getAttribute) return false;
            return Boolean(
                target.getAttribute("data-abe-drawing-length")
                || target.getAttribute("data-abe-drawing-angle")
            );
        }

        lifecycle.listen(window, "keydown", (event) => {
            if (isDrawingMeasureField(event.target) && isMeasureEnter(event)) {
                if (!event.defaultPrevented && drawingTool === "polyline") {
                    event.preventDefault();
                    const kind = event.target.getAttribute("data-abe-drawing-angle") ? "angle" : "length";
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    const bar = host && host.querySelector("[data-abe-drawing-measure]");
                    const lengthInput = bar && bar.querySelector("[data-abe-drawing-length]");
                    const angleInput = bar && bar.querySelector("[data-abe-drawing-angle]");
                    if (kind === "length" && lengthInput && lengthInput !== event.target) {
                        lengthInput.value = event.target.value;
                    }
                    if (kind === "angle" && angleInput && angleInput !== event.target) {
                        angleInput.value = event.target.value;
                    }
                    commitDrawingHud(
                        lengthInput ? lengthInput.value : event.target.value,
                        angleInput ? angleInput.value : "",
                        kind
                    );
                }
                return;
            }
            if (event.code === "Space" && !isEditableTarget(event.target)) {
                spaceHeld = true;
                if (penGesture && penGesture.active()) cancelPenStroke(true);
                if (moveInteraction) moveInteraction.onPanIntent();
            }
            if (event.key === "Alt" || event.code === "AltLeft" || event.code === "AltRight") {
                altHeld = true;
                if (moveInteraction && moveInteraction.refreshPreviewFromPointer) {
                    moveInteraction.refreshPreviewFromPointer();
                }
                if (measureInteraction && measureInteraction.refreshAltInspection) {
                    measureInteraction.refreshAltInspection();
                }
            }
            if (store && !layoutCommandsAllowed() && !isEditableTarget(event.target)) {
                const keyName = String(event.key || "");
                const modified = event.metaKey || event.ctrlKey;
                const undoKey = modified && (keyName.toLowerCase() === "z" || keyName.toLowerCase() === "y");
                const distributionKey = keyName === "Delete"
                    || keyName === "Backspace"
                    || keyName.indexOf("Arrow") === 0
                    || undoKey;
                if (distributionKey) {
                    event.preventDefault();
                    if (undoKey && drawingSession) {
                        applyDrawingHistory(event.shiftKey || keyName.toLowerCase() === "y" ? "redo" : "undo");
                    } else if ((keyName === "Delete" || keyName === "Backspace") && drawingSession && (drawingTool === "select" || drawingTool === "node_edit" || drawingTool === "shapes")) {
                        drawingSession.deleteSelection();
                        refreshCutValidation();
                        syncDrawing();
                    }
                    return;
                }
                if (keyName === "Enter" && drawingTool === "polyline") {
                    const host = ensureShell().querySelector("[data-abe-canvas]");
                    const lengthInput = host && host.querySelector("[data-abe-drawing-measure] [data-abe-drawing-length]");
                    const angleInput = host && host.querySelector("[data-abe-drawing-measure] [data-abe-drawing-angle]");
                    if (lengthInput && !lengthInput.disabled) {
                        event.preventDefault();
                        commitDrawingHud(lengthInput.value, angleInput && angleInput.value, "length");
                    }
                }
            }
            if (event.code === "Escape") {
                if (vectorGesture && !isEditableTarget(event.target)) {
                    event.preventDefault();
                    endVectorGesture("cancel");
                    return;
                }
                if (referenceCalibration && !isEditableTarget(event.target)) {
                    event.preventDefault();
                    referenceCalibration = null;
                    syncDrawing();
                    return;
                }
                if (penGesture && penGesture.active() && !isEditableTarget(event.target)) {
                    event.preventDefault();
                    cancelPenStroke(true);
                    return;
                }
                if (store && !layoutCommandsAllowed() && drawingSession && !isEditableTarget(event.target)) {
                    if (drawingSession.escape()) {
                        event.preventDefault();
                        drawingPointer = null;
                        syncDrawing();
                        return;
                    }
                }
                if (measureInteraction && measureInteraction.cancel && measureInteraction.cancel()) {
                    event.preventDefault();
                    return;
                }
                if (moveInteraction && moveInteraction.isActive()) {
                    moveInteraction.cancel();
                    event.preventDefault();
                    return;
                }
            }
            if (nudgeSelectedPieceByArrow(event)) return;
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
                if (measureInteraction && measureInteraction.clearAltOverlay) {
                    measureInteraction.clearAltOverlay();
                }
            }
        });
        lifecycle.listen(window, "blur", () => {
            altHeld = false;
            if (moveInteraction) moveInteraction.cancel();
            if (measureInteraction) measureInteraction.clearAll();
        });
        lifecycle.listen(window, "pagehide", () => {
            altHeld = false;
            if (moveInteraction) moveInteraction.cancel();
            if (measureInteraction) measureInteraction.clearAll();
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
