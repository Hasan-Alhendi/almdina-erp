(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    const history = window.AlmdinaSketchHistory;
    const lineModel = window.AlmdinaExactLineModel;
    const arcModel = window.AlmdinaExactArcModel;
    if (!baseEditor || !history || !lineModel || !arcModel) {
        console.error("Exact-arc dependencies must load before exact-arc UX");
        return;
    }
    if (baseEditor.__exactArcIntegrated) return;

    const STYLE_ID = "dco-exact-arc-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const MOUNT_RETRIES = 14;

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-exact-arc-card{position:absolute;z-index:10;left:20px;bottom:20px;width:292px;display:none;direction:rtl;border:1px solid #cbd9e4;border-radius:14px;background:rgba(255,255,255,.985);box-shadow:0 12px 36px rgba(15,23,42,.15);backdrop-filter:blur(8px);overflow:hidden}
            .dco-exact-arc-card.is-visible{display:block}
            .dco-exact-arc-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 11px;background:#f4f9fd;border-bottom:1px solid #e3ebf1}
            .dco-exact-arc-head strong{font-size:10px;color:#163d59}.dco-exact-arc-badge{padding:4px 7px;border-radius:999px;background:#dff1ff;color:#0e639d;font-size:7.5px;font-weight:900}
            .dco-exact-arc-body{padding:10px}.dco-exact-arc-status{margin-bottom:8px;padding:7px 8px;border-radius:9px;background:#f8fafc;color:#536979;font-size:8px;line-height:1.55}.dco-exact-arc-status.is-error{background:#fff1ef;color:#a33126}.dco-exact-arc-status.is-success{background:#edf9f3;color:#12633f}
            .dco-exact-arc-field label{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px;color:#64748b;font-size:7.5px;font-weight:900}.dco-exact-arc-field label b{color:#23465f}
            .dco-exact-arc-shell{display:flex;align-items:center;border:1px solid #d5dfe6;border-radius:9px;background:#fff;overflow:hidden}.dco-exact-arc-shell input{min-width:0;width:100%;height:37px;border:0!important;box-shadow:none!important;padding:5px 7px;text-align:center;font-size:13px;font-weight:900;color:#172033}.dco-exact-arc-shell span{padding:0 7px;border-right:1px solid #e4eaee;color:#64748b;font-size:7.5px}
            .dco-exact-arc-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin:8px 0}.dco-exact-arc-stat{padding:6px 4px;border-radius:8px;background:#f6f9fb;text-align:center}.dco-exact-arc-stat b{display:block;color:#24465c;font-size:9px;font-variant-numeric:tabular-nums}.dco-exact-arc-stat span{font-size:6.5px;color:#718096}
            .dco-exact-arc-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px}.dco-exact-arc-actions button{min-height:33px;border:1px solid #d6e0e7;border-radius:9px;background:#fff;color:#334155;cursor:pointer;font-size:7.8px;font-weight:900}.dco-exact-arc-actions button:hover{border-color:#2490ef;color:#0e639d;background:#f4faff}.dco-exact-arc-apply{grid-column:1/-1!important;background:#1769aa!important;border-color:#1769aa!important;color:#fff!important}.dco-exact-arc-apply:hover{background:#0f5f92!important;color:#fff!important}.dco-exact-arc-straight[hidden]{display:none}
            .dco-exact-arc-note{margin-top:7px;padding:6px 7px;border-radius:8px;background:#f8fafc;color:#6b7b87;font-size:7px;line-height:1.5}
            .dco-exact-arc-path{fill:none;stroke:#0f78bd;stroke-width:3;stroke-linecap:round;vector-effect:non-scaling-stroke;pointer-events:none}.dco-exact-arc-path.is-selected{stroke:#7c3aed;stroke-width:3.4}.dco-exact-arc-preview{fill:none;stroke:#0ea5a8;stroke-width:3;stroke-dasharray:8 6;stroke-linecap:round;vector-effect:non-scaling-stroke;pointer-events:none}.dco-exact-arc-apex{fill:#fff;stroke:#0ea5a8;stroke-width:2.2;vector-effect:non-scaling-stroke;pointer-events:none}.dco-exact-arc-label{fill:#0f6670;font-family:Tahoma,Arial,sans-serif;font-size:10px;font-weight:900;text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:4;stroke-linejoin:round;pointer-events:none}
            @media(max-width:700px){.dco-exact-arc-card{left:12px;right:12px;bottom:12px;width:auto;max-height:calc(100vh - 110px);overflow:auto}}
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

    function selectedElement(controller) {
        const state = liveState(controller);
        if (!state || state.tool !== "select") return null;
        return (state.elements || []).find(element => String(element && element.id) === String(state.selectedId || "")) || null;
    }

    function selectedKind(controller) {
        const element = selectedElement(controller);
        if (!element) return { element: null, kind: "" };
        if (arcModel.arcMeta(element)) return { element, kind: "arc" };
        if (lineModel.exactMeta(element)) return { element, kind: "line" };
        return { element: null, kind: "" };
    }

    function transformFor(controller) {
        return lineModel.createTransform(
            Number(controller.row.width_cm) || 0,
            Number(controller.row.length_cm) || 0
        );
    }

    function setStatus(controller, text, type = "") {
        controller.status.className = `dco-exact-arc-status${type ? ` is-${type}` : ""}`;
        controller.status.textContent = text;
    }

    function refreshEditor(controller) {
        const button = controller.root.querySelector('.dco-sketch-tool[data-tool="select"]');
        if (button) button.click();
        if (history.activateState) {
            const state = history.getActiveState ? history.getActiveState() : null;
            if (state) history.activateState(state);
        }
    }

    function hydrate(controller, target) {
        const transform = transformFor(controller);
        if (!target.element || !transform) return;
        if (target.kind === "line") {
            const meta = lineModel.exactMeta(target.element);
            const limits = arcModel.limits(meta.start_cm, meta.end_cm);
            controller.rise.value = String(limits.defaultRise);
            controller.side = 1;
            controller.title.textContent = "تحويل الضلع إلى قوس";
            controller.apply.textContent = "تحويل إلى قوس دائري دقيق";
            controller.straight.hidden = true;
            setStatus(controller, "حدّد ارتفاع القوس بالسنتيمتر. نقطتا بداية ونهاية الضلع ستبقيان ثابتتين.");
        } else {
            const meta = arcModel.arcMeta(target.element);
            controller.rise.value = String(meta.rise_cm);
            controller.side = arcModel.normalizeSide(meta.side);
            controller.title.textContent = "خصائص القوس الدقيق";
            controller.apply.textContent = "تطبيق تعديل القوس";
            controller.straight.hidden = false;
            setStatus(controller, "القوس دائري محسوب هندسيًا. عدّل الارتفاع أو اعكس الجهة ثم طبّق.");
        }
        renderPreview(controller);
    }

    function previewResult(controller) {
        const target = selectedKind(controller);
        const transform = transformFor(controller);
        if (!target.element || !transform) return null;
        return target.kind === "line"
            ? arcModel.fromLine(target.element, transform, controller.rise.value, controller.side)
            : arcModel.rebuild(target.element, transform, { riseCm: controller.rise.value, side: controller.side });
    }

    function updateStats(controller, result) {
        if (!result || !result.valid || !result.geometry) {
            controller.radius.textContent = "—";
            controller.chord.textContent = "—";
            controller.arcLength.textContent = "—";
            return;
        }
        controller.radius.textContent = `${lineModel.rounded(result.geometry.radius, 2)} سم`;
        controller.chord.textContent = `${lineModel.rounded(result.geometry.frame.length, 2)} سم`;
        controller.arcLength.textContent = `${lineModel.rounded(result.geometry.arcLength, 2)} سم`;
    }

    function appendPath(group, element, transform, className) {
        const pathData = arcModel.svgArcPath(element, transform);
        if (!pathData) return;
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("class", className);
        path.setAttribute("d", pathData);
        group.appendChild(path);
    }

    function renderOverlay(controller, preview = null) {
        if (controller.rendering) return;
        controller.rendering = true;
        if (controller.observer) controller.observer.disconnect();
        try {
            const previous = controller.svg.querySelector(".dco-exact-arc-overlay");
            if (previous) previous.remove();
            const state = liveState(controller);
            const transform = transformFor(controller);
            if (!state || !transform) return;
            const arcs = (state.elements || []).filter(element => arcModel.arcMeta(element));
            if (!arcs.length && !(preview && preview.valid)) return;
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "dco-exact-arc-overlay");
            group.setAttribute("pointer-events", "none");
            arcs.forEach(element => appendPath(
                group,
                element,
                transform,
                `dco-exact-arc-path${String(element.id) === String(state.selectedId || "") ? " is-selected" : ""}`
            ));
            if (preview && preview.valid && preview.element) {
                appendPath(group, preview.element, transform, "dco-exact-arc-preview");
                const meta = arcModel.arcMeta(preview.element);
                const apex = meta && lineModel.cmToCanvas(transform, meta.apex_cm);
                if (apex) {
                    const circle = document.createElementNS(SVG_NS, "circle");
                    circle.setAttribute("class", "dco-exact-arc-apex");
                    circle.setAttribute("cx", String(apex[0]));
                    circle.setAttribute("cy", String(apex[1]));
                    circle.setAttribute("r", "5");
                    group.appendChild(circle);
                    const label = document.createElementNS(SVG_NS, "text");
                    label.setAttribute("class", "dco-exact-arc-label");
                    label.setAttribute("x", String(apex[0]));
                    label.setAttribute("y", String(apex[1] - 10));
                    label.textContent = `ارتفاع ${lineModel.rounded(meta.rise_cm, 2)} سم`;
                    group.appendChild(label);
                }
            }
            controller.svg.appendChild(group);
        } finally {
            controller.rendering = false;
            if (controller.observer) controller.observer.observe(controller.svg, { childList: true });
        }
    }

    function renderPreview(controller) {
        const result = previewResult(controller);
        updateStats(controller, result);
        if (result && !result.valid) {
            const target = selectedKind(controller);
            const meta = target.kind === "line"
                ? lineModel.exactMeta(target.element)
                : arcModel.arcMeta(target.element);
            const allowed = meta ? arcModel.limits(meta.start_cm, meta.end_cm) : null;
            if (result.reason === "arc-outside-piece") {
                setStatus(controller, "القوس بهذه الجهة أو بهذا الارتفاع يخرج خارج حدود الدرفة. قلّل الارتفاع أو اعكس الجهة.", "error");
            } else if (allowed) {
                setStatus(controller, `ارتفاع القوس يجب أن يكون بين ${allowed.minimum} و ${lineModel.rounded(allowed.maximum, 2)} سم لهذا الضلع.`, "error");
            }
        }
        renderOverlay(controller, result && result.valid ? result : null);
        return result;
    }

    function snapshotReplace(controller, nextElement, message) {
        const state = liveState(controller);
        const selected = selectedElement(controller);
        if (!state || !selected || !nextElement) return false;
        const index = (state.elements || []).findIndex(element => String(element && element.id) === String(selected.id));
        if (index < 0) return false;
        const before = JSON.parse(JSON.stringify(state.elements));
        const transition = history.snapshot(state, before);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        const next = before.slice();
        next[index] = nextElement;
        state.elements = next;
        state.selectedId = String(nextElement.id);
        state.hasChanges = true;
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        controller.selectedId = "";
        window.setTimeout(() => {
            syncVisibility(controller);
            setStatus(controller, message, "success");
        }, 0);
        return true;
    }

    function apply(controller) {
        const target = selectedKind(controller);
        const result = renderPreview(controller);
        if (!target.element || !result || !result.valid || !result.element) return false;
        const meta = arcModel.arcMeta(result.element);
        return snapshotReplace(
            controller,
            result.element,
            `تم حفظ قوس دائري دقيق: ارتفاع ${lineModel.rounded(meta.rise_cm, 2)} سم · نصف قطر ${lineModel.rounded(meta.radius_cm, 2)} سم.`
        );
    }

    function flip(controller) {
        controller.side = -arcModel.normalizeSide(controller.side);
        renderPreview(controller);
        controller.rise.focus();
    }

    function straighten(controller) {
        const target = selectedKind(controller);
        if (target.kind !== "arc") return false;
        const result = arcModel.toLine(target.element, transformFor(controller));
        if (!result.valid || !result.element) return false;
        return snapshotReplace(controller, result.element, "تمت إعادة القوس إلى ضلع مستقيم مع الحفاظ على نقطتي البداية والنهاية.");
    }

    function syncVisibility(controller) {
        const creationActive = Boolean(controller.root.querySelector(".dco-exact-line-tool.is-active"));
        const target = creationActive ? { element: null, kind: "" } : selectedKind(controller);
        const id = target.element ? `${target.kind}:${target.element.id}` : "";
        controller.card.classList.toggle("is-visible", Boolean(target.element));
        if (!target.element) {
            controller.selectedId = "";
            renderOverlay(controller, null);
            return;
        }
        if (controller.selectedId !== id) {
            controller.selectedId = id;
            hydrate(controller, target);
        } else {
            renderOverlay(controller, null);
        }
    }

    function selectArcWithoutDragging(controller, event) {
        if (controller.root.querySelector(".dco-exact-line-tool.is-active")) return false;
        const targetNode = event.target && event.target.closest ? event.target.closest("[data-element-id]") : null;
        if (!targetNode) return false;
        const state = liveState(controller);
        if (!state || state.tool !== "select") return false;
        const element = (state.elements || []).find(item => String(item && item.id) === String(targetNode.dataset.elementId || ""));
        if (!element || !arcModel.arcMeta(element)) return false;
        const transition = history.selectElement(state, element.id);
        if (transition && transition.changed) Object.assign(state, transition.patch);
        if (history.activateState) history.activateState(state);
        refreshEditor(controller);
        controller.selectedId = "";
        window.setTimeout(() => syncVisibility(controller), 0);
        event.preventDefault();
        event.stopImmediatePropagation();
        return true;
    }

    function cardHtml() {
        return `<section class="dco-exact-arc-card" aria-label="القوس الدائري الدقيق">
            <div class="dco-exact-arc-head"><strong data-arc-title>القوس الدقيق</strong><span class="dco-exact-arc-badge">CIRCLE · CM</span></div>
            <div class="dco-exact-arc-body">
                <div class="dco-exact-arc-status"></div>
                <div class="dco-exact-arc-field"><label><span>ارتفاع القوس</span><b>سنتيمتر حقيقي</b></label><div class="dco-exact-arc-shell"><input type="number" min="0.2" step="0.1" inputmode="decimal" data-arc-rise><span>سم</span></div></div>
                <div class="dco-exact-arc-stats">
                    <div class="dco-exact-arc-stat"><b data-arc-chord>—</b><span>الوتر</span></div>
                    <div class="dco-exact-arc-stat"><b data-arc-radius>—</b><span>نصف القطر</span></div>
                    <div class="dco-exact-arc-stat"><b data-arc-length>—</b><span>طول القوس</span></div>
                </div>
                <div class="dco-exact-arc-actions">
                    <button type="button" data-arc-flip>⇄ عكس جهة القوس</button>
                    <button type="button" class="dco-exact-arc-straight" data-arc-straight hidden>— إعادة لمستقيم</button>
                    <button type="button" class="dco-exact-arc-apply" data-arc-apply>تطبيق القوس الدقيق</button>
                </div>
                <div class="dco-exact-arc-note">هذا قوس دائري بمعادلة هندسية ونصف قطر حقيقي، وليس Bézier. التمثيل النقطي داخل الرسم للعرض فقط؛ بيانات القوس الدقيقة محفوظة مستقلة.</div>
            </div>
        </section>`;
    }

    function mount(frm, row) {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoExactArc === "1") return Boolean(root);
        const svg = root.querySelector(".dco-sketch-paper");
        const paperWrap = root.querySelector(".dco-sketch-paper-wrap");
        if (!svg || !paperWrap) return false;
        root.dataset.dcoExactArc = "1";
        paperWrap.insertAdjacentHTML("beforeend", cardHtml());
        const card = paperWrap.querySelector(".dco-exact-arc-card");
        const controller = {
            frm,
            row,
            modal,
            root,
            svg,
            card,
            title: card.querySelector("[data-arc-title]"),
            status: card.querySelector(".dco-exact-arc-status"),
            rise: card.querySelector("[data-arc-rise]"),
            chord: card.querySelector("[data-arc-chord]"),
            radius: card.querySelector("[data-arc-radius]"),
            arcLength: card.querySelector("[data-arc-length]"),
            apply: card.querySelector("[data-arc-apply]"),
            straight: card.querySelector("[data-arc-straight]"),
            selectedId: "",
            side: 1,
            rendering: false,
            observer: null,
        };

        controller.rise.addEventListener("input", () => renderPreview(controller));
        controller.rise.addEventListener("keydown", event => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            event.stopPropagation();
            apply(controller);
        });
        card.querySelector("[data-arc-flip]").addEventListener("click", () => flip(controller));
        controller.apply.addEventListener("click", () => apply(controller));
        controller.straight.addEventListener("click", () => straighten(controller));
        svg.addEventListener("pointerdown", event => selectArcWithoutDragging(controller, event), true);

        controller.observer = new MutationObserver(() => {
            if (controller.rendering) return;
            window.setTimeout(() => syncVisibility(controller), 0);
        });
        controller.observer.observe(svg, { childList: true, subtree: true });
        syncVisibility(controller);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-exact-arc", () => {
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
        __exactArcIntegrated: true,
        open,
        view,
    });
    window.AlmdinaExactArcUX = Object.freeze({ installStyles, mount, model: arcModel });
})();
