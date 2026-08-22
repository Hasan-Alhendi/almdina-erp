(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);

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
        const D = root.Document;
        if (!D) throw new Error("Special-shape document contract is unavailable");
        if (tool === "line") return { id: D.id("line"), type: "line", start, end, style: { color: "#1463e6", width: 3 } };
        if (tool === "dimension") return { id: D.id("dimension"), type: "dimension", start, end, valueMm: Math.round(distance(start, end) * 10) / 10, unit: "mm", style: { color: "#173c75", width: 2 } };
        const xMm = Math.min(start.xMm, end.xMm), yMm = Math.min(start.yMm, end.yMm), widthMm = Math.abs(end.xMm - start.xMm), heightMm = Math.abs(end.yMm - start.yMm);
        if (tool === "rect" || tool === "ellipse") return { id: D.id(tool), type: tool, xMm, yMm, widthMm, heightMm, style: { color: "#1463e6", width: 3 } };
        return null;
    }
    function mount(wrapper) {
        const D = root.Document, H = root.History, T = root.Templates, Pen = root.SmartPen, Transform = root.ElementTransform, Api = root.WorkspaceApi, Scanner = root.ScannerBridge;
        const Shell = root.WorkspaceShell, Canvas = root.CanvasRenderer;
        if (![D, H, T, Pen, Transform, Api, Scanner, Shell, Canvas].every(Boolean)) throw new Error("Special-shape documentation dependencies are incomplete");
        const main = wrapper.querySelector(".layout-main-section");
        if (!main) throw new Error("Documentation page main section is missing");
        let generation = 0, suspended = false, shell = null, renderer = null, context = null, history = null;
        let tool = "select", selectedId = null, draft = null, dragging = false, saving = false, scanning = false, pendingFileRemovals = new Set();
        const resizeHandler = () => { if (renderer) renderer.draw(); };
        const beforeUnloadHandler = event => {
            if (!history || !history.isDirty()) return;
            event.preventDefault();
            event.returnValue = "";
        };

        function cleanup() { window.removeEventListener("resize", resizeHandler); window.removeEventListener("beforeunload", beforeUnloadHandler); if (shell) shell.destroy(); shell = null; renderer = null; history = null; context = null; scanning = false; }
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
        async function upload(file, options = {}) {
            if (!file || !context || !context.permissions.can_edit) return false; if (file.size > 8 * 1024 * 1024) { frappe.msgprint("حجم الصورة يتجاوز 8 MB."); return false; }
            const token = generation, activeContext = context;
            shell.setSaveState("جار رفع الصورة…", "saving");
            try {
                const encoded = await readFile(file); const previous = history.get().reference; const result = await Api.upload(activeContext.order.name, activeContext.piece.name, file.name, encoded);
                if (token !== generation || suspended || !history) {
                    await Api.removeImage(activeContext.order.name, activeContext.piece.name, result.file_url).catch(error => console.warn("Stale reference cleanup failed", error));
                    return false;
                }
                if (previous && previous.fileUrl !== result.file_url) pendingFileRemovals.add(previous.fileUrl);
                commit(D.setReference(history.get(), { fileUrl: result.file_url, rotationDeg: 0, opacity: 0.72, locked: true })); frappe.show_alert({ message: options.successMessage || "تم رفع الصورة وإضافتها إلى التوثيق.", indicator: "green" }, 3); return true;
            } catch (error) { console.error("Reference upload failed", error); frappe.msgprint("تعذر رفع الصورة. استخدم JPG أو PNG أو WEBP بحجم لا يتجاوز 8 MB."); render(); return false; }
            finally { if (shell) { shell.referenceInput.value = ""; shell.cameraInput.value = ""; } }
        }
        function scannerErrorMessage(error) {
            if (error && error.code === Scanner.ERROR_CODES.FORBIDDEN) return "هذا الموقع غير مضاف إلى المواقع المسموحة في جسر السكانر. اطلب من مسؤول النظام إضافته ثم إعادة تشغيل الجسر.";
            if (error && error.code === Scanner.ERROR_CODES.BUSY) return "السكانر مشغول بعملية أخرى. انتظر انتهاءها ثم أعد المحاولة.";
            if (error && error.code === Scanner.ERROR_CODES.SCAN_FAILED) return "تعذر إتمام المسح. تحقق من أن Windows يرى السكانر وأنه غير مستخدم من برنامج آخر.";
            if (error && error.code === Scanner.ERROR_CODES.IMAGE_TOO_LARGE) return "الصورة الناتجة من السكانر تتجاوز 8 MB. خفّض دقة المسح ثم حاول مرة أخرى.";
            if (error && error.code === Scanner.ERROR_CODES.INVALID_RESPONSE) return "استجابة السكانر غير صالحة. أعد تشغيل Almdina Scanner Bridge ثم حاول مرة أخرى.";
            return "برنامج السكانر غير مثبت أو متوقف. ثبّته مرة واحدة، أو افتحه من قائمة ابدأ إذا كان مثبتًا.";
        }
        async function scanReference() {
            if (scanning || !context || !context.permissions.can_edit) return;
            const token = generation; let feedback = "", feedbackState = "idle", installerUrl = ""; scanning = true;
            shell.setScannerState({ busy: true, message: "سيظهر مربع Windows لاختيار جهاز السكانر وإعدادات المسح." });
            try {
                await Scanner.health(); if (token !== generation || suspended) return;
                const file = await Scanner.scan(); if (token !== generation || suspended) return;
                if (!file) { feedback = "تم إلغاء عملية المسح ولم تُضف صورة."; return; }
                const added = await upload(file, { successMessage: "تم المسح وإضافة الصورة إلى التوثيق." });
                feedback = added ? "تمت إضافة صورة السكانر. يمكنك الآن الرسم أو إضافة القياسات." : "تعذر إضافة صورة السكانر إلى التوثيق.";
                feedbackState = added ? "success" : "error";
            } catch (error) {
                console.error("Scanner acquisition failed", error); feedback = scannerErrorMessage(error); feedbackState = "error";
                if (error && error.code === Scanner.ERROR_CODES.UNAVAILABLE) installerUrl = Scanner.INSTALLER_URL;
                frappe.msgprint(feedback);
            } finally {
                scanning = false; if (shell && token === generation && !suspended) shell.setScannerState({ busy: false, message: feedback, state: feedbackState, installerUrl });
            }
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
        function pointerMove(event) {
            if (!dragging || !draft) return;
            const point = renderer.screenToMm(event); draft.end = point;
            if (tool === "select" && draft.original) {
                const transformed = draft.mode === "move"
                    ? Transform.translate(draft.original, point.xMm - draft.start.xMm, point.yMm - draft.start.yMm, history.get().canvas)
                    : Transform.resize(draft.original, draft.mode, point, history.get().canvas);
                draft.previewDocument = Transform.replace(history.get(), transformed);
                renderer.render(draft.previewDocument, { selectedId }); return;
            }
            if (tool === "pen") {
                const samples = typeof event.getCoalescedEvents === "function" ? event.getCoalescedEvents() : [];
                (samples.length ? samples : [event]).forEach(sample => draft.points.push(renderer.screenToMm(sample)));
            } else draft.points = [draft.start, point];
            renderer.render(history.get(), { selectedId, preview: draft.points });
        }
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
                else if (target.dataset.action === "choose-image") shell.referenceInput.click(); else if (target.dataset.action === "capture-image") shell.cameraInput.click(); else if (target.dataset.action === "scan-image") scanReference(); else if (target.dataset.action === "undo") { history.undo(); selectedId = null; render(); }
                else if (target.dataset.action === "redo") { history.redo(); selectedId = null; render(); }
                else if (target.dataset.action === "rotate-left") updateReference({ rotationDeg: history.get().reference.rotationDeg - 90 });
                else if (target.dataset.action === "rotate-right") updateReference({ rotationDeg: history.get().reference.rotationDeg + 90 });
                else if (target.dataset.action === "remove-image") removeImage();
                else if (target.dataset.layer && target.dataset.layer !== "reference") { selectedId = target.dataset.layer; tool = "select"; render(); }
            });
            shell.referenceInput.addEventListener("change", () => upload(shell.referenceInput.files && shell.referenceInput.files[0]));
            shell.cameraInput.addEventListener("change", () => upload(shell.cameraInput.files && shell.cameraInput.files[0], { successMessage: "تم التقاط الصورة وإضافتها إلى التوثيق." }));
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
