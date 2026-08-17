(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);

    function toolButton(tool, shortcut, label, icon) {
        return `<button type="button" class="ald-v4-tool" data-tool="${tool}" aria-label="${label}" title="${label} (${shortcut})"><span class="ald-v4-tool-icon" aria-hidden="true">${icon}</span><span class="ald-v4-tool-key">${shortcut}</span></button>`;
    }

    function formatNumber(value) {
        return Number.isFinite(Number(value)) ? String(Number(value)) : "—";
    }

    function metric(label, value, unit = "") {
        const wrapper = document.createElement("div");
        wrapper.className = "ald-v4-property-field";
        const key = document.createElement("span");
        key.className = "ald-v4-property-key";
        key.textContent = label;
        const field = document.createElement("span");
        field.className = "ald-v4-property-value";
        field.textContent = `${formatNumber(value)}${value !== null && value !== undefined && unit ? ` ${unit}` : ""}`;
        wrapper.append(key, field);
        return wrapper;
    }

    function layerRow(layer) {
        const row = document.createElement("div");
        row.className = `ald-v4-layer-row${layer.selected ? " is-selected" : ""}`;
        row.dataset.layerKind = layer.kind;
        row.dataset.layerId = layer.id;

        const icon = document.createElement("span");
        icon.className = "ald-v4-layer-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = layer.kind === "dimension" ? "↔" : (layer.closed ? "▱" : "⌁");

        const name = document.createElement("span");
        name.className = "ald-v4-layer-name";
        name.textContent = layer.label;

        const meta = document.createElement("span");
        meta.className = "ald-v4-layer-meta";
        if (layer.kind === "dimension") meta.textContent = layer.valueMm === null ? "" : `${formatNumber(layer.valueMm)} mm`;
        else meta.textContent = layer.closed ? "مغلق" : "مفتوح";

        row.append(icon, name, meta);
        return row;
    }

    function mount(container) {
        if (!container) throw new Error("Drawing V4 editor container is required");
        container.innerHTML = `
            <section class="ald-v4-editor" dir="rtl" aria-label="محرر رسم الدرفة">
                <div class="ald-v4-layout" dir="ltr">
                    <aside class="ald-v4-panel ald-v4-layers-panel" dir="rtl" aria-label="الطبقات">
                        <div class="ald-v4-panel-header">
                            <strong>الطبقات</strong>
                            <span class="ald-v4-panel-count" data-layer-count>0</span>
                        </div>
                        <div class="ald-v4-panel-body ald-v4-layers-list" data-layers-list></div>
                    </aside>

                    <main class="ald-v4-canvas-region" dir="rtl">
                        <div class="ald-v4-canvas-wrap">
                            <canvas class="ald-v4-canvas" tabindex="0" aria-label="مساحة الرسم"></canvas>
                            <input class="ald-v4-length-input" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" aria-label="القيمة بالميليمتر" placeholder="القيمة mm" hidden>
                            <div class="ald-v4-hint" aria-live="polite"></div>
                            <div class="ald-v4-zoom-controls" dir="ltr" aria-label="التكبير والتصغير">
                                <button type="button" data-view-action="zoom-out" aria-label="تصغير">−</button>
                                <button type="button" class="ald-v4-zoom-value" data-view-action="fit" aria-label="ملاءمة الرسم للشاشة">100%</button>
                                <button type="button" data-view-action="zoom-in" aria-label="تكبير">+</button>
                            </div>
                            <div class="ald-v4-toolbar" role="toolbar" aria-label="أدوات الرسم">
                                ${toolButton("select", "V", "تحديد", "↖")}
                                ${toolButton("node", "A", "تعديل النقاط", "◇")}
                                <span class="ald-v4-toolbar-separator" aria-hidden="true"></span>
                                ${toolButton("pen", "P", "القلم الذكي", "⌁")}
                                ${toolButton("dimension", "D", "إضافة بُعد", "↔")}
                                ${toolButton("hand", "Space", "تحريك اللوحة", "✋")}
                            </div>
                            <div class="ald-v4-status" aria-live="polite">
                                <span class="ald-v4-status-tool">تحديد</span>
                                <span class="ald-v4-status-separator">•</span>
                                <span class="ald-v4-status-coordinates">X 0 · Y 0 mm</span>
                                <span class="ald-v4-status-snap"></span>
                            </div>
                        </div>
                    </main>

                    <aside class="ald-v4-panel ald-v4-properties-panel" dir="rtl" aria-label="الخصائص">
                        <div class="ald-v4-properties-tabs" role="tablist" aria-label="لوحة الخصائص">
                            <button type="button" class="is-active" role="tab" aria-selected="true">تصميم</button>
                        </div>
                        <div class="ald-v4-panel-body ald-v4-properties-body">
                            <section class="ald-v4-property-section">
                                <div class="ald-v4-property-heading" data-property-title>الرسم</div>
                                <div class="ald-v4-property-grid" data-position-properties></div>
                            </section>
                            <section class="ald-v4-property-section">
                                <div class="ald-v4-property-heading">الأبعاد</div>
                                <div class="ald-v4-property-grid" data-size-properties></div>
                            </section>
                            <section class="ald-v4-property-section">
                                <div class="ald-v4-property-heading">معلومات</div>
                                <div class="ald-v4-property-summary" data-property-summary>لا يوجد تحديد</div>
                            </section>
                        </div>
                    </aside>
                </div>
            </section>`;

        const editor = container.querySelector(".ald-v4-editor");
        const canvasWrap = editor.querySelector(".ald-v4-canvas-wrap");
        const canvas = editor.querySelector(".ald-v4-canvas");
        const lengthInput = editor.querySelector(".ald-v4-length-input");
        const hint = editor.querySelector(".ald-v4-hint");
        const statusTool = editor.querySelector(".ald-v4-status-tool");
        const statusCoordinates = editor.querySelector(".ald-v4-status-coordinates");
        const statusSnap = editor.querySelector(".ald-v4-status-snap");
        const zoomValue = editor.querySelector(".ald-v4-zoom-value");
        const layersList = editor.querySelector("[data-layers-list]");
        const layerCount = editor.querySelector("[data-layer-count]");
        const propertyTitle = editor.querySelector("[data-property-title]");
        const positionProperties = editor.querySelector("[data-position-properties]");
        const sizeProperties = editor.querySelector("[data-size-properties]");
        const propertySummary = editor.querySelector("[data-property-summary]");

        function setActiveTool(tool) {
            editor.querySelectorAll("[data-tool]").forEach(button => {
                const active = button.dataset.tool === tool;
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-pressed", active ? "true" : "false");
            });
        }

        function setReadOnly(readOnly) {
            const locked = Boolean(readOnly);
            editor.classList.toggle("is-readonly", locked);
            editor.querySelectorAll("[data-tool]").forEach(button => {
                const allowed = button.dataset.tool === "hand";
                button.disabled = locked && !allowed;
            });
            lengthInput.disabled = locked;
        }

        function setHint(text = "") {
            hint.textContent = text;
            hint.classList.toggle("is-visible", Boolean(text));
        }

        function showLengthInput(screenPoint, initialValue = "") {
            if (lengthInput.disabled) return;
            lengthInput.hidden = false;
            const width = 116;
            const x = Math.max(12, Math.min(canvas.clientWidth - width - 12, Number(screenPoint.x) + 14));
            const y = Math.max(12, Math.min(canvas.clientHeight - 44, Number(screenPoint.y) + 14));
            lengthInput.style.left = `${x}px`;
            lengthInput.style.top = `${y}px`;
            lengthInput.value = initialValue;
            lengthInput.focus({ preventScroll: true });
            lengthInput.setSelectionRange(lengthInput.value.length, lengthInput.value.length);
        }

        function hideLengthInput() {
            lengthInput.hidden = true;
            lengthInput.value = "";
        }

        function renderLayers(viewModel) {
            layersList.innerHTML = "";
            const layers = [
                ...(viewModel && viewModel.layers && viewModel.layers.paths || []),
                ...(viewModel && viewModel.layers && viewModel.layers.dimensions || []),
            ];
            layerCount.textContent = String(layers.length);
            if (!layers.length) {
                const empty = document.createElement("div");
                empty.className = "ald-v4-panel-empty";
                empty.textContent = "ابدأ بالقلم لرسم محيط الدرفة";
                layersList.appendChild(empty);
                return;
            }
            layers.forEach(layer => layersList.appendChild(layerRow(layer)));
        }

        function renderProperties(viewModel) {
            const properties = viewModel && viewModel.properties || {};
            propertyTitle.textContent = properties.title || "الرسم";
            positionProperties.innerHTML = "";
            positionProperties.append(
                metric("X", properties.xMm, "mm"),
                metric("Y", properties.yMm, "mm")
            );
            sizeProperties.innerHTML = "";
            if (properties.kind === "dimension") {
                sizeProperties.append(
                    metric("القيمة", properties.valueMm, "mm"),
                    metric("الزاوية", properties.rotationDeg, "°")
                );
                propertySummary.textContent = properties.driving ? "بُعد ثابت يقود الهندسة" : "بُعد مرجعي";
                return;
            }
            sizeProperties.append(
                metric("W", properties.widthMm, "mm"),
                metric("H", properties.heightMm, "mm"),
                metric("الدوران", properties.rotationDeg, "°")
            );
            if (properties.kind === "path") {
                propertySummary.textContent = `${properties.closed ? "مسار مغلق" : "مسار مفتوح"} · ${properties.segmentCount || 0} ضلع`;
            } else if (properties.kind === "node") {
                propertySummary.textContent = "نقطة هندسية محددة";
            } else {
                const summary = viewModel && viewModel.summary || {};
                propertySummary.textContent = `${summary.paths || 0} مسار · ${summary.dimensions || 0} بُعد · ${summary.nodes || 0} نقطة`;
            }
        }

        function renderViewModel(viewModel) {
            if (!viewModel) return;
            renderLayers(viewModel);
            renderProperties(viewModel);
            if (viewModel.activeTool) setActiveTool(viewModel.activeTool);
        }

        return Object.freeze({
            editor,
            canvasWrap,
            canvas,
            lengthInput,
            hint,
            statusTool,
            statusCoordinates,
            statusSnap,
            zoomValue,
            layersList,
            propertyTitle,
            setActiveTool,
            setReadOnly,
            setHint,
            showLengthInput,
            hideLengthInput,
            renderViewModel,
            destroy() {
                container.innerHTML = "";
            },
        });
    }

    root.EditorShell = Object.freeze({ mount });
})();
