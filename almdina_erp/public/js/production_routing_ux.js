(() => {
    "use strict";

    const STAGE_LABELS = Object.freeze({
        Sharyoun: "شريون",
        Drawing: "رسم",
        CNC: "CNC",
        Sanding: "تقشيط",
        Cutting: "قص",
        "Edge Banding": "قشاط",
        "Review / Preparation": "مراجعة وتجهيز",
        Drilling: "تثقيب",
        Assembly: "تجميع",
        "Quality Check": "فحص الجودة",
        Packing: "تغليف",
    });

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
        return row.department_label || STAGE_LABELS[String(row.stage_type || "").trim()] || row.stage_type || __("مرحلة غير مسماة");
    }

    function routePreview(frm) {
        return activeStages(frm).map((row, index) => ({
            index: index + 1,
            label: stageLabel(row),
            role: row.operational_role || __("دون دور"),
            planning: Boolean(Number(row.is_planning_stage || 0)),
        }));
    }

    function previewHtml(frm) {
        const stages = routePreview(frm);
        if (!stages.length) {
            return `<div dir="rtl" class="text-muted">${__("أضف مرحلة فعالة واحدة على الأقل.")}</div>`;
        }
        const chips = stages.map(stage => `
            <div style="min-width:150px;max-width:220px;padding:11px 13px;border:1px solid ${stage.planning ? "#f0b429" : "var(--border-color,#dfe3e8)"};border-radius:14px;background:${stage.planning ? "#fff8e6" : "var(--fg-color,#fff)"}">
                <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap">
                    <b style="font-size:14px">${stage.index}. ${frappe.utils.escape_html(stage.label)}</b>
                    ${stage.planning ? `<span style="padding:2px 7px;border-radius:999px;background:#f59e0b;color:#fff;font-size:10px;font-weight:800">${__("تخطيط")}</span>` : ""}
                </div>
                <div style="margin-top:5px;color:var(--text-muted,#667085);font-size:11px">${__("الدور")}: ${frappe.utils.escape_html(stage.role)}</div>
            </div>`).join('<div style="font-size:20px;color:var(--text-muted,#98a2b3)">←</div>');
        const startsPlanning = stages[0] && stages[0].planning;
        const gate = startsPlanning
            ? __("يمكن إرسال الطلب إلى مرحلة التخطيط بعد حساب الخطة، لكن لا يمكن مغادرتها قبل اعتماد خطة القص.")
            : __("هذا المسار يبدأ بالتنفيذ الفعلي؛ يجب اعتماد خطة القص قبل إرسال الطلب إليه.");
        return `
            <div dir="rtl">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">${chips}</div>
                <div style="margin-top:14px;padding:10px 12px;border-radius:10px;background:var(--subtle-fg,#f7f8fa);font-size:12px;line-height:1.8">
                    <b>${__("بوابة خطة القص")}:</b> ${gate}
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
                title: __("مرحلة التخطيط"),
                indicator: "orange",
                message: __("مرحلة التخطيط يجب أن تكون أول مرحلة فعالة في المسار. غيّر ترتيب المراحل أولًا ثم فعّل الخيار."),
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
                __("ابنِ المسار بالترتيب الفعلي للعمل، وحدد الدور المؤهل لكل مرحلة. الدور يحدد من يمكن إسناد المهمة إليه، بينما الصلاحيات تحدد ما يستطيع العامل فعله."),
                "blue"
            );
            if (!frm.is_new() && routePreview(frm).length) {
                frm.add_custom_button(__("معاينة سير الإنتاج"), () => {
                    frappe.msgprint({
                        title: __("سير الطلب"),
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
