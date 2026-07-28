(() => {
    "use strict";

    const STYLE_ID = "dco-cut-dimensions-css";
    const EDGE_FIELDS = [
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ];

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function num(value) {
        if (value === null || value === undefined || value === "") return 0;
        const result = Number(String(value).replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function round(value, decimals = 3) {
        const factor = 10 ** decimals;
        return Math.round(num(value) * factor) / factor;
    }

    function format(value) {
        return String(round(value, 3));
    }

    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table .dco-col-cut-size {
                width:108px !important;
                min-width:108px !important;
                max-width:108px !important;
                text-align:center;
                padding-inline:4px !important;
            }
            .dco-cut-size-card {
                min-height:35px;
                display:flex;
                flex-direction:column;
                align-items:center;
                justify-content:center;
                gap:1px;
                border:1px solid rgba(36,144,239,.2);
                border-radius:8px;
                background:rgba(36,144,239,.045);
                padding:3px 4px;
                line-height:1.15;
            }
            .dco-cut-size-card.is-unchanged {
                border-color:var(--border-color,#dfe3e8);
                background:var(--subtle-fg,#f8f9fa);
            }
            .dco-cut-size-card.is-warning {
                border-color:rgba(217,119,6,.35);
                background:rgba(245,158,11,.08);
            }
            .dco-cut-size-value {
                direction:ltr;
                font-size:12px;
                font-weight:800;
                font-variant-numeric:tabular-nums;
                white-space:nowrap;
            }
            .dco-cut-size-meta {
                max-width:100%;
                overflow:hidden;
                text-overflow:ellipsis;
                white-space:nowrap;
                color:var(--text-muted,#6c7680);
                font-size:9px;
            }
            .dco-cut-rule-hint {
                display:inline-flex;
                align-items:center;
                gap:5px;
                border-radius:999px;
                padding:3px 8px;
                background:rgba(36,144,239,.08);
                color:var(--text-color,#36414c);
                font-weight:650;
            }
            @media (max-width:900px) {
                .dco-fast-table .dco-col-cut-size {
                    width:98px !important;
                    min-width:98px !important;
                    max-width:98px !important;
                }
                .dco-cut-size-value { font-size:11px; }
            }
        `;
        document.head.appendChild(style);
    }

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function edgeProfiles(frm) {
        if (!(frm._dco_edge_thicknesses instanceof Map)) {
            frm._dco_edge_thicknesses = new Map();
        }
        return frm._dco_edge_thicknesses;
    }

    function loadProfiles(frm) {
        if (frm._dco_cut_profiles_loading) return frm._dco_cut_profiles_loading;
        const request = frappe.db.get_list("Edge Banding Type", {
            fields: ["name", "edge_type_name", "thickness_mm"],
            filters: { disabled: 0 },
            order_by: "width_cm asc, edge_type_name asc",
            limit: 200,
        }).then(rows => {
            const profiles = edgeProfiles(frm);
            profiles.clear();
            (rows || []).forEach(row => {
                const name = row.name || row.edge_type_name;
                if (name) profiles.set(String(name), Math.max(0, num(row.thickness_mm)));
            });
            schedule(frm);
        }).catch(error => {
            console.error("Failed to load edge thicknesses", error);
        }).finally(() => {
            frm._dco_cut_profiles_loading = null;
        });
        frm._dco_cut_profiles_loading = request;
        return request;
    }

    function dataFromVirtualRow(tr) {
        const value = fieldname => {
            const control = tr.querySelector(`[data-field='${fieldname}']`);
            return control ? control.value : "";
        };
        const checked = fieldname => {
            const button = tr.querySelector(`[data-check-field='${fieldname}']`);
            return button && button.classList.contains("is-checked") ? 1 : 0;
        };
        return {
            width_cm: value("width_cm"),
            length_cm: value("length_cm"),
            edge_type: value("edge_type"),
            edge_long_right: checked("edge_long_right"),
            edge_long_left: checked("edge_long_left"),
            edge_width_top: checked("edge_width_top"),
            edge_width_bottom: checked("edge_width_bottom"),
        };
    }

    function rowData(frm, tr) {
        const row = rowByName(frm, tr.dataset.rowName || "");
        return row || dataFromVirtualRow(tr);
    }

    function calculate(frm, row) {
        const finalWidth = num(row.width_cm);
        const finalLength = num(row.length_cm);
        const longSides = Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left));
        const widthSides = Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom));
        const selectedSides = longSides + widthSides;
        const edgeType = String(row.edge_type || frm.doc.default_edge_type || "");
        const profiles = edgeProfiles(frm);
        const profileKnown = !edgeType || profiles.has(edgeType);
        const thickness = selectedSides && edgeType ? num(profiles.get(edgeType)) : 0;
        const widthDeduction = thickness * longSides;
        const lengthDeduction = thickness * widthSides;
        const cutWidth = round(finalWidth - (widthDeduction / 10), 3);
        const cutLength = round(finalLength - (lengthDeduction / 10), 3);

        return {
            finalWidth,
            finalLength,
            cutWidth,
            cutLength,
            edgeType,
            thickness,
            widthDeduction,
            lengthDeduction,
            selectedSides,
            missingType: selectedSides > 0 && !edgeType,
            loadingProfile: selectedSides > 0 && edgeType && !profileKnown,
            valid: finalWidth > 0 && finalLength > 0 && cutWidth > 0 && cutLength > 0,
        };
    }

    function syncCalculatedFields(row, result) {
        if (!row || !row.doctype || !result.valid) return;
        row.edge_thickness_mm = result.thickness;
        row.cut_width_cm = result.cutWidth;
        row.cut_length_cm = result.cutLength;
        row.cut_size_label = `${format(result.cutWidth)} × ${format(result.cutLength)}`;
    }

    function metadata(result) {
        if (result.missingType) return isArabic() ? "حدد نوع القشاط" : "Select edge type";
        if (result.loadingProfile) return isArabic() ? "تحميل السماكة..." : "Loading thickness...";
        if (!result.selectedSides || !result.thickness) return isArabic() ? "بدون خصم" : "No deduction";
        const parts = [];
        if (result.widthDeduction) {
            parts.push(isArabic()
                ? `خصم ${format(result.widthDeduction)} مم عرض`
                : `${format(result.widthDeduction)} mm width`);
        }
        if (result.lengthDeduction) {
            parts.push(isArabic()
                ? `خصم ${format(result.lengthDeduction)} مم طول`
                : `${format(result.lengthDeduction)} mm length`);
        }
        return parts.join("، ");
    }

    function tooltip(result) {
        const finished = `${format(result.finalWidth)} × ${format(result.finalLength)}`;
        const cutting = `${format(result.cutWidth)} × ${format(result.cutLength)}`;
        const thickness = format(result.thickness);
        return isArabic()
            ? `القياس النهائي: ${finished} سم | قياس القص: ${cutting} سم | سماكة القشاط: ${thickness} مم`
            : `Finished size: ${finished} cm | Cut size: ${cutting} cm | Edge thickness: ${thickness} mm`;
    }

    function renderCell(frm, tr, cell) {
        const row = rowData(frm, tr);
        const result = calculate(frm, row);
        const persistentRow = rowByName(frm, tr.dataset.rowName || "");
        syncCalculatedFields(persistentRow, result);

        const warning = result.missingType || result.loadingProfile || !result.valid;
        const unchanged = !result.selectedSides || !result.thickness;
        const label = result.valid
            ? `${format(result.cutWidth)} × ${format(result.cutLength)}`
            : "—";
        cell.innerHTML = `
            <div class="dco-cut-size-card ${warning ? "is-warning" : ""} ${unchanged ? "is-unchanged" : ""}" title="${escapeHtml(tooltip(result))}">
                <span class="dco-cut-size-value">${escapeHtml(label)}</span>
                <span class="dco-cut-size-meta">${escapeHtml(metadata(result))}</span>
            </div>`;
    }

    function ensureHeader(root) {
        const edgeHeader = root.querySelector(".dco-fast-table thead th.dco-col-edge-type");
        if (!edgeHeader) return;
        let header = root.querySelector(".dco-fast-table thead th.dco-col-cut-size");
        if (!header) {
            header = document.createElement("th");
            header.className = "dco-col-cut-size";
            edgeHeader.insertAdjacentElement("afterend", header);
        }
        header.textContent = isArabic() ? "مقاس القص" : "Cut size";
        header.title = isArabic()
            ? "يُحسب تلقائيًا من القياس النهائي بعد خصم سماكة القشاط"
            : "Calculated from the finished size after edge allowance";
    }

    function ensureRowCells(frm, root) {
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => {
            const edgeCell = tr.querySelector(":scope > td.dco-col-edge-type");
            if (!edgeCell) return;
            let cell = tr.querySelector(":scope > td.dco-col-cut-size");
            if (!cell) {
                cell = document.createElement("td");
                cell.className = "dco-col-cut-size";
                edgeCell.insertAdjacentElement("afterend", cell);
            }
            renderCell(frm, tr, cell);
        });
    }

    function ensureHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help || help.querySelector(".dco-cut-rule-hint")) return;
        const hint = document.createElement("span");
        hint.className = "dco-cut-rule-hint";
        hint.textContent = isArabic()
            ? "المدخل نهائي ← مقاس القص يُحسب تلقائيًا"
            : "Enter finished size → cut size is automatic";
        help.appendChild(hint);
    }

    function installObserver(frm, root) {
        if (root._dcoCutDimensionObserver) return;
        let queued = false;
        const observer = new MutationObserver(() => {
            if (queued) return;
            queued = true;
            requestAnimationFrame(() => {
                queued = false;
                apply(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoCutDimensionObserver = observer;

        const scheduleAfterEvent = event => {
            if (!event.target.closest("[data-field],[data-check-field]")) return;
            requestAnimationFrame(() => apply(frm));
        };
        root.addEventListener("input", scheduleAfterEvent);
        root.addEventListener("change", scheduleAfterEvent);
        root.addEventListener("click", scheduleAfterEvent);
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        ensureHeader(root);
        ensureRowCells(frm, root);
        ensureHelp(root);
        installObserver(frm, root);
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            loadProfiles(frm);
            schedule(frm);
        },
        refresh(frm) {
            loadProfiles(frm);
            schedule(frm);
        },
        default_edge_type(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm(frm) { schedule(frm); },
        length_cm(frm) { schedule(frm); },
        edge_type(frm) { schedule(frm); },
        edge_long_right(frm) { schedule(frm); },
        edge_long_left(frm) { schedule(frm); },
        edge_width_top(frm) { schedule(frm); },
        edge_width_bottom(frm) { schedule(frm); },
    });
})();
