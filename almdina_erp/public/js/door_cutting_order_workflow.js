(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    function call_action(method, args, success_message, frm) {
        return frappe.call({
            method,
            args,
            freeze: true,
            freeze_message: __("Processing..."),
        }).then(r => {
            if (success_message) {
                frappe.show_alert({ message: success_message, indicator: "green" });
            }
            if (frm) {
                return frm.reload_doc().then(() => r.message);
            }
            return r.message;
        });
    }

    function add_review_actions(frm) {
        if (frm.is_new()) return;

        if (["Draft", "Rejected"].includes(frm.doc.status) && (has_role("Order Entry") || has_role("Production Manager"))) {
            frm.add_custom_button(__("إرسال للمراجعة"), () => {
                frm.save().then(() => call_action(
                    "almdina_erp.almdina_erp.services.cutting_plan_service.submit_order_for_review",
                    { order_name: frm.doc.name },
                    __("تم إرسال الطلب للمراجعة."),
                    frm
                ));
            }, __("دورة الطلب"));
        }

        if (frm.doc.status === "Pending Review" && has_role("Production Manager")) {
            frm.add_custom_button(__("اعتماد الطلب"), () => {
                frappe.confirm(
                    __("سيتم تثبيت خطة القص الحالية كنسخة معتمدة وفحص توفر المخزون. هل تريد المتابعة؟"),
                    () => call_action(
                        "almdina_erp.almdina_erp.services.cutting_plan_service.approve_order",
                        { order_name: frm.doc.name },
                        __("تم اعتماد الطلب وتثبيت خطة القص."),
                        frm
                    )
                );
            }, __("دورة الطلب"));

            frm.add_custom_button(__("رفض وإعادة للتعديل"), () => {
                frappe.prompt(
                    [{
                        fieldname: "reason",
                        fieldtype: "Small Text",
                        label: __("سبب الرفض"),
                        reqd: 1,
                    }],
                    values => call_action(
                        "almdina_erp.almdina_erp.services.cutting_plan_service.reject_order",
                        { order_name: frm.doc.name, reason: values.reason },
                        __("تم رفض الطلب وإعادته للتعديل."),
                        frm
                    ),
                    __("رفض الطلب"),
                    __("تأكيد")
                );
            }, __("دورة الطلب"));
        }
    }

    function add_stock_action(frm) {
        if (frm.is_new() || ["Draft", "Rejected", "Pending Review"].includes(frm.doc.status)) return;
        if (!(has_role("Production Manager") || has_role("Stock Manager") || has_role("Cutting Operator"))) return;

        frm.add_custom_button(__("فحص توفر المواد"), () => {
            frappe.call({
                method: "almdina_erp.almdina_erp.services.stock_service.check_order_stock",
                args: { order_name: frm.doc.name },
                freeze: true,
            }).then(r => {
                const data = r.message || {};
                const rows = data.materials || [];
                let html = `<div><b>${__("Warehouse")}:</b> ${frappe.utils.escape_html(data.warehouse || "")}</div>`;
                html += `<table class="table table-bordered" style="margin-top:10px"><thead><tr><th>${__("Item")}</th><th>${__("Required")}</th><th>${__("Available")}</th><th>${__("Shortage")}</th></tr></thead><tbody>`;
                rows.forEach(row => {
                    html += `<tr><td>${frappe.utils.escape_html(row.item_code || "")}</td><td>${row.required_qty}</td><td>${row.actual_qty}</td><td>${row.shortage_qty}</td></tr>`;
                });
                html += "</tbody></table>";
                if (!rows.length) html += `<p>${__("No stock-managed materials are mapped for this order.")}</p>`;
                frappe.msgprint({
                    title: data.is_available ? __("المخزون متوفر") : __("يوجد عجز في المخزون"),
                    indicator: data.is_available ? "green" : "red",
                    message: html,
                });
            });
        }, __("المخزون"));
    }

    function add_related_views(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("مراحل الإنتاج"), () => {
            frappe.set_route("List", "Production Stage", { door_cutting_order: frm.doc.name });
        }, __("عرض"));

        frm.add_custom_button(__("خطط القص"), () => {
            frappe.set_route("List", "Cutting Plan", { door_cutting_order: frm.doc.name });
        }, __("عرض"));

        frm.add_custom_button(__("الأخطاء والتعويضات"), () => {
            frappe.set_route("List", "Production Incident", { door_cutting_order: frm.doc.name });
        }, __("عرض"));
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            add_review_actions(frm);
            add_stock_action(frm);
            add_related_views(frm);
        },
    });
})();
