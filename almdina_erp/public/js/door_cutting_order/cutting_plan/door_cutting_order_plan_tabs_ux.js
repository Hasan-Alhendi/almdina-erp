(() => {
	"use strict";

	const PLAN_TABS = Object.freeze([
		Object.freeze({
			id: "System",
			label: "خطة النظام",
			capability: "view_system_cutting_plan",
		}),
		Object.freeze({
			id: "Custom",
			label: "الخطة المرفوعة",
			capability: "view_uploaded_cutting_plan",
		}),
		Object.freeze({
			id: "Approved",
			label: "الخطة المعتمدة",
			capability: "view_approved_cutting_plan",
		}),
	]);

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

	function defaultTab(frm) {
		const allowed = visibleTabs(frm).map((tab) => tab.id);
		if (!allowed.length) return "System";

		const preferred = frm.__almdina_active_plan_tab;
		if (preferred && allowed.includes(preferred)) {
			return preferred;
		}

		if (frm.doc.approved_plan && allowed.includes("Approved")) {
			return "Approved";
		}
		if (
			frm.doc.approved_plan &&
			frm.doc.approved_plan_source === "Custom" &&
			hasCustomPlan(frm) &&
			allowed.includes("Custom")
		) {
			return "Custom";
		}
		if (allowed.includes("System")) return "System";
		return allowed[0];
	}

	function buildTabBar(frm, activeTab, tabs) {
		const approvedSource = frm.doc.approved_plan_source || "System";
		const badge = (tab) => {
			if (tab === "Approved" && frm.doc.approved_plan) {
				return '<span style="margin-right:6px;font-size:10px;background:#15803d;color:#fff;border-radius:999px;padding:2px 8px;">معتمدة للإنتاج</span>';
			}
			if (frm.doc.approved_plan && approvedSource === tab) {
				return '<span style="margin-right:6px;font-size:10px;background:#15803d;color:#fff;border-radius:999px;padding:2px 8px;">مصدر الاعتماد</span>';
			}
			return "";
		};
		const buttons = tabs
			.map(
				(tab) => `
				<button type="button" class="btn btn-sm ${activeTab === tab.id ? "btn-primary" : "btn-default"}" data-plan-tab="${tab.id}">
					${badge(tab.id)}${__(tab.label)}
				</button>`
			)
			.join("");
		return `
			<div class="dco-plan-tabs" style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 10px 0;">
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
		return `<div style="padding:12px;color:#666;">${__("تعذر عرض الخطة.")}</div>`;
	}

	function emptyState(message) {
		return `<div style="padding:16px;color:#666;text-align:center;border:1px dashed #ccd3da;border-radius:12px;background:#fafafa;">${__(
			message
		)}</div>`;
	}

	function renderTabContent(frm, tab) {
		if (tab === "Custom") {
			if (!hasCustomPlan(frm)) {
				return emptyState("لا يوجد خطة مرفوعة");
			}
			return renderPlanHtml(frm, getPlanForTab(frm, "Custom"));
		}

		if (tab === "Approved") {
			if (!hasApprovedPlan(frm)) {
				return emptyState("لا توجد خطة معتمدة للإنتاج.");
			}
			const plan = getPlanForTab(frm, "Approved");
			return (
				renderPlanHtml(frm, plan) ||
				emptyState("لا توجد بيانات لعرضها في الخطة المعتمدة.")
			);
		}

		const planHtml = renderPlanHtml(frm, getPlanForTab(frm, "System"));
		return planHtml || emptyState("لا توجد خطة نظام لعرضها.");
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

	function renderDualTabs(frm) {
		const wrapper = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
		const tabs = visibleTabs(frm);
		if (!wrapper || !tabs.length) return false;

		const activeTab = defaultTab(frm);
		frm.__almdina_active_plan_tab = activeTab;
		const content = renderTabContent(frm, activeTab);
		const orderName = String(frm.doc.name || "");
		const escapedOrderName = frappe.utils.escape_html(orderName);
		wrapper
			.attr("data-almdina-order", orderName)
			.html(`
				${buildTabBar(frm, activeTab, tabs)}
				<div class="dco-plan-context-actions-host" data-almdina-order="${escapedOrderName}"></div>
				<div class="dco-plan-tab-content" data-almdina-order="${escapedOrderName}">${content}</div>
			`);
		renderContextActions(frm, wrapper);
		wrapper.find("[data-plan-tab]").on("click", function onTabClick() {
			frm.__almdina_active_plan_tab = $(this).attr("data-plan-tab");
			renderDualTabs(frm);
		});
		return true;
	}

	function printActivePlan(frm) {
		const tab = frm.__almdina_active_plan_tab || defaultTab(frm);
		const plan = getPlanForTab(frm, tab);
		const renderer = window.AlmdinaCuttingPlanRender;
		if (!plan || !plan.sheets || !plan.sheets.length) {
			const emptyMessages = {
				Custom: __("لا يوجد خطة مرفوعة للطباعة."),
				Approved: __("لا توجد خطة معتمدة للطباعة."),
			};
			frappe.msgprint(emptyMessages[tab] || __("لا يوجد مخطط قص للطباعة."));
			return;
		}
		if (renderer && typeof renderer.print === "function") {
			renderer.print(frm, plan);
			return;
		}
		frappe.msgprint(__("تعذر تجهيز الطباعة."));
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
		getPlanForTab,
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
