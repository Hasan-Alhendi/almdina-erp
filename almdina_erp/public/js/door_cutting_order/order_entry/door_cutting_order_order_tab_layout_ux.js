(() => {
    "use strict";

    if (window.AlmdinaOrderTabLayoutUX) return;

    const STYLE_ID = "dco-order-tab-layout-css-v3";
    const LEGACY_STYLE_IDS = Object.freeze([
        "dco-order-tab-layout-css",
        "dco-order-tab-layout-css-v2",
    ]);
    const ROOT_CLASS = "dco-order-tab-layout";

    const SECTION_COPY = Object.freeze({
        order_details_section: Object.freeze({
            className: "dco-order-intake-card",
            title: "بيانات الطلب",
            subtitle: "معلومات العميل والطلب الأساسية.",
        }),
        board_section: Object.freeze({
            className: "dco-material-edge-card",
            title: "المادة والقشاط",
            subtitle: "حدد اللوح والقشاط الافتراضي لهذا الطلب.",
        }),
        pieces_section: Object.freeze({
            className: "dco-measurements-card",
            title: "قياسات الدرف",
            subtitle: "أدخل أبعاد وكميات القطع؛ هذا هو سطح العمل الرئيسي للطلب.",
        }),
    });

    const ALWAYS_VISIBLE_FIELDS = Object.freeze({
        order_notes: "أضف ملاحظة للطلب…",
        order_cutting_machine: "اختر آلة القص",
        edge_color: "أدخل لون القشاط",
    });

    const INTAKE_ROWS = Object.freeze({
        pair: Object.freeze(["customer", "order_date"]),
        notes: Object.freeze(["order_notes"]),
        machine: Object.freeze(["order_cutting_machine"]),
    });

    const MATERIAL_ROWS = Object.freeze({
        primary: Object.freeze([
            "board_description",
            "board_length_cm",
            "board_width_cm",
        ]),
        edge: Object.freeze([
            "default_edge_type",
            "edge_color",
        ]),
    });

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function installStyles() {
        LEGACY_STYLE_IDS.forEach((id) => {
            const legacy = document.getElementById(id);
            if (legacy) legacy.remove();
        });
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .${ROOT_CLASS} .layout-main-section .form-page,
                .${ROOT_CLASS} .layout-main-section-wrapper .form-page {
                    max-width: var(--dco-tab-shell-max, 1440px) !important;
                    margin-inline: auto !important;
                    width: 100% !important;
                    padding-inline: var(--dco-tab-content-gutter, 20px) !important;
                    box-sizing: border-box !important;
                }
                .${ROOT_CLASS} .dco-status-strip,
                .${ROOT_CLASS} .dco-board-summary,
                .${ROOT_CLASS} .form-section.dco-order-status-shell,
                .${ROOT_CLASS} .form-section:has([data-fieldname="operator_status_strip"]) {
                    width: 100% !important;
                    max-width: none !important;
                    /* Vertical rhythm between sections comes from the tab-pane row-gap token. */
                    margin: 0 !important;
                    padding: 0 !important;
                    border-bottom: none !important;
                }
                .${ROOT_CLASS} .form-section.dco-order-status-shell > .section-body,
                .${ROOT_CLASS} .form-section:has([data-fieldname="operator_status_strip"]) > .section-body,
                .${ROOT_CLASS} .form-section.dco-order-status-shell .form-column,
                .${ROOT_CLASS} .form-section:has([data-fieldname="operator_status_strip"]) .form-column {
                    width: 100% !important;
                    max-width: none !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    flex: 1 1 100% !important;
                }
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"],
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .frappe-control,
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .form-group,
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .control-input-wrapper {
                    max-width: none !important;
                    width: 100% !important;
                    margin-inline: 0 !important;
                    box-sizing: border-box !important;
                }
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"] {
                    margin-block: 0 !important;
                    padding: 0 !important;
                }
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .dco-order-tracking-strip,
                .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .frappe-card {
                    width: 100% !important;
                    max-width: none !important;
                    margin: 0 !important;
                    padding-block: 8px 9px !important;
                    padding-inline: var(--dco-tab-card-inset-inline, 44px) !important;
                    border-radius: 12px !important;
                    border-top: 1px solid var(--border-color,#dfe3e8) !important;
                    border-inline-end: 1px solid var(--border-color,#dfe3e8) !important;
                    border-bottom: 1px solid var(--border-color,#dfe3e8) !important;
                    box-shadow: 0 2px 10px rgba(15,23,42,.035) !important;
                    box-sizing: border-box !important;
                }
                .${ROOT_CLASS} .dco-order-intake-card,
                .${ROOT_CLASS} .dco-material-edge-card,
                .${ROOT_CLASS} .dco-measurements-card {
                    width: 100% !important;
                    box-sizing: border-box !important;
                }
                .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) {
                    display: grid !important;
                    grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
                    column-gap: 14px;
                    row-gap: var(--dco-section-stack-gap, 8px);
                    width: 100% !important;
                    max-width: 100% !important;
                    align-items: stretch;
                    box-sizing: border-box;
                }
                .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) > .form-section:not(.dco-order-intake-card):not(.dco-material-edge-card) {
                    grid-column: 1 / -1;
                    width: 100% !important;
                    max-width: 100% !important;
                    min-width: 0;
                }
                .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) > .dco-order-intake-card {
                    grid-column: 1;
                    min-width: 0;
                }
                .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) > .dco-material-edge-card {
                    grid-column: 2;
                    min-width: 0;
                }
                .${ROOT_CLASS} [data-fieldname="order_details_section"],
                .${ROOT_CLASS} [data-fieldname="board_section"],
                .${ROOT_CLASS} [data-fieldname="pieces_section"] {
                    scroll-margin-top: 92px;
                }
                .${ROOT_CLASS} .dco-order-intake-card,
                .${ROOT_CLASS} .dco-material-edge-card {
                    margin-block: 0 !important;
                    padding-block: var(--dco-tab-card-inset-block, 12px 14px) !important;
                    padding-inline: var(--dco-tab-card-inset-inline, 44px) !important;
                    border: 1px solid var(--alm-card-border,#e4e8ee) !important;
                    border-radius: var(--alm-radius-card,16px) !important;
                    background: var(--alm-card,#fff) !important;
                    box-shadow: var(--alm-shadow-card,0 8px 24px rgba(15,23,42,.045)) !important;
                    display: flex !important;
                    flex-direction: column !important;
                    min-height: 0;
                    height: 100%;
                }
                .${ROOT_CLASS} .dco-order-intake-card > .dco-order-section-heading,
                .${ROOT_CLASS} .dco-material-edge-card > .dco-order-section-heading {
                    width: 100%;
                    box-sizing: border-box;
                    flex: 0 0 auto;
                }
                .${ROOT_CLASS} .dco-order-intake-card > .section-body {
                    display: flex !important;
                    flex-direction: column !important;
                    flex: 1 1 auto;
                    direction: rtl;
                    width: 100% !important;
                    max-width: none !important;
                    margin: 0 !important;
                    box-sizing: border-box;
                    gap: 10px;
                }
                .${ROOT_CLASS} .dco-order-intake-card > .section-body > .dco-order-section-heading {
                    margin-bottom: 0;
                    flex: 0 0 auto;
                }
                .${ROOT_CLASS} .dco-measurements-card {
                    margin-block: 0 0 !important;
                    padding-block: var(--dco-tab-card-inset-block, 12px 14px) !important;
                    padding-inline: var(--dco-tab-card-inset-inline, 44px) !important;
                    border: 1px solid var(--alm-card-border, #e4e8ee) !important;
                    border-radius: var(--alm-radius-card, 16px) !important;
                    background: var(--alm-card, #fff) !important;
                    box-shadow: var(--alm-shadow-card, 0 8px 24px rgba(15, 23, 42, .045)) !important;
                }
                .${ROOT_CLASS} .dco-order-section-heading {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 12px;
                    width: 100%;
                    padding: 0 0 10px;
                    margin: 0;
                }
                .${ROOT_CLASS} .dco-order-section-heading__copy {
                    min-width: 0;
                    padding-inline: 0;
                }
                .${ROOT_CLASS} .dco-order-intake-card.form-section,
                .${ROOT_CLASS} .dco-material-edge-card.form-section,
                .${ROOT_CLASS} .dco-measurements-card.form-section {
                    padding-inline: var(--dco-tab-card-inset-inline, 44px) !important;
                }
                .${ROOT_CLASS} .dco-order-intake-card .frappe-control,
                .${ROOT_CLASS} .dco-material-edge-card .frappe-control,
                .${ROOT_CLASS} .dco-material-edge-card .form-group {
                    padding-inline: 0 !important;
                    margin-inline: 0 !important;
                }
                .${ROOT_CLASS} .dco-order-intake-card .frappe-control .control-label,
                .${ROOT_CLASS} .dco-material-edge-card .frappe-control .control-label,
                .${ROOT_CLASS} .dco-material-edge-card .form-group .control-label,
                .${ROOT_CLASS} .dco-measurements-card .dco-fast-entry-toolbar {
                    padding-inline: 0 !important;
                    margin-inline: 0 !important;
                }
                .${ROOT_CLASS} .dco-order-section-heading__title,
                .${ROOT_CLASS} .dco-order-section-heading__subtitle {
                    padding-inline: 0;
                    text-align: start;
                }
                .${ROOT_CLASS} .dco-order-section-heading__title {
                    display: block;
                    margin: 0;
                    color: var(--text-color,#26313b);
                    font-size: 15px;
                    font-weight: 850;
                    line-height: 1.45;
                }
                .${ROOT_CLASS} .dco-order-section-heading__subtitle {
                    display: block;
                    margin-top: 3px;
                    color: var(--text-muted,#687481);
                    font-size: 10.5px;
                    font-weight: 550;
                    line-height: 1.55;
                }
                .${ROOT_CLASS} .dco-order-section-heading__meta {
                    display: inline-flex;
                    align-items: center;
                    min-height: 25px;
                    padding: 3px 9px;
                    border-radius: 999px;
                    background: var(--subtle-fg,#f4f6f8);
                    color: var(--text-muted,#687481);
                    font-size: 10px;
                    font-weight: 800;
                    white-space: nowrap;
                }
                .${ROOT_CLASS} .dco-order-intake-card > .section-head,
                .${ROOT_CLASS} .dco-material-edge-card > .section-head,
                .${ROOT_CLASS} .dco-measurements-card > .section-head {
                    display: none !important;
                }
                .${ROOT_CLASS} .dco-order-intake-card > .section-body,
                .${ROOT_CLASS} .dco-material-edge-card > .section-body,
                .${ROOT_CLASS} .dco-measurements-card > .section-body {
                    padding-inline: 0 !important;
                    padding-top: 0 !important;
                    margin: 0 !important;
                    max-width: none !important;
                    width: 100% !important;
                }

                /* Order intake rows — explicit DOM rows (see ensureIntakeRows). */
                .${ROOT_CLASS} .dco-order-intake-card > .section-body > .form-column {
                    display: none !important;
                }
                .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="important_note_preview"],
                .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="important_note_comment"] {
                    display: none !important;
                }
                .${ROOT_CLASS} .dco-intake-row {
                    display: grid;
                    direction: rtl;
                    gap: 10px 16px;
                    align-items: start;
                    width: 100%;
                    flex: 0 0 auto;
                }
                .${ROOT_CLASS} .dco-intake-row + .dco-intake-row {
                    margin-top: 0;
                }
                .${ROOT_CLASS} .dco-intake-row--machine {
                    margin-top: 2px;
                }
                .${ROOT_CLASS} .dco-intake-row--pair {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
                .${ROOT_CLASS} .dco-intake-row--notes,
                .${ROOT_CLASS} .dco-intake-row--machine {
                    grid-template-columns: minmax(0, 1fr);
                }
                .${ROOT_CLASS} .dco-intake-row > .frappe-control,
                .${ROOT_CLASS} .dco-intake-row > .form-group {
                    min-width: 0;
                    width: 100% !important;
                    max-width: none !important;
                    margin-bottom: 0 !important;
                }
                .${ROOT_CLASS} .dco-intake-row--notes [data-fieldname="order_notes"] .form-group,
                .${ROOT_CLASS} .dco-intake-row--notes [data-fieldname="order_notes"] .frappe-control,
                .${ROOT_CLASS} .dco-intake-row--notes [data-fieldname="order_notes"] .control-input-wrapper,
                .${ROOT_CLASS} .dco-intake-row--notes [data-fieldname="order_notes"] textarea {
                    width: 100% !important;
                    max-width: none !important;
                }
                .${ROOT_CLASS} .dco-intake-row--machine [data-fieldname="order_cutting_machine"] .form-group,
                .${ROOT_CLASS} .dco-intake-row--machine [data-fieldname="order_cutting_machine"] .frappe-control,
                .${ROOT_CLASS} .dco-intake-row--machine [data-fieldname="order_cutting_machine"] .dco-cutting-machine-host {
                    width: 100% !important;
                    max-width: none !important;
                }
                .${ROOT_CLASS} .dco-intake-row--machine [data-fieldname="order_cutting_machine"] .dco-cutting-machine-row {
                    width: auto;
                    max-width: 100%;
                    flex-wrap: wrap;
                }

                /*
                 * Material layout is explicit rather than inferred from Frappe's
                 * Column Break DOM. We move the original field wrappers only;
                 * controls, values, event handlers and document state remain owned
                 * by Frappe. This guarantees the exact visual rows requested.
                 */
                .${ROOT_CLASS} .dco-material-edge-card > .section-body {
                    display: flex !important;
                    flex-direction: column !important;
                    flex: 1 1 auto;
                    justify-content: space-between;
                    gap: 12px;
                    min-height: 0;
                }
                .${ROOT_CLASS} .dco-material-edge-card > .section-body > .form-column {
                    display: none !important;
                }
                .${ROOT_CLASS} .dco-material-edge-card > .section-body > .dco-order-section-heading {
                    flex: 0 0 auto;
                    margin-bottom: 0;
                }
                .${ROOT_CLASS} .dco-material-row {
                    display: grid;
                    direction: rtl;
                    gap: 10px 14px;
                    align-items: start;
                    width: 100%;
                    flex: 0 0 auto;
                }
                .${ROOT_CLASS} .dco-material-row + .dco-material-row {
                    margin-top: 0;
                }
                .${ROOT_CLASS} .dco-material-row--primary {
                    grid-template-columns: minmax(0,2fr) minmax(140px,1fr) minmax(140px,1fr);
                }
                .${ROOT_CLASS} .dco-material-row--edge {
                    grid-template-columns: repeat(2,minmax(0,1fr));
                }
                .${ROOT_CLASS} .dco-material-row > .frappe-control,
                .${ROOT_CLASS} .dco-material-row > .form-group {
                    min-width: 0;
                    width: 100% !important;
                    margin-bottom: 0 !important;
                }

                .${ROOT_CLASS} .dco-keep-empty-field {
                    display: block !important;
                    visibility: visible !important;
                    min-width: 0;
                }
                .${ROOT_CLASS} .dco-empty-display:empty::before {
                    content: attr(data-dco-empty-placeholder);
                    color: var(--text-muted,#8a949e);
                    font-weight: 500;
                }
                .${ROOT_CLASS} [data-fieldname="order_notes"] textarea {
                    min-height: 38px !important;
                    max-height: 72px !important;
                    height: 38px !important;
                    resize: none !important;
                    overflow-x: hidden !important;
                    overflow-y: auto !important;
                    line-height: 1.45 !important;
                    white-space: normal !important;
                }
                .${ROOT_CLASS} .dco-order-notes-locked textarea:disabled,
                .${ROOT_CLASS} .dco-order-notes-locked textarea[readonly],
                .${ROOT_CLASS} .dco-order-notes-locked select:disabled,
                .${ROOT_CLASS} .dco-order-notes-locked input[type="radio"]:disabled {
                    cursor: not-allowed !important;
                    background: var(--subtle-fg,#f6f8fa) !important;
                    color: var(--text-color,#26313b) !important;
                    opacity: 1 !important;
                }
                .${ROOT_CLASS} [data-fieldname="board_description"] .help-box,
                .${ROOT_CLASS} [data-fieldname="edge_color"] .help-box {
                    margin-top: 5px !important;
                    color: var(--text-muted,#7b8793) !important;
                    font-size: 10px !important;
                    line-height: 1.45 !important;
                }
                .${ROOT_CLASS} .dco-edge-color-origin {
                    display: inline-flex;
                    align-items: center;
                    gap: 5px;
                    margin-top: 5px;
                    padding: 3px 7px;
                    border-radius: 999px;
                    background: color-mix(in srgb, var(--alm-primary, #172033) 7%, transparent);
                    color: var(--alm-primary,#172033);
                    font-size: 9.5px;
                    font-weight: 800;
                }
                .${ROOT_CLASS} .dco-edge-color-origin.is-override {
                    background: rgba(181,112,28,.10);
                    color: #9a5b12;
                }

                @media (max-width: 980px) {
                    .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) {
                        grid-template-columns: 1fr;
                        align-items: start;
                    }
                    .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) > .dco-order-intake-card,
                    .${ROOT_CLASS} .tab-pane.show.active:has(.dco-order-intake-card) > .dco-material-edge-card {
                        grid-column: 1 / -1;
                        height: auto;
                    }
                    .${ROOT_CLASS} .dco-material-edge-card > .section-body {
                        justify-content: flex-start;
                    }
                    .${ROOT_CLASS} .dco-intake-row--pair {
                        grid-template-columns: 1fr;
                    }
                    .${ROOT_CLASS} .dco-material-row--primary {
                        grid-template-columns: minmax(0,1.5fr) minmax(120px,1fr) minmax(120px,1fr);
                    }
                }
                @media (max-width: 700px) { 
                    .${ROOT_CLASS} .layout-main-section .form-page,
                    .${ROOT_CLASS} .layout-main-section-wrapper .form-page {
                        padding-inline: var(--dco-tab-content-gutter, 12px) !important;
                    }
                    .${ROOT_CLASS} .dco-order-intake-card,
                    .${ROOT_CLASS} .dco-material-edge-card {
                        padding-block: var(--dco-tab-card-inset-block, 10px 12px) !important;
                        padding-inline: var(--dco-tab-card-inset-inline, 32px) !important;
                        border-radius: 12px !important;
                        height: auto;
                    }
                    .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .dco-order-tracking-strip,
                    .${ROOT_CLASS} [data-fieldname="operator_status_strip"] .frappe-card {
                        padding-block: 7px 8px !important;
                        padding-inline: var(--dco-tab-card-inset-inline, 32px) !important;
                        border-radius: 12px !important;
                    }
                    .${ROOT_CLASS} .dco-order-intake-card > .section-body {
                        gap: 8px;
                    }
                    .${ROOT_CLASS} .dco-intake-row--pair {
                        grid-template-columns: 1fr;
                    }
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="customer"],
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_date"],
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_notes"],
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_cutting_machine"] {
                        max-width: none;
                    }
                    .${ROOT_CLASS} .dco-material-row--primary {
                        grid-template-columns: repeat(2,minmax(0,1fr));
                    }
                    .${ROOT_CLASS} .dco-material-row--primary [data-fieldname="board_description"] {
                        grid-column: 1 / -1;
                    }
                    .${ROOT_CLASS} .dco-material-row--edge {
                        grid-template-columns: 1fr;
                    }
                    .${ROOT_CLASS} .dco-order-section-heading {
                        align-items: center;
                        padding-bottom: 9px;
                    }
                    .${ROOT_CLASS} .dco-order-section-heading__subtitle { max-width: 240px; }
                    .${ROOT_CLASS} .layout-main-section .form-page:has(.dco-measurements-mobile-scroll),
                    .${ROOT_CLASS} .layout-main-section-wrapper .form-page:has(.dco-measurements-mobile-scroll) {
                        padding-inline: 20px !important;
                    }
                    .${ROOT_CLASS} .dco-measurements-card.dco-measurements-mobile-scroll,
                    .${ROOT_CLASS} .dco-measurements-card.form-section.dco-measurements-mobile-scroll {
                        padding-inline: 0 !important;
                        margin-inline: 0 !important;
                        width: 100% !important;
                        max-width: none !important;
                    }
                    .${ROOT_CLASS} .dco-measurements-card.dco-measurements-mobile-scroll > .section-body,
                    .${ROOT_CLASS} .dco-measurements-card.dco-measurements-mobile-scroll [data-fieldname="pieces_fast_entry"],
                    .${ROOT_CLASS} .dco-measurements-card.dco-measurements-mobile-scroll [data-fieldname="pieces_fast_entry"] .frappe-control,
                    .${ROOT_CLASS} .dco-measurements-card.dco-measurements-mobile-scroll [data-fieldname="pieces_fast_entry"] .control-input-wrapper {
                        width: 100% !important;
                        max-width: none !important;
                        margin-inline: 0 !important;
                        padding-inline: 0 !important;
                        box-sizing: border-box !important;
                    }
                    .${ROOT_CLASS} .dco-measurements-card.dco-measurements-mobile-scroll > .dco-order-section-heading {
                        padding-inline: 0 !important;
                    }
                }
            </style>
        `);
    }

    function fieldNode(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const wrapper = field && (field.$wrapper || field.wrapper);
        if (!wrapper) return null;
        return wrapper.nodeType ? wrapper : wrapper[0] || null;
    }

    function sectionNode(frm, fieldname) {
        const node = fieldNode(frm, fieldname);
        return node && node.closest ? node.closest(".form-section") : null;
    }

    function pieceCount(frm) {
        return (frm && frm.doc && Array.isArray(frm.doc.pieces))
            ? frm.doc.pieces.reduce((total, row) => total + Math.max(0, Number(row.qty || 0)), 0)
            : 0;
    }

    function ensureStatusShell(frm) {
        const node = fieldNode(frm, "operator_status_strip");
        const section = node && node.closest ? node.closest(".form-section") : null;
        if (section) section.classList.add("dco-order-status-shell");
    }

    function ensureHeading(frm, fieldname, config) {
        const section = sectionNode(frm, fieldname);
        const body = section && section.querySelector(":scope > .section-body");
        if (!section || !body) return null;
        section.classList.add(config.className);
        let heading = section.querySelector(":scope > .dco-order-section-heading")
            || body.querySelector(":scope > .dco-order-section-heading");
        if (!heading) {
            heading = document.createElement("div");
            heading.className = "dco-order-section-heading";
        }
        if (heading.parentElement !== body) {
            body.insertBefore(heading, body.firstChild || null);
        }
        const meta = fieldname === "pieces_section"
            ? `<span class="dco-order-section-heading__meta">${pieceCount(frm)} قطعة</span>`
            : "";
        heading.innerHTML = `
            <div class="dco-order-section-heading__copy">
                <strong class="dco-order-section-heading__title">${frappe.utils.escape_html(__(config.title))}</strong>
                <span class="dco-order-section-heading__subtitle">${frappe.utils.escape_html(__(config.subtitle))}</span>
            </div>
            ${meta}
        `;
        return section;
    }

    function removeTopRowWrapper(frm) {
        const root = formRoot(frm);
        if (!root) return;
        root.querySelectorAll(".dco-order-top-row").forEach((row) => {
            const parent = row.parentElement;
            if (!parent) return;
            while (row.firstElementChild) {
                parent.insertBefore(row.firstElementChild, row);
            }
            row.remove();
        });
    }

    function ensureIntakeRow(body, name) {
        let row = body.querySelector(`:scope > .dco-intake-row--${name}`);
        if (!row) {
            row = document.createElement("div");
            row.className = `dco-intake-row dco-intake-row--${name}`;
            body.appendChild(row);
        }
        return row;
    }

    function ensureIntakeRows(frm) {
        const section = sectionNode(frm, "order_details_section");
        const body = section && section.querySelector(":scope > .section-body");
        if (!body) return;

        const heading = body.querySelector(":scope > .dco-order-section-heading");
        const pair = ensureIntakeRow(body, "pair");
        const notes = ensureIntakeRow(body, "notes");
        const machine = ensureIntakeRow(body, "machine");

        let anchor = heading || null;
        [pair, notes, machine].forEach((row) => {
            if (anchor) {
                if (row.previousElementSibling !== anchor) {
                    anchor.insertAdjacentElement("afterend", row);
                }
                anchor = row;
            } else if (row.parentElement !== body) {
                body.appendChild(row);
            }
        });

        INTAKE_ROWS.pair.forEach((fieldname) => {
            const node = fieldNode(frm, fieldname);
            if (node && node.parentElement !== pair) pair.appendChild(node);
        });
        INTAKE_ROWS.notes.forEach((fieldname) => {
            const node = fieldNode(frm, fieldname);
            if (node && node.parentElement !== notes) notes.appendChild(node);
        });
        INTAKE_ROWS.machine.forEach((fieldname) => {
            const node = fieldNode(frm, fieldname);
            if (node && node.parentElement !== machine) machine.appendChild(node);
        });
    }

    function ensureMaterialRow(body, name) {
        let row = body.querySelector(`:scope > .dco-material-row--${name}`);
        if (!row) {
            row = document.createElement("div");
            row.className = `dco-material-row dco-material-row--${name}`;
            body.appendChild(row);
        }
        return row;
    }

    function ensureMaterialRows(frm) {
        const section = sectionNode(frm, "board_section");
        const body = section && section.querySelector(":scope > .section-body");
        if (!body) return;

        const primary = ensureMaterialRow(body, "primary");
        const edge = ensureMaterialRow(body, "edge");

        MATERIAL_ROWS.primary.forEach((fieldname) => {
            const node = fieldNode(frm, fieldname);
            if (node && node.parentElement !== primary) primary.appendChild(node);
        });
        MATERIAL_ROWS.edge.forEach((fieldname) => {
            const node = fieldNode(frm, fieldname);
            if (node && node.parentElement !== edge) edge.appendChild(node);
        });
    }

    function isOrderNotesEditable(frm) {
        if (!frm || !frm.doc) return false;
        if (frm.is_new && frm.is_new()) return true;
        const api = window.AlmdinaOrderRevisionUX;
        if (api && typeof api.isEditableDraft === "function") {
            return Boolean(api.isEditableDraft(frm));
        }
        return false;
    }

    function syncLockedInput(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const wrapper = fieldNode(frm, fieldname);
        const input = field && field.$input && field.$input.get(0);
        const editable = isOrderNotesEditable(frm);
        if (wrapper) wrapper.classList.toggle("dco-order-notes-locked", !editable);
        if (!input) return;
        input.disabled = !editable;
        input.readOnly = !editable;
        if (editable) {
            input.removeAttribute("aria-disabled");
        } else {
            input.setAttribute("aria-disabled", "true");
        }
    }

    function syncOrderNotesAccess(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_notes;
        const wrapper = fieldNode(frm, "order_notes");
        const textarea = field && field.$input && field.$input.get(0);
        const editable = isOrderNotesEditable(frm);
        if (wrapper) wrapper.classList.toggle("dco-order-notes-locked", !editable);
        if (textarea) {
            textarea.disabled = !editable;
            textarea.readOnly = !editable;
            if (editable) {
                textarea.removeAttribute("aria-disabled");
            } else {
                textarea.setAttribute("aria-disabled", "true");
            }
        }
        syncLockedInput(frm, "order_cutting_machine");
    }

    function autoGrowNotes(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_notes;
        const textarea = field && field.$input && field.$input.get(0);
        if (!textarea) return;
        textarea.rows = 1;
        textarea.style.height = "38px";
        textarea.style.minHeight = "38px";
        textarea.style.maxHeight = "38px";
    }

    function keepFieldVisible(frm, fieldname, placeholder) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        if (!field || (field.df && Number(field.df.hidden || 0) === 1)) return;
        const wrapper = fieldNode(frm, fieldname);
        if (!wrapper) return;

        wrapper.classList.add("dco-keep-empty-field");
        wrapper.classList.remove("hide-control");
        wrapper.removeAttribute("hidden");
        if (wrapper.style && wrapper.style.display === "none") wrapper.style.removeProperty("display");

        const input = field.$input && field.$input.get(0);
        if (input) input.setAttribute("placeholder", __(placeholder));

        const value = String((frm.doc && frm.doc[fieldname]) || "").trim();
        const display = wrapper.querySelector(".control-value, .like-disabled-input");
        if (!display) return;
        if (!value && !String(display.textContent || "").trim()) {
            display.classList.add("dco-empty-display");
            display.setAttribute("data-dco-empty-placeholder", __(placeholder));
        } else {
            display.classList.remove("dco-empty-display");
            display.removeAttribute("data-dco-empty-placeholder");
        }
    }

    function keepEmptyFieldsVisible(frm) {
        Object.entries(ALWAYS_VISIBLE_FIELDS).forEach(([fieldname, placeholder]) => {
            keepFieldVisible(frm, fieldname, placeholder);
        });
    }

    function edgeOptionSnapshot(frm) {
        const owner = window.AlmdinaOrderEdgeOptions;
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function edgeDefaultColor(frm) {
        const type = String((frm && frm.doc && frm.doc.default_edge_type) || "").trim();
        if (!type) return "";
        const snapshot = edgeOptionSnapshot(frm);
        const row = snapshot && Array.isArray(snapshot.options)
            ? snapshot.options.find((option) => String(option.name || option.edge_type_name || "").trim() === type)
            : null;
        return String((row && row.edge_color) || "").trim();
    }

    function renderEdgeColorOrigin(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.edge_color;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return;
        wrapper.find(".dco-edge-color-origin").remove();
        const current = String((frm.doc && frm.doc.edge_color) || "").trim();
        const defaultColor = edgeDefaultColor(frm);
        if (!current || !defaultColor) return;
        const overridden = current !== defaultColor;
        wrapper.append(`
            <span class="dco-edge-color-origin ${overridden ? "is-override" : ""}">
                ${frappe.utils.escape_html(__(overridden ? "معدل لهذا الطلب" : "مأخوذ تلقائيًا من نوع القشاط"))}
            </span>
        `);
    }

    function removeLegacyRequiredHint(frm) {
        const section = sectionNode(frm, "board_section");
        if (!section) return;
        section.querySelectorAll(".dco-required-material-hint").forEach((node) => node.remove());
    }

    function apply(frm) {
        const root = formRoot(frm);
        if (!root) return;
        installStyles();
        root.classList.add(ROOT_CLASS);
        ensureStatusShell(frm);
        Object.entries(SECTION_COPY).forEach(([fieldname, config]) => ensureHeading(frm, fieldname, config));
        removeTopRowWrapper(frm);
        ensureIntakeRows(frm);
        ensureMaterialRows(frm);
        keepEmptyFieldsVisible(frm);
        autoGrowNotes(frm);
        syncOrderNotesAccess(frm);
        renderEdgeColorOrigin(frm);
        removeLegacyRequiredHint(frm);
        const machine = window.AlmdinaOrderCuttingMachineUX;
        if (machine && typeof machine.schedule === "function") machine.schedule(frm);
    }

    function schedule(frm) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "order-tab-layout", () => apply(frm));
            return;
        }
        requestAnimationFrame(() => {
            if (window.cur_frm === frm) apply(frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        customer(frm) { schedule(frm); },
        order_date(frm) { schedule(frm); },
        order_notes(frm) { schedule(frm); },
        order_cutting_machine(frm) { schedule(frm); },
        board_description(frm) { schedule(frm); },
        board_length_cm(frm) { schedule(frm); },
        board_width_cm(frm) { schedule(frm); },
        default_edge_type(frm) { schedule(frm); },
        edge_color(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
    });

    window.AlmdinaOrderTabLayoutUX = Object.freeze({ apply, schedule });
})();