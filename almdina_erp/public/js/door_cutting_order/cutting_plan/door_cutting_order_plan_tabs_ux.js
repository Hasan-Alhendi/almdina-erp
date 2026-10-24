(() => {
	"use strict";

	const PLAN_TABS = Object.freeze([
		Object.freeze({
			id: "System",
			label: "System plan",
			capability: "view_system_cutting_plan",
		}),
		Object.freeze({
			id: "Custom",
			label: "Uploaded plan",
			capability: "view_uploaded_cutting_plan",
		}),
		Object.freeze({
			id: "Approved",
			label: "Approved plan",
			capability: "view_approved_cutting_plan",
		}),
	]);
	const SOURCE_LOCK_TITLE = "Save or cancel the cutting plan edit before changing the plan source.";

	function translate(message, replacements) {
		const locale = window.AlmdinaLocale;
		if (locale && typeof locale.translate === "function") {
			return locale.translate(message, replacements);
		}
		if (typeof __ === "function") {
			return replacements === undefined ? __(message) : __(message, replacements);
		}
		let text = String(message == null ? "" : message);
		if (Array.isArray(replacements)) {
			replacements.forEach((value, index) => {
				text = text.split(`{${index}}`).join(String(value));
			});
		}
		return text;
	}

	function uiDirection() {
		const locale = window.AlmdinaLocale;
		if (locale && typeof locale.direction === "function") {
			const value = locale.direction();
			if (value === "ltr" || value === "rtl") return value;
		}
		const root = typeof document !== "undefined" ? document.documentElement : null;
		const dir = root && root.getAttribute("dir");
		return dir === "ltr" ? "ltr" : "rtl";
	}

	function permissions() {
		return window.AlmdinaPermissions || null;
	}

	function canCapability(frm, capability) {
		const context = permissions();
		return Boolean(
			context &&
			(
				typeof context.canDocument === "function"
					? context.canDocument(frm, capability)
					: context.can(capability)
			)
		);
	}

	function canViewCuttingPlan(frm) {
		return (
			canCapability(frm, "view_cutting_plan") ||
			PLAN_TABS.some((tab) => canCapability(frm, tab.capability))
		);
	}

	function isPlanEditing(frm) {
		const editor = window.AlmdinaPlanEditSessionUX;
		return Boolean(editor && typeof editor.isEditing === "function" && editor.isEditing(frm));
	}

	function isSourceTabLocked(frm, tabId) {
		return isPlanEditing(frm) && String(tabId || "") !== "System";
	}

	function visibleTabs(frm) {
		// The server normalizes legacy umbrella grants into granular tab grants.
		// The browser must never widen an explicit denial by guessing that the
		// umbrella permission means all tabs.
		return PLAN_TABS.filter((tab) => canCapability(frm, tab.capability));
	}

	function parseJsonField(raw) {
		if (!raw) return null;
		if (typeof raw === "object") return raw;
		try {
			return JSON.parse(raw);
		} catch (error) {
			return null;
		}
	}

	function hasCustomPlan(frm) {
		const custom = parseJsonField(frm.doc.custom_plan_json);
		return Boolean(custom && custom.sheets && custom.sheets.length);
	}

	function hasApprovedPlan(frm) {
		return Boolean(frm.doc && frm.doc.approved_plan);
	}

	function shouldShowPlanTabs(frm) {
		return Boolean(frm && visibleTabs(frm).length);
	}

	function canShowDualTabs(frm) {
		return shouldShowPlanTabs(frm);
	}

	function getCachedApprovedPlan(frm) {
		if (frm.__almdina_approved_plan_order !== frm.doc.name) return null;
		const cached = frm.__almdina_approved_plan_snapshot;
		if (cached && typeof cached === "object") return cached;
		return null;
	}

	function getPlanForTab(frm, tab) {
		if (tab === "Custom") {
			return parseJsonField(frm.doc.custom_plan_json);
		}
		if (tab === "Approved") {
			return getCachedApprovedPlan(frm);
		}
		return (
			parseJsonField(frm.doc.system_plan_json) ||
			parseJsonField(frm.doc.cutting_plan_json) ||
			(window.AlmdinaCuttingPlanRender && window.AlmdinaCuttingPlanRender.parse(frm))
		);
	}

	function displayedPlanForTab(frm, tab) {
		if (tab === "System") {
			const preview = window.AlmdinaPlanPreviewSession;
			const row = preview && preview.displayedPreviewRow && preview.displayedPreviewRow(frm);
			if (row) return parseJsonField(row.snapshot_json);
		}
		return getPlanForTab(frm, tab);
	}

	function defaultTab(frm) {
		const allowed = visibleTabs(frm).map((tab) => tab.id);
		if (!allowed.length) return "System";

		// Optimizer editing/preview owns System settings only. Keep the operator
		// on that source for the whole edit session, even if a later workspace
		// refresh rebuilds the tab bar while Custom/Approved was preferred.
		if (isPlanEditing(frm) && allowed.includes("System")) {
			return "System";
		}

		const preferred = frm.__almdina_active_plan_tab;
		if (preferred && allowed.includes(preferred)) {
			return preferred;
		}

		if (frm.doc.approved_plan && allowed.includes("Approved")) {
			return "Approved";
		}
		// An accepted uploaded DXF is the only plan surface that owns the exact
		// imported contours. Prefer it on first entry so the operator sees the
		// geometry they just validated instead of the rectangular System estimate.
		if (hasCustomPlan(frm) && allowed.includes("Custom")) {
			return "Custom";
		}
		if (allowed.includes("System")) return "System";
		return allowed[0];
	}

	function activeTab(frm) {
		return defaultTab(frm);
	}

	function notifyPlanSelection(frm, tab) {
		window.dispatchEvent(new CustomEvent("almdina:plan-selection-changed", {
			detail: { frm, tab },
		}));
	}

	function buildTabBar(frm, activeTab, tabs) {
		const approvedSource = frm.doc.approved_plan_source || "System";
		const badge = (tab) => {
			if (tab === "Approved" && frm.doc.approved_plan) {
				return `<span style="margin-inline-end:6px;font-size:10px;background:#15803d;color:#fff;border-radius:999px;padding:2px 8px;">${frappe.utils.escape_html(translate("Approved for production"))}</span>`;
			}
			if (frm.doc.approved_plan && approvedSource === tab) {
				return `<span style="margin-inline-end:6px;font-size:10px;background:#15803d;color:#fff;border-radius:999px;padding:2px 8px;">${frappe.utils.escape_html(translate("Approval source"))}</span>`;
			}
			return "";
		};
		const buttons = tabs
			.map((tab) => {
				const locked = isSourceTabLocked(frm, tab.id);
				const selected = activeTab === tab.id;
				const lockAttrs = locked
					? ` disabled aria-disabled="true" title="${frappe.utils.escape_html(translate(SOURCE_LOCK_TITLE))}"`
					: "";
				return `
				<button type="button" role="tab" class="btn btn-sm btn-default${selected ? " is-active" : ""}" data-plan-tab="${tab.id}" aria-selected="${selected ? "true" : "false"}" tabindex="${selected ? "0" : "-1"}"${lockAttrs}>
					${badge(tab.id)}${frappe.utils.escape_html(translate(tab.label))}
				</button>`;
			})
			.join("");
		return `
			<div class="almdina-ui dco-plan-tabs dco-plan-tabs--underline" role="tablist" dir="${frappe.utils.escape_html(uiDirection())}" aria-label="${frappe.utils.escape_html(translate("Cutting plan source"))}" style="display:flex;gap:8px;flex-wrap:wrap;width:100%;box-sizing:border-box;margin:0 0 10px 0;">
				${buttons}
			</div>
		`;
	}

	function renderPlanHtml(frm, plan) {
		const renderer = window.AlmdinaCuttingPlanRender;
		if (!plan || !plan.sheets || !plan.sheets.length) {
			return "";
		}
		if (renderer && renderer.build) {
			return renderer.build(frm, plan);
		}
		return `<div style="padding:12px;color:#666;">${frappe.utils.escape_html(translate("Could not display the plan."))}</div>`;
	}

	function emptyState(message) {
		return `<div style="padding:16px;color:#666;text-align:center;border:1px dashed #ccd3da;border-radius:12px;background:#fafafa;">${frappe.utils.escape_html(translate(message))}</div>`;
	}

	function planRowMismatched(frm, tab) {
		const owner = window.AlmdinaPlanWorkspaceState;
		if (!owner || typeof owner.planForTab !== "function") return false;
		const row = owner.planForTab(frm, tab);
		return Boolean(row && row.validation && row.validation.needs_recalculation);
	}

	function uploadedPlanMismatched(frm) {
		return planRowMismatched(frm, "Custom");
	}

	function mismatchBanner(frm, tab) {
        const owner = window.AlmdinaPlanWorkspaceState;
        const row = owner && typeof owner.planForTab === "function" ? owner.planForTab(frm, tab) : null;
        const state = row && row.validation && row.validation.freshness_state;
        const review = state === "REVIEW_REQUIRED" || state === "PERSISTED_STALE";
        const title = review ? "Plan matching requires review" : "The plan does not match the order";
        const summary = state === "PERSISTED_STALE"
            ? "The plan is marked as out of date. Review it before starting new manufacturing."
            : review
                ? "Plan compatibility could not be confirmed after the system update. Review the plan before starting new manufacturing."
                : "This order was changed and the plan no longer matches";
		return `
			<div class="dco-uploaded-plan-mismatch-banner" role="alert" aria-live="assertive">
				<span class="dco-uploaded-plan-mismatch-banner__icon" aria-hidden="true">⚠</span>
				<div class="dco-uploaded-plan-mismatch-banner__body">
					<strong class="dco-uploaded-plan-mismatch-banner__title">${frappe.utils.escape_html(translate(title))}</strong>
					<span class="dco-uploaded-plan-mismatch-banner__summary">${frappe.utils.escape_html(translate(summary))}</span>
				</div>
			</div>
		`;
	}

	function renderTabContent(frm, tab) {
		if (tab === "Custom") {
			if (!hasCustomPlan(frm)) {
				return emptyState("There is no uploaded plan");
			}
			const banner = uploadedPlanMismatched(frm) ? mismatchBanner(frm, "Custom") : "";
			return `${banner}${renderPlanHtml(frm, getPlanForTab(frm, "Custom"))}`;
		}

		if (tab === "Approved") {
			if (!hasApprovedPlan(frm)) {
				return emptyState("There is no plan approved for production.");
			}
			const plan = getPlanForTab(frm, "Approved");
            const banner = planRowMismatched(frm, "Approved") ? mismatchBanner(frm, "Approved") : "";
            return banner + (
                renderPlanHtml(frm, plan) ||
                emptyState("There is no data to display in the approved plan.")
            );
		}

		const displayed = window.AlmdinaPlanTabsUX.displayedPlanForTab(frm, "System");
		const planHtml = renderPlanHtml(frm, displayed);
		if (!planHtml) {
			return emptyState("There is no system plan to display.");
		}
		const preview = window.AlmdinaPlanPreviewSession;
		const banner = !(preview && preview.displayedPreviewRow && preview.displayedPreviewRow(frm))
			&& planRowMismatched(frm, "System") ? mismatchBanner(frm, "System") : "";
		return `${banner}${planHtml}`;
	}

	function ensureApprovedPlanLoaded(frm) {
		// A5.2 makes this module a pure visual owner. The workspace adapter owns
		// loading/authorization and replaces this compatibility method at runtime.
		return Promise.resolve(getCachedApprovedPlan(frm));
	}

	function renderContextActions(frm, wrapper) {
		const owner = window.AlmdinaPlanContextActionsUX;
		if (!owner || typeof owner.render !== "function") return false;
		return owner.render(frm, wrapper.find(".dco-plan-context-actions-host").first());
	}

	function lockSourceTabs(frm, wrapper) {
		const host = wrapper
			|| (frm && frm.fields_dict && frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper);
		if (!host || typeof host.find !== "function") return;
		const nodes = host.find("[data-plan-tab]");
		if (!nodes || typeof nodes.each !== "function") return;
		nodes.each((_, element) => {
			const tab = $(element);
			const locked = isSourceTabLocked(frm, tab.attr("data-plan-tab"));
			tab.prop("disabled", locked);
			if (locked) {
				tab.attr("aria-disabled", "true");
				tab.attr("title", translate(SOURCE_LOCK_TITLE));
				return;
			}
			if (typeof tab.removeAttr === "function") {
				tab.removeAttr("aria-disabled");
				tab.removeAttr("title");
			}
		});
	}

	function renderDualTabs(frm) {
		const wrapper = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
		const tabs = visibleTabs(frm);
		if (!wrapper || !tabs.length) return false;

		const selectedTab = activeTab(frm);
		frm.__almdina_active_plan_tab = selectedTab;
		const content = renderTabContent(frm, selectedTab);
		const orderName = String(frm.doc.name || "");
		const escapedOrderName = frappe.utils.escape_html(orderName);
		wrapper
			.attr("data-almdina-order", orderName)
			.html(`
				${buildTabBar(frm, selectedTab, tabs)}
				<div class="dco-plan-context-actions-host" data-almdina-order="${escapedOrderName}"></div>
				<div class="dco-plan-tab-content" data-almdina-order="${escapedOrderName}">${content}</div>
			`);
		renderContextActions(frm, wrapper);
		wrapper.find("[data-plan-tab]").on("click", function onTabClick() {
			const nextTab = $(this).attr("data-plan-tab");
			if (this && this.disabled) return;
			if (isSourceTabLocked(frm, nextTab)) return;
			if (nextTab === frm.__almdina_active_plan_tab) return;
			frm.__almdina_active_plan_tab = nextTab;
			renderDualTabs(frm);
			notifyPlanSelection(frm, nextTab);
		});
		lockSourceTabs(frm, wrapper);
		return true;
	}

	function printActivePlan(frm) {
		const tab = activeTab(frm);
		const plan = window.AlmdinaPlanTabsUX.displayedPlanForTab(frm, tab);
		const renderer = window.AlmdinaCuttingPlanRender;
		if (!plan || !plan.sheets || !plan.sheets.length) {
			const emptyMessages = {
				Custom: translate("There is no uploaded plan to print."),
				Approved: translate("There is no approved plan to print."),
			};
			frappe.msgprint(emptyMessages[tab] || translate("There is no cutting plan to print."));
			return;
		}
		if (renderer && typeof renderer.print === "function") {
			const owner = window.AlmdinaPlanWorkspaceState;
			const row = owner?.displayedPlanForTab?.(frm, tab);
			return renderer.print(frm, plan, { tab, row });
		}
		frappe.msgprint(translate("Could not prepare printing."));
	}

	window.AlmdinaPlanTabsUX = {
		PLAN_TABS,
		canShowDualTabs,
		canViewCuttingPlan,
		shouldShowPlanTabs,
		hasCustomPlan,
		hasApprovedPlan,
		visibleTabs,
		defaultTab,
		activeTab,
		isPlanEditing,
		isSourceTabLocked,
		lockSourceTabs,
		getPlanForTab,
		displayedPlanForTab,
		ensureApprovedPlanLoaded,
		renderDualTabs,
		printActivePlan,
		afterRender(frm) {
			if (shouldShowPlanTabs(frm)) {
				renderDualTabs(frm);
				return true;
			}
			return false;
		},
	};

	// No Form refresh hook lives here in A5.2. The workspace presenter adapter
	// and the cutting-plan surface bootstrap own refresh/loading so this visual
	// module cannot render stale DCO compatibility values before store readiness.
})();
