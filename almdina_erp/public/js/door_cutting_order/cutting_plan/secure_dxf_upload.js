(() => {
    "use strict";

    frappe.provide("frappe.almdina");
    if (frappe.almdina.__secureDxfUploadInstalled) return;

    const UPLOAD_METHOD =
        "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        return String(message == null ? "" : message);
    }

    function activateUploadedPlan(frm) {
        if (!frm) return;
        frm.__almdina_active_plan_tab = "Custom";
        const workspace = window.AlmdinaPlanWorkspaceState;
        if (workspace && typeof workspace.invalidate === "function") {
            workspace.invalidate(frm, "dxf_uploaded");
        }
    }

    function uploadProductionDxf(frm) {
        if (!frm || frm.is_new()) {
            frappe.msgprint(translate("Save the order before uploading a DXF file."));
            return null;
        }

        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.fileUploader !== "function") {
            throw new Error("AlmdinaUi.fileUploader is required for secure DXF upload");
        }

        const orderName = frm.doc.name;
        const replacing = Boolean(frm.doc.production_dxf);
        const context = window.AlmdinaDocumentContext;
        const frontend = window.AlmdinaFrontend;
        if (!context || typeof context.capture !== "function" || typeof context.isCurrent !== "function"
            || !frontend || typeof frontend.ownedRpc !== "function" || typeof ui.errorDialog !== "function") {
            frappe.msgprint(translate("The DXF upload service is not ready. Save or cancel unsaved changes, then reload the page."));
            return null;
        }
        const owner = context.capture(frm);
        const ownsUpload = () => Boolean(owner && context.isCurrent(frm, owner));

        // Security contract: create a brand-new private File without a document
        // attachment. The server owns authorization, geometry validation, and the
        // final attachment to the Door Cutting Order after validation succeeds.
        return ui.fileUploader({
            preset: "securePrivate",
            restrictions: {
                allowed_file_types: [".dxf"],
                max_file_size: 10 * 1024 * 1024,
            },
            on_success(file) {
                if (!ownsUpload()) return null;
                return frontend.ownedRpc(UPLOAD_METHOD, {
                        order_name: orderName,
                        file_url: file.file_url,
                        file_id: file.name,
                    }, {
                    freeze: true,
                    freezeMessage: translate("Validating the DXF file and applying the plan..."),
                    fallback: translate("The DXF file could not be accepted"),
                }).then(() => {
                    if (!ownsUpload()) return null;
                    frappe.show_alert({
                        message: replacing
                            ? translate("The DXF file was replaced and validated.")
                            : translate("The DXF file was uploaded and validated."),
                        indicator: "green",
                    }, 5);
                    activateUploadedPlan(frm);
                    return frm.reload_doc();
                }, error => {
                    if (!ownsUpload()) return null;
                    const dialog = ui.errorDialog(error, {
                        isCurrent: ownsUpload,
                        outcomeMessages: {
                            rejected: translate("The current DXF cutting plan was not replaced."),
                        },
                    });
                    if (dialog && context && typeof context.registerCleanup === "function") {
                        context.registerCleanup(frm, "dxf-upload-error", () => dialog.hide());
                    }
                    return null;
                });
            },
        });
    }

    // Always install the secure owner, even if a legacy bundle defined the same
    // public helper first. Shop Floor UX wraps this core with stage/capability guards.
    frappe.almdina.__uploadProductionDxfCore = uploadProductionDxf;
    frappe.almdina.__secureDxfUploadInstalled = true;
    if (typeof frappe.almdina.upload_production_dxf !== "function") {
        frappe.almdina.upload_production_dxf = uploadProductionDxf;
    }
})();
