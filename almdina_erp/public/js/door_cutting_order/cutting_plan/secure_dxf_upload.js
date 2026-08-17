(() => {
    "use strict";

    frappe.provide("frappe.almdina");
    if (typeof frappe.almdina.upload_production_dxf === "function") return;

    const UPLOAD_METHOD =
        "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf";

    function uploadProductionDxf(frm) {
        if (!frm || frm.is_new()) {
            frappe.msgprint(__("احفظ الطلب قبل رفع ملف DXF."));
            return null;
        }

        const orderName = frm.doc.name;
        const replacing = Boolean(frm.doc.production_dxf);

        // Security contract: the browser creates only a private, unattached File.
        // The server authorizes and validates it before linking it to the order.
        return new frappe.ui.FileUploader({
            folder: "Home/Attachments",
            is_private: 1,
            restrictions: {
                allowed_file_types: [".dxf"],
                max_file_size: 10 * 1024 * 1024,
            },
            on_success(file) {
                return frappe.call({
                    method: UPLOAD_METHOD,
                    args: {
                        order_name: orderName,
                        file_url: file.file_url,
                    },
                    freeze: true,
                    freeze_message: __("جاري التحقق من ملف DXF وتطبيق الخطة..."),
                }).then(() => {
                    frappe.show_alert({
                        message: replacing
                            ? __("تم استبدال ملف DXF والتحقق منه.")
                            : __("تم رفع ملف DXF والتحقق منه."),
                        indicator: "green",
                    }, 5);
                    if (frm.doc && frm.doc.name === orderName) {
                        return frm.reload_doc();
                    }
                    return null;
                });
            },
        });
    }

    frappe.almdina.upload_production_dxf = uploadProductionDxf;
})();
