"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const files = [
    "public/js/door_cutting_order/core/order_lifecycle.js",
    "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_action_permission_guard.js",
    "public/js/door_cutting_order/core/door_cutting_order_form_sidebar_controller.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_freshness_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_status_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_document_context.js",
    "public/js/door_cutting_order/core/door_cutting_order_tab_edit_lifecycle_guard.js",
    "public/js/door_cutting_order/core/door_cutting_order_plan_cost_workspace_visual_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js",
    "public/js/door_cutting_order/list_view/door_cutting_order_list.js",
    "public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js",
];

const compatibility = [
    "دورة الطلب",
    "إرسال للمراجعة",
    "اعتماد الطلب",
    "اعتماد التعديل",
    "تعديل الطلب",
    "نسخ الطلب",
    "إنشاء نسخة تعديل",
    "إلغاء تخصيص قشاط الدرف",
    "إلغاء تخصيص قشاط الدرفة",
    "إلغاء تخصيص القشاط",
    "طباعة جدول القياسات",
    "طباعة القياسات",
    "طباعة خطة القص",
    "طباعة فاتورة الزبون",
    "تصدير DXF لأوتوكاد",
    "تصدير DXF",
    "تصدير",
    "تنزيل DXF المرفوع",
    "تصدير DXF للرسم",
    "تصدير DXF للتعديل",
    "تنزيل DXF للإنتاج",
    "رفع ملف DXF",
    "استبدال ملف DXF",
    "اعتماد الرسم",
    "إعادة اعتماد الرسم",
    "الرسم / DXF",
    "طباعة",
    "إرسال للإنتاج",
    "إلغاء الطلب",
    "استئناف الطلب",
    "إعادة حساب خطة القص",
    "إعادة للمسودة",
    "إرجاع لمرحلة سابقة",
    "عرض",
    "صالة الإنتاج",
    "الملاحظات",
    "بحث",
    "صلاحية",
    "رقم الطلب",
    "قيد العمل",
    "تم التسليم",
    "جاهز للتسليم",
    "تسليم",
];

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
const messageIds = new Set();

