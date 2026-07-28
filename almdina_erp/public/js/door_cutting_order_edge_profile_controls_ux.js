(() => {
    "use strict";

    const STYLE_ID = "dco-edge-profile-controls-css";
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

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table .dco-col-edges{vertical-align:middle!important;overflow:visible!important}
            .dco-edge-bulk-toolbar{display:flex;align-items:center;justify-content:flex-end;min-height:24px;margin:0 0 3px;position:relative;z-index:7}
            .dco-edge-bulk-profile{display:inline-flex;align-items:center;justify-content:center;gap:4px;min-height:22px;padding:2px 8px;border:1px solid rgba(36,144,239,.32);border-radius:999px;background:rgba(36,144,239,.07);color:var(--text-color,#36414c);font-size:9.5px;font-weight:900;line-height:1;cursor:pointer;white-space:nowrap;transition:background .12s ease,border-color .12s ease,transform .12s ease}
            .dco-edge-bulk-profile:hover{background:rgba(36,144,239,.13);border-color:var(--primary,#2490ef);transform:translateY(-1px)}
            .dco-edge-bulk-profile.is-custom{background:#fff6db;border-color:#d7a514;color:#805c00}
            .dco-edge-bulk-profile:disabled{opacity:.48;cursor:not-allowed;transform:none}
            .dco-edge-buttons{padding-top:0!important;overflow:visible!important;align-items:stretch!important}
            .dco-col-edges .dco-check-toggle{position:relative!important;overflow:visible!important;min-height:45px!important;padding:15px 4px 4px!important;align-items:flex-end!important}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger{
                display:flex!important;position:absolute!important;z-index:20!important;top:2px!important;inset-inline-end:3px!important;
                align-items:center!important;justify-content:center!important;width:17px!important;height:17px!important;margin:0!important;
                border:1px solid var(--border-color,#cbd2d9)!important;border-radius:999px!important;background:var(--card-bg,#fff)!important;
                color:#4b5966!important;font-size:12px!important;font-weight:900!important;line-height:1!important;box-shadow:none!important;
                cursor:pointer!important;opacity:1!important;pointer-events:auto!important;transform:none!important
            }
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger:hover{border-color:var(--primary,#2490ef)!important;background:#eef7ff!important;color:#146eb4!important}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger.is-custom{background:#fff0b8!important;border-color:#ca9800!important;color:#765400!important}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger.is-missing{background:#fff0f0!important;border-color:#d94b4b!important;color:#b32626!important}
            .dco-check-toggle.is-checked>.dco-side-profile-trigger{background:#fff!important;color:#26323d!important}
            .dco-bulk-edge-summary{padding:9px 11px;border:1px solid var(--border-color,#dfe3e8);border-radius:9px;background:var(--subtle-fg,#f7f9fb);font-size:11px;line-height:1.7}
            .dco-bulk-edge-summary b{display:block;font-size:13px;margin-bottom:2px}
            @media(max-width:900px){.dco-edge-bulk-profile{padding-inline:6px;font-size:9px}.dco-col-edges .dco-check-toggle{min-height:43px!important}}
        `;
        document.head.appendChild(style);
    }

    function configForToggle(toggle) {
        const fieldname = toggle && toggle.dataset.checkField;
        return SIDE_CONFIG.find(item => item.selectedField === fieldname) || null;
    }

    function ensureIndicator(toggle, config) {
        let indicator = toggle.querySelector(":scope > .dco-side-profile-trigger");
        if (!indicator) {
            indicator = document.createElement("span");
            indicator.className = "dco-side-profile-trigger";
            indicator.setAttribute("role", "button");
            indicator.setAttribute("tabindex", "0");
            indicator.dataset.edgeSide = config.side;
            toggle.appendChild(indicator);
        }
        indicator.dataset.edgeSide = config.side;
        indicator.setAttribute(
            "aria-label",
            isArabic() ? `تخصيص قشاط ${config.labelAr}` : `Customize ${config.labelEn}`
        );
        return indicator;
    }

    function allOverrides(row) {
        return SIDE_CONFIG.map(config => String((row && row[config.overrideField]) || "").trim());
    }

    function bulkLabel(row) {
        const overrides = allOverrides(row);
        const customCount = overrides.filter(Boolean).length;
        if (customCount === 4) return isArabic() ? "✦ الأربعة مخصصة" : "✦ All four custom";
        if (customCount) return isArabic() ? `✦ مخصص ${customCount}/4` : `✦ Custom ${customCount}/4`;
        return isArabic() ? "✦ تخصيص الأربعة" : "✦ Customize all four";
    }

    function ensureBulkToolbar(frm, tr, row) {
        const cell = tr.querySelector(":scope > td.dco-col-edges");
        const edgeButtons = cell && cell.querySelector(":scope > .dco-edge-buttons");
        if (!cell || !edgeButtons) return;

        let toolbar = cell.querySelector(":scope > .dco-edge-bulk-toolbar");
        if (!toolbar) {
            toolbar = document.createElement("div");
            toolbar.className = "dco-edge-bulk-toolbar";
            edgeButtons.insertAdjacentElement("beforebegin", toolbar);
        }

        let button = toolbar.querySelector(".dco-edge-bulk-profile");
        if (!button) {
            button = document.createElement("button");
            button.type = "button";
            button.className = "dco-edge-bulk-profile";
            toolbar.appendChild(button);
        }

        const overrides = allOverrides(row);
        const customCount = overrides.filter(Boolean).length;
        button.textContent = bulkLabel(row);
        button.classList.toggle("is-custom", customCount > 0);
        button.disabled = !isEditable(frm);
        button.title = isArabic()
            ? "تفعيل الأضلاع الأربعة وتطبيق نوع قشاط واحد عليها بسرعة"
            : "Enable all four sides and apply one edge profile quickly";
    }

    function renderRow(frm, tr) {
        const row = rowByName(frm, tr.dataset.rowName) || {};
        tr.querySelectorAll(".dco-check-toggle[data-check-field]").forEach(toggle => {
            const config = configForToggle(toggle);
            if (!config) return;
            const indicator = ensureIndicator(toggle, config);
            const override = String(row[config.overrideField] || "").trim();
            indicator.textContent = override ? "✦" : "⌄";
            indicator.classList.toggle("is-custom", Boolean(override));
        });
        ensureBulkToolbar(frm, tr, row);
    }

    function defaultSummary(frm) {
        const value = String(frm.doc.default_edge_type || "").trim();
        if (value) return value;
        return isArabic() ? "لم يتم اختيار قشاط افتراضي للطلب" : "No default profile selected";
    }

    function commonOverride(row) {
        const values = allOverrides(row).filter(Boolean);
        if (!values.length) return "";
        const unique = new Set(values);
        return unique.size === 1 ? values[0] : "";
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

    function notifyBulkChange(frm, tr, row) {
        frm.dirty();
        syncToggleVisuals(tr, row);
        const root = rootFor(frm);
        if (root) {
            root.dispatchEvent(new CustomEvent("dco:side-edge-change", {
                bubbles: true,
                detail: { row: row.name, fieldname: "bulk_edge_profile" },
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

    function applyToAllSides(frm, tr, row, overrideType) {
        SIDE_CONFIG.forEach(config => {
            row[config.selectedField] = 1;
            row[config.overrideField] = overrideType;
        });
        notifyBulkChange(frm, tr, row);
    }

    function openBulkDialog(frm, tr) {
        const row = materialize(frm, tr);
        if (!row) return;

        const dialog = new frappe.ui.Dialog({
            title: isArabic() ? "تخصيص الأضلاع الأربعة" : "Customize all four edges",
            fields: [
                {
                    fieldname: "summary",
                    fieldtype: "HTML",
                    options: `<div class="dco-bulk-edge-summary"><b>${isArabic() ? "إجراء سريع" : "Quick action"}</b>${isArabic()
                        ? `سيتم تفعيل الأضلاع الأربعة وتطبيق النوع نفسه عليها. القشاط الافتراضي الحالي: <strong>${frappe.utils.escape_html(defaultSummary(frm))}</strong>`
                        : `All four sides will be enabled and receive the same profile. Current default: <strong>${frappe.utils.escape_html(defaultSummary(frm))}</strong>`}</div>`,
                },
                {
                    fieldname: "edge_type",
                    fieldtype: "Link",
                    options: "Edge Banding Type",
                    label: isArabic() ? "نوع القشاط للأضلاع الأربعة" : "Profile for all four edges",
                    reqd: 1,
                    default: commonOverride(row),
                },
            ],
            primary_action_label: isArabic() ? "تطبيق على الأربعة" : "Apply to all four",
            primary_action(values) {
                const edgeType = String(values.edge_type || "").trim();
                if (!edgeType) return;
                applyToAllSides(frm, tr, row, edgeType);
                dialog.hide();
            },
        });
        dialog.show();

        const footer = dialog.$wrapper && dialog.$wrapper.find(".modal-footer");
        if (footer && footer.length) {
            const useDefault = document.createElement("button");
            useDefault.type = "button";
            useDefault.className = "btn btn-default btn-sm";
            useDefault.textContent = isArabic() ? "الأربعة بالافتراضي" : "Use default for all four";
            useDefault.addEventListener("click", () => {
                if (!String(frm.doc.default_edge_type || "").trim()) {
                    frappe.show_alert({
                        message: isArabic() ? "اختر القشاط الافتراضي للطلب أولًا." : "Select the order default profile first.",
                        indicator: "orange",
                    });
                    return;
                }
                applyToAllSides(frm, tr, row, "");
                dialog.hide();
            });
            footer.prepend(useDefault);
        }
    }

    function bind(frm, root) {
        if (root._dcoEdgeProfileControlsBound) return;
        root._dcoEdgeProfileControlsBound = true;

        root.addEventListener("pointerdown", event => {
            const button = event.target.closest(".dco-edge-bulk-profile");
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            event.stopPropagation();
        }, true);

        root.addEventListener("click", event => {
            const button = event.target.closest(".dco-edge-bulk-profile");
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            event.stopPropagation();
            const tr = button.closest("tr[data-row-name]");
            if (tr) openBulkDialog(frm, tr);
        });

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
        root._dcoEdgeProfileControlsObserver = observer;
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => renderRow(frm, tr));
        bind(frm, root);
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 140);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
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
        applyToAllSides,
    };
})();
