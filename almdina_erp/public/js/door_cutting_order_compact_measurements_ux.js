(() => {
    "use strict";

    const STYLE_ID = "dco-compact-measurements-css";
    const EDGE_LABELS = {
        edge_long_right: { ar: "قشاط الطول الأيمن", en: "Right long edge" },
        edge_long_left: { ar: "قشاط الطول الأيسر", en: "Left long edge" },
        edge_width_top: { ar: "قشاط العرض العلوي", en: "Top width edge" },
        edge_width_bottom: { ar: "قشاط العرض السفلي", en: "Bottom width edge" },
    };

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            /* Calculated values stay in the child model and invoices, but are not
               useful while the operator is entering dimensions. */
            .dco-fast-table th.dco-col-calc,
            .dco-fast-table td.dco-col-calc {
                display:none !important;
            }

            .dco-fast-entry-shell {
                width:100% !important;
                max-width:100% !important;
            }

            .dco-fast-entry-toolbar {
                padding:8px 10px !important;
                gap:6px 12px !important;
                min-height:44px;
            }

            .dco-fast-entry-toolbar .dco-fast-help {
                flex:1 1 auto;
                min-width:0;
                gap:5px 9px !important;
                line-height:1.45;
            }

            .dco-fast-entry-toolbar .dco-help-secondary {
                color:var(--text-muted,#6c7680);
            }

            .dco-fast-entry-scroll {
                width:100% !important;
                max-width:100% !important;
                overflow-y:auto !important;
                overflow-x:hidden !important;
                scrollbar-gutter:stable;
                max-height:min(70vh,720px) !important;
            }

            .dco-fast-table {
                width:100% !important;
                max-width:100% !important;
                min-width:0 !important;
                table-layout:fixed !important;
                border-collapse:separate;
                border-spacing:0;
            }

            .dco-fast-table th,
            .dco-fast-table td {
                box-sizing:border-box;
                min-width:0 !important;
                overflow:hidden;
                text-overflow:ellipsis;
            }

            .dco-fast-table th {
                padding:6px 3px !important;
                font-size:10.5px !important;
                line-height:1.2;
                white-space:normal !important;
                word-break:keep-all;
            }

            .dco-fast-table td {
                height:45px;
                padding:4px 3px !important;
            }

            /* Fixed compact columns leave all remaining width to Notes. */
            .dco-fast-table .dco-select-col {
                width:32px !important;
                min-width:32px !important;
                max-width:32px !important;
                padding-inline:2px !important;
            }
            .dco-fast-table .dco-col-no { width:34px !important; }
            .dco-fast-table .dco-col-type { width:92px !important; }
            .dco-fast-table .dco-col-number { width:76px !important; }
            .dco-fast-table .dco-col-qty { width:54px !important; }
            .dco-fast-table .dco-col-rotate { width:46px !important; }
            .dco-fast-table .dco-col-edges { width:188px !important; }
            .dco-fast-table .dco-col-edge-type { width:128px !important; }
            .dco-fast-table .dco-col-sketch { width:50px !important; }
            .dco-fast-table .dco-col-notes {
                width:auto !important;
                min-width:0 !important;
            }
            .dco-fast-table .dco-col-delete { width:34px !important; }

            .dco-fast-input,
            .dco-fast-select {
                min-width:0 !important;
                min-height:35px !important;
                height:35px;
                border-radius:7px !important;
                padding:4px 6px !important;
                font-size:13px !important;
            }

            .dco-fast-input[type="number"] {
                font-size:14.5px !important;
                font-weight:650;
            }

            .dco-col-notes .dco-fast-input {
                text-align:right;
                font-size:12.5px !important;
            }

            .dco-row-selector,
            .dco-select-all {
                width:17px !important;
                height:17px !important;
            }

            .dco-column-header-select {
                min-height:45px !important;
                gap:3px !important;
            }

            .dco-column-select-all {
                gap:3px !important;
                font-size:9px !important;
            }

            .dco-column-select-all input {
                width:14px !important;
                height:14px !important;
            }

            .dco-edge-header-grid {
                grid-template-columns:repeat(4,minmax(0,1fr)) !important;
                gap:2px !important;
                min-height:45px !important;
            }

            .dco-edge-header-item {
                gap:3px !important;
                padding:0 1px;
                font-size:9px !important;
                line-height:1.1 !important;
            }

            .dco-edge-buttons {
                grid-template-columns:repeat(4,minmax(0,1fr)) !important;
                gap:3px !important;
                width:100%;
            }

            /* The header already names each side. Row controls use a clear visual
               side indicator instead of repeating four long Arabic labels. */
            .dco-col-edges .dco-check-toggle {
                position:relative;
                width:100%;
                min-width:0;
                min-height:34px !important;
                height:34px;
                padding:0 !important;
                border-radius:7px !important;
                font-size:0 !important;
                color:var(--text-color,#36414c);
            }

            .dco-col-edges .dco-check-toggle .dco-check-mark,
            .dco-col-edges .dco-check-toggle > span:last-child {
                display:none !important;
            }

            .dco-col-edges .dco-check-toggle::before,
            .dco-col-edges .dco-check-toggle::after {
                content:"";
                position:absolute;
                left:50%;
                top:50%;
                width:21px;
                height:15px;
                box-sizing:border-box;
                transform:translate(-50%,-50%);
                border-radius:3px;
                pointer-events:none;
            }

            .dco-col-edges .dco-check-toggle::before {
                border:1px solid currentColor;
                opacity:.25;
            }

            .dco-col-edges .dco-check-toggle[data-check-field="edge_long_right"]::after {
                border-right:3px solid currentColor;
            }
            .dco-col-edges .dco-check-toggle[data-check-field="edge_long_left"]::after {
                border-left:3px solid currentColor;
            }
            .dco-col-edges .dco-check-toggle[data-check-field="edge_width_top"]::after {
                border-top:3px solid currentColor;
            }
            .dco-col-edges .dco-check-toggle[data-check-field="edge_width_bottom"]::after {
                border-bottom:3px solid currentColor;
            }

            .dco-col-edges .dco-check-toggle.is-checked {
                color:#fff !important;
                box-shadow:0 2px 7px rgba(15,23,42,.16);
            }

            .dco-rotate-toggle {
                width:34px !important;
                height:34px !important;
                min-height:34px !important;
                margin:auto;
                padding:0 !important;
                font-size:18px !important;
                border-radius:8px !important;
            }

            .dco-rotate-toggle .dco-check-mark { display:none !important; }

            .dco-special-sketch-button {
                width:36px !important;
                min-width:36px !important;
                min-height:34px !important;
                height:34px;
                margin:auto;
                padding:0 !important;
                border-radius:8px !important;
            }

            .dco-special-sketch-button > span:last-child { display:none !important; }
            .dco-special-sketch-button > span:first-child { font-size:16px; }

            .dco-delete-row {
                width:28px !important;
                height:30px !important;
                border-radius:7px !important;
            }

            .dco-fast-table tbody tr:hover td {
                background:rgba(36,144,239,.025);
            }

            .dco-fast-table tbody tr:focus-within td {
                background:rgba(36,144,239,.045);
            }

            @media (max-width:900px) {
                .dco-fast-table .dco-col-type { width:82px !important; }
                .dco-fast-table .dco-col-number { width:69px !important; }
                .dco-fast-table .dco-col-qty { width:49px !important; }
                .dco-fast-table .dco-col-rotate { width:42px !important; }
                .dco-fast-table .dco-col-edges { width:164px !important; }
                .dco-fast-table .dco-col-edge-type { width:112px !important; }
                .dco-fast-table .dco-col-sketch { width:44px !important; }
                .dco-fast-table .dco-col-delete { width:31px !important; }
                .dco-fast-input,.dco-fast-select { padding-inline:4px !important; }
            }

            @media (max-width:720px) {
                .dco-fast-table .dco-col-sketch,
                .dco-fast-table .dco-col-delete {
                    display:none !important;
                }
                .dco-fast-table .dco-col-type { width:72px !important; }
                .dco-fast-table .dco-col-number { width:61px !important; }
                .dco-fast-table .dco-col-qty { width:45px !important; }
                .dco-fast-table .dco-col-rotate { width:39px !important; }
                .dco-fast-table .dco-col-edges { width:148px !important; }
                .dco-fast-table .dco-col-edge-type { width:94px !important; }
                .dco-fast-entry-toolbar .dco-help-secondary { display:none; }
            }
        `;
        document.head.appendChild(style);
    }

    function compactHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help || help.dataset.compactHelpReady === "1") return;
        help.dataset.compactHelpReady = "1";
        help.innerHTML = isArabic()
            ? `
                <b>إدخال سريع:</b>
                <span>العرض <kbd>Tab</kbd> الطول <kbd>Enter</kbd> سطر جديد</span>
                <span class="dco-arrow-nav-hint"><kbd>← ↑ ↓ →</kbd><span>للتنقل</span></span>
                <span class="dco-help-secondary">القشاط والتدوير بنقرة واحدة</span>`
            : `
                <b>Fast entry:</b>
                <span>Width <kbd>Tab</kbd> Length <kbd>Enter</kbd> new row</span>
                <span class="dco-arrow-nav-hint"><kbd>← ↑ ↓ →</kbd><span>navigate</span></span>
                <span class="dco-help-secondary">Edges and rotation toggle in one click</span>`;
    }

    function decorateControls(root) {
        Object.entries(EDGE_LABELS).forEach(([fieldname, labels]) => {
            root.querySelectorAll(`button.dco-check-toggle[data-check-field="${fieldname}"]`).forEach(button => {
                const label = isArabic() ? labels.ar : labels.en;
                button.title = label;
                button.setAttribute("aria-label", label);
            });
        });

        root.querySelectorAll("button.dco-rotate-toggle").forEach(button => {
            const label = isArabic() ? "السماح بتدوير الدرفة" : "Allow piece rotation";
            button.title = label;
            button.setAttribute("aria-label", label);
        });

        root.querySelectorAll("input.dco-fast-input[data-field='notes']").forEach(input => {
            if (!input.placeholder) input.placeholder = isArabic() ? "ملاحظات..." : "Notes...";
        });

        const sketchHeader = root.querySelector("th.dco-col-sketch");
        if (sketchHeader) sketchHeader.textContent = isArabic() ? "رسم" : "Sketch";
    }

    function observeRows(frm, root) {
        const tbody = root.querySelector(".dco-fast-table tbody");
        if (!tbody || root._dcoCompactObservedBody === tbody) return;
        if (root._dcoCompactObserver) root._dcoCompactObserver.disconnect();

        const observer = new MutationObserver(() => {
            requestAnimationFrame(() => compactTable(frm));
        });
        observer.observe(tbody, { childList:true, subtree:true });
        root._dcoCompactObserver = observer;
        root._dcoCompactObservedBody = tbody;
    }

    function compactTable(frm) {
        installStyles();
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        root.classList.add("dco-compact-measurements");
        root.querySelectorAll("th.dco-col-calc, td.dco-col-calc").forEach(cell => {
            cell.setAttribute("aria-hidden", "true");
            cell.tabIndex = -1;
        });

        compactHelp(root);
        decorateControls(root);
        observeRows(frm, root);
    }

    function schedule(frm) {
        compactTable(frm);
        requestAnimationFrame(() => compactTable(frm));
        setTimeout(() => compactTable(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });
})();
