(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const v4 = window.AlmdinaDoorDrawingV4;
    const geometry = v4.Geometry;
    const documentModel = v4.DocumentModel;
    const dimensionDomain = v4.DimensionDomain;
    const viewport = v4.Viewport;
    const renderer = v4.CanvasRenderer;
    const tools = v4.ToolStateMachine;
    const sessions = root.EditorSession;
    const keyboard = root.KeyboardController;
    const shellFactory = root.WorkspaceShell;
    if (!geometry || !documentModel || !dimensionDomain || !viewport || !renderer || !tools || !sessions || !keyboard || !shellFactory) throw new Error("Professional editor dependencies are incomplete");

    const TOOL_LABELS = Object.freeze({ select: "تحديد", node: "تعديل النقاط", pen: "القلم الذكي", dimension: "الأبعاد", hand: "تحريك اللوحة" });
    const SNAP_LABELS = Object.freeze({ close: "إغلاق ذكي", endpoint: "نقطة نهاية", intersection: "تقاطع", midpoint: "منتصف", perpendicular: "عمودي", edge: "على ضلع", parallel: "متوازي", extension: "امتداد", horizontal: "أفقي", vertical: "رأسي", angle: "زاوية", grid: "شبكة" });

    function create(options = {}) {
        if (!options.container) throw new Error("Professional editor requires a container");
        const readOnly = Boolean(options.readOnly);
        const shell = shellFactory.mount(options.container, options.meta || {});
        const session = sessions.create({ document: options.document, initialTool: readOnly ? tools.TOOLS.HAND : tools.TOOLS.SELECT });
        let camera = viewport.create();
        let dpr = Math.max(1, Number(window.devicePixelRatio || 1));
        let lastPoint = Object.freeze({ x: 0, y: 0 });
        let pan = null;
        let numericMode = null;
        let dirty = false;
        let destroyed = false;
        let didFit = false;
        const listeners = [];

        function listen(target, type, handler, opts) { target.addEventListener(type, handler, opts); listeners.push(() => target.removeEventListener(type, handler, opts)); }
        function screenPoint(event) { const rect = shell.canvas.getBoundingClientRect(); return Object.freeze({ x: event.clientX - rect.left, y: event.clientY - rect.top }); }
        function world(point) { return viewport.screenToWorld(camera, point); }
        function interactionOptions(event) {
            const tolerance = viewport.screenToleranceToMm(camera, event && event.altKey ? 0 : 11);
            return Object.freeze({ toleranceMm: tolerance, releaseToleranceMm: viewport.screenToleranceToMm(camera, 16), hitToleranceMm: viewport.screenToleranceToMm(camera, 9), gridStepMm: viewport.gridStepMm(camera), angleToleranceDeg: event && event.shiftKey ? 180 : undefined });
        }
        function markDirty() { if (readOnly || dirty) return; dirty = true; shell.setSaveState("غير محفوظ", "dirty"); if (typeof options.onDirty === "function") options.onDirty(true); }
        function mutate(callback) {
            const before = session.state().document;
            const result = callback();
            if (session.state().document !== before) { markDirty(); if (typeof options.onChange === "function") options.onChange(session.state().document); }
            render();
            return result;
        }
        function pathBounds(document, pathId) {
            const path = documentModel.pathById(document, pathId); if (!path) return null;
            const ids = new Set();
            (path.segmentIds || []).forEach(id => { const segment = documentModel.segmentById(document, id); if (segment) { ids.add(segment.startNodeId); ids.add(segment.endNodeId); } });
            const nodes = [...ids].map(id => documentModel.nodeById(document, id)).filter(Boolean); if (!nodes.length) return null;
            const xs = nodes.map(node => node.xMm), ys = nodes.map(node => node.yMm);
            const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
            return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
        }
        function layerItems(state) { return (state.document.paths || []).map((path, index) => ({ id: path.id, label: index === 0 ? "محيط الدرفة" : `مسار ${index + 1}`, closed: Boolean(path.closed) })); }
        function propertiesModel(state) {
            const selection = state.selection;
            if (selection && selection.kind === "path") { const box = pathBounds(state.document, selection.id); return { kind: "path", title: "Selection", values: box ? [{label:"X",value:`${geometry.roundMm(box.x)} mm`},{label:"Y",value:`${geometry.roundMm(box.y)} mm`},{label:"W",value:`${geometry.roundMm(box.width)} mm`},{label:"H",value:`${geometry.roundMm(box.height)} mm`}] : [], help:"V للتحديد · A لتعديل النقاط" }; }
            if (selection && selection.kind === "node") { const node = documentModel.nodeById(state.document, selection.id); return { kind: "node", title: "Node", values: node ? [{label:"X",value:`${geometry.roundMm(node.xMm)} mm`},{label:"Y",value:`${geometry.roundMm(node.yMm)} mm`}] : [], help:"اسحب النقطة؛ المحاذاة والـSnap يعملان أثناء الحركة." }; }
            if (selection && selection.kind === "dimension") { const measurement = dimensionDomain.resolve(state.document, selection.id); return { kind: "dimension", title: "Dimension", values: measurement ? [{label:"Length",value:`${geometry.roundMm(measurement.valueMm)} mm`}] : [], help:"اكتب قيمة مباشرة ثم Enter لتثبيت البعد." }; }
            return { kind: "document", title: "Frame", values: [{label:"W",value:`${geometry.roundMm(state.document.blank.widthMm)} mm`},{label:"H",value:`${geometry.roundMm(state.document.blank.heightMm)} mm`}], help:"P القلم الذكي · D الأبعاد · Space للتحريك" };
        }
        function snapText(preview) { if (!preview || preview.type === "free") return ""; const base = SNAP_LABELS[preview.semantic] || SNAP_LABELS[preview.type] || "Snap"; return preview.semantic === "angle" ? `${base} ${Math.round(preview.angleDeg || 0)}°` : base; }
        function hintFor(state) {
            if (readOnly) return "عرض فقط · Space أو أداة اليد للتحريك";
            if (state.drag) return "Snap ذكي أثناء تحريك النقطة · Esc لإلغاء الحركة";
            if (state.toolState.activeTool === "pen") return state.activePathId ? "انقر لإضافة ضلع · اقترب من البداية للإغلاق · اكتب الطول مباشرة" : "انقر لبدء الرسم · P";
            if (state.toolState.activeTool === "node") return "انقر واسحب نقطة · A";
            if (state.toolState.activeTool === "dimension") return "انقر على ضلع لإضافة/تحديد البعد · D";
            if (state.selection) return "العنصر محدد · A للنقاط · Esc لإلغاء التحديد";
            return "V تحديد · A نقاط · P قلم · D أبعاد";
        }
        function render() {
            if (destroyed) return;
            const state = session.state();
            renderer.render(shell.canvas, { camera, document: state.document, interactionState: readOnly ? { ...state, preview:null, selection:null, drag:null } : state, dpr, showNodes: !readOnly && (state.toolState.activeTool === "node" || Boolean(state.drag)) });
            const cursor = world(lastPoint);
            shell.setActiveTool(state.toolState.activeTool);
            shell.setStatus(TOOL_LABELS[state.toolState.activeTool] || state.toolState.activeTool, `X ${geometry.roundMm(cursor.xMm)} · Y ${geometry.roundMm(cursor.yMm)} mm`, snapText(state.preview));
            shell.setZoom(`${viewport.zoomPercent(camera)}%`);
            shell.setHint(hintFor(state));
            shell.renderLayers(layerItems(state), state.selection && state.selection.kind === "path" ? state.selection.id : null);
            shell.renderProperties(propertiesModel(state));
            shell.workspace.classList.toggle("is-panning", Boolean(pan));
        }
        function resize(opts = {}) { const rect = shell.stage.getBoundingClientRect(); camera = viewport.resize(camera, Math.max(1,rect.width), Math.max(1,rect.height)); dpr = Math.max(1, Number(window.devicePixelRatio || 1)); renderer.resizeCanvas(shell.canvas, Math.max(1,rect.width), Math.max(1,rect.height), dpr); if (!didFit || opts.fit) { camera = viewport.fitBlank(camera, session.state().document.blank); didFit = true; } render(); }
        function beginPan(event, point) { pan = { pointerId:event.pointerId, last:point }; shell.canvas.setPointerCapture(event.pointerId); render(); }
        function endPan(event) { if (!pan || (event && event.pointerId !== pan.pointerId)) return; pan = null; render(); }
        function pointerDown(event) { if (![0,1].includes(event.button)) return; const point = screenPoint(event); lastPoint = point; shell.canvas.focus({preventScroll:true}); hideNumeric(); const tool = session.state().toolState.activeTool; if (readOnly || event.button === 1 || tool === "hand") { event.preventDefault(); beginPan(event,point); return; } event.preventDefault(); shell.canvas.setPointerCapture(event.pointerId); const result = mutate(() => session.pointerDown(world(point), interactionOptions(event))); if (result && result.kind === "constraint-protected-node") shell.setHint("هذه النقطة مرتبطة بقيد هندسي؛ عدّل البعد بدل كسر القيد."); }
        function pointerMove(event) { const point = screenPoint(event); lastPoint = point; if (pan && pan.pointerId === event.pointerId) { camera = viewport.panBy(camera, point.x-pan.last.x, point.y-pan.last.y); pan = {pointerId:event.pointerId,last:point}; render(); return; } if (readOnly) { render(); return; } mutate(() => session.pointerMove(world(point), interactionOptions(event))); }
        function pointerUp(event) { endPan(event); if (!readOnly) mutate(() => session.pointerUp()); if (shell.canvas.hasPointerCapture && shell.canvas.hasPointerCapture(event.pointerId)) shell.canvas.releasePointerCapture(event.pointerId); }
        function wheel(event) { event.preventDefault(); const point = screenPoint(event); lastPoint = point; camera = viewport.zoomAt(camera, point, Math.exp(-event.deltaY*.0015)); render(); }
        function setTool(tool) { if (readOnly && tool !== "hand") return; hideNumeric(); session.setTool(tool); render(); }
        function hideNumeric() { numericMode = null; shell.hideNumeric(); }
        function beginNumeric(seed) { if (readOnly) return false; const state = session.state(); if (state.toolState.activeTool === "pen" && state.activePathId && state.preview) numericMode = "pen"; else if (state.toolState.activeTool === "dimension" && state.selection && state.selection.kind === "dimension") numericMode = "dimension"; else return false; shell.showNumeric(lastPoint, seed === "." || seed === "," ? `0${seed}` : seed); return true; }
        function beginDimensionEntry() { const state = session.state(); if (readOnly || state.toolState.activeTool !== "dimension" || !state.selection || state.selection.kind !== "dimension") return false; const measurement = dimensionDomain.resolve(state.document,state.selection.id); if (!measurement) return false; numericMode="dimension"; shell.showNumeric(lastPoint,String(geometry.roundMm(measurement.valueMm))); return true; }
        function commitNumeric() { const value = Number(String(shell.numeric.value||"").replace(",",".")); if (!Number.isFinite(value) || value<=0) { shell.numeric.select(); return; } const result = numericMode === "dimension" ? mutate(() => session.inputDimensionValue(value)) : mutate(() => session.inputLength(value)); if (result && result.kind === "dimension-drive-failed") { shell.setHint("لا يمكن تطبيق هذا القياس دون كسر قيود الشكل."); shell.numeric.select(); return; } hideNumeric(); shell.canvas.focus({preventScroll:true}); }
        function numericKey(event) { if (event.key === "Enter") { event.preventDefault(); commitNumeric(); } else if (event.key === "Escape") { event.preventDefault(); hideNumeric(); shell.canvas.focus({preventScroll:true}); } }
        function undo() { if (!readOnly) mutate(() => session.undo()); }
        function redo() { if (!readOnly) mutate(() => session.redo()); }
        function click(event) { const toolButton = event.target.closest("[data-tool]"); if (toolButton) { setTool(toolButton.dataset.tool); return; } const action = event.target.closest("[data-action]"); if (action) { const name=action.dataset.action; if(name==="undo")undo(); else if(name==="redo")redo(); else if(name==="save"&&options.onSave)options.onSave(session.state().document); else if(name==="back"&&options.onBack)options.onBack(dirty); return; } const view = event.target.closest("[data-view]"); if(view){ if(view.dataset.view==="in")camera=viewport.zoomAt(camera,{x:camera.viewportWidthPx/2,y:camera.viewportHeightPx/2},1.2); if(view.dataset.view==="out")camera=viewport.zoomAt(camera,{x:camera.viewportWidthPx/2,y:camera.viewportHeightPx/2},1/1.2); if(view.dataset.view==="fit")camera=viewport.fitBlank(camera,session.state().document.blank); render(); return; } const layer=event.target.closest("[data-path-id]"); if(layer){ session.selectPath(layer.dataset.pathId); render(); } }

        if (readOnly) { shell.workspace.querySelectorAll("[data-tool]").forEach(button => button.disabled = button.dataset.tool !== "hand"); const save=shell.workspace.querySelector('[data-action="save"]'); if(save) save.style.display="none"; }
        listen(shell.canvas,"pointerdown",pointerDown); listen(shell.canvas,"pointermove",pointerMove); listen(shell.canvas,"pointerup",pointerUp); listen(shell.canvas,"pointercancel",pointerUp); listen(shell.canvas,"wheel",wheel,{passive:false}); listen(shell.workspace,"click",click); listen(shell.numeric,"keydown",numericKey);
        const keys = keyboard.mount(shell.workspace,{ tool:setTool, escape(){ if(!readOnly)mutate(() => session.cancel()); else render(); }, undo, redo, spaceDown(){ session.spaceDown(); render(); }, spaceUp(){ session.spaceUp(); endPan(); render(); }, numeric:beginNumeric, enter:beginDimensionEntry });
        let resizeObserver=null; if(typeof ResizeObserver==="function"){resizeObserver=new ResizeObserver(()=>resize());resizeObserver.observe(shell.stage);}else listen(window,"resize",resize);
        requestAnimationFrame(()=>resize({fit:true}));

        return Object.freeze({
            state:()=>Object.freeze({interaction:session.state(),camera,readOnly,dirty}),
            render,resize,setTool,
            markSaved(){dirty=false;shell.setSaveState("محفوظ","saved");if(typeof options.onDirty==="function")options.onDirty(false);render();},
            setSaving(saving){shell.setSaving(saving);shell.setSaveState(saving?"يتم الحفظ…":(dirty?"غير محفوظ":"محفوظ"),saving?"saving":(dirty?"dirty":"saved"));},
            destroy(){if(destroyed)return;destroyed=true;keys.destroy();listeners.splice(0).forEach(dispose=>dispose());if(resizeObserver)resizeObserver.disconnect();shell.destroy();}
        });
    }
    root.EditorController = Object.freeze({ create });
})();
