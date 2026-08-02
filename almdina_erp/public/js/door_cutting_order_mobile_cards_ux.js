(() => {
    "use strict";

    const STYLE_ID = "dco-mobile-piece-cards-css";
    const CARD_MAX_WIDTH = 900;

    const CARD_CSS = `
        .dco-mobile-piece-cards {
            --dco-card-touch-target:44px;
            --dco-card-gap:9px;
            width:100%;
            min-width:0;
            max-width:100%;
        }
        .dco-mobile-piece-cards .dco-fast-entry-shell {
            width:100%!important;
            max-width:100%!important;
            border:0!important;
            border-radius:0!important;
            background:transparent!important;
            overflow:visible!important;
        }
        .dco-mobile-piece-cards .dco-fast-entry-toolbar {
            display:block!important;
            width:100%;
            margin-bottom:10px;
            padding:10px!important;
            border:1px solid var(--border-color,#dfe3e8)!important;
            border-radius:12px!important;
            background:var(--subtle-fg,#f8f9fa)!important;
        }
        .dco-mobile-piece-cards .dco-fast-help {
            display:grid!important;
            grid-template-columns:1fr;
            gap:5px!important;
            width:100%;
            min-width:0;
        }
        .dco-mobile-piece-cards .dco-arrow-nav-hint,
        .dco-mobile-piece-cards .dco-help-secondary {
            display:none!important;
        }
        .dco-mobile-piece-cards .dco-fast-entry-scroll {
            width:100%!important;
            min-width:0!important;
            max-width:100%!important;
            max-height:none!important;
            overflow:visible!important;
            scrollbar-gutter:auto!important;
        }
        .dco-mobile-piece-cards .dco-fast-table {
            display:block!important;
            width:100%!important;
            min-width:0!important;
            max-width:100%!important;
            table-layout:auto!important;
            border:0!important;
            background:transparent!important;
        }
        .dco-mobile-piece-cards .dco-fast-table thead {
            position:absolute!important;
            width:1px!important;
            height:1px!important;
            padding:0!important;
            margin:-1px!important;
            overflow:hidden!important;
            clip:rect(0,0,0,0)!important;
            white-space:nowrap!important;
            border:0!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody {
            display:grid!important;
            grid-template-columns:1fr;
            gap:12px;
            width:100%;
            min-width:0;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody tr {
            position:relative;
            display:grid!important;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:var(--dco-card-gap);
            width:100%!important;
            min-width:0!important;
            max-width:100%!important;
            padding:12px!important;
            border:1px solid var(--border-color,#dfe3e8)!important;
            border-radius:15px!important;
            background:var(--card-bg,var(--fg-color,#fff))!important;
            box-shadow:0 5px 16px rgba(15,23,42,.07)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody tr.dco-virtual-row {
            border-style:dashed!important;
            background:rgba(36,144,239,.025)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody tr.dco-row-selected {
            border-color:var(--primary,#2490ef)!important;
            box-shadow:inset -3px 0 0 var(--primary,#2490ef),0 5px 16px rgba(15,23,42,.08)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody td {
            position:static!important;
            display:flex!important;
            flex-direction:column;
            align-items:stretch;
            justify-content:flex-start;
            gap:5px;
            width:auto!important;
            min-width:0!important;
            max-width:none!important;
            height:auto!important;
            padding:0!important;
            border:0!important;
            background:transparent!important;
            box-shadow:none!important;
            overflow:visible!important;
            text-align:start!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody td::before {
            content:attr(data-label);
            display:block;
            min-height:17px;
            color:var(--text-muted,#607080);
            font-size:11px;
            font-weight:800;
            line-height:1.35;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody :where(.dco-col-type,.dco-col-edges,.dco-col-edge-type,.dco-col-notes) {
            grid-column:1/-1;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-select-col {
            grid-column:1;
            grid-row:1;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-no {
            grid-column:2;
            grid-row:1;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-calc,
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-delete:empty {
            display:none!important;
        }
        .dco-mobile-piece-cards .dco-fast-table :where(.dco-fast-input,.dco-fast-select,.dco-notes-expand,.dco-check-toggle,.dco-special-sketch-button,.dco-delete-row) {
            width:100%!important;
            min-width:0!important;
            min-height:var(--dco-card-touch-target)!important;
            height:var(--dco-card-touch-target)!important;
            margin:0!important;
            font-size:16px!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-special-sketch-button > span:last-child {
            display:inline!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-edge-buttons {
            display:grid!important;
            grid-template-columns:repeat(2,minmax(0,1fr))!important;
            gap:7px!important;
            width:100%;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-col-edges .dco-check-toggle {
            min-height:48px!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-notes-editor {
            display:grid!important;
            grid-template-columns:minmax(0,1fr) var(--dco-card-touch-target)!important;
            gap:7px!important;
            width:100%;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-row-selector {
            width:22px!important;
            height:22px!important;
            margin:9px 2px!important;
        }
        .dco-mobile-piece-cards .dco-bulk-footer {
            position:static!important;
            display:grid!important;
            grid-template-columns:1fr;
            gap:8px!important;
            width:100%;
            margin-top:10px;
            padding:10px!important;
            border:1px solid var(--border-color,#dfe3e8)!important;
            border-radius:12px!important;
            background:var(--card-bg,var(--fg-color,#fff));
            box-shadow:none!important;
        }
        .dco-mobile-piece-cards .dco-selection-actions {
            display:grid!important;
            grid-template-columns:1fr;
            gap:7px;
            width:100%;
        }
        .dco-mobile-piece-cards .dco-selection-actions[hidden] {
            display:none!important;
        }
        .dco-mobile-piece-cards .dco-bulk-footer :where(.btn,button) {
            width:100%!important;
            min-width:0!important;
            min-height:var(--dco-card-touch-target)!important;
        }
        @media(max-width:480px) {
            .dco-mobile-piece-cards .dco-fast-table tbody tr {
                grid-template-columns:1fr;
            }
            .dco-mobile-piece-cards .dco-fast-table tbody td {
                grid-column:1/-1!important;
                grid-row:auto!important;
            }
            .dco-mobile-piece-cards .dco-fast-table tbody :where(.dco-select-col,.dco-col-no) {
                display:grid!important;
                grid-template-columns:minmax(96px,auto) 1fr;
                align-items:center;
            }
        }
    `;

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = CARD_CSS;
        document.head.appendChild(style);
    }

    function rootNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return null;
        return field.$wrapper.get ? field.$wrapper.get(0) : field.$wrapper[0];
    }

    function positiveWidth(value) {
        const width = Number(value || 0);
        return Number.isFinite(width) && width > 0 ? width : null;
    }

    function availableWidth(root) {
        const documentWidth = positiveWidth(document.documentElement && document.documentElement.clientWidth);
        const viewportWidth = positiveWidth(window.innerWidth);
        const screenWidth = positiveWidth(window.screen && window.screen.width);
        const rootWidth = positiveWidth(root && root.getBoundingClientRect().width);
        const widths = [documentWidth, viewportWidth, screenWidth, rootWidth].filter(Boolean);
        return widths.length ? Math.min(...widths) : Number.POSITIVE_INFINITY;
    }

    function shouldUseCardLayout(root) {
        return availableWidth(root) <= CARD_MAX_WIDTH;
    }

    function apply(frm) {
        installStyles();
        const root = rootNode(frm);
        if (!root) return;
        root.classList.toggle("dco-mobile-piece-cards", shouldUseCardLayout(root));
    }

    function observe(frm) {
        const root = rootNode(frm);
        if (!root || frm.__dcoMobileCardsObservedRoot === root) return;

        if (frm.__dcoMobileCardsObserver) frm.__dcoMobileCardsObserver.disconnect();
        if (frm.__dcoMobileCardsResizeHandler) {
            window.removeEventListener("resize", frm.__dcoMobileCardsResizeHandler);
        }

        const refresh = () => apply(frm);
        if (typeof ResizeObserver === "function") {
            frm.__dcoMobileCardsObserver = new ResizeObserver(refresh);
            frm.__dcoMobileCardsObserver.observe(root);
        }
        window.addEventListener("resize", refresh, { passive: true });
        frm.__dcoMobileCardsResizeHandler = refresh;
        frm.__dcoMobileCardsObservedRoot = root;
    }

    function refresh(frm) {
        apply(frm);
        observe(frm);
        requestAnimationFrame(() => apply(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
    });

    window.AlmdinaMobilePieceCardsUX = Object.freeze({
        apply,
        shouldUseCardLayout,
    });
})();
