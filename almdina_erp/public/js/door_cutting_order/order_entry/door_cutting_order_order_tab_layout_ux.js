(() => {
    "use strict";

    if (window.AlmdinaOrderTabLayoutUX) return;

    const STYLE_ID = "dco-order-tab-layout-css";
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
        edge_color: "أدخل لون القشاط",
    });

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .${ROOT_CLASS} [data-fieldname="order_details_section"],
                .${ROOT_CLASS} [data-fieldname="board_section"],
                .${ROOT_CLASS} [data-fieldname="pieces_section"] {
                    scroll-margin-top: 92px;
                }
                .${ROOT_CLASS} .dco-order-intake-card,
                .${ROOT_CLASS} .dco-material-edge-card {
                    margin: 10px 0 14px !important;
                    padding: 6px 16px 14px !important;
                    border: 1px solid var(--border-color,#dfe3e8) !important;
                    border-radius: 14px !important;
                    background: var(--card-bg,var(--fg-color,#fff)) !important;
                    box-shadow: 0 2px 10px rgba(15,23,42,.035) !important;
                }
                .${ROOT_CLASS} .dco-measurements-card {
                    margin: 14px 0 0 !important;
                    padding: 4px 0 0 !important;
                    border: 0 !important;
                    border-radius: 0 !important;
                    background: transparent !important;
                    box-shadow: none !important;
                }
                .${ROOT_CLASS} .dco-order-section-heading {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 12px;
                    width: 100%;
                    padding: 7px 0 11px;
                }
                .${ROOT_CLASS} .dco-order-section-heading__copy { min-width: 0; }
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

                /*
                 * Frappe owns the native controls and their values. These two
                 * section bodies only become layout grids; their original
                 * form-column wrappers participate through display:contents so no
                 * field is cloned, moved to another state owner, or reimplemented.
                 */
                .${ROOT_CLASS} .dco-order-intake-card > .section-body {
                    display: grid !important;
                    grid-template-columns: minmax(0,2fr) minmax(220px,1fr);
                    gap: 12px 16px;
                    direction: rtl;
                    align-items: start;
                }
                .${ROOT_CLASS} .dco-material-edge-card > .section-body {
                    display: grid !important;
                    grid-template-columns: repeat(4,minmax(0,1fr));
                    gap: 12px 14px;
                    direction: rtl;
                    align-items: start;
                }
                .${ROOT_CLASS} .dco-order-intake-card > .section-body > .form-column,
                .${ROOT_CLASS} .dco-material-edge-card > .section-body > .form-column {
                    display: contents !important;
                }

                .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="customer"] {
                    grid-column: 1;
                    grid-row: 1;
                }
                .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_date"] {
                    grid-column: 2;
                    grid-row: 1;
                }
                .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_notes"] {
                    grid-column: 1 / -1;
                    grid-row: 2;
                }

                .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="board_description"] {
                    grid-column: 1 / span 2;
                    grid-row: 1;
                }
                .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="board_length_cm"] {
                    grid-column: 3;
                    grid-row: 1;
                }
                .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="board_width_cm"] {
                    grid-column: 4;
                    grid-row: 1;
                }
                .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="default_edge_type"] {
                    grid-column: 1 / span 2;
                    grid-row: 2;
                }
                .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="edge_color"] {
                    grid-column: 3 / span 2;
                    grid-row: 2;
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
                    min-height: 72px !important;
                    max-height: 170px !important;
                    resize: none !important;
                    overflow-y: auto !important;
                    line-height: 1.55 !important;
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
                    background: rgba(36,144,239,.07);
                    color: var(--primary,#2490ef);
                    font-size: 9.5px;
                    font-weight: 800;
                }
                .${ROOT_CLASS} .dco-edge-color-origin.is-override {
                    background: rgba(181,112,28,.10);
                    color: #9a5b12;
                }

                @media (max-width: 980px) {
                    .${ROOT_CLASS} .dco-order-intake-card > .section-body {
                        grid-template-columns: minmax(0,1.5fr) minmax(190px,1fr);
                    }
                    .${ROOT_CLASS} .dco-material-edge-card > .section-body {
                        grid-template-columns: repeat(2,minmax(0,1fr));
                    }
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="board_description"] {
                        grid-column: 1 / -1;
                        grid-row: auto;
                    }
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="board_length_cm"] {
                        grid-column: 1;
                        grid-row: auto;
                    }
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="board_width_cm"] {
                        grid-column: 2;
                        grid-row: auto;
                    }
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="default_edge_type"],
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="edge_color"] {
                        grid-column: auto;
                        grid-row: auto;
                    }
                }
                @media (max-width: 700px) {
                    .${ROOT_CLASS} .dco-order-intake-card,
                    .${ROOT_CLASS} .dco-material-edge-card {
                        padding: 5px 11px 12px !important;
                        border-radius: 12px !important;
                    }
                    .${ROOT_CLASS} .dco-order-intake-card > .section-body {
                        grid-template-columns: 1fr;
                        gap: 9px;
                    }
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="customer"],
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_date"],
                    .${ROOT_CLASS} .dco-order-intake-card [data-fieldname="order_notes"] {
                        grid-column: 1;
                        grid-row: auto;
                    }
                    .${ROOT_CLASS} .dco-material-edge-card > .section-body {
                        grid-template-columns: repeat(2,minmax(0,1fr));
                        gap: 9px;
                    }
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="default_edge_type"],
                    .${ROOT_CLASS} .dco-material-edge-card [data-fieldname="edge_color"] {
                        grid-column: 1 / -1;
                    }
                    .${ROOT_CLASS} .dco-order-section-heading {
                        align-items: center;
                        padding-bottom: 9px;
                    }
                    .${ROOT_CLASS} .dco-order-section-heading__subtitle { max-width: 240px; }
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

    function ensureHeading(frm, fieldname, config) {
        const section = sectionNode(frm, fieldname);
        if (!section) return null;
        section.classList.add(config.className);
        let heading = section.querySelector(":scope > .dco-order-section-heading");
        if (!heading) {
            heading = document.createElement("div");
            heading.className = "dco-order-section-heading";
            const body = section.querySelector(":scope > .section-body") || section.firstElementChild;
            section.insertBefore(heading, body || null);
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

    function autoGrowNotes(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_notes;
        const textarea = field && field.$input && field.$input.get(0);
        if (!textarea) return;
        const resize = () => {
            textarea.style.height = "auto";
            const next = Math.min(170, Math.max(72, textarea.scrollHeight || 72));
            textarea.style.height = `${next}px`;
        };
        if (!textarea.__almdinaAutoGrowBound) {
            textarea.addEventListener("input", resize);
            textarea.__almdinaAutoGrowBound = true;
        }
        resize();
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
        Object.entries(SECTION_COPY).forEach(([fieldname, config]) => ensureHeading(frm, fieldname, config));
        keepEmptyFieldsVisible(frm);
        autoGrowNotes(frm);
        renderEdgeColorOrigin(frm);
        removeLegacyRequiredHint(frm);
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
        customer(frm) { schedule(frm); },
        order_date(frm) { schedule(frm); },
        order_notes(frm) { schedule(frm); },
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