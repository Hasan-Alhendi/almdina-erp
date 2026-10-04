"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const panelSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_production_settings/whatsapp_panel.js"),
    "utf8"
);
const deliverySource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/order_entry/door_cutting_order_whatsapp_delivery_ux.js"
    ),
    "utf8"
);

function loadPanel(overrides = {}) {
    const timers = [];
    const fakeWindow = {
        setInterval(fn, ms) {
            timers.push({ fn, ms, cleared: false });
            return timers.length;
        },
        clearInterval(id) {
            const timer = timers[id - 1];
            if (timer) timer.cleared = true;
        },
        ...overrides.window,
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: {
            show_alert() {},
            ui: { form: { on() {} } },
        },
        Object,
        Boolean,
        String,
        Promise,
        setTimeout,
    });
    vm.runInContext(panelSource, context);
    return { fakeWindow, timers, api: fakeWindow.AlmdinaFactoryProductionSettingsWhatsApp };
}

function loadDelivery(overrides = {}) {
    const confirms = [];
    const messages = [];
    const fakeWindow = {
        AlmdinaFrontend: overrides.frontend || {
            rpc() { return Promise.resolve({ working: true }); },
            errorMessage(error, fallback) { return String((error && error.message) || fallback); },
        },
        AlmdinaPermissions: overrides.permissions || {
            can() { return true; },
            canDocument() { return true; },
        },
        AlmdinaOrderRevisionUX: overrides.revision || {
            canOfferEditSession() { return true; },
        },
        AlmdinaDcoEditSessionCoordinator: overrides.coordinator || {
            decorate(kind, decorator) {
                this.kind = kind;
                this.adapter = decorator({
                    async save() { return true; },
                });
                return true;
            },
        },
        addEventListener() {},
        ...overrides.window,
    };
    const frappe = {
        confirm(message, yes) {
            confirms.push(message);
            if (yes) yes();
        },
        msgprint(payload) { messages.push(payload); },
        show_alert() {},
        ui: { form: { on() {} } },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        Object,
        Boolean,
        String,
        Promise,
        Number,
    });
    vm.runInContext(deliverySource, context);
    return {
        fakeWindow,
        confirms,
        messages,
        ux: fakeWindow.AlmdinaOrderWhatsAppDeliveryUX,
    };
}

const panel = loadPanel();
assert.equal(panel.api.QR_INTERVAL_MS, 5000);

const requests = [];
const renderer = { snapshots: [] };
const dialogs = {
    opened: 0,
    hidden: null,
    openQr(config) {
        this.opened += 1;
        this.hidden = config.onHide;
        return {
            setQr() {},
            close() {},
        };
    },
};
const attached = panel.api.attach({
    api: {
        getWhatsAppSession() {
            requests.push("session");
            return Promise.resolve({ configured: true, session: null, can_create: true });
        },
        getWhatsAppQr() {
            requests.push("qr");
            return Promise.resolve({ qr_code: "data:image/png;base64,xx", status: "qr_ready", working: false });
        },
        createWhatsAppSession() { return Promise.resolve({}); },
        reconnectWhatsAppSession() { return Promise.resolve({}); },
    },
    renderer: {
        renderWhatsApp(snapshot) { renderer.snapshots.push(snapshot); },
    },
    dialogs,
    frontend: {
        createLatestRequestGate() {
            let current = 0;
            return {
                begin() { current += 1; return current; },
                isCurrent(token) { return token === current; },
                invalidate() { current += 1; },
            };
        },
        errorMessage(error, fallback) { return String(fallback || error); },
    },
    lifecycle: { track() {} },
    translate: (value) => value,
    isActive: () => true,
});

assert.equal(typeof attached.refresh, "function");
attached.dispose();
assert.ok(panel.timers.every((timer) => timer.cleared || timer.ms === 5000));

const dialogsSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_production_settings/dialogs.js"),
    "utf8"
);
const qrHtml = [];
class FakeQrDialog {
    constructor() {
        this.fields_dict = { qr_html: { $wrapper: { html(value) { qrHtml.push(String(value || "")); } } } };
    }
    show() {}
    hide() {}
}
const dialogContext = vm.createContext({
    window: {},
    frappe: { ui: { Dialog: FakeQrDialog }, show_alert() {} },
    Object,
    Boolean,
    String,
    Map,
});
vm.runInContext(dialogsSource, dialogContext);
const qrDialogs = dialogContext.window.AlmdinaFactoryProductionSettingsDialogs.create({
    translate: (value) => value,
    escapeHtml: (value) => String(value ?? ""),
});
const surface = qrDialogs.openQr({ statusLabel: () => "امسح الرمز من واتساب" });
surface.setQr("data:image/png;base64,xx", "qr_ready");
assert.equal(qrHtml.length, 1);
assert.match(qrHtml[0], /data:image\/png;base64,xx/);
assert.match(qrHtml[0], /امسح الرمز من واتساب/);
surface.setQr("http://evil.example/qr.png", "qr_ready");
assert.doesNotMatch(qrHtml[1], /http:\/\/evil\.example/);
assert.match(qrHtml[1], /جاري تجهيز الرمز/);

const delivery = loadDelivery();
assert.equal(delivery.fakeWindow.AlmdinaDcoEditSessionCoordinator.kind, "order");
assert.equal(delivery.ux.CONFIRM_MESSAGE, "هل تريد إرسال ملف القياسات للزبون؟");
assert.equal(delivery.ux.AMENDMENT_CONFIRM_MESSAGE, "هل تريد إرسال تعديلات القياسات للزبون؟");
assert.equal(delivery.ux.BUTTON_ACTION_LABEL, "إرسال القياسات عبر واتساب");
assert.equal(delivery.ux.BUTTON_LABEL_AMENDMENT, "إرسال تعديلات القياسات عبر واتساب");

const invoiceToolbarSource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_customer_invoice_toolbar_ux.js"
    ),
    "utf8"
);
assert.match(invoiceToolbarSource, /إرسال الفاتورة عبر واتساب/);
assert.match(invoiceToolbarSource, /هل تريد إرسال الفاتورة للزبون؟/);
assert.match(invoiceToolbarSource, /dco-whatsapp-send-invoice/);
assert.match(invoiceToolbarSource, /send_order_invoice/);
assert.match(invoiceToolbarSource, /frappe\.confirm\(INVOICE_CONFIRM_MESSAGE/);
assert.doesNotMatch(invoiceToolbarSource, /print_measurements/);

const skipped = delivery.ux.offerAfterOrderSave({
    doctype: "Door Cutting Order",
    __almdina_order_checkpoint_save_in_progress: true,
    doc: { name: "DCO-1" },
});
assert.equal(skipped, false);

function savedDraft(overrides = {}) {
    return {
        doctype: "Door Cutting Order",
        doc: { name: "26-00089", status: "Draft", docstatus: 0 },
        is_new() { return false; },
        is_dirty() { return false; },
        ...overrides,
    };
}

const firstSaveFrm = savedDraft({ __almdina_whatsapp_just_created: true });
assert.equal(delivery.ux.isAmendmentContext(firstSaveFrm), false);
assert.equal(delivery.ux.confirmMessage(firstSaveFrm), delivery.ux.CONFIRM_MESSAGE);
assert.equal(delivery.ux.buttonLabel(firstSaveFrm), delivery.ux.BUTTON_ACTION_LABEL);

const editedFrm = savedDraft({ __almdina_whatsapp_amendment: true });
assert.equal(delivery.ux.isAmendmentContext(editedFrm), true);
assert.equal(delivery.ux.confirmMessage(editedFrm), delivery.ux.AMENDMENT_CONFIRM_MESSAGE);
assert.equal(delivery.ux.buttonLabel(editedFrm), delivery.ux.BUTTON_LABEL_AMENDMENT);

assert.equal(delivery.ux.canShowSendButton({
    doctype: "Door Cutting Order",
    doc: { name: "new-door-cutting-order", status: "Draft" },
    is_new() { return true; },
    is_dirty() { return true; },
}), false);

const dirtyOffer = delivery.ux.offerFromButton(savedDraft({ is_dirty() { return true; } }));
assert.equal(dirtyOffer, false);
assert.equal(delivery.messages.at(-1).message, delivery.ux.SAVE_FIRST_MESSAGE);
assert.equal(delivery.confirms.length, 0);

const buttonOffer = delivery.ux.offerFromButton(savedDraft());
assert.equal(buttonOffer, true);

console.log("whatsapp frontend simulations ok");
