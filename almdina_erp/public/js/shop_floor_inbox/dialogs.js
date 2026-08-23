(() => {
    "use strict";

    function confirm(message, onYes) {
        return frappe.confirm(message, () => {
            if (typeof onYes === "function") onYes();
        });
    }

    function workerOptions(workers) {
        return (workers || []).map(worker => ({
            label: worker.full_name && worker.full_name !== worker.name
                ? `${worker.full_name} (${worker.name})`
                : worker.name,
            value: worker.name,
        }));
    }

    function promptWorker(handoff, onSubmit) {
        const workers = Array.isArray(handoff && handoff.workers) ? handoff.workers : [];
        return frappe.prompt(
            [{
                fieldname: "next_assignee",
                fieldtype: "Select",
                label: `${__("العامل التالي")} — ${handoff.next_department || handoff.next_stage_type || ""}`,
                options: workerOptions(workers),
                reqd: 1,
            }],
            values => {
                if (typeof onSubmit === "function") onSubmit(values.next_assignee);
            },
            __("إرسال للقسم التالي"),
            __("إرسال")
        );
    }

    function noWorkers(handoff) {
        return frappe.msgprint(__("لا يوجد عمال متاحون للدور {0} في القسم التالي.", [
            (handoff && handoff.operational_role) || "",
        ]));
    }

    window.AlmdinaShopFloorInboxDialogs = Object.freeze({
        confirmTerminal: onYes => confirm(__("تأكيد إنهاء آخر مرحلة واعتبار الطلب جاهزًا للتسليم؟"), onYes),
        confirmLogout: onYes => confirm(__("تأكيد تسجيل الخروج؟"), onYes),
        promptWorker,
        noWorkers,
        success(message) {
            frappe.show_alert({ message, indicator: "green" });
        },
        error(message) {
            return frappe.msgprint(message || __("تعذر تنفيذ العملية."));
        },
    });
})();
