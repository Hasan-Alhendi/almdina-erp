(() => {
    "use strict";

    const MOVE_THRESHOLD_PX = (
        window.AlmdinaBoardEditor && Number(window.AlmdinaBoardEditor.MOVE_THRESHOLD_PX)
    ) || 5;

    function createMarqueeInteraction(options) {
        const {
            store,
            getStageEl,
            getSvgEl,
            getCanvasHost,
            getWorldMetrics,
            onOverlay,
            onSelectKeys,
            onEmptyClick,
            isPanKey,
            isBlocked,
        } = options;

        let gesture = null;
        let suppressClick = false;
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
            const CanvasRenderer = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.CanvasRenderer;
            if (CanvasRenderer && typeof CanvasRenderer.clientToWorld === "function") {
                return CanvasRenderer.clientToWorld(svg, metrics, clientX, clientY);
            }
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

        function publishOverlay(rect) {
            if (onOverlay) onOverlay(rect);
            const host = getCanvasHost && getCanvasHost();
            const CanvasRenderer = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.CanvasRenderer;
            if (host && CanvasRenderer && typeof CanvasRenderer.patchMarqueeOverlay === "function") {
                CanvasRenderer.patchMarqueeOverlay(host, rect);
            }
        }

        function emitPhase(phase) {
            const stage = getStageEl && getStageEl();
            if (!stage || !stage.classList) return;
            stage.classList.toggle("is-marqueeing", phase === "selecting");
            if (phase === "selecting") {
                stage.style.cursor = "crosshair";
            } else if (
                !stage.classList.contains("is-panning")
                && !stage.classList.contains("is-dragging")
                && !stage.classList.contains("is-rotating")
            ) {
                stage.style.cursor = "";
            }
        }

        function releaseCapture() {
            if (!gesture || !gesture.target || !gesture.target.releasePointerCapture) return;
            try {
                gesture.target.releasePointerCapture(gesture.pointerId);
            } catch (err) {
                /* ignore */
            }
        }

        function capturePointer() {
            if (!gesture || !gesture.target || !gesture.target.setPointerCapture) return;
            try {
                gesture.target.setPointerCapture(gesture.pointerId);
            } catch (err) {
                /* ignore */
            }
        }

        function currentRect() {
            if (!gesture) return null;
            const MarqueeGeometry = window.AlmdinaBoardEditor.MarqueeGeometry;
            return MarqueeGeometry.normalizeRect(
                gesture.startWorldX,
                gesture.startWorldY,
                gesture.endWorldX,
                gesture.endWorldY
            );
        }

        function resetGesture() {
            releaseCapture();
            unbindWindowTracking();
            gesture = null;
            publishOverlay(null);
            emitPhase("idle");
        }

        function begin(event) {
            if (!event || event.button === 1) return false;
            if (isPanKey && isPanKey()) return false;
            if (isBlocked && isBlocked()) return false;
            if (event.pointerType === "mouse" && event.button !== 0) return false;

            const snap = store && store.snapshot();
            if (!snap || !snap.session) return false;
            const world = clientToWorld(event.clientX, event.clientY);
            if (!world) return false;

            resetGesture();
            suppressClick = false;
            gesture = {
                phase: "pending",
                pointerId: event.pointerId,
                pointerType: event.pointerType || "mouse",
                target: event.currentTarget || event.target,
                startClientX: event.clientX,
                startClientY: event.clientY,
                startWorldX: world.x,
                startWorldY: world.y,
                endWorldX: world.x,
                endWorldY: world.y,
                shiftKey: Boolean(event.shiftKey),
                activated: false,
            };
            emitPhase("pending");
            bindWindowTracking();
            // Do not capture while pending: capturing on the stage retargets the
            // subsequent click away from svg/sheet handlers and blocks empty-click clear.
            if (event.stopPropagation) event.stopPropagation();
            return true;
        }

        function activate(event) {
            if (!gesture || gesture.phase !== "pending") return false;
            gesture.phase = "selecting";
            gesture.activated = true;
            capturePointer();
            emitPhase("selecting");
            publishOverlay(currentRect());
            if (event && event.preventDefault) event.preventDefault();
            return true;
        }

        function onPointerMove(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            if (typeof event.shiftKey === "boolean") gesture.shiftKey = event.shiftKey;
            const world = clientToWorld(event.clientX, event.clientY);
            if (world) {
                gesture.endWorldX = world.x;
                gesture.endWorldY = world.y;
            }
            const dist = Math.hypot(
                event.clientX - gesture.startClientX,
                event.clientY - gesture.startClientY
            ) || 0;

            if (gesture.phase === "pending") {
                if (dist < MOVE_THRESHOLD_PX) return;
                activate(event);
                return;
            }

            if (gesture.phase !== "selecting") return;
            publishOverlay(currentRect());
            if (event.preventDefault) event.preventDefault();
        }

        function commitSelection() {
            const MarqueeGeometry = window.AlmdinaBoardEditor.MarqueeGeometry;
            const snap = store.snapshot();
            const rect = currentRect();
            const hits = MarqueeGeometry.hitTestPieceKeys(snap.session, rect);
            const mode = gesture.shiftKey ? "add" : "replace";
            const keys = MarqueeGeometry.mergePieceKeys(
                snap.selectedPieceKeys,
                hits,
                mode
            );
            if (onSelectKeys) {
                onSelectKeys(keys, { mode, shiftKey: Boolean(gesture.shiftKey), hits });
            } else if (store && typeof store.selectPieces === "function") {
                store.selectPieces(keys, { mode: "replace" });
            }
            suppressClick = true;
            resetGesture();
        }

        function finish(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            if (event && typeof event.shiftKey === "boolean") gesture.shiftKey = event.shiftKey;
            const activated = gesture.activated && gesture.phase === "selecting";
            if (activated) {
                commitSelection();
                return;
            }
            // Click without real drag on empty workspace.
            // Handle clear/keep here: pointer-capture / sheet click paths are unreliable
            // once marquee owns the empty-space pointerdown.
            const shiftKey = Boolean(gesture.shiftKey);
            if (!shiftKey) {
                if (typeof onEmptyClick === "function") {
                    onEmptyClick({ shiftKey: false });
                } else if (store && typeof store.selectPieces === "function") {
                    store.selectPieces([], { mode: "replace" });
                } else if (store && typeof store.selectPiece === "function") {
                    store.selectPiece(null, { pieceKey: null, elementId: null });
                }
            }
            // Suppress the trailing click so sheet-select does not re-enter / race.
            suppressClick = true;
            resetGesture();
        }

        function onPointerUp(event) {
            finish(event);
        }

        function onPointerCancel(event) {
            if (!gesture) return;
            if (event && event.pointerId != null && event.pointerId !== gesture.pointerId) return;
            suppressClick = true;
            resetGesture();
        }

        function cancel() {
            if (!gesture) return;
            suppressClick = true;
            resetGesture();
        }

        function consumeClickSuppression() {
            if (!suppressClick) return false;
            suppressClick = false;
            return true;
        }

        function isActive() {
            return Boolean(gesture);
        }

        function isSelecting() {
            return Boolean(gesture && gesture.phase === "selecting");
        }

        function getGesture() {
            return gesture;
        }

        return {
            begin,
            onPointerMove,
            onPointerUp,
            onPointerCancel,
            cancel,
            consumeClickSuppression,
            isActive,
            isSelecting,
            getGesture,
            clientToWorld,
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createMarqueeInteraction = createMarqueeInteraction;
})();