for (const relative of files) {
    const source = fs.readFileSync(path.join(root, relative), "utf8");
    let visible = source;
    const phrases = compatibility.slice().sort((left, right) => right.length - left.length);
    for (const phrase of phrases) visible = visible.split(phrase).join("");
    assert.doesNotMatch(visible, /[\u0600-\u06FF]/, relative);
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*__\(/m, relative);
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*translate\(/m, relative);
    assert.doesNotMatch(source, /direction:\s*rtl|text-align:\s*(?:right|left)\b|placeholder\*=['"]ابحث/, relative);
    assert.doesNotMatch(source, /translate\(\s*["'`][^"'`]*[\u0600-\u06FF]/, relative);
    for (const match of source.matchAll(/translate\(\s*"((?:\\.|[^"\\])*)"/g)) {
        messageIds.add(match[1]);
    }
}

const catalogRows = new Set();
for (const line of catalog.split(/\r?\n/)) {
    if (!line) continue;
    if (line.startsWith('"')) {
        const end = line.indexOf('",');
        if (end > 0) catalogRows.add(line.slice(1, end).replace(/""/g, '"'));
        continue;
    }
    const comma = line.indexOf(",");
    if (comma > 0) catalogRows.add(line.slice(0, comma));
}
for (const messageId of messageIds) {
    assert.ok(catalogRows.has(messageId), messageId);
}

let direction = "rtl";
let armed = false;
const french = {
    "Return to draft": "Retour au brouillon",
    "Cancel the order": "Annuler la commande",
    "Resume the order": "Reprendre la commande",
    "Edit order": "Modifier la commande",
    "Save": "Enregistrer",
    "Order lifecycle": "Cycle de commande",
    "Order copies": "Copies de commande",
    "Show the side panel": "Afficher le panneau lateral",
    "Hide the side panel": "Masquer le panneau lateral",
    "Customer name or order number": "Nom du client ou numero de commande",
    "Search by customer name or order number": "Rechercher par nom ou numero",
    "Current worker": "Ouvrier actuel",
    "All statuses": "Tous les statuts",
    "All workers": "Tous les ouvriers",
    "Default sort": "Tri par defaut",
    "Customer name": "Nom du client",
    "Order ID": "ID commande",
    "Open the order": "Ouvrir la commande",
    "Order details": "Details de la commande",
    "Board color": "Couleur du panneau",
    "Edge color": "Couleur du chant",
    "Edge type": "Type de chant",
    "Ready for delivery": "Pret pour livraison",
    "Delivered": "Livre",
    "Draft": "Brouillon",
    "Unspecified": "Non precise",
    "Unsaved local draft": "Brouillon local non enregistre",
    "Restore an incomplete cutting order": "Restaurer une commande incomplete",
    "Continue the order": "Continuer la commande",
    "Delete the draft": "Supprimer le brouillon",
    "Start a new order": "Demarrer une nouvelle commande",
    "Could not restore the draft": "Impossible de restaurer le brouillon",
    "Waiting for update": "En attente de mise a jour",
    "Edit mode": "Mode edition",
    "Read mode": "Mode lecture",
    "Order information": "Informations commande",
    "Cutting plan": "Plan de coupe",
    "Order cost": "Cout de la commande",
};

function translate(message, replacements) {
    if (!armed) throw new Error(`translation during load: ${message}`);
    let text = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function loadLifecycle() {
    const removed = [];
    const added = [];
    const context = {
        window: {
            AlmdinaLocale: {
                translate,
                direction: () => direction,
            },
            AlmdinaPermissions: {
                canDocument: () => true,
                can: () => true,
            },
            AlmdinaDocumentContext: {
                capture: () => ({ name: "DCO-1" }),
                isCurrent: () => true,
                registerSurface() {},
            },
            frappe: {
                provide() {},
                call() {
                    return Promise.resolve({ message: {} });
                },
                confirm(message, yes) {
                    context.lastConfirm = message;
                    if (typeof yes === "function") yes();
                },
                prompt() {},
                show_alert() {},
                msgprint() {},
                set_route() {},
                ui: { form: { on() {} } },
            },
            cur_frm: null,
            console,
            addEventListener() {},
        },
        document: {
            documentElement: { getAttribute: () => direction },
        },
        frappe: null,
        console,
    };
    context.frappe = context.window.frappe;
    context.window.frappe.almdina = {};
    const sandbox = vm.createContext(context);
    vm.runInContext(
        fs.readFileSync(path.join(root, "public/js/door_cutting_order/core/order_lifecycle.js"), "utf8"),
        sandbox,
        { filename: "order_lifecycle.js" }
    );
    const frm = {
        doc: { name: "DCO-1", status: "Approved", doctype: "Door Cutting Order" },
        is_new: () => false,
        custom_buttons: {},
        remove_custom_button(label, group) {
            removed.push({ label, group: group || "" });
        },
        add_custom_button(label, handler) {
            added.push(label);
            frm.custom_buttons[label] = handler;
            return {
                removeClass() { return this; },
                addClass() { return this; },
            };
        },
        page: { wrapper: { querySelectorAll: () => [] } },
        refresh_field() {},
        reload_doc() { return Promise.resolve(); },
        __almdina_lifecycle_context: {
            order_name: "DCO-1",
            status: "Approved",
            actions: {
                return_to_draft: { allowed: true },
                cancel: { allowed: true },
                resume_cancelled: { allowed: false },
            },
        },
    };
    context.window.cur_frm = frm;
    armed = true;
    direction = "rtl";
    sandbox.window.AlmdinaOrderLifecycleUX.installButtons(frm, frm.__almdina_lifecycle_context);
    assert.ok(added.includes("Retour au brouillon"));
    assert.ok(added.includes("Annuler la commande"));
    assert.equal(frm.doc.status, "Approved");
    assert.ok(removed.some(item => item.group === "دورة الطلب" || item.group === "Cycle de commande" || item.label));

    added.length = 0;
    direction = "ltr";
    frm.custom_buttons = {};
    frm.__almdinaLifecycleRenderedLabels = new Set();
    sandbox.window.AlmdinaOrderLifecycleUX.installButtons(frm, frm.__almdina_lifecycle_context);
    assert.ok(added.includes("Retour au brouillon"));
    assert.ok(added.includes("Annuler la commande"));
    assert.equal(sandbox.window.AlmdinaLocale.direction(), "ltr");
    return { context: sandbox, frm, removed, added };
}

armed = false;
const lifecycle = loadLifecycle();
assert.equal(lifecycle.frm.doc.status, "Approved");

const listSource = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/list_view/door_cutting_order_list.js"),
    "utf8"
);
assert.match(listSource, /data-dco-order-search/);
assert.doesNotMatch(listSource, /placeholder\*=/);
assert.match(listSource, /data-dco-order-search/);
assert.match(listSource, /department_status \|\| ""\)\.trim\(\) === "قيد العمل"/);
assert.match(listSource, /department === "تم التسليم"/);
assert.match(listSource, /METHODS\.statusFilterOptions/);
assert.match(listSource, /METHODS\.assigneeFilterOptions/);

const recoverySource = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js"),
    "utf8"
);
assert.match(recoverySource, /uiDirection\(\)/);
assert.match(recoverySource, /attr\("dir", uiDirection\(\)\)/);
assert.match(recoverySource, /summary\.customer/);
assert.doesNotMatch(recoverySource, /translate\(summary\.customer/);

const pageEdit = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"),
    "utf8"
);
assert.match(pageEdit, /direction:inherit/);
assert.doesNotMatch(pageEdit, /direction:\s*rtl/);

console.log("dco operational shell locale passed");
