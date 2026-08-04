(() => {
	"use strict";

	function permissions() {
		return window.AlmdinaPermissions || null;
	}

	function canViewCuttingPlan(frm) {
		const context = permissions();
		return Boolean(
			context &&
			(
				typeof context.canDocument === "function"
					? context.canDocument(frm, "view_cutting_plan")
					: context.can("view_cutting_plan")
			)
		);
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

	function shouldShowPlanTabs(frm) {
		return Boolean(frm && !frm.is_new() && canViewCuttingPlan(frm));
	}

	function canShowDualTabs(frm) {
		return shouldShowPlanTabs(frm);
	}

	function getPlanForTab(frm, tab) {
		if (tab === "Custom") {
			return parseJsonField(frm.doc.custom_plan_json);
		}
		return (
			parseJsonField(frm.doc.system_plan_json) ||
			parseJsonField(frm.doc.cutting_plan_json) ||
			(window.AlmdinaCuttingPlanRender && window.AlmdinaCuttingPlanRender.parse(frm))
		);
	}

	function defaultTab(frm) {
		if (frm.doc.approved_plan) {
			if (frm.doc.approved_plan_source === "Custom" && hasCustomPlan(frm)) {
				return "Custom";
			}
			return "System";
		}
		return frm.__almdina_active_plan_tab || "System";
	}

	function buildTabBar(frm, activeTab) {
		const approved = frm.doc.approved_plan_source || "System";
		const badge = (tab) =>
			frm.doc.approved_plan && approved === tab
				? '<span style="margin-right:6px;font-size:10px;background:#15803d;color:#fff;border-radius:999px;padding:2px 8px;">معتمدة للإنتاج</span>'
				: "";
		return `
			<div class="dco-plan-tabs" style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px 0;">
				<button type="button" class="btn btn-sm ${activeTab === "System" ? "btn-primary" : "btn-default"}" data-plan-tab="System">
					${badge("System")}${__("خطة النظام")}
				</button>
				<button type="button" class="btn btn-sm ${activeTab === "Custom" ? "btn-primary" : "btn-default"}" data-plan-tab="Custom">
					${badge("Custom")}${__("الخطة المرفوعة")}
				</button>
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

	function renderTabContent(frm, tab) {
		if (tab === "Custom") {
			if (!hasCustomPlan(frm)) {
				return `<div style="padding:16px;color:#666;text-align:center;border:1px dashed #ccd3da;border-radius:12px;background:#fafafa;">${__(
					"لا يوجد خطة مرفوعة"
				)}</div>`;
			}
			return renderPlanHtml(frm, getPlanForTab(frm, "Custom"));
		}

		const parts = [];
		if (
			window.AlmdinaDrawingPlanUX &&
			window.AlmdinaDrawingPlanUX.canUseDrawingOptimizer &&
			window.AlmdinaDrawingPlanUX.canUseDrawingOptimizer(frm)
		) {
			parts.push('<div class="dco-drawing-plan-panel-host"></div>');
		}
		const planHtml = renderPlanHtml(frm, getPlanForTab(frm, "System"));
		parts.push(
			planHtml ||
				`<div style="padding:16px;color:#666;text-align:center;border:1px dashed #ccd3da;border-radius:12px;background:#fafafa;">${__(
					"لا توجد خطة نظام لعرضها."
				)}</div>`
		);
		return parts.join("");
	}

	function renderDualTabs(frm) {
		const wrapper = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
		if (!wrapper || !shouldShowPlanTabs(frm)) return false;

		const activeTab = frm.__almdina_active_plan_tab || defaultTab(frm);
		frm.__almdina_active_plan_tab = activeTab;
		const content = renderTabContent(frm, activeTab);
		wrapper.html(`${buildTabBar(frm, activeTab)}<div class="dco-plan-tab-content">${content}</div>`);
		wrapper.find("[data-plan-tab]").on("click", function onTabClick() {
			frm.__almdina_active_plan_tab = $(this).attr("data-plan-tab");
			renderDualTabs(frm);
		});

		if (
			activeTab === "System" &&
			window.AlmdinaDrawingPlanUX &&
			window.AlmdinaDrawingPlanUX.renderPanel
		) {
			const host = wrapper.find(".dco-drawing-plan-panel-host");
			if (host.length) {
				window.AlmdinaDrawingPlanUX.renderPanel(frm, host);
			} else {
				window.AlmdinaDrawingPlanUX.renderPanel(frm);
			}
		}
		return true;
	}

	function printActivePlan(frm) {
		const tab = frm.__almdina_active_plan_tab || defaultTab(frm);
		const plan = getPlanForTab(frm, tab);
		const renderer = window.AlmdinaCuttingPlanRender;
		if (!plan || !plan.sheets || !plan.sheets.length) {
			frappe.msgprint(
				tab === "Custom" ? __("لا يوجد خطة مرفوعة للطباعة.") : __("لا يوجد مخطط قص للطباعة.")
			);
			return;
		}
		if (renderer && typeof renderer.print === "function") {
			renderer.print(frm, plan);
			return;
		}
		frappe.msgprint(__("تعذر تجهيز الطباعة."));
	}

	window.AlmdinaPlanTabsUX = {
		canShowDualTabs,
		canViewCuttingPlan,
		shouldShowPlanTabs,
		hasCustomPlan,
		defaultTab,
		getPlanForTab,
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

	frappe.ui.form.on("Door Cutting Order", {
		refresh(frm) {
			if (shouldShowPlanTabs(frm)) {
				setTimeout(() => renderDualTabs(frm), 0);
			}
		},
	});
})();
