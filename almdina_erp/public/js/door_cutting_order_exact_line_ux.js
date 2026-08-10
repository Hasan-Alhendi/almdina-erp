(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const model = window.AlmdinaExactLineModel;
    if (!baseEditor || !history || !model) {
        console.error("Exact-line dependencies must load before the exact-line UX");
        return;
    }
    if (baseEditor.__exactLineIntegrated) return;

    const STYLE_ID = "dco-exact-line-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 14;
    let sequence = 0;

    function esc(value) {
        if (window.frappe && frappe.utils && frappe.utils.escape_html) {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-exact-line-tool{display:flex;align-items:center;gap:9px;width:100%;min-height:42px;border:1px solid #b8d9f3;border-radius:10px;background:#f5fbff;color:#175f91;padding:6px 8px;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-exact-line-tool:hover{border-color:#2490ef;background:#edf8ff}
            .dco-exact-line-tool.is-active{border-color:#2490ef;background:#e6f5ff;box-shadow:0 0 0 2px rgba(36,144,239,.10);color:#0e639d}
            .dco-exact-line-tool-icon{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;background:#dff1ff;color:#0d6da8;font-size:15px;font-weight:900;flex:0 0 auto}
            .dco-exact-line-tool strong{display:block;font-size:9.5px}
            .dco-exact-line-tool small{display:block;margin-top:1px;color:#55768c;font-size:7.5px;font-weight:500}
            .dco-exact-line-hud{position:absolute;z-index:8;top:20px;left:20px;width:285px;display:none;direction:rtl;border:1px solid #cbd9e4;border-radius:14px;background:rgba(255,255,255,.98);box-shadow:0 12px 36px rgba(15,23,42,.15);backdrop-filter:blur(8px);overflow:hidden}
            .dco-exact-line-hud.is-visible{display:block}
            .dco-exact-line-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;background:#f4f9fd;border-bottom:1px solid #e3ebf1}
            .dco-exact-line-head strong{font-size:10px;color:#163d59}
            .dco-exact-line-badge{padding:4px 7px;border-radius:999px;background:#dff1ff;color:#0e639d;font-size:7.5px;font-weight:900}
            .dco-exact-line-body{padding:10px}
            .dco-exact-line-status{min-height:34px;margin-bottom:8px;padding:7px 8px;border-radius:9px;background:#f8fafc;color:#536979;font-size:8px;line-height:1.55}
            .dco-exact-line-status.is-ready{background:#edf9f3;color:#12633f}
            .dco-exact-line-grid{display:grid;grid-template-columns:1fr .78fr;gap:7px;margin-bottom:7px}
            .dco-exact-line-field label{display:block;margin-bottom:4px;color:#64748b;font-size:7.5px;font-weight:900}
            .dco-exact-line-shell{display:flex;align-items:center;border:1px solid #d5dfe6;border-radius:9px;background:#fff;overflow:hidden}
            .dco-exact-line-shell input{min-width:0;width:100%;height:37px;border:0!important;box-shadow:none!important;padding:5px 7px;text-align:center;font-size:13px;font-weight:900;color:#172033}
            .dco-exact-line-shell span{padding:0 7px;border-right:1px solid #e4eaee;color:#64748b;font-size:7.5px;white-space:nowrap}
            .dco-exact-line-axis{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:7px}
            .dco-exact-line-axis button,.dco-exact-line-reset{min-height:34px;border:1px solid #d6e0e7;border-radius:9px;background:#fff;color:#334155;cursor:pointer;font-size:8px;font-weight:900}
            .dco-exact-line-axis button:hover,.dco-exact-line-reset:hover{border-color:#2490ef;color:#0e639d;background:#f4faff}
            .dco-exact-line-axis button.is-active{border-color:#2490ef;background:#e9f6ff;color:#0e639d}
            .dco-exact-line-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px;padding:6px 8px;border-radius:8px;background:#f8fafc;color:#667785;font-size:7.5px}
            .dco-exact-line-meta b{color:#24465c;font-variant-numeric:tabular-nums}
            .dco-exact-line-reset{width:100%}
            .dco-exact-line-foot{margin-top:7px;color:#718096;font-size:7px;line-height:1.5}
            .dco-exact-frame{fill:rgba(36,144,239,.025);stroke:#2490ef;stroke-width:1.2;stroke-dasharray:8 6;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-exact-frame-label{fill:#0f6fad;font-family:Tahoma,Arial,sans-serif;font-size:11px;font-weight:900;pointer-events:none}
            .dco-exact-line-preview{stroke:#2490ef;stroke-width:3;stroke-dasharray:9 6;stroke-linecap:round;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-exact-line-start{fill:#fff;stroke:#158e5b;stroke-width:2.3;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-exact-line-end{fill:#2490ef;stroke:#fff;stroke-width:2.3;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-exact-line-label rect{fill:rgba(255,255,255,.96);stroke:#9cc9e7;stroke-width:1;vector-effect:non-scaling-stroke}
            .dco-exact-line-label text{fill:#0f5f92;font-family:Tahoma,Arial,sans-serif;font-size:11px;font-weight:900;text-anchor:middle;dominant-baseline:central;pointer-events:none}
            .dco-exact-saved-label{fill:#0b6e4f;font-family:Tahoma,Arial,sans-serif;font-size:10px;font-weight:900;text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:4;stroke-linejoin:round;pointer-events:none}
            @media(max-width:700px){.dco-exact-line-hud{left:12px;right:12px;top:12px;width:auto}.dco-exact-line-tool{display:none}}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        return modals.reverse().find(modal =>
            !modal.classList.contains("dco-special-shape-readonly")
            && (modal.classList.contains("show") || modal.style.display === "block")
        ) || null;
    }

    function liveState(controller) {
        const current = history.getActiveState ? history.getActiveState() : null;
        if (current && current.root === controller.root && current.svg === controller.svg) return current;
        return null;
    }

    // The legacy editor originally spread the history seed into its host state.
    // A harmless empty selection publishes that host object back through history,
    // so extensions share one source of truth without duplicating editor state.
    function ensureLiveState(controller) {
        let state = liveState(controller);
        if (state) return state;
        const activeButton = controller.root.querySelector(".dco-sketch-tool.is-active");
        const selectButton = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (!selectButton) return null;
        controller.refreshing = true;
        try {
            selectButton.click();
            const rect = controller.svg.getBoundingClientRect();
            const EventClass = window.PointerEvent || window.MouseEvent;
            controller.svg.dispatchEvent(new EventClass("pointerdown", {
                bubbles: true,
                cancelable: true,
                button: 0,
                clientX: rect.left + 1,
                clientY: rect.top + 1,
                pointerId: 881,
            }));
            if (activeButton && activeButton !== selectButton) activeButton.click();
        } finally {
            controller.refreshing = false;
        }
        state = history.getActiveState ? history.getActiveState() : null;
        return state && state.root === controller.root ? state : null;
    }

    function pointFromEvent(controller, event) {
        const point = baseEditor.clientPointToCanvas(
            controller.svg,
            event.clientX,
            event.clientY
        );
        return [Number(point.x), Number(point.y)];
    }

    function activeAngle(controller) {
        if (controller.axis === "horizontal") {
            return controller.pointerCm && controller.startCm
                && controller.pointerCm[0] < controller.startCm[0] ? 180 : 0;
        }
        if (controller.axis === "vertical") {
            return controller.pointerCm && controller.startCm
                && controller.pointerCm[1] < controller.startCm[1] ? -90 : 90;
        }
        if (controller.manualAngle) {
            return model.normalizeAngle(controller.angleInput.value);
        }
        if (controller.startCm && controller.pointerCm) {
            return controller.shiftHeld
                ? model.axisLockedAngle(controller.startCm, controller.pointerCm)
                : model.angleBetween(controller.startCm, controller.pointerCm);
        }
        return model.normalizeAngle(controller.angleInput.value || 0);
    }

    function updateHud(controller) {
        const angle = activeAngle(controller);
        if (!controller.manualAngle && controller.axis === "pointer") {
            controller.angleInput.value = Number.isFinite(angle) ? String(model.rounded(angle, 1)) : "0";
        }
        const maximum = controller.startCm
            ? model.maxLengthFrom(controller.transform, controller.startCm, angle)
            : 0;
        controller.maxValue.textContent = controller.startCm
            ? `${model.rounded(maximum, 2)} سم`
            : "—";
        controller.axisButtons.forEach(button => {
            button.classList.toggle("is-active", button.dataset.exactAxis === controller.axis);
        });
        if (!controller.startCm) {
            controller.status.className = "dco-exact-line-status";
            controller.status.textContent = "انقر نقطة البداية داخل إطار الدرفة الحقيقي، ثم وجّه المؤشر واكتب الطول واضغط Enter.";
            return;
        }
        controller.status.className = "dco-exact-line-status is-ready";
        controller.status.innerHTML = `البداية <b>${model.rounded(controller.startCm[0], 2)}، ${model.rounded(controller.startCm[1], 2)}</b> سم · اكتب الطول الآن ثم Enter. بعد الإضافة تصبح النهاية بداية الخط التالي تلقائيًا.`;
    }

    function labelGroup(svg, x, y, text, className = "dco-exact-line-label") {
        const group = document.createElementNS(SVG_NS, "g");
        group.setAttribute("class", className);
        const width = Math.max(64, String(text).length * 7.2);
        const rect = document.createElementNS(SVG_NS, "rect");
        rect.setAttribute("x", String(x - width / 2));
        rect.setAttribute("y", String(y - 25));
        rect.setAttribute("width", String(width));
        rect.setAttribute("height", "20");
        rect.setAttribute("rx", "6");
        group.appendChild(rect);
        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("x", String(x));
        label.setAttribute("y", String(y - 15));
        label.textContent = text;
        group.appendChild(label);
        svg.appendChild(group);
    }

    function renderOverlay(controller) {
        if (controller.rendering) return;
        controller.rendering = true;
        try {
            const existing = controller.svg.querySelector(".dco-exact-line-overlay");
            if (existing) existing.remove();
            const state = liveState(controller) || history.getActiveState && history.getActiveState();
            const exactLines = state && Array.isArray(state.elements)
                ? state.elements.filter(element => model.exactMeta(element))
                : [];
            if (!controller.active && !exactLines.length) return;

            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-exact-line-overlay");
            group.setAttribute("pointer-events", "none");
            if (controller.active && controller.transform) {
                const topLeft = model.cmToCanvas(controller.transform, [0, 0]);
                const bottomRight = model.cmToCanvas(controller.transform, [
                    controller.transform.widthCm,
                    controller.transform.lengthCm,
                ]);
                const frame = document.createElementNS(SVG_NS, "rect");
                frame.setAttribute("class", "dco-exact-frame");
                frame.setAttribute("x", String(topLeft[0]));
                frame.setAttribute("y", String(topLeft[1]));
                frame.setAttribute("width", String(bottomRight[0] - topLeft[0]));
                frame.setAttribute("height", String(bottomRight[1] - topLeft[1]));
                group.appendChild(frame);
                const title = document.createElementNS(SVG_NS, "text");
                title.setAttribute("class", "dco-exact-frame-label");
                title.setAttribute("x", String(topLeft[0] + 7));
                title.setAttribute("y", String(topLeft[1] - 9));
                title.textContent = `${model.rounded(controller.transform.widthCm, 2)} × ${model.rounded(controller.transform.lengthCm, 2)} سم`;
                group.appendChild(title);
            }

            exactLines.forEach(element => {
                const meta = model.exactMeta(element);
                const midX = (Number(element.x1) + Number(element.x2)) / 2;
                const midY = (Number(element.y1) + Number(element.y2)) / 2;
                const label = document.createElementNS(SVG_NS, "text");
                label.setAttribute("class", "dco-exact-saved-label");
                label.setAttribute("x", String(midX));
                label.setAttribute("y", String(midY - 9));
                label.textContent = `${model.rounded(meta.length_cm, 2)} سم`;
                group.appendChild(label);
            });

            if (controller.active && controller.startCm) {
                const angle = activeAngle(controller);
                const parsed = model.command(controller.lengthInput.value);
                const fallbackLength = controller.pointerCm
                    ? Math.hypot(
                        controller.pointerCm[0] - controller.startCm[0],
                        controller.pointerCm[1] - controller.startCm[1]
                    ) : 0;
                const length = parsed.valid ? parsed.lengthCm : fallbackLength;
                const maximum = model.maxLengthFrom(controller.transform, controller.startCm, angle);
                const previewLength = Math.min(Math.max(0, length), maximum);
                const endCm = model.pointAt(controller.startCm, previewLength, angle);
                const start = model.cmToCanvas(controller.transform, controller.startCm);
                const end = model.cmToCanvas(controller.transform, endCm);
                const line = document.createElementNS(SVG_NS, "line");
                line.setAttribute("class", "dco-exact-line-preview");
                line.setAttribute("x1", String(start[0]));
                line.setAttribute("y1", String(start[1]));
                line.setAttribute("x2", String(end[0]));
                line.setAttribute("y2", String(end[1]));
                group.appendChild(line);
                const startCircle = document.createElementNS(SVG_NS, "circle");
                startCircle.setAttribute("class", "dco-exact-line-start");
                startCircle.setAttribute("cx", String(start[0]));
                startCircle.setAttribute("cy", String(start[1]));
                startCircle.setAttribute("r", "6");
                group.appendChild(startCircle);
                const endCircle = document.createElementNS(SVG_NS, "circle");
                endCircle.setAttribute("class", "dco-exact-line-end");
                endCircle.setAttribute("cx", String(end[0]));
                endCircle.setAttribute("cy", String(end[1]));
                endCircle.setAttribute("r", "5");
                group.appendChild(endCircle);
                controller.svg.appendChild(group);
                if (previewLength > 0.03) {
                    labelGroup(
                        controller.svg,
                        (start[0] + end[0]) / 2,
                        (start[1] + end[1]) / 2,
                        `${model.rounded(previewLength, 2)} سم · ${model.rounded(angle, 1)}°`
                    );
                }
                return;
            }
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
        }
    }

    function refreshEditor(controller) {
        const button = controller.root.querySelector(".dco-sketch-tool.is-active")
            || controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (!button) return;
        controller.refreshing = true;
        try { button.click(); } finally { controller.refreshing = false; }
    }

    function setActive(controller, active) {
        if (active && !controller.transform) {
            if (window.frappe) frappe.msgprint("أدخل عرض الدرفة وطولها أولًا حتى يستطيع النظام إنشاء خط بقياس حقيقي.");
            return false;
        }
        controller.active = Boolean(active);
        controller.button.classList.toggle("is-active", controller.active);
        controller.hud.classList.toggle("is-visible", controller.active);
        if (!controller.active) {
            controller.startCm = null;
            controller.pointerCm = null;
            controller.shiftHeld = false;
        } else {
            ensureLiveState(controller);
            controller.lengthInput.focus();
        }
        updateHud(controller);
        renderOverlay(controller);
        return controller.active;
    }

    function commit(controller) {
        const state = ensureLiveState(controller);
        if (!state || !controller.startCm) return false;
        const parsed = model.command(controller.lengthInput.value);
        if (!parsed.valid) {
            controller.status.className = "dco-exact-line-status";
            controller.status.textContent = "أدخل طولًا أكبر من صفر، مثال: 45 ثم اضغط Enter.";
            controller.lengthInput.focus();
            return false;
        }
        if (parsed.angleDeg !== null) {
            controller.manualAngle = true;
            controller.axis = "pointer";
            controller.angleInput.value = String(parsed.angleDeg);
        }
        const angle = activeAngle(controller);
        sequence += 1;
        const result = model.buildElement({
            transform: controller.transform,
            startCm: controller.startCm,
            lengthCm: parsed.lengthCm,
            angleDeg: angle,
            color: state.color,
            id: `exact-line-${Date.now()}-${sequence}`,
        });
        if (!result.valid) {
            const maximum = Number(result.maximumLengthCm) || 0;
            controller.status.className = "dco-exact-line-status";
            controller.status.innerHTML = maximum > 0
                ? `الخط يخرج خارج حدود الدرفة. أقصى طول في هذا الاتجاه هو <b>${model.rounded(maximum, 2)} سم</b>.`
                : "لا يمكن إنشاء الخط في هذا الاتجاه من نقطة البداية الحالية.";
            controller.lengthInput.focus();
            return false;
        }
        const transition = history.addElement(state, result.element);
        if (!transition || !transition.changed) return false;
        Object.assign(state, transition.patch);
        if (history.activateState) history.activateState(state);
        const meta = model.exactMeta(result.element);
        controller.startCm = meta.end_cm.slice();
        controller.pointerCm = model.pointAt(controller.startCm, 1, angle);
        controller.lengthInput.value = "";
        controller.manualAngle = false;
        controller.axis = "pointer";
        refreshEditor(controller);
        updateHud(controller);
        renderOverlay(controller);
        controller.lengthInput.focus();
        const notice = controller.root.querySelector(".dco-sketch-notice-text");
        if (notice) notice.textContent = `تمت إضافة خط دقيق بطول ${model.rounded(meta.length_cm, 2)} سم. النهاية أصبحت نقطة بداية الخط التالي.`;
        if (window.frappe) frappe.show_alert({ message: `خط ${model.rounded(meta.length_cm, 2)} سم`, indicator: "green" }, 3);
        return true;
    }

    function mount(row) {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoExactLine === "1") return Boolean(root);
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        const toolbar = root.querySelector(".dco-sketch-toolbar");
        const normalLine = root.querySelector('.dco-sketch-tool[data-tool="line"]');
        if (!svg || !paperWrap || !toolbar || !normalLine) return false;

        const dimensions = model.pieceDimensions(row);
        const transform = model.createTransform(dimensions.width, dimensions.length);
        root.dataset.dcoExactLine = "1";
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dco-exact-line-tool";
        button.innerHTML = `<span class="dco-exact-line-tool-icon">↔</span><span><strong>خط بمقاس حقيقي</strong><small>انقر البداية · وجّه · اكتب الطول · Enter</small></span>`;
        normalLine.insertAdjacentElement("afterend", button);

        const hud = document.createElement("section");
        hud.className = "dco-exact-line-hud";
        hud.innerHTML = `
            <div class="dco-exact-line-head"><strong>الخط الدقيق</strong><span class="dco-exact-line-badge">CM · EXACT</span></div>
            <div class="dco-exact-line-body">
                <div class="dco-exact-line-status"></div>
                <div class="dco-exact-line-grid">
                    <div class="dco-exact-line-field"><label>طول الخط</label><div class="dco-exact-line-shell"><input type="text" inputmode="decimal" autocomplete="off" placeholder="45" data-exact-length><span>سم</span></div></div>
                    <div class="dco-exact-line-field"><label>الزاوية</label><div class="dco-exact-line-shell"><input type="number" step="1" value="0" data-exact-angle><span>°</span></div></div>
                </div>
                <div class="dco-exact-line-axis"><button type="button" data-exact-axis="horizontal">↔ أفقي</button><button type="button" data-exact-axis="vertical">↕ عمودي</button></div>
                <div class="dco-exact-line-meta"><span>أقصى طول في الاتجاه</span><b data-exact-max>—</b></div>
                <button type="button" class="dco-exact-line-reset">إنهاء السلسلة / نقطة بداية جديدة</button>
                <div class="dco-exact-line-foot">بدون اختيار أفقي/عمودي، اتجاه المؤشر هو الاتجاه. Shift يقفل الاتجاه على محور. يمكنك أيضًا كتابة <b>45@30</b> لإنشاء 45 سم بزاوية 30°.</div>
            </div>`;
        paperWrap.appendChild(hud);

        const controller = {
            modal,
            root,
            svg,
            row,
            transform,
            button,
            hud,
            status: hud.querySelector(".dco-exact-line-status"),
            lengthInput: hud.querySelector("[data-exact-length]"),
            angleInput: hud.querySelector("[data-exact-angle]"),
            maxValue: hud.querySelector("[data-exact-max]"),
            axisButtons: Array.from(hud.querySelectorAll("[data-exact-axis]")),
            active: false,
            startCm: null,
            pointerCm: null,
            shiftHeld: false,
            axis: "pointer",
            manualAngle: false,
            refreshing: false,
            rendering: false,
            observer: null,
        };

        button.addEventListener("click", () => setActive(controller, !controller.active));
        controller.axisButtons.forEach(axisButton => axisButton.addEventListener("click", () => {
            controller.axis = axisButton.dataset.exactAxis;
            controller.manualAngle = false;
            updateHud(controller);
            renderOverlay(controller);
            controller.lengthInput.focus();
        }));
        controller.angleInput.addEventListener("input", () => {
            controller.axis = "pointer";
            controller.manualAngle = true;
            updateHud(controller);
            renderOverlay(controller);
        });
        controller.lengthInput.addEventListener("input", () => renderOverlay(controller));
        controller.lengthInput.addEventListener("keydown", event => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            event.stopPropagation();
            commit(controller);
        });
        hud.querySelector(".dco-exact-line-reset").addEventListener("click", () => {
            controller.startCm = null;
            controller.pointerCm = null;
            controller.lengthInput.value = "";
            controller.axis = "pointer";
            controller.manualAngle = false;
            updateHud(controller);
            renderOverlay(controller);
        });

        root.addEventListener("click", event => {
            if (!controller.active || controller.refreshing) return;
            const baseTool = event.target.closest && event.target.closest(".dco-sketch-tool");
            if (baseTool) setActive(controller, false);
        }, true);

        svg.addEventListener("pointerdown", event => {
            if (!controller.active) return;
            const state = ensureLiveState(controller);
            if (!state) return;
            const canvasPoint = pointFromEvent(controller, event);
            let cmPoint = model.canvasToCm(controller.transform, canvasPoint);
            if (!model.insidePiece(controller.transform, cmPoint, 0.02)) {
                controller.status.className = "dco-exact-line-status";
                controller.status.textContent = "انقر داخل الإطار الأزرق؛ هذا الإطار يمثل أبعاد الدرفة الحقيقية بالسنتيمتر.";
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            cmPoint = model.clampPointToPiece(controller.transform, cmPoint);
            const snapped = model.nearestEndpoint(cmPoint, state.elements);
            cmPoint = snapped ? snapped.point : cmPoint;
            if (!controller.startCm) controller.startCm = cmPoint.slice();
            controller.pointerCm = cmPoint.slice();
            controller.lengthInput.focus();
            updateHud(controller);
            renderOverlay(controller);
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        svg.addEventListener("pointermove", event => {
            if (!controller.active || !controller.startCm) return;
            const canvasPoint = pointFromEvent(controller, event);
            controller.pointerCm = model.canvasToCm(controller.transform, canvasPoint);
            controller.shiftHeld = Boolean(event.shiftKey);
            if (!controller.manualAngle && controller.axis === "pointer") updateHud(controller);
            renderOverlay(controller);
            event.preventDefault();
            event.stopImmediatePropagation();
        }, true);

        const keyHandler = event => {
            if (!controller.active) return;
            if (event.key === "Escape") {
                event.preventDefault();
                event.stopImmediatePropagation();
                if (controller.startCm) {
                    controller.startCm = null;
                    controller.pointerCm = null;
                    controller.lengthInput.value = "";
                    updateHud(controller);
                    renderOverlay(controller);
                } else {
                    setActive(controller, false);
                }
            }
        };
        document.addEventListener("keydown", keyHandler, true);

        controller.observer = new MutationObserver(() => {
            window.setTimeout(() => renderOverlay(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        updateHud(controller);
        renderOverlay(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-exact-line", () => {
                document.removeEventListener("keydown", keyHandler, true);
                if (controller.observer) controller.observer.disconnect();
                if (history.clearActiveState) history.clearActiveState(liveState(controller));
            });
        }
        return true;
    }

    function scheduleMount(row, attempt = 0) {
        window.setTimeout(() => {
            if (mount(row)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(row, attempt + 1);
        }, attempt ? 35 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount(row);
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __exactLineIntegrated: true,
        open,
        view,
    });
    window.AlmdinaExactLineUX = Object.freeze({
        installStyles,
        mount,
        model,
    });
})();
