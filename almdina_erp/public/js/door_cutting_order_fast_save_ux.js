(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

    function editable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function installStyles() {
        if (document.getElementById("dco-fast-save-css")) return;
        $("head").append(`
            <style id="dco-fast-save-css">
                .dco-plan-stale-banner {
                    display:flex;
                    align-items:flex-start;
                    gap:10px;
                    padding:11px 13px;
                    margin:0 0 10px;
                    border:1px solid #f0c36d;
                    border-radius:11px;
                    background:#fff8e6;
                    color:#6f4b00;
                    font-size:11px;
                    line-height:1.65;
                    font-weight:750;
                }
                .dco-plan-stale-banner strong { display:block; font-size:12px; }
                .dco-plan-stale-banner .icon { font-size:18px; line-height:1.2; }
            </style>
        `);
    }

    function planIsStale(frm) {
        return Number(frm.doc.plan_needs_recalculation || 0) === 1 || !frm.doc.cutting_plan_json;
    }

    function invalidateEditSessionRecalculation(frm) {
        if (
            window.frappe
            && frappe.almdina
            && typeof frappe.almdina.invalidateOrderEditSessionRecalculation === "function"
        ) {
            frappe.almdina.invalidateOrderEditSessionRecalculation(frm);
        }
    }

    function markPlanStale(frm) {
        if (!frm || !frm.doc || frm.doc.approved_plan) return;
        frm.doc.plan_needs_recalculation = 1;
        invalidateEditSessionRecalculation(frm);
        renderStaleState(frm);
    }

    function markOrderInputPlanStale(frm) {
        if (!editable(frm)) return;
        markPlanStale(frm);
    }

    function markOptimizerPlanStale(frm) {
        if (!can(frm, "edit_optimizer_settings")) return;
        markPlanStale(frm);
    }

    function renderStaleState(frm) {
        installStyles();
        const stale = planIsStale(frm);
        const planActions = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!planActions || !planActions.$wrapper) return;

        planActions.$wrapper.find(".dco-plan-stale-banner").remove();
        if (!stale) return;

        planActions.$wrapper.prepend(`
            <div class="dco-plan-stale-banner">
                <span class="icon">⚡</span>
                <div>
                    <strong>خطة القص تحتاج إعادة حساب</strong>
                    تم تغيير مدخل يؤثر على توزيع القطع. اضغط «إعادة الحساب بالإعدادات الحالية» بعد الانتهاء من التعديل.
                </div>
            </div>`);
        planActions.$wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
    }

    function schedule(frm) {
        installStyles();
        renderStaleState(frm);
        requestAnimationFrame(() => renderStaleState(frm));
        setTimeout(() => renderStaleState(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        board_description(frm) { markOrderInputPlanStale(frm); },
        board_length_cm(frm) { markOrderInputPlanStale(frm); },
        board_width_cm(frm) { markOrderInputPlanStale(frm); },
        kerf_mm(frm) { markOptimizerPlanStale(frm); },
        trim_margin_mm(frm) { markOptimizerPlanStale(frm); },
        packing_mode(frm) { markOptimizerPlanStale(frm); },
        cutting_machine_type(frm) { markOptimizerPlanStale(frm); },
        optimization_time_limit_sec(frm) { markOptimizerPlanStale(frm); },
        pieces_add(frm) { markOrderInputPlanStale(frm); },
        pieces_remove(frm) { markOrderInputPlanStale(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm(frm) { markOrderInputPlanStale(frm); },
        length_cm(frm) { markOrderInputPlanStale(frm); },
        qty(frm) { markOrderInputPlanStale(frm); },
        allow_rotation(frm) { markOrderInputPlanStale(frm); },
    });

    window.AlmdinaFastSaveUX = Object.freeze({
        planIsStale,
        markOrderInputPlanStale,
        markOptimizerPlanStale,
        renderStaleState,
    });
})();
