(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const engine = window.AlmdinaSketchEngine;
    const lineModel = window.AlmdinaExactLineModel;
    const arcModel = window.AlmdinaExactArcModel;
    const segmentModel = window.AlmdinaExactSegmentDimensionModel;
    const interaction = window.AlmdinaFigmaInteractionModel;
    if (!baseEditor || !history || !engine || !lineModel || !arcModel || !segmentModel || !interaction) {
        console.error("Figma-like editor dependencies must load before professional drawing UX");
        return;
    }
    if (baseEditor.__figmaEditorIntegrated) return;

    const STYLE_ID = "dco-figma-editor-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 24;
    let clipboard = null;

    function esc(value) {
        if (window.frappe && frappe.utils && frappe.utils.escape_html) {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-special-shape-modal .modal-dialog{max-width:100vw!important;width:100vw!important;height:100vh!important;margin:0!important}
            .dco-special-shape-modal .modal-content{height:100vh!important;border-radius:0!important}
            .dco-special-shape-modal .modal-header{min-height:54px;padding:10px 18px!important}
            .dco-special-shape-modal .modal-body{overflow:hidden!important}
            .dco-special-sketch-shell.dco-figma-editor{position:relative;display:grid!important;grid-template-columns:minmax(0,1fr) 286px!important;direction:ltr!important;min-height:calc(100vh - 116px)!important;height:calc(100vh - 116px);background:#e5e7e9}
            .dco-figma-editor>.dco-sketch-toolbar,.dco-figma-editor>.dco-sketch-sidebar{display:none!important}
            .dco-figma-editor>.dco-sketch-center{grid-column:1;direction:rtl;min-width:0;height:100%;padding:10px 12px 12px!important;gap:8px!important;overflow:hidden}
            .dco-figma-editor .dco-sketch-topbar{min-height:48px;padding:7px 10px!important;border-radius:9px!important;box-shadow:none!important}
            .dco-figma-editor .dco-sketch-paper-wrap{min-height:0!important;height:100%;padding:18px 18px 72px!important;border:0!important;border-radius:0!important;background:#dedede!important;overflow:hidden}
            .dco-figma-editor .dco-sketch-paper{max-height:calc(100vh - 220px)!important;border-radius:2px!important;box-shadow:0 1px 4px rgba(0,0,0,.14)!important}
            .dco-figma-editor .dco-sketch-key-hint{display:none!important}
            .dco-figma-editor .dco-sketch-zoom{left:18px!important;bottom:18px!important;border-radius:8px!important;box-shadow:0 2px 8px rgba(0,0,0,.13)!important}

            .dco-figma-properties{grid-column:2;direction:rtl;min-width:0;height:100%;overflow:auto;background:#fff;border-left:1px solid #d7d7d7;color:#1f2933}
            .dco-figma-properties-head{position:sticky;top:0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:48px;padding:0 13px;background:#fff;border-bottom:1px solid #e5e7eb}
            .dco-figma-properties-head strong{font-size:12px}.dco-figma-properties-head span{font-size:8px;color:#7b8794}
            .dco-figma-tool-options{padding:0 10px}.dco-figma-selection-properties{padding:10px}
            .dco-figma-empty{padding:22px 12px;text-align:center;color:#7a8792;font-size:10px;line-height:1.7}.dco-figma-empty b{display:block;margin-bottom:4px;color:#394b59;font-size:11px}
            .dco-figma-section{padding:10px 0;border-bottom:1px solid #edf0f2}.dco-figma-section:last-child{border-bottom:0}.dco-figma-section-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;font-size:9px;font-weight:900;color:#253746}.dco-figma-section-title small{color:#8a97a3;font-size:7px;font-weight:600}
            .dco-figma-field-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.dco-figma-field label{display:block;margin:0 0 3px;color:#73808c;font-size:7px;font-weight:800}
            .dco-figma-input{display:flex;align-items:center;height:34px;border:1px solid #d9dee3;border-radius:6px;background:#fff;overflow:hidden}.dco-figma-input:focus-within{border-color:#0d99ff;box-shadow:0 0 0 1px #0d99ff}.dco-figma-input input{min-width:0;width:100%;height:100%;padding:0 7px;border:0!important;outline:0!important;box-shadow:none!important;background:transparent;text-align:center;font-size:10px;font-weight:800;font-variant-numeric:tabular-nums}.dco-figma-input span{padding:0 6px;color:#7b8794;font-size:7px;border-right:1px solid #edf0f2}
            .dco-figma-primary{width:100%;min-height:34px;margin-top:7px;border:1px solid #0d99ff;border-radius:6px;background:#0d99ff;color:#fff;cursor:pointer;font-size:8.5px;font-weight:900}.dco-figma-primary:hover{background:#0788e5}
            .dco-figma-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}.dco-figma-action{min-height:32px;border:1px solid #dce1e5;border-radius:6px;background:#fff;color:#344454;cursor:pointer;font-size:7.8px;font-weight:900}.dco-figma-action:hover{border-color:#0d99ff;color:#0878c9;background:#f4faff}.dco-figma-action.is-danger:hover{border-color:#e04b43;color:#b42318;background:#fff6f5}
            .dco-figma-metric{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 7px;border-radius:6px;background:#f7f8f9;color:#64717d;font-size:8px}.dco-figma-metric b{color:#263d4d;font-variant-numeric:tabular-nums}
            .dco-figma-tip{margin-top:7px;padding:7px 8px;border-radius:7px;background:#f5f8fa;color:#60717f;font-size:7.5px;line-height:1.55}

            .dco-figma-dock{position:absolute;z-index:35;left:50%;bottom:17px;transform:translateX(-50%);direction:rtl;display:flex;align-items:center;gap:3px;padding:5px;border:1px solid rgba(0,0,0,.13);border-radius:10px;background:#2c2c2c;box-shadow:0 7px 24px rgba(0,0,0,.25)}
            .dco-figma-dock button{display:grid;place-items:center;min-width:36px;height:36px;padding:0 8px;border:0;border-radius:7px;background:transparent;color:#f3f4f5;cursor:pointer;font-size:9px;font-weight:900}.dco-figma-dock button:hover{background:#454545}.dco-figma-dock button.is-active{background:#0d99ff;color:#fff}.dco-figma-dock button b{font-size:14px;line-height:1}.dco-figma-dock-separator{width:1px;height:24px;margin:0 2px;background:#555}
            .dco-figma-dock .dco-figma-wide{padding:0 10px;display:flex;gap:5px}.dco-figma-shortcut{font-size:6px!important;color:#aeb6bd;font-weight:700!important}.dco-figma-dock button.is-active .dco-figma-shortcut{color:#e9f7ff}

            .dco-figma-endpoints{pointer-events:none}.dco-figma-endpoint-hit{fill:transparent;stroke:transparent;stroke-width:18;pointer-events:stroke;cursor:crosshair}.dco-figma-endpoint{fill:#fff;stroke:#0d99ff;stroke-width:2.5;vector-effect:non-scaling-stroke;pointer-events:none}.dco-figma-endpoint.is-active{fill:#0d99ff;stroke:#fff;stroke-width:3}.dco-figma-selected-path{fill:none;stroke:#0d99ff;stroke-width:2.5;stroke-dasharray:6 4;vector-effect:non-scaling-stroke;pointer-events:none}.dco-figma-endpoint-label{fill:#0d78c6;font-family:Tahoma,Arial,sans-serif;font-size:9px;font-weight:900;text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:4;stroke-linejoin:round;pointer-events:none}
            .dco-figma-editor .dco-exact-line-inspector,.dco-figma-editor .dco-exact-arc-card,.dco-figma-editor .dco-exact-segment-dimensions-panel{display:none!important}
            .dco-figma-editor .dco-exact-line-hud.dco-drawing-workspace-side-panel{position:static!important;width:100%!important;margin:8px 0!important;border-radius:8px!important;box-shadow:none!important}
            .dco-figma-editor .dco-smart-template-palette.dco-drawing-workspace-gallery{left:50%!important;right:auto!important;top:86px!important;transform:translateX(-50%)!important;width:min(760px,calc(100vw - 340px))!important;max-width:760px!important}
            .dco-figma-editor .dco-drawing-workspace-gallery .dco-smart-template-list{grid-template-columns:repeat(3,minmax(0,1fr))!important}

            @media(max-width:900px){.dco-special-sketch-shell.dco-figma-editor{grid-template-columns:minmax(0,1fr)!important}.dco-figma-properties{position:absolute;z-index:45;top:0;right:0;width:min(310px,86vw);transform:translateX(102%);transition:.18s ease;box-shadow:-10px 0 30px rgba(0,0,0,.14)}.dco-figma-properties.is-mobile-open{transform:translateX(0)}.dco-figma-dock{max-width:calc(100vw - 24px);overflow:auto}.dco-figma-editor .dco-smart-template-palette.dco-drawing-workspace-gallery{width:calc(100vw - 30px)!important}.dco-figma-editor .dco-drawing-workspace-gallery .dco-smart-template-list{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        return Array.from(document.querySelectorAll(".dco-special-shape-modal")).reverse().find(modal =>
            !modal.classList.contains("dco-special-shape-readonly")
            && (modal.classList.contains("show") || modal.style.display === "block")
        ) || null;
    }

    function liveState(controller) {
        const state = history.getActiveState ? history.getActiveState() : null;
        return state && state.root === controller.root && state.svg === controller.svg ? state : null;
    }

    function selectedElement(controller) {
        const state = liveState(controller);
        return state ? interaction.selected(state.elements, state.selectedId) : null;
    }

    function refreshEditor(controller) {
        const state = liveState(controller);
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        if (history.activateState && state) history.activateState(state);
    }

    function transformFor(controller) {
        const dims = lineModel.pieceDimensions(controller.row);
        return lineModel.createTransform(dims.width, dims.length);
    }

    function format(value, precision = 2) {
        return String(lineModel.rounded(value, precision));
    }

    function commitElements(controller, original, nextElements, selectedId) {
        const state = liveState(controller);
        if (!state) return false;
        const transition = history.snapshot(state, original);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        state.elements = clone(nextElements);
        state.selectedId = String(selectedId || "");
        state.hasChanges = true;
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        controller.lastSelectedId = "";
        window.setTimeout(() => renderAll(controller), 0);
        return true;
    }

    function applyEditedSegment(controller, nextElement) {
        const state = liveState(controller);
        const current = selectedElement(controller);
        const transform = transformFor(controller);
        if (!state || !current || !transform || !nextElement) return false;
        const original = clone(state.elements);
        const result = segmentModel.applyEdit(state.elements, current.id, nextElement, transform, { preserveConnections: true });
        if (!result.valid) {
            if (window.frappe) frappe.show_alert({ message: "التعديل غير صالح أو يخرج العنصر خارج حدود الدرفة", indicator: "orange" }, 4);
            return false;
        }
        return commitElements(controller, original, result.elements, current.id);
    }

    function lineProperties(controller, element) {
        const meta = lineModel.exactMeta(element);
        return `<div class="dco-figma-section">
            <div class="dco-figma-section-title"><span>المستقيم</span><small>قياس حقيقي CM</small></div>
            <div class="dco-figma-field-grid">
                <div class="dco-figma-field"><label>الطول</label><div class="dco-figma-input"><input type="number" min="0.1" step="0.1" value="${esc(format(meta.length_cm, 3))}" data-figma-line-length><span>سم</span></div></div>
                <div class="dco-figma-field"><label>الزاوية</label><div class="dco-figma-input"><input type="number" step="1" value="${esc(format(meta.angle_deg, 2))}" data-figma-line-angle><span>°</span></div></div>
            </div>
            <button type="button" class="dco-figma-primary" data-figma-apply-line>تطبيق القياس</button>
            <div class="dco-figma-tip">يمكنك أيضًا سحب نقطة البداية أو النهاية مباشرة على الرسم. Shift أثناء السحب يحافظ على اتجاه أفقي/عمودي.</div>
        </div>
        <div class="dco-figma-section"><div class="dco-figma-section-title"><span>النقاط</span><small>X / Y سم</small></div>
            <div class="dco-figma-field-grid">
                <div class="dco-figma-metric"><span>البداية</span><b>${format(meta.start_cm[0])}, ${format(meta.start_cm[1])}</b></div>
                <div class="dco-figma-metric"><span>النهاية</span><b>${format(meta.end_cm[0])}, ${format(meta.end_cm[1])}</b></div>
            </div>
        </div>`;
    }

    function arcProperties(controller, element) {
        const meta = arcModel.arcMeta(element);
        return `<div class="dco-figma-section">
            <div class="dco-figma-section-title"><span>قوس دائري</span><small>Exact Arc</small></div>
            <div class="dco-figma-field-grid">
                <div class="dco-figma-field"><label>طول الوتر</label><div class="dco-figma-input"><input type="number" min="0.1" step="0.1" value="${esc(format(meta.chord_cm, 3))}" data-figma-arc-chord><span>سم</span></div></div>
                <div class="dco-figma-field"><label>ارتفاع القوس</label><div class="dco-figma-input"><input type="number" min="0.2" step="0.1" value="${esc(format(meta.rise_cm, 3))}" data-figma-arc-rise><span>سم</span></div></div>
            </div>
            <button type="button" class="dco-figma-primary" data-figma-apply-arc>تطبيق القياس</button>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:7px"><div class="dco-figma-metric"><span>R</span><b>${format(meta.radius_cm)} سم</b></div><div class="dco-figma-metric"><span>طول القوس</span><b>${format(meta.length_cm)} سم</b></div></div>
            <div class="dco-figma-tip">اسحب نقطة البداية أو النهاية لتغيير الوتر مع بقاء القوس دائريًا حقيقيًا، أو أدخل الأرقام هنا.</div>
        </div>`;
    }

    function genericProperties(element) {
        const kind = interaction.elementKind(element);
        const names = { template: "قالب ذكي", pen: "قلم", line: "خط توضيحي", rectangle: "مستطيل", ellipse: "دائرة / بيضاوي", dimension: "قياس", note: "ملاحظة" };
        const bounds = engine.elementBounds(element) || {};
        const points = Array.isArray(element.points) ? engine.sanitizePoints(element.points).length : 0;
        return `<div class="dco-figma-section"><div class="dco-figma-section-title"><span>${esc(names[kind] || "عنصر")}</span><small>${esc(kind)}</small></div>
            ${points ? `<div class="dco-figma-metric"><span>عدد نقاط التحكم</span><b>${points}</b></div>` : ""}
            ${Number.isFinite(bounds.width) ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:6px"><div class="dco-figma-metric"><span>العرض البصري</span><b>${format(bounds.width, 1)}</b></div><div class="dco-figma-metric"><span>الارتفاع البصري</span><b>${format(bounds.height, 1)}</b></div></div>` : ""}
            <div class="dco-figma-tip">هذا عنصر توثيقي بصري. للعناصر الإنتاجية استخدم «ضلع بمقاس» أو القوس الدقيق حتى تكون القيم بالسنتيمتر الحقيقي.</div></div>`;
    }

    function actionSection() {
        return `<div class="dco-figma-section"><div class="dco-figma-section-title"><span>الإجراءات</span><small>Ctrl/Cmd</small></div><div class="dco-figma-actions"><button type="button" class="dco-figma-action" data-figma-copy>نسخ</button><button type="button" class="dco-figma-action" data-figma-duplicate>تكرار</button><button type="button" class="dco-figma-action is-danger" data-figma-delete>حذف</button></div><div class="dco-figma-tip">Ctrl+C نسخ · Ctrl+V لصق · Ctrl+D تكرار · Delete حذف · Ctrl+Z تراجع.</div></div>`;
    }

    function renderProperties(controller) {
        const element = selectedElement(controller);
        const state = liveState(controller);
        if (!element || !state || state.tool !== "select") {
            controller.properties.innerHTML = `<div class="dco-figma-empty"><b>خصائص العنصر</b>حدد أي عنصر من الرسم. عند تحديد مستقيم ستظهر هنا قيمة الطول والزاوية، ويمكنك تغييرهما مباشرة.</div>`;
            controller.propertiesPanel.classList.remove("is-mobile-open");
            return;
        }
        const line = lineModel.exactMeta(element);
        const arc = arcModel.arcMeta(element);
        controller.properties.innerHTML = `${line ? lineProperties(controller, element) : arc ? arcProperties(controller, element) : genericProperties(element)}${actionSection()}`;
        controller.propertiesPanel.classList.add("is-mobile-open");
    }

    function toolTarget(root, key) {
        if (key === "exact-line") return root.querySelector(".dco-exact-line-tool");
        if (key === "templates") return root.querySelector(".dco-drawing-workspace-template-launcher");
        if (key === "undo") return root.querySelector(".dco-sketch-undo");
        if (key === "redo") return root.querySelector(".dco-sketch-redo");
        return root.querySelector(`.dco-sketch-tool[data-tool="${key}"]`);
    }

    function dockHtml() {
        return `<nav class="dco-figma-dock" aria-label="أدوات الرسم السريعة">
            <button type="button" data-figma-tool="select" title="تحديد V"><b>↖</b><span class="dco-figma-shortcut">V</span></button>
            <button type="button" class="dco-figma-wide" data-figma-tool="exact-line" title="ضلع بمقاس L"><b>╱</b><span>ضلع</span><span class="dco-figma-shortcut">L</span></button>
            <button type="button" data-figma-tool="pen" title="قلم P"><b>✎</b><span class="dco-figma-shortcut">P</span></button>
            <button type="button" data-figma-tool="rectangle" title="مستطيل R"><b>□</b><span class="dco-figma-shortcut">R</span></button>
            <button type="button" data-figma-tool="ellipse" title="دائرة O"><b>○</b><span class="dco-figma-shortcut">O</span></button>
            <span class="dco-figma-dock-separator"></span>
            <button type="button" data-figma-tool="dimension" title="قياس D"><b>↔</b><span class="dco-figma-shortcut">D</span></button>
            <button type="button" data-figma-tool="note" title="ملاحظة N"><b>T</b><span class="dco-figma-shortcut">N</span></button>
            <button type="button" class="dco-figma-wide" data-figma-tool="templates" title="قوالب"><b>▰</b><span>قوالب</span></button>
            <span class="dco-figma-dock-separator"></span>
            <button type="button" data-figma-tool="undo" title="تراجع Ctrl+Z"><b>↶</b></button><button type="button" data-figma-tool="redo" title="إعادة"><b>↷</b></button>
        </nav>`;
    }

    function updateDock(controller) {
        const state = liveState(controller);
        const exactActive = controller.root.querySelector(".dco-exact-line-tool.is-active");
        controller.dock.querySelectorAll("[data-figma-tool]").forEach(button => {
            const key = button.dataset.figmaTool;
            const active = key === "exact-line" ? Boolean(exactActive) : state && state.tool === key;
            button.classList.toggle("is-active", Boolean(active));
        });
    }

    function renderEndpointOverlay(controller) {
        if (controller.rendering) return;
        controller.rendering = true;
        if (controller.observer) controller.observer.disconnect();
        try {
            const old = controller.svg.querySelector(".dco-figma-endpoints");
            if (old) old.remove();
            const element = selectedElement(controller);
            const state = liveState(controller);
            const transform = transformFor(controller);
            const endpoints = element && segmentModel.endpoints(element);
            if (!state || state.tool !== "select" || !element || !endpoints || !transform) return;

            let startCm = endpoints.start.slice();
            let endCm = endpoints.end.slice();
            if (controller.drag && String(controller.drag.elementId) === String(element.id) && controller.drag.previewCm) {
                if (controller.drag.role === "start") startCm = controller.drag.previewCm.slice();
                else endCm = controller.drag.previewCm.slice();
            }
            const start = lineModel.cmToCanvas(transform, startCm);
            const end = lineModel.cmToCanvas(transform, endCm);
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-figma-endpoints");

            const arc = arcModel.arcMeta(element);
            if (arc && !controller.drag) {
                const path = document.createElementNS(SVG_NS, "path");
                path.setAttribute("class", "dco-figma-selected-path");
                path.setAttribute("d", arcModel.svgArcPath(element, transform));
                group.appendChild(path);
            } else {
                const path = document.createElementNS(SVG_NS, "line");
                path.setAttribute("class", "dco-figma-selected-path");
                path.setAttribute("x1", String(start[0])); path.setAttribute("y1", String(start[1])); path.setAttribute("x2", String(end[0])); path.setAttribute("y2", String(end[1]));
                group.appendChild(path);
            }

            [["start", start], ["end", end]].forEach(([role, point]) => {
                const hit = document.createElementNS(SVG_NS, "circle");
                hit.setAttribute("class", "dco-figma-endpoint-hit"); hit.setAttribute("data-figma-endpoint", role); hit.setAttribute("cx", String(point[0])); hit.setAttribute("cy", String(point[1])); hit.setAttribute("r", "8");
                group.appendChild(hit);
                const dot = document.createElementNS(SVG_NS, "circle");
                dot.setAttribute("class", `dco-figma-endpoint${controller.drag && controller.drag.role === role ? " is-active" : ""}`); dot.setAttribute("cx", String(point[0])); dot.setAttribute("cy", String(point[1])); dot.setAttribute("r", "6");
                group.appendChild(dot);
            });
            const metrics = segmentModel.metrics(element);
            if (metrics) {
                const label = document.createElementNS(SVG_NS, "text");
                label.setAttribute("class", "dco-figma-endpoint-label"); label.setAttribute("x", String((start[0] + end[0]) / 2)); label.setAttribute("y", String((start[1] + end[1]) / 2 - 12));
                label.textContent = metrics.kind === "line" ? `${format(metrics.lengthCm)} سم` : `قوس ${format(metrics.arcLengthCm)} سم`;
                group.appendChild(label);
            }
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
            if (controller.observer) controller.observer.observe(controller.svg, { childList: true });
        }
    }

    function renderAll(controller) {
        renderProperties(controller);
        renderEndpointOverlay(controller);
        updateDock(controller);
    }

    function canvasPoint(controller, event) {
        const point = baseEditor.clientPointToCanvas(controller.svg, event.clientX, event.clientY);
        return [Number(point.x), Number(point.y)];
    }

    function dragPointCm(controller, event, role) {
        const transform = transformFor(controller);
        if (!transform) return null;
        let point = lineModel.canvasToCm(transform, canvasPoint(controller, event));
        point = lineModel.clampPointToPiece(transform, point);
        const element = selectedElement(controller);
        const endpoints = element && segmentModel.endpoints(element);
        if (event.shiftKey && endpoints) {
            const fixed = role === "start" ? endpoints.end : endpoints.start;
            const dx = Math.abs(point[0] - fixed[0]);
            const dy = Math.abs(point[1] - fixed[1]);
            if (dx >= dy) point[1] = fixed[1]; else point[0] = fixed[0];
        }
        const state = liveState(controller);
        const otherElements = state ? state.elements.filter(item => String(item.id) !== String(element && element.id)) : [];
        const snapped = lineModel.nearestEndpoint(point, otherElements, 1.2);
        return snapped ? snapped.point.slice() : point;
    }

    function bindEndpointDragging(controller) {
        controller.svg.addEventListener("pointerdown", event => {
            const handle = event.target.closest && event.target.closest("[data-figma-endpoint]");
            if (!handle) return;
            const state = liveState(controller);
            const element = selectedElement(controller);
            if (!state || !element || state.tool !== "select" || !segmentModel.endpoints(element)) return;
            controller.drag = { pointerId: event.pointerId, elementId: element.id, role: handle.dataset.figmaEndpoint, original: clone(state.elements), previewCm: null };
            try { controller.svg.setPointerCapture(event.pointerId); } catch (error) { /* optional */ }
            event.preventDefault(); event.stopImmediatePropagation(); renderEndpointOverlay(controller);
        }, true);

        controller.svg.addEventListener("pointermove", event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            drag.previewCm = dragPointCm(controller, event, drag.role);
            renderEndpointOverlay(controller);
            event.preventDefault(); event.stopImmediatePropagation();
        }, true);

        const finish = event => {
            const drag = controller.drag;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const state = liveState(controller);
            const transform = transformFor(controller);
            if (event.type !== "pointercancel" && state && transform && drag.previewCm) {
                const result = interaction.applyEndpointDrag(state.elements, drag.elementId, drag.role, drag.previewCm, transform, { preserveConnections: true });
                if (result.valid) commitElements(controller, drag.original, result.elements, drag.elementId);
                else if (window.frappe) frappe.show_alert({ message: "لا يمكن وضع النقطة هنا؛ تحقق من حدود الدرفة واتصال العناصر", indicator: "orange" }, 4);
            }
            controller.drag = null;
            try { controller.svg.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }
            renderAll(controller);
            event.preventDefault(); event.stopImmediatePropagation();
        };
        controller.svg.addEventListener("pointerup", finish, true);
        controller.svg.addEventListener("pointercancel", finish, true);
    }

    function copySelected(controller) {
        const element = selectedElement(controller);
        if (!element) return false;
        clipboard = clone(element);
        if (window.frappe) frappe.show_alert({ message: "تم نسخ العنصر", indicator: "blue" }, 2);
        return true;
    }

    function paste(controller, source = clipboard) {
        const state = liveState(controller);
        const transform = transformFor(controller);
        if (!state || !source || !transform) return false;
        const result = interaction.duplicateElement(source, transform);
        if (!result.valid || !result.element) {
            if (window.frappe) frappe.show_alert({ message: "لا توجد مساحة كافية للصق العنصر داخل الدرفة", indicator: "orange" }, 3);
            return false;
        }
        const transition = history.addElement(state, result.element);
        if (!transition || !transition.changed) return false;
        Object.assign(state, transition.patch);
        state.selectedId = result.element.id;
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        window.setTimeout(() => renderAll(controller), 0);
        return true;
    }

    function deleteSelected(controller) {
        const state = liveState(controller);
        if (!state || !state.selectedId) return false;
        const transition = history.deleteSelected(state);
        if (!transition || !transition.changed) return false;
        Object.assign(state, transition.patch);
        if (history.activateState) history.activateState(state);
        refreshEditor(controller); renderAll(controller); return true;
    }

    function bindProperties(controller) {
        controller.properties.addEventListener("click", event => {
            const element = selectedElement(controller);
            const transform = transformFor(controller);
            if (!element || !transform) return;
            if (event.target.closest("[data-figma-copy]")) { copySelected(controller); return; }
            if (event.target.closest("[data-figma-duplicate]")) { copySelected(controller); paste(controller); return; }
            if (event.target.closest("[data-figma-delete]")) { deleteSelected(controller); return; }
            if (event.target.closest("[data-figma-apply-line]")) {
                const length = controller.properties.querySelector("[data-figma-line-length]");
                const angle = controller.properties.querySelector("[data-figma-line-angle]");
                const result = segmentModel.resizeLine(element, transform, { lengthCm: length && length.value, angleDeg: angle && angle.value, anchor: "start" });
                if (result.valid) applyEditedSegment(controller, result.element);
                return;
            }
            if (event.target.closest("[data-figma-apply-arc]")) {
                const chord = controller.properties.querySelector("[data-figma-arc-chord]");
                const rise = controller.properties.querySelector("[data-figma-arc-rise]");
                const result = segmentModel.resizeArc(element, transform, { chordCm: chord && chord.value, riseCm: rise && rise.value, anchor: "start" });
                if (result.valid) applyEditedSegment(controller, result.element);
            }
        });
        controller.properties.addEventListener("keydown", event => {
            if (event.key !== "Enter") return;
            const apply = controller.properties.querySelector(lineModel.exactMeta(selectedElement(controller)) ? "[data-figma-apply-line]" : "[data-figma-apply-arc]");
            if (apply) { event.preventDefault(); event.stopPropagation(); apply.click(); }
        });
    }

    function bindDock(controller) {
        controller.dock.addEventListener("click", event => {
            const button = event.target.closest && event.target.closest("[data-figma-tool]");
            if (!button) return;
            const target = toolTarget(controller.root, button.dataset.figmaTool);
            if (target) target.click();
            window.setTimeout(() => {
                updateDock(controller);
                const exactHud = controller.root.querySelector(".dco-exact-line-hud");
                if (exactHud && exactHud.parentNode !== controller.toolOptions) controller.toolOptions.appendChild(exactHud);
            }, 0);
        });
    }

    function bindKeyboard(controller) {
        const handler = event => {
            if (!controller.modal.classList.contains("show") && controller.modal.style.display !== "block") return;
            const target = event.target;
            if (target && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)) return;
            const mod = event.ctrlKey || event.metaKey;
            const key = String(event.key || "").toLowerCase();
            if (mod && key === "c") { if (copySelected(controller)) event.preventDefault(); return; }
            if (mod && key === "v") { if (paste(controller)) event.preventDefault(); return; }
            if (mod && key === "d") { const element = selectedElement(controller); if (element) { clipboard = clone(element); paste(controller); event.preventDefault(); } return; }
            if ((event.key === "Delete" || event.key === "Backspace") && selectedElement(controller)) { if (deleteSelected(controller)) event.preventDefault(); return; }
            if (mod) return;
            const shortcut = { v: "select", l: "exact-line", p: "pen", r: "rectangle", o: "ellipse", d: "dimension", n: "note" }[key];
            if (shortcut) { const targetTool = toolTarget(controller.root, shortcut); if (targetTool) { targetTool.click(); event.preventDefault(); updateDock(controller); } }
        };
        document.addEventListener("keydown", handler, true);
        controller.keyHandler = handler;
    }

    function mount(frm, row) {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        const center = root && root.querySelector(".dco-sketch-center");
        const paperWrap = root && root.querySelector(".dco-sketch-paper-wrap");
        const svg = root && root.querySelector(".dco-sketch-paper");
        const exactHud = root && root.querySelector(".dco-exact-line-hud");
        if (!root || !center || !paperWrap || !svg || !exactHud || root.dataset.dcoFigmaEditor === "1") return Boolean(root && root.dataset.dcoFigmaEditor === "1");

        root.dataset.dcoFigmaEditor = "1";
        root.classList.add("dco-figma-editor");
        const panel = document.createElement("aside");
        panel.className = "dco-figma-properties";
        panel.innerHTML = `<div class="dco-figma-properties-head"><strong>الخصائص</strong><span>بدون Layers</span></div><div class="dco-figma-tool-options"></div><div class="dco-figma-selection-properties"></div>`;
        root.appendChild(panel);
        paperWrap.insertAdjacentHTML("beforeend", dockHtml());
        const controller = {
            frm, row, modal, root, center, paperWrap, svg,
            propertiesPanel: panel,
            toolOptions: panel.querySelector(".dco-figma-tool-options"),
            properties: panel.querySelector(".dco-figma-selection-properties"),
            dock: paperWrap.querySelector(".dco-figma-dock"),
            observer: null, rendering: false, drag: null, lastSelectedId: "", keyHandler: null,
        };
        controller.toolOptions.appendChild(exactHud);
        bindDock(controller); bindProperties(controller); bindEndpointDragging(controller); bindKeyboard(controller);

        svg.addEventListener("pointerdown", event => {
            if (event.target.closest && event.target.closest("[data-figma-endpoint]")) return;
            window.setTimeout(() => renderAll(controller), 0);
        }, false);
        controller.observer = new MutationObserver(() => {
            if (controller.rendering) return;
            window.setTimeout(() => renderAll(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        renderAll(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-figma-editor", () => {
                if (controller.observer) controller.observer.disconnect();
                if (controller.keyHandler) document.removeEventListener("keydown", controller.keyHandler, true);
            });
        }
        return true;
    }

    function scheduleMount(frm, row, attempt = 0) {
        window.setTimeout(() => {
            if (mount(frm, row)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(frm, row, attempt + 1);
        }, attempt ? 45 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount(frm, row);
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({ ...baseEditor, __figmaEditorIntegrated: true, open, view });
    window.AlmdinaFigmaEditorUX = Object.freeze({ installStyles, mount, model: interaction });
})();
