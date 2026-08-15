(() => {
    "use strict";

    const STYLE_ID = "dco-compact-measurements-css";
    const EDGE_LABELS = {
        edge_width_top: { ar: "قشاط العرض العلوي", en: "Top width edge" },
        edge_width_bottom: { ar: "قشاط العرض السفلي", en: "Bottom width edge" },
        edge_long_right: { ar: "قشاط الطول الأيمن", en: "Right long edge" },
        edge_long_left: { ar: "قشاط الطول الأيسر", en: "Left long edge" },
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
            .dco-fast-table th.dco-col-calc,
            .dco-fast-table td.dco-col-calc{display:none !important;}

            .dco-fast-entry-shell{width:100% !important;max-width:100% !important;}

            .dco-fast-entry-toolbar{
                flex-wrap:nowrap !important;
                align-items:center !important;
                padding:5px 8px !important;
                gap:6px 9px !important;
                min-height:42px !important;
            }

            .dco-fast-entry-toolbar .dco-fast-help{
                flex:1 1 auto !important;
                min-width:0;
                display:flex !important;
                align-items:center !important;
                flex-wrap:nowrap !important;
                gap:0 !important;
                padding:0 !important;
                border:0 !important;
                line-height:1.2 !important;
                white-space:nowrap;
                overflow:hidden;
            }

            .dco-fast-entry-toolbar .dco-measurement-title{
                font-size:13px;
                font-weight:850;
                color:var(--text-color,#36414c);
                overflow:hidden;
                text-overflow:ellipsis;
                white-space:nowrap;
            }

            /* The header now intentionally contains only the table title and actions. */
            .dco-fast-entry-toolbar>.dco-fast-readonly-note,
            .dco-fast-entry-toolbar>.dco-order-edge-color-badge{
                display:none !important;
            }

            .dco-fast-entry-toolbar>.dco-measurement-table-actions{
                order:100;
                direction:ltr;
                display:flex;
                align-items:center;
                gap:5px !important;
                width:auto !important;
                margin:0 !important;
                flex:0 0 auto;
            }

            .dco-fast-entry-toolbar .dco-measurement-table-actions .dco-toolbar-icon-button{
                width:32px !important;
                min-width:32px !important;
                height:32px !important;
                min-height:32px !important;
                flex:0 0 32px !important;
                display:inline-flex !important;
                align-items:center;
                justify-content:center;
                padding:0 !important;
                border:1px solid var(--border-color,#d8dee5) !important;
                border-radius:8px !important;
                background:var(--card-bg,var(--fg-color,#fff)) !important;
                color:var(--text-color,#36414c) !important;
                box-shadow:0 1px 2px rgba(15,23,42,.035);
                transition:border-color .14s ease,background .14s ease,box-shadow .14s ease,transform .08s ease;
            }

            .dco-fast-entry-toolbar .dco-measurement-table-actions .dco-toolbar-icon-button:hover{
                border-color:var(--primary,#2490ef) !important;
                background:rgba(36,144,239,.06) !important;
                color:var(--primary,#2490ef) !important;
                box-shadow:0 3px 9px rgba(15,23,42,.08);
            }

            .dco-fast-entry-toolbar .dco-measurement-table-actions .dco-toolbar-icon-button:active{
                transform:translateY(1px);
            }

            .dco-fast-entry-toolbar .dco-measurement-table-actions .dco-toolbar-icon-button:focus-visible{
                outline:2px solid var(--primary,#2490ef);
                outline-offset:2px;
            }

            .dco-toolbar-icon-button svg{
                width:16px;
                height:16px;
                display:block;
                fill:none;
                stroke:currentColor;
                stroke-width:1.8;
                stroke-linecap:round;
                stroke-linejoin:round;
                pointer-events:none;
            }

            .dco-fast-entry-scroll{
                width:100% !important;
                max-width:100% !important;
                overflow-y:auto !important;
                overflow-x:hidden !important;
                scrollbar-gutter:stable;
                max-height:min(70vh,720px) !important;
            }

            .dco-fast-table{
                width:100% !important;
                max-width:100% !important;
                min-width:0 !important;
                table-layout:fixed !important;
                border-collapse:separate;
                border-spacing:0;
            }

            .dco-fast-table th,
            .dco-fast-table td{
                box-sizing:border-box;
                min-width:0 !important;
                overflow:hidden;
                text-overflow:ellipsis;
            }

            .dco-fast-table th{
                padding:5px 3px !important;
                font-size:10.5px !important;
                line-height:1.15;
                white-space:normal !important;
                word-break:keep-all;
            }

            .dco-fast-table td{height:44px;padding:4px 3px !important;}

            .dco-fast-table .dco-select-col{
                width:32px !important;
                min-width:32px !important;
                max-width:32px !important;
                padding-inline:2px !important;
            }
            .dco-fast-table .dco-col-no{width:34px !important;}
            .dco-fast-table .dco-col-type{width:112px !important;}
            .dco-fast-table .dco-col-number{width:76px !important;}
            .dco-fast-table .dco-col-qty{width:54px !important;}
            .dco-fast-table .dco-col-rotate{width:46px !important;}
            .dco-fast-table .dco-col-edges{width:188px !important;}
            .dco-fast-table .dco-col-edge-type{width:128px !important;}
            .dco-fast-table .dco-col-sketch{width:50px !important;}
            .dco-fast-table .dco-col-notes{width:auto !important;min-width:0 !important;}
            .dco-fast-table .dco-col-delete{width:34px !important;}

            .dco-fast-input,
            .dco-fast-select{
                min-width:0 !important;
                min-height:35px !important;
                height:35px;
                border-radius:7px !important;
                padding:4px 6px !important;
                font-size:13px !important;
            }

            .dco-fast-input[type="number"]{font-size:14.5px !important;font-weight:650;}
            .dco-col-notes .dco-fast-input{text-align:right;font-size:12.5px !important;}
            .dco-row-selector,.dco-select-all{width:17px !important;height:17px !important;}
            .dco-column-header-select{min-height:43px !important;gap:3px !important;}
            .dco-column-select-all{gap:3px !important;font-size:9px !important;}
            .dco-column-select-all input{width:14px !important;height:14px !important;}

            .dco-edge-header-grid{
                grid-template-columns:repeat(4,minmax(0,1fr)) !important;
                gap:2px !important;
                min-height:43px !important;
            }

            .dco-edge-header-item{
                gap:3px !important;
                padding:0 1px;
                font-size:9px !important;
                line-height:1.1 !important;
            }

            .dco-edge-buttons{
                grid-template-columns:repeat(4,minmax(0,1fr)) !important;
                gap:3px !important;
                width:100%;
            }

            .dco-col-edges .dco-check-toggle{
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
            .dco-col-edges .dco-check-toggle>span:last-child{display:none !important;}

            .dco-col-edges .dco-check-toggle::before,
            .dco-col-edges .dco-check-toggle::after{
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

            .dco-col-edges .dco-check-toggle::before{border:1px solid currentColor;opacity:.25;}
            .dco-col-edges .dco-check-toggle[data-check-field="edge_long_right"]::after{border-right:3px solid currentColor;}
            .dco-col-edges .dco-check-toggle[data-check-field="edge_long_left"]::after{border-left:3px solid currentColor;}
            .dco-col-edges .dco-check-toggle[data-check-field="edge_width_top"]::after{border-top:3px solid currentColor;}
            .dco-col-edges .dco-check-toggle[data-check-field="edge_width_bottom"]::after{border-bottom:3px solid currentColor;}

            .dco-col-edges .dco-check-toggle.is-checked{
                color:#fff !important;
                box-shadow:0 2px 7px rgba(15,23,42,.16);
            }

            .dco-rotate-toggle{
                width:34px !important;
                height:34px !important;
                min-height:34px !important;
                margin:auto;
                padding:0 !important;
                font-size:18px !important;
                border-radius:8px !important;
            }

            .dco-rotate-toggle .dco-check-mark{display:none !important;}

            .dco-special-sketch-button{
                width:36px !important;
                min-width:36px !important;
                min-height:34px !important;
                height:34px;
                margin:auto;
                padding:0 !important;
                border-radius:8px !important;
            }

            .dco-special-sketch-button>span:last-child{display:none !important;}
            .dco-special-sketch-button>span:first-child{font-size:16px;}
            .dco-delete-row{width:28px !important;height:30px !important;border-radius:7px !important;}
            .dco-fast-table tbody tr:hover td{background:rgba(36,144,239,.025);}
            .dco-fast-table tbody tr:focus-within td{background:rgba(36,144,239,.045);}

            @media (max-width:900px){
                .dco-fast-table .dco-col-type{width:102px !important;}
                .dco-fast-table .dco-col-number{width:69px !important;}
                .dco-fast-table .dco-col-qty{width:49px !important;}
                .dco-fast-table .dco-col-rotate{width:42px !important;}
                .dco-fast-table .dco-col-edges{width:164px !important;}
                .dco-fast-table .dco-col-edge-type{width:112px !important;}
                .dco-fast-table .dco-col-sketch{width:44px !important;}
                .dco-fast-table .dco-col-delete{width:31px !important;}
                .dco-fast-input,.dco-fast-select{padding-inline:4px !important;}
            }

            @media (max-width:760px){
                .dco-fast-entry-toolbar{flex-wrap:nowrap !important;align-items:center !important;}
                .dco-fast-entry-toolbar .dco-fast-help{flex:1 1 auto !important;overflow:hidden;}
            }

            @media (max-width:720px){
                .dco-fast-table .dco-col-sketch,
                .dco-fast-table .dco-col-delete{display:none !important;}
                .dco-fast-table .dco-col-type{width:92px !important;}
                .dco-fast-table .dco-col-number{width:61px !important;}
                .dco-fast-table .dco-col-qty{width:45px !important;}
                .dco-fast-table .dco-col-rotate{width:39px !important;}
                .dco-fast-table .dco-col-edges{width:148px !important;}
                .dco-fast-table .dco-col-edge-type{width:94px !important;}
                .dco-fast-entry-toolbar>.dco-measurement-table-actions{width:auto !important;}
                .dco-fast-entry-toolbar .dco-measurement-table-actions .dco-toolbar-icon-button{flex:0 0 32px !important;}
            }
        `;
        document.head.appendChild(style);
    }

    function compactHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help || help.dataset.compactHelpReady === "1") return;
        help.dataset.compactHelpReady = "1";
        help.innerHTML = `<b class="dco-measurement-title">${isArabic() ? "جدول قياسات الدرف" : "Door Measurements Table"}</b>`;
    }

    function toolbarIconSvg(kind) {
        if (kind === "print") {
            return `
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M7 8V4h10v4"></path>
                    <path d="M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"></path>
                    <path d="M7 14h10v6H7z"></path>
                    <path d="M17.5 11.5h.01"></path>
                </svg>`;
        }
        return `
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M8 3H3v5"></path>
                <path d="M16 3h5v5"></path>
                <path d="M21 16v5h-5"></path>
                <path d="M3 16v5h5"></path>
            </svg>`;
    }

    function compactReadonlyNote(root) {
        const note = root.querySelector(".dco-fast-readonly-note");
        if (!note || note.dataset.compactReadonlyReady === "1") return;
        const label = isArabic() ? "الطلب للعرض فقط" : "Order is read only";
        note.dataset.compactReadonlyReady = "1";
        note.title = label;
        note.setAttribute("aria-label", label);
        note.textContent = isArabic() ? "🔒 عرض فقط" : "🔒 Read only";
    }

    function polishToolbar(root) {
        compactReadonlyNote(root);
        const actions = root.querySelector(".dco-measurement-table-actions");
        if (!actions) return;

        const printButton = actions.querySelector(".dco-print-measurements");
        if (printButton && printButton.dataset.compactIconReady !== "1") {
            const label = isArabic() ? "طباعة القياسات" : "Print measurements";
            printButton.dataset.compactIconReady = "1";
            printButton.classList.add("dco-toolbar-icon-button");
            printButton.title = label;
            printButton.setAttribute("aria-label", label);
            printButton.innerHTML = toolbarIconSvg("print");
        }

        const openButton = actions.querySelector(".dco-open-measurements-window");
        if (openButton && openButton.dataset.compactIconReady !== "1") {
            const label = isArabic() ? "تكبير جدول الإدخال" : "Expand measurement table";
            const title = isArabic() ? "فتح جدول الإدخال في نافذة مستقلة" : "Open measurement table in a separate window";
            openButton.dataset.compactIconReady = "1";
            openButton.classList.add("dco-toolbar-icon-button");
            openButton.title = title;
            openButton.setAttribute("aria-label", label);
            openButton.innerHTML = toolbarIconSvg("expand");
        }
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
        if (sketchHeader) sketchHeader.textContent = isArabic() ? "الشكل" : "Shape";
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

    function observeToolbar(root) {
        const toolbar = root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar || root._dcoCompactObservedToolbar === toolbar) return;
        if (root._dcoCompactToolbarObserver) root._dcoCompactToolbarObserver.disconnect();

        const observer = new MutationObserver(() => {
            requestAnimationFrame(() => polishToolbar(root));
        });
        observer.observe(toolbar, { childList:true, subtree:true });
        root._dcoCompactToolbarObserver = observer;
        root._dcoCompactObservedToolbar = toolbar;
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
        polishToolbar(root);
        observeRows(frm, root);
        observeToolbar(root);
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