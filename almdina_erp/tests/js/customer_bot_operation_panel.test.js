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

function element(tag, attributes) {
    const node = {
        tag,
        attrs: attributes,
        hidden: Object.prototype.hasOwnProperty.call(attributes, "hidden"),
        disabled: Object.prototype.hasOwnProperty.call(attributes, "disabled"),
        children: [],
        markup: "",
        getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        replaceChildren() { this.children = []; },
        appendChild(child) { this.children.push(child); },
    };
    return node;
}

function parseMarkup(html) {
    const nodes = [];
    const pattern = /<(button|p|div|section|span|dl)\b([^>]*)>/g;
    for (const match of String(html || "").matchAll(pattern)) {
        nodes.push(element(match[1], attrs(match[2])));
    }
    return nodes;
}

function matches(node, selector) {
    const named = selector.match(/^(\w+)?\[([^\]]+)\]$/);
    if (!named) return false;
    return (!named[1] || node.tag === named[1]) && node.getAttribute(named[2]) != null;
}

function walk(nodes, visit) {
    nodes.forEach(node => {
        visit(node);
        walk(node.children || [], visit);
    });
}

function wrap(nodes) {
    const list = nodes.filter(Boolean);
    return {
        length: list.length,
        find(selector) {
            const hits = [];
            list.forEach(node => walk(node.children || [], child => {
                if (matches(child, selector)) hits.push(child);
            }));
            return wrap(hits);
        },
        html(value) {
            list.forEach(node => {
                node.children = parseMarkup(value);
                node.markup = value;
            });
            return this;
        },
        get(index) { return list[index]; },
    };
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((done, fail) => {
        resolve = done;
        reject = fail;
    });
    return { promise, resolve, reject };
}

function status(extra = {}) {
    return {
        decision: "stopped",
        state: "stopped",
        reason: "",
        generation: 1,
        session: { status: "unreachable", matches_factory: false },
        webhook_registered: false,
        secret_configured: false,
        ingest_user_configured: false,
        queue: { ok: false, checked_at: null },
        last_accepted_inbound_at: null,
        last_gateway_accept_at: null,
        last_error: "",
        settings_ready: false,
        connection_ready: false,
        transport_armed: false,
        sending_accepted: false,
        customer_receipt_proven: false,
        activation_busy: false,
        ...extra,
    };
}

function harness(permissions) {
    const handlers = [];
    const calls = [];
    const pending = [];
    const timers = [];
    let timerId = 0;
    let active = true;
    const article = element("article", { "data-bot-root": "" });
    const bodyNode = { children: [article] };
    const $body = wrap([bodyNode]);
    $body.on = (event, selector, handler) => {
        handlers.push({ event, selector, handler });
        return $body;
    };
    $body.off = namespace => {
        for (let index = handlers.length - 1; index >= 0; index -= 1) {
            if (handlers[index].event.includes(namespace)) handlers.splice(index, 1);
        }
    };
    const context = vm.createContext({
        window: {},
        document: {
            body: { tag: "body" },
            documentElement: { tag: "html" },
            activeElement: null,
            createElement(tag) { return element(tag, {}); },
        },
        Object,
        Array,
        Boolean,
        Number,
        String,
        JSON,
        Promise,
        Error,
        setTimeout(fn, ms) {
            timerId += 1;
            timers.push({ id: timerId, fn, ms, cleared: false });
            return timerId;
        },
        clearTimeout(id) {
            const timer = timers.find(item => item.id === id);
            if (timer) timer.cleared = true;
        },
    });
    context.document.activeElement = context.document.body;
    load("public/js/almdina_ui.js", context);
    load("public/js/factory_production_settings/renderer.js", context);
    load("public/js/factory_production_settings/customer_bot_panel.js", context);
    const api = {
        getCustomerBotSettings() {
            calls.push("settings");
            return Promise.resolve({ ok: true, revision: 1, draft: {}, published: {}, fields: [] });
        },
        getCustomerBotOperationStatus() {
            const task = deferred();
            pending.push(task);
            calls.push("status");
            return task.promise;
        },
        startCustomerBotOperation() {
            const task = deferred();
            pending.push(task);
            calls.push("start");
            return task.promise;
        },
        stopCustomerBotOperation() {
            const task = deferred();
            pending.push(task);
            calls.push("stop");
            return task.promise;
        },
        checkCustomerBotOperation() {
            const task = deferred();
            pending.push(task);
            calls.push("check");
            return task.promise;
        },
    };
    const cleanups = [];
    const dialogsOpened = [];
    const panel = context.window.AlmdinaFactoryProductionSettingsCustomerBot.attach({
        api,
        renderer: context.window.AlmdinaFactoryProductionSettingsRenderer.create({
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
        }),
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
        translate(message) { return String(message ?? ""); },
        $body,
        isActive: () => active,
        permissions: () => permissions,
        dialogs: {
            openCustomerBotTest(config) {
                const surface = {
                    config,
                    shown: true,
                    show() { this.shown = true; },
                    hide() { this.shown = false; },
                };
                dialogsOpened.push(surface);
                return surface;
            },
        },
    });
    function fire(selector) {
        handlers
            .filter(handler => handler.event.startsWith("click") && handler.selector === selector)
            .forEach(handler => handler.handler.call({}));
    }
    function card() {
        return article.children.find(node => node.getAttribute("data-bot-operation") != null);
    }
    function alertText() {
        const host = article.children.find(node => node.getAttribute("data-bot-alert") != null);
        return host ? (host.children || []).map(node => node.textContent || "").join("") : "";
    }
    return { article, calls, pending, panel, timers, cleanups, fire, card, alertText, dialogsOpened, setActive(value) { active = value; } };
}

