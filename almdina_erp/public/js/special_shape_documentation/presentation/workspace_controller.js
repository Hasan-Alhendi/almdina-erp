(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const D = root.Document, H = root.History, T = root.Templates, Pen = root.SmartPen, Transform = root.ElementTransform, Api = root.WorkspaceApi;
    const Shell = root.WorkspaceShell, Canvas = root.CanvasRenderer;
    if (![D, H, T, Pen, Transform, Api, Shell, Canvas].every(Boolean)) throw new Error("Special-shape documentation dependencies are incomplete");

    const TOOL_HINTS = Object.freeze({
        select: "انقر على عنصر لتحديده. استخدم Delete للحذف.", pen: "ارسم بحرية؛ سننظف الخط ونثبت اتجاهاته.",
        line: "اسحب من بداية الخط إلى نهايته.", rect: "اسحب لرسم مستطيل.", ellipse: "اسحب لرسم دائرة أو قطع ناقص.",
        dimension: "اسحب بين نقطتي القياس.", text: "انقر في موضع الملاحظة.",
    });
    function readFile(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result || "")); reader.onerror = reject; reader.readAsDataURL(file); }); }
    function confirmAsync(message) { return new Promise(resolve => frappe.confirm(message, () => resolve(true), () => resolve(false))); }
    function promptText() { return new Promise(resolve => frappe.prompt([{ fieldname: "text", fieldtype: "Data", label: "نص الملاحظة", reqd: 1, maxlength: 300 }], values => resolve(String(values.text || "").trim()), "إضافة ملاحظة", "إضافة")); }
    function distance(a, b) { return Math.hypot(b.xMm - a.xMm, b.yMm - a.yMm); }
    function makeElement(tool, start, end) {
        if (tool === "line") return { id: D.id("line"), type: "line", start, end, style: { color: "#1463e6", width: 3 } };
        if (tool === "dimension") return { id: D.id("dimension"), type: "dimension", start, end, valueMm: Math.round(distance(start, end) * 10) / 10, unit: "mm", style: { color: "#173c75", width: 2 } };
        const xMm = Math.min(start.xMm, end.xMm), yMm = Math.min(start.yMm, end.yMm), widthMm = Math.abs(end.xMm - start.xMm), heightMm = Math.abs(end.yMm - start.yMm);
        if (tool === "rect" || tool === "ellipse") return { id: D.id(tool), type: tool, xMm, yMm, widthMm, heightMm, style: { color: "#1463e6", width: 3 } };
        return null;
    }
    function mount(wrapper) {
        const main = wrapper.querySelector(".layout-main-section");
        if (!main) throw new Error("Documentation page main section is missing");
        let generation = 0, suspended = false, shell = null, renderer = null, context = null, history = null;
        let tool = "select", selectedId = null, draft = null, dragging = false, saving = false, pendingFileRemovals = new Set();
        const resizeHandler = () => { if (renderer) renderer.draw(); };
        const beforeUnloadHandler = event => {
            if (!history || !history.isDirty()) return;
            event.preventDefault();
            event.returnValue = "";
        };

        function cleanup() { window.removeEventListener("resize", resizeHandler); window.removeEventListener("beforeunload", beforeUnloadHandler); if (shell) shell.destroy(); shell = null; renderer = null; history = null; context = null; }
        function showMessage(message, error = false) { main.innerHTML = `<div class="ald-doc-message ${error ? "is-error" : ""}">${frappe.utils.escape_html(String(message))}</div>`; }
        function back() { if (context) frappe.set_route("Form", "Door Cutting Order", context.order.name); else frappe.set_route("List", "Door Cutting Order"); }
        function render() {
            if (!history || !shell || !renderer) return; const state = history.state();
            shell.render(state.document, { ...state, selectedId }); shell.setActiveTool(tool); shell.setHint(TOOL_HINTS[tool]); shell.setSaveState(state.dirty ? "غير محفوظ" : "محفوظ", state.dirty ? "dirty" : "saved");
            renderer.render(draft && draft.previewDocument || state.document, { selectedId, preview: draft && draft.points });
        }
        function commit(next) { history.commit(next); render(); }
        function chooseTool(next) { if (!context.permissions.can_edit && next !== "select") return; tool = next; draft = null; dragging = false; render(); }
        async function save() {
            if (saving || !context.permissions.can_edit) return; const document = history.get();
            if (!D.hasContent(document)) { frappe.msgprint("أضف صورة مرجعية أو عنصرًا توضيحيًا قبل الحفظ."); return; }
            saving = true; shell.setSaving(true); shell.setSaveState("جار الحفظ…", "saving");
            try {
                const result = await Api.save(context.order.name, context.piece.name, D.toStored(document)); context = { ...context, piece: result.piece }; history.markSaved();
                const removals = [...pendingFileRemovals]; pendingFileRemovals.clear(); await Promise.all(removals.map(url => Api.removeImage(context.order.name, context.piece.name, url).catch(error => console.warn("Deferred reference cleanup failed", error))));
                frappe.show_alert({ message: "تم حفظ توثيق الدرفة.", indicator: "green" }, 3); render();
            } catch (error) { console.error("Documentation save failed", error); shell.setSaveState("فشل الحفظ", "error"); frappe.msgprint("تعذر حفظ التوثيق. تحقق من البيانات والصلاحيات ثم حاول مرة أخرى."); }
            finally { saving = false; if (shell) shell.setSaving(false); }
        }
        async function requestBack() { if (!history || !history.isDirty()) { back(); return; } if (await confirmAsync("لديك تعديلات غير محفوظة. هل تريد الرجوع دون حفظ؟")) back(); }
        async function upload(file) {
            if (!file || !context.permissions.can_edit) return; if (file.size > 8 * 1024 * 1024) { frappe.msgprint("حجم الصورة يتجاوز 8 MB."); return; }
            shell.setSaveState("جار رفع الصورة…", "saving");
            try {
                const encoded = await readFile(file); const previous = history.get().reference; const result = await Api.upload(context.order.name, context.piece.name, file.name, encoded);
                if (previous && previous.fileUrl !== result.file_url) pendingFileRemovals.add(previous.fileUrl);
                commit(D.setReference(history.get(), { fileUrl: result.file_url, rotationDeg: 0, opacity: 0.72, locked: true })); frappe.show_alert({ message: "تم رفع الصورة وإضافتها إلى التوثيق.", indicator: "green" }, 3);
            } catch (error) { console.error("Reference upload failed", error); frappe.msgprint("تعذر رفع الصورة. استخدم JPG أو PNG أو WEBP بحجم لا يتجاوز 8 MB."); render(); }
            finally { shell.referenceInput.value = ""; }
        }
        async function removeImage() { if (!context.permissions.can_edit) return; const reference = history.get().reference; if (!reference || !await confirmAsync("هل تريد مسح الصورة المرجعية من التوثيق؟")) return; pendingFileRemovals.add(reference.fileUrl); commit(D.setReference(history.get(), null)); }
        function updateReference(changes) { if (!context.permissions.can_edit) return; const current = history.get(); if (!current.reference) return; commit(D.setReference(current, { ...current.reference, ...changes })); }
        async function finishPen() {
            if (!draft || !draft.points || draft.points.length < 2) { draft = null; render(); return; }
            const cleaned = Pen.clean(draft.points, { toleranceMm: Math.max(3, history.get().canvas.widthMm * 0.006), joinToleranceMm: Math.max(18, history.get().canvas.widthMm * 0.025) }); let points = cleaned.points, closed = false;
            if (cleaned.suggestClose && await confirmAsync("النهاية قريبة من البداية. هل تريد إغلاق الشكل؟")) { points = Pen.close(points); closed = true; }
            commit(D.addElement(history.get(), { id: D.id("stroke"), type: "stroke", points, closed, style: { color: "#1463e6", width: 3 } })); draft = null;
        }
        function pointerDown(event) {
            if (!context.permissions.can_edit && tool !== "select") return; shell.canvas.setPointerCapture(event.pointerId); const point = renderer.screenToMm(event);
            if (tool === "select") { const hit = renderer.hitTest(event); selectedId = hit && hit.id || null; if (hit && context.permissions.can_edit) { dragging = true; draft = { mode: renderer.selectionRegion(event, hit), start: point, original: D.clone(hit), previewDocument: history.get() }; } render(); return; }
            if (tool === "text") { promptText().then(text => { if (text) commit(D.addElement(history.get(), { id: D.id("text"), type: "text", position: point, text, style: { color: "#9a4b00" } })); }); return; }
            dragging = true; draft = { start: point, points: [point], end: point };
        }
        function pointerMove(event) { if (!dragging || !draft) return; const point = renderer.screenToMm(event); draft.end = point; if (tool === "select" && draft.original) { const transformed = draft.mode === "move" ? Transform.translate(draft.original, point.xMm - draft.start.xMm, point.yMm - draft.start.yMm, history.get().canvas) : Transform.resize(draft.original, draft.mode, point, history.get().canvas); draft.previewDocument = Transform.replace(history.get(), transformed); renderer.render(draft.previewDocument, { selectedId }); return; } if (tool === "pen") draft.points.push(point); else draft.points = [draft.start, point]; renderer.render(history.get(), { selectedId, preview: draft.points }); }
        function pointerUp() {
            if (!dragging || !draft) return; dragging = false;
            if (tool === "select" && draft.previewDocument) { const next = draft.previewDocument; draft = null; commit(next); return; }
            if (tool === "pen") { finishPen(); return; }
            const element = makeElement(tool, draft.start, draft.end); draft = null; if (element && distance(element.start || { xMm: element.xMm, yMm: element.yMm }, element.end || { xMm: element.xMm + element.widthMm, yMm: element.yMm + element.heightMm }) > 3) commit(D.addElement(history.get(), element)); else render();
        }
        function keydown(event) {
            if (!history || /INPUT|TEXTAREA/.test(event.target.tagName)) return;
            const key = event.key.toLowerCase(); if ((event.ctrlKey || event.metaKey) && key === "s") { event.preventDefault(); save(); return; }
            if ((event.ctrlKey || event.metaKey) && key === "z") { event.preventDefault(); if (event.shiftKey) history.redo(); else history.undo(); selectedId = null; render(); return; }
            const shortcuts = { v: "select", p: "pen", l: "line", r: "rect", o: "ellipse", d: "dimension", t: "text" }; if (shortcuts[key]) { event.preventDefault(); chooseTool(shortcuts[key]); return; }
            if ((event.key === "Delete" || event.key === "Backspace") && selectedId && context.permissions.can_edit) { event.preventDefault(); commit(D.removeElement(history.get(), selectedId)); selectedId = null; }
            if (event.key === "Escape") { draft = null; dragging = false; selectedId = null; render(); }
        }
        function bindEvents() {
            const workspace = shell.workspace;
            workspace.addEventListener("click", event => {
                const target = event.target.closest("button"); if (!target) return;
                if (target.dataset.tool) chooseTool(target.dataset.tool);
                else if (target.dataset.template && context.permissions.can_edit) { commit(T.apply(history.get(), target.dataset.template)); selectedId = null; }
                else if (target.dataset.action === "back") requestBack(); else if (target.dataset.action === "save") save();
                else if (target.dataset.action === "choose-image") shell.referenceInput.click(); else if (target.dataset.action === "undo") { history.undo(); selectedId = null; render(); }
                else if (target.dataset.action === "redo") { history.redo(); selectedId = null; render(); }
                else if (target.dataset.action === "rotate-left") updateReference({ rotationDeg: history.get().reference.rotationDeg - 90 });
                else if (target.dataset.action === "rotate-right") updateReference({ rotationDeg: history.get().reference.rotationDeg + 90 });
                else if (target.dataset.action === "remove-image") removeImage();
                else if (target.dataset.layer && target.dataset.layer !== "reference") { selectedId = target.dataset.layer; tool = "select"; render(); }
            });
            shell.referenceInput.addEventListener("change", () => upload(shell.referenceInput.files && shell.referenceInput.files[0]));
            workspace.querySelector("[data-opacity]").addEventListener("change", event => updateReference({ opacity: Number(event.target.value) / 100 }));
            workspace.querySelector("[data-reference-lock]").addEventListener("change", event => updateReference({ locked: Boolean(event.target.checked) }));
            workspace.querySelector("[data-notes]").addEventListener("change", event => commit(D.setNotes(history.get(), event.target.value)));
            shell.canvas.addEventListener("pointerdown", pointerDown); shell.canvas.addEventListener("pointermove", pointerMove); shell.canvas.addEventListener("pointerup", pointerUp); shell.canvas.addEventListener("pointercancel", pointerUp);
            workspace.addEventListener("keydown", keydown); window.addEventListener("resize", resizeHandler); window.addEventListener("beforeunload", beforeUnloadHandler);
        }
        async function open(route) {
            const token = ++generation; suspended = false; cleanup(); showMessage("جار تحميل توثيق الدرفة…");
            try {
                const loaded = await Api.load(route.orderName, route.pieceName); if (token !== generation || suspended) return; context = loaded;
                const document = D.fromStored(loaded.piece.special_shape_drawing_json, loaded.piece); history = H.create(document); main.innerHTML = ""; shell = Shell.mount(main, loaded); renderer = Canvas.create(shell.canvas); bindEvents(); chooseTool("select");
                if (!loaded.permissions.can_edit && loaded.permissions.edit_reason) frappe.show_alert({ message: loaded.permissions.edit_reason, indicator: "orange" }, 5);
            } catch (error) { console.error("Documentation workspace load failed", error); if (token === generation) showMessage("تعذر تحميل الدرفة. افتح التوثيق من الطلب وتحقق من الصلاحيات.", true); }
        }
        function suspend() { suspended = true; generation += 1; cleanup(); }
        return Object.freeze({ open, suspend, destroy: suspend, showRouteError: message => showMessage(message, true) });
    }
    root.WorkspaceController = Object.freeze({ mount });
})();
