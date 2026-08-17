(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const v4 = window.AlmdinaDoorDrawingV4;
    const geometry = v4.Geometry;
    const documentModel = v4.DocumentModel;
    const dimensionDomain = v4.DimensionDomain;
    const viewport = v4.Viewport;
    const canvasRenderer = v4.CanvasRenderer;
    const tools = v4.ToolStateMachine;
    const sessions = root.EditorSession;
    const keyboard = root.KeyboardController;
    const viewModel = root.EditorViewModel;
    const selectionOverlay = root.SelectionOverlay;
    const shellFactory = root.WorkspaceShell;

    if (
        !geometry || !documentModel || !dimensionDomain || !viewport || !canvasRenderer || !tools
        || !sessions || !keyboard || !viewModel || !selectionOverlay || !shellFactory
    ) {
        throw new Error("Professional editor dependencies are incomplete");
    }

    const SNAP_TOLERANCE_PX = 11;
    const SNAP_RELEASE_PX = 16;
    const HIT_TOLERANCE_PX = 9;
    const ANGLE_INCREMENT_DEG = 45;

    function create(options = {}) {
        if (!options.container) throw new Error("Professional editor requires a container");

        const readOnly = Boolean(options.readOnly);
        const shell = shellFactory.mount(options.container, options.meta || {});
        const session = sessions.create({
            document: options.document,
            initialTool: readOnly ? tools.TOOLS.HAND : tools.TOOLS.SELECT,
        });

        let camera = viewport.create();
        let dpr = Math.max(1, Number(window.devicePixelRatio || 1));
        let lastScreenPoint = Object.freeze({ x: 0, y: 0 });
        let pan = null;
        let numericMode = null;
        let dirty = false;
        let destroyed = false;
        let didFit = false;
        const listeners = [];

        function listen(target, type, handler, listenerOptions) {
            target.addEventListener(type, handler, listenerOptions);
            listeners.push(() => target.removeEventListener(type, handler, listenerOptions));
        }

        function screenPoint(event) {
            const rect = shell.canvas.getBoundingClientRect();
            return Object.freeze({ x: event.clientX - rect.left, y: event.clientY - rect.top });
        }

        function worldPoint(screen) {
            return viewport.screenToWorld(camera, screen);
        }

        function penAnchor(state) {
            if (!state.activePathId) return null;
            const nodeId = documentModel.pathEndNodeId(state.document, state.activePathId);
            return documentModel.nodeById(state.document, nodeId);
        }

        function applyShiftAngleLock(rawPoint, event) {
            if (!event || !event.shiftKey) return rawPoint;
            const state = session.state();
            if (state.toolState.activeTool !== tools.TOOLS.PEN || !state.activePathId) return rawPoint;
            const anchor = penAnchor(state);
            if (!anchor) return rawPoint;
            const lengthMm = geometry.distance(anchor, rawPoint);
            if (lengthMm <= geometry.EPSILON_MM) return rawPoint;
            const rawAngle = geometry.angleDeg(anchor, rawPoint);
            const lockedAngle = Math.round(rawAngle / ANGLE_INCREMENT_DEG) * ANGLE_INCREMENT_DEG;
            return geometry.pointFromPolar(anchor, lengthMm, lockedAngle);
        }

        function interactionWorldPoint(event, screen) {
            return applyShiftAngleLock(worldPoint(screen), event);
        }

        function interactionOptions(event) {
            const snapDisabled = Boolean(event && event.altKey);
            return Object.freeze({
                toleranceMm: viewport.screenToleranceToMm(camera, snapDisabled ? 0 : SNAP_TOLERANCE_PX),
                releaseToleranceMm: viewport.screenToleranceToMm(camera, snapDisabled ? 0 : SNAP_RELEASE_PX),
                hitToleranceMm: viewport.screenToleranceToMm(camera, HIT_TOLERANCE_PX),
                gridStepMm: snapDisabled ? 0 : viewport.gridStepMm(camera),
            });
        }

        function markDirty() {
            if (readOnly || dirty) return;
            dirty = true;
            shell.setSaveState("غير محفوظ", "dirty");
            if (typeof options.onDirty === "function") options.onDirty(true);
        }

        function mutate(callback) {
            const before = session.state().document;
            const result = callback();
            const after = session.state().document;
            if (after !== before) {
                markDirty();
                if (typeof options.onChange === "function") options.onChange(after);
            }
            render();
            return result;
        }

        function render() {
            if (destroyed) return;
            const state = session.state();
            const interactionState = readOnly
                ? { ...state, preview: null, selection: null, drag: null }
                : state;

            canvasRenderer.render(shell.canvas, {
                camera,
                document: state.document,
                interactionState,
                dpr,
                showNodes: !readOnly && (state.toolState.activeTool === tools.TOOLS.NODE || Boolean(state.drag)),
            });
            if (!readOnly) {
                selectionOverlay.render(shell.canvas, {
                    camera,
                    document: state.document,
                    selection: state.selection,
                    dpr,
                });
            }

            const cursor = worldPoint(lastScreenPoint);
            shell.setActiveTool(state.toolState.activeTool);
            shell.setStatus(
                viewModel.TOOL_LABELS[state.toolState.activeTool] || state.toolState.activeTool,
                `X ${geometry.roundMm(cursor.xMm)} · Y ${geometry.roundMm(cursor.yMm)} mm`,
                viewModel.snapText(state.preview)
            );
            shell.setZoom(`${viewport.zoomPercent(camera)}%`);
            shell.setHint(viewModel.hint(state, readOnly));
            shell.renderLayers(
                viewModel.layers(state),
                state.selection && state.selection.kind === "path" ? state.selection.id : null
            );
            shell.renderProperties(viewModel.properties(state));
            shell.workspace.classList.toggle("is-panning", Boolean(pan));
        }

        function resize(resizeOptions = {}) {
            const rect = shell.stage.getBoundingClientRect();
            camera = viewport.resize(camera, Math.max(1, rect.width), Math.max(1, rect.height));
            dpr = Math.max(1, Number(window.devicePixelRatio || 1));
            canvasRenderer.resizeCanvas(shell.canvas, Math.max(1, rect.width), Math.max(1, rect.height), dpr);
            if (!didFit || resizeOptions.fit) {
                camera = viewport.fitBlank(camera, session.state().document.blank);
                didFit = true;
            }
            render();
        }

        function beginPan(event, point) {
            pan = { pointerId: event.pointerId, last: point };
            if (shell.canvas.setPointerCapture) shell.canvas.setPointerCapture(event.pointerId);
            render();
        }

        function endPan(event) {
            if (!pan || (event && event.pointerId !== pan.pointerId)) return;
            pan = null;
            render();
        }

        function hideNumeric() {
            numericMode = null;
            shell.hideNumeric();
        }

        function pointerDown(event) {
            if (![0, 1].includes(event.button)) return;
            const point = screenPoint(event);
            lastScreenPoint = point;
            shell.canvas.focus({ preventScroll: true });
            hideNumeric();

            const tool = session.state().toolState.activeTool;
            if (readOnly || event.button === 1 || tool === tools.TOOLS.HAND) {
                event.preventDefault();
                beginPan(event, point);
                return;
            }

            event.preventDefault();
            if (shell.canvas.setPointerCapture) shell.canvas.setPointerCapture(event.pointerId);
            const result = mutate(() => session.pointerDown(
                interactionWorldPoint(event, point),
                interactionOptions(event)
            ));
            if (result && result.kind === "fixed-length-protected-node") {
                shell.setHint("هذه النقطة مرتبطة بطول ثابت؛ عدّل قيمة البعد بدل كسر الطول.");
            }
        }

        function pointerMove(event) {
            const point = screenPoint(event);
            lastScreenPoint = point;
            if (pan && pan.pointerId === event.pointerId) {
                camera = viewport.panBy(camera, point.x - pan.last.x, point.y - pan.last.y);
                pan = { pointerId: event.pointerId, last: point };
                render();
                return;
            }
            if (readOnly) {
                render();
                return;
            }
            mutate(() => session.pointerMove(
                interactionWorldPoint(event, point),
                interactionOptions(event)
            ));
        }

        function pointerUp(event) {
            endPan(event);
            if (!readOnly) mutate(() => session.pointerUp());
            if (shell.canvas.hasPointerCapture && shell.canvas.hasPointerCapture(event.pointerId)) {
                shell.canvas.releasePointerCapture(event.pointerId);
            }
        }

        function wheel(event) {
            event.preventDefault();
            const point = screenPoint(event);
            lastScreenPoint = point;
            camera = viewport.zoomAt(camera, point, Math.exp(-event.deltaY * 0.0015));
            render();
        }

        function setTool(tool) {
            if (readOnly && tool !== tools.TOOLS.HAND) return;
            hideNumeric();
            session.setTool(tool);
            render();
        }

        function beginNumeric(seed) {
            if (readOnly) return false;
            const state = session.state();
            if (state.toolState.activeTool === tools.TOOLS.PEN && state.activePathId && state.preview) {
                numericMode = "pen";
            } else if (
                state.toolState.activeTool === tools.TOOLS.DIMENSION
                && state.selection
                && state.selection.kind === "dimension"
            ) {
                numericMode = "dimension";
            } else {
                return false;
            }
            shell.showNumeric(lastScreenPoint, seed === "." || seed === "," ? `0${seed}` : seed);
            return true;
        }

        function beginDimensionEntry() {
            const state = session.state();
            if (
                readOnly
                || state.toolState.activeTool !== tools.TOOLS.DIMENSION
                || !state.selection
                || state.selection.kind !== "dimension"
            ) return false;
            const measurement = dimensionDomain.resolve(state.document, state.selection.id);
            if (!measurement) return false;
            numericMode = "dimension";
            shell.showNumeric(lastScreenPoint, String(geometry.roundMm(measurement.valueMm)));
            return true;
        }

        function commitNumeric() {
            const value = Number(String(shell.numeric.value || "").replace(",", "."));
            if (!Number.isFinite(value) || value <= 0) {
                shell.numeric.select();
                return;
            }
            const result = numericMode === "dimension"
                ? mutate(() => session.inputDimensionValue(value))
                : mutate(() => session.inputLength(value));
            if (result && result.kind === "dimension-drive-failed") {
                shell.setHint("لا يمكن تطبيق هذا القياس دون كسر قيود الشكل.");
                shell.numeric.select();
                return;
            }
            hideNumeric();
            shell.canvas.focus({ preventScroll: true });
        }

        function numericKey(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                commitNumeric();
            } else if (event.key === "Escape") {
                event.preventDefault();
                hideNumeric();
                shell.canvas.focus({ preventScroll: true });
            }
        }

        function undo() {
            if (!readOnly) mutate(() => session.undo());
        }

        function redo() {
            if (!readOnly) mutate(() => session.redo());
        }

        function handleClick(event) {
            const toolButton = event.target.closest("[data-tool]");
            if (toolButton) {
                setTool(toolButton.dataset.tool);
                return;
            }

            const action = event.target.closest("[data-action]");
            if (action) {
                if (action.dataset.action === "undo") undo();
                else if (action.dataset.action === "redo") redo();
                else if (action.dataset.action === "save" && typeof options.onSave === "function") {
                    options.onSave(session.state().document);
                } else if (action.dataset.action === "back" && typeof options.onBack === "function") {
                    options.onBack(dirty);
                }
                return;
            }

            const view = event.target.closest("[data-view]");
            if (view) {
                const center = { x: camera.viewportWidthPx / 2, y: camera.viewportHeightPx / 2 };
                if (view.dataset.view === "in") camera = viewport.zoomAt(camera, center, 1.2);
                if (view.dataset.view === "out") camera = viewport.zoomAt(camera, center, 1 / 1.2);
                if (view.dataset.view === "fit") camera = viewport.fitBlank(camera, session.state().document.blank);
                render();
                return;
            }

            const layer = event.target.closest("[data-path-id]");
            if (layer) {
                session.selectPath(layer.dataset.pathId);
                render();
            }
        }

        if (readOnly) {
            shell.workspace.querySelectorAll("[data-tool]").forEach(button => {
                button.disabled = button.dataset.tool !== tools.TOOLS.HAND;
            });
            const save = shell.workspace.querySelector('[data-action="save"]');
            if (save) save.style.display = "none";
        }

        listen(shell.canvas, "pointerdown", pointerDown);
        listen(shell.canvas, "pointermove", pointerMove);
        listen(shell.canvas, "pointerup", pointerUp);
        listen(shell.canvas, "pointercancel", pointerUp);
        listen(shell.canvas, "wheel", wheel, { passive: false });
        listen(shell.workspace, "click", handleClick);
        listen(shell.numeric, "keydown", numericKey);

        const keys = keyboard.mount(shell.workspace, {
            tool: setTool,
            escape() {
                if (!readOnly) mutate(() => session.cancel());
                else render();
            },
            undo,
            redo,
            spaceDown() {
                session.spaceDown();
                render();
            },
            spaceUp() {
                session.spaceUp();
                endPan();
                render();
            },
            numeric: beginNumeric,
            enter: beginDimensionEntry,
        });

        let resizeObserver = null;
        if (typeof ResizeObserver === "function") {
            resizeObserver = new ResizeObserver(() => resize());
            resizeObserver.observe(shell.stage);
        } else {
            listen(window, "resize", resize);
        }
        requestAnimationFrame(() => resize({ fit: true }));

        return Object.freeze({
            state: () => Object.freeze({ interaction: session.state(), camera, readOnly, dirty }),
            render,
            resize,
            setTool,
            markSaved() {
                dirty = false;
                shell.setSaveState("محفوظ", "saved");
                if (typeof options.onDirty === "function") options.onDirty(false);
                render();
            },
            setSaving(saving) {
                shell.setSaving(saving);
                shell.setSaveState(
                    saving ? "يتم الحفظ…" : (dirty ? "غير محفوظ" : "محفوظ"),
                    saving ? "saving" : (dirty ? "dirty" : "saved")
                );
            },
            destroy() {
                if (destroyed) return;
                destroyed = true;
                keys.destroy();
                listeners.splice(0).forEach(dispose => dispose());
                if (resizeObserver) resizeObserver.disconnect();
                shell.destroy();
            },
        });
    }

    root.EditorController = Object.freeze({ create });
})();
