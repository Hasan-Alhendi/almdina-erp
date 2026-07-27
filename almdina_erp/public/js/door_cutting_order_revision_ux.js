(() => {
    "use strict";

    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const TERMINAL = new Set(["Delivered", "Cancelled"]);

    function hasRole(role) {
        const roles = frappe.user_roles || [];
        return roles.includes("System Manager") || roles.includes(role);
    }

    function canCreateRevision(frm) {
        if (!frm || frm.is_new()) return false;
        const status = frm.doc.status || "Draft";
        if (DRAFT_LIKE.has(status) || TERMINAL.has(status)) return false;
        return hasRole("Order Entry") || hasRole("Production Manager");
    }

    function installImmutableEditPolicy() {
        frappe.provide("frappe.almdina");
        frappe.almdina.orderCanEdit = frm => Boolean(
            frm && frm.doc && frm.doc.docstatus === 0 && DRAFT_LIKE.has(frm.doc.status || "Draft")
        );
    }

    function openRevision(frm) {
        frappe.prompt(
            [{
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("سبب إنشاء نسخة التعديل"),
                reqd: 1,
            }],
            values => frappe.call({
                method: "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
                args: { order_name: frm.doc.name, reason: values.reason },
                freeze: true,
                freeze_message: __("جاري إنشاء نسخة تعديل مستقلة..."),
            }).then(r => {
                const data = r.message || {};
                if (!data.name) return;
                frappe.show_alert({
                    message: data.already_exists
                        ? __("توجد نسخة تعديل مرتبطة بهذا الطلب.")
                        : __("تم إنشاء نسخة تعديل مع الحفاظ على الطلب والخطة الأصلية."),
                    indicator: data.already_exists ? "orange" : "green",
                });
                frappe.set_route("Form", "Door Cutting Order", data.name);
            }),
            __("إنشاء نسخة تعديل"),
            __("إنشاء النسخة")
        );
    }

    installImmutableEditPolicy();

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            frm.remove_custom_button(__("إعادة للمسودة"), __("دورة الطلب"));

            if (frm.doc.superseded_by) {
                frm.add_custom_button(__("فتح نسخة التعديل"), () => {
                    frappe.set_route("Form", "Door Cutting Order", frm.doc.superseded_by);
                }, __("دورة الطلب"));
                return;
            }

            if (canCreateRevision(frm)) {
                frm.add_custom_button(__("إنشاء نسخة تعديل"), () => openRevision(frm), __("دورة الطلب"));
            }
        },
    });
})();
