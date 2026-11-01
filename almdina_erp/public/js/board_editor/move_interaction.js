(() => {
    "use strict";

    const LONG_PRESS_MS = 250;
    const MOVE_THRESHOLD_PX = 5;

    function createMoveInteraction(options) {
        const {
            store,
            getStageEl,
            getSvgEl,
            getWorldMetrics,
            onPreview,
            onDropRejected,
            onSelectPiece,
            onSelectSheet,
            onGesturePhase,
            isPanKey,
            isAltKey,
            getScale,
            now: nowFn,
            setTimeout: setTimeoutFn,
            clearTimeout: clearTimeoutFn,
        } = options;

        const clock = {
            now: typeof nowFn === "function" ? nowFn : () => Date.now(),
            setTimeout: typeof setTimeoutFn === "function" ? setTimeoutFn : (fn, ms) => window.setTimeout(fn, ms),
            clearTimeout: typeof clearTimeoutFn === "function" ? clearTimeoutFn : (id) => window.clearTimeout(id),
        };

        function __(msg) {
            return typeof window.__ === "function" ? window.__(msg) : msg;
        }

        // Single interaction owner: idle → pending → armed → dragging | aborted.
        let gesture = null;
        let suppressClick = false;
        let gestureToken = 0;
        let windowBound = false;

        function onWindowPointerMove(event) {
            onPointerMove(event);
        }

        function onWindowPointerUp(event) {
            onPointerUp(event);
        }

        function onWindowPointerCancel(event) {
            onPointerCancel(event);
        }

        function bindWindowTracking() {
            if (windowBound || typeof window === "undefined" || !window.addEventListener) return;
            window.addEventListener("pointermove", onWindowPointerMove, true);
            window.addEventListener("pointerup", onWindowPointerUp, true);
            window.addEventListener("pointercancel", onWindowPointerCancel, true);
            windowBound = true;
        }

        function unbindWindowTracking() {
            if (!windowBound || typeof window === "undefined" || !window.removeEventListener) return;
            window.removeEventListener("pointermove", onWindowPointerMove, true);
            window.removeEventListener("pointerup", onWindowPointerUp, true);
            window.removeEventListener("pointercancel", onWindowPointerCancel, true);
            windowBound = false;
        }

        function clientToWorld(clientX, clientY) {
            const svg = getSvgEl && getSvgEl();
            const metrics = getWorldMetrics && getWorldMetrics();
            if (!svg || !metrics || !metrics.width || !metrics.height) return null;
            const rect = svg.getBoundingClientRect();
            if (!rect.width || !rect.height) return null;
            const nx = (clientX - rect.left) / rect.width;
            const ny = (clientY - rect.top) / rect.height;
            return {
                x: metrics.minX + nx * metrics.width,
                y: metrics.minY + ny * metrics.height,
            };
        }

        function ensureScrollNearPointer(clientX, clientY) {
            const stage = getStageEl && getStageEl();
            if (!stage) return;
            const edge = 36;
            const rect = stage.getBoundingClientRect();
            let dx = 0;
            let dy = 0;
            if (clientX < rect.left + edge) dx = -18;
            else if (clientX > rect.right - edge) dx = 18;
            if (clientY < rect.top + edge) dy = -18;
            else if (clientY > rect.bottom - edge) dy = 18;
            if (dx || dy) {
                stage.scrollLeft += dx;
                stage.scrollTop += dy;
            }
        }

        function publishPreview(preview) {
            store.setDragPreview(preview);
            if (onPreview) onPreview(preview);
        }

        function emitPhase(phase) {
            if (onGesturePhase) onGesturePhase(phase, gesture);
            const stage = getStageEl && getStageEl();
            if (!stage) return;
            stage.classList.toggle("is-drag-armed", phase === "armed");
            stage.classList.toggle("is-dragging", phase === "dragging");
            if (phase === "armed" || phase === "dragging") {
                stage.style.cursor = phase === "dragging" ? "grabbing" : "grab";
            } else if (!stage.classList.contains("is-panning")) {
                stage.style.cursor = "";
            }
        }

        function clearTimer() {
            if (!gesture || gesture.timerId == null) return;
            clock.clearTimeout(gesture.timerId);
            gesture.timerId = null;
        }

        function releaseCapture() {
            if (!gesture || !gesture.target || !gesture.target.releasePointerCapture) return;
            try {
                gesture.target.releasePointerCapture(gesture.pointerId);
            } catch (err) {
                /* ignore */
            }
        }

        function resetGesture() {
            clearTimer();
            releaseCapture();
            unbindWindowTracking();
            gesture = null;
            publishPreview(null);
            emitPhase("idle");
        }

        function clearGuidesOnly() {
            const snap = store.snapshot();
            if (snap.dragPreview) {
                publishPreview({ ...snap.dragPreview, guides: [], snapped: false });
            }
        }

        function armGesture() {
            if (!gesture || gesture.phase !== "pending" || !gesture.canDrag) return;
            gesture.phase = "armed";
            gesture.timerId = null;
            if (gesture.target && gesture.target.setPointerCapture) {
                try {
                    gesture.target.setPointerCapture(gesture.pointerId);
                } catch (err) {
                    /* ignore */
                }
            }
            emitPhase("armed");
        }

        function abortLongPress() {
            if (!gesture || (gesture.phase !== "pending" && gesture.phase !== "armed")) return;
            clearTimer();
            gesture.phase = "aborted";
            gesture.canDrag = false;
            emitPhase("aborted");
        }

        function beginGesture(spec, event) {
            if (!event || event.button === 1) return false;
            if (isPanKey && isPanKey()) return false;
            if (event.pointerType === "mouse" && event.button !== 0) return false;

            const snap = store.snapshot();
            if (!snap.session) return false;
            const world = clientToWorld(event.clientX, event.clientY);
            if (!world) return false;

            resetGesture();
            suppressClick = false;
            const token = ++gestureToken;
            gesture = {
                token,
                phase: "pending",
                kind: spec.kind,
                pointerId: event.pointerId,
                pointerType: event.pointerType || "mouse",
                target: event.currentTarget || event.target,
                startClientX: event.clientX,
                startClientY: event.clientY,
                startWorldX: world.x,
                startWorldY: world.y,
                lastClientX: event.clientX,
                lastClientY: event.clientY,
                worldOriginX: 0,
                worldOriginY: 0,
                originX: 0,
                originY: 0,
                pieceKey: spec.pieceKey || null,
                pieceInstanceId: spec.pieceInstanceId || null,
                pieceId: spec.pieceId || null,
                elementId: spec.elementId || null,
                sheetNo: spec.sheetNo == null ? null : Number(spec.sheetNo),
                ids: spec.ids || [],
                canDrag: Boolean(spec.canDrag),
                canSelect: Boolean(spec.canSelect),
                moved: false,
                lastDx: 0,
                lastDy: 0,
                rawDx: 0,
                rawDy: 0,
                activeSnap: null,
                timerId: null,
            };

            if (spec.kind === "piece") {
                const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
                const worldStart = MoveGeometry.pieceWorldOrigin(snap.session, spec.pieceKey);
                gesture.worldOriginX = worldStart.x;
                gesture.worldOriginY = worldStart.y;
            } else if (spec.kind === "board") {
                const board = snap.session.boards[String(spec.sheetNo)];
                gesture.originX = board ? Number(board.origin_x_mm) || 0 : 0;
                gesture.originY = board ? Number(board.origin_y_mm) || 0 : 0;
            }

            emitPhase("pending");
            bindWindowTracking();

            if (gesture.canDrag) {
                gesture.timerId = clock.setTimeout(() => {
                    if (!gesture || gesture.token !== token) return;
                    if (gesture.phase !== "pending") return;
                    armGesture();
                }, LONG_PRESS_MS);
            }

            // Do not preventDefault while pending: touch scrolling stays natural.
            event.stopPropagation();
            return true;
        }

        function beginPieceGesture(pieceKeyOrInstance, event, meta) {
            const snap = store.snapshot();
            if (!snap.session) return false;
            const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
            const pieceKey = MoveGeometry.resolvePieceKey(snap.session, pieceKeyOrInstance);
            const piece = pieceKey && snap.session.pieces[pieceKey];
            const pieceId = (meta && meta.pieceId) || (piece && piece.piece_id);
            if (!piece && pieceId == null) return false;
            return beginGesture({
                kind: "piece",
                pieceKey,
                pieceInstanceId: piece && piece.piece_instance_id,
                pieceId,
                elementId: meta && meta.elementId,
                ids: piece && piece.editable ? MoveGeometry.draggedPieceIds(snap.session, pieceKey) : [],
                canDrag: Boolean(piece && piece.editable),
                canSelect: true,
            }, event);
        }

        function beginBoardGesture(sheetNo, event) {
            const snap = store.snapshot();
            if (!snap.session || !snap.session.boards[String(sheetNo)]) return false;
            return beginGesture({
                kind: "board",
                sheetNo,
                canDrag: true,
                canSelect: true,
            }, event);
        }

        function resolvePiecePreviewDelta(rawDx, rawDy) {
            const snap = store.snapshot();
            const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
            const SnapGeometry = window.AlmdinaBoardEditor.SnapGeometry;
            gesture.rawDx = rawDx;
            gesture.rawDy = rawDy;
            const magnetOn = snap.magnetEnabled !== false;
            const altBypass = Boolean(isAltKey && isAltKey());
            if (!magnetOn || altBypass || !SnapGeometry) {
                gesture.activeSnap = null;
                return { dx: rawDx, dy: rawDy, guides: [], snapped: false };
            }
            const scale = (typeof getScale === "function" && getScale())
                || ((getWorldMetrics && getWorldMetrics()) || {}).scale
                || 1;
            const thresholdMm = SnapGeometry.thresholdMmFromScale(scale, SnapGeometry.SNAP_ENTER_PX);
            const exitMm = SnapGeometry.thresholdMmFromScale(scale, SnapGeometry.SNAP_EXIT_PX);
            const suggestion = SnapGeometry.suggestPieceSnap(
                snap.session,
                gesture.pieceKey,
                gesture.worldOriginX + rawDx,
                gesture.worldOriginY + rawDy,
                {
                    magnetEnabled: true,
                    thresholdMm,
                    exitThresholdMm: exitMm,
                    activeSnap: gesture.activeSnap,
                }
            );
            if (suggestion && suggestion.ok) {
                gesture.activeSnap = suggestion;
                return {
                    dx: suggestion.dx,
                    dy: suggestion.dy,
                    guides: suggestion.guides || [],
                    snapped: true,
                    suggestion,
                };
            }
            gesture.activeSnap = null;
            return { dx: rawDx, dy: rawDy, guides: [], snapped: false };
        }

        function updatePreview(dx, dy) {
            const snap = store.snapshot();
            if (!gesture || !snap.session) return;
            const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
            if (gesture.kind === "piece") {
                const resolved = resolvePiecePreviewDelta(dx, dy);
                gesture.lastDx = resolved.dx;
                gesture.lastDy = resolved.dy;
                const proposal = MoveGeometry.proposePieceDrop(
                    snap.session,
                    gesture.pieceKey,
                    gesture.worldOriginX + resolved.dx,
                    gesture.worldOriginY + resolved.dy
                );
                publishPreview({
                    kind: "piece",
                    pieceKey: gesture.pieceKey,
                    pieceInstanceId: gesture.pieceInstanceId,
                    ids: gesture.ids,
                    dx: resolved.dx,
                    dy: resolved.dy,
                    rawDx: dx,
                    rawDy: dy,
                    guides: resolved.snapped ? resolved.guides : [],
                    snapped: Boolean(resolved.snapped),
                    valid: proposal.ok,
                    reason: proposal.ok ? null : proposal.reason,
                    targetSheetNo: proposal.ok ? proposal.target_sheet_no : null,
                    ghostLocalX: proposal.ok ? proposal.local_x_mm : null,
                    ghostLocalY: proposal.ok ? proposal.local_y_mm : null,
                });
            } else if (gesture.kind === "board") {
                gesture.activeSnap = null;
                gesture.lastDx = dx;
                gesture.lastDy = dy;
                const proposal = MoveGeometry.proposeBoardDrop(
                    snap.session,
                    gesture.sheetNo,
                    gesture.originX + dx,
                    gesture.originY + dy
                );
                publishPreview({
                    kind: "board",
                    sheetNo: gesture.sheetNo,
                    dx,
                    dy,
                    guides: [],
                    snapped: false,
                    valid: proposal.ok,
                    reason: proposal.ok ? null : proposal.reason,
                });
            }
        }

        function refreshPreviewFromPointer() {
            if (!gesture || gesture.phase !== "dragging") return;
            updatePreview(gesture.rawDx, gesture.rawDy);
        }

        function onPointerMove(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            gesture.lastClientX = event.clientX;
            gesture.lastClientY = event.clientY;
            const dist = Math.hypot(
                event.clientX - gesture.startClientX,
                event.clientY - gesture.startClientY
            ) || 0;

            if (gesture.phase === "pending") {
                if (dist >= MOVE_THRESHOLD_PX) {
                    abortLongPress();
                }
                return;
            }

            if (gesture.phase === "armed") {
                if (dist < MOVE_THRESHOLD_PX) return;
                const world = clientToWorld(event.clientX, event.clientY);
                if (!world) return;
                // Re-anchor world delta at first real move so the piece does not jump.
                gesture.startWorldX = world.x;
                gesture.startWorldY = world.y;
                gesture.phase = "dragging";
                gesture.moved = true;
                gesture.lastDx = 0;
                gesture.lastDy = 0;
                emitPhase("dragging");
                updatePreview(0, 0);
                event.preventDefault();
                return;
            }

            if (gesture.phase !== "dragging") return;
            const world = clientToWorld(event.clientX, event.clientY);
            if (!world) return;
            const dx = world.x - gesture.startWorldX;
            const dy = world.y - gesture.startWorldY;
            gesture.moved = true;
            ensureScrollNearPointer(event.clientX, event.clientY);
            updatePreview(dx, dy);
            event.preventDefault();
        }

        function applySelection() {
            if (!gesture || !gesture.canSelect) return;
            if (gesture.kind === "piece") {
                if (onSelectPiece) {
                    onSelectPiece(gesture.pieceId, gesture.elementId, gesture.pieceKey);
                }
            } else if (gesture.kind === "board") {
                if (onSelectSheet) onSelectSheet(gesture.sheetNo);
            }
        }

        function commitDrag() {
            const snap = store.snapshot();
            const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
            const dx = gesture.lastDx;
            const dy = gesture.lastDy;

            if (gesture.kind === "piece") {
                const proposal = MoveGeometry.proposePieceDrop(
                    snap.session,
                    gesture.pieceKey,
                    gesture.worldOriginX + dx,
                    gesture.worldOriginY + dy
                );
                if (!proposal.ok) {
                    store.setDropMessage(__(proposal.reason || "Drop rejected."));
                    if (onDropRejected) onDropRejected(proposal.reason);
                    suppressClick = true;
                    resetGesture();
                    return;
                }
                let next = JSON.parse(JSON.stringify(snap.session));
                next = MoveGeometry.applyPieceMove(next, {
                    piece_key: gesture.pieceKey,
                    piece_instance_id: gesture.pieceInstanceId,
                    target_sheet_no: proposal.target_sheet_no,
                    local_x_mm: proposal.local_x_mm,
                    local_y_mm: proposal.local_y_mm,
                    delta_x_mm: proposal.delta_x_mm,
                    delta_y_mm: proposal.delta_y_mm,
                    detach_host: proposal.detach_host,
                });
                store.commitSession(next);
                store.setDropMessage(null);
                suppressClick = true;
                resetGesture();
                return;
            }

            if (gesture.kind === "board") {
                const proposal = MoveGeometry.proposeBoardDrop(
                    snap.session,
                    gesture.sheetNo,
                    gesture.originX + dx,
                    gesture.originY + dy
                );
                if (!proposal.ok) {
                    store.setDropMessage(__(proposal.reason || "Drop rejected."));
                    if (onDropRejected) onDropRejected(proposal.reason);
                    suppressClick = true;
                    resetGesture();
                    return;
                }
                let next = JSON.parse(JSON.stringify(snap.session));
                next = MoveGeometry.applyBoardMove(next, {
                    sheet_no: gesture.sheetNo,
                    origin_x_mm: proposal.origin_x_mm,
                    origin_y_mm: proposal.origin_y_mm,
                });
                store.commitSession(next);
                store.setDropMessage(null);
                suppressClick = true;
                resetGesture();
            }
        }

        function finish(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            const phase = gesture.phase;
            const wasDragging = phase === "dragging" && gesture.moved;

            clearTimer();

            if (wasDragging) {
                commitDrag();
                return;
            }

            // Pending / armed / aborted without a completed drag: select only.
            applySelection();
            resetGesture();
        }

        function onPointerUp(event) {
            finish(event);
        }

        function onPointerCancel(event) {
            if (!gesture) return;
            if (event && event.pointerId != null && event.pointerId !== gesture.pointerId) return;
            suppressClick = true;
            store.setDropMessage(null);
            resetGesture();
        }

        function cancel() {
            if (!gesture) return;
            suppressClick = true;
            store.setDropMessage(null);
            resetGesture();
        }

        function onPanIntent() {
            // Space or middle-button pan wins over an incomplete piece gesture.
            if (!gesture) return;
            if (gesture.phase === "dragging") return;
            cancel();
        }

        function consumeClickSuppression() {
            if (!suppressClick) return false;
            suppressClick = false;
            return true;
        }

        function isActive() {
            return Boolean(gesture);
        }

        function getGesture() {
            return gesture;
        }

        function getPhase() {
            return gesture ? gesture.phase : "idle";
        }

        return {
            beginPieceGesture,
            beginBoardGesture,
            // Compatibility aliases used while wiring settles.
            startPieceDrag: beginPieceGesture,
            startBoardDrag: beginBoardGesture,
            onPointerMove,
            onPointerUp,
            onPointerCancel,
            cancel,
            onPanIntent,
            consumeClickSuppression,
            isActive,
            getGesture,
            getPhase,
            clientToWorld,
            refreshPreviewFromPointer,
            clearGuidesOnly,
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.LONG_PRESS_MS = LONG_PRESS_MS;
    window.AlmdinaBoardEditor.MOVE_THRESHOLD_PX = MOVE_THRESHOLD_PX;
    window.AlmdinaBoardEditor.createMoveInteraction = createMoveInteraction;
})();
