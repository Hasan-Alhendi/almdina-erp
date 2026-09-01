(() => {
    "use strict";

    const STYLE_ID = "dco-measurement-toolbar-ux-css";
    const TITLE_AR = "جدول قياسات الدرف";
    const TITLE_EN = "Door Measurements Table";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang)
            || (frappe.boot && frappe.boot.user && frappe.boot.user.language)
            || document.documentElement.lang
            || ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-entry-toolbar{position:relative}
            .dco-fast-entry-toolbar .dco-fast-help{flex:1 1 auto!important;min-width:0!important;overflow:hidden!important}
            .dco-fast-entry-toolbar .dco-fast-help .dco-measurement-title{display:block;font-size:13px;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-color,#36414c)}
            .dco-measurement-table-actions{display:flex!important;align-items:center!important;gap:5px!important;flex:0 0 auto!important;width:auto!important;margin:0!important;direction:ltr!important}
            .dco-measurement-table-actions .dco-toolbar-icon-button{width:32px!important;min-width:32px!important;height:32px!important;min-height:32px!important;padding:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;border:1px solid var(--border-color,#d8dee5)!important;border-radius:8px!important;background:var(--card-bg,#fff)!important;color:var(--text-color,#36414c)!important}
            .dco-measurement-table-actions .dco-toolbar-icon-button:hover{border-color:var(--primary,#2490ef)!important;background:rgba(36,144,239,.06)!important;color:var(--primary,#2490ef)!important}
            .dco-measurement-table-actions .dco-toolbar-icon-button svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
            .dco-measurement-help-popover{position:absolute;z-index:35;top:calc(100% + 7px);left:8px;width:min(360px,calc(100vw - 32px));padding:10px 12px;border:1px solid var(--border-color,#d9e0e6);border-radius:10px;background:var(--card-bg,#fff);box-shadow:0 12px 30px rgba(15,23,42,.16);direction:rtl;color:var(--text-color,#36414c);font-size:11px;line-height:1.75}
            .dco-measurement-help-popover[hidden]{display:none!important}
            .dco-measurement-help-popover strong{display:block;margin-bottom:4px;font-size:12px}
            .dco-measurement-help-popover ul{margin:0;padding-inline-start:18px}
            @media(max-width:720px){.dco-measurement-help-popover{left:6px;right:6px;width:auto}}
        `;
        document.head.appendChild(style);
    }

    function icon(kind) {
        if (kind === "help") {
            return `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M9.7 9a2.5 2.5 0 1 1 4.1 1.9c-1.15.82-1.8 1.35-1.8 2.6"></path><path d="M12 17h.01"></path></svg>`;
        }
        return "";
    }

    function ensureTitle(toolbar) {
        const help = toolbar.querySelector(".dco-fast-help");
        if (!help) return;
        const title = isArabic() ? TITLE_AR : TITLE_EN;
        const current = help.querySelector(".dco-measurement-title");
        if (current && current.textContent.trim() === title && help.children.length === 1) return;
        help.innerHTML = `<b class="dco-measurement-title">${title}</b>`;
    }

    function ensureHelpPopover(toolbar) {
        let popover = toolbar.querySelector(".dco-measurement-help-popover");
        if (popover) return popover;
        popover = document.createElement("div");
        popover.className = "dco-measurement-help-popover";
        popover.hidden = true;
        popover.innerHTML = isArabic()
            ? `<strong>تعليمات جدول القياسات</strong><ul><li>كل ضلع يأخذ نوع القشاط الافتراضي ما لم تخصصه.</li><li>لتخصيص ضلع استخدم رمز الضلع داخل صف الدرفة.</li><li>القياس النهائي يُحسب مع الخصم حسب سماكة القشاط لكل ضلع.</li></ul>`
            : `<strong>Measurement table help</strong><ul><li>Each edge uses the default banding unless overridden.</li><li>Use the edge control in the row to override an edge.</li><li>Final size accounts for the band thickness on each edge.</li></ul>`;
        toolbar.appendChild(popover);
        return popover;
    }

    function ensureHelpButton(toolbar, actions) {
        let button = actions.querySelector(".dco-measurement-instructions");
        if (!button) {
            button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-default btn-sm dco-toolbar-icon-button dco-measurement-instructions";
            actions.appendChild(button);
        }
        const label = isArabic() ? "تعليمات" : "Instructions";
        button.title = label;
        button.setAttribute("aria-label", label);
        button.setAttribute("aria-expanded", "false");
        button.innerHTML = icon("help");

        if (button.dataset.dcoHelpBound !== "1") {
            button.dataset.dcoHelpBound = "1";
            button.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                const popover = ensureHelpPopover(toolbar);
                const open = popover.hidden;
                popover.hidden = !open;
                button.setAttribute("aria-expanded", open ? "true" : "false");
            });
        }
    }

    function polish(frm) {
        installStyles();
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return false;

        ensureTitle(toolbar);
        const actions = toolbar.querySelector(".dco-measurement-table-actions");
        if (!actions) return false;
        ensureHelpButton(toolbar, actions);
        ensureHelpPopover(toolbar);

        if (!root._dcoMeasurementToolbarOutsideBound) {
            root._dcoMeasurementToolbarOutsideBound = true;
            document.addEventListener("click", event => {
                if (!root.isConnected || toolbar.contains(event.target)) return;
                const popover = toolbar.querySelector(".dco-measurement-help-popover");
                const button = toolbar.querySelector(".dco-measurement-instructions");
                if (popover) popover.hidden = true;
                if (button) button.setAttribute("aria-expanded", "false");
            });
        }
        return true;
    }

    function schedule(frm) {
        const lifecycle = window.AlmdinaMeasurementLifecycle;
        if (!lifecycle) {
            requestAnimationFrame(() => polish(frm));
            return;
        }
        lifecycle.retry(
            frm,
            "measurement-toolbar",
            () => polish(frm),
            { maxAttempts: 11, delay: 60 }
        );
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
    if (measurementLifecycle && typeof measurementLifecycle.registerFeature === "function") {
        measurementLifecycle.registerFeature("measurement-toolbar", polish);
    }

    window.AlmdinaMeasurementToolbarUX = Object.freeze({
        polish,
        ensureTitle,
        ensureHelpButton,
    });
})();
