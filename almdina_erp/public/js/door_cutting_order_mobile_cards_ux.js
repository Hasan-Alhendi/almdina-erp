(() => {
    "use strict";

    const STYLE_ID = "dco-mobile-piece-cards-css";
    const PHONE_SHORT_SIDE_MAX_WIDTH = 600;
    const PHONE_VIEWPORT_MAX_WIDTH = 900;

    const CARD_CSS = `
        .dco-mobile-piece-cards {
            --dco-compact-control-height:38px;
            --dco-compact-gap:6px;
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
            margin-bottom:7px;
            padding:7px 8px!important;
            border:1px solid var(--border-color,#dfe3e8)!important;
            border-radius:9px!important;
            background:var(--subtle-fg,#f8f9fa)!important;
            font-size:11px!important;
        }
        .dco-mobile-piece-cards .dco-fast-help {
            display:flex!important;
            flex-wrap:wrap;
            align-items:center;
            gap:3px 7px!important;
            width:100%;
            min-width:0;
        }
        .dco-mobile-piece-cards .dco-arrow-nav-hint,
        .dco-mobile-piece-cards .dco-help-secondary,
        .dco-mobile-piece-cards .dco-fast-help > span:last-child {
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
            gap:8px;
            width:100%;
            min-width:0;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody tr {
            position:relative;
            display:grid!important;
            grid-template-columns:repeat(6,minmax(0,1fr));
            gap:var(--dco-compact-gap);
            width:100%!important;
            min-width:0!important;
            max-width:100%!important;
            padding:8px!important;
            border:1px solid var(--border-color,#dfe3e8)!important;
            border-radius:10px!important;
            background:var(--card-bg,var(--fg-color,#fff))!important;
            box-shadow:0 1px 4px rgba(15,23,42,.055)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody tr.dco-virtual-row {
            border-style:dashed!important;
            background:rgba(36,144,239,.02)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody tr.dco-row-selected {
            border-color:var(--primary,#2490ef)!important;
            box-shadow:inset -2px 0 0 var(--primary,#2490ef),0 1px 4px rgba(15,23,42,.06)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody td {
            position:static!important;
            display:flex!important;
            flex-direction:column;
            align-items:stretch;
            justify-content:flex-end;
            gap:2px;
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
            min-height:13px;
            color:var(--text-muted,#607080);
            font-size:9.5px;
            font-weight:750;
            line-height:1.2;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-select-col {
            grid-column:1;
            grid-row:1;
            align-items:center;
            justify-content:center;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-no {
            grid-column:2;
            grid-row:1;
            align-items:center;
            justify-content:center;
            min-height:var(--dco-compact-control-height)!important;
            border-radius:7px!important;
            background:var(--subtle-fg,#f5f6f7)!important;
            font-size:12px;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody :where(.dco-select-col,.dco-col-no)::before,
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-delete::before {
            display:none!important;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-type {
            grid-column:3/7;
            grid-row:1;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-width {
            grid-column:1/3;
            grid-row:2;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-length {
            grid-column:3/5;
            grid-row:2;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-qty {
            grid-column:5/7;
            grid-row:2;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-rotate {
            grid-column:1/3;
            grid-row:3;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-edges {
            grid-column:3/7;
            grid-row:3;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-edge-type {
            grid-column:1/4;
            grid-row:4;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-sketch {
            grid-column:4/7;
            grid-row:4;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-notes {
            grid-column:1/6;
            grid-row:5;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-delete {
            grid-column:6;
            grid-row:5;
            justify-content:flex-end;
        }
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-calc,
        .dco-mobile-piece-cards .dco-fast-table tbody .dco-col-delete:empty {
            display:none!important;
        }
        .dco-mobile-piece-cards .dco-fast-table :where(.dco-fast-input,.dco-fast-select,.dco-notes-expand,.dco-check-toggle,.dco-special-sketch-button,.dco-delete-row) {
            width:100%!important;
            min-width:0!important;
            min-height:var(--dco-compact-control-height)!important;
            height:var(--dco-compact-control-height)!important;
            margin:0!important;
            padding-block:3px!important;
            font-size:16px!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-check-toggle {
            padding-inline:3px!important;
            font-size:10px!important;
            line-height:1.1!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-special-sketch-button {
            font-size:11px!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-special-sketch-button > span:last-child {
            display:inline!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-edge-buttons {
            display:grid!important;
            grid-template-columns:repeat(4,minmax(0,1fr))!important;
            gap:3px!important;
            width:100%;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-col-edges .dco-check-toggle {
            min-height:var(--dco-compact-control-height)!important;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-notes-editor {
            display:grid!important;
            grid-template-columns:minmax(0,1fr) var(--dco-compact-control-height)!important;
            gap:4px!important;
            width:100%;
        }
        .dco-mobile-piece-cards .dco-fast-table .dco-row-selector {
            width:20px!important;
            height:20px!important;
            margin:0!important;
        }
        .dco-mobile-piece-cards .dco-bulk-footer {
            position:static!important;
            display:grid!important;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:6px!important;
            width:100%;
            margin-top:7px;
            padding:7px!important;
            border:1px solid var(--border-color,#dfe3e8)!important;
            border-radius:9px!important;
            background:var(--card-bg,var(--fg-color,#fff));
            box-shadow:none!important;
        }
        .dco-mobile-piece-cards .dco-selection-actions {
            display:grid!important;
            grid-column:1/-1;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:5px;
            width:100%;
        }
        .dco-mobile-piece-cards .dco-selection-actions[hidden] {
            display:none!important;
        }
        .dco-mobile-piece-cards .dco-bulk-footer :where(.btn,button) {
            width:100%!important;
            min-width:0!important;
            min-height:38px!important;
            padding:5px 7px!important;
            font-size:11px!important;
        }
        @media(max-width:360px) {
            .dco-mobile-piece-cards .dco-fast-table tbody tr {
                gap:5px;
                padding:6px!important;
            }
            .dco-mobile-piece-cards .dco-fast-table .dco-check-toggle {
                font-size:9px!important;
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

    function deviceShortSide() {
        const screenWidth = positiveWidth(window.screen && window.screen.width);
        const screenHeight = positiveWidth(window.screen && window.screen.height);
        if (screenWidth && screenHeight) return Math.min(screenWidth, screenHeight);
        return screenWidth || screenHeight || Number.POSITIVE_INFINITY;
    }

    function availableWidth(root) {
        const documentWidth = positiveWidth(document.documentElement && document.documentElement.clientWidth);
        const viewportWidth = positiveWidth(window.innerWidth);
        const rootWidth = positiveWidth(root && root.getBoundingClientRect().width);
        const widths = [documentWidth, viewportWidth, rootWidth].filter(Boolean);
        return widths.length ? Math.min(...widths) : Number.POSITIVE_INFINITY;
    }

    function shouldUseCardLayout(root) {
        return deviceShortSide() <= PHONE_SHORT_SIDE_MAX_WIDTH
            && availableWidth(root) <= PHONE_VIEWPORT_MAX_WIDTH;
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
