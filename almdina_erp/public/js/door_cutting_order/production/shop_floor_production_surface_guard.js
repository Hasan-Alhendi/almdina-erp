(() => {
	"use strict";

	if (window.AlmdinaShopFloorProductionSurfaceGuard) return;

	const SURFACE_NAME = "production-actions";
	const STATE_FIELD = "__almdinaProductionSurfaceGuardState";
	const MAX_RECOVERY_ATTEMPTS = 3;

	function documentContext() {
		return window.AlmdinaDocumentContext || null;
	}

	function productionUX() {
		return window.AlmdinaShopFloorOrderUX || null;
	}

	function permissionVersion() {
		const permissions = window.AlmdinaPermissions || null;
		if (!permissions || typeof permissions.version !== "function") return 0;
		const version = Number(permissions.version());
		return Number.isFinite(version) ? version : 0;
	}

	function recoveryKey(frm) {
		if (!frm || !frm.doc) return "";
		return [
			frm.doc.name || "",
			frm.doc.current_production_stage || "",
			frm.doc.status || "",
			frm.doc.production_path || "",
			frm.__almdina_stage_context_ready ? "stage-ready" : "stage-pending",
			permissionVersion(),
		].join("::");
	}

	function guardState(frm) {
		if (!frm) return null;
		const key = recoveryKey(frm);
		const current = frm[STATE_FIELD];
		if (current && current.key === key) return current;
		const state = {
			key,
			attempts: 0,
			promise: null,
			circuitReported: false,
		};
		frm[STATE_FIELD] = state;
		return state;
	}

	function resetGuard(frm) {
		if (frm) frm[STATE_FIELD] = null;
	}

	function currentProductionPass(frm) {
		if (!frm || !frm.__almdinaProductionActionsPromise) return null;
		const context = documentContext();
		if (
			context
			&& typeof context.isCurrent === "function"
			&& frm.__almdinaProductionActionsContext
			&& !context.isCurrent(frm, frm.__almdinaProductionActionsContext)
		) {
			return null;
		}
		return frm.__almdinaProductionActionsPromise;
	}

	function isReady(frm) {
		const ux = productionUX();
		const ready = Boolean(
			ux
			&& typeof ux.productionActionsReady === "function"
			&& ux.productionActionsReady(frm)
		);
		if (ready) resetGuard(frm);
		return ready;
	}

	function recover(frm) {
		if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") {
			return Promise.resolve(false);
		}

		// Never start another reconciliation while the current production-action
		// pass is waiting for stage context. All recovery callers share the same
		// in-flight work instead of multiplying stage-context requests.
		const activePass = currentProductionPass(frm);
		if (activePass) return activePass;

		const ux = productionUX();
		if (!ux || typeof ux.recoverProductionActions !== "function") {
			return Promise.resolve(false);
		}

		const state = guardState(frm);
		if (state.promise) return state.promise;
		if (state.attempts >= MAX_RECOVERY_ATTEMPTS) {
			if (!state.circuitReported) {
				state.circuitReported = true;
				console.warn(
					"Almdina production surface recovery circuit opened",
					{ key: state.key, attempts: state.attempts }
				);
			}
			return Promise.resolve(false);
		}

		state.attempts += 1;
		let recovery;
		try {
			recovery = ux.recoverProductionActions(frm);
		} catch (error) {
			console.error("Failed to recover production actions", error);
			return Promise.resolve(false);
		}

		const promise = Promise.resolve(recovery)
			.catch((error) => {
				console.error("Failed to recover production actions", error);
				return false;
			})
			.finally(() => {
				if (frm[STATE_FIELD] === state && state.promise === promise) {
					state.promise = null;
				}
			});
		state.promise = promise;
		return promise;
	}

	function install() {
		const context = documentContext();
		const ux = productionUX();
		if (
			!context
			|| typeof context.registerSurface !== "function"
			|| !ux
			|| typeof ux.productionActionsReady !== "function"
			|| typeof ux.recoverProductionActions !== "function"
		) {
			return false;
		}

		// registerSurface is keyed. Re-registering the same production surface
		// replaces the legacy eager recovery probe with this bounded lifecycle
		// owner without changing business permissions or server authorization.
		return context.registerSurface(SURFACE_NAME, {
			isReady,
			recover,
		});
	}

	window.AlmdinaShopFloorProductionSurfaceGuard = Object.freeze({
		SURFACE_NAME,
		MAX_RECOVERY_ATTEMPTS,
		recoveryKey,
		isReady,
		recover,
		install,
	});

	install();
})();
