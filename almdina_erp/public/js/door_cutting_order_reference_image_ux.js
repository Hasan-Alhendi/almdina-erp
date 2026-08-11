(() => {
    "use strict";

    const contract = window.AlmdinaReferenceImageContract;
    const acquisition = window.AlmdinaReferenceImageAcquisition;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (!contract || !acquisition || !baseEditor) {
        console.error("Reference image modules must load after the special-shape editor");
        return;
    }
    if (baseEditor.__referenceImageIntegrated) return;

    const STYLE_ID = "dco-reference-image-ux-css";
    const SVG_NS = "http://www.w3.org/2000/svg";
    const XLINK_NS = "http://www.w3.org/1999/xlink";
    const MOUNT_RETRIES = 14;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-reference-panel{direction:rtl;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 12px;border:1px solid #d9e2e8;border-radius:13px;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.03)}
            .dco-reference-panel.is-dragging{border-color:#2490ef;box-shadow:0 0 0 3px rgba(36,144,239,.12);background:#f5fbff}
            .dco-reference-icon{display:grid;place-items:center;width:42px;height:42px;border-radius:11px;background:#eef6fc;color:#1669a6;font-size:20px;flex:0 0 auto}
            .dco-reference-copy{min-width:170px;flex:1 1 210px}
            .dco-reference-title{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:900;color:#172033}
            .dco-reference-badge{display:inline-flex;align-items:center;gap:4px;padding:3px 7px;border-radius:999px;background:#e9f8ef;color:#12633f;font-size:9px;font-weight:900}
            .dco-reference-hint{margin-top:3px;color:#687785;font-size:9px;line-height:1.6}
            .dco-reference-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap;flex:1 1 360px}
            .dco-reference-button{min-height:36px;border:1px solid #d6dee5;border-radius:9px;background:#fff;color:#294457;padding:6px 10px;cursor:pointer;font-size:10px;font-weight:900;white-space:nowrap}
            .dco-reference-button:hover:not(:disabled){border-color:#2490ef;color:#1669a6;background:#f7fbff}
            .dco-reference-button.is-primary{border-color:#2490ef;background:#2490ef;color:#fff}
            .dco-reference-button.is-primary:hover:not(:disabled){background:#1674c5;color:#fff}
            .dco-reference-button.is-danger{color:#b42318;border-color:#efc2bd}
            .dco-reference-button:disabled{opacity:.48;cursor:wait}
            .dco-reference-opacity{display:flex;align-items:center;gap:6px;min-width:155px;padding:0 4px}
            .dco-reference-opacity label{font-size:9px;font-weight:800;color:#64748b;white-space:nowrap}
            .dco-reference-opacity input{width:92px;accent-color:#2490ef;cursor:pointer}
            .dco-reference-opacity output{min-width:30px;font-size:9px;font-weight:900;color:#334e60;text-align:center}
            .dco-reference-file{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#4d6474;font-size:9px}
            .dco-reference-busy{display:none;align-items:center;gap:6px;color:#1669a6;font-size:9px;font-weight:900}
            .dco-reference-panel.is-busy .dco-reference-busy{display:flex}
            .dco-reference-panel.is-busy .dco-reference-actions{opacity:.58;pointer-events:none}
            .dco-reference-spinner{width:13px;height:13px;border:2px solid #c9dfef;border-top-color:#1674c5;border-radius:50%;animation:dco-reference-spin .75s linear infinite}
            .dco-reference-image-layer{pointer-events:none;user-select:none}
            @keyframes dco-reference-spin{to{transform:rotate(360deg)}}
            @media(max-width:780px){.dco-reference-panel{align-items:flex-start}.dco-reference-icon{width:36px;height:36px}.dco-reference-actions{justify-content:flex-start;flex-basis:100%}.dco-reference-opacity{min-width:145px}.dco-reference-file{max-width:170px}}
        `;
        document.head.appendChild(style);
    }

    function referencePanelHtml(reference, readOnly) {
        const hasReference = Boolean(reference);
        const percent = Math.round((reference ? reference.opacity : contract.DEFAULT_OPACITY) * 100);
        const sourceLabel = reference && reference.source === "scanner" ? "مسح ضوئي" : "ملف";
        return `
            <div class="dco-reference-icon" aria-hidden="true">▧</div>
            <div class="dco-reference-copy">
                <div class="dco-reference-title">
                    <span>صورة الورقة كمرجع</span>
                    ${hasReference ? `<span class="dco-reference-badge">✓ ${sourceLabel} مضاف</span>` : ""}
                </div>
                <div class="dco-reference-hint">
                    ${hasReference
                        ? "تظهر الصورة خلف الرسم فقط، ولا تتحول إلى مسار قص أو DXF."
                        : "ارسم الشكل على الورقة ثم ارفع الصورة، أو ضع الورقة في سكانر الطابعة وابدأ المسح مباشرة."}
                </div>
                ${hasReference ? `<div class="dco-reference-file" title="${esc(reference.file_name)}">${esc(reference.file_name)}</div>` : ""}
                <div class="dco-reference-busy"><span class="dco-reference-spinner"></span><span class="dco-reference-busy-text">جارٍ تجهيز المرجع…</span></div>
            </div>
            <div class="dco-reference-actions">
                ${!readOnly ? `
                    <button type="button" class="dco-reference-button ${hasReference ? "" : "is-primary"}" data-reference-upload>▣ ${hasReference ? "استبدال من الملفات" : "رفع من الملفات"}</button>
                    <button type="button" class="dco-reference-button ${hasReference ? "" : "is-primary"}" data-reference-scan>⌁ مسح من الطابعة</button>
                ` : ""}
                ${hasReference ? `
                    <div class="dco-reference-opacity">
                        <label for="dco-reference-opacity">وضوح المرجع</label>
                        <input id="dco-reference-opacity" type="range" min="${Math.round(contract.MIN_OPACITY * 100)}" max="${Math.round(contract.MAX_OPACITY * 100)}" step="1" value="${percent}" data-reference-opacity ${readOnly ? "disabled" : ""}>
                        <output>${percent}%</output>
                    </div>
                    <button type="button" class="dco-reference-button" data-reference-toggle>${reference.visible ? "◉ إخفاء" : "◎ إظهار"}</button>
                    <button type="button" class="dco-reference-button" data-reference-open>↗ فتح الأصل</button>
                    ${!readOnly ? `<button type="button" class="dco-reference-button is-danger" data-reference-remove>حذف المرجع</button>` : ""}
                ` : ""}
            </div>`;
    }

    function visibleSpecialShapeModal() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        return modals.reverse().find(modal =>
            modal.classList.contains("show")
            || modal.style.display === "block"
            || modal.getAttribute("aria-hidden") !== "true"
        ) || null;
    }

    function directCanvasRect(svg) {
        return Array.from(svg.children || []).find(child =>
            String(child.tagName || "").toLowerCase() === "rect"
            && child.getAttribute("x") === "0"
            && child.getAttribute("y") === "0"
        ) || null;
    }

    function createOverlay(svg) {
        const image = document.createElementNS(SVG_NS, "image");
        image.setAttribute("class", "dco-reference-image-layer");
        image.setAttribute("x", "0");
        image.setAttribute("y", "0");
        image.setAttribute("width", String(contract.DEFAULT_CANVAS.width));
        image.setAttribute("height", String(contract.DEFAULT_CANVAS.height));
        image.setAttribute("preserveAspectRatio", "xMidYMid meet");
        image.setAttribute("pointer-events", "none");
        const background = directCanvasRect(svg);
        if (background && background.parentNode === svg) {
            svg.insertBefore(image, background.nextSibling);
        } else {
            svg.insertBefore(image, svg.firstChild || null);
        }
        return image;
    }

    function applyOverlay(controller) {
        if (controller.renderingOverlay) return;
        controller.renderingOverlay = true;
        try {
            let layer = controller.svg.querySelector(".dco-reference-image-layer");
            const reference = controller.reference;
            if (!reference) {
                if (layer) layer.remove();
                return;
            }
            if (!layer) layer = createOverlay(controller.svg);
            layer.setAttribute("href", reference.file_url);
            try { layer.setAttributeNS(XLINK_NS, "href", reference.file_url); } catch (error) { /* SVG2 href is enough */ }
            layer.setAttribute("opacity", String(reference.opacity));
            layer.setAttribute("display", reference.visible ? "" : "none");
        } finally {
            controller.renderingOverlay = false;
        }
    }

    function renderPanel(controller) {
        controller.panel.innerHTML = referencePanelHtml(controller.reference, controller.readOnly);
        applyOverlay(controller);
    }

    function setBusy(controller, busy, text = "جارٍ تجهيز المرجع…") {
        controller.panel.classList.toggle("is-busy", Boolean(busy));
        controller.panel.querySelectorAll("button,input").forEach(control => {
            control.disabled = Boolean(busy) || (controller.readOnly && control.matches("input"));
        });
        const label = controller.panel.querySelector(".dco-reference-busy-text");
        if (label) label.textContent = text;
    }

    function preserveReferenceOnRow(controller) {
        contract.writeToRow(controller.row, controller.reference);
        if (
            controller.row.piece_type === "Special"
            && !controller.row.special_shape_geometry_json
            && !contract.hasDrawingElements(controller.row)
        ) {
            controller.row.special_shape_status = "Needs Documentation";
        }
        if (controller.frm && typeof controller.frm.dirty === "function") controller.frm.dirty();
    }

    function setReference(controller, reference) {
        controller.reference = contract.normalize(reference);
        preserveReferenceOnRow(controller);
        renderPanel(controller);
    }

    function friendlyError(error) {
        if (error && error.code === "scanner-bridge-unavailable") {
            frappe.msgprint({
                title: "الماسح الضوئي غير متصل بالنظام",
                message: "خيار المسح جاهز، لكن هذا اللابتوب يحتاج تشغيل <b>Almdina Scanner Bridge</b> مرة واحدة حتى يستطيع المتصفح التواصل مع سكانر الطابعة. يمكنك الآن استخدام «رفع من الملفات» دون أي إعداد إضافي.",
                indicator: "orange",
            });
            return;
        }
        if (error && error.code === "scanner-cancelled") {
            frappe.show_alert({ message: error.message, indicator: "blue" });
            return;
        }
        frappe.msgprint({
            title: "تعذر تجهيز صورة المرجع",
            message: esc(error && error.message || "حدث خطأ غير متوقع."),
            indicator: "red",
        });
    }

    async function acquireAndUpload(controller, source, file = null) {
        setBusy(
            controller,
            true,
            source === "scanner" ? "بانتظار المسح من الطابعة…" : "جارٍ رفع صورة المرجع…"
        );
        try {
            const selected = file || (source === "scanner"
                ? await acquisition.scanFromPrinter()
                : await acquisition.pickImageFile());
            if (!selected) return;
            acquisition.validateImage(selected);
            setBusy(controller, true, "جارٍ حفظ صورة المرجع داخل الطلب…");
            const uploaded = await acquisition.uploadImage(selected, controller.frm, source);
            setReference(controller, {
                ...uploaded,
                opacity: controller.reference
                    ? controller.reference.opacity
                    : contract.DEFAULT_OPACITY,
                visible: true,
            });
            frappe.show_alert({
                message: source === "scanner"
                    ? "تم مسح الورقة وإضافتها كمرجع خلف الرسم."
                    : "تم رفع الصورة وإضافتها كمرجع خلف الرسم.",
                indicator: "green",
            }, 5);
        } catch (error) {
            friendlyError(error);
        } finally {
            setBusy(controller, false);
        }
    }

    function bindPanel(controller) {
        controller.panel.addEventListener("click", event => {
            const upload = event.target.closest && event.target.closest("[data-reference-upload]");
            if (upload && !controller.readOnly) {
                acquireAndUpload(controller, "file");
                return;
            }
            const scan = event.target.closest && event.target.closest("[data-reference-scan]");
            if (scan && !controller.readOnly) {
                acquireAndUpload(controller, "scanner");
                return;
            }
            const toggle = event.target.closest && event.target.closest("[data-reference-toggle]");
            if (toggle && controller.reference) {
                const next = contract.normalize({
                    ...controller.reference,
                    visible: !controller.reference.visible,
                });
                if (controller.readOnly) {
                    controller.reference = next;
                    renderPanel(controller);
                } else {
                    setReference(controller, next);
                }
                return;
            }
            const open = event.target.closest && event.target.closest("[data-reference-open]");
            if (open && controller.reference) {
                window.open(controller.reference.file_url, "_blank", "noopener,noreferrer");
                return;
            }
            const remove = event.target.closest && event.target.closest("[data-reference-remove]");
            if (remove && controller.reference && !controller.readOnly) {
                frappe.confirm("هل تريد إزالة صورة الورقة من هذه الدرفة؟ لن يتم حذف الرسم الذي رسمته فوقها.", () => {
                    setReference(controller, null);
                    frappe.show_alert({ message: "تمت إزالة صورة المرجع.", indicator: "blue" });
                });
            }
        });
        controller.panel.addEventListener("input", event => {
            const input = event.target.closest && event.target.closest("[data-reference-opacity]");
            if (!input || !controller.reference || controller.readOnly) return;
            const opacity = contract.clampOpacity(Number(input.value) / 100);
            controller.reference = contract.normalize({ ...controller.reference, opacity });
            const output = controller.panel.querySelector(".dco-reference-opacity output");
            if (output) output.textContent = `${Math.round(opacity * 100)}%`;
            applyOverlay(controller);
        });
        controller.panel.addEventListener("change", event => {
            const input = event.target.closest && event.target.closest("[data-reference-opacity]");
            if (!input || !controller.reference || controller.readOnly) return;
            preserveReferenceOnRow(controller);
        });
        if (!controller.readOnly) {
            ["dragenter", "dragover"].forEach(type => controller.panel.addEventListener(type, event => {
                if (!event.dataTransfer || !Array.from(event.dataTransfer.types || []).includes("Files")) return;
                event.preventDefault();
                controller.panel.classList.add("is-dragging");
            }));
            ["dragleave", "drop"].forEach(type => controller.panel.addEventListener(type, event => {
                controller.panel.classList.remove("is-dragging");
                if (type !== "drop") return;
                const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
                if (!file) return;
                event.preventDefault();
                acquireAndUpload(controller, "file", file);
            }));
        }
    }

    function bindLifecycle(controller) {
        controller.observer = new MutationObserver(() => applyOverlay(controller));
        controller.observer.observe(controller.svg, { childList: true });
        const $modal = window.jQuery ? window.jQuery(controller.modal) : null;
        if ($modal) {
            $modal.on("hide.bs.modal.dco-reference-image", () => {
                if (controller.reference) preserveReferenceOnRow(controller);
            });
            $modal.on("hidden.bs.modal.dco-reference-image", () => {
                if (controller.observer) controller.observer.disconnect();
                $modal.off(".dco-reference-image");
            });
        }
    }

    function mount(frm, row, readOnly) {
        installStyles();
        const modal = visibleSpecialShapeModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.querySelector(".dco-reference-panel")) return Boolean(root);
        const center = root.querySelector(".dco-sketch-center");
        const svg = root.querySelector(".dco-sketch-paper");
        if (!center || !svg) return false;

        const panel = document.createElement("section");
        panel.className = "dco-reference-panel";
        panel.setAttribute("aria-label", "صورة الورقة كمرجع");
        center.insertBefore(panel, center.firstChild);
        const controller = {
            frm,
            row,
            modal,
            root,
            svg,
            panel,
            readOnly: Boolean(readOnly),
            reference: contract.fromRow(row),
            observer: null,
            renderingOverlay: false,
        };
        renderPanel(controller);
        bindPanel(controller);
        bindLifecycle(controller);
        applyOverlay(controller);
        return true;
    }

    function scheduleMount(frm, row, readOnly, attempt = 0) {
        window.setTimeout(() => {
            if (mount(frm, row, readOnly)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(frm, row, readOnly, attempt + 1);
        }, attempt ? 45 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        scheduleMount(frm, row, Boolean(options.readOnly));
        return result;
    }

    function view(frm, row) {
        const result = baseEditor.view(frm, row);
        scheduleMount(frm, row, true);
        return result;
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __referenceImageIntegrated: true,
        open,
        view,
    });
    window.AlmdinaReferenceImageUX = Object.freeze({
        installStyles,
        referencePanelHtml,
        mount,
        applyOverlay,
    });
})();
