(() => {
    "use strict";

    if (window.AlmdinaCustomerInvoiceToolbarUX) return;

    const CUSTOMER_CLASS = "dco-secure-print-customer-invoice";
    const WHATSAPP_CLASS = "dco-whatsapp-send-invoice";
    const COST_API_FLAG = "__almdinaInvoiceButtonCoordinator";
    const STATUS_METHOD = "almdina_erp.almdina_erp.services.whatsapp_service.get_whatsapp_delivery_status";
    const SEND_METHOD = "almdina_erp.almdina_erp.services.whatsapp_service.send_order_invoice";
    const INVOICE_CONFIRM_MESSAGE = "هل تريد إرسال الفاتورة للزبون؟";
    const DISCONNECTED_MESSAGE = "لن يتم إرسال رسالة واتساب لأن الجلسة غير متصلة.";

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, capability)
                    : permissions.can(capability)
            )
        );
    }

    function canPrint(frm) {
        return can(frm, "print_customer_invoice");
    }

    function uiButton(options) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for DCO customer invoice toolbar");
        }
        return ui.button(options);
    }

    function costWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper : $();
    }

    function costActions(frm) {
        return costWrapper(frm).find(".dco-cost-actions").first();
    }

    function currentIdentity(frm) {
        const context = window.AlmdinaDocumentContext;
        return context && typeof context.capture === "function"
            ? context.capture(frm)
            : `${frm && frm.doctype || "Door Cutting Order"}::${frm && frm.doc && frm.doc.name || "__new__"}`;
    }

    function isCurrent(frm, identity) {
        const context = window.AlmdinaDocumentContext;
        return context && typeof context.isCurrent === "function"
            ? context.isCurrent(frm, identity)
            : currentIdentity(frm) === identity;
    }

    function frontend() {
        return window.AlmdinaFrontend || null;
    }

    function errorMessage(error, fallback) {
        const api = frontend();
        if (api && typeof api.errorMessage === "function") {
            return api.errorMessage(error, fallback);
        }
        return String((error && error.message) || fallback || "");
    }

    function rpc(method, args, options) {
        const api = frontend();
        if (!api || typeof api.rpc !== "function") {
            return Promise.reject(new Error("تعذر الاتصال بالخادم."));
        }
        return api.rpc(method, args, options || { freeze: true, freezeMessage: "جاري إرسال واتساب..." });
    }

    function sendInvoice(frm) {
        const orderName = String(frm && frm.doc && frm.doc.name || "").trim();
        if (!orderName) {
            frappe.msgprint("تعذر تحديد الطلب لإرسال الفاتورة.");
            return Promise.resolve(null);
        }
        return rpc(SEND_METHOD, { order_name: orderName }).then(result => {
            const payload = result || {};
            const ok = payload.ok !== false && payload.code !== "document_failed";
            frappe.show_alert({
                message: payload.message || (ok ? "تم إرسال فاتورة الزبون إلى الزبون عبر واتساب." : "تعذر إرسال ملف الفاتورة."),
                indicator: ok ? "green" : "orange",
            }, 8);
            if (!ok && payload.message) {
                frappe.msgprint({ title: "إرسال واتساب", message: payload.message, indicator: "orange" });
            }
            return payload;
        }).catch(error => {
            frappe.msgprint({
                title: "تعذر إرسال واتساب",
                message: errorMessage(error, "حدثت مشكلة أثناء إرسال فاتورة الزبون."),
                indicator: "red",
            });
            return null;
        });
    }

    function offerInvoiceSend(frm) {
        if (!canPrint(frm) || frm.is_new()) return false;
        const api = frontend();
        if (!api || typeof api.rpc !== "function") {
            frappe.msgprint({
                title: "واتساب",
                message: DISCONNECTED_MESSAGE,
                indicator: "orange",
            });
            return false;
        }
        rpc(STATUS_METHOD, {}, { freeze: false }).then(status => {
            const snapshot = status || {};
            if (!snapshot.working) {
                frappe.msgprint({
                    title: "واتساب",
                    message: snapshot.reason || DISCONNECTED_MESSAGE,
                    indicator: "orange",
                });
                return;
            }
            frappe.confirm(INVOICE_CONFIRM_MESSAGE, () => {
                sendInvoice(frm);
            });
        }).catch(error => {
            frappe.msgprint({
                title: "واتساب",
                message: errorMessage(error, DISCONNECTED_MESSAGE),
                indicator: "orange",
            });
        });
        return true;
    }

    function bindSecurePresenter(frm, created) {
        if (!created) return;
        const documents = window.AlmdinaFinancialDocuments;
        if (documents && typeof documents.apply === "function") {
            // The secure presenter owns the click handler and the server-authorized
            // payload. Re-applying only after a newly rendered button avoids two
            // independent print handlers while making the action immediately live.
            setTimeout(() => documents.apply(frm), 0);
        }
    }

    function ensureCostButton(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper.length) return false;
        const actions = costActions(frm);
        if (!actions.length) return false;

        const visible = !frm.is_new() && canPrint(frm);
        let button = actions.find(`.${CUSTOMER_CLASS}`).first();
        actions.find(`.${CUSTOMER_CLASS}`).slice(1).remove();

        if (!visible) {
            button.remove();
            actions.find(`.${WHATSAPP_CLASS}`).remove();
            return false;
        }

        actions.addClass("almdina-ui");

        let created = false;
        if (!button.length) {
            button = $(uiButton({
                label: __("طباعة فاتورة الزبون"),
                variant: "primary",
                size: "btn-sm",
                className: CUSTOMER_CLASS,
            }));
            actions.prepend(button);
            created = true;
        }
        button
            .prop("disabled", false)
            .removeClass("is-plan-stale")
            .attr("aria-disabled", "false");
        bindSecurePresenter(frm, created);
        ensureWhatsAppButton(frm, actions);
        return true;
    }

    function ensureWhatsAppButton(frm, actions) {
        const visible = !frm.is_new() && canPrint(frm);
        let button = actions.find(`.${WHATSAPP_CLASS}`).first();
        actions.find(`.${WHATSAPP_CLASS}`).slice(1).remove();
        if (!visible) {
            button.remove();
            return false;
        }
        if (!button.length) {
            button = $(uiButton({
                label: __("إرسال الفاتورة عبر واتساب"),
                variant: "secondary",
                size: "btn-sm",
                className: WHATSAPP_CLASS,
            }));
            const printButton = actions.find(`.${CUSTOMER_CLASS}`).first();
            if (printButton.length) printButton.after(button);
            else actions.prepend(button);
        }
        button
            .prop("disabled", false)
            .removeClass("is-plan-stale")
            .attr("aria-disabled", "false")
            .off("click.almdinaWhatsAppInvoice")
            .on("click.almdinaWhatsAppInvoice", event => {
                event.preventDefault();
                offerInvoiceSend(frm);
            });
        return true;
    }

    function observeCostActions(frm) {
        const wrapper = costWrapper(frm);
        const element = wrapper.get(0);
        if (!element) return;

        if (frm.__almdina_invoice_button_observer) {
            frm.__almdina_invoice_button_observer.disconnect();
        }
        let queued = false;
        const observer = new MutationObserver(() => {
            if (queued) return;
            queued = true;
            requestAnimationFrame(() => {
                queued = false;
                ensureCostButton(frm);
            });
        });
        observer.observe(element, { childList: true, subtree: true });
        frm.__almdina_invoice_button_observer = observer;
    }

    function wrapCostPresenter() {
        const original = window.AlmdinaOrderCostUX;
        if (!original || original[COST_API_FLAG] || typeof original.render !== "function") return;

        window.AlmdinaOrderCostUX = Object.freeze({
            ...original,
            [COST_API_FLAG]: true,
            render(frm) {
                const result = original.render(frm);
                requestAnimationFrame(() => ensureCostButton(frm));
                return result;
            },
        });
    }

    function reconcileAuthoritativeCost(frm) {
        if (!frm || frm.is_new() || !can(frm, "view_costs")) return Promise.resolve(false);
        const edgeBanding = window.AlmdinaMultiEdgeBanding;
        const costPermissions = window.AlmdinaCostPermissionsUX;
        if (
            !edgeBanding
            || typeof edgeBanding.ensureProfiles !== "function"
            || !costPermissions
            || typeof costPermissions.apply !== "function"
        ) {
            return Promise.resolve(false);
        }

        const identity = currentIdentity(frm);
        if (
            frm.__almdina_invoice_cost_reconcile_promise
            && frm.__almdina_invoice_cost_reconcile_identity === identity
        ) {
            return frm.__almdina_invoice_cost_reconcile_promise;
        }

        // Edge Banding Type is loaded asynchronously by the entry UI. Its local
        // preview renderer may run after the protected cost snapshot and write
        // temporary preview values into the child rows. Always let that profile
        // load/render settle first, then re-apply the server cost snapshot so the
        // cost tab and invoice end with the persisted server calculation.
        const promise = Promise.resolve(edgeBanding.ensureProfiles(frm))
            .catch(error => {
                console.error("Edge profile readiness failed before cost reconciliation", error);
            })
            .then(() => {
                if (!isCurrent(frm, identity)) return false;
                costPermissions.apply(frm);
                return true;
            })
            .finally(() => {
                if (frm.__almdina_invoice_cost_reconcile_promise === promise) {
                    frm.__almdina_invoice_cost_reconcile_promise = null;
                    frm.__almdina_invoice_cost_reconcile_identity = null;
                }
            });

        frm.__almdina_invoice_cost_reconcile_identity = identity;
        frm.__almdina_invoice_cost_reconcile_promise = promise;
        return promise;
    }

    function install(frm) {
        wrapCostPresenter();
        ensureCostButton(frm);
        observeCostActions(frm);
        requestAnimationFrame(() => ensureCostButton(frm));
        reconcileAuthoritativeCost(frm).catch(error => {
            console.error("Authoritative invoice cost reconciliation failed", error);
        });
    }

    function printCustomerInvoice(frm) {
        const documents = window.AlmdinaFinancialDocuments;
        if (!documents || typeof documents.printCustomerInvoice !== "function") {
            frappe.msgprint(__("تعذر تحميل خدمة طباعة فاتورة الزبون. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return Promise.resolve(false);
        }
        return Promise.resolve(documents.printCustomerInvoice(frm))
            .then(() => true)
            .catch(error => {
                if (!error || !error.__almdinaHandled) {
                    console.error("Customer invoice print failed", error);
                    frappe.msgprint(__("تعذر تجهيز فاتورة الزبون. أعد تحميل الصفحة ثم حاول مرة أخرى."));
                }
                return false;
            });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            setTimeout(() => install(frm), 0);
        },
        refresh(frm) {
            setTimeout(() => install(frm), 0);
        },
        almdina_edit_session_changed(frm) {
            setTimeout(() => install(frm), 0);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") install(frm);
    });

    window.AlmdinaCustomerInvoiceToolbarUX = Object.freeze({
        INVOICE_CONFIRM_MESSAGE,
        WHATSAPP_CLASS,
        install,
        ensureCostButton,
        offerInvoiceSend,
        reconcileAuthoritativeCost,
        printCustomerInvoice,
    });
})();
