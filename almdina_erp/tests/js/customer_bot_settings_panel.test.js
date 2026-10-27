"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(relative, context) {
    vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
}

function decode(value) {
    return String(value || "")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, "\"")
        .replace(/&#039;/g, "'")
        .replace(/&amp;/g, "&");
}

function attrs(source) {
    const parsed = {};
    String(source || "").replace(/([:\w-]+)(?:="([^"]*)")?/g, (_all, name, value) => {
        if (name === "class") return "";
        parsed[name] = value == null ? "" : decode(value);
        return "";
    });
    return parsed;
}

function element(tag, attributes, className = "") {
    const node = {
        tag,
        attrs: attributes,
        value: attributes.value || "",
        textContent: "",
        hidden: Object.prototype.hasOwnProperty.call(attributes, "hidden"),
        checked: Object.prototype.hasOwnProperty.call(attributes, "checked"),
        disabled: false,
        className,
        children: [],
        tabIndex: 0,
        getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        focus() { this.focused = true; },
        setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; },
        replaceChildren() { this.children = []; },
        appendChild(child) { this.children.push(child); },
    };
    node.classList = {
        add(...names) {
            const current = new Set(node.className.split(/\s+/).filter(Boolean));
            names.forEach(name => current.add(name));
            node.className = [...current].join(" ");
        },
        remove(...names) {
            const drop = new Set(names);
            node.className = node.className.split(/\s+/).filter(name => name && !drop.has(name)).join(" ");
        },
        contains(name) {
            return node.className.split(/\s+/).includes(name);
        },
    };
    return node;
}

function classFrom(source) {
    const match = String(source || "").match(/\bclass="([^"]*)"/);
    return match ? decode(match[1]) : "";
}

function parseMarkup(html) {
    const nodes = [];
    const patterns = [
        [/<textarea\b([^>]*)>([\s\S]*?)<\/textarea>/g, "textarea", true],
        [/<input\b([^>]*)>/g, "input", false],
        [/<select\b([^>]*)>/g, "select", false],
        [/<button\b([^>]*)>/g, "button", false],
        [/<(p|div|section|span)\b([^>]*data-bot-[^>]*)>/g, null, false],
    ];
    patterns.forEach(([pattern, tag, hasValue]) => {
        for (const match of html.matchAll(pattern)) {
            const source = tag ? match[1] : match[2];
            const node = element(tag || match[1], attrs(source), classFrom(source));
            if (hasValue) node.value = decode(match[2]);
            if (node.tag === "select") {
                const selected = html.slice(match.index).match(/<option value="([^"]*)"[^>]*selected/);
                const first = html.slice(match.index).match(/<option value="([^"]*)"/);
                node.value = selected ? selected[1] : (first ? first[1] : "");
            }
            nodes.push(node);
        }
    });
    return nodes;
}

function matches(node, selector) {
    if (selector === "button, textarea, input, select") return ["button", "textarea", "input", "select"].includes(node.tag);
    if (selector.endsWith(":checked")) return matches(node, selector.slice(0, -8)) && node.checked;
    const named = selector.match(/^(\w+)?\[([^\]]+)='([^']+)'\]$/);
    if (named) {
        return (!named[1] || node.tag === named[1]) && node.getAttribute(named[2]) === named[3];
    }
    const plain = selector.match(/^\[([^\]]+)\]$/);
    return Boolean(plain && node.getAttribute(plain[1]) != null);
}

function wrap(nodes) {
    const list = nodes.filter(Boolean);
    return {
        length: list.length,
        each(fn) { list.forEach((node, index) => fn.call(node, index, node)); return this; },
        find(selector) {
            const hits = [];
            list.forEach(node => {
                (node.children || []).forEach(child => {
                    if (matches(child, selector)) hits.push(child);
                });
            });
            return wrap(hits);
        },
        filter(fn) { return wrap(list.filter((node, index) => fn.call(node, index, node))); },
        prop(name, value) {
            if (value === undefined) return list[0] ? list[0][name] : undefined;
            list.forEach(node => { node[name] = value; });
            return this;
        },
        attr(name, value) {
            if (value === undefined) return list[0] ? list[0].getAttribute(name) : undefined;
            list.forEach(node => node.setAttribute(name, value));
            return this;
        },
        val(value) {
            if (value === undefined) return list[0] ? list[0].value : undefined;
            list.forEach(node => { node.value = value; });
            return this;
        },
        text(value) {
            if (value === undefined) return list[0] ? list[0].textContent : "";
            list.forEach(node => { node.textContent = value; });
            return this;
        },
        html(value) {
            list.forEach(node => { node.children = parseMarkup(value); node.markup = value; });
            return this;
        },
        get(index) { return list[index]; },
    };
}

function deferred() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
}

