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
                .${ROOT_CLASS} .dco-order-section-heading__copy {
                    min-width: 0;
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
                .${ROOT_CLASS} .dco-order-primary-column {
                    flex: 0 0 44% !important;
                    max-width: 44% !important;
                }
                .${ROOT_CLASS} .dco-order-notes-column {
                    flex: 0 0 56% !important;
                    max-width: 56% !important;
                }
                .${ROOT_CLASS} .dco-material-board-column {
                    flex: 0 0 38% !important;
                    max-width: 38% !important;
                }
                .${ROOT_CLASS} .dco-material-size-column {
                    flex: 0 0 24% !important;
                    max-width: 24% !important;
                    display: grid !important;
                    grid-template-columns: repeat(2,minmax(0,1fr));
                    gap: 8px;
                    align-content: start;
                }
                .${ROOT_CLASS} .dco-material-edge-column {
                    flex: 0 0 38% !important;
                    max-width: 38% !important;
                }
                .${ROOT_CLASS} .dco-material-size-column > .frappe-control,
                .${ROOT_CLASS} .dco-material-size-column > .form-group {
                    min-width: 0;
                    width: 100% !important;
                    margin-bottom: 0 !important;
                }
                .${ROOT_CLASS} [data-fieldname="order_notes"] textarea {
                    min-height: 78px !important;
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
                .${ROOT_CLASS} .dco-required-material-hint {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    margin-top: 7px;
                    color: var(--text-muted,#687481);
                    font-size: 10px;
                    font-weight: 650;
                }
                .${ROOT_CLASS} .dco-required-material-hint__dot {
                    width: 6px;
                    height: 6px;
                    border-radius: 999px;
                    background: #ef4444;
                    flex: 0 0 auto;
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
                    .${ROOT_CLASS} .dco-order-primary-column,
                    .${ROOT_CLASS} .dco-order-notes-column,
                    .${ROOT_CLASS} .dco-material-board-column,
                    .${ROOT_CLASS} .dco-material-size-column,
                    .${ROOT_CLASS} .dco-material-edge-column {
                        flex: 0 0 50% !important;
                        max-width: 50% !important;
                    }
                    .${ROOT_CLASS} .dco-material-edge-column {
                        margin-top: 8px;
                    }
                }
                @media (max-width: 700px) {
                    .${ROOT_CLASS} .dco-order-intake-card,
                    .${ROOT_CLASS} .dco-material-edge-card {
                        padding: 5px 11px 12px !important;
                        border-radius: 12px !important;
                    }
                    .${ROOT_CLASS} .dco-order-primary-column,
                    .${ROOT_CLASS} .dco-order-notes-column,
                    .${ROOT_CLASS} .dco-material-board-column,
                    .${ROOT_CLASS} .dco-material-size-column,
                    .${ROOT_CLASS} .dco-material-edge-column {
                        flex: 0 0 100% !important;
                        max-width: 100% !important;
                    }
                    .${ROOT_CLASS} .dco-order-notes-column,
                    .${ROOT_CLASS} .dco-material-size-column,
                    .${ROOT_CLASS} .dco-material-edge-column {
                        margin-top: 6px;
                    }
                    .${ROOT_CLASS} .dco-material-size-column {
                        grid-template-columns: repeat(2,minmax(0,1fr));
                    }
                    .${ROOT_CLASS} .dco-order-section-heading {
                        align-items: center;
                        padding-bottom: 9px;
                    }
                    .${ROOT_CLASS} .dco-order-section-heading__subtitle {
                        max-width: 240px;
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

    function columnNode(frm, fieldname) {
        const node = fieldNode(frm, fieldname);
        return node && node.closest ? node.closest(".form-column") : null;
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

    function markColumns(frm) {
        const assignments = [
            ["customer", "dco-order-primary-column"],
            ["order_notes", "dco-order-notes-column"],
            ["board_description", "dco-material-board-column"],
            ["board_length_cm", "dco-material-size-column"],
            ["default_edge_type", "dco-material-edge-column"],
        ];
        assignments.forEach(([fieldname, className]) => {
            const column = columnNode(frm, fieldname);
            if (column) column.classList.add(className);
        });
    }

    function autoGrowNotes(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_notes;
        const textarea = field && field.$input && field.$input.get(0);
        if (!textarea) return;
        const resize = () => {
            textarea.style.height = "auto";
            const next = Math.min(170, Math.max(78, textarea.scrollHeight || 78));
            textarea.style.height = `${next}px`;
        };
        if (!textarea.__almdinaAutoGrowBound) {
            textarea.addEventListener("input", resize);
            textarea.__almdinaAutoGrowBound = true;
        }
        resize();
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

    function ensureRequiredHint(frm) {
        const section = sectionNode(frm, "board_section");
        if (!section) return;
        let hint = section.querySelector(".dco-required-material-hint");
        if (!hint) {
            hint = document.createElement("div");
            hint.className = "dco-required-material-hint";
            hint.innerHTML = `
                <span class="dco-required-material-hint__dot"></span>
                <span>${frappe.utils.escape_html(__("نوع القشاط ولون القشاط مطلوبان قبل حفظ الطلب."))}</span>
            `;
            section.appendChild(hint);
        }
    }

    function apply(frm) {
        const root = formRoot(frm);
        if (!root) return;
        installStyles();
        root.classList.add(ROOT_CLASS);
        Object.entries(SECTION_COPY).forEach(([fieldname, config]) => ensureHeading(frm, fieldname, config));
        markColumns(frm);
        autoGrowNotes(frm);
        renderEdgeColorOrigin(frm);
        ensureRequiredHint(frm);
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
