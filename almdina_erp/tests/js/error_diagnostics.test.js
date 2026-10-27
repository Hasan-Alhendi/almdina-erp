"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.resolve(__dirname, "../../public/js/frontend_foundation.js"), "utf8");
const translations = [];
const runtime = { csrf_token: "csrf", dom: { freeze() {}, unfreeze() {} } };
const window = { frappe: runtime };
vm.runInNewContext(source, { window, console, URLSearchParams, __: s => { translations.push(s); return s; } });
const api = window.AlmdinaFrontend;
const server = message => JSON.stringify([JSON.stringify({ message })]);

(async () => {
    assert.equal(api.errorMessage({ responseJSON: { exc_type: "ValidationError", _server_messages: server("Enter a width.") } }, "fallback"), "Enter a width.");
    assert.equal(api.errorMessage({ _server_messages: server("Enter a width.") }, "fallback"), "Enter a width.");
    assert.equal(api.errorMessage({ exc: '["Traceback secret"]' }, "fallback"), "fallback");
    assert.equal(api.errorMessage(new Error("SQL private_table"), "fallback"), "fallback");
    assert.equal(api.errorMessage({ responseJSON: { exc_type: "RuntimeError", _server_messages: server("secret") } }, "fallback"), "fallback");
    assert.equal(api.errorMessage({ _server_messages: "malformed" }, "fallback"), "fallback");
    assert.equal(api.errorMessage({ message: { private: "secret" } }, "fallback"), "fallback");
    assert.equal(api.normalizeError({ status: 504 }, { fallback: "Timed out" }).outcome, "unknown");
    const envelope = { schema_version: 1, outcome: "rejected", title: "DXF", operation: "dxf_upload", issues: [{ code: "KERF_VIOLATION", problem: "Too close", target: "Board 3", action: "Move" }], request_reference: "ref-123" };
    const normalized = api.normalizeError({ responseJSON: { almdina_error: envelope } });
    assert.equal(normalized.issues[0].code, "KERF_VIOLATION");
    assert.equal(normalized.outcome, "rejected");
    assert.equal(api.normalizeError({ almdina_error: { ...envelope, schema_version: 99 } }).issues.length, 0);
    assert.equal(api.normalizeError({ almdina_error: { ...envelope, issues: [{ problem: "x", debug: "secret" }] } }).issues.length, 0);

    let freezes = 0, requests = 0;
    runtime.dom.freeze = () => { freezes++; };
    runtime.dom.unfreeze = () => { freezes--; };
    window.fetch = async (url, opts) => {
        requests++;
        assert.equal(url, "/api/method/example.operation");
        assert.equal(opts.headers["X-Frappe-CSRF-Token"], "csrf");
        assert.equal(opts.credentials, "same-origin");
        assert.equal(opts.body.get("payload"), '{"a":1}');
        return { ok: false, status: 417, headers: { get: () => "ref-123" }, json: async () => ({ almdina_error: envelope }) };
    };
    await assert.rejects(api.ownedRpc("example.operation", { payload: { a: 1 } }, { freeze: true }), error => error.outcome === "rejected" && error.issues[0].code === "KERF_VIOLATION");
    assert.equal(freezes, 0);
    assert.equal(requests, 1);
    window.fetch = async () => { requests++; throw new Error("network"); };
    await assert.rejects(api.ownedRpc("example.operation", {}, { freeze: true }), error => error.outcome === "unknown");
    assert.equal(freezes, 0);
    assert.equal(requests, 2, "no automatic retry of mutations");
    await assert.rejects(api.ownedRpc("https://foreign.invalid", {}));
    assert.equal(requests, 2, "transport only accepts a same-origin method name");
    console.log("Structured error diagnostics and caller-owned RPC passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
