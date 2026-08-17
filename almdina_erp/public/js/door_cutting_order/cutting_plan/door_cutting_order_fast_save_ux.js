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

    async function validateCurrentPlanInputs(frm) {
        const boardUX = window.AlmdinaBoardTextUX;
        if (boardUX && typeof boardUX.syncInputs === "function") {
            await boardUX.syncInputs(frm);
        }
        if (!boardUX || !boardUX.canCalculatePlan(frm)) return false;
        return true;
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
        // Recalculation receives optimizer values explicitly, while piece rows and
        // board inputs are loaded by the server from the persisted order. Track
        // only the latter so plan-only users never inherit order-edit requirements.
        frm.__almdina_pending_order_input_persistence = true;
        markPlanStale(frm);
    }

    function markOptimizerPlanStale(frm) {
        if (!can(frm, "edit_optimizer_settings")) return;
        // Optimizer values, including kerf and trim, are sent explicitly through
        // the focused recalculation command. They must never request a broad
        // Door Cutting Order save checkpoint from a plan-only user.
        markPlanStale(frm);
    }

    async function persistPendingOrderInputs(frm) {
        if (!frm || !frm.__almdina_pending_order_input_persistence) return true;
        const dirty = Boolean(frm.is_dirty && frm.is_dirty());
        if (!dirty) {
            frm.__almdina_pending_order_input_persistence = false;
            return true;
        }
        if (!editable(frm)) {
            frappe.msgprint(__("تعذر تثبيت تعديلات القياسات قبل حساب خطة القص. افتح الطلب للتعديل ثم حاول مرة أخرى."));
            return false;
        }

        const editPolicy = window.frappe && frappe.almdina;
        if (!editPolicy || typeof editPolicy.persistOrderEditCheckpoint !== "function") {
            frappe.msgprint(__("تعذر تثبيت تعديلات القياسات قبل حساب خطة القص. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        }

        frappe.show_alert({
            message: __("يتم حفظ تعديلات القياسات أولًا حتى لا تفقد عند إعادة حساب خطة القص."),
            indicator: "blue",
        }, 4);

        const saved = Boolean(await editPolicy.persistOrderEditCheckpoint(frm));
        if (saved) frm.__almdina_pending_order_input_persistence = false;
        return saved;
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
        after_save(frm) {
            if (!(frm.is_dirty && frm.is_dirty())) {
                frm.__almdina_pending_order_input_persistence = false;
            }
            schedule(frm);
        },
        board_description(frm) { markOrderInputPlanStale(frm); },
        board_length_cm(frm) { markOrderInputPlanStale(frm); },
        board_width_cm(frm) { markOrderInputPlanStale(frm); },
        default_edge_type(frm) { markOrderInputPlanStale(frm); },
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
        piece_type(frm) { markOrderInputPlanStale(frm); },
        allow_rotation(frm) { markOrderInputPlanStale(frm); },
        edge_long_right(frm) { markOrderInputPlanStale(frm); },
        edge_long_left(frm) { markOrderInputPlanStale(frm); },
        edge_width_top(frm) { markOrderInputPlanStale(frm); },
        edge_width_bottom(frm) { markOrderInputPlanStale(frm); },
        edge_long_right_type_override(frm) { markOrderInputPlanStale(frm); },
        edge_long_left_type_override(frm) { markOrderInputPlanStale(frm); },
        edge_width_top_type_override(frm) { markOrderInputPlanStale(frm); },
        edge_width_bottom_type_override(frm) { markOrderInputPlanStale(frm); },
    });

    window.AlmdinaFastSaveUX = Object.freeze({
        planIsStale,
        markOrderInputPlanStale,
        markOptimizerPlanStale,
        persistPendingOrderInputs,
        renderStaleState,
        validateCurrentPlanInputs,
    });
})();
