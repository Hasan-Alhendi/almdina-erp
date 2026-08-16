"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

let frameSequence = 0;
const frames = new Map();

global.window = {
    setTimeout,
    clearTimeout,
    requestAnimationFrame(callback) {
        frameSequence += 1;
        frames.set(frameSequence, callback);
        return frameSequence;
    },
    cancelAnimationFrame(id) {
        frames.delete(id);
    },
};

function flushFrames() {
    const pending = [...frames.entries()];
    frames.clear();
    pending.forEach(([, callback]) => callback());
}

function sleep(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

require(path.resolve(__dirname, "../../public/js/frontend_foundation.js"));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js"
));

const lifecycle = window.AlmdinaMeasurementLifecycle;
assert.ok(lifecycle, "Measurement lifecycle API must be installed");
assert.equal(Object.isFrozen(lifecycle), true, "Measurement lifecycle API must be immutable");

async function testSameFeatureCancelsStaleFrameAndTimer() {
    const frm = { doc: { name: "DCO-LIFECYCLE-1" } };
    const calls = [];

    lifecycle.schedule(frm, "feature", () => calls.push("stale"), {
        immediate: false,
        delays: [5],
    });
    lifecycle.schedule(frm, "feature", () => calls.push("current"), {
        immediate: false,
        delays: [5],
    });

    flushFrames();
    await sleep(15);

    assert.deepEqual(
        calls,
        ["current", "current"],
        "Replacing one feature schedule must cancel its stale frame and timeout"
    );
}

async function testDocumentIdentityInvalidatesQueuedWork() {
    const frm = { doc: { name: "DCO-LIFECYCLE-A" } };
    const calls = [];

    lifecycle.schedule(frm, "document-bound", () => calls.push("ran"), {
        immediate: false,
        delays: [5],
    });
    frm.doc.name = "DCO-LIFECYCLE-B";

    flushFrames();
    await sleep(15);

    assert.deepEqual(calls, [], "Queued work must not render a different document");
}

async function testRetryStopsAfterSuccessAndCanBeCancelled() {
    const frm = { doc: { name: "DCO-LIFECYCLE-RETRY" } };
    let attempts = 0;

    lifecycle.retry(
        frm,
        "retry",
        () => {
            attempts += 1;
            return attempts >= 3;
        },
        { maxAttempts: 11, delay: 2 }
    );

    flushFrames();
    await sleep(4);
    flushFrames();
    await sleep(4);
    flushFrames();
    await sleep(4);

    assert.equal(attempts, 3, "Retry must stop immediately after the callback succeeds");

    let cancelledCalls = 0;
    lifecycle.schedule(frm, "cancelled", () => { cancelledCalls += 1; }, {
        immediate: false,
        delays: [5],
    });
    assert.equal(lifecycle.cancel(frm, "cancelled"), true);
    flushFrames();
    await sleep(15);
    assert.equal(cancelledCalls, 0, "Explicit cancellation must dispose queued work");
}

(async () => {
    await testSameFeatureCancelsStaleFrameAndTimer();
    await testDocumentIdentityInvalidatesQueuedWork();
    await testRetryStopsAfterSuccessAndCanBeCancelled();
    console.log("DCO measurement lifecycle checks passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
