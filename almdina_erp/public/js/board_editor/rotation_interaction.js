(() => {
    "use strict";

    function createRotationInteraction(options) {
        const {
            store,
            getStageEl,
            getSvgEl,
            getWorldMetrics,
            getScale,
            onPreview,
            onRejected,
            onCommitted,
            isPanKey,
        } = options;

        let gesture = null;
        let windowBound = false;

        function __(msg) {
            return typeof window.__ === "function" ? window.__(msg) : msg;
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

        function publishPreview(preview) {
            store.setDragPreview(preview);
            if (onPreview) onPreview(preview);
        }

        function bindWindow() {
            if (windowBound || typeof window === "undefined") return;
            window.addEventListener("pointermove", onPointerMove, true);
            window.addEventListener("pointerup", onPointerUp, true);
            window.addEventListener("pointercancel", onPointerCancel, true);
            window.addEventListener("keydown", onKeyDown, true);
            window.addEventListener("blur", onBlur);
            windowBound = true;
        }

        function unbindWindow() {
            if (!windowBound || typeof window === "undefined") return;
            window.removeEventListener("pointermove", onPointerMove, true);
            window.removeEventListener("pointerup", onPointerUp, true);
            window.removeEventListener("pointercancel", onPointerCancel, true);
            window.removeEventListener("keydown", onKeyDown, true);
            window.removeEventListener("blur", onBlur);
            windowBound = false;
        }

        function reset() {
            if (gesture && gesture.target && gesture.target.releasePointerCapture) {
                try {
                    gesture.target.releasePointerCapture(gesture.pointerId);
                } catch (err) {
                    /* ignore */
                }
            }
            unbindWindow();
            gesture = null;
            publishPreview(null);
            const stage = getStageEl && getStageEl();
            if (stage) {
                stage.classList.remove("is-rotating");
                if (!stage.classList.contains("is-panning") && !stage.classList.contains("is-dragging")) {
                    stage.style.cursor = "";
                }
            }
        }

        function updateFromWorld(world) {
            if (!gesture || !world) return;
            const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
            const pointerAngle = RotationGeometry.angleFromPointer(
                gesture.pivotWorld,
                world.x,
                world.y
            );
            const absolute = RotationGeometry.normalizeAngleDeg(
                gesture.startRotation + (pointerAngle - gesture.startPointerAngle)
            );
            // Continuous value for display without 0/360 jump.
            let delta = pointerAngle - gesture.startPointerAngle;
            if (delta > 180) delta -= 360;
            if (delta < -180) delta += 360;
            const continuous = gesture.startRotation + delta;
            gesture.lastContinuous = continuous;
            gesture.lastAngle = absolute;

            const snap = store.snapshot();
            const decision = RotationGeometry.validatePieceRotation(
                snap.session,
                gesture.pieceKey,
                absolute
            );
            publishPreview({
                kind: "rotate",
                pieceKey: gesture.pieceKey,
                ids: gesture.ids,
                rotation_deg: absolute,
                display_deg: continuous,
                pivotX: gesture.pivotWorld.x,
                pivotY: gesture.pivotWorld.y,
                pivotLocalX: gesture.pivotLocal.x,
                pivotLocalY: gesture.pivotLocal.y,
                valid: Boolean(decision.ok),
                reason: decision.ok ? null : decision.code,
                // No positional magnet during rotation.
                guides: [],
                snapped: false,
            });
        }

        function beginHandleGesture(pieceKey, event) {
            if (!event || event.button === 1) return false;
            if (isPanKey && isPanKey()) return false;
            if (event.pointerType === "mouse" && event.button !== 0) return false;
            const snap = store.snapshot();
            if (!snap.session || !snap.session.pieces[pieceKey]) return false;
            const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
            const eligibility = RotationGeometry.pieceRotationEligibility(snap.session, pieceKey);
            if (!eligibility.rotatable) return false;

            const piece = snap.session.pieces[pieceKey];
            RotationGeometry.ensureBaseGeometry(piece);
            const scale = (typeof getScale === "function" && getScale()) || 1;
            const handleOffsetMm = 28 / Math.max(scale, 0.05);
            const handle = RotationGeometry.handleWorldPosition(
                piece,
                snap.session.boards,
                handleOffsetMm
            );
            const world = clientToWorld(event.clientX, event.clientY);
            if (!world) return false;

            reset();
            gesture = {
                pieceKey,
                pieceId: piece.piece_id,
                ids: eligibility.affected_keys.slice(),
                pointerId: event.pointerId,
                target: event.currentTarget || event.target,
                pivotWorld: handle.pivotWorld,
                pivotLocal: {
                    x: Number(piece.pivot_mm.x) || 0,
                    y: Number(piece.pivot_mm.y) || 0,
                },
                startRotation: RotationGeometry.normalizeAngleDeg(piece.rotation_deg),
                startPointerAngle: RotationGeometry.angleFromPointer(
                    handle.pivotWorld,
                    world.x,
                    world.y
                ),
                lastAngle: RotationGeometry.normalizeAngleDeg(piece.rotation_deg),
                lastContinuous: RotationGeometry.normalizeAngleDeg(piece.rotation_deg),
            };
            if (gesture.target && gesture.target.setPointerCapture) {
                try {
                    gesture.target.setPointerCapture(event.pointerId);
                } catch (err) {
                    /* ignore */
                }
            }
            bindWindow();
            const stage = getStageEl && getStageEl();
            if (stage) {
                stage.classList.add("is-rotating");
                stage.style.cursor = "grabbing";
            }
            event.preventDefault();
            event.stopPropagation();
            updateFromWorld(world);
            return true;
        }

        function onPointerMove(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            const world = clientToWorld(event.clientX, event.clientY);
            updateFromWorld(world);
        }

        function commitOrReject(decision) {
            const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
            if (!decision || !decision.ok) {
                if (onRejected) {
                    onRejected(
                        __(RotationGeometry.reasonMessage(decision && decision.code))
                    );
                }
                reset();
                return;
            }
            if (decision.noop) {
                reset();
                return;
            }
            if (onCommitted) onCommitted(gesture.pieceKey, decision.rotation_deg);
            reset();
        }

        function onPointerUp(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            const snap = store.snapshot();
            const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
            const decision = RotationGeometry.validatePieceRotation(
                snap.session,
                gesture.pieceKey,
                gesture.lastAngle
            );
            commitOrReject(decision);
        }

        function onPointerCancel() {
            reset();
        }

        function onKeyDown(event) {
            if (!gesture) return;
            if (event.key === "Escape") {
                event.preventDefault();
                reset();
            }
        }

        function onBlur() {
            if (gesture) reset();
        }

        function applyNumericAngle(pieceKey, rawValue) {
            const RotationGeometry = window.AlmdinaBoardEditor.RotationGeometry;
            const parsed = Number(String(rawValue == null ? "" : rawValue).trim());
            if (!Number.isFinite(parsed)) {
                if (onRejected) onRejected(__("Enter a valid angle in degrees."));
                return false;
            }
            const snap = store.snapshot();
            if (!snap.session || !snap.session.pieces[pieceKey]) return false;
            const decision = RotationGeometry.validatePieceRotation(
                snap.session,
                pieceKey,
                RotationGeometry.normalizeAngleDeg(parsed)
            );
            if (!decision.ok) {
                if (onRejected) {
                    onRejected(__(RotationGeometry.reasonMessage(decision.code)));
                }
                return false;
            }
            if (decision.noop) return true;
            if (onCommitted) onCommitted(pieceKey, decision.rotation_deg);
            return true;
        }

        function isActive() {
            return Boolean(gesture);
        }

        function cancel() {
            reset();
        }

        return Object.freeze({
            beginHandleGesture,
            applyNumericAngle,
            isActive,
            cancel,
            onPointerMove,
            onPointerUp,
            onPointerCancel,
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.createRotationInteraction = createRotationInteraction;
})();
