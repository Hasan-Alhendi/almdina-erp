(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const lineModel = window.AlmdinaExactLineModel;
    const arcModel = window.AlmdinaExactArcModel;
    const dimensionModel = window.AlmdinaExactSegmentDimensionModel;
    if (!baseEditor || !history || !lineModel || !arcModel || !dimensionModel) {
        console.error("Exact segment dimension dependencies must load before dimensions UX");
        return;
    }
    if (baseEditor.__exactSegmentDimensionsIntegrated) return;

    const STYLE_ID = "dco-exact-segment-dimensions-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 14;

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-all-dimensions-tool{margin-top:4px;border:1px solid #bfd8ea!important;background:#f4faff!important}.dco-all-dimensions-tool.is-active{background:#e5f4ff!important;border-color:#2490ef!important;color:#0e639d!important}
            .dco-all-dimensions-panel{position:absolute;z-index:12;left:20px;top:20px;width:350px;max-height:calc(100% - 40px);display:none;direction:rtl;border:1px solid #c8d8e4;border-radius:15px;background:rgba(255,255,255,.99);box-shadow:0 15px 42px rgba(15,23,42,.17);backdrop-filter:blur(9px);overflow:hidden}
            .dco-all-dimensions-panel.is-visible{display:flex;flex-direction:column}.dco-all-dimensions-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;background:#f5f9fc;border-bottom:1px solid #e2e9ee}.dco-all-dimensions-head strong{font-size:10px;color:#173d57}.dco-all-dimensions-head span{padding:4px 7px;border-radius:999px;background:#e4f4ff;color:#0e639d;font-size:7px;font-weight:900}
            .dco-all-dimensions-summary{padding:8px 10px;border-bottom:1px solid #edf1f4;color:#5f7180;font-size:7.6px;line-height:1.55}.dco-all-dimensions-summary b{color:#23465f}.dco-all-dimensions-options{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:5px}.dco-all-dimensions-options label{display:flex;align-items:center;gap:5px;margin:0;font-weight:800}.dco-all-dimensions-options input{accent-color:#1769aa}.dco-all-dimensions-close{border:0;background:transparent;color:#64748b;cursor:pointer;font-size:15px;line-height:1}
            .dco-all-dimensions-list{padding:8px;overflow:auto;display:flex;flex-direction:column;gap:7px}.dco-all-dimension-row{border:1px solid #dfe7ec;border-radius:11px;background:#fff;overflow:hidden;transition:.12s ease}.dco-all-dimension-row:hover{border-color:#b8d3e5}.dco-all-dimension-row.is-selected{border-color:#2490ef;box-shadow:0 0 0 2px rgba(36,144,239,.09)}
            .dco-all-dimension-row-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 8px;background:#f8fafc;cursor:pointer}.dco-all-dimension-row-title{display:flex;align-items:center;gap:7px;font-size:8px;font-weight:900;color:#29485d}.dco-all-dimension-row-icon{display:grid;place-items:center;width:23px;height:23px;border-radius:7px;background:#eaf5fc;color:#0e639d;font-size:12px}.dco-all-dimension-row-meta{font-size:6.8px;color:#718096;direction:ltr}
            .dco-all-dimension-fields{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:8px}.dco-all-dimension-field label{display:block;margin-bottom:3px;color:#6b7b87;font-size:6.8px;font-weight:900}.dco-all-dimension-input{display:flex;align-items:center;border:1px solid #d7e0e6;border-radius:8px;overflow:hidden}.dco-all-dimension-input input{width:100%;min-width:0;height:34px;border:0!important;box-shadow:none!important;padding:5px;text-align:center;font-size:10.5px;font-weight:900;color:#172033}.dco-all-dimension-input span{padding:0 6px;border-right:1px solid #e7ecef;color:#718096;font-size:6.5px}
            .dco-all-dimension-substats{grid-column:1/-1;display:flex;gap:5px;flex-wrap:wrap}.dco-all-dimension-pill{padding:4px 6px;border-radius:999px;background:#f3f6f8;color:#64748b;font-size:6.6px}.dco-all-dimension-pill b{color:#35556a}
            .dco-all-dimension-actions{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr auto;gap:5px;align-items:center}.dco-all-dimension-anchor{display:flex;border:1px solid #d8e1e7;border-radius:8px;overflow:hidden}.dco-all-dimension-anchor button{flex:1;min-height:29px;border:0;border-left:1px solid #e1e7eb;background:#fff;color:#64748b;font-size:6.7px;font-weight:900;cursor:pointer}.dco-all-dimension-anchor button:last-child{border-left:0}.dco-all-dimension-anchor button.is-active{background:#e9f6ff;color:#0e639d}.dco-all-dimension-apply{min-width:54px;min-height:31px;border:1px solid #1769aa;border-radius:8px;background:#1769aa;color:#fff;font-size:7px;font-weight:900;cursor:pointer}.dco-all-dimension-apply:hover{background:#0f5f92}.dco-all-dimension-status{padding:7px 9px;border-top:1px solid #edf1f4;background:#f8fafc;color:#5f7180;font-size:7px}.dco-all-dimension-status.is-error{background:#fff1ef;color:#a33126}.dco-all-dimension-status.is-success{background:#edf9f3;color:#12633f}
            .dco-exact-measure-overlay{pointer-events:none}.dco-exact-measure-tag{fill:#fff;stroke:#9bbfd6;stroke-width:1;vector-effect:non-scaling-stroke}.dco-exact-measure-text{fill:#174f70;font-family:Tahoma,Arial,sans-serif;font-size:9px;font-weight:900;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:3;stroke-linejoin:round}.dco-exact-measure-leader{stroke:#76a9c8;stroke-width:1;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
            @media(max-width:700px){.dco-all-dimensions-panel{left:10px;right:10px;top:10px;width:auto;max-height:calc(100% - 20px)}.dco-all-dimension-fields{grid-template-columns:1fr 1fr}}
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

    function transformFor(controller) {
        return lineModel.createTransform(Number(controller.row.width_cm) || 0, Number(controller.row.length_cm) || 0);
    }

    function esc(value) {
        const text = String(value ?? "");
        return window.frappe && frappe.utils ? frappe.utils.escape_html(text) : text.replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
    }

    function fmt(value, precision = 2) {
        return String(lineModel.rounded(value, precision));
    }

    function setStatus(controller, text, type = "") {
        controller.status.className = `dco-all-dimension-status${type ? ` is-${type}` : ""}`;
        controller.status.textContent = text;
    }

    function selectedId(controller) {
        const state = liveState(controller);
        return String(state && state.selectedId || "");
    }

    function selectElement(controller, id) {
        const state = liveState(controller);
        if (!state) return;
        const transition = history.selectElement(state, id);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        if (history.activateState) history.activateState(state);
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        window.setTimeout(() => render(controller), 0);
    }

    function rowHtml(item, selected) {
        const isArc = item.kind === "arc";
        const firstLabel = isArc ? "طول الوتر" : "طول الضلع";
        const firstValue = isArc ? item.chordCm : item.lengthCm;
        const secondLabel = isArc ? "ارتفاع القوس" : "الزاوية";
        const secondValue = isArc ? item.riseCm : item.angleDeg;
        const secondUnit = isArc ? "سم" : "°";
        const extra = isArc
            ? `<div class="dco-all-dimension-substats"><span class="dco-all-dimension-pill">R <b>${fmt(item.radiusCm)}</b> سم</span><span class="dco-all-dimension-pill">طول القوس <b>${fmt(item.arcLengthCm)}</b> سم</span><span class="dco-all-dimension-pill">الجهة <b>${item.side > 0 ? "A" : "B"}</b></span></div>`
            : `<div class="dco-all-dimension-substats"><span class="dco-all-dimension-pill">من <b>${fmt(item.start[0])}, ${fmt(item.start[1])}</b></span><span class="dco-all-dimension-pill">إلى <b>${fmt(item.end[0])}, ${fmt(item.end[1])}</b></span></div>`;
        return `<article class="dco-all-dimension-row${selected ? " is-selected" : ""}" data-dimension-id="${esc(item.id)}" data-kind="${item.kind}" data-anchor="start">
            <div class="dco-all-dimension-row-head" data-select-dimension="${esc(item.id)}"><div class="dco-all-dimension-row-title"><span class="dco-all-dimension-row-icon">${isArc ? "⌒" : "—"}</span><span>${esc(item.label)}</span></div><span class="dco-all-dimension-row-meta">#${item.number} · ${isArc ? "ARC" : "LINE"}</span></div>
            <div class="dco-all-dimension-fields">
                <div class="dco-all-dimension-field"><label>${firstLabel}</label><div class="dco-all-dimension-input"><input type="number" min="0.01" step="0.1" inputmode="decimal" data-primary value="${fmt(firstValue, 3)}"><span>سم</span></div></div>
                <div class="dco-all-dimension-field"><label>${secondLabel}</label><div class="dco-all-dimension-input"><input type="number" step="0.1" inputmode="decimal" data-secondary value="${fmt(secondValue, 3)}"><span>${secondUnit}</span></div></div>
                ${extra}
                <div class="dco-all-dimension-actions"><div class="dco-all-dimension-anchor"><button type="button" class="is-active" data-anchor="start">ثبّت البداية</button><button type="button" data-anchor="end">ثبّت النهاية</button></div>${isArc ? '<button type="button" class="dco-all-dimension-apply" data-flip>عكس</button>' : '<span></span>'}<button type="button" class="dco-all-dimension-apply" data-apply>تطبيق</button></div>
            </div>
        </article>`;
    }

    function renderList(controller) {
        const state = liveState(controller);
        const items = dimensionModel.descriptors(state && state.elements);
        const selected = selectedId(controller);
        controller.tool.hidden = !items.length;
        if (!items.length) {
            controller.list.innerHTML = '<div style="padding:12px;text-align:center;color:#718096;font-size:8px">لا توجد عناصر دقيقة بعد.</div>';
            controller.summary.innerHTML = "لا توجد أضلاع أو أقواس دقيقة.";
            return items;
        }
        const lines = items.filter(item => item.kind === "line").length;
        const arcs = items.filter(item => item.kind === "arc").length;
        controller.summary.innerHTML = `<b>${items.length}</b> عنصر هندسي · ${lines} مستقيم · ${arcs} قوس. أدخل قياس كل عنصر بالسنتيمتر الحقيقي واضغط Enter أو تطبيق.`;
        controller.list.innerHTML = items.map(item => rowHtml(item, item.id === selected)).join("");
        return items;
    }

    function renderLabels(controller, items) {
        if (controller.rendering) return;
        controller.rendering = true;
        if (controller.observer) controller.observer.disconnect();
        try {
            const previous = controller.svg.querySelector(".dco-exact-measure-overlay");
            if (previous) previous.remove();
            if (!controller.panel.classList.contains("is-visible") || !items.length) return;
            const transform = transformFor(controller);
            if (!transform) return;
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-exact-measure-overlay");
            items.forEach(item => {
                let cmPoint;
                let text;
                if (item.kind === "arc") {
                    const element = (liveState(controller).elements || []).find(candidate => String(candidate.id) === item.id);
                    const meta = arcModel.arcMeta(element);
                    cmPoint = meta && meta.apex_cm ? meta.apex_cm : [(item.start[0] + item.end[0]) / 2, (item.start[1] + item.end[1]) / 2];
                    text = `${item.number} · قوس ${fmt(item.arcLengthCm)} سم`;
                } else {
                    cmPoint = [(item.start[0] + item.end[0]) / 2, (item.start[1] + item.end[1]) / 2];
                    text = `${item.number} · ${fmt(item.lengthCm)} سم`;
                }
                const canvas = lineModel.cmToCanvas(transform, cmPoint);
                const width = Math.max(54, Math.min(112, text.length * 5.5));
                const rect = document.createElementNS(SVG_NS, "rect");
                rect.setAttribute("class", "dco-exact-measure-tag");
                rect.setAttribute("x", String(canvas[0] - width / 2));
                rect.setAttribute("y", String(canvas[1] - 11));
                rect.setAttribute("width", String(width));
                rect.setAttribute("height", "22");
                rect.setAttribute("rx", "7");
                group.appendChild(rect);
                const label = document.createElementNS(SVG_NS, "text");
                label.setAttribute("class", "dco-exact-measure-text");
                label.setAttribute("x", String(canvas[0]));
                label.setAttribute("y", String(canvas[1]));
                label.textContent = text;
                group.appendChild(label);
            });
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
            if (controller.observer) controller.observer.observe(controller.svg, { childList: true });
        }
    }

    function render(controller) {
        const items = renderList(controller);
        renderLabels(controller, items);
    }

    function applyRow(controller, row, flipOnly = false) {
        const state = liveState(controller);
        const transform = transformFor(controller);
        if (!state || !transform) return false;
        const id = String(row.dataset.dimensionId || "");
        const element = (state.elements || []).find(candidate => String(candidate && candidate.id) === id);
        if (!element) return false;
        const kind = dimensionModel.kind(element);
        const anchor = row.dataset.anchor === "end" ? "end" : "start";
        const primary = row.querySelector("[data-primary]").value;
        const secondary = row.querySelector("[data-secondary]").value;
        let result;
        if (kind === "arc") {
            const meta = arcModel.arcMeta(element);
            result = dimensionModel.resizeArc(element, transform, {
                chordCm: primary,
                riseCm: secondary,
                side: flipOnly ? -Number(meta.side || 1) : meta.side,
                anchor,
            });
        } else {
            result = dimensionModel.resizeLine(element, transform, {
                lengthCm: primary,
                angleDeg: secondary,
                anchor,
            });
        }
        if (!result || !result.valid) {
            const reason = result && result.reason;
            const message = reason === "arc-outside-piece" || reason === "outside-piece"
                ? "القياس الجديد يخرج العنصر خارج حدود الدرفة."
                : reason === "rise-too-large"
                    ? "ارتفاع القوس أكبر من المسموح بالنسبة لطول الوتر."
                    : "تعذر تطبيق القياس. راجع الطول والزاوية أو الوتر وارتفاع القوس.";
            setStatus(controller, message, "error");
            return false;
        }
        const original = JSON.parse(JSON.stringify(state.elements));
        const applied = dimensionModel.applyEdit(state.elements, id, result.element, transform, {
            preserveConnections: controller.preserve.checked,
        });
        if (!applied.valid) {
            setStatus(controller, "التعديل سيجعل عنصرًا متصلًا غير صالح. غيّر القياس أو عطّل حفظ الاتصال لهذا التعديل.", "error");
            return false;
        }
        const snapshot = history.snapshot(state, original);
        if (snapshot && snapshot.changed) Object.assign(state, snapshot.patch);
        state.elements = applied.elements;
        state.selectedId = id;
        state.hasChanges = true;
        if (history.activateState) history.activateState(state);
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
        setStatus(controller, applied.changedIds.length > 1
            ? `تم تطبيق القياس وحفظ اتصال ${applied.changedIds.length - 1} عنصر مجاور.`
            : "تم تطبيق القياس الحقيقي على العنصر.", "success");
        window.setTimeout(() => render(controller), 0);
        return true;
    }

    function bindPanel(controller) {
        controller.tool.addEventListener("click", () => {
            const visible = !controller.panel.classList.contains("is-visible");
            controller.panel.classList.toggle("is-visible", visible);
            controller.tool.classList.toggle("is-active", visible);
            render(controller);
        });
        controller.close.addEventListener("click", () => {
            controller.panel.classList.remove("is-visible");
            controller.tool.classList.remove("is-active");
            renderLabels(controller, []);
        });
        controller.list.addEventListener("click", event => {
            const select = event.target.closest && event.target.closest("[data-select-dimension]");
            if (select) {
                selectElement(controller, select.dataset.selectDimension);
                return;
            }
            const row = event.target.closest && event.target.closest(".dco-all-dimension-row");
            if (!row) return;
            const anchor = event.target.closest("[data-anchor]");
            if (anchor) {
                row.dataset.anchor = anchor.dataset.anchor;
                row.querySelectorAll("[data-anchor]").forEach(button => button.classList.toggle("is-active", button === anchor));
                return;
            }
            if (event.target.closest("[data-flip]")) {
                applyRow(controller, row, true);
                return;
            }
            if (event.target.closest("[data-apply]")) applyRow(controller, row, false);
        });
        controller.list.addEventListener("keydown", event => {
            if (event.key !== "Enter" || !event.target.matches("input")) return;
            const row = event.target.closest(".dco-all-dimension-row");
            if (!row) return;
            event.preventDefault();
            event.stopPropagation();
            applyRow(controller, row, false);
        });
    }

    function panelHtml() {
        return `<section class="dco-all-dimensions-panel" aria-label="قياسات جميع العناصر">
            <div class="dco-all-dimensions-head"><strong>قياسات جميع العناصر</strong><span>CM · EXACT</span><button type="button" class="dco-all-dimensions-close" aria-label="إغلاق">×</button></div>
            <div class="dco-all-dimensions-summary"></div>
            <div class="dco-all-dimensions-summary"><div class="dco-all-dimensions-options"><label><input type="checkbox" data-preserve-connections checked> حافظ على اتصال العناصر</label><span>Enter = تطبيق</span></div></div>
            <div class="dco-all-dimensions-list"></div>
            <div class="dco-all-dimension-status">كل قيمة هنا مرتبطة بهندسة السنتيمتر الحقيقية، وليست بوحدة الرسم على الشاشة.</div>
        </section>`;
    }

    function toolHtml() {
        return `<button type="button" class="dco-sketch-tool dco-all-dimensions-tool" data-all-dimensions><span class="dco-sketch-tool-icon">⌗</span><span>قياسات العناصر<small>أدخل قياس كل ضلع وقوس</small></span></button>`;
    }

    function mount(frm, row) {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoAllDimensions === "1") return Boolean(root);
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        const toolbar = root.querySelector(".dco-sketch-toolbar");
        if (!svg || !paperWrap || !toolbar) return false;
        root.dataset.dcoAllDimensions = "1";
        toolbar.insertAdjacentHTML("beforeend", toolHtml());
        paperWrap.insertAdjacentHTML("beforeend", panelHtml());
        const panel = paperWrap.querySelector(".dco-all-dimensions-panel");
        const controller = {
            frm,
            row,
            modal,
            root,
            svg,
            toolbar,
            tool: toolbar.querySelector("[data-all-dimensions]"),
            panel,
            close: panel.querySelector(".dco-all-dimensions-close"),
            summary: panel.querySelector(".dco-all-dimensions-summary"),
            list: panel.querySelector(".dco-all-dimensions-list"),
            preserve: panel.querySelector("[data-preserve-connections]"),
            status: panel.querySelector(".dco-all-dimension-status"),
            rendering: false,
            observer: null,
        };
        bindPanel(controller);
        controller.observer = new MutationObserver(() => {
            if (controller.rendering) return;
            window.setTimeout(() => render(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        render(controller);
        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-all-dimensions", () => {
                if (controller.observer) controller.observer.disconnect();
            });
        }
        return true;
    }

    function scheduleMount(frm, row, attempt = 0) {
        window.setTimeout(() => {
            if (mount(frm, row)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(frm, row, attempt + 1);
        }, attempt ? 35 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount(frm, row);
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __exactSegmentDimensionsIntegrated: true,
        open,
        view,
    });
    window.AlmdinaExactSegmentDimensionsUX = Object.freeze({ installStyles, mount, model: dimensionModel });
})();
