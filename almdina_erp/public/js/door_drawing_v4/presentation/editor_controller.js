(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const viewport = root.Viewport;
    const interaction = root.InteractionEngine;
    const tools = root.ToolStateMachine;
    const renderer = root.CanvasRenderer;
    const shellFactory = root.EditorShell;
    if (!geometry || !viewport || !interaction || !tools || !renderer || !shellFactory) {
        throw new Error("Drawing V4 dependencies must load before editor controller");
    }

    const DEFAULT_SNAP_TOLERANCE_PX = 10;
    const DEFAULT_HIT_TOLERANCE_PX = 9;
    const TOOL_LABELS = Object.freeze({
        [tools.TOOLS.SELECT]: "تحديد",
        [tools.TOOLS.NODE]: "تعديل النقاط",
        [tools.TOOLS.PEN]: "القلم الذكي",
        [tools.TOOLS.HAND]: "تحريك اللوحة",
    });
    const SNAP_LABELS = Object.freeze({ endpoint: "نقطة نهاية", horizontal: "أفقي", vertical: "عمودي" });

    function snapLabel(preview) {
        if (!preview || !preview.semantic) return "";
        if (preview.semantic === "angle") return `${Math.round(preview.angleDeg || 0)}°`;
        return SNAP_LABELS[preview.semantic] || "";
    }

    function create(options = {}) {
        if (!options.container) throw new Error("Drawing V4 editor container is required");
        const readOnly = Boolean(options.readOnly);
        const shell = shellFactory.mount(options.container);
        shell.setReadOnly(readOnly);
        const engine = interaction.create({
            document: options.document,
            blank: options.blank,
            initialTool: readOnly ? tools.TOOLS.HAND : (options.initialTool || tools.TOOLS.SELECT),
        });
        let camera = viewport.create();
        let dpr = Math.max(1, Number(window.devicePixelRatio || 1));
        let lastScreenPoint = Object.freeze({ x: 0, y: 0 });
        let panSession = null;
        let destroyed = false;
        let didInitialFit = false;
        const listeners = [];
        const snapTolerancePx = Math.max(4, Number(options.snapTolerancePx || DEFAULT_SNAP_TOLERANCE_PX));
        const hitTolerancePx = Math.max(4, Number(options.hitTolerancePx || DEFAULT_HIT_TOLERANCE_PX));

        function listen(target, type, handler, listenerOptions) {
            target.addEventListener(type, handler, listenerOptions);
            listeners.push(() => target.removeEventListener(type, handler, listenerOptions));
        }

        function screenPoint(event) {
            const rect = shell.canvas.getBoundingClientRect();
            return Object.freeze({ x: event.clientX - rect.left, y: event.clientY - rect.top });
        }

        function worldPoint(point) {
            return viewport.screenToWorld(camera, point);
        }

        function interactionOptions(event) {
            return Object.freeze({
                toleranceMm: viewport.screenToleranceToMm(camera, snapTolerancePx),
                hitToleranceMm: viewport.screenToleranceToMm(camera, hitTolerancePx),
                angleToleranceDeg: event && event.shiftKey ? 180 : undefined,
            });
        }

        function notifyDocumentChange(previousDocument) {
            const nextDocument = engine.state().document;
            if (previousDocument !== nextDocument && typeof options.onChange === "function") options.onChange(nextDocument);
        }

        function mutate(callback) {
            if (readOnly) return null;
            const before = engine.state().document;
            const result = callback();
            notifyDocumentChange(before);
            render();
            return result;
        }

        function statusText(state) {
            if (readOnly) return "عرض فقط";
            if (state.drag && state.drag.current) return `تحريك نقطة · X ${geometry.roundMm(state.drag.current.xMm)} · Y ${geometry.roundMm(state.drag.current.yMm)}`;
            if (state.selection && state.selection.kind === "node") return "نقطة محددة";
            if (state.selection && state.selection.kind === "path") return "مسار محدد";
            return TOOL_LABELS[state.toolState.activeTool] || state.toolState.activeTool;
        }

        function updateStatus() {
            const state = engine.state();
            const world = worldPoint(lastScreenPoint);
            const activeTool = state.toolState.activeTool;
            shell.setActiveTool(activeTool);
            shell.statusTool.textContent = statusText(state);
            shell.statusCoordinates.textContent = `X ${geometry.roundMm(world.xMm)} · Y ${geometry.roundMm(world.yMm)} mm`;
            shell.statusSnap.textContent = readOnly ? "" : snapLabel(state.preview);
            shell.zoomValue.textContent = `${viewport.zoomPercent(camera)}%`;
            shell.editor.dataset.tool = activeTool;
            shell.editor.classList.toggle("is-node-dragging", Boolean(state.drag));

            if (readOnly) shell.setHint("عرض فقط · اسحب لتحريك اللوحة · استخدم عجلة الماوس للتكبير");
            else if (state.drag) shell.setHint("حرّك النقطة · Esc لإلغاء الحركة · Ctrl+Z للتراجع بعد الإفلات");
            else if (activeTool === tools.TOOLS.NODE) shell.setHint("انقر واسحب نقطة لتعديل الشكل · A");
            else if (activeTool === tools.TOOLS.SELECT && state.selection) shell.setHint("المسار محدد · A لتعديل النقاط · Esc لإلغاء التحديد");
            else if (activeTool === tools.TOOLS.PEN && state.activePathId) shell.setHint("انقر لإضافة ضلع · اكتب الطول ثم Enter · Esc لإنهاء الرسم");
            else if (activeTool === tools.TOOLS.PEN) shell.setHint("انقر لبدء الرسم · P");
            else shell.setHint("");
        }

        function render() {
            if (destroyed) return;
            const state = engine.state();
            renderer.render(shell.canvas, {
                camera,
                document: state.document,
                interactionState: readOnly ? { ...state, preview: null, selection: null, drag: null } : state,
                dpr,
                showNodes: !readOnly && activeNodeSurface(state),
            });
            updateStatus();
        }

        function activeNodeSurface(state) {
            return state.toolState.activeTool === tools.TOOLS.NODE || Boolean(state.drag);
        }

        function resize(resizeOptions = {}) {
            if (destroyed) return;
            const rect = shell.canvasWrap.getBoundingClientRect();
            const widthPx = Math.max(1, rect.width);
            const heightPx = Math.max(1, rect.height);
            dpr = Math.max(1, Number(window.devicePixelRatio || 1));
            camera = viewport.resize(camera, widthPx, heightPx);
            renderer.resizeCanvas(shell.canvas, widthPx, heightPx, dpr);
            if (!didInitialFit || resizeOptions.fit) {
                camera = viewport.fitBlank(camera, engine.state().document.blank);
                didInitialFit = true;
            }
            render();
        }

        function fitView() { camera = viewport.fitBlank(camera, engine.state().document.blank); render(); }
        function zoomBy(factor, anchor = null) {
            camera = viewport.zoomAt(camera, anchor || { x: camera.viewportWidthPx / 2, y: camera.viewportHeightPx / 2 }, factor);
            render();
        }

        function beginPan(event, point) {
            panSession = Object.freeze({ pointerId: event.pointerId, last: point });
            shell.canvas.setPointerCapture(event.pointerId);
            shell.editor.classList.add("is-panning");
        }

        function endPan(event) {
            if (!panSession || (event && panSession.pointerId !== event.pointerId)) return;
            panSession = null;
            shell.editor.classList.remove("is-panning");
        }

        function handlePointerDown(event) {
            if (event.button !== 0 && event.button !== 1) return;
            shell.canvas.focus({ preventScroll: true });
            shell.hideLengthInput();
            const point = screenPoint(event);
            lastScreenPoint = point;
            const activeTool = engine.state().toolState.activeTool;
            if (readOnly || event.button === 1 || activeTool === tools.TOOLS.HAND) {
                event.preventDefault();
                beginPan(event, point);
                render();
                return;
            }
            if (event.button !== 0) return;
            event.preventDefault();
            shell.canvas.setPointerCapture(event.pointerId);
            mutate(() => engine.pointerDown(worldPoint(point), interactionOptions(event)));
        }

        function handlePointerMove(event) {
            const point = screenPoint(event);
            lastScreenPoint = point;
            if (panSession && panSession.pointerId === event.pointerId) {
                camera = viewport.panBy(camera, point.x - panSession.last.x, point.y - panSession.last.y);
                panSession = Object.freeze({ pointerId: event.pointerId, last: point });
                render();
                return;
            }
            if (readOnly) return render();
            mutate(() => engine.pointerMove(worldPoint(point), interactionOptions(event)));
        }

        function handlePointerUp(event) {
            endPan(event);
            if (!readOnly) mutate(() => engine.pointerUp());
            if (shell.canvas.hasPointerCapture && shell.canvas.hasPointerCapture(event.pointerId)) shell.canvas.releasePointerCapture(event.pointerId);
            render();
        }

        function handleWheel(event) {
            event.preventDefault();
            const point = screenPoint(event);
            lastScreenPoint = point;
            camera = viewport.zoomAt(camera, point, Math.exp(-event.deltaY * 0.0015));
            render();
        }

        function beginLengthEntry(key) {
            if (readOnly) return false;
            const state = engine.state();
            if (state.toolState.activeTool !== tools.TOOLS.PEN || !state.activePathId || !state.preview) return false;
            shell.showLengthInput(lastScreenPoint, key === "." || key === "," ? `0${key}` : key);
            return true;
        }

        function historyShortcut(event) {
            if (!(event.ctrlKey || event.metaKey) || event.altKey) return false;
            const key = String(event.key).toLowerCase();
            if (key === "z" && event.shiftKey) { event.preventDefault(); mutate(() => engine.redo()); return true; }
            if (key === "z") { event.preventDefault(); mutate(() => engine.undo()); return true; }
            if (key === "y") { event.preventDefault(); mutate(() => engine.redo()); return true; }
            return false;
        }

        function handleKeyDown(event) {
            if (event.target === shell.lengthInput) return;
            if (readOnly) return;
            if (historyShortcut(event)) return;
            if (event.code === "Space") {
                if (!event.repeat) { event.preventDefault(); engine.spaceDown(); render(); }
                return;
            }
            if (/^[0-9.,]$/.test(event.key) && beginLengthEntry(event.key)) { event.preventDefault(); return; }
            const beforeTool = engine.state().toolState.activeTool;
            const nextTool = tools.toolForShortcut(event.key);
            if (nextTool || event.key === "Escape") {
                event.preventDefault();
                mutate(() => engine.keyDown(event.key));
                if (beforeTool !== engine.state().toolState.activeTool) shell.hideLengthInput();
            }
        }

        function handleKeyUp(event) {
            if (readOnly || event.code !== "Space") return;
            event.preventDefault(); engine.spaceUp(); endPan(); render();
        }

        function commitLength() {
            if (readOnly) return;
            const lengthMm = Number(shell.lengthInput.value.trim().replace(",", "."));
            if (!Number.isFinite(lengthMm) || lengthMm <= 0) {
                shell.lengthInput.classList.add("is-invalid"); shell.lengthInput.select(); return;
            }
            shell.lengthInput.classList.remove("is-invalid");
            mutate(() => engine.inputLength(lengthMm));
            shell.hideLengthInput();
            shell.canvas.focus({ preventScroll: true });
        }

        function handleLengthKeyDown(event) {
            if (readOnly) return;
            if (event.key === "Enter") { event.preventDefault(); commitLength(); }
            else if (event.key === "Escape") { event.preventDefault(); shell.hideLengthInput(); shell.canvas.focus({ preventScroll: true }); render(); }
        }

        function handleToolbarClick(event) {
            const button = event.target.closest("[data-tool]");
            if (!button || button.disabled) return;
            shell.hideLengthInput(); engine.setTool(button.dataset.tool); shell.canvas.focus({ preventScroll: true }); render();
        }

        function handleViewClick(event) {
            const button = event.target.closest("[data-view-action]");
            if (!button) return;
            if (button.dataset.viewAction === "zoom-in") zoomBy(1.2);
            if (button.dataset.viewAction === "zoom-out") zoomBy(1 / 1.2);
            if (button.dataset.viewAction === "fit") fitView();
        }

        listen(shell.canvas, "pointerdown", handlePointerDown);
        listen(shell.canvas, "pointermove", handlePointerMove);
        listen(shell.canvas, "pointerup", handlePointerUp);
        listen(shell.canvas, "pointercancel", handlePointerUp);
        listen(shell.canvas, "wheel", handleWheel, { passive: false });
        listen(shell.editor, "keydown", handleKeyDown);
        listen(shell.editor, "keyup", handleKeyUp);
        listen(shell.lengthInput, "keydown", handleLengthKeyDown);
        listen(shell.editor, "click", handleToolbarClick);
        listen(shell.editor, "click", handleViewClick);

        let resizeObserver = null;
        if (typeof ResizeObserver === "function") { resizeObserver = new ResizeObserver(() => resize()); resizeObserver.observe(shell.canvasWrap); }
        else listen(window, "resize", resize);
        requestAnimationFrame(() => resize({ fit: true }));

        return Object.freeze({
            shell,
            state: () => Object.freeze({ camera, interaction: engine.state(), readOnly }),
            render, resize, fitView, zoomBy,
            setTool(tool) { if (!readOnly || tool === tools.TOOLS.HAND) { engine.setTool(tool); render(); } },
            undo() { if (!readOnly) mutate(() => engine.undo()); },
            redo() { if (!readOnly) mutate(() => engine.redo()); },
            destroy() {
                if (destroyed) return;
                destroyed = true;
                listeners.splice(0).forEach(dispose => dispose());
                if (resizeObserver) resizeObserver.disconnect();
                shell.destroy();
            },
        });
    }

    root.EditorController = Object.freeze({ DEFAULT_SNAP_TOLERANCE_PX, DEFAULT_HIT_TOLERANCE_PX, create });
})();