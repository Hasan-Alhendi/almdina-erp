(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const ICONS = Object.freeze({
        select: "↖", node: "◇", pen: "⌁", dimension: "↔", hand: "✋"
    });
    const KEYS = Object.freeze({ select: "V", node: "A", pen: "P", dimension: "D", hand: "Space" });

    function toolButton(tool, label) {
        return `<button type="button" class="ald-prof-tool" data-tool="${tool}" title="${label} (${KEYS[tool]})" aria-label="${label}"><span class="ald-prof-tool-icon">${ICONS[tool]}</span><span class="ald-prof-tool-key">${KEYS[tool]}</span></button>`;
    }
    function escapeHtml(value) {
        const node = document.createElement("div");
        node.textContent = String(value ?? "");
        return node.innerHTML;
    }
    function mount(container, meta = {}) {
        container.innerHTML = `
            <section class="ald-prof-workspace" dir="rtl" aria-label="مساحة رسم الدرفة الاحترافية">
                <header class="ald-prof-topbar">
                    <div class="ald-prof-topbar-start">
                        <button type="button" class="ald-prof-icon-button" data-action="back" aria-label="العودة للطلب">←</button>
                        <div class="ald-prof-file-title"><strong>${escapeHtml(meta.orderName || "درفة خاصة")}</strong><span>${escapeHtml(meta.pieceLabel || "")}</span></div>
                    </div>
                    <div class="ald-prof-topbar-center">
                        <button type="button" class="ald-prof-icon-button" data-action="undo" title="تراجع Ctrl+Z">↶</button>
                        <button type="button" class="ald-prof-icon-button" data-action="redo" title="إعادة Ctrl+Shift+Z">↷</button>
                        <span class="ald-prof-save-state" data-save-state>محفوظ</span>
                    </div>
                    <div class="ald-prof-topbar-end"><button type="button" class="ald-prof-save" data-action="save">حفظ</button></div>
                </header>
                <div class="ald-prof-body">
                    <aside class="ald-prof-sidebar ald-prof-sidebar-left">
                        <div class="ald-prof-panel-tabs"><button class="is-active" type="button">Layers</button><button type="button">Assets</button></div>
                        <div class="ald-prof-panel-heading">طبقات الرسم</div>
                        <div class="ald-prof-layers" data-layers></div>
                    </aside>
                    <main class="ald-prof-stage" data-stage>
                        <canvas class="ald-prof-canvas" tabindex="0" aria-label="مساحة رسم الدرفة"></canvas>
                        <div class="ald-prof-hint" data-hint></div>
                        <input class="ald-prof-numeric" data-numeric type="text" inputmode="decimal" autocomplete="off" spellcheck="false" hidden aria-label="القيمة بالميليمتر">
                        <div class="ald-prof-zoom"><button type="button" data-view="out">−</button><button type="button" data-view="fit" data-zoom>100%</button><button type="button" data-view="in">+</button></div>
                        <div class="ald-prof-toolbar" role="toolbar" aria-label="أدوات الرسم">
                            ${toolButton("select", "تحديد")}${toolButton("node", "تعديل النقاط")}<span class="ald-prof-separator"></span>${toolButton("pen", "القلم الذكي")}${toolButton("dimension", "الأبعاد")}${toolButton("hand", "تحريك اللوحة")}
                        </div>
                    </main>
                    <aside class="ald-prof-sidebar ald-prof-sidebar-right">
                        <div class="ald-prof-panel-tabs"><button class="is-active" type="button">Design</button><button type="button">Prototype</button></div>
                        <div class="ald-prof-properties" data-properties></div>
                    </aside>
                </div>
                <footer class="ald-prof-status"><span data-tool-status>تحديد</span><span>•</span><span dir="ltr" data-coordinates>X 0 · Y 0 mm</span><span class="ald-prof-snap" data-snap></span></footer>
            </section>`;
        const workspace = container.querySelector(".ald-prof-workspace");
        const stage = workspace.querySelector("[data-stage]");
        const canvas = workspace.querySelector(".ald-prof-canvas");
        const numeric = workspace.querySelector("[data-numeric]");
        const layers = workspace.querySelector("[data-layers]");
        const properties = workspace.querySelector("[data-properties]");
        const hint = workspace.querySelector("[data-hint]");
        const saveState = workspace.querySelector("[data-save-state]");

        return Object.freeze({
            workspace, stage, canvas, numeric, layers, properties, hint,
            setActiveTool(tool) { workspace.dataset.activeTool = tool; workspace.querySelectorAll("[data-tool]").forEach(button => button.classList.toggle("is-active", button.dataset.tool === tool)); },
            setSaveState(text, state = "saved") { saveState.textContent = text; saveState.dataset.state = state; },
            setSaving(saving) { const button = workspace.querySelector('[data-action="save"]'); button.disabled = Boolean(saving); button.textContent = saving ? "يتم الحفظ…" : "حفظ"; },
            setHint(text = "") { hint.textContent = text; hint.classList.toggle("is-visible", Boolean(text)); },
            setStatus(tool, coordinates, snap = "") { workspace.querySelector("[data-tool-status]").textContent = tool; workspace.querySelector("[data-coordinates]").textContent = coordinates; workspace.querySelector("[data-snap]").textContent = snap; },
            setZoom(value) { workspace.querySelector("[data-zoom]").textContent = value; },
            renderLayers(items, selectedId) {
                layers.innerHTML = items.length ? items.map((item, index) => `<button type="button" class="ald-prof-layer ${item.id === selectedId ? "is-selected" : ""}" data-path-id="${escapeHtml(item.id)}"><span class="ald-prof-layer-icon">◇</span><span><strong>${escapeHtml(item.label || `محيط ${index + 1}`)}</strong><small>${item.closed ? "مغلق" : "مفتوح"}</small></span></button>`).join("") : '<div class="ald-prof-empty">ابدأ بالقلم P لرسم محيط الدرفة.</div>';
            },
            renderProperties(model) {
                if (!model || model.kind === "empty") { properties.innerHTML = '<div class="ald-prof-empty">حدد عنصرًا لعرض خصائصه.</div>'; return; }
                properties.innerHTML = `<section class="ald-prof-prop-section"><h3>${escapeHtml(model.title)}</h3><div class="ald-prof-prop-grid">${(model.values || []).map(item => `<label><span>${escapeHtml(item.label)}</span><strong dir="ltr">${escapeHtml(item.value)}</strong></label>`).join("")}</div></section>${model.help ? `<p class="ald-prof-prop-help">${escapeHtml(model.help)}</p>` : ""}`;
            },
            showNumeric(point, value = "") { numeric.hidden = false; numeric.value = value; const x = Math.max(12, Math.min(stage.clientWidth - 132, Number(point.x) + 14)); const y = Math.max(12, Math.min(stage.clientHeight - 56, Number(point.y) + 14)); numeric.style.left = `${x}px`; numeric.style.top = `${y}px`; numeric.focus({ preventScroll: true }); numeric.select(); },
            hideNumeric() { numeric.hidden = true; numeric.value = ""; },
            destroy() { container.innerHTML = ""; },
        });
    }
    root.WorkspaceShell = Object.freeze({ mount });
})();
