"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js");

function read(relativePath) {
    return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

const french = {
    "Notes:notes-panel": "Notes",
    "Close notes": "Fermer les notes",
    "Close": "Fermer",
    "Note context": "Contexte des notes",
    "Order": "Commande",
    "Customer": "Client",
    "Current important note": "Note importante actuelle",
    "No important note is currently selected.": "Aucune note importante.",
    "Clear selection:note-action": "Effacer la sélection",
    "Edited": "Modifiée",
    "Edit note": "Modifier la note",
    "Cancel": "Annuler",
    "Saving...": "Enregistrement...",
    "Save edit": "Enregistrer",
    "Mark as important": "Marquer comme importante",
    "Important note": "Note importante",
    "Edit:note-action": "Modifier",
    "Delete:note-action": "Supprimer",
    "User": "Utilisateur",
    "You do not have permission to view the customer notes linked to this order.": "Notes client indisponibles.",
    "All notes": "Toutes les notes",
    "No notes yet.": "Aucune note.",
    "Add note": "Ajouter une note",
    "Write a short and clear note...": "Écrire une note...",
    "Adding...": "Ajout...",
    "Add": "Ajouter",
    "Loading notes...": "Chargement des notes...",
    "Could not load notes.": "Chargement impossible.",
    "Check the connection and try again.": "Vérifiez la connexion.",
    "Retry": "Réessayer",
    "Delete this note? This action cannot be undone.": "Supprimer cette note ?",
    "Open important note: {0}": "Ouvrir la note importante : {0}",
    "The operation could not be completed. Try again.": "Opération impossible.",
};

const arabic = {
    "Notes:notes-panel": "الملاحظات",
    "Close notes": "إغلاق الملاحظات",
    "Order": "الطلب",
    "Customer": "العميل",
    "Current important note": "الملاحظة المهمة الحالية",
    "Edited": "تم التعديل",
    "Mark as important": "تعيين كملاحظة مهمة",
    "Important note": "ملاحظة مهمة",
    "Edit:note-action": "تعديل",
    "Delete:note-action": "حذف",
    "User": "مستخدم",
    "All notes": "كل الملاحظات",
    "Add note": "إضافة ملاحظة",
    "Add": "إضافة",
    "Open important note: {0}": "فتح الملاحظة المهمة: {0}",
};

let active = french;
const confirmed = [];

function translate(message, replacements, context) {
    const contextual = context ? `${message}:${context}` : "";
    const text = contextual && Object.prototype.hasOwnProperty.call(active, contextual)
        ? active[contextual]
        : (Object.prototype.hasOwnProperty.call(active, message) ? active[message] : message);
    if (!replacements) return text;
    return String(text).replace(/\{(\d+)\}/g, (_match, index) => String(replacements[Number(index)] ?? ""));
}

function createElement(tag) {
    const node = {
        nodeType: 1,
        tagName: String(tag || "div").toUpperCase(),
        className: "",
        _html: "",
        children: [],
        attributes: {},
        dataset: {},
        style: {},
        isConnected: false,
        parentNode: null,
        listeners: {},
        textContent: "",
        named: {},
    };
    node.classList = {
        add(...names) {
            node.className = [...new Set(`${node.className} ${names.join(" ")}`.split(/\s+/).filter(Boolean))].join(" ");
        },
        remove(...names) {
            const drop = new Set(names);
            node.className = node.className.split(/\s+/).filter(name => name && !drop.has(name)).join(" ");
        },
        contains(name) {
            return node.className.split(/\s+/).includes(name);
        },
    };
    node.setAttribute = (name, value) => {
        node.attributes[name] = String(value);
    };
    node.getAttribute = name => node.attributes[name];
    node.addEventListener = (type, handler) => {
        node.listeners[type] = node.listeners[type] || [];
        node.listeners[type].push(handler);
    };
    node.removeEventListener = () => {};
    node.appendChild = child => {
        child.parentNode = node;
        child.isConnected = true;
        node.children.push(child);
        return child;
    };
    node.insertBefore = (child, _before) => node.appendChild(child);
    node.remove = () => {
        node.isConnected = false;
    };
    node.focus = () => {};
    node.contains = () => true;
    Object.defineProperty(node, "innerHTML", {
        get() {
            return node._html;
        },
        set(value) {
            node._html = String(value);
            node.children = [];
            if (node._html.includes("almdina-notes-panel-content")) {
                const content = createElement("div");
                content.className = "almdina-notes-panel-content";
                content.isConnected = true;
                content.parentNode = node;
                node.children.push(content);
                node.named.content = content;
            }
        },
    });
    node.querySelector = selector => {
        if (selector === ".almdina-notes-panel-content" && node.named.content) return node.named.content;
        const blob = `${node._html}${(node.children || []).map(child => child._html || "").join("")}`;
        if (selector === ".almdina-notes-counter" && blob.includes("almdina-notes-counter")) return { textContent: "" };
        if (selector === '[data-notes-action="close"]' && blob.includes('data-notes-action="close"')) return { focus() {} };
        if (selector === ".dco-mobile-order-card" && node.card) return node.card;
        if (selector === ".dco-card-important-note") return node.importantNote || null;
        if (selector === ".dco-card-date-row") return node.dateRow || null;
        for (const child of node.children || []) {
            if (child.querySelector) {
                const found = child.querySelector(selector);
                if (found) return found;
            }
        }
        return null;
    };
    node.querySelectorAll = selector => (selector === ".list-row-container" ? node.rows || [] : []);
    return node;
}

const body = createElement("body");
body.isConnected = true;
const documentStub = {
    body,
    activeElement: null,
    addEventListener() {},
    dispatchEvent() {},
    createElement,
};
const fakeWindow = {
    document: documentStub,
    frappe: {
        utils: { escape_html: escapeHtml },
        call() {
            return Promise.resolve({ message: noteContext });
        },
        confirm(message) {
            confirmed.push(message);
        },
        meta: {
            get_docfield() {
                return { label: "" };
            },
        },
    },
};
fakeWindow.window = fakeWindow;

const context = vm.createContext({
    window: fakeWindow,
    document: documentStub,
    frappe: fakeWindow.frappe,
    __: translate,
    console,
    Object,
    Array,
    Promise,
    String,
    Number,
    Boolean,
    Error,
    Math,
    Set,
    JSON,
    CustomEvent: class CustomEvent {
        constructor(type, init) {
            this.type = type;
            this.detail = init && init.detail;
        }
    },
});

const noteContext = {
    order: "26-00089",
    customer: "CUST-1",
    counts: { order: 2, customer: 0 },
    permissions: {
        can_add_order_note: true,
        can_add_customer_note: false,
        can_view_customer_notes: false,
        can_manage_important_note: true,
    },
    important_note: {
        name: "NOTE-1",
        content: "تسليم <بعد> الظهر",
        author: "أحمد & علي",
        creation: "2026-10-11 09:00:00",
        is_edited: true,
    },
    order_notes: [
        {
            name: "NOTE-1",
            content: "تسليم <بعد> الظهر",
            author: "أحمد & علي",
            author_user: "ahmad@example.com",
            creation: "2026-10-11 09:00:00",
            is_edited: true,
            is_important: true,
            can_edit: true,
            can_delete: true,
        },
        {
            name: "NOTE-2",
            content: "ملاحظة عادية",
            author: "",
            author_user: "",
            creation: "2026-10-11 10:00:00",
            is_important: false,
            can_edit: false,
            can_delete: false,
        },
    ],
    customer_notes: [],
    important_note_preview: "تسليم <بعد> الظهر",
};

vm.runInContext(read("almdina_ui.js"), context, { filename: "almdina_ui.js" });
vm.runInContext(read("notes/notes_panel.js"), context, { filename: "notes_panel.js" });
vm.runInContext(read("notes/notes_dco_list_integration.js"), context, { filename: "notes_dco_list_integration.js" });

const panel = fakeWindow.AlmdinaNotesPanel;
const opened = panel.openForOrder("26-00089");
assert.equal(opened instanceof Promise, true);

opened.then(loaded => {
    assert.equal(loaded.order, "26-00089");
    const html = body.children[0].named.content.innerHTML;
    assert.match(html, />Notes</);
    assert.match(html, /Fermer les notes/);
    assert.match(html, /Commande/);
    assert.match(html, /Client/);
    assert.match(html, /Note importante actuelle/);
    assert.match(html, /Modifiée/);
    assert.match(html, /Marquer comme importante/);
    assert.match(html, /Note importante/);
    assert.match(html, />Modifier</);
    assert.match(html, />Supprimer</);
    assert.match(html, /Toutes les notes/);
    assert.match(html, /Ajouter une note/);
    assert.match(html, /Écrire une note\.\.\./);
    assert.match(html, />Ajouter</);
    assert.match(html, /Utilisateur/);
    assert.match(html, /aria-hidden="true">U</);
    assert.match(html, /تسليم &lt;بعد&gt; الظهر/);
    assert.match(html, /أحمد &amp; علي/);
    assert.match(html, /ملاحظة عادية/);
    assert.match(html, /data-notes-action="edit"/);
    assert.match(html, /data-notes-action="delete"/);
    assert.match(html, /data-notes-action="pin"/);
    assert.match(html, /data-notes-action="submit"/);
    assert.match(html, /data-notes-action="clear-important"/);
    assert.match(html, /data-notes-tab="order"/);
    assert.match(html, /data-notes-tab="customer"/);
    assert.doesNotMatch(html, /الملاحظات|إغلاق الملاحظات|سياق الملاحظات|الملاحظة المهمة الحالية|تعيين كملاحظة مهمة|ملاحظة مهمة|كل الملاحظات|إضافة ملاحظة|مستخدم|جارٍ/);

    const overlay = body.children[0];
    overlay.listeners.click[0]({
        target: {
            closest(selector) {
                if (selector !== "[data-notes-action]") return null;
                return { dataset: { notesAction: "delete", commentName: "NOTE-1" } };
            },
        },
    });
    assert.deepEqual(confirmed, ["Supprimer cette note ?"]);

    const list = fakeWindow.AlmdinaDcoNotesListIntegration;
    const desktop = list.formatter("تسليم <سريع>", {}, { name: "26-00089" });
    assert.match(desktop, /data-order-name="26-00089"/);
    assert.match(desktop, /Ouvrir la note importante : تسليم &lt;سريع&gt;/);
    assert.match(desktop, /تسليم &lt;سريع&gt;/);
    assert.doesNotMatch(desktop, /فتح الملاحظة المهمة/);

    const card = createElement("article");
    card.dataset.orderName = "26-00089";
    card.dateRow = createElement("div");
    const container = createElement("div");
    container.card = card;
    const listRoot = createElement("div");
    listRoot.className = "dco-order-card-layout";
    listRoot.rows = [container];
    const listview = {
        doctype: "Door Cutting Order",
        data: [{ name: "26-00089", important_note_preview: "تسليم <سريع>" }],
        page: { wrapper: listRoot },
        list_view_settings: { fields: JSON.stringify([{ fieldname: "order_notes" }]) },
        columns: [],
    };
    list.reconcileMobileCards(listview);
    const mobile = card.children[0];
    assert.equal(mobile.getAttribute("aria-label"), "Ouvrir la note importante : تسليم <سريع>");
    assert.match(mobile.innerHTML, /Note importante/);
    assert.match(mobile.innerHTML, /تسليم &lt;سريع&gt;/);
    assert.equal(mobile.dataset.orderName, "26-00089");
    assert.equal(list.ensureImportantFieldInListSettings(listview), true);
    const stored = JSON.parse(listview.list_view_settings.fields);
    assert.equal(stored[1].fieldname, "important_note_preview");
    assert.equal(stored[1].label, "Note importante");

    fakeWindow.frappe.meta.get_docfield = () => ({ label: "ملاحظة مهمة" });
    listview.list_view_settings.fields = JSON.stringify([{ fieldname: "order_notes" }]);
    assert.equal(list.ensureImportantFieldInListSettings(listview), true);
    assert.equal(JSON.parse(listview.list_view_settings.fields)[1].label, "ملاحظة مهمة");

    active = arabic;
    return panel.refresh();
}).then(() => {
    const html = body.children[0].named.content.innerHTML;
    assert.match(html, /الملاحظات/);
    assert.match(html, /إغلاق الملاحظات/);
    assert.match(html, /الطلب/);
    assert.match(html, /العميل/);
    assert.match(html, /الملاحظة المهمة الحالية/);
    assert.match(html, /تم التعديل/);
    assert.match(html, /ملاحظة مهمة/);
    assert.match(html, />تعديل</);
    assert.match(html, />حذف</);
    assert.match(html, /مستخدم/);
    assert.match(html, /تسليم &lt;بعد&gt; الظهر/);
    assert.match(html, /أحمد &amp; علي/);
    assert.match(html, /data-notes-action="delete"/);
    console.log("Notes locale simulation passed");
}).catch(error => {
    console.error(error);
    process.exit(1);
});
