(() => {
    "use strict";

    const ACTION_GROUP = __("دورة الطلب");
    const LABELS = Object.freeze({
        submit_for_review: __("إرسال للمراجعة"),
        approve: __("اعتماد الطلب"),
        create_revision: __("تعديل الطلب"),
        return_to_draft: __("إعادة للمسودة"),
        cancel: __("إلغاء الطلب"),
    });
    const LEGACY_LABELS = Object.freeze([
        __("إرسال للمراجعة"),
        __("اعتماد الطلب"),
        __("تعديل الطلب"),
        __("إنشاء نسخة تعديل"),
        __("إعادة للمسودة"),
        __("إلغاء الطلب"),
        __("Cancel Order"),
        "Cancel Order",
    ]);

    function permissions() {
        return window.AlmdinaPermissions;
    }

    function documentContext() {
        return window.AlmdinaDocumentContext;
    }

    function can(frm, capability) {
        const context = permissions();
        return Boolean(
            context &&
            (
                typeof context.canDocument === "function"
                    ? context.canDocument(frm, capability)
                    : context.can(capability)
            )
        );
    }

    function orderCanEdit(frm) {
        if (!frm || !frm.doc || Number(frm.doc.docstatus || 0) !== 0) return false;
        if (frm.is_new()) return can(frm, "create_order");
        if ((frm.doc.revision_state || "Current") === "Superseded") return false;

        const revisionUx = window.AlmdinaOrderRevisionUX;
        if (revisionUx && typeof revisionUx.isEditableDraft === "function") {
            return revisionUx.isEditableDraft(frm);
        }

        const context = frm.__almdina_lifecycle_context;
        const status = frm.doc.status || "Draft";
        if (status !== "Draft") return false;

        let allowed = can(frm, "edit_order");
        if (context && context.order_name === frm.doc.name) {
            allowed = context.editable === true;
        }
        const sessionActive = Boolean(
            frm.__almdina_edit_session
            || (
                frappe.almdina
                && frappe.almdina._orderEditSessions
                && frm.doc.name
                && frappe.almdina._orderEditSessions[frm.doc.name]
                && frappe.almdina._orderEditSessions[frm.doc.name].active
            )
        );
        return allowed && sessionActive;
    }

    function installGlobalPolicy() {
        frappe.provide("frappe.almdina");
        frappe.almdina.orderCanEdit = orderCanEdit;
        frappe.almdina.isOrderEditor = frm => can(frm || window.cur_frm, "edit_order");
    }

    function removeLifecycleButtons(frm) {
        LEGACY_LABELS.forEach(label => {
            frm.remove_custom_button(label, ACTION_GROUP);
            frm.remove_custom_button(label, __("Order Workflow"));
        });
    }

    function actionAllowed(context, action) {
        return Boolean(
            context &&
            context.actions &&
            context.actions[action] &&
            context.actions[action].allowed === true
        );
    }

    function callAction(frm, options) {
        const identity = documentContext().capture(frm);
        return frappe.call({
            method: options.method,
            args: options.args || { order_name: frm.doc.name },
            freeze: true,
            freeze_message: options.freezeMessage,
        }).then(response => {
            if (!documentContext().isCurrent(frm, identity)) return null;
            const result = response.message || {};
            if (options.routeToResult && result.name) {
                frappe.show_alert({
                    message: options.successMessage,
                    indicator: "green",
                }, 6);
                frappe.set_route("Form", "Door Cutting Order", result.name);
                return result;
            }
            frappe.show_alert({
                message: options.successMessage,
                indicator: options.indicator || "green",
            }, 6);
            return frm.reload_doc().then(() => result);
        });
    }

    function submitForReview(frm) {
        frappe.confirm(
            __("سيتم إرسال الطلب للمراجعة ومنع التعديل عليه بعد الاعتماد. هل تريد المتابعة؟"),
            () => callAction(frm, {
                method: "almdina_erp.almdina_erp.services.order_lifecycle_permission_service.submit_order_for_review",
                freezeMessage: __("جاري إرسال الطلب للمراجعة..."),
                successMessage: __("تم إرسال الطلب للمراجعة."),
            })
        );
    }

    function approveOrder(frm) {
        frappe.confirm(
            __("سيتم اعتماد الطلب والخطة الحالية. هل تريد المتابعة؟"),
            () => callAction(frm, {
                method: "almdina_erp.almdina_erp.services.order_approval_service.approve_order",
                freezeMessage: __("جاري اعتماد الطلب..."),
                successMessage: __("تم اعتماد الطلب بنجاح."),
            })
        );
    }

    function returnToDraft(frm) {
        frappe.prompt(
            [{
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("سبب إعادة الطلب للمسودة (اختياري)"),
                description: __("سيتم إلغاء مراحل الإنتاج النشطة وإعادة نفس الطلب إلى المسودة حتى يمكن تعديله."),
                reqd: 0,
            }],
            values => callAction(frm, {
                method: "almdina_erp.almdina_erp.services.order_revision_service.return_order_to_draft",
                args: {
                    order_name: frm.doc.name,
                    reason: String(values.reason || "").trim(),
                },
                freezeMessage: __("جاري إعادة الطلب للمسودة..."),
                successMessage: __("تمت إعادة الطلب نفسه إلى المسودة."),
            }),
            __("إعادة الطلب للمسودة"),
            __("تأكيد الإعادة")
        );
    }

    function cancelOrder(frm) {
        frappe.prompt(
            [{
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("سبب إلغاء الطلب"),
                description: __("سيتم إلغاء مراحل الإنتاج النشطة التي يمكن إلغاؤها بأمان."),
                reqd: 1,
            }],
            values => {
                frappe.confirm(
                    __("هذا الإجراء يلغي الطلب ومراحل الإنتاج النشطة. هل تريد المتابعة؟"),
                    () => callAction(frm, {
                        method: "almdina_erp.almdina_erp.services.order_lifecycle_service.cancel_order",
                        args: {
                            order_name: frm.doc.name,
                            reason: String(values.reason || "").trim(),
                        },
                        freezeMessage: __("جاري إلغاء الطلب..."),
                        successMessage: __("تم إلغاء الطلب ومراحل الإنتاج المرتبطة به."),
                        indicator: "orange",
                    })
                );
            },
            __("إلغاء الطلب"),
            __("متابعة")
        );
    }

    function installButtons(frm, context) {
        removeLifecycleButtons(frm);
        if (frm.is_new() || !context || context.order_name !== frm.doc.name) return;

        // Review and order-approval were retired: orders go straight to production.
        // Keep return-to-draft / cancel for stuck or in-flight documents.
        if (actionAllowed(context, "return_to_draft")) {
            frm.add_custom_button(
                LABELS.return_to_draft,
                () => returnToDraft(frm),
                ACTION_GROUP
            );
        }
        if (actionAllowed(context, "cancel")) {
            frm.add_custom_button(
                LABELS.cancel,
                () => cancelOrder(frm),
                ACTION_GROUP
            );
        }
    }

    function loadContext(frm) {
        removeLifecycleButtons(frm);
        if (frm.is_new()) {
            frm.__almdina_lifecycle_context = null;
            return Promise.resolve(null);
        }

        const identity = documentContext().capture(frm);
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.order_lifecycle_permission_service.get_order_lifecycle_context",
            args: { order_name: frm.doc.name },
        }).then(response => {
            if (!documentContext().isCurrent(frm, identity)) return null;
            const context = response.message || null;
            if (!context || context.order_name !== frm.doc.name) return null;
            frm.__almdina_lifecycle_context = context;
            installButtons(frm, context);
            return context;
        }).catch(error => {
            if (documentContext().isCurrent(frm, identity)) {
                frm.__almdina_lifecycle_context = null;
                removeLifecycleButtons(frm);
            }
            console.error("Failed to load order lifecycle permissions", error);
            return null;
        });
    }

    installGlobalPolicy();

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            setTimeout(() => loadContext(frm), 0);
        },
        refresh(frm) {
            setTimeout(() => loadContext(frm), 0);
        },
    });

    window.AlmdinaOrderLifecycleUX = Object.freeze({
        actionAllowed,
        installButtons,
        loadContext,
        orderCanEdit,
    });
})();
