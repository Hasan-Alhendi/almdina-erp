(() => {
    "use strict";

    const GROUP = __("قطعة التعويض");
    const CONTEXT_METHOD =
        "almdina_erp.almdina_erp.services.replacement_permission_service.get_replacement_context";
    const ACTION_METHOD = "almdina_erp.almdina_erp.services.replacement_service";
    const LABELS = Object.freeze([
        __("فتح خطة قص التعويض"),
        __("اعتماد قطعة التعويض"),
        __("بدء تنفيذ التعويض"),
        __("إكمال قطعة التعويض"),
        __("إلغاء قطعة التعويض"),
    ]);

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function can(capability) {
        const api = permissions();
        return Boolean(api && typeof api.can === "function" && api.can(capability));
    }

    function removeButtons(frm) {
        LABELS.forEach(label => frm.remove_custom_button(label, GROUP));
    }

    function actionAllowed(context, action) {
        return Boolean(
            context &&
            context.actions &&
            context.actions[action] &&
            context.actions[action].allowed === true
        );
    }

    function callAction(frm, method, args = {}) {
        const expectedName = frm.doc.name;
        return frappe.call({
            method: `${ACTION_METHOD}.${method}`,
            args: { replacement_name: expectedName, ...args },
            freeze: true,
            freeze_message: __("جاري تنفيذ الإجراء على قطعة التعويض..."),
        }).then(response => {
            if (!frm.doc || frm.doc.name !== expectedName) return null;
            return frm.reload_doc().then(() => response.message || {});
        });
    }

    function notifyCompleted(data) {
        if (!data) return;
        frappe.show_alert({
            message: __("تم إكمال قطعة التعويض وتحديث حالة الطلب."),
            indicator: "green",
        });
    }

    function completeReplacement(frm, context) {
        if (!actionAllowed(context, "edit_actual_cost")) {
            frappe.confirm(
                __("سيتم اعتماد التكلفة المتوقعة المجمدة وإكمال قطعة التعويض. هل تريد المتابعة؟"),
                () => callAction(frm, "complete_replacement", {
                    internal_loss_cost_usd: null,
                }).then(notifyCompleted)
            );
            return;
        }

        frappe.prompt(
            [{
                fieldname: "internal_loss_cost_usd",
                fieldtype: "Currency",
                label: __("الخسارة الداخلية الفعلية بالدولار"),
                description: __("اترك الحقل فارغًا لاعتماد التكلفة المتوقعة المجمدة."),
            }],
            values => {
                const loss = (values || {}).internal_loss_cost_usd;
                return callAction(frm, "complete_replacement", {
                    internal_loss_cost_usd:
                        loss === undefined || loss === null || loss === ""
                            ? null
                            : loss,
                }).then(notifyCompleted);
            },
            __("إكمال قطعة التعويض"),
            __("إنهاء")
        );
    }

    function installButtons(frm, context) {
        removeButtons(frm);
        if (!context || context.replacement_name !== frm.doc.name) return;

        if (context.cutting_plan && can("view_cutting_plan")) {
            frm.add_custom_button(__("فتح خطة قص التعويض"), () => {
                frappe.set_route("Form", "Cutting Plan", context.cutting_plan);
            }, GROUP);
        }

        if (actionAllowed(context, "approve")) {
            frm.add_custom_button(__("اعتماد قطعة التعويض"), () => {
                frappe.confirm(
                    __("سيتم إنشاء خطة قص مصغرة معتمدة وتجميد التكلفة المتوقعة. هل تريد المتابعة؟"),
                    () => callAction(frm, "approve_replacement").then(data => {
                        if (!data) return;
                        frappe.msgprint({
                            title: __("تم اعتماد قطعة التعويض"),
                            indicator: "green",
                            message: `${__("خطة القص")}: <b>${frappe.utils.escape_html(data.cutting_plan || "")}</b>`,
                        });
                    })
                );
            }, GROUP);
        }

        if (actionAllowed(context, "start")) {
            frm.add_custom_button(__("بدء تنفيذ التعويض"), () => {
                frappe.confirm(
                    __("هل تريد بدء العمل على قطعة التعويض المعتمدة؟"),
                    () => callAction(frm, "start_replacement")
                );
            }, GROUP);
        }

        if (actionAllowed(context, "complete")) {
            frm.add_custom_button(
                __("إكمال قطعة التعويض"),
                () => completeReplacement(frm, context),
                GROUP
            );
        }

        if (actionAllowed(context, "cancel")) {
            frm.add_custom_button(__("إلغاء قطعة التعويض"), () => {
                frappe.prompt(
                    [{
                        fieldname: "reason",
                        fieldtype: "Small Text",
                        label: __("سبب الإلغاء"),
                        reqd: 1,
                    }],
                    values => callAction(frm, "cancel_replacement", {
                        reason: String((values || {}).reason || "").trim(),
                    }),
                    __("إلغاء قطعة التعويض"),
                    __("تأكيد الإلغاء")
                );
            }, GROUP);
        }
    }

    function loadContext(frm) {
        removeButtons(frm);
        if (frm.is_new()) return Promise.resolve(null);
        const requestId = (frm.__almdinaReplacementRequest || 0) + 1;
        const expectedName = frm.doc.name;
        frm.__almdinaReplacementRequest = requestId;
        return frappe.call({
            method: CONTEXT_METHOD,
            args: { replacement_name: expectedName },
            freeze: false,
        }).then(response => {
            if (
                frm.__almdinaReplacementRequest !== requestId ||
                !frm.doc ||
                frm.doc.name !== expectedName
            ) return null;
            const context = response.message || null;
            frm.__almdinaReplacementContext = context;
            installButtons(frm, context);
            return context;
        }).catch(error => {
            if (frm.__almdinaReplacementRequest !== requestId) return null;
            frm.__almdinaReplacementContext = null;
            removeButtons(frm);
            if (error && error.exc_type !== "PermissionError") {
                frappe.show_alert({
                    message: __("تعذر تحميل إجراءات قطعة التعويض."),
                    indicator: "red",
                });
            }
            return null;
        });
    }

    frappe.ui.form.on("Replacement Piece", {
        refresh(frm) {
            loadContext(frm);
        },
    });
})();
