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
			id: "BoardEditor",
			label: "Edited plan",
			capability: "view_system_cutting_plan",
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
		const tab = String(tabId || "");
		return isPlanEditing(frm) && tab !== "System" && tab !== "BoardEditor";
	}

	function hasBoardEditorPlan(frm) {
		const owner = window.AlmdinaPlanWorkspaceState;
		const row = owner && typeof owner.planForTab === "function"
			? owner.planForTab(frm, "BoardEditor")
			: null;
		if (row && String(row.name || "").trim()) return true;
		// Keep the Edited tab reachable while an apply-return visit waits for the
		// authorized board_editor_draft row, including the first-apply race.
		const pending = owner && typeof owner.ensureApplyReturnState === "function"
			? owner.ensureApplyReturnState(frm)
			: (owner && typeof owner.applyReturnState === "function" ? owner.applyReturnState(frm) : null);
		return Boolean(
			pending
			&& ["pending", "waiting_row", "failed", "newer"].includes(String(pending.status || ""))
		);
	}

	function visibleTabs(frm) {
		// The server normalizes legacy umbrella grants into granular tab grants.
		// The browser must never widen an explicit denial by guessing that the
		// umbrella permission means all tabs.
		return PLAN_TABS.filter((tab) => {
			if (!canCapability(frm, tab.capability)) return false;
			if (tab.id === "BoardEditor") return hasBoardEditorPlan(frm);
			return true;
		});
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
		if (tab === "BoardEditor") {
			const owner = window.AlmdinaPlanWorkspaceState;
			const row = owner && typeof owner.planForTab === "function"
				? owner.planForTab(frm, "BoardEditor")
				: null;
			return parseJsonField(row && row.snapshot_json);
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
		if (tab === "BoardEditor") {
			return getPlanForTab(frm, "BoardEditor");
		}
		return getPlanForTab(frm, tab);
	}

	function consumePreferredPlanTab(frm, allowedTabs) {
		const orderName = String((frm && frm.doc && frm.doc.name) || "").trim();
		if (!orderName || typeof window === "undefined" || !window.sessionStorage) {
			return "";
		}
		const key = `almdina.dco.planTab.${orderName}`;
		try {
			const preferred = String(window.sessionStorage.getItem(key) || "").trim();
			if (!preferred) return "";
			// Do not consume the preference before the Edited tab is authorized to
			// appear (first apply). Leaving it stored keeps the return intent.
			if (Array.isArray(allowedTabs) && !allowedTabs.includes(preferred)) {
				return "";
			}
			window.sessionStorage.removeItem(key);
			return preferred;
		} catch (error) {
			return "";
		}
	}

	function applyReturnBanner(frm) {
		const owner = window.AlmdinaPlanWorkspaceState;
		const pending = owner && typeof owner.applyReturnState === "function"
			? owner.applyReturnState(frm)
			: null;
		// Prefer the in-memory visit state after load() has hydrated it. Do not
		// create a new visit from sessionStorage during paint-only calls.
		if (!pending) return "";
		const status = String(pending.status || "");
		if (status === "waiting_row" || status === "pending") {
			return `
				<div class="dco-plan-apply-return-banner" data-status="${frappe.utils.escape_html(status)}" role="status" aria-live="polite">
					<strong class="dco-plan-apply-return-banner__title">${frappe.utils.escape_html(translate("Updating the edited plan"))}</strong>
					<span class="dco-plan-apply-return-banner__summary">${frappe.utils.escape_html(pending.message || translate("Waiting for the edited cutting plan to appear..."))}</span>
				</div>
			`;
		}
		if (status === "failed") {
			return `
				<div class="dco-plan-apply-return-banner is-error" data-status="failed" role="alert" aria-live="assertive">
					<strong class="dco-plan-apply-return-banner__title">${frappe.utils.escape_html(translate("Could not refresh the edited plan"))}</strong>
					<span class="dco-plan-apply-return-banner__summary">${frappe.utils.escape_html(pending.message || translate("The edited cutting plan could not be refreshed after apply. Retry loading the plan."))}</span>
					<button type="button" class="btn btn-sm btn-default dco-plan-apply-return-retry">${frappe.utils.escape_html(translate("Retry loading the plan"))}</button>
				</div>
			`;
		}
		if (status === "newer") {
			return `
				<div class="dco-plan-apply-return-banner is-warning" data-status="newer" role="status" aria-live="polite">
					<strong class="dco-plan-apply-return-banner__title">${frappe.utils.escape_html(translate("Newer edited plan available"))}</strong>
					<span class="dco-plan-apply-return-banner__summary">${frappe.utils.escape_html(pending.message || translate("A newer edited cutting plan is shown."))}</span>
				</div>
			`;
		}
		return "";
	}

	function bindApplyReturnRetry(frm, wrapper) {
		if (!wrapper || typeof wrapper.find !== "function") return;
		const button = wrapper.find(".dco-plan-apply-return-retry");
		if (!button || !button.length || typeof button.off !== "function") return;
		button.off("click.almdinaApplyReturn").on("click.almdinaApplyReturn", () => {
			const owner = window.AlmdinaPlanWorkspaceState;
			if (!owner || typeof owner.retryApplyReturnRead !== "function") return;
			Promise.resolve(owner.retryApplyReturnRead(frm)).catch(() => {
				// Workspace state owns error/retry presentation.
			});
		});
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

		// After applying a board-editor layout, return to the Edited plan tab
		// without changing approved_plan. Consumed once the tab is visible so
		// later opens keep the normal Approved/System preference.
		const remembered = consumePreferredPlanTab(frm, allowed);
		if (remembered && allowed.includes(remembered)) {
			frm.__almdina_active_plan_tab = remembered;
			return remembered;
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
		return Boolean(row && !isHistoricalPlanRow(frm, row)
			&& row.validation && row.validation.needs_recalculation);
	}

	function uploadedPlanMismatched(frm) {
		return planRowMismatched(frm, "Custom");
	}

	function isHistoricalPlanRow(frm, row) {
		if (!row) return false;
		if (row.display_context) return row.display_context === "historical";
		const status = String(row.status || "");
		if (["Cancelled", "Superseded"].includes(status)) return true;
		if (status === "Approved") {
			const owner = window.AlmdinaPlanWorkspaceState;
			const state = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
			return String(row.name || "") !== String(state?.data?.approved_plan || "");
		}
		return false;
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

	function historicalBanner(frm, tab) {
		const owner = window.AlmdinaPlanWorkspaceState;
		const row = owner && typeof owner.planForTab === "function" ? owner.planForTab(frm, tab) : null;
		if (!isHistoricalPlanRow(frm, row)) return "";
		const status = String(row.status || "");
		const title = status === "Cancelled" ? "Previous plan — cancelled"
			: status === "Superseded" ? "Previous plan — superseded"
				: status === "Approved" ? "Approved plan — no longer current"
					: "Previous plan";
		const freshness = row.validation && row.validation.freshness_state;
		const summary = freshness === "MISMATCH"
			? "Current order inputs differ from this saved historical plan."
			: freshness === "PERSISTED_STALE"
				? "This historical plan carries an older saved review flag whose cause is unknown."
				: freshness === "REVIEW_REQUIRED"
					? "The historical plan fingerprint could not be confirmed."
					: "This plan is kept for reference and is not approved for manufacturing.";
		return `
			<div class="dco-plan-historical-banner" role="status" aria-live="polite">
				<strong class="dco-plan-historical-banner__title">${frappe.utils.escape_html(translate(title))}</strong>
				<span class="dco-plan-historical-banner__summary">${frappe.utils.escape_html(translate(summary))}</span>
			</div>
		`;
	}

	function planStatusBanner(frm, tab) {
		const mismatched = tab === "Custom"
			? uploadedPlanMismatched(frm)
			: planRowMismatched(frm, tab);
		return historicalBanner(frm, tab) || (mismatched ? mismatchBanner(frm, tab) : "");
	}

	function planPaintIdentity(frm, tab) {
		const owner = window.AlmdinaPlanWorkspaceState;
		const row = owner && typeof owner.planForTab === "function"
			? owner.planForTab(frm, tab)
			: null;
		if (!row || !String(row.name || "").trim()) {
			return `${tab}::empty`;
		}
		const content = String(row.content_identity || "").trim();
		if (content) return `${tab}::${content}`;
		return [
			tab,
			String(row.name || ""),
			String(row.revision || ""),
			String(row.modified || ""),
			String(row.status || ""),
			String((row.validation && row.validation.freshness_state) || ""),
		].join("::");
	}

	function unappliedEditorDraftBanner(row) {
		const draft = row && row.editor_draft;
		if (!draft || !draft.present || !draft.unapplied) return "";
		return `
			<div class="dco-plan-historical-banner" role="status" aria-live="polite">
				<strong class="dco-plan-historical-banner__title">${frappe.utils.escape_html(translate("Unapplied board-editor draft"))}</strong>
				<span class="dco-plan-historical-banner__summary">${frappe.utils.escape_html(translate("The board editor has saved changes that are not applied to this cutting plan yet. The layout below is the last applied plan, not those unapplied edits."))}</span>
			</div>
		`;
	}

	function renderTabContent(frm, tab) {
		if (tab === "Custom") {
			if (!hasCustomPlan(frm)) {
				return emptyState("There is no uploaded plan");
			}
			const banner = planStatusBanner(frm, "Custom");
			return `${banner}${renderPlanHtml(frm, getPlanForTab(frm, "Custom"))}`;
		}

		if (tab === "BoardEditor") {
			const returnBanner = applyReturnBanner(frm);
			const plan = getPlanForTab(frm, "BoardEditor");
			if (!plan || !plan.sheets || !plan.sheets.length) {
				if (returnBanner) {
					return `${returnBanner}${emptyState("Waiting for the edited cutting plan to appear...")}`;
				}
				return emptyState("There is no edited board-editor plan yet.");
			}
			const owner = window.AlmdinaPlanWorkspaceState;
			const row = owner && typeof owner.planForTab === "function"
				? owner.planForTab(frm, "BoardEditor")
				: null;
			let block = returnBanner;
			if (row && row.manufacturing_blocked) {
				const reason = String(row.manufacturing_block_reason || "").trim();
				const summary = reason === "board_editor_plan_not_ready"
					? translate("This edited plan is not ready for approval or DXF export yet. Fix validation issues, then re-apply the layout.")
					: translate("This edited plan cannot be approved or exported for a specific manufacturing reason.");
				block = `${block}
					<div class="dco-plan-historical-banner" role="status" aria-live="polite">
						<strong class="dco-plan-historical-banner__title">${frappe.utils.escape_html(translate("Edited plan blocked"))}</strong>
						<span class="dco-plan-historical-banner__summary">${frappe.utils.escape_html(summary)}</span>
					</div>
				`;
			} else {
				block = `${block}${planStatusBanner(frm, "BoardEditor") || ""}`;
			}
			block = `${unappliedEditorDraftBanner(row)}${block}`;
			return `${block}${renderPlanHtml(frm, plan)}`;
		}

		if (tab === "Approved") {
			if (!hasApprovedPlan(frm)) {
				return emptyState("There is no plan approved for production.");
			}
			const plan = getPlanForTab(frm, "Approved");
			const banner = planStatusBanner(frm, "Approved");
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
			? planStatusBanner(frm, "System") : "";
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
		const paintKey = planPaintIdentity(frm, selectedTab);
		const previousPaintKey = String(frm.__almdina_plan_paint_key || "");
		const content = renderTabContent(frm, selectedTab);
		const orderName = String(frm.doc.name || "");
		const escapedOrderName = frappe.utils.escape_html(orderName);
		const escapedPaintKey = frappe.utils.escape_html(paintKey);
		// Tab switches never mutate approved_plan. Paint identity includes plan
		// name + content revision so a retained DOM cannot keep an older layout.
		frm.__almdina_plan_paint_key = paintKey;
		if (previousPaintKey && previousPaintKey !== paintKey) {
			frm.__almdina_plan_paint_generation = Number(frm.__almdina_plan_paint_generation || 0) + 1;
		}
		wrapper
			.attr("data-almdina-order", orderName)
			.attr("data-almdina-plan-paint-key", paintKey)
			.html(`
				${buildTabBar(frm, selectedTab, tabs)}
				<div class="dco-plan-context-actions-host" data-almdina-order="${escapedOrderName}"></div>
				<div class="dco-plan-tab-content" data-almdina-order="${escapedOrderName}" data-almdina-plan-paint-key="${escapedPaintKey}">${content}</div>
			`);
		renderContextActions(frm, wrapper);
		bindApplyReturnRetry(frm, wrapper);
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
