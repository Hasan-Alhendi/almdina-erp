(() => {
    "use strict";

    if (window.AlmdinaCustomerInvoiceToolbarUX) return;

    const LABEL = "طباعة فاتورة الزبون";
    const GROUP = "طباعة";
    const FRAME_ID = "dco-customer-invoice-toolbar-print-frame";

    function canPrint() {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && typeof permissions.can === "function"
            && permissions.can("print_customer_invoice")
        );
    }

    function current(frm, identity) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, identity);
        }
        return Boolean(window.cur_frm === frm && frm.doc && frm.doc.name === identity);
    }

    function capture(frm) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.capture === "function") {
            return context.capture(frm);
        }
        return frm.doc && frm.doc.name;
    }

    function removeButton(frm) {
        try {
            frm.remove_custom_button(__(LABEL), __(GROUP));
        } catch (error) {
            void error;
        }
    }

    function printHtml(html) {
        document.getElementById(FRAME_ID)?.remove();
        const frame = document.createElement("iframe");
        frame.id = FRAME_ID;
        frame.setAttribute("aria-hidden", "true");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:1px;height:1px;border:0;opacity:0;pointer-events:none;z-index:-1";
        let cleaned = false;
        const cleanup = () => {
            if (cleaned) return;
            cleaned = true;
            frame.remove();
        };
        frame.onload = () => {
            try {
                const printWindow = frame.contentWindow;
                if (!printWindow) throw new Error("Print frame is unavailable");
                printWindow.addEventListener("afterprint", cleanup, { once: true });
                window.setTimeout(() => {
                    printWindow.focus();
                    printWindow.print();
                }, 100);
            } catch (error) {
                console.error("Customer invoice toolbar print failed", error);
                cleanup();
                frappe.msgprint(__("تعذر تشغيل الطباعة. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            }
        };
        frame.srcdoc = html;
        document.body.appendChild(frame);
        window.setTimeout(cleanup, 120000);
    }

    function printCustomerInvoice(frm) {
        if (!canPrint()) {
            frappe.msgprint(__("ليس لديك صلاحية طباعة فاتورة الزبون."));
            return Promise.resolve(false);
        }
        if (frm.is_new()) {
            frappe.msgprint(__("احفظ الطلب قبل طباعة فاتورة الزبون."));
            return Promise.resolve(false);
        }

        const identity = capture(frm);
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.cost_document_service.get_customer_invoice_document",
            args: { order_name: frm.doc.name },
            freeze: true,
            freeze_message: __("جاري تجهيز فاتورة الزبون..."),
        }).then(response => {
            if (!current(frm, identity)) return false;
            const payload = response.message || {};
            if (payload.kind !== "customer_invoice" || payload.order_name !== frm.doc.name) {
                throw new Error("Customer invoice response does not match the active order");
            }
            const documents = window.AlmdinaFinancialDocuments;
            if (!documents || typeof documents.documentHtml !== "function") {
                throw new Error("Financial document presenter is unavailable");
            }
            printHtml(documents.documentHtml(payload));
            return true;
        }).catch(error => {
            console.error("Customer invoice toolbar preparation failed", error);
            frappe.msgprint(__("تعذر تجهيز فاتورة الزبون. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        });
    }

    function install(frm) {
        removeButton(frm);
        if (!canPrint() || frm.is_new()) return;
        frm.add_custom_button(
            __(LABEL),
            () => printCustomerInvoice(frm),
            __(GROUP)
        );
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            window.setTimeout(() => install(frm), 0);
        },
        refresh(frm) {
            window.setTimeout(() => install(frm), 0);
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") install(frm);
    });

    window.AlmdinaCustomerInvoiceToolbarUX = Object.freeze({
        install,
        printCustomerInvoice,
    });
})();
