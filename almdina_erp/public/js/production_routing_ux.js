(() => {
    "use strict";


    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    const TRANSLATABLE_STAGE_TYPES = new Set([
        "Sharyoun",
        "Drawing",
        "CNC",
        "Sanding",
        "Cutting",
        "Edge Banding",
        "Review / Preparation",
        "Drilling",
        "Assembly",
        "Quality Check",
        "Packing",
    ]);

    function activeStages(frm) {
        return (frm.doc.stages || [])
            .slice()
            .sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0))
            .filter(row => Number(row.required || 0));
    }

    function nextSequence(frm) {
        return Math.max(
            0,
            ...(frm.doc.stages || []).map(row => Number(row.sequence || 0))
        ) + 10;
    }

    function stageLabel(row) {
        if (row.department_label) return row.department_label;
        const code = String(row.stage_type || "").trim();
        if (TRANSLATABLE_STAGE_TYPES.has(code)) return translate(code);
        return code || translate("Unnamed stage");
    }

    function routePreview(frm) {
        return activeStages(frm).map((row, index) => ({
            index: index + 1,
            label: stageLabel(row),
            role: row.operational_role || translate("No role"),
            planning: Boolean(Number(row.is_planning_stage || 0)),
        }));
    }

    function previewHtml(frm) {
        const stages = routePreview(frm);
        if (!stages.length) {
            return `<div class="text-muted">${translate("Add at least one active stage.")}</div>`;
        }
        const chips = stages.map(stage => `
            <div style="min-width:150px;max-width:220px;padding:11px 13px;border:1px solid ${stage.planning ? "#f0b429" : "var(--border-color,#dfe3e8)"};border-radius:14px;background:${stage.planning ? "#fff8e6" : "var(--fg-color,#fff)"}">
                <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap">
                    <b style="font-size:14px">${stage.index}. ${frappe.utils.escape_html(stage.label)}</b>
                    ${stage.planning ? `<span style="padding:2px 7px;border-radius:999px;background:#f59e0b;color:#fff;font-size:10px;font-weight:800">${translate("Planning")}</span>` : ""}
                </div>
                <div style="margin-top:5px;color:var(--text-muted,#667085);font-size:11px">${translate("Role")}: ${frappe.utils.escape_html(stage.role)}</div>
            </div>`).join(`<div style="font-size:20px;color:var(--text-muted,#98a2b3)">${(uiDirection() === "rtl") ? "←" : "→"}</div>`);
        const startsPlanning = stages[0] && stages[0].planning;
        const gate = startsPlanning
            ? translate("The order can enter the planning stage before approval, but it cannot leave that stage before the cutting plan is approved.")
            : translate("The order can go directly to the first execution stage without approving the cutting plan first.");
        return `
            <div>
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">${chips}</div>
                <div style="margin-top:14px;padding:10px 12px;border-radius:10px;background:var(--subtle-fg,#f7f8fa);font-size:12px;line-height:1.8">
                    <b>${translate("Cutting plan gate")}:</b> ${gate}
                </div>
            </div>`;
    }

    function ensurePlanningPosition(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!Number(row.is_planning_stage || 0)) return;
        if (!Number(row.required || 0)) {
            frappe.model.set_value(cdt, cdn, "required", 1);
        }
        const first = activeStages(frm)[0];
        if (first && first.name !== row.name) {
            frappe.model.set_value(cdt, cdn, "is_planning_stage", 0);
            frappe.msgprint({
                title: translate("Planning stage"),
                indicator: "orange",
                message: translate("The planning stage must be the first active stage. Reorder the stages, then enable this option."),
            });
            return;
        }
        (frm.doc.stages || []).forEach(other => {
            if (other.name !== row.name && Number(other.is_planning_stage || 0)) {
                frappe.model.set_value(other.doctype, other.name, "is_planning_stage", 0);
            }
        });
    }

    frappe.ui.form.on("Production Routing", {
        setup(frm) {
            frm.set_query("operational_role", "stages", () => ({
                query: "almdina_erp.almdina_erp.services.master_data_service.search_operational_roles",
            }));
        },
        refresh(frm) {
            frm.set_intro(
                translate("Build the route in the real work order and assign the operational role for each stage. The role decides who can receive the task, while permissions decide what the worker can do."),
                "blue"
            );
            if (!frm.is_new() && routePreview(frm).length) {
                frm.add_custom_button(translate("Preview production route"), () => {
                    frappe.msgprint({
                        title: translate("Order route"),
                        indicator: "blue",
                        wide: true,
                        message: previewHtml(frm),
                    });
                });
            }
        },
    });

    frappe.ui.form.on("Production Routing Stage", {
        stages_add(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row.sequence) frappe.model.set_value(cdt, cdn, "sequence", nextSequence(frm));
            if (row.required === undefined || row.required === null) {
                frappe.model.set_value(cdt, cdn, "required", 1);
            }
        },
        stage_type(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            const label = STAGE_LABELS[String(row.stage_type || "").trim()];
            if (label && !row.department_label) {
                frappe.model.set_value(cdt, cdn, "department_label", label);
            }
        },
        is_planning_stage(frm, cdt, cdn) {
            ensurePlanningPosition(frm, cdt, cdn);
        },
        required(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!Number(row.required || 0) && Number(row.is_planning_stage || 0)) {
                frappe.model.set_value(cdt, cdn, "is_planning_stage", 0);
            }
        },
    });
})();
