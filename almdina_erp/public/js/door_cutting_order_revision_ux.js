(() => {
    "use strict";

    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const TERMINAL = new Set(["Delivered", "Cancelled"]);
    const ORDER_INPUT_FIELDS = [
        "customer",
        "order_date",
        "external_reference",
        "order_notes",
        "board_description",
        "board_length_cm",
        "board_width_cm",
        "default_edge_type",
        "edge_color",
        "cutting_cost_per_board_usd",
        "board_rate_usd",
        "kerf_mm",
        "trim_margin_mm",
        "packing_mode",
        "cutting_machine_type",
        "optimization_time_limit_sec",
    ];

    function hasRole(role) {
        const roles = frappe.user_roles || [];
        return roles.includes("System Manager") || roles.includes(role);
    }

    function isEditableDraft(frm) {
        return Boolean(
            frm && frm.doc && frm.doc.docstatus === 0 && DRAFT_LIKE.has(frm.doc.status || "Draft")
        );
    }

    function canCreateRevision(frm) {
        if (!frm || frm.is_new()) return false;
        const status = frm.doc.status || "Draft";
        if (DRAFT_LIKE.has(status) || TERMINAL.has(status)) return false;
        return hasRole("Order Entry") || hasRole("Production Manager");
    }

    function installImmutableEditPolicy() {
        frappe.provide("frappe.almdina");
        frappe.almdina.orderCanEdit = isEditableDraft;
    }

    function applyImmutableFields(frm) {
        frm.toggle_enable(ORDER_INPUT_FIELDS, isEditableDraft(frm));
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
            applyImmutableFields(frm);
            frm.remove_custom_button(__("إعادة للمسودة"), __("دورة الطلب"));

            if (frm.doc.revision_of) {
                frm.add_custom_button(__("فتح الطلب الأصلي"), () => {
                    frappe.set_route("Form", "Door Cutting Order", frm.doc.revision_of);
                }, __("دورة الطلب"));
            }

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
