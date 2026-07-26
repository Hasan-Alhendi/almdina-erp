(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const PLAN_BUTTONS = {
        ".dco-recalculate-plan": null,
        ".dco-auto-pro-plan": "Auto Pro",
        ".dco-deep-plan": "Deep Search",
        ".dco-optimal-plan": "Optimal Search",
    };

    function editable(frm) {
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
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
                .dco-cost-plan-stale {
                    margin:12px 0 0;
                    padding:11px 13px;
                    border:1px solid #f0c36d;
                    border-radius:11px;
                    background:#fff8e6;
                    color:#6f4b00;
                    font-size:11px;
                    line-height:1.65;
                    font-weight:750;
                }
                .dco-print-customer-invoice.is-plan-stale {
                    opacity:.55;
                    cursor:not-allowed !important;
                }
            </style>
        `);
    }

    function planIsStale(frm) {
        return Number(frm.doc.plan_needs_recalculation || 0) === 1 || !frm.doc.cutting_plan_json;
    }

    function markClientPlanStale(frm) {
        if (!editable(frm)) return;
        frm.doc.plan_needs_recalculation = 1;
        renderStaleState(frm);
    }

    function renderStaleState(frm) {
        installStyles();
        const stale = planIsStale(frm);

        const planActions = frm.fields_dict.plan_control_actions;
        if (planActions && planActions.$wrapper) {
            planActions.$wrapper.find(".dco-plan-stale-banner").remove();
            if (stale) {
                planActions.$wrapper.prepend(`
                    <div class="dco-plan-stale-banner">
                        <span class="icon">⚡</span>
                        <div>
                            <strong>تم حفظ التعديلات دون تشغيل محرك القص الثقيل</strong>
                            خطة القص والتكلفة النهائية تحتاج إعادة حساب. اضغط زر إعادة الحساب عندما تنتهي من إدخال القياسات.
                        </div>
                    </div>`);
                planActions.$wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
            }
        }

        const costField = frm.fields_dict.order_cost_invoice_html;
        if (costField && costField.$wrapper) {
            costField.$wrapper.find(".dco-cost-plan-stale").remove();
            const printButton = costField.$wrapper.find(".dco-print-customer-invoice");
            printButton.toggleClass("is-plan-stale", stale).attr("aria-disabled", stale ? "true" : "false");
            if (stale) {
                costField.$wrapper.find(".dco-cost-hero").after(`
                    <div class="dco-cost-plan-stale">
                        تكلفة الألواح والقص غير نهائية لأن خطة القص تغيرت. أعد حساب خطة القص قبل طباعة فاتورة الزبون.
                    </div>`);
            }
        }
    }

    function modeForButton(button) {
        for (const [selector, mode] of Object.entries(PLAN_BUTTONS)) {
            if (button.matches(selector)) return mode;
        }
        return undefined;
    }

    async function runExplicitRecalculation(frm, requestedMode) {
        if (frm._dco_plan_recalculation_running) return;
        if (!editable(frm)) {
            frappe.msgprint("لا يمكن إعادة حساب طلب معتمد أو دخل الإنتاج.");
            return;
        }
        if (!frm.doc.board_item || !(frm.doc.pieces || []).length) {
            frappe.msgprint("اختر اللوح وأدخل القياسات أولًا قبل حساب خطة القص.");
            return;
        }

        frm._dco_plan_recalculation_running = true;
        if (requestedMode && frm.doc.packing_mode !== requestedMode) {
            await frm.set_value("packing_mode", requestedMode);
        }

        const mode = frm.doc.packing_mode || "Auto Pro";
        const message = mode === "Optimal Search"
            ? "جاري البحث الأمثل عن أقل عدد ألواح..."
            : mode === "Deep Search"
                ? "جاري البحث المعمق عن أفضل توزيع..."
                : "جاري حساب أفضل توزيع للقطع...";

        frappe.dom.freeze(message);
        try {
            // First persist edits through the new lightweight Save path.
            if (frm.is_new() || frm.is_dirty()) {
                await frm.save();
            }
            await frappe.call({
                method: "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.recalculate_order",
                args: { order_name: frm.doc.name },
            });
            await frm.reload_doc();
            frappe.show_alert({ message: "تم تحديث خطة القص والتكلفة", indicator: "green" }, 3);
        } catch (error) {
            console.error("Explicit cutting plan recalculation failed", error);
            throw error;
        } finally {
            frappe.dom.unfreeze();
            frm._dco_plan_recalculation_running = false;
            renderStaleState(frm);
        }
    }

    function bindCaptureActions(frm) {
        const root = frm.wrapper && (frm.wrapper[0] || frm.wrapper);
        if (!root || root._dcoFastSaveCaptureBound) return;
        root._dcoFastSaveCaptureBound = true;

        root.addEventListener("click", event => {
            const button = event.target.closest(Object.keys(PLAN_BUTTONS).join(","));
            if (button && root.contains(button)) {
                const requestedMode = modeForButton(button);
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                runExplicitRecalculation(frm, requestedMode);
                return;
            }

            const printButton = event.target.closest(".dco-print-customer-invoice");
            if (printButton && root.contains(printButton) && planIsStale(frm)) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                frappe.msgprint("أعد حساب خطة القص أولًا حتى تكون تكلفة الطلب والفاتورة صحيحة.");
            }
        }, true);
    }

    function schedule(frm) {
        installStyles();
        bindCaptureActions(frm);
        renderStaleState(frm);
        requestAnimationFrame(() => renderStaleState(frm));
        setTimeout(() => renderStaleState(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        board_item(frm) { markClientPlanStale(frm); },
        kerf_mm(frm) { markClientPlanStale(frm); },
        trim_margin_mm(frm) { markClientPlanStale(frm); },
        packing_mode(frm) { markClientPlanStale(frm); },
        cutting_machine_type(frm) { markClientPlanStale(frm); },
        optimization_time_limit_sec(frm) { markClientPlanStale(frm); },
        pieces_add(frm) { markClientPlanStale(frm); },
        pieces_remove(frm) { markClientPlanStale(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm(frm) { markClientPlanStale(frm); },
        length_cm(frm) { markClientPlanStale(frm); },
        qty(frm) { markClientPlanStale(frm); },
        allow_rotation(frm) { markClientPlanStale(frm); },
    });
})();
