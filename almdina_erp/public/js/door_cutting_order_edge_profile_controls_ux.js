(() => {
    "use strict";

    const STYLE_ID = "dco-direct-edge-profile-controls-css";
    const BULK_DEFAULT_VALUE = "__almdina_default__";
    const SIDE_CONFIG = [
        {
            side: "long_right",
            selectedField: "edge_long_right",
            overrideField: "edge_long_right_type_override",
            labelAr: "الطول الأيمن",
            labelEn: "Right long edge",
        },
        {
            side: "long_left",
            selectedField: "edge_long_left",
            overrideField: "edge_long_left_type_override",
            labelAr: "الطول الأيسر",
            labelEn: "Left long edge",
        },
        {
            side: "width_top",
            selectedField: "edge_width_top",
            overrideField: "edge_width_top_type_override",
            labelAr: "العرض العلوي",
            labelEn: "Top width edge",
        },
        {
            side: "width_bottom",
            selectedField: "edge_width_bottom",
            overrideField: "edge_width_bottom_type_override",
            labelAr: "العرض السفلي",
            labelEn: "Bottom width edge",
        },
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

    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function materialize(frm, tr) {
        let row = rowByName(frm, tr && tr.dataset.rowName);
        if (row || !tr || !String(tr.dataset.rowName || "").startsWith("__virtual__")) {
            return row;
        }
        const qtyInput = tr.querySelector("input[data-field='qty']");
        if (qtyInput) qtyInput.dispatchEvent(new Event("input", { bubbles: true }));
        return rowByName(frm, tr.dataset.rowName);
    }

    function isEditable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0;
    }

    function moduleApi() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function profileMap(frm) {
        const api = moduleApi();
        if (!api || !api.profiles) return new Map();
        return api.profiles(frm);
    }

    function profileEntries(frm, current = "") {
        const values = new Map();
        profileMap(frm).forEach(profile => {
            const name = String((profile && profile.name) || "").trim();
            if (!name) return;
            values.set(name, String(profile.label || name));
        });
        if (current && !values.has(current)) values.set(current, current);
        return [...values.entries()];
    }

    function sideOptionsHtml(frm, current) {
        const defaultLabel = isArabic() ? "الافتراضي" : "Default";
        return [
            `<option value="">${defaultLabel}</option>`,
            ...profileEntries(frm, current).map(([value, label]) => (
                `<option value="${escapeHtml(value)}" ${value === current ? "selected" : ""}>${escapeHtml(label)}</option>`
            )),
        ].join("");
    }

    function bulkOptionsHtml(frm) {
        const placeholder = isArabic() ? "تطبيق على الأربعة" : "Apply to all four";
        const useDefault = isArabic() ? "الأربعة بالافتراضي" : "Default for all four";
        return [
            `<option value="">${placeholder}</option>`,
            `<option value="${BULK_DEFAULT_VALUE}">${useDefault}</option>`,
            ...profileEntries(frm).map(([value, label]) => (
                `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`
            )),
        ].join("");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table tbody td{vertical-align:bottom!important}
            .dco-fast-table .dco-col-edges{vertical-align:bottom!important;overflow:visible!important}
            .dco-fast-table .dco-col-edge-bulk{
                width:122px!important;min-width:122px!important;max-width:122px!important;
                text-align:center;padding-inline:4px!important;vertical-align:bottom!important
            }
            .dco-edge-bulk-toolbar,.dco-edge-direct-actions{display:none!important}
            .dco-side-profile-trigger{display:none!important}
            .dco-edge-bulk-cell-content{display:flex;align-items:flex-end;justify-content:center;min-height:39px;width:100%}
            .dco-all-sides-profile-select{
                width:100%;max-width:100%;height:39px;min-height:39px;border:1px solid rgba(36,144,239,.38);
                border-radius:7px;background:rgba(36,144,239,.07);color:var(--text-color,#36414c);
                padding:2px 6px;font-size:9.5px;font-weight:850;line-height:1;cursor:pointer;outline:none
            }
            .dco-all-sides-profile-select:hover,.dco-all-sides-profile-select:focus{
                border-color:var(--primary,#2490ef);background:#eef7ff;box-shadow:0 0 0 2px rgba(36,144,239,.1)
            }
            .dco-edge-profile-grid{
                display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;margin:0 0 4px;
                direction:rtl;align-items:stretch
            }
            .dco-side-profile-select{
                width:100%;min-width:0;height:25px;min-height:25px;border:1px solid var(--border-color,#cbd2d9);
                border-radius:7px;background:var(--card-bg,#fff);color:#52606d;padding:1px 3px;
                font-size:9px;font-weight:800;line-height:1;cursor:pointer;outline:none;text-overflow:ellipsis
            }
            .dco-side-profile-select:hover,.dco-side-profile-select:focus{
                border-color:var(--primary,#2490ef);background:#f2f8ff;box-shadow:0 0 0 2px rgba(36,144,239,.1)
            }
            .dco-side-profile-select.is-active-default{border-color:rgba(36,144,239,.5);background:#edf7ff;color:#155f97}
            .dco-side-profile-select.is-custom{border-color:#d3a20a;background:#fff5cc;color:#765500}
            .dco-side-profile-select:disabled,.dco-all-sides-profile-select:disabled{opacity:.48;cursor:not-allowed;box-shadow:none}
            .dco-edge-buttons{padding-top:0!important;overflow:visible!important;align-items:stretch!important;margin:0!important}
            .dco-col-edges .dco-check-toggle{min-height:39px!important;height:39px!important;padding:4px!important;align-items:center!important;overflow:hidden!important}
            @media(max-width:900px){
                .dco-fast-table .dco-col-edge-bulk{width:112px!important;min-width:112px!important;max-width:112px!important}
                .dco-all-sides-profile-select{font-size:9px;padding-inline:4px}
                .dco-side-profile-select{font-size:8.5px;padding-inline:2px}
            }
        `;
        document.head.appendChild(style);
    }

    function syncToggleVisuals(tr, row) {
        SIDE_CONFIG.forEach(config => {
            const toggle = tr.querySelector(`.dco-check-toggle[data-check-field='${config.selectedField}']`);
            if (!toggle) return;
            const checked = Boolean(row[config.selectedField]);
            toggle.classList.toggle("is-checked", checked);
            toggle.setAttribute("aria-pressed", checked ? "true" : "false");
            const mark = toggle.querySelector(".dco-check-mark");
            if (mark) mark.textContent = checked ? "✓" : "";
        });
    }

    function notifyChanged(frm, tr, row, fieldname) {
        frm.dirty();
        syncToggleVisuals(tr, row);

        const root = rootFor(frm);
        if (root) {
            root.dispatchEvent(new CustomEvent("dco:side-edge-change", {
                bubbles: true,
                detail: { row: row.name, fieldname },
            }));
        }

        const api = moduleApi();
        if (api && api.schedule) api.schedule(frm);
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        if (window.AlmdinaMultiEdgeDocuments && window.AlmdinaMultiEdgeDocuments.patch) {
            window.AlmdinaMultiEdgeDocuments.patch(frm);
        }
        schedule(frm);
    }

    function applySideSelection(frm, tr, config, overrideType) {
        const row = materialize(frm, tr);
        if (!row) return;
        row[config.selectedField] = 1;
        row[config.overrideField] = String(overrideType || "").trim();
        notifyChanged(frm, tr, row, config.overrideField);
    }

    function applyAllSides(frm, tr, selectedValue) {
        const row = materialize(frm, tr);
        if (!row) return;
        const overrideType = selectedValue === BULK_DEFAULT_VALUE
            ? ""
            : String(selectedValue || "").trim();
        SIDE_CONFIG.forEach(config => {
            row[config.selectedField] = 1;
            row[config.overrideField] = overrideType;
        });
        notifyChanged(frm, tr, row, "all_side_edge_profiles");
    }

    function ensureBulkHeader(root) {
        const edgeTypeHeader = root.querySelector(".dco-fast-table thead th.dco-col-edge-type");
        if (!edgeTypeHeader) return;
        let header = root.querySelector(".dco-fast-table thead th.dco-col-edge-bulk");
        if (!header) {
            header = document.createElement("th");
            header.className = "dco-col-edge-bulk";
            edgeTypeHeader.insertAdjacentElement("afterend", header);
        }
        header.textContent = isArabic() ? "تطبيق على الأربعة" : "Apply to all four";
        header.title = isArabic()
            ? "تفعيل الأضلاع الأربعة وتطبيق نوع قشاط واحد عليها"
            : "Enable all four sides and apply one profile";
    }

    function ensureBulkSelect(frm, tr) {
        const edgeTypeCell = tr.querySelector(":scope > td.dco-col-edge-type");
        if (!edgeTypeCell) return;

        let cell = tr.querySelector(":scope > td.dco-col-edge-bulk");
        if (!cell) {
            cell = document.createElement("td");
            cell.className = "dco-col-edge-bulk";
            edgeTypeCell.insertAdjacentElement("afterend", cell);
        }

        let content = cell.querySelector(":scope > .dco-edge-bulk-cell-content");
        if (!content) {
            content = document.createElement("div");
            content.className = "dco-edge-bulk-cell-content";
            cell.replaceChildren(content);
        }

        let select = content.querySelector(".dco-all-sides-profile-select");
        if (!select) {
            select = document.createElement("select");
            select.className = "dco-all-sides-profile-select";
            select.dataset.bulkEdgeProfile = "1";
            content.appendChild(select);
        }

        const options = bulkOptionsHtml(frm);
        if (select.dataset.optionsSignature !== options) {
            select.innerHTML = options;
            select.dataset.optionsSignature = options;
        }
        select.value = "";
        select.disabled = !isEditable(frm);
        select.title = isArabic()
            ? "فعّل الأضلاع الأربعة وطبّق نوعًا واحدًا عليها مباشرة"
            : "Enable all four sides and apply one profile immediately";
    }

    function ensureSideGrid(frm, cell, edgeButtons, row) {
        let grid = cell.querySelector(":scope > .dco-edge-profile-grid");
        if (!grid) {
            grid = document.createElement("div");
            grid.className = "dco-edge-profile-grid";
            edgeButtons.insertAdjacentElement("beforebegin", grid);
        }

        SIDE_CONFIG.forEach(config => {
            let select = grid.querySelector(`select[data-edge-side='${config.side}']`);
            if (!select) {
                select = document.createElement("select");
                select.className = "dco-side-profile-select";
                select.dataset.edgeSide = config.side;
                select.setAttribute(
                    "aria-label",
                    isArabic() ? `نوع قشاط ${config.labelAr}` : `${config.labelEn} profile`
                );
                grid.appendChild(select);
            }

            const current = String((row && row[config.overrideField]) || "").trim();
            const selected = Boolean(row && row[config.selectedField]);
            const options = sideOptionsHtml(frm, current);
            const signature = `${current}\n${options}`;
            if (select.dataset.optionsSignature !== signature) {
                select.innerHTML = options;
                select.dataset.optionsSignature = signature;
            }
            select.value = current;
            select.disabled = !isEditable(frm);
            select.classList.toggle("is-custom", Boolean(current));
            select.classList.toggle("is-active-default", selected && !current);

            const label = isArabic() ? config.labelAr : config.labelEn;
            const effective = current || String(frm.doc.default_edge_type || "").trim();
            const mode = current
                ? (isArabic() ? "مخصص" : "Custom")
                : (isArabic() ? "افتراضي" : "Default");
            select.title = `${label} — ${mode}: ${effective || "—"}`;
        });
    }

    function removeObsoleteControls(cell) {
        cell.querySelectorAll(":scope > .dco-edge-bulk-toolbar,:scope > .dco-edge-direct-actions").forEach(element => element.remove());
    }

    function renderRow(frm, tr) {
        const cell = tr.querySelector(":scope > td.dco-col-edges");
        const edgeButtons = cell && cell.querySelector(":scope > .dco-edge-buttons");
        if (!cell || !edgeButtons) return;

        removeObsoleteControls(cell);
        const row = rowByName(frm, tr.dataset.rowName) || {};
        ensureSideGrid(frm, cell, edgeButtons, row);
        ensureBulkSelect(frm, tr);
    }

    function renderHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help) return;
        let hint = help.querySelector(".dco-side-edge-help");
        if (!hint) {
            hint = document.createElement("span");
            hint.className = "dco-side-edge-help";
            help.appendChild(hint);
        }
        hint.textContent = isArabic()
            ? "القوائم فوق اتجاهات القشاط، واتجاهات القشاط بمحاذاة القياسات والتدوير"
            : "Profile selects stay above the edge directions; directions align with dimensions and rotation";
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        ensureBulkHeader(root);
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => renderRow(frm, tr));
        renderHelp(root);
        bind(frm, root);
    }

    function bind(frm, root) {
        if (root._dcoDirectEdgeProfileControlsBound) return;
        root._dcoDirectEdgeProfileControlsBound = true;

        root.addEventListener("pointerdown", event => {
            const select = event.target.closest(".dco-side-profile-select,.dco-all-sides-profile-select");
            if (!select || !root.contains(select)) return;
            event.stopPropagation();
        }, true);

        root.addEventListener("click", event => {
            const select = event.target.closest(".dco-side-profile-select,.dco-all-sides-profile-select");
            if (!select || !root.contains(select)) return;
            event.stopPropagation();
        }, true);

        root.addEventListener("change", event => {
            const sideSelect = event.target.closest(".dco-side-profile-select[data-edge-side]");
            if (sideSelect && root.contains(sideSelect)) {
                event.stopPropagation();
                const config = SIDE_CONFIG.find(item => item.side === sideSelect.dataset.edgeSide);
                const tr = sideSelect.closest("tr[data-row-name]");
                if (config && tr) applySideSelection(frm, tr, config, sideSelect.value);
                return;
            }

            const bulkSelect = event.target.closest(".dco-all-sides-profile-select[data-bulk-edge-profile]");
            if (!bulkSelect || !root.contains(bulkSelect) || !bulkSelect.value) return;
            event.stopPropagation();
            const tr = bulkSelect.closest("tr[data-row-name]");
            const value = bulkSelect.value;
            bulkSelect.value = "";
            if (tr) applyAllSides(frm, tr, value);
        }, true);

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
        root._dcoDirectEdgeProfileControlsObserver = observer;
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 140);
    }

    function loadProfilesAndRender(frm) {
        const api = moduleApi();
        if (api && api.ensureProfiles) {
            Promise.resolve(api.ensureProfiles(frm)).finally(() => schedule(frm));
            return;
        }
        schedule(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { loadProfilesAndRender(frm); },
        refresh(frm) { loadProfilesAndRender(frm); },
        default_edge_type(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        edge_long_right(frm) { schedule(frm); },
        edge_long_left(frm) { schedule(frm); },
        edge_width_top(frm) { schedule(frm); },
        edge_width_bottom(frm) { schedule(frm); },
        edge_long_right_type_override(frm) { schedule(frm); },
        edge_long_left_type_override(frm) { schedule(frm); },
        edge_width_top_type_override(frm) { schedule(frm); },
        edge_width_bottom_type_override(frm) { schedule(frm); },
    });

    window.AlmdinaEdgeProfileControls = {
        apply,
        schedule,
        applySideSelection,
        applyAllSides,
    };
})();
