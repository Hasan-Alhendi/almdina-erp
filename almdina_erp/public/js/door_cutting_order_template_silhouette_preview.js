(() => {
    "use strict";

    const catalog = window.AlmdinaSketchTemplateCatalog;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (!catalog || !baseEditor) {
        console.error("Template catalog and editor must load before silhouette previews");
        return;
    }
    if (baseEditor.__templateSilhouettePreviewIntegrated) return;

    const STYLE_ID = "dco-template-silhouette-preview-css";
    const MOUNT_RETRIES = 14;
    const PREVIEW_VIEWBOX = "180 90 640 470";

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
            .dco-smart-template-card-icon{width:38px!important;height:34px!important;padding:3px!important;border-radius:8px!important;background:#f5f9fc!important;color:#1769aa!important;overflow:hidden}
            .dco-smart-template-card-icon svg{display:block;width:100%;height:100%;overflow:visible}
            .dco-smart-template-card-icon path{fill:rgba(36,144,239,.10);stroke:#1769aa;stroke-width:15;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
            .dco-smart-template-card:hover .dco-smart-template-card-icon{background:#eaf5fd!important}
            .dco-smart-template-card:hover .dco-smart-template-card-icon path{fill:rgba(36,144,239,.16);stroke:#0f6fad}
        `;
        document.head.appendChild(style);
    }

    function previewSvg(key) {
        const d = catalog.pathData(key);
        if (!d) return "";
        return `<svg viewBox="${PREVIEW_VIEWBOX}" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false"><path d="${esc(d)}"></path></svg>`;
    }

    function apply(root) {
        if (!root) return false;
        installStyles();
        const cards = Array.from(root.querySelectorAll("[data-smart-template]"));
        if (!cards.length) return false;
        let changed = false;
        cards.forEach(card => {
            const key = String(card.dataset.smartTemplate || "");
            const icon = card.querySelector(".dco-smart-template-card-icon");
            if (!icon || icon.dataset.silhouetteKey === key) return;
            const markup = previewSvg(key);
            if (!markup) return;
            icon.innerHTML = markup;
            icon.dataset.silhouetteKey = key;
            changed = true;
        });
        return changed || cards.every(card => {
            const icon = card.querySelector(".dco-smart-template-card-icon");
            return icon && icon.dataset.silhouetteKey === String(card.dataset.smartTemplate || "");
        });
    }

    function visibleRoot() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        const modal = modals.reverse().find(item =>
            item.classList.contains("show")
            || item.style.display === "block"
            || item.getAttribute("aria-hidden") !== "true"
        );
        return modal ? modal.querySelector(".dco-special-sketch-shell") : null;
    }

    function scheduleApply(attempt = 0) {
        window.setTimeout(() => {
            const root = visibleRoot();
            if (root && apply(root)) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleApply(attempt + 1);
        }, attempt ? 35 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleApply();
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __templateSilhouettePreviewIntegrated: true,
        open,
        view,
    });
    window.AlmdinaTemplateSilhouettePreview = Object.freeze({
        PREVIEW_VIEWBOX,
        previewSvg,
        apply,
        installStyles,
    });
})();