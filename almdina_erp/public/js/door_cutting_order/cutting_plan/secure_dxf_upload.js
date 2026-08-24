(() => {
    "use strict";

    frappe.provide("frappe.almdina");
    if (frappe.almdina.__secureDxfUploadInstalled) return;

    const UPLOAD_METHOD =
        "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf";

    function uploadProductionDxf(frm) {
        if (!frm || frm.is_new()) {
            frappe.msgprint(__("احفظ الطلب قبل رفع ملف DXF."));
            return null;
        }

        const orderName = frm.doc.name;
        const replacing = Boolean(frm.doc.production_dxf);
        const documentContext = window.AlmdinaDocumentContext;
        const identity = documentContext && typeof documentContext.capture === "function"
            ? documentContext.capture(frm)
            : null;
        const isCurrent = () => documentContext && typeof documentContext.isCurrent === "function"
            ? documentContext.isCurrent(frm, identity)
            : window.cur_frm === frm;

        // Security contract: create a brand-new private File without a document
        // attachment. The server owns authorization, geometry validation, and the
        // final attachment to the Door Cutting Order after validation succeeds.
        return new frappe.ui.FileUploader({
            folder: "Home/Attachments",
            make_attachments_public: false,
            allow_toggle_private: false,
            allow_multiple: false,
            disable_file_browser: true,
            allow_web_link: false,
            allow_take_photo: false,
            restrictions: {
                allowed_file_types: [".dxf"],
                max_file_size: 10 * 1024 * 1024,
            },
            on_success(file) {
                if (!isCurrent()) return null;
                return frappe.call({
                    method: UPLOAD_METHOD,
                    args: {
                        order_name: orderName,
                        file_url: file.file_url,
                    },
                    freeze: true,
                    freeze_message: __("جاري التحقق من ملف DXF وتطبيق الخطة..."),
                }).then(() => {
                    if (isCurrent()) {
                        frappe.show_alert({
                            message: replacing
                                ? __("تم استبدال ملف DXF والتحقق منه.")
                                : __("تم رفع ملف DXF والتحقق منه."),
                            indicator: "green",
                        }, 5);
                    }
                    if (frm.doc && frm.doc.name === orderName) {
                        return frm.reload_doc();
                    }
                    return null;
                });
            },
        });
    }

    // Always install the secure owner, even if a legacy bundle defined the same
    // public helper first. This prevents a stale uploader from attaching the File
    // to the order before the granular DXF authorization runs.
    frappe.almdina.upload_production_dxf = uploadProductionDxf;
    frappe.almdina.__secureDxfUploadInstalled = true;
})();
