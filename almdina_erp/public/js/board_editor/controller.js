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

        function confirmLeave() {
            if (leaveConfirmed || !distributionDirty()) return true;
            const accepted = window.confirm(translate(
                "Board editor changes are not saved. Leave without saving?"
            ));
            if (accepted) leaveConfirmed = true;
            return accepted;
        }

        function installLeaveGuards() {
            removeLeaveGuards();
            beforeUnloadHandler = (event) => {
                if (!distributionDirty()) return;
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
            return distributionDirty();
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
            const target = event.target;
            if (target && target.closest && target.closest(".abe-float-tools, .abe-angle-field, .abe-angle-input")) {
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
                saveDraft: () => saveDraft(),
                reviewDraft: () => reviewDraft(),
                createPlanCopy: () => createPlanCopy(),
            });
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
            closeReviewDialog();
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
            removeLeaveGuards();
            lifecycle.dispose();
        }

        async function saveDraft() {
            if (!store || !activeOrderName || !loadedPlanName) return;
            const view = store.snapshot();
            if (!view.canSaveLayout || view.saveInFlight || !view.distributionDirty || !view.session) return;
            const sentFingerprint = SessionDocument.distributionFingerprint(view.session);
            const layout = SessionDocument.exportLayout(view.session);
            const expectedDraftVersion = view.draftVersion || 0;
            const sourceContentRevision = contentRevisionToken(view.payload || {});
            if (!store.beginDraftSave()) return;
            try {
                const response = await Api.saveDraft({
                    orderName: activeOrderName,
                    planName: loadedPlanName,
                    expectedDraftVersion,
                    sourceContentRevision,
                    layout,
                });
                if (!store) return;
                store.settleDraftSave(sentFingerprint, response || { ok: false, code: "failed" });
            } catch (error) {
                if (!store) return;
                store.settleDraftSave(sentFingerprint, null);
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

        function rememberPreferEditedPlanTab(orderName) {
            const key = String(orderName || "").trim();
            if (!key || typeof window === "undefined" || !window.sessionStorage) return;
            try {
                window.sessionStorage.setItem(`almdina.dco.planTab.${key}`, "BoardEditor");
                // Force the order plan workspace to reload so the new Edited plan
                // appears without a manual page refresh.
                window.sessionStorage.setItem(`almdina.dco.planWorkspaceReload.${key}`, "1");
            } catch (error) {
                // sessionStorage may be unavailable; returning to the order still works.
            }
        }

        async function createPlanCopy() {
            if (!store || !activeOrderName || !loadedPlanName) return;
            const view = store.snapshot();
            if (!view.session || view.createPlanInFlight) return;
            if (view.distributionDirty) {
                if (typeof frappe !== "undefined" && frappe.msgprint) {
                    frappe.msgprint({
                        title: __("Apply to cutting plan"),
                        message: __("Save the current distribution before applying it to the cutting plan."),
                        indicator: "orange",
                    });
                }
                return;
            }
            if (!(Number(view.draftVersion) > 0)) {
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
            const draft = (view.payload && view.payload.editor_draft) || {};
            const planMeta = (view.payload && view.payload.plan) || {};
            try {
                const response = await Api.createPlanCopy({
                    orderName: activeOrderName,
                    planName: loadedPlanName,
                    expectedDraftVersion: request.draftVersion,
                    sourceContentRevision: contentRevisionToken(view.payload || {}),
                    sourceInputFingerprint: String(planMeta.input_fingerprint || ""),
                    createRequestId: request.requestId,
                    draftName: String(draft.name || ""),
                });
                if (!store) return;
                store.settleCreatePlan(response || null);
                if (response && response.ok && response.plan_name && typeof frappe !== "undefined") {
                    const planName = String(response.plan_name);
                    const orderName = String(activeOrderName);
                    rememberPreferEditedPlanTab(orderName);
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
                    const title = (code === "version_conflict" || code === "source_conflict" || code === "source_changed")
                        ? __("Could not apply layout")
                        : __("Apply to cutting plan");
                    frappe.msgprint({
                        title,
                        message: (response && response.message)
                            || __("The layout could not be applied to a cutting plan."),
                        indicator: "orange",
                    });
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