(async () => {
    const textsOnly = harness({ canOperate: false, canEditTexts: true });
    await textsOnly.panel.refresh();
    assert.equal(textsOnly.calls.includes("status"), false);
    assert.equal(textsOnly.calls.includes("start"), false);
    assert.match(textsOnly.article.markup, /Operation controls are available/);
    assert.doesNotMatch(textsOnly.article.markup, /data-bot-start/);

    const operateOnly = harness({ canOperate: true, canEditTexts: false });
    const loading = operateOnly.panel.refresh();
    assert.equal(operateOnly.calls.includes("settings"), false);
    assert.equal(operateOnly.calls.filter(call => call === "status").length, 1);
    operateOnly.pending.shift().resolve(status({
        decision: "running",
        state: "activating",
        generation: 4,
    }));
    await loading;
    assert.doesNotMatch(operateOnly.article.markup, /data-bot-save|data-bot-publish|data-bot-field=/);
    assert.match(operateOnly.card().markup, /Activating/);
    assert.match(operateOnly.card().markup, /alm-badge--info/);
    assert.match(operateOnly.card().markup, /data-bot-stop/);
    assert.doesNotMatch(operateOnly.card().markup, /data-bot-start/);
    assert.equal(operateOnly.timers.some(timer => timer.ms === 4000 && !timer.cleared), true);

    const steady = status({
        decision: "running",
        state: "ready",
        generation: 5,
        session: { status: "ready", matches_factory: true },
        webhook_registered: true,
        queue: { ok: true, checked_at: "2026-10-26 10:00:00" },
        connection_ready: true,
        transport_armed: true,
        last_accepted_inbound_at: "2026-10-26 10:04:00",
        last_gateway_accept_at: "2026-10-26 10:05:00",
    });
    const poll = operateOnly.timers.find(timer => timer.ms === 4000 && !timer.cleared);
    poll.fn();
    operateOnly.pending.shift().resolve(steady);
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(operateOnly.calls.filter(call => call === "start" || call === "check").length, 0);
    assert.match(operateOnly.card().markup, />Ready</);
    assert.equal(operateOnly.timers.some(timer => timer.ms === 20000 && !timer.cleared), true);

    const beforeTest = operateOnly.calls.length;
    operateOnly.fire("[data-bot-test]");
    operateOnly.fire("[data-bot-test]");
    assert.equal(operateOnly.calls.length, beforeTest);
    assert.equal(operateOnly.dialogsOpened.length, 1);
    assert.equal(operateOnly.dialogsOpened[0].shown, true);
    assert.match(operateOnly.dialogsOpened[0].config.steps.join("\n"), /This window does not send a message and does not start the bot/);
    assert.doesNotMatch(operateOnly.dialogsOpened[0].config.steps.join("\n"), /2026-10-26 10:04/);
    assert.doesNotMatch(operateOnly.card().markup, /This window does not send a message/);
    operateOnly.fire("[data-bot-details-toggle]");
    assert.match(operateOnly.card().markup, /Gateway acceptance is not proof/);
    assert.match(operateOnly.card().markup, /2026-10-26 10:04/);
    assert.match(operateOnly.card().markup, /Ready to reply/);
    assert.match(operateOnly.card().markup, /Reply processing/);

    operateOnly.fire("[data-bot-start]");
    operateOnly.fire("[data-bot-start]");
    assert.equal(operateOnly.calls.filter(call => call === "start").length, 0);

    const stopped = harness({ canOperate: true, canEditTexts: true });
    const stoppedLoad = stopped.panel.refresh();
    stopped.pending.shift().resolve(status());
    await stoppedLoad;
    stopped.fire("[data-bot-start]");
    stopped.fire("[data-bot-start]");
    assert.equal(stopped.calls.filter(call => call === "start").length, 1);
    stopped.fire("[data-bot-stop]");
    assert.equal(stopped.calls.filter(call => call === "stop").length, 1);
    const startTask = stopped.pending.shift();
    const stopTask = stopped.pending.shift();
    stopTask.resolve(status({ decision: "stopped", state: "stopped", generation: 2 }));
    startTask.resolve(status({ decision: "running", state: "ready", generation: 2 }));
    await Promise.resolve();
    await Promise.resolve();
    assert.match(stopped.card().markup, />Stopped</);
    assert.doesNotMatch(stopped.card().markup, />Ready</);
    assert.doesNotMatch(stopped.card().markup, /Activation did not finish/);

    const stale = harness({ canOperate: true, canEditTexts: false });
    const first = stale.panel.refresh();
    const firstTask = stale.pending.shift();
    const second = stale.panel.refresh();
    const secondTask = stale.pending.shift();
    secondTask.resolve(status({ decision: "running", state: "ready", generation: 8 }));
    firstTask.resolve(status({ decision: "stopped", state: "stopped", generation: 1 }));
    await Promise.all([first, second]);
    assert.match(stale.card().markup, />Ready</);

    stale.setActive(false);
    stale.panel.deactivate();
    assert.equal(stale.timers.every(timer => timer.cleared), true);
    const late = stale.calls.filter(call => call === "status").length;
    stale.timers.forEach(timer => { if (!timer.cleared) timer.fn(); });
    assert.equal(stale.calls.filter(call => call === "status").length, late);

    const fault = harness({ canOperate: true, canEditTexts: false });
    const faultLoad = fault.panel.refresh();
    fault.pending.shift().resolve(status({
        decision: "running",
        state: "degraded",
        reason: "session_unreachable",
        session: { status: "unreachable", matches_factory: true },
        last_error: "gateway timeout",
    }));
    await faultLoad;
    assert.match(fault.card().markup, />Fault</);
    assert.match(fault.card().markup, /alm-badge--danger/);
    assert.match(fault.card().markup, /run decision and session data stay in place/);
    assert.doesNotMatch(fault.card().markup, /does not create a session or a QR code/);
    fault.fire("[data-bot-details-toggle]");
    assert.match(fault.card().markup, /gateway timeout/);
    fault.fire("[data-bot-check]");
    fault.pending.shift().resolve(status({
        decision: "running",
        state: "ready",
        session: { status: "ready", matches_factory: true },
        connection_ready: true,
        transport_armed: true,
        webhook_registered: true,
    }));
    await Promise.resolve();
    await Promise.resolve();
    assert.match(fault.card().markup, /The check is complete, and the bot is ready to reply/);
    assert.doesNotMatch(fault.card().markup, /Sending is armed/);

    const setup = harness({ canOperate: true, canEditTexts: false });
    const setupLoad = setup.panel.refresh();
    setup.pending.shift().resolve(status({
        decision: "stopped",
        state: "needs_setup",
        reason: "public_base_url_missing",
    }));
    await setupLoad;
    assert.match(setup.card().markup, /The public site address is not configured/);
    assert.match(setup.card().markup, /data-bot-technical/);
    assert.doesNotMatch(setup.card().markup, /ssh|SSH|api_secret|webhook_secret/i);
    setup.fire("[data-bot-technical]");
    assert.match(setup.card().markup, /does not ask you to run server commands/);
    setup.fire("[data-bot-start]");
    setup.pending.shift().resolve(status({
        decision: "stopped",
        state: "needs_setup",
        reason: "session_login_required",
        session: { status: "login_required", matches_factory: false },
    }));
    await Promise.resolve();
    await Promise.resolve();
    assert.match(setup.card().markup, /does not create a session or a QR code/);
    assert.doesNotMatch(setup.card().markup, /Activation did not finish/);

    const split = harness({ canOperate: true, canEditTexts: false });
    const splitLoad = split.panel.refresh();
    split.pending.shift().resolve(status({
        decision: "stopped",
        state: "needs_setup",
        reason: "webhook_failed",
        session: { status: "ready", matches_factory: true },
        webhook_registered: false,
        connection_ready: false,
    }));
    await splitLoad;
    split.fire("[data-bot-details-toggle]");
    assert.match(split.card().markup, /Connected/);
    assert.match(split.card().markup, /Not registered/);
    assert.doesNotMatch(split.card().markup, /Connection interrupted/);
    assert.match(split.card().markup, /alm-badge--warning/);

    const unknown = harness({ canOperate: true, canEditTexts: false });
    const unknownLoad = unknown.panel.refresh();
    unknown.pending.shift().resolve(status());
    await unknownLoad;
    unknown.fire("[data-bot-details-toggle]");
    assert.match(unknown.card().markup, /Not checked/);
    assert.doesNotMatch(unknown.card().markup, /Connection interrupted/);
    assert.doesNotMatch(unknown.card().markup, /Activation did not finish/);
    unknown.fire("[data-bot-check]");
    unknown.pending.shift().resolve(status());
    await Promise.resolve();
    await Promise.resolve();
    assert.match(unknown.card().markup, /Connection check finished/);
    assert.doesNotMatch(unknown.card().markup, /Sending is armed/);
    assert.doesNotMatch(unknown.card().markup, /ready to reply/i);

    const source = fs.readFileSync(path.join(root, "public/js/factory_production_settings/customer_bot_panel.js"), "utf8");
    assert.match(source, /getCustomerBotOperationStatus/);
    assert.doesNotMatch(source, /setCustomerBotEnabled/);
    console.log("customer bot operation panel ok");
})().catch(error => {
    console.error(error);
    process.exit(1);
});