function harness() {
    const handlers = [];
    const calls = [];
    const pending = [];
    const article = element("article", { "data-bot-root": "" });
    article.children = [];
    const bodyNode = { children: [article] };
    const $body = wrap([bodyNode]);
    $body.on = (event, selector, handler) => { handlers.push({ event, selector, handler }); return $body; };
    $body.off = namespace => {
        for (let index = handlers.length - 1; index >= 0; index -= 1) {
            if (handlers[index].event.includes(namespace)) handlers.splice(index, 1);
        }
    };
    const document = {
        body: { tag: "body" },
        documentElement: { tag: "html" },
        activeElement: null,
        createElement(tag) { return element(tag, {}); },
    };
    document.activeElement = document.body;
    const context = vm.createContext({
        window: {},
        document,
        Object,
        Array,
        Boolean,
        Number,
        String,
        JSON,
        Promise,
        Error,
    });
    load("public/js/almdina_ui.js", context);
    load("public/js/factory_production_settings/renderer.js", context);
    load("public/js/factory_production_settings/customer_bot_panel.js", context);
    const renderer = context.window.AlmdinaFactoryProductionSettingsRenderer.create({
        $body,
        escapeHtml(value) {
            return String(value ?? "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        },
        translate(message, replacements) {
            let value = String(message ?? "");
            (replacements || []).forEach((replacement, index) => {
                value = value.split(`{${index}}`).join(String(replacement));
            });
            return value;
        },
    });
    const api = {
        getCustomerBotSettings() {
            const task = deferred();
            pending.push(task);
            calls.push("get");
            return task.promise;
        },
        saveCustomerBotDraft(revision, texts) {
            calls.push(["save", revision, texts]);
            return Promise.resolve({ ok: true, ...snapshot(texts), revision: revision + 1 });
        },
        publishCustomerBotTexts(revision, texts) {
            calls.push(["publish", revision, texts]);
            return Promise.resolve({ ok: true, ...snapshot(texts), revision: revision + 1, published: texts });
        },
        setCustomerBotEnabled(revision, enabled) {
            calls.push(["enabled", revision, enabled]);
            return Promise.resolve({ ok: true, ...snapshot(baseDraft), revision: revision + 1, enabled });
        },
        previewCustomerBot(payload) {
            calls.push(["preview", payload]);
            return Promise.resolve({ ok: true, lines: ["reply"], state: { step: 1 } });
        },
    };
    const panel = context.window.AlmdinaFactoryProductionSettingsCustomerBot;
    const cleanups = [];
    const view = panel.attach({
        api,
        renderer,
        frontend: {
            createLatestRequestGate() {
                let generation = 0;
                return {
                    begin() { generation += 1; return { generation }; },
                    isCurrent(token) { return token && token.generation === generation; },
                };
            },
            errorMessage(error, fallback) { return (error && error.message) || fallback; },
        },
        lifecycle: { track(fn) { cleanups.push(fn); } },
        translate(message, replacements) {
            let value = String(message ?? "");
            (replacements || []).forEach((replacement, index) => {
                value = value.split(`{${index}}`).join(String(replacement));
            });
            return value;
        },
        $body,
        isActive: () => true,
    });
    function fire(eventName, selector, node, event) {
        handlers
            .filter(handler => handler.event.startsWith(eventName) && handler.selector === selector)
            .forEach(handler => handler.handler.call(node || {}, event || { preventDefault() {}, key: "" }));
    }
    function field(key) {
        return article.children.find(node => node.getAttribute("data-bot-field") === key);
    }
    function groupWrap(key) {
        return article.children.find(node => node.getAttribute("data-bot-field-wrap") === key);
    }
    return { article, calls, pending, panel, view, fire, field, groupWrap, handlers, cleanups, bot: panel, api, renderer, $body };
}

const baseDraft = {
    welcome: "أهلاً",
    order_status: "حالة الطلب",
    final_price: "السعر",
    order_measurements: "القياسات",
};
const baseFields = Object.keys(baseDraft).map(key => ({
    key,
    group: "guidance",
    max_length: 500,
    variables: key === "final_price" ? [{ name: "amount", example: "10" }] : [],
}));

function snapshot(draft, extra = {}) {
    return {
        ok: true,
        enabled: false,
        revision: 7,
        draft,
        published: { ...baseDraft },
        published_on: "2026-10-21 12:30:46.796820",
        fields: baseFields,
        ...extra,
    };
}

function assertMarked(nodes, attr, selectedId) {
    const buttons = nodes.filter(node => node.tag === "button" && node.getAttribute(attr) != null);
    const marked = buttons.filter(node => node.classList.contains("alm-btn-primary"));
    assert.equal(marked.length, 1);
    assert.equal(marked[0].getAttribute(attr), selectedId);
    buttons.forEach(node => {
        const selected = node.getAttribute(attr) === selectedId;
        assert.equal(node.classList.contains("alm-btn-primary"), selected);
        assert.equal(node.classList.contains("alm-btn-secondary"), !selected);
        const stateAttr = attr === "data-bot-tab" ? "aria-selected" : "aria-pressed";
        assert.equal(node.getAttribute(stateAttr), selected ? "true" : "false");
    });
}

function assertVisible(env, panelId, groupId) {
    env.article.children.filter(node => node.getAttribute("data-bot-panel")).forEach(node => {
        assert.equal(node.hidden, node.getAttribute("data-bot-panel") !== panelId);
    });
    if (!groupId) return;
    const shown = env.article.children.filter(node => node.getAttribute("data-bot-field-wrap") && !node.hidden);
    assert.ok(shown.length > 0);
    shown.forEach(node => assert.equal(node.getAttribute("data-bot-group"), groupId));
}

async function ready(env) {
    const loading = env.view.refresh();
    env.pending.shift().resolve(snapshot({ ...baseDraft }));
    await loading;
}

(async () => {
    const bot = harness().bot;
    const assigned = bot.groupOrder.flatMap(group => group.keys).slice().sort();
    const known = bot.fieldKeys().slice().sort();
    assert.equal(assigned.join("|"), known.join("|"));
    assert.equal(new Set(assigned).size, assigned.length);
    assert.equal(bot.groupIdFor("future_message"), "general_errors");
    assert.equal(bot.shortStamp("2026-10-21 12:30:46.796820"), "2026-10-21 12:30");
    assert.equal(bot.shortStamp(""), "");

    const css = fs.readFileSync(path.join(root, "public/css/factory_production_settings.css"), "utf8");
    assert.match(css, /\.aps-section\.aps-bot\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;/s);

    const env = harness();
    await ready(env);
    assert.equal(env.calls.filter(call => call === "get").length, 1);
    assert.doesNotMatch(env.article.markup, /data-bot-tab="operation"/);
    assert.doesNotMatch(env.article.markup, /data-bot-start/);
    assert.match(env.article.markup, /data-bot-panel="texts"/);
    assert.doesNotMatch(env.article.markup, /data-bot-panel="texts"[^>]*hidden/);
    assert.match(env.article.markup, /data-bot-panel="preview"[^>]*hidden/);
    assert.match(env.article.markup, /Last published 2026-10-21 12:30/);
    assert.doesNotMatch(env.article.markup, /12:30:46/);
    assert.equal(env.groupWrap("order_status").hidden, true);
    assert.equal(env.groupWrap("welcome").hidden, false);

    ["preview", "texts"].forEach(tabId => {
        env.fire("click", "[data-bot-tab]", element("button", { "data-bot-tab": tabId }));
        assertMarked(env.article.children, "data-bot-tab", tabId);
        assertVisible(env, tabId, tabId === "texts" ? "welcome_menu" : "");
    });
    assert.equal(env.calls.some(call => Array.isArray(call) && (call[0] === "save" || call[0] === "publish")), false);
    assert.equal(env.calls.filter(call => call === "get").length, 1);
    const textsPanel = env.article.children.find(node => node.getAttribute("data-bot-panel") === "texts");
    assert.equal(textsPanel.hidden, false);

    const welcome = env.field("welcome");
    welcome.value = "أهلاً معدلة";
    env.fire("input", "[data-bot-field]", welcome);
    ["price_invoice", "measurements", "order_statuses"].forEach(groupId => {
        env.fire("click", "[data-bot-group-button]", element("button", { "data-bot-group-button": groupId }));
        assertMarked(env.article.children, "data-bot-group-button", groupId);
        assertVisible(env, "texts", groupId);
        assert.equal(env.field("welcome").value, "أهلاً معدلة");
    });
    const price = env.field("final_price");
    price.value = "السعر الجديد";
    env.fire("input", "[data-bot-field]", price);
    const search = element("input", { "data-bot-search": "" });
    search.value = "missing-text";
    env.fire("input", "[data-bot-search]", search);
    assertMarked(env.article.children, "data-bot-group-button", "order_statuses");
    assert.equal(env.field("welcome").value, "أهلاً معدلة");
    assert.equal(env.field("final_price").value, "السعر الجديد");
    env.fire("click", "[data-bot-group-button]", element("button", { "data-bot-group-button": "welcome_menu" }));
    search.value = "";
    env.fire("input", "[data-bot-search]", search);
    assertMarked(env.article.children, "data-bot-tab", "texts");
    assertMarked(env.article.children, "data-bot-group-button", "welcome_menu");
    assertVisible(env, "texts", "welcome_menu");

    env.fire("click", "[data-bot-save]");
    await Promise.resolve();
    const save = env.calls.find(call => Array.isArray(call) && call[0] === "save");
    assert.equal(save[1], 7);
    assert.equal(save[2].welcome, "أهلاً معدلة");
    assert.equal(save[2].final_price, "السعر الجديد");
    assert.equal(save[2].order_status, "حالة الطلب");
    assert.equal(save[2].order_measurements, "القياسات");
    assertMarked(env.article.children, "data-bot-tab", "texts");
    assertMarked(env.article.children, "data-bot-group-button", "welcome_menu");
    assertVisible(env, "texts", "welcome_menu");
    assert.equal(env.field("welcome").value, "أهلاً معدلة");
    assert.equal(env.field("final_price").value, "السعر الجديد");

    const stale = env.view.refresh();
    const staleTask = env.pending.shift();
    const current = env.view.refresh();
    const currentTask = env.pending.shift();
    staleTask.resolve(snapshot({ ...baseDraft, welcome: "قديم" }, { revision: 1 }));
    currentTask.resolve(snapshot({ ...baseDraft, welcome: "من الخادم" }, { revision: 9 }));
    await Promise.all([stale, current]);
    assert.equal(env.field("welcome").value, "من الخادم");

    const editing = env.field("welcome");
    editing.value = "أثناء التحميل";
    env.fire("input", "[data-bot-field]", editing);
    const ignored = env.view.refresh();
    env.pending.shift().resolve(snapshot({ ...baseDraft, welcome: "لا تستبدل" }, { revision: 10 }));
    await ignored;
    assert.equal(env.field("welcome").value, "أثناء التحميل");

    assert.doesNotMatch(env.article.markup, /data-bot-toggle/);
    assert.doesNotMatch(env.article.markup, /The bot connection to WhatsApp is not active yet/);
    assert.equal(env.calls.some(call => Array.isArray(call) && call[0] === "enabled"), false);
    assert.equal(env.calls.some(call => call === "status" || call === "start" || call === "check"), false);
    assert.equal(env.field("welcome").value, "أثناء التحميل");

    const saveDraft = env.api.saveCustomerBotDraft;
    env.api.saveCustomerBotDraft = (revision, texts) => {
        env.calls.push(["save-conflict", revision, texts]);
        return Promise.resolve({ ok: false, code: "conflict", issues: [] });
    };
    const beforeConflict = env.field("welcome").value;
    env.fire("click", "[data-bot-save]");
    await Promise.resolve();
    assert.equal(env.field("welcome").value, beforeConflict);
    const reloaded = env.view.refresh();
    env.pending.shift().resolve(snapshot({ ...baseDraft, welcome: "بعد التعارض" }, { revision: 11 }));
    await reloaded;
    assert.equal(env.field("welcome").value, "بعد التعارض");

    const publishBefore = env.calls.filter(call => Array.isArray(call) && call[0] === "publish").length;
    env.fire("click", "[data-bot-tab]", element("button", { "data-bot-tab": "preview" }));
    env.fire("click", "[data-bot-tab]", element("button", { "data-bot-tab": "texts" }));
    assert.equal(env.calls.filter(call => Array.isArray(call) && call[0] === "publish").length, publishBefore);
    assert.equal(env.field("welcome").value, "بعد التعارض");

    env.api.saveCustomerBotDraft = saveDraft;
    const savesBeforeReopen = env.calls.filter(call => Array.isArray(call) && call[0] === "save").length;
    const handlerCount = env.handlers.length;
    env.view.dispose();
    env.cleanups.forEach(fn => fn());
    assert.equal(env.handlers.length, 0);
    const reopened = env.panel.attach({
        api: env.api,
        renderer: env.renderer,
        frontend: {
            createLatestRequestGate() {
                let generation = 0;
                return {
                    begin() { generation += 1; return { generation }; },
                    isCurrent(token) { return token && token.generation === generation; },
                };
            },
            errorMessage(error, fallback) { return (error && error.message) || fallback; },
        },
        lifecycle: { track(fn) { env.cleanups.push(fn); } },
        translate(message, replacements) {
            let value = String(message ?? "");
            (replacements || []).forEach((replacement, index) => {
                value = value.split(`{${index}}`).join(String(replacement));
            });
            return value;
        },
        $body: env.$body,
        isActive: () => true,
    });
    const loading = reopened.refresh();
    env.pending.shift().resolve(snapshot({ ...baseDraft }));
    await loading;
    env.fire("click", "[data-bot-save]");
    await Promise.resolve();
    assert.equal(env.calls.filter(call => Array.isArray(call) && call[0] === "save").length, savesBeforeReopen + 1);
    assert.equal(env.handlers.length, handlerCount);
    console.log("customer bot settings panel behavior ok");
})().catch(error => {
    console.error(error);
    process.exit(1);
});
