"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
	path.resolve(__dirname, "../../public/js/door_cutting_order/production/shop_floor_production_surface_guard.js"),
	"utf8"
);

function deferred() {
	let resolve;
	let reject;
	const promise = new Promise((resolvePromise, rejectPromise) => {
		resolve = resolvePromise;
		reject = rejectPromise;
	});
	return { promise, resolve, reject };
}

(async () => {
	let probe = null;
	let recoveries = 0;
	let ready = false;
	let permissionVersion = 0;

	const fakeWindow = {
		AlmdinaPermissions: {
			version() { return permissionVersion; },
		},
		AlmdinaDocumentContext: {
			registerSurface(name, value) {
				assert.equal(name, "production-actions");
				probe = value;
				return true;
			},
			isCurrent() { return true; },
		},
		AlmdinaShopFloorOrderUX: {
			productionActionsReady() { return ready; },
			recoverProductionActions() {
				recoveries += 1;
				return Promise.resolve(true);
			},
		},
	};
	const warnings = [];
	const context = vm.createContext({
		window: fakeWindow,
		Promise,
		Number,
		Boolean,
		String,
		Object,
		console: {
			warn(...args) { warnings.push(args); },
			error(...args) { throw new Error(args.join(" ")); },
		},
	});
	vm.runInContext(source, context);

	assert.ok(probe, "the guard must replace the production-actions recovery probe");
	assert.equal(fakeWindow.AlmdinaShopFloorProductionSurfaceGuard.MAX_RECOVERY_ATTEMPTS, 3);

	const frm = {
		doctype: "Door Cutting Order",
		doc: {
			name: "DCO-STORM",
			status: "At Drawing",
			production_path: "Drawing",
			current_production_stage: "STAGE-1",
		},
		__almdina_stage_context_ready: false,
	};

	// A broken/eager surface-settle loop may call recover hundreds of times in
	// the same state. The guard must make that a bounded amount of work.
	for (let index = 0; index < 100; index += 1) {
		await probe.recover(frm);
	}
	assert.equal(recoveries, 3, "same-state recovery must be circuit-broken");
	assert.equal(warnings.length, 1, "an opened circuit should be reported once only");

	// A permission snapshot change is a real state change and gets a fresh,
	// bounded recovery budget.
	permissionVersion = 1;
	await probe.recover(frm);
	assert.equal(recoveries, 4);

	// An in-flight production action pass is shared rather than spawning another
	// recovery (and therefore another stage-context request).
	const pending = deferred();
	frm.__almdinaProductionActionsContext = { identity: "DCO-STORM" };
	frm.__almdinaProductionActionsPromise = pending.promise;
	for (let index = 0; index < 100; index += 1) {
		assert.equal(probe.recover(frm), pending.promise);
	}
	assert.equal(recoveries, 4, "in-flight production work must be single-flight");
	pending.resolve(true);
	await pending.promise;
	frm.__almdinaProductionActionsPromise = null;

	// Once the surface becomes healthy, the budget resets. A later toolbar
	// rebuild may then recover normally instead of remaining permanently open.
	ready = true;
	assert.equal(probe.isReady(frm), true);
	ready = false;
	await probe.recover(frm);
	assert.equal(recoveries, 5);

	// Stage readiness is also a new state and must reopen recovery safely.
	frm.__almdina_stage_context_ready = true;
	await probe.recover(frm);
	assert.equal(recoveries, 6);

	console.log("Shop-floor production surface request-storm guard simulation passed");
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});
