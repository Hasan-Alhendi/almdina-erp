(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
    function tool(id, icon, label, key = "", disabled = false) { return `<button type="button" class="ald-doc-tool" data-tool="${id}" title="${label}${key ? ` (${key})` : ""}" aria-label="${label}" ${disabled ? "disabled" : ""}><span>${icon}</span><small>${label}</small></button>`; }
    function templates(disabled = false) {
        const definitions = root.Templates && root.Templates.DEFINITIONS;
        if (!definitions) throw new Error("Special-shape templates are unavailable");
        return definitions.map(item => `<button type="button" class="ald-doc-template" data-template="${item.id}" title="${item.label}" aria-label="${item.label}" ${disabled ? "disabled" : ""}><span>${item.icon}</span><small>${item.label}</small></button>`).join("");
    }
    function mount(container, context) {
        const order = context.order, piece = context.piece, readOnly = !context.permissions.can_edit;
        container.innerHTML = `<section class="ald-doc-workspace" dir="rtl" data-read-only="${readOnly ? "1" : "0"}" aria-label="توثيق الدرفة الخاصة">
            <header class="ald-doc-topbar">
                <div class="ald-doc-title-group"><button type="button" class="ald-doc-back" data-action="back" aria-label="العودة للطلب">→</button><div><h1>توثيق الدرفة الخاصة</h1><p><bdi>${escapeHtml(order.name)}</bdi> · ${escapeHtml(order.customer || "")}</p></div></div>
                <div class="ald-doc-piece-meta"><span>الدرفة ${escapeHtml(piece.piece_no || "")}</span><bdi>${escapeHtml(piece.width_cm)} × ${escapeHtml(piece.length_cm)} سم</bdi></div>
                <div class="ald-doc-save-group"><span class="ald-doc-save-state" data-save-state data-state="saved">محفوظ</span><button type="button" class="ald-doc-primary" data-action="save" ${readOnly ? "disabled" : ""}>حفظ التوثيق</button></div>
            </header>
            <div class="ald-doc-layout">
                <aside class="ald-doc-panel ald-doc-start-panel">
                    <h2>ابدأ من هنا</h2>
                    <section class="ald-doc-source ald-doc-image-source is-active">
                        <span class="ald-doc-source-icon" aria-hidden="true">▧</span><span class="ald-doc-source-copy"><strong>صورة مرجعية</strong><small>اختر المصدر المناسب — حتى 8 MB</small></span>
                        <div class="ald-doc-source-actions">
                            <button type="button" class="ald-doc-source-action" data-action="choose-image" ${readOnly ? "disabled" : ""}><span aria-hidden="true">↑</span> رفع صورة</button>
                            <button type="button" class="ald-doc-source-action ald-doc-scan-action" data-action="scan-image" aria-describedby="ald-doc-scanner-status" ${readOnly ? "disabled" : ""}><span aria-hidden="true">▣</span> <span data-scan-label>مسح بالسكانر</span></button>
                            <button type="button" class="ald-doc-source-action ald-doc-camera-action" data-action="capture-image" ${readOnly ? "disabled" : ""}><span aria-hidden="true">◎</span> التقاط بالكاميرا</button>
                        </div>
                        <div class="ald-doc-scanner-feedback" data-scanner-feedback hidden><p id="ald-doc-scanner-status" class="ald-doc-source-status" data-scanner-status role="status" aria-live="polite"></p><a class="ald-doc-scanner-install" data-scanner-install target="_blank" rel="noopener" hidden>تنزيل برنامج السكانر — تثبيت مرة واحدة</a></div>
                    </section>
                    <input type="file" accept="image/jpeg,image/png,image/webp" data-reference-input hidden>
                    <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" data-camera-input hidden>
                    <section class="ald-doc-source ald-doc-templates"><strong>شكل جاهز</strong><div class="ald-doc-template-grid">${templates(readOnly)}</div></section>
                    <button type="button" class="ald-doc-source" data-tool="pen" ${readOnly ? "disabled" : ""}><span class="ald-doc-source-icon">✎</span><strong>رسم بالقلم</strong><small>تنظيف وتثبيت تلقائي</small></button>
                    <section class="ald-doc-reference-controls" data-reference-controls hidden><div class="ald-doc-section-head"><strong>الصورة المرجعية</strong><span data-reference-lock-label>مقفلة</span></div>
                        <div class="ald-doc-reference-crop-actions"><button type="button" class="ald-doc-crop-start" data-action="start-crop" ${readOnly ? "disabled" : ""}>اقتصاص الصورة</button><button type="button" data-action="reset-reference-crop" data-reference-crop-reset hidden ${readOnly ? "disabled" : ""}>إعادة الصورة كاملة</button></div>
                        <label><span>تدوير</span><span class="ald-doc-inline"><button type="button" data-action="rotate-left" ${readOnly ? "disabled" : ""}>↶</button><bdi data-rotation>0°</bdi><button type="button" data-action="rotate-right" ${readOnly ? "disabled" : ""}>↷</button></span></label>
                        <label><span>الشفافية</span><span class="ald-doc-inline"><output data-opacity-output>72%</output><input type="range" min="10" max="100" value="72" data-opacity ${readOnly ? "disabled" : ""}></span></label>
                        <label><span>قفل الصورة</span><input type="checkbox" checked data-reference-lock ${readOnly ? "disabled" : ""}></label>
                        <a class="ald-doc-download" data-reference-download target="_blank" rel="noopener" hidden>تنزيل الصورة الأصلية للمصمم</a><button type="button" class="ald-doc-danger" data-action="remove-image" ${readOnly ? "disabled" : ""}>مسح الصورة</button>
                    </section>
                </aside>
                <main class="ald-doc-stage"><canvas class="ald-doc-canvas" tabindex="0" aria-label="لوحة توثيق الدرفة"></canvas><div class="ald-doc-hint" data-hint>اختر صورة أو شكلًا جاهزًا أو ابدأ بالقلم الذكي</div>
                    <div class="ald-doc-crop-toolbar" data-crop-toolbar hidden role="toolbar" aria-label="أدوات اقتصاص الصورة"><strong>اقتصاص الصورة</strong><span>اسحب الإطار أو مقابضه</span><button type="button" data-action="auto-crop">اقتصاص تلقائي</button><button type="button" data-action="reset-crop">إعادة ضبط</button><button type="button" data-action="cancel-crop">إلغاء</button><button type="button" class="ald-doc-primary" data-action="apply-crop">تطبيق</button></div>
                    <div class="ald-doc-toolbar" role="toolbar" aria-label="أدوات التوثيق">
                        ${tool("select", "↖", "تحديد", "V")}${tool("pen", "✎", "قلم ذكي", "P", readOnly)}${tool("line", "╱", "خط", "L", readOnly)}${tool("rect", "□", "مستطيل", "R", readOnly)}${tool("ellipse", "○", "دائرة", "O", readOnly)}${tool("dimension", "↔", "قياس", "D", readOnly)}${tool("text", "T", "ملاحظة", "T", readOnly)}
                        <span class="ald-doc-toolbar-separator"></span><button type="button" class="ald-doc-tool" data-action="undo" title="تراجع Ctrl+Z"><span>↶</span><small>تراجع</small></button><button type="button" class="ald-doc-tool" data-action="redo" title="إعادة Ctrl+Y أو Ctrl+Shift+Z"><span>↷</span><small>إعادة</small></button>
                        <span class="ald-doc-toolbar-separator"></span><div class="ald-doc-zoom-controls" aria-label="تكبير مساحة الرسم"><button type="button" data-action="zoom-out" title="تصغير" aria-label="تصغير">−</button><output class="ald-doc-zoom" data-zoom aria-live="polite">100%</output><button type="button" data-action="zoom-in" title="تكبير" aria-label="تكبير">+</button><button type="button" data-action="fit-view" title="ملاءمة الرسم (F)" aria-label="ملاءمة الرسم">ملاءمة</button></div>
                    </div>
                </main>
                <aside class="ald-doc-panel ald-doc-detail-panel"><h2>تفاصيل التوثيق</h2><label class="ald-doc-notes"><span>ملاحظات المصمم</span><textarea maxlength="2000" rows="5" data-notes placeholder="اكتب ما يجب أن ينتبه إليه المصمم…" ${readOnly ? "readonly" : ""}></textarea></label>
                    <section><div class="ald-doc-section-head"><strong>الطبقات</strong><span data-element-count>0</span></div><div class="ald-doc-layers" data-layers></div></section>
                    <div class="ald-doc-warning">⚠ <span>${escapeHtml(context.manufacturing_notice || "هذا توثيق لطلب العميل وليس ملف تصنيع")}</span></div>
                    <section class="ald-doc-preview"><div class="ald-doc-section-head"><strong>ملخص التوثيق</strong><span>للطباعة والمصمم</span></div><dl><div><dt>المصدر</dt><dd data-summary-source>—</dd></div><div><dt>القياسات</dt><dd data-summary-dimensions>0</dd></div><div><dt>الملاحظات</dt><dd data-summary-notes>لا يوجد</dd></div></dl></section>
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
            workspace.querySelector(".ald-doc-canvas").setAttribute("aria-label", next ? "اقتصاص الصورة المرجعية" : "لوحة توثيق الدرفة");
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
            setSaving(saving) { const button = workspace.querySelector('[data-action="save"]'); button.disabled = readOnly || saving; button.textContent = saving ? "جار الحفظ…" : "حفظ التوثيق"; },
            setScannerState({ busy = false, message = "", state = "idle", installerUrl = "" } = {}) {
                const button = workspace.querySelector('[data-action="scan-image"]'); const label = workspace.querySelector("[data-scan-label]"); const status = workspace.querySelector("[data-scanner-status]"); const feedback = workspace.querySelector("[data-scanner-feedback]"); const install = workspace.querySelector("[data-scanner-install]");
                button.disabled = readOnly || busy; button.dataset.busy = busy ? "1" : "0"; button.setAttribute("aria-busy", busy ? "true" : "false"); label.textContent = busy ? "جار فتح السكانر…" : "مسح بالسكانر";
                status.textContent = message; status.dataset.state = state; install.hidden = !installerUrl; if (installerUrl) install.href = installerUrl; else install.removeAttribute("href"); feedback.hidden = !message && !installerUrl;
            },
            setHint(value) { const node = workspace.querySelector("[data-hint]"); node.textContent = value || ""; node.hidden = !value; },
            render(document, state = {}) {
                const reference = document.reference; const controls = workspace.querySelector("[data-reference-controls]"); controls.hidden = !reference;
                const cropContract = root.ReferenceCrop; const download = workspace.querySelector("[data-reference-download]"); download.hidden = !reference; if (reference) { download.href = reference.fileUrl; workspace.querySelector("[data-rotation]").textContent = `${reference.rotationDeg}°`; const opacity = Math.round(reference.opacity * 100); workspace.querySelector("[data-opacity]").value = opacity; workspace.querySelector("[data-opacity-output]").textContent = `${opacity}%`; workspace.querySelector("[data-reference-lock]").checked = reference.locked; workspace.querySelector("[data-reference-lock-label]").textContent = reference.locked ? "مقفلة" : "غير مقفلة"; workspace.querySelector("[data-reference-crop-reset]").hidden = !cropContract || cropContract.isFull(reference.crop); }
                workspace.querySelector("[data-notes]").value = document.notes;
                const labels = { stroke: "رسم بالقلم", line: "خط", rect: "مستطيل", ellipse: "دائرة", arrow: "سهم", dimension: "قياس", text: "ملاحظة" };
                const layers = workspace.querySelector("[data-layers]"); const items = [];
                if (reference) items.push(`<button type="button" class="ald-doc-layer" data-layer="reference"><span>▧</span><strong>الصورة المرجعية</strong><small>${reference.locked ? "مقفلة" : "مفتوحة"}</small></button>`);
                document.elements.forEach((element, index) => items.push(`<button type="button" class="ald-doc-layer ${state.selectedId === element.id ? "is-selected" : ""}" data-layer="${escapeHtml(element.id)}"><span>◇</span><strong>${labels[element.type] || "عنصر"} ${index + 1}</strong><small>${element.type}</small></button>`));
                layers.innerHTML = items.length ? items.join("") : '<div class="ald-doc-empty">لا توجد طبقات بعد.</div>';
                workspace.querySelector("[data-element-count]").textContent = String(document.elements.length + (reference ? 1 : 0));
                const sourceLabels = { image: "صورة", template: "شكل جاهز", pen: "رسم", mixed: "مختلط" };
                workspace.querySelector("[data-summary-source]").textContent = sourceLabels[document.source] || "—";
                workspace.querySelector("[data-summary-dimensions]").textContent = String(document.elements.filter(item => item.type === "dimension").length);
                workspace.querySelector("[data-summary-notes]").textContent = document.notes.trim() ? "موجودة" : "لا يوجد";
                workspace.querySelector('[data-action="undo"]').disabled = !state.canUndo; workspace.querySelector('[data-action="redo"]').disabled = !state.canRedo;
                setCropMode(Boolean(state.cropMode), state.cropCanReset !== false);
            },
            destroy() { container.innerHTML = ""; },
        });
    }
    root.WorkspaceShell = Object.freeze({ mount });
})();
