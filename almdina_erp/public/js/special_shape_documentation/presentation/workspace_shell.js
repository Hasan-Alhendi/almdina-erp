(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
    function translateCopy(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message, replacements);
        if (typeof __ === "function") return replacements === undefined ? __(message) : __(message, replacements);
        return String(message == null ? "" : message);
    }
    function tx(message, replacements) { return escapeHtml(translateCopy(message, replacements)); }
    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const dir = document.documentElement && document.documentElement.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }
    function uiButton(options) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for special-shape documentation");
        }
        return ui.button(options);
    }
    function tool(id, icon, label, key = "", disabled = false) {
        const text = tx(label);
        const title = escapeHtml(`${translateCopy(label)}${key ? ` (${key})` : ""}`);
        return `<button type="button" class="ald-doc-tool" data-tool="${escapeHtml(id)}" title="${title}" aria-label="${text}" ${disabled ? "disabled" : ""}><span>${icon}</span><small>${text}</small></button>`;
    }
    function templates(disabled = false) {
        const definitions = root.Templates && root.Templates.DEFINITIONS;
        if (!definitions) throw new Error("Special-shape templates are unavailable");
        return definitions.map(item => {
            const label = tx(item.label);
            return `<button type="button" class="ald-doc-template" data-template="${escapeHtml(item.id)}" title="${label}" aria-label="${label}" ${disabled ? "disabled" : ""}><span>${item.icon}</span><small>${label}</small></button>`;
        }).join("");
    }
    const LAYER_LABELS = Object.freeze({
        stroke: "Pen stroke {0}",
        line: "Line {0}",
        rect: "Rectangle {0}",
        ellipse: "Circle {0}",
        arrow: "Arrow {0}",
        dimension: "Dimension {0}",
        text: "Note {0}",
    });
    const SOURCE_LABELS = Object.freeze({
        image: "Image",
        template: "Ready-made shape",
        pen: "Drawing",
        mixed: "Mixed",
    });
    function mount(container, context) {
        const order = context.order, piece = context.piece, readOnly = !context.permissions.can_edit;
        const notice = context.manufacturing_notice || translateCopy("This documents the customer order and is not a manufacturing file");
        container.innerHTML = `<section class="ald-doc-workspace almdina-ui" dir="${uiDirection()}" data-read-only="${readOnly ? "1" : "0"}" aria-label="${tx("Special door documentation")}">
            <header class="ald-doc-topbar">
                <div class="ald-doc-title-group"><button type="button" class="ald-doc-back" data-action="back" aria-label="${tx("Back to the order")}"></button><div><h1>${tx("Special door documentation")}</h1><p><bdi>${escapeHtml(order.name)}</bdi> · ${escapeHtml(order.customer || "")}</p></div></div>
                <div class="ald-doc-piece-meta"><span>${tx("Door {0}", [piece.piece_no || ""])}</span><bdi>${tx("{0} × {1} cm", [piece.width_cm, piece.length_cm])}</bdi></div>
                <div class="ald-doc-save-group"><span class="ald-doc-save-state" data-save-state data-state="saved">${tx("Saved")}</span>${uiButton({ label: translateCopy("Save documentation"), variant: "primary", disabled: readOnly, attrs: { "data-action": "save" } })}</div>
            </header>
            <div class="ald-doc-layout">
                <aside class="ald-doc-panel ald-doc-start-panel">
                    <h2>${tx("Start here")}</h2>
                    <section class="ald-doc-source ald-doc-image-source is-active">
                        <span class="ald-doc-source-icon" aria-hidden="true">▧</span><span class="ald-doc-source-copy"><strong>${tx("Reference image")}</strong><small>${tx("Choose a suitable source — up to 8 MB")}</small></span>
                        <div class="ald-doc-source-actions">
                            <button type="button" class="ald-doc-source-action" data-action="choose-image" ${readOnly ? "disabled" : ""}><span aria-hidden="true">↑</span> ${tx("Upload an image")}</button>
                            <button type="button" class="ald-doc-source-action ald-doc-scan-action" data-action="scan-image" aria-describedby="ald-doc-scanner-status" ${readOnly ? "disabled" : ""}><span aria-hidden="true">▣</span> <span data-scan-label>${tx("Scan")}</span></button>
                            <button type="button" class="ald-doc-source-action ald-doc-camera-action" data-action="capture-image" ${readOnly ? "disabled" : ""}><span aria-hidden="true">◎</span> ${tx("Capture with the camera")}</button>
                        </div>
                        <div class="ald-doc-scanner-feedback" data-scanner-feedback hidden><p id="ald-doc-scanner-status" class="ald-doc-source-status" data-scanner-status role="status" aria-live="polite"></p><a class="ald-doc-scanner-install" data-scanner-install target="_blank" rel="noopener" hidden>${tx("Download the scanner program — one-time setup")}</a></div>
                    </section>
                    <input type="file" accept="image/jpeg,image/png,image/webp" data-reference-input hidden>
                    <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" data-camera-input hidden>
                    <section class="ald-doc-source ald-doc-templates"><strong>${tx("Ready-made shape")}</strong><div class="ald-doc-template-grid">${templates(readOnly)}</div></section>
                    <button type="button" class="ald-doc-source" data-tool="pen" ${readOnly ? "disabled" : ""}><span class="ald-doc-source-icon">✎</span><strong>${tx("Draw with the pen")}</strong><small>${tx("Automatic cleanup and alignment")}</small></button>
                    <section class="ald-doc-reference-controls" data-reference-controls hidden><div class="ald-doc-section-head"><strong>${tx("Reference image")}</strong><span data-reference-lock-label>${tx("Locked")}</span></div>
                        <div class="ald-doc-reference-crop-actions"><button type="button" class="ald-doc-crop-start" data-action="start-crop" ${readOnly ? "disabled" : ""}>${tx("Crop the image")}</button><button type="button" data-action="reset-reference-crop" data-reference-crop-reset hidden ${readOnly ? "disabled" : ""}>${tx("Restore the full image")}</button></div>
                        <label><span>${tx("Rotate")}</span><span class="ald-doc-inline"><button type="button" data-action="rotate-left" ${readOnly ? "disabled" : ""}>↶</button><bdi data-rotation>0°</bdi><button type="button" data-action="rotate-right" ${readOnly ? "disabled" : ""}>↷</button></span></label>
                        <label><span>${tx("Lock the image")}</span><input type="checkbox" checked data-reference-lock ${readOnly ? "disabled" : ""}></label>
                        <a class="ald-doc-download" data-reference-download target="_blank" rel="noopener" hidden>${tx("Download the original image for the designer")}</a>${uiButton({ label: translateCopy("Remove the image"), variant: "danger", className: "ald-doc-remove-image", disabled: readOnly, attrs: { "data-action": "remove-image" } })}
                    </section>
                </aside>
                <main class="ald-doc-stage"><canvas class="ald-doc-canvas" tabindex="0" aria-label="${tx("Door documentation canvas")}"></canvas><div class="ald-doc-hint" data-hint>${tx("Choose an image, a ready-made shape, or start with the smart pen")}</div>
                    <div class="ald-doc-crop-toolbar" data-crop-toolbar hidden role="toolbar" aria-label="${tx("Image crop tools")}"><strong>${tx("Crop the image")}</strong><span>${tx("Drag the frame or its handles")}</span><button type="button" data-action="auto-crop">${tx("Auto crop")}</button><button type="button" data-action="reset-crop">${tx("Reset")}</button><button type="button" data-action="cancel-crop">${tx("Cancel")}</button>${uiButton({ label: translateCopy("Apply"), variant: "primary", attrs: { "data-action": "apply-crop" } })}</div>
                    <div class="ald-doc-toolbar" role="toolbar" aria-label="${tx("Documentation tools")}">
                        ${tool("select", "↖", "Select", "V")}${tool("pen", "✎", "Smart pen", "P", readOnly)}${tool("line", "╱", "Line", "L", readOnly)}${tool("rect", "□", "Rectangle", "R", readOnly)}${tool("ellipse", "○", "Circle", "O", readOnly)}${tool("dimension", "↔", "Dimension", "D", readOnly)}${tool("text", "T", "Note", "T", readOnly)}
                        <span class="ald-doc-toolbar-separator"></span><button type="button" class="ald-doc-tool" data-action="undo" title="${tx("Undo Ctrl+Z")}"><span>↶</span><small>${tx("Undo")}</small></button><button type="button" class="ald-doc-tool" data-action="redo" title="${tx("Redo Ctrl+Y or Ctrl+Shift+Z")}"><span>↷</span><small>${tx("Redo")}</small></button>
                        <span class="ald-doc-toolbar-separator"></span><div class="ald-doc-zoom-controls" aria-label="${tx("Zoom the drawing area")}"><button type="button" data-action="zoom-out" title="${tx("Zoom out")}" aria-label="${tx("Zoom out")}">−</button><output class="ald-doc-zoom" data-zoom aria-live="polite">100%</output><button type="button" data-action="zoom-in" title="${tx("Zoom in")}" aria-label="${tx("Zoom in")}">+</button><button type="button" data-action="fit-view" title="${tx("Fit the drawing (F)")}" aria-label="${tx("Fit the drawing")}">${tx("Fit")}</button></div>
                    </div>
                </main>
                <aside class="ald-doc-panel ald-doc-detail-panel"><h2>${tx("Documentation details")}</h2><label class="ald-doc-notes"><span>${tx("Designer notes")}</span><textarea maxlength="2000" rows="5" data-notes placeholder="${tx("Write what the designer should pay attention to…")}" ${readOnly ? "readonly" : ""}></textarea></label>
                    <section><div class="ald-doc-section-head"><strong>${tx("Layers")}</strong><span data-element-count>0</span></div><div class="ald-doc-layers" data-layers></div></section>
                    <div class="ald-doc-warning">⚠ <span>${escapeHtml(notice)}</span></div>
                    <section class="ald-doc-preview"><div class="ald-doc-section-head"><strong>${tx("Documentation summary")}</strong><span>${tx("For print and the designer")}</span></div><dl><div><dt>${tx("Source")}</dt><dd data-summary-source>—</dd></div><div><dt>${tx("Documentation measurements")}</dt><dd data-summary-dimensions>0</dd></div><div><dt>${tx("Documentation notes")}</dt><dd data-summary-notes>${tx("None")}</dd></div></dl></section>
                </aside>
            </div>
        </section>`;
        const workspace = container.querySelector(".ald-doc-workspace");
        let cropActive = false;
        function setCropMode(active, canReset = true) {
            const next = Boolean(active);
            if (next) {
                workspace.querySelectorAll("button, input, textarea, select").forEach(control => {
                    if (control.closest("[data-crop-toolbar]") || control.dataset.action === "back") return;
                    if (!Object.prototype.hasOwnProperty.call(control.dataset, "cropWasDisabled")) control.dataset.cropWasDisabled = control.disabled ? "1" : "0";
                    control.disabled = true;
                });
            } else if (cropActive) {
                workspace.querySelectorAll("[data-crop-was-disabled]").forEach(control => { control.disabled = control.dataset.cropWasDisabled === "1"; delete control.dataset.cropWasDisabled; });
            }
            cropActive = next;
            workspace.dataset.cropMode = next ? "1" : "0";
            workspace.querySelector("[data-crop-toolbar]").hidden = !next;
            workspace.querySelector('[data-action="reset-crop"]').disabled = !canReset;
            workspace.querySelector(".ald-doc-canvas").setAttribute("aria-label", next ? translateCopy("Crop the reference image") : translateCopy("Door documentation canvas"));
        }
        return Object.freeze({
            workspace,
            canvas: workspace.querySelector(".ald-doc-canvas"),
            referenceInput: workspace.querySelector("[data-reference-input]"),
            cameraInput: workspace.querySelector("[data-camera-input]"),
            setActiveTool(value) { workspace.querySelectorAll("[data-tool]").forEach(button => button.classList.toggle("is-active", button.dataset.tool === value)); workspace.dataset.activeTool = value; },
            setPanMode(active) { workspace.dataset.panMode = active ? "1" : "0"; },
            setZoom(value) { workspace.querySelector("[data-zoom]").textContent = `${Math.max(10, Math.min(400, Math.round(Number(value) || 100)))}%`; },
            setSaveState(text, state) { const node = workspace.querySelector("[data-save-state]"); node.textContent = text; node.dataset.state = state; },
            setSaving(saving) { const button = workspace.querySelector('[data-action="save"]'); button.disabled = readOnly || saving; button.textContent = saving ? translateCopy("Saving…") : translateCopy("Save documentation"); },
            setScannerState({ busy = false, message = "", state = "idle", installerUrl = "" } = {}) {
                const button = workspace.querySelector('[data-action="scan-image"]'); const label = workspace.querySelector("[data-scan-label]"); const status = workspace.querySelector("[data-scanner-status]"); const feedback = workspace.querySelector("[data-scanner-feedback]"); const install = workspace.querySelector("[data-scanner-install]");
                button.disabled = readOnly || busy; button.dataset.busy = busy ? "1" : "0"; button.setAttribute("aria-busy", busy ? "true" : "false"); label.textContent = busy ? translateCopy("Opening the scanner…") : translateCopy("Scan");
                status.textContent = message; status.dataset.state = state; install.hidden = !installerUrl; if (installerUrl) install.href = installerUrl; else install.removeAttribute("href"); feedback.hidden = !message && !installerUrl;
            },
            setHint(value) { const node = workspace.querySelector("[data-hint]"); node.textContent = value || ""; node.hidden = !value; },
            render(document, state = {}) {
                const reference = document.reference; const controls = workspace.querySelector("[data-reference-controls]"); controls.hidden = !reference;
                const cropContract = root.ReferenceCrop; const download = workspace.querySelector("[data-reference-download]"); download.hidden = !reference; if (reference) { download.href = reference.fileUrl; workspace.querySelector("[data-rotation]").textContent = `${reference.rotationDeg}°`; workspace.querySelector("[data-reference-lock]").checked = reference.locked; workspace.querySelector("[data-reference-lock-label]").textContent = reference.locked ? translateCopy("Locked") : translateCopy("Unlocked"); workspace.querySelector("[data-reference-crop-reset]").hidden = !cropContract || cropContract.isFull(reference.crop); }
                workspace.querySelector("[data-notes]").value = document.notes;
                const layers = workspace.querySelector("[data-layers]"); const items = [];
                if (reference) items.push(`<button type="button" class="ald-doc-layer" data-layer="reference"><span>▧</span><strong>${tx("Reference image")}</strong><small>${reference.locked ? tx("Locked") : tx("Image is open")}</small></button>`);
                document.elements.forEach((element, index) => items.push(`<button type="button" class="ald-doc-layer ${state.selectedId === element.id ? "is-selected" : ""}" data-layer="${escapeHtml(element.id)}"><span>◇</span><strong>${tx(LAYER_LABELS[element.type] || "Element {0}", [index + 1])}</strong><small>${escapeHtml(element.type)}</small></button>`));
                layers.innerHTML = items.length ? items.join("") : `<div class="ald-doc-empty">${tx("No layers yet.")}</div>`;
                workspace.querySelector("[data-element-count]").textContent = String(document.elements.length + (reference ? 1 : 0));
                workspace.querySelector("[data-summary-source]").textContent = SOURCE_LABELS[document.source] ? translateCopy(SOURCE_LABELS[document.source]) : "—";
                workspace.querySelector("[data-summary-dimensions]").textContent = String(document.elements.filter(item => item.type === "dimension").length);
                workspace.querySelector("[data-summary-notes]").textContent = document.notes.trim() ? translateCopy("Present") : translateCopy("None");
                workspace.querySelector('[data-action="undo"]').disabled = !state.canUndo; workspace.querySelector('[data-action="redo"]').disabled = !state.canRedo;
                setCropMode(Boolean(state.cropMode), state.cropCanReset !== false);
            },
            destroy() { container.innerHTML = ""; },
        });
    }
    root.WorkspaceShell = Object.freeze({ mount });
})();
