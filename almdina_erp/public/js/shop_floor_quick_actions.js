(() => {
    "use strict";

    const METHODS = Object.freeze({
        start: "almdina_erp.almdina_erp.services.shop_floor_commands.start_my_stage",
        handoffWorkers: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_workers",
        handoff: "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
    });

    function actionFor(context) {
        if (context && context.canStart === true) {
            return {
                kind: "start",
                label: __("بدء العمل"),
                indicator: "primary",
            };
        }
        if (context && context.canHandoff === true) {
            const isFinalStage = context.stageType === "Sanding";
            return {
                kind: "handoff",
                label: isFinalStage ? __("إنهاء التقشيط") : __("إنهاء وإرسال"),
                indicator: "success",
            };
        }
        return null;
    }

    function setBusy(button, busy) {
        if (!button) return;
        button.disabled = Boolean(busy);
        button.setAttribute("aria-busy", busy ? "true" : "false");
        button.classList.toggle("is-loading", Boolean(busy));
    }

    function workerOptions(workers) {
        return (workers || []).map(worker => ({
            label: worker.full_name && worker.full_name !== worker.name
                ? `${worker.full_name} (${worker.name})`
                : worker.name,
            value: worker.name,
        }));
    }

    function notify(message) {
        frappe.show_alert({ message, indicator: "green" });
    }

    function runCommand({ method, args, button, successMessage, onSuccess }) {
        setBusy(button, true);
        return frappe.call({
            method,
            args,
            freeze: true,
            freeze_message: __("جاري تحديث مسار الإنتاج..."),
        }).then(response => {
            notify(successMessage);
            if (typeof onSuccess === "function") {
                onSuccess(response.message || {});
            }
            return response.message || {};
        }).finally(() => setBusy(button, false));
    }

    function start(context, options) {
        return runCommand({
            method: METHODS.start,
            args: { stage_name: context.stage },
            button: options.button,
            successMessage: __("تم بدء العمل."),
            onSuccess: options.onSuccess,
        });
    }

    function finishFinalStage(context, options) {
        frappe.confirm(
            __("تأكيد إنهاء التقشيط واعتبار الطلب جاهزًا للتسليم؟"),
            () => runCommand({
                method: METHODS.handoff,
                args: { stage_name: context.stage },
                button: options.button,
                successMessage: __("الطلب جاهز للتسليم."),
                onSuccess: options.onSuccess,
            })
        );
    }

    function handoff(context, options) {
        if (context.stageType === "Sanding") {
            finishFinalStage(context, options);
            return;
        }

        setBusy(options.button, true);
        return frappe.call({
            method: METHODS.handoffWorkers,
            args: { stage_name: context.stage },
        }).then(response => {
            const workers = response.message || [];
            if (!workers.length) {
                frappe.msgprint(__("لا يوجد عمال متاحون للقسم التالي."));
                return;
            }
            frappe.prompt(
                [{
                    fieldname: "next_assignee",
                    fieldtype: "Select",
                    label: __("العامل التالي"),
                    options: workerOptions(workers),
                    reqd: 1,
                }],
                values => runCommand({
                    method: METHODS.handoff,
                    args: {
                        stage_name: context.stage,
                        next_assignee: values.next_assignee,
                    },
                    button: options.button,
                    successMessage: __("تم إنهاء المرحلة وإرسال الطلب للقسم التالي."),
                    onSuccess: options.onSuccess,
                }),
                __("إنهاء وإرسال"),
                __("إرسال")
            );
        }).finally(() => setBusy(options.button, false));
    }

    function perform(context, options = {}) {
        const action = actionFor(context);
        if (!action || !context.stage) return;
        if (action.kind === "start") {
            return start(context, options);
        }
        return handoff(context, options);
    }

    window.AlmdinaShopFloorQuickActions = Object.freeze({
        actionFor,
        perform,
    });
})();
