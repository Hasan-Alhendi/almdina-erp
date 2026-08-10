(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const lineModel = window.AlmdinaExactLineModel;
    const chainModel = window.AlmdinaExactShapeChainModel;
    if (!baseEditor || !history || !lineModel || !chainModel) {
        console.error("Exact shape-chain dependencies must load before shape-chain UX");
        return;
    }
    if (baseEditor.__exactShapeChainIntegrated) return;

    const STYLE_ID = "dco-exact-shape-chain-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 14;
    let closeSequence = 0;

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-exact-shape-card{position:absolute;z-index:8;right:20px;bottom:20px;width:305px;display:none;direction:rtl;border:1px solid #cbd9e4;border-radius:14px;background:rgba(255,255,255,.985);box-shadow:0 12px 36px rgba(15,23,42,.14);backdrop-filter:blur(8px);overflow:hidden}
            .dco-exact-shape-card.is-visible{display:block}
            .dco-exact-shape-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 11px;background:#f7fafc;border-bottom:1px solid #e4eaee}
            .dco-exact-shape-head strong{font-size:10px;color:#183c56}.dco-exact-shape-badge{padding:4px 7px;border-radius:999px;background:#eef3f6;color:#526779;font-size:7.5px;font-weight:900}
            .dco-exact-shape-badge.is-open{background:#fff4d8;color:#8a5a08}.dco-exact-shape-badge.is-valid{background:#e6f8ef;color:#12633f}.dco-exact-shape-badge.is-error{background:#fff0ee;color:#a33126}
            .dco-exact-shape-body{padding:10px}.dco-exact-shape-status{font-size:8px;line-height:1.6;color:#536979;margin-bottom:8px}.dco-exact-shape-status b{color:#233f53}
            .dco-exact-shape-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-bottom:8px}.dco-exact-shape-stat{padding:6px 5px;border-radius:8px;background:#f6f9fb;text-align:center}.dco-exact-shape-stat b{display:block;color:#24465c;font-size:10px;font-variant-numeric:tabular-nums}.dco-exact-shape-stat span{font-size:6.8px;color:#718096}
            .dco-exact-shape-action{width:100%;min-height:34px;border:1px solid #2490ef;border-radius:9px;background:#edf8ff;color:#0e639d;cursor:pointer;font-size:8px;font-weight:900}.dco-exact-shape-action:hover{background:#dff3ff}.dco-exact-shape-action[hidden]{display:none}
            .dco-exact-shape-note{margin-top:7px;padding:6px 7px;border-radius:8px;background:#f8fafc;color:#6b7b87;font-size:7px;line-height:1.5}.dco-exact-shape-note.is-warning{background:#fff8e8;color:#7a5414}.dco-exact-shape-note.is-success{background:#edf9f3;color:#12633f}
            .dco-exact-close-preview{stroke:#168a60;stroke-width:2;stroke-dasharray:7 5;vector-effect:non-scaling-stroke;pointer-events:none}.dco-exact-close-point{fill:#fff;stroke:#168a60;stroke-width:2;vector-effect:non-scaling-stroke;pointer-events:none}.dco-exact-close-label{fill:#12633f;font-family:Tahoma,Arial,sans-serif;font-size:10px;font-weight:900;text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:4;stroke-linejoin:round;pointer-events:none}
            @media(max-width:700px){.dco-exact-shape-card{left:12px;right:12px;bottom:12px;width:auto}.dco-exact-shape-stats{grid-template-columns:repeat(3,1fr)}}
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
        const state = history.getActiveState ? history.getActiveState() : null;
        return state && state.root === controller.root && state.svg === controller.svg ? state : null;
    }

    function currentElements(controller) {
        const state = liveState(controller);
        if (state && Array.isArray(state.elements)) return state.elements;
        return typeof baseEditor.parseDrawing === "function"
            ? baseEditor.parseDrawing(controller.row.special_shape_drawing_json)
            : [];
    }

    function analyze(controller) {
        return chainModel.analyze(currentElements(controller), {
            width: Number(controller.row.width_cm) || 0,
            length: Number(controller.row.length_cm) || 0,
        });
    }

    function stateCopy(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function labelFor(analysis) {
        if (analysis.state === "exact-closed") return ["مغلق ودقيق", "is-valid"];
        if (analysis.state === "closed-invalid") return ["مغلق · يحتاج تصحيح", "is-error"];
        if (analysis.state === "open") return ["المسار مفتوح", "is-open"];
        if (analysis.state === "branched") return ["المسار متشعب", "is-error"];
        if (analysis.state === "disconnected") return ["خطوط منفصلة", "is-error"];
        if (analysis.state === "invalid") return ["مسار غير صالح", "is-error"];
        return ["لا توجد خطوط دقيقة", ""];
    }

    function statusText(controller, analysis) {
        if (analysis.state === "exact-closed") {
            return `تم التعرف على حدود مغلقة حقيقية من <b>${analysis.exactLineCount}</b> أضلاع. سيُزامن الشكل الهندسي بالسنتيمتر عند حفظ الرسم.`;
        }
        if (analysis.state === "closed-invalid") {
            const firstError = analysis.geometryErrors[0] || "الشكل المغلق لا يحقق شروط الهندسة الدقيقة.";
            return `المسار مغلق، لكنه لا يمكن اعتماده كمسار قص دقيق بعد: <b>${firstError}</b>`;
        }
        if (analysis.state === "open") {
            return analysis.canAutoClose
                ? `المسار متصل لكنه مفتوح. المسافة بين طرفي الإغلاق <b>${lineModel.rounded(analysis.closeGapCm, 2)} سم</b>.`
                : "أكمل الأضلاع حتى يصبح لديك مسار واحد يمكن إغلاقه.";
        }
        if (analysis.state === "branched") return "هناك نقطة تتصل بها أكثر من ضلعين. حدود الدرفة يجب أن تكون مسارًا واحدًا بلا تفرعات.";
        if (analysis.state === "disconnected") return "توجد مجموعات خطوط دقيقة غير متصلة. اربطها أولًا قبل اعتماد الشكل.";
        if (analysis.state === "invalid") return "الخطوط الحالية لا تكوّن مسارًا بسيطًا. راجع نقاط الاتصال ثم حاول مجددًا.";
        return "ابدأ بإضافة خطوط بمقاسات حقيقية. عند إغلاق الحدود سيتعرف النظام على الشكل تلقائيًا.";
    }

    function renderPanel(controller) {
        const analysis = analyze(controller);
        controller.lastAnalysis = stateCopy(analysis);
        const [badgeText, badgeClass] = labelFor(analysis);
        controller.card.classList.toggle("is-visible", analysis.exactLineCount > 0);
        controller.badge.className = `dco-exact-shape-badge${badgeClass ? ` ${badgeClass}` : ""}`;
        controller.badge.textContent = badgeText;
        controller.status.innerHTML = statusText(controller, analysis);
        controller.linesValue.textContent = String(analysis.exactLineCount);
        controller.perimeterValue.textContent = analysis.exactLineCount ? `${lineModel.rounded(analysis.perimeterCm, 2)} سم` : "—";
        controller.areaValue.textContent = analysis.closed ? `${lineModel.rounded(analysis.areaCm2 / 10000, 3)} م²` : "—";
        controller.closeButton.hidden = !analysis.canAutoClose;

        const existingForeign = Boolean(
            controller.row.special_shape_geometry_json
            && !chainModel.isGeneratedGeometry(controller.row.special_shape_geometry_json)
        );
        controller.note.className = "dco-exact-shape-note";
        if (existingForeign && analysis.geometryValid) {
            controller.note.classList.add("is-warning");
            controller.note.textContent = "يوجد شكل هندسي دقيق محفوظ من مصدر آخر؛ لن يستبدله النظام تلقائيًا عند حفظ رسم الخطوط.";
        } else if (analysis.geometryValid) {
            controller.note.classList.add("is-success");
            controller.note.textContent = "جاهز: حفظ الرسم سيحفظ نفس الحدود كـ Polygon دقيق بالسنتيمتر.";
        } else if (chainModel.isGeneratedGeometry(controller.row.special_shape_geometry_json)) {
            controller.note.classList.add("is-warning");
            controller.note.textContent = "الشكل الدقيق السابق مولّد من هذه الخطوط. إذا حفظت المسار وهو غير صالح سيُزال المسار الدقيق القديم كي لا يبقى DXF قديمًا.";
        } else {
            controller.note.textContent = "التحويل الهندسي لا يعتمد على شكل الشاشة؛ يعتمد على إحداثيات CM المخزنة في الخطوط الدقيقة.";
        }
        renderOverlay(controller, analysis);
        return analysis;
    }

    function renderOverlay(controller, analysis) {
        if (controller.rendering) return;
        controller.rendering = true;
        if (controller.observer) controller.observer.disconnect();
        try {
            const previous = controller.svg.querySelector(".dco-exact-shape-chain-overlay");
            if (previous) previous.remove();
            if (!analysis || analysis.state !== "open" || analysis.openEnds.length !== 2) return;
            const transform = lineModel.createTransform(
                Number(controller.row.width_cm) || 0,
                Number(controller.row.length_cm) || 0
            );
            if (!transform) return;
            const first = lineModel.cmToCanvas(transform, analysis.openEnds[0]);
            const second = lineModel.cmToCanvas(transform, analysis.openEnds[1]);
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-exact-shape-chain-overlay");
            group.setAttribute("pointer-events", "none");
            const line = document.createElementNS(SVG_NS, "line");
            line.setAttribute("class", "dco-exact-close-preview");
            line.setAttribute("x1", String(first[0]));
            line.setAttribute("y1", String(first[1]));
            line.setAttribute("x2", String(second[0]));
            line.setAttribute("y2", String(second[1]));
            group.appendChild(line);
            [first, second].forEach(next => {
                const circle = document.createElementNS(SVG_NS, "circle");
                circle.setAttribute("class", "dco-exact-close-point");
                circle.setAttribute("cx", String(next[0]));
                circle.setAttribute("cy", String(next[1]));
                circle.setAttribute("r", "5");
                group.appendChild(circle);
            });
            const label = document.createElementNS(SVG_NS, "text");
            label.setAttribute("class", "dco-exact-close-label");
            label.setAttribute("x", String((first[0] + second[0]) / 2));
            label.setAttribute("y", String((first[1] + second[1]) / 2 - 8));
            label.textContent = `إغلاق ${lineModel.rounded(analysis.closeGapCm, 2)} سم`;
            group.appendChild(label);
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
            if (controller.observer) controller.observer.observe(controller.svg, { childList: true });
        }
    }

    function refreshEditor(controller) {
        const select = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (select) select.click();
    }

    function autoClose(controller) {
        const state = liveState(controller);
        const analysis = analyze(controller);
        if (!state || !analysis.canAutoClose) return false;
        const transform = lineModel.createTransform(
            Number(controller.row.width_cm) || 0,
            Number(controller.row.length_cm) || 0
        );
        closeSequence += 1;
        const result = chainModel.createClosingElement(analysis, transform, {
            id: `exact-close-${Date.now()}-${closeSequence}`,
            color: state.color || "#172033",
        });
        if (!result.valid || !result.element) return false;
        const transition = history.addElement(state, result.element);
        if (!transition || !transition.changed) return false;
        Object.assign(state, transition.patch);
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        window.setTimeout(() => renderPanel(controller), 0);
        const notice = controller.root.querySelector(".dco-sketch-notice-text");
        if (notice) notice.textContent = `تم إغلاق المسار بخط دقيق طوله ${lineModel.rounded(analysis.closeGapCm, 2)} سم.`;
        if (window.frappe) frappe.show_alert({ message: "تم إغلاق حدود الشكل", indicator: "green" }, 3);
        return true;
    }

    function syncGeometryAfterSave(controller) {
        const analysis = controller.lastAnalysis || analyze(controller);
        const row = controller.row;
        const currentRaw = String(row.special_shape_geometry_json || "");
        const generatedBefore = chainModel.isGeneratedGeometry(currentRaw);
        const foreignGeometry = Boolean(currentRaw && !generatedBefore);

        if (analysis.geometryValid) {
            if (foreignGeometry) {
                if (window.frappe) frappe.show_alert({
                    message: "تم حفظ الرسم. أُبقي الشكل الهندسي الدقيق الموجود لأنه من مصدر آخر.",
                    indicator: "orange",
                }, 5);
                return;
            }
            const serialized = chainModel.serializeGenerated(analysis);
            if (serialized && serialized !== currentRaw) {
                row.special_shape_geometry_json = serialized;
                row.special_shape_status = "Documented";
                controller.frm.dirty();
            }
            if (window.frappe) frappe.show_alert({
                message: `تم اعتماد شكل هندسي مغلق · المحيط ${lineModel.rounded(analysis.perimeterCm, 2)} سم`,
                indicator: "green",
            }, 5);
            return;
        }

        if (generatedBefore) {
            row.special_shape_geometry_json = "";
            controller.frm.dirty();
            if (window.frappe) frappe.show_alert({
                message: "أُزيل المسار الهندسي الدقيق السابق لأن حدود الخطوط المحفوظة لم تعد مغلقة وصالحة.",
                indicator: "orange",
            }, 6);
        }
    }

    function cardHtml() {
        return `<section class="dco-exact-shape-card" aria-label="حالة الشكل الهندسي الدقيق">
            <div class="dco-exact-shape-head"><strong>الشكل الهندسي</strong><span class="dco-exact-shape-badge"></span></div>
            <div class="dco-exact-shape-body">
                <div class="dco-exact-shape-status"></div>
                <div class="dco-exact-shape-stats">
                    <div class="dco-exact-shape-stat"><b data-shape-lines>0</b><span>أضلاع دقيقة</span></div>
                    <div class="dco-exact-shape-stat"><b data-shape-perimeter>—</b><span>المحيط</span></div>
                    <div class="dco-exact-shape-stat"><b data-shape-area>—</b><span>المساحة</span></div>
                </div>
                <button type="button" class="dco-exact-shape-action" data-shape-auto-close hidden>إغلاق المسار بخط دقيق</button>
                <div class="dco-exact-shape-note"></div>
            </div>
        </section>`;
    }

    function mount(frm, row) {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoExactShapeChain === "1") return Boolean(root);
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        if (!svg || !paperWrap) return false;
        root.dataset.dcoExactShapeChain = "1";
        paperWrap.insertAdjacentHTML("beforeend", cardHtml());
        const card = paperWrap.querySelector(".dco-exact-shape-card");
        const controller = {
            frm,
            row,
            modal,
            root,
            svg,
            card,
            badge: card.querySelector(".dco-exact-shape-badge"),
            status: card.querySelector(".dco-exact-shape-status"),
            linesValue: card.querySelector("[data-shape-lines]"),
            perimeterValue: card.querySelector("[data-shape-perimeter]"),
            areaValue: card.querySelector("[data-shape-area]"),
            closeButton: card.querySelector("[data-shape-auto-close]"),
            note: card.querySelector(".dco-exact-shape-note"),
            lastAnalysis: null,
            saveRequested: false,
            rendering: false,
            observer: null,
        };
        controller.closeButton.addEventListener("click", () => autoClose(controller));

        modal.addEventListener("click", event => {
            const target = event.target && event.target.closest
                ? event.target.closest(".btn-modal-primary,.modal-footer .btn-primary")
                : null;
            if (target) controller.saveRequested = true;
        }, true);

        controller.observer = new MutationObserver(() => {
            if (controller.rendering) return;
            window.setTimeout(() => renderPanel(controller), 0);
        });
        controller.observer.observe(svg, { childList: true });
        renderPanel(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-exact-shape-chain", () => {
                if (controller.observer) controller.observer.disconnect();
                if (controller.saveRequested) syncGeometryAfterSave(controller);
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
        __exactShapeChainIntegrated: true,
        open,
        view,
    });
    window.AlmdinaExactShapeChainUX = Object.freeze({ installStyles, mount, model: chainModel });
})();
