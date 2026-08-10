(() => {
    "use strict";

    const catalog = window.AlmdinaSketchTemplateCatalog;
    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (!catalog || !baseEditor) {
        console.error("Template catalog and special-shape editor must load before smart template palette");
        return;
    }
    if (baseEditor.__smartTemplatePaletteIntegrated) return;

    const STYLE_ID = "dco-smart-template-palette-css";
    const MOUNT_RETRIES = 12;

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
            .dco-smart-template-palette{margin:3px 0 5px;padding:8px;border:1px solid var(--border-color,#dce3e8);border-radius:11px;background:var(--subtle-fg,#f8fafb)}
            .dco-smart-template-head{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:7px}
            .dco-smart-template-head strong{font-size:10px;color:var(--text-color,#172033)}
            .dco-smart-template-head span{font-size:8px;color:var(--text-muted,#71808e)}
            .dco-smart-template-list{display:grid;grid-template-columns:1fr 1fr;gap:5px;max-height:228px;overflow:auto;padding:1px}
            .dco-smart-template-card{display:flex;align-items:center;gap:6px;min-height:43px;padding:5px 6px;border:1px solid #dce3e8;border-radius:9px;background:#fff;color:inherit;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-smart-template-card:hover{border-color:#2490ef;background:#f4faff;box-shadow:0 0 0 2px rgba(36,144,239,.07)}
            .dco-smart-template-card-icon{display:grid;place-items:center;width:25px;height:25px;border-radius:7px;background:#edf5fb;color:#1769aa;font-size:15px;font-weight:900;flex:0 0 auto}
            .dco-smart-template-card strong{display:block;font-size:8.5px;line-height:1.2}
            .dco-smart-template-card small{display:block;margin-top:2px;font-size:7px;line-height:1.15;color:#71808e}
            .dco-smart-template-more{width:100%;margin-top:6px;min-height:30px;border:1px dashed #b8c5cf;border-radius:8px;background:#fff;color:#36566c;cursor:pointer;font-size:8.5px;font-weight:900}
            .dco-smart-template-more:hover{border-color:#2490ef;color:#1769aa;background:#f7fbff}
            .dco-smart-template-palette:not(.is-expanded) .dco-smart-template-card[data-common="0"]{display:none}
            .dco-sketch-template-grid.dco-smart-template-proxy{display:none!important}
            .dco-sketch-snap-point{filter:drop-shadow(0 0 3px rgba(21,142,91,.32))}
            .dco-special-shape-modal .dco-smart-axis-guide{animation:dco-smart-guide-in .12s ease-out}
            @keyframes dco-smart-guide-in{from{opacity:.25}to{opacity:1}}
            @media(max-width:700px){.dco-smart-template-palette{display:none}}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        return modals.reverse().find(modal =>
            modal.classList.contains("show")
            || modal.style.display === "block"
            || modal.getAttribute("aria-hidden") !== "true"
        ) || null;
    }

    function cardHtml(item) {
        return `<button type="button" class="dco-smart-template-card" data-smart-template="${esc(item.key)}" data-common="${item.common ? "1" : "0"}" title="${esc(item.hint)}">
            <span class="dco-smart-template-card-icon" aria-hidden="true">${esc(item.icon)}</span>
            <span><strong>${esc(item.label)}</strong><small>${esc(item.hint)}</small></span>
        </button>`;
    }

    function panelHtml() {
        return `<section class="dco-smart-template-palette" aria-label="قوالب الدرف الذكية">
            <div class="dco-smart-template-head"><strong>قوالب ذكية</strong><span>اختر ثم عدّل</span></div>
            <div class="dco-smart-template-list">${catalog.all().map(cardHtml).join("")}</div>
            <button type="button" class="dco-smart-template-more">عرض كل القوالب</button>
        </section>`;
    }

    function proxyTemplateClick(grid, key) {
        const proxy = grid.querySelector(".dco-sketch-template");
        if (!proxy) return false;
        const previous = proxy.dataset.template;
        proxy.dataset.template = key;
        try {
            proxy.click();
            return true;
        } finally {
            proxy.dataset.template = previous;
        }
    }

    function selectTool(root, tool) {
        const button = root.querySelector(`.dco-sketch-tool[data-tool="${tool}"]`);
        if (!button) return false;
        button.click();
        return true;
    }

    function bindShortcuts(modal, root) {
        if (modal.dataset.dcoSmartShortcuts === "1") return;
        modal.dataset.dcoSmartShortcuts = "1";
        const handler = event => {
            if (!modal.classList.contains("show") && modal.style.display !== "block") return;
            const target = event.target;
            if (target && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)) return;
            if (event.ctrlKey || event.metaKey || event.altKey) return;
            const tool = {
                l: "line",
                r: "rectangle",
                o: "ellipse",
                d: "dimension",
                n: "note",
            }[String(event.key || "").toLowerCase()];
            if (!tool) return;
            if (selectTool(root, tool)) event.preventDefault();
        };
        document.addEventListener("keydown", handler, true);
        const cleanup = () => document.removeEventListener("keydown", handler, true);
        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-smart-template-shortcuts", cleanup);
        } else {
            modal.addEventListener("hidden.bs.modal", cleanup, { once: true });
        }
    }

    function mount(row) {
        installStyles();
        const modal = visibleModal();
        if (!modal || modal.classList.contains("dco-special-shape-readonly")) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root) return false;
        const grid = root.querySelector(".dco-sketch-template-grid");
        if (!grid) return false;
        if (root.querySelector(".dco-smart-template-palette")) return true;

        const wrapper = document.createElement("div");
        wrapper.innerHTML = panelHtml();
        const panel = wrapper.firstElementChild;
        grid.classList.add("dco-smart-template-proxy");
        grid.parentNode.insertBefore(panel, grid);

        panel.addEventListener("click", event => {
            const more = event.target.closest && event.target.closest(".dco-smart-template-more");
            if (more) {
                panel.classList.toggle("is-expanded");
                more.textContent = panel.classList.contains("is-expanded")
                    ? "عرض الأكثر استخدامًا فقط"
                    : "عرض كل القوالب";
                return;
            }
            const button = event.target.closest && event.target.closest("[data-smart-template]");
            if (!button) return;
            const key = button.dataset.smartTemplate;
            if (!proxyTemplateClick(grid, key)) return;
            const item = catalog.find(key);
            const notice = root.querySelector(".dco-sketch-notice-text");
            if (notice && item) {
                notice.textContent = `تمت إضافة «${item.label}». اسحبه فوق صورة المرجع ثم أضف القياسات الحقيقية.`;
            }
        });

        const keyHint = root.querySelector(".dco-sketch-key-hint");
        if (keyHint) {
            keyHint.textContent = "Shift: أفقي/عمودي · النهايات مغناطيسية · L خط · R مستطيل · O دائرة · Ctrl + عجلة: تكبير";
        }
        const lineTool = root.querySelector('.dco-sketch-tool[data-tool="line"] small');
        if (lineTool) lineTool.textContent = "Shift يقفل أفقي/عمودي + Snap للنهايات";
        bindShortcuts(modal, root);
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
        __smartTemplatePaletteIntegrated: true,
        open,
        view,
    });
    window.AlmdinaSmartTemplatePalette = Object.freeze({
        installStyles,
        panelHtml,
        proxyTemplateClick,
        mount,
    });
})();