(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);

    const TOOL_HINTS = Object.freeze({
        select: "Click an element to select it. Use Delete to remove it.",
        pen: "Draw freely; the line will be cleaned and its directions fixed.",
        line: "Drag from the start of the line to its end.",
        rect: "Drag to draw a rectangle.",
        ellipse: "Drag to draw a circle or ellipse.",
        dimension: "Drag between the two measurement points.",
        text: "Click where the note should go.",
    });
    function translateCopy(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message, replacements);
        if (typeof __ === "function") return replacements === undefined ? __(message) : __(message, replacements);
        return String(message == null ? "" : message);
    }
    function readFile(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result || "")); reader.onerror = reject; reader.readAsDataURL(file); }); }
    function confirmAsync(message) { return new Promise(resolve => frappe.confirm(message, () => resolve(true), () => resolve(false))); }
    function promptText() { return new Promise(resolve => frappe.prompt([{ fieldname: "text", fieldtype: "Data", label: translateCopy("Note text"), reqd: 1, maxlength: 300 }], values => resolve(String(values.text || "").trim()), translateCopy("Add a note"), translateCopy("Add"))); }
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
        const D = root.Document, Crop = root.ReferenceCrop, H = root.History, T = root.Templates, Pen = root.SmartPen, Transform = root.ElementTransform, Clipboard = root.ElementClipboard, Shortcuts = root.KeyboardShortcuts, Api = root.WorkspaceApi, Scanner = root.ScannerBridge;
        const Shell = root.WorkspaceShell, Canvas = root.CanvasRenderer;
        if (![D, Crop, H, T, Pen, Transform, Clipboard, Shortcuts, Api, Scanner, Shell, Canvas].every(Boolean)) throw new Error("Special-shape documentation dependencies are incomplete");
        const main = wrapper.querySelector(".layout-main-section");
        if (!main) throw new Error("Documentation page main section is missing");
        let generation = 0, suspended = false, shell = null, renderer = null, context = null, history = null;
        let tool = "select", selectedId = null, draft = null, cropSession = null, dragging = false, saving = false, scanning = false, pendingFileRemovals = new Set();
        const clipboard = Clipboard.create(D, Transform);
        let spacePressed = false, panning = false, panPoint = null;
        const resizeHandler = () => { if (renderer) { renderer.draw(); syncZoom(); } };
        const keyupHandler = event => {
            if (Shortcuts.physicalCode(event) !== "Space") return;
            spacePressed = false;
            if (!panning && shell) shell.setPanMode(false);
        };
        const beforeUnloadHandler = event => {
            if (!history || (!history.isDirty() && !cropSession)) return;
            event.preventDefault();
            event.returnValue = "";
        };

        function cleanup() { window.removeEventListener("resize", resizeHandler); window.removeEventListener("beforeunload", beforeUnloadHandler); window.removeEventListener("keyup", keyupHandler); if (shell) shell.destroy(); shell = null; renderer = null; history = null; context = null; cropSession = null; draft = null; dragging = false; scanning = false; clipboard.clear(); spacePressed = false; panning = false; panPoint = null; }
        function showMessage(message, error = false) { main.innerHTML = `<div class="ald-doc-message ${error ? "is-error" : ""}">${frappe.utils.escape_html(String(message))}</div>`; }
        function back() {
            if (window.opener && !window.opener.closed) { window.close(); if (window.closed) return; }
            if (context) frappe.set_route("Form", "Door Cutting Order", context.order.name); else frappe.set_route("List", "Door Cutting Order");
        }
        function render() {
            if (!history || !shell || !renderer) return; const state = history.state();
            shell.render(state.document, { ...state, selectedId, cropMode: Boolean(cropSession), cropCanReset: cropSession ? !Crop.isFull(cropSession.value) : false }); shell.setActiveTool(tool); shell.setHint(cropSession ? translateCopy("Drag inside the frame to move it, or drag a handle to choose the required part.") : translateCopy(TOOL_HINTS[tool])); shell.setSaveState(cropSession ? translateCopy("Crop in progress") : (state.dirty ? translateCopy("Unsaved") : translateCopy("Saved")), cropSession || state.dirty ? "dirty" : "saved");
            renderer.render(draft && draft.previewDocument || state.document, { selectedId, preview: draft && draft.points, cropSession: cropSession ? { active: true, value: cropSession.value } : null });
            syncZoom();
        }
        function syncZoom() { if (shell && renderer) shell.setZoom(renderer.zoomPercentage()); }
        function commit(next) { history.commit(next); render(); }
        function chooseTool(next) { if (cropSession || (!context.permissions.can_edit && next !== "select")) return; tool = next; draft = null; dragging = false; render(); }
        async function save() {
            if (saving || !context.permissions.can_edit) return; const document = history.get();
            if (cropSession) { frappe.msgprint(translateCopy("Apply or cancel the crop before saving the documentation.")); return; }
            if (!D.hasContent(document)) { frappe.msgprint(translateCopy("Add a reference image or an explanatory element before saving.")); return; }
            saving = true; shell.setSaving(true); shell.setSaveState(translateCopy("Saving…"), "saving");
            try {
                const result = await Api.save(context.order.name, context.piece.name, D.toStored(document)); context = { ...context, piece: result.piece }; history.markSaved(document);
                const removals = [...pendingFileRemovals]; pendingFileRemovals.clear(); await Promise.all(removals.map(url => Api.removeImage(context.order.name, context.piece.name, url).catch(error => console.warn("Deferred reference cleanup failed", error))));
                frappe.show_alert({ message: translateCopy("Door documentation was saved."), indicator: "green" }, 3); render();
            } catch (error) { console.error("Documentation save failed", error); shell.setSaveState(translateCopy("Save failed"), "error"); frappe.msgprint(translateCopy("Could not save the documentation. Check the data and permissions, then try again.")); }
            finally { saving = false; if (shell) shell.setSaving(false); }
        }
        async function requestBack() {
            if (cropSession && !await confirmAsync(translateCopy("The crop has not been applied yet. Go back and cancel the crop?"))) return;
            if (!history || !history.isDirty()) { back(); return; }
            if (await confirmAsync(translateCopy("You have unsaved changes. Go back without saving?"))) back();
        }
        async function upload(file, options = {}) {
            if (!file || !context || !context.permissions.can_edit) return false; if (file.size > 8 * 1024 * 1024) { frappe.msgprint(translateCopy("The image is larger than 8 MB.")); return false; }
            const token = generation, activeContext = context;
            shell.setSaveState(translateCopy("Uploading the image…"), "saving");
            try {
                const encoded = await readFile(file); const previous = history.get().reference; const result = await Api.upload(activeContext.order.name, activeContext.piece.name, file.name, encoded);
                if (token !== generation || suspended || !history) {
                    await Api.removeImage(activeContext.order.name, activeContext.piece.name, result.file_url).catch(error => console.warn("Stale reference cleanup failed", error));
                    return false;
                }
                if (previous && previous.fileUrl !== result.file_url) pendingFileRemovals.add(previous.fileUrl);
                commit(D.setReference(history.get(), { fileUrl: result.file_url, rotationDeg: 0, opacity: 1, locked: true, crop: Crop.FULL })); frappe.show_alert({ message: options.successMessage || translateCopy("The image was uploaded and added to the documentation."), indicator: "green" }, 3); return true;
            } catch (error) { console.error("Reference upload failed", error); frappe.msgprint(translateCopy("Could not upload the image. Use JPG, PNG, or WEBP no larger than 8 MB.")); render(); return false; }
            finally { if (shell) { shell.referenceInput.value = ""; shell.cameraInput.value = ""; } }
        }
        function scannerErrorMessage(error) {
            if (error && error.code === Scanner.ERROR_CODES.FORBIDDEN) return translateCopy("This site is not allowed by the scanner bridge. Ask a system administrator to add it, then restart the bridge.");
            if (error && error.code === Scanner.ERROR_CODES.BUSY) return translateCopy("The scanner is busy with another job. Wait until it finishes, then try again.");
            if (error && error.code === Scanner.ERROR_CODES.NO_SCANNER) return translateCopy("No compatible scanner was found. Make sure it is connected and recognized by Windows, then try again.");
            if (error && error.code === Scanner.ERROR_CODES.INVALID_IMAGE) return translateCopy("The scanner returned an unsupported image and it could not be converted. Send the Scanner Bridge log to a system administrator.");
            if (error && error.code === Scanner.ERROR_CODES.SCAN_FAILED) return translateCopy("The scan could not be completed. Check that Windows sees the scanner and that no other program is using it.");
            if (error && error.code === Scanner.ERROR_CODES.IMAGE_TOO_LARGE) return translateCopy("The scanned image is larger than 8 MB. Lower the scan resolution and try again.");
            if (error && error.code === Scanner.ERROR_CODES.INVALID_RESPONSE) return translateCopy("The scanner response is invalid. Restart Almdina Scanner Bridge and try again.");
            return translateCopy("The scanner program is not installed or is stopped. Install it once, or open it from the Start menu if it is already installed.");
        }
        async function scanReference() {
            if (scanning || !context || !context.permissions.can_edit) return;
            const token = generation; let feedback = "", feedbackState = "idle", installerUrl = ""; scanning = true;
            shell.setScannerState({ busy: true, message: translateCopy("Windows will ask you to choose the scanner and the scan settings.") });
            try {
                await Scanner.health(); if (token !== generation || suspended) return;
                const file = await Scanner.scan(); if (token !== generation || suspended) return;
                if (!file) { feedback = translateCopy("The scan was cancelled and no image was added."); return; }
                const added = await upload(file, { successMessage: translateCopy("The scan finished and the image was added to the documentation.") });
                feedback = added ? translateCopy("The scanner image was added. You can now draw or add dimensions.") : translateCopy("Could not add the scanner image to the documentation.");
                feedbackState = added ? "success" : "error";
            } catch (error) {
                console.error("Scanner acquisition failed", error); feedback = scannerErrorMessage(error); feedbackState = "error";
                if (error && error.code === Scanner.ERROR_CODES.UNAVAILABLE) installerUrl = Scanner.INSTALLER_URL;
                frappe.msgprint(feedback);
            } finally {
                scanning = false; if (shell && token === generation && !suspended) shell.setScannerState({ busy: false, message: feedback, state: feedbackState, installerUrl });
            }
        }
        async function removeImage() { if (!context.permissions.can_edit) return; const reference = history.get().reference; if (!reference || !await confirmAsync(translateCopy("Remove the reference image from the documentation?"))) return; pendingFileRemovals.add(reference.fileUrl); commit(D.setReference(history.get(), null)); }
        function updateReference(changes) { if (!context.permissions.can_edit || cropSession) return; const current = history.get(); if (!current.reference) return; commit(D.setReference(current, { ...current.reference, ...changes })); }
        function startCrop() {
            const reference = history.get().reference;
            if (!context.permissions.can_edit || !reference || cropSession) return;
            tool = "select"; selectedId = null; draft = null; dragging = false;
            cropSession = { value: Crop.normalize(reference.crop) };
            render();
        }
        function cancelCrop() { if (!cropSession) return; cropSession = null; draft = null; dragging = false; render(); }
        function applyCrop() {
            if (!cropSession || !context.permissions.can_edit) return;
            const crop = Crop.normalize(cropSession.value); const imageSize = renderer.referenceImageSize();
            cropSession = null; draft = null; dragging = false;
            const current = history.get();
            commit(D.setReference(current, { ...current.reference, crop, imageSize: imageSize || current.reference.imageSize }));
        }
        function resetCrop() { if (!cropSession) return; cropSession = { value: Crop.normalize(Crop.FULL) }; draft = null; dragging = false; render(); }
        function resetReferenceCrop() {
            const current = history.get();
            if (!context.permissions.can_edit || !current.reference || Crop.isFull(current.reference.crop)) return;
            commit(D.setReference(current, { ...current.reference, crop: Crop.FULL }));
        }
        function autoCrop() {
            if (!cropSession) return;
            const suggested = renderer.suggestReferenceCrop();
            if (!suggested || Crop.isFull(suggested)) { frappe.show_alert({ message: translateCopy("No clear white margins were found. Adjust the frame manually."), indicator: "orange" }, 4); return; }
            cropSession = { value: suggested }; draft = null; dragging = false; render();
        }
        async function finishPen() {
            if (!draft || !draft.points || draft.points.length < 2) { draft = null; render(); return; }
            const cleaned = Pen.clean(draft.points, { toleranceMm: Math.max(3, history.get().canvas.widthMm * 0.006), joinToleranceMm: Math.max(18, history.get().canvas.widthMm * 0.025) }); let points = cleaned.points, closed = false;
            if (cleaned.suggestClose && await confirmAsync(translateCopy("The end is close to the start. Close the shape?"))) { points = Pen.close(points); closed = true; }
            commit(D.addElement(history.get(), { id: D.id("stroke"), type: "stroke", points, closed, style: { color: "#1463e6", width: 3 } })); draft = null;
        }
        function pointerDown(event) {
            shell.canvas.focus({ preventScroll: true });
            if (event.button === 1 || spacePressed) {
                event.preventDefault();
                shell.canvas.setPointerCapture(event.pointerId);
                panning = true;
                panPoint = { x: event.clientX, y: event.clientY };
                shell.setPanMode(true);
                return;
            }
            if (event.button !== 0 || (!context.permissions.can_edit && tool !== "select")) return;
            if (cropSession) {
                const region = renderer.cropRegion(event, cropSession.value);
                const point = renderer.cropPoint(event);
                if (!region || !point) return;
                shell.canvas.setPointerCapture(event.pointerId); dragging = true;
                draft = { mode: "crop", region, start: point, originalCrop: Crop.normalize(cropSession.value) };
                return;
            }
            shell.canvas.setPointerCapture(event.pointerId); const point = renderer.screenToMm(event);
            if (tool === "select") { const hit = renderer.hitTest(event); selectedId = hit && hit.id || null; if (hit && context.permissions.can_edit) { dragging = true; draft = { mode: renderer.selectionRegion(event, hit), start: point, original: D.clone(hit), previewDocument: history.get() }; } render(); return; }
            if (tool === "text") { promptText().then(text => { if (text) commit(D.addElement(history.get(), { id: D.id("text"), type: "text", position: point, text, style: { color: "#9a4b00" } })); }); return; }
            dragging = true; draft = { start: point, points: [point], end: point };
        }
        function pointerMove(event) {
            if (panning && panPoint) {
                renderer.panBy(event.clientX - panPoint.x, event.clientY - panPoint.y);
                panPoint = { x: event.clientX, y: event.clientY };
                return;
            }
            if (!dragging || !draft) return;
            if (draft.mode === "crop") {
                const point = renderer.cropPoint(event); if (!point) return;
                cropSession = { value: Crop.transform(draft.originalCrop, draft.region, { x: point.x - draft.start.x, y: point.y - draft.start.y }) };
                render(); return;
            }
            const point = renderer.screenToMm(event); draft.end = point;
            if (tool === "select" && draft.original) {
                const transformed = draft.mode === "move"
                    ? Transform.translate(draft.original, point.xMm - draft.start.xMm, point.yMm - draft.start.yMm)
                    : Transform.resize(draft.original, draft.mode, point);
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
            if (panning) {
                panning = false;
                panPoint = null;
                if (shell) shell.setPanMode(spacePressed);
                return;
            }
            if (!dragging || !draft) return; dragging = false;
            if (draft.mode === "crop") { draft = null; render(); return; }
            if (tool === "select" && draft.previewDocument) { const next = draft.previewDocument; draft = null; commit(next); return; }
            if (tool === "pen") { finishPen(); return; }
            const element = makeElement(tool, draft.start, draft.end); draft = null; if (element && distance(element.start || { xMm: element.xMm, yMm: element.yMm }, element.end || { xMm: element.xMm + element.widthMm, yMm: element.yMm + element.heightMm }) > 3) commit(D.addElement(history.get(), element)); else render();
        }
        function undo() { if (cropSession) return; history.undo(); selectedId = null; render(); }
        function redo() { if (cropSession) return; history.redo(); selectedId = null; render(); }
        function copySelection() {
            const selected = history.get().elements.find(element => element.id === selectedId);
            if (!selected || cropSession) return false;
            return clipboard.copy(selected);
        }
        function pasteSelection() {
            if (cropSession || !clipboard.canPaste() || !context.permissions.can_edit) return false;
            const offsetMm = renderer.screenDeltaToMm(24);
            const pasted = clipboard.paste(offsetMm);
            selectedId = pasted.id;
            commit(D.addElement(history.get(), pasted));
            return true;
        }
        function deleteSelection() {
            if (cropSession || !selectedId || !context.permissions.can_edit) return false;
            const next = D.removeElement(history.get(), selectedId);
            selectedId = null;
            commit(next);
            return true;
        }
        function escapeInteraction() {
            if (cropSession) { cancelCrop(); return; }
            draft = null;
            dragging = false;
            selectedId = null;
            render();
        }
        function executeShortcut(command) {
            if (command === "save") { save(); return true; }
            if (command === "undo") { undo(); return true; }
            if (command === "redo") { redo(); return true; }
            if (command === "copy") return copySelection();
            if (command === "paste") return pasteSelection();
            if (command === "delete") return deleteSelection();
            if (command === "escape") { escapeInteraction(); return true; }
            if (command === "pan") { spacePressed = true; shell.setPanMode(true); return true; }
            if (command === "fit-view") { renderer.fitToContent(); syncZoom(); return true; }
            if (command === "reset-zoom") { renderer.resetZoom(); syncZoom(); return true; }
            if (["select", "pen", "line", "rect", "ellipse", "dimension", "text"].includes(command)) { chooseTool(command); return true; }
            return false;
        }
        function keydown(event) {
            if (!history || Shortcuts.isEditableTarget(event.target)) return;
            if (cropSession && event.code === "Enter") { event.preventDefault(); applyCrop(); return; }
            const command = Shortcuts.resolve(event);
            if (command && executeShortcut(command)) event.preventDefault();
        }
        function wheel(event) {
            if (!renderer) return;
            event.preventDefault();
            if (event.ctrlKey || event.metaKey) {
                renderer.zoomAt(event, Math.exp(-Number(event.deltaY || 0) * 0.002));
                syncZoom();
                return;
            }
            const dx = event.shiftKey ? -Number(event.deltaY || 0) : -Number(event.deltaX || 0);
            const dy = event.shiftKey ? 0 : -Number(event.deltaY || 0);
            renderer.panBy(dx, dy);
        }
        function bindEvents() {
            const workspace = shell.workspace;
            workspace.addEventListener("click", event => {
                const target = event.target.closest("button"); if (!target) return;
                if (target.dataset.tool) chooseTool(target.dataset.tool);
                else if (target.dataset.template && context.permissions.can_edit) { selectedId = null; commit(T.apply(history.get(), target.dataset.template)); }
                else if (target.dataset.action === "back") requestBack(); else if (target.dataset.action === "save") save();
                else if (target.dataset.action === "choose-image") shell.referenceInput.click(); else if (target.dataset.action === "capture-image") shell.cameraInput.click(); else if (target.dataset.action === "scan-image") scanReference(); else if (target.dataset.action === "undo") undo();
                else if (target.dataset.action === "redo") redo();
                else if (target.dataset.action === "zoom-out") { renderer.zoomBy(0.8); syncZoom(); }
                else if (target.dataset.action === "zoom-in") { renderer.zoomBy(1.25); syncZoom(); }
                else if (target.dataset.action === "fit-view") { renderer.fitToContent(); syncZoom(); }
                else if (target.dataset.action === "start-crop") startCrop();
                else if (target.dataset.action === "auto-crop") autoCrop();
                else if (target.dataset.action === "reset-crop") resetCrop();
                else if (target.dataset.action === "cancel-crop") cancelCrop();
                else if (target.dataset.action === "apply-crop") applyCrop();
                else if (target.dataset.action === "reset-reference-crop") resetReferenceCrop();
                else if (target.dataset.action === "rotate-left") updateReference({ rotationDeg: history.get().reference.rotationDeg - 90 });
                else if (target.dataset.action === "rotate-right") updateReference({ rotationDeg: history.get().reference.rotationDeg + 90 });
                else if (target.dataset.action === "remove-image") removeImage();
                else if (target.dataset.layer && target.dataset.layer !== "reference") { selectedId = target.dataset.layer; tool = "select"; render(); }
            });
            shell.referenceInput.addEventListener("change", () => upload(shell.referenceInput.files && shell.referenceInput.files[0]));
            shell.cameraInput.addEventListener("change", () => upload(shell.cameraInput.files && shell.cameraInput.files[0], { successMessage: translateCopy("The photo was captured and added to the documentation.") }));
            workspace.querySelector("[data-reference-lock]").addEventListener("change", event => updateReference({ locked: Boolean(event.target.checked) }));
            workspace.querySelector("[data-notes]").addEventListener("change", event => commit(D.setNotes(history.get(), event.target.value)));
            shell.canvas.addEventListener("pointerdown", pointerDown); shell.canvas.addEventListener("pointermove", pointerMove); shell.canvas.addEventListener("pointerup", pointerUp); shell.canvas.addEventListener("pointercancel", pointerUp); shell.canvas.addEventListener("wheel", wheel, { passive: false });
            workspace.addEventListener("keydown", keydown); window.addEventListener("keyup", keyupHandler); window.addEventListener("resize", resizeHandler); window.addEventListener("beforeunload", beforeUnloadHandler);
        }
        async function open(route) {
            const token = ++generation; suspended = false; cleanup(); showMessage(translateCopy("Loading door documentation…"));
            try {
                const loaded = await Api.load(route.orderName, route.pieceName); if (token !== generation || suspended) return;
                // A view-only order link cannot unlock editing through stage permissions.
                context = route.readOnly
                    ? { ...loaded, permissions: { ...loaded.permissions, can_edit: false } }
                    : loaded;
                const document = D.fromStored(context.piece.special_shape_drawing_json, context.piece); history = H.create(document); main.innerHTML = ""; shell = Shell.mount(main, context); renderer = Canvas.create(shell.canvas); bindEvents(); chooseTool("select");
                if (!context.permissions.can_edit && context.permissions.edit_reason) frappe.show_alert({ message: context.permissions.edit_reason, indicator: "orange" }, 5);
            } catch (error) { console.error("Documentation workspace load failed", error); if (token === generation) showMessage(translateCopy("Could not load the door. Open the documentation from the order and check the permissions."), true); }
        }
        function suspend() { suspended = true; generation += 1; cleanup(); }
        return Object.freeze({ open, suspend, destroy: suspend, showRouteError: message => showMessage(message, true) });
    }
    root.WorkspaceController = Object.freeze({ mount });
})();
