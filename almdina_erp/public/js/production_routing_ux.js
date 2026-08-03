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

    function nextSequence(frm) {
        return Math.max(
            0,
            ...(frm.doc.stages || []).map(row => Number(row.sequence || 0))
        ) + 10;
    }

    function routePreview(frm) {
        return (frm.doc.stages || [])
            .slice()
            .sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0))
            .filter(row => Number(row.required || 0))
            .map(row => row.department_label || row.stage_type)
            .filter(Boolean)
            .join(" ← ");
    }

    frappe.ui.form.on("Production Routing", {
        setup(frm) {
            frm.set_query("operational_role", "stages", () => ({
                query: "almdina_erp.almdina_erp.services.master_data_service.search_operational_roles",
            }));
        },
        refresh(frm) {
            frm.set_intro(
                __("رتّب مراحل التنفيذ، وحدد اسم القسم الظاهر والدور المؤهل لاستلام كل مرحلة. تعديل المسار المستخدم في طلب نشط محمي تلقائيًا."),
                "blue"
            );
            if (!frm.is_new() && routePreview(frm)) {
                frm.add_custom_button(__("معاينة المسار"), () => {
                    frappe.msgprint({
                        title: __("سير الطلب"),
                        indicator: "blue",
                        message: `<div dir="rtl" style="font-size:16px;font-weight:800;line-height:2">${frappe.utils.escape_html(routePreview(frm))}</div>`,
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
            if (!label) return;
            if (!row.department_label) {
                frappe.model.set_value(cdt, cdn, "department_label", label);
            }
        },
    });
})();
