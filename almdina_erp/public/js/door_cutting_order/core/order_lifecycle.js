(() => {
    "use strict";

    const ACTION_GROUP = __("دورة الطلب"); // legacy cleanup only
    const NON_RETURNABLE_STATUSES = new Set(["Draft", "Rejected", "Delivered", "Cancelled"]);
    const NON_CANCELLABLE_STATUSES = new Set(["Cancelled", "Delivered", "Completed"]);
    const LABELS = Object.freeze({
        submit_for_review: __("إرسال للمراجعة"),
        approve: __("اعتماد الطلب"),
        create_revision: __("تعديل الطلب"),
        return_to_draft: __("إعادة للمسودة"),
        cancel: __("إلغاء الطلب"),
    });
    const RETIRED_LABELS = Object.freeze([
        __("إرسال للمراجعة"),
        __("اعتماد الطلب"),
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

    function removeRetiredLifecycleButtons(frm) {
        RETIRED_LABELS.forEach(label => {
            frm.remove_custom_button(label);
            frm.remove_custom_button(label, ACTION_GROUP);
            frm.remove_custom_button(label, __("Order Workflow"));
        });
    }

    function removeManagedLifecycleButton(frm, label) {
        frm.remove_custom_button(label);
        frm.remove_custom_button(label, ACTION_GROUP);
        frm.remove_custom_button(label, __("Order Workflow"));
        if (frm.__almdinaLifecycleRenderedLabels instanceof Set) {
            frm.__almdinaLifecycleRenderedLabels.delete(label);
        }
    }

    function removeLifecycleButtons(frm) {
        removeRetiredLifecycleButtons(frm);
        removeManagedLifecycleButton(frm, LABELS.return_to_draft);
        removeManagedLifecycleButton(frm, LABELS.cancel);
    }

    function rememberLifecycleButton(frm, label) {
        if (!(frm.__almdinaLifecycleRenderedLabels instanceof Set)) {
            frm.__almdinaLifecycleRenderedLabels = new Set();
        }
        frm.__almdinaLifecycleRenderedLabels.add(label);
    }

    function ensureLifecycleButton(frm, label, handler) {
        if (lifecycleButtonRendered(frm, label)) return null;
        const button = frm.add_custom_button(label, handler);
        rememberLifecycleButton(frm, label);
        return button;
    }

    function actionAllowed(context, action) {
        return Boolean(
            context &&
            context.actions &&
            context.actions[action] &&
            context.actions[action].allowed === true
        );
    }

    function isSuperseded(frm) {
        return String((frm && frm.doc && frm.doc.revision_state) || "Current") === "Superseded";
    }

    function canReturnToDraft(frm, context) {
        if (!frm || !frm.doc || frm.is_new() || isSuperseded(frm)) return false;
        const status = String(frm.doc.status || "Draft");
        if (NON_RETURNABLE_STATUSES.has(status)) return false;
        return actionAllowed(context, "return_to_draft");
    }

    function canCancelOrder(frm, context) {
        if (!frm || !frm.doc || frm.is_new() || isSuperseded(frm)) return false;
        const status = String(frm.doc.status || "Draft");
        if (NON_CANCELLABLE_STATUSES.has(status)) return false;
        return actionAllowed(context, "cancel");
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
        removeRetiredLifecycleButtons(frm);
        if (!frm || frm.is_new()) {
            removeManagedLifecycleButton(frm, LABELS.return_to_draft);
            removeManagedLifecycleButton(frm, LABELS.cancel);
            return;
        }

        if (canReturnToDraft(frm, context)) {
            ensureLifecycleButton(
                frm,
                LABELS.return_to_draft,
                () => returnToDraft(frm)
            );
        } else {
            removeManagedLifecycleButton(frm, LABELS.return_to_draft);
        }
        if (canCancelOrder(frm, context)) {
            const cancelButton = ensureLifecycleButton(
                frm,
                LABELS.cancel,
                () => cancelOrder(frm)
            );
            if (cancelButton && typeof cancelButton.removeClass === "function") {
                cancelButton.removeClass("btn-default").addClass("btn-danger");
            }
        } else {
            removeManagedLifecycleButton(frm, LABELS.cancel);
        }
    }

    function loadContext(frm) {
        if (!frm || frm.is_new()) {
            frm.__almdina_lifecycle_context = null;
            frm.__almdinaLifecycleContextPending = false;
            removeLifecycleButtons(frm);
            return Promise.resolve(null);
        }

        const contextApi = documentContext();
        if (
            !contextApi
            || typeof contextApi.capture !== "function"
            || typeof contextApi.isCurrent !== "function"
        ) {
            removeLifecycleButtons(frm);
            return Promise.resolve(null);
        }

        if (
            frm.__almdinaLifecycleContextPromise
            && contextApi.isCurrent(frm, frm.__almdinaLifecycleContextToken)
        ) {
            return frm.__almdinaLifecycleContextPromise;
        }

        const cached = frm.__almdina_lifecycle_context;
        if (cached && cached.order_name === frm.doc.name) installButtons(frm, cached);
        else removeLifecycleButtons(frm);

        const identity = contextApi.capture(frm);
        frm.__almdinaLifecycleContextPending = true;
        const request = Promise.resolve(
            frappe.call({
                method: "almdina_erp.almdina_erp.services.order_lifecycle_permission_service.get_order_lifecycle_context",
                args: { order_name: frm.doc.name },
            })
        ).then(response => {
            if (!contextApi.isCurrent(frm, identity)) return frm.__almdina_lifecycle_context;
            const context = response.message || null;
            if (!context || context.order_name !== frm.doc.name) {
                removeLifecycleButtons(frm);
                return frm.__almdina_lifecycle_context;
            }
            frm.__almdina_lifecycle_context = context;
            installButtons(frm, context);
            return context;
        }).catch(error => {
            if (!contextApi.isCurrent(frm, identity)) return frm.__almdina_lifecycle_context;
            console.error("Failed to load order lifecycle permissions", error);
            if (cached && cached.order_name === frm.doc.name) installButtons(frm, cached);
            else removeLifecycleButtons(frm);
            return frm.__almdina_lifecycle_context;
        }).finally(() => {
            if (frm.__almdinaLifecycleContextPromise === request) {
                frm.__almdinaLifecycleContextPending = false;
                frm.__almdinaLifecycleContextPromise = null;
                frm.__almdinaLifecycleContextToken = null;
                const owner = documentContext();
                if (owner && typeof owner.settleSurfaces === "function") {
                    owner.settleSurfaces(frm, 0);
                }
            }
        });

        frm.__almdinaLifecycleContextToken = identity;
        frm.__almdinaLifecycleContextPromise = request;
        return request;
    }

    function lifecycleButtonRendered(frm, label) {
        const root = frm && frm.page && frm.page.wrapper;
        const node = root && (root.nodeType ? root : root[0]);
        if (node && typeof node.querySelectorAll === "function") {
            return [...node.querySelectorAll(".custom-actions button, .page-actions button")]
                .some((button) => String(button.textContent || "").replace(/\s+/g, " ").trim() === label);
        }
        const buttons = frm.custom_buttons || {};
        return Boolean(
            buttons[label]
            || (
                frm.__almdinaLifecycleRenderedLabels instanceof Set
                && frm.__almdinaLifecycleRenderedLabels.has(label)
            )
        );
    }

    function lifecycleActionsReady(frm) {
        if (!frm || !frm.doc || frm.is_new()) return true;
        if (frm.__almdinaLifecycleContextPending) return false;
        const context = frm.__almdina_lifecycle_context;
        if (!context || context.order_name !== frm.doc.name) return true;
        const wantsReturn = canReturnToDraft(frm, context);
        const wantsCancel = canCancelOrder(frm, context);
        return (
            lifecycleButtonRendered(frm, LABELS.return_to_draft) === wantsReturn
            && lifecycleButtonRendered(frm, LABELS.cancel) === wantsCancel
        );
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

    if (typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            const frm = window.cur_frm;
            if (!frm || frm.doctype !== "Door Cutting Order") return;
            loadContext(frm);
        });
    }

    const surfaceOwner = documentContext();
    if (surfaceOwner && typeof surfaceOwner.registerSurface === "function") {
        surfaceOwner.registerSurface("order-lifecycle-actions", {
            isReady(frm) { return lifecycleActionsReady(frm); },
            recover(frm) { return loadContext(frm); },
        });
    }

    window.AlmdinaOrderLifecycleUX = Object.freeze({
        actionAllowed,
        installButtons,
        loadContext,
        orderCanEdit,
    });
})();
