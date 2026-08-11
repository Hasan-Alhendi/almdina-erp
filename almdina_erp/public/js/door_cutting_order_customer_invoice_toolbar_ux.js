(() => {
    "use strict";

    if (window.AlmdinaCustomerInvoiceToolbarUX) return;

    const CUSTOMER_CLASS = "dco-secure-print-customer-invoice";
    const COST_API_FLAG = "__almdinaInvoiceButtonCoordinator";

    function canPrint(frm) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, "print_customer_invoice")
                    : permissions.can("print_customer_invoice")
            )
        );
    }

    function costWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper : $();
    }

    function costActions(frm) {
        return costWrapper(frm).find(".dco-cost-actions").first();
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
            return false;
        }

        let created = false;
        if (!button.length) {
            button = $(`<button type="button" class="btn btn-primary btn-sm ${CUSTOMER_CLASS}">${__("طباعة فاتورة الزبون")}</button>`);
            actions.prepend(button);
            created = true;
        }
        button
            .prop("disabled", false)
            .removeClass("is-plan-stale")
            .attr("aria-disabled", "false");
        bindSecurePresenter(frm, created);
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

    function install(frm) {
        wrapCostPresenter();
        ensureCostButton(frm);
        observeCostActions(frm);
        requestAnimationFrame(() => ensureCostButton(frm));
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
        install,
        ensureCostButton,
        printCustomerInvoice,
    });
})();
