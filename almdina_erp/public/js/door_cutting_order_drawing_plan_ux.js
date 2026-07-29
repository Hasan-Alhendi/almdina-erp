(() => {
	"use strict";

	const PACKING_MODES = [
		"Auto Pro",
		"Auto",
		"Deep Search",
		"Optimal Search",
		"MaxRects Best Area",
		"MaxRects Best Short Side",
		"Shelf Horizontal",
		"Guillotine Best Area Fit",
	];

	function hasRole(role) {
		return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
	}

	function isDrawingStage(frm) {
		if (frm.doc.status === "At Drawing") return true;
		if (frm.doc.production_path !== "Drawing") return false;
		if (frm.doc.current_department === "رسم") return true;
		return frm.__almdina_stage_type === "Drawing";
	}

	function canUseDrawingOptimizer(frm) {
		return (
			!frm.is_new() &&
			isDrawingStage(frm) &&
			!frm.doc.approved_plan &&
			(hasRole("عامل رسم") || hasRole("Production Manager"))
		);
	}

	function canUseDrawingOptimizerInbox(detail, meta) {
		return Boolean(
			detail &&
				meta &&
				meta.stageType === "Drawing" &&
				detail.production_path === "Drawing" &&
				!detail.approved_plan &&
				(detail.can_recalculate_drawing_plan || detail.current_stage_type === "Drawing" || detail.status === "At Drawing") &&
				(hasRole("عامل رسم") || hasRole("Production Manager"))
		);
	}

	function ensureStageType(frm) {
		if (!frm.doc.current_production_stage) {
			frm.__almdina_stage_type = null;
			return Promise.resolve();
		}
		return frappe.db
			.get_value("Production Stage", frm.doc.current_production_stage, "stage_type")
			.then((r) => {
				frm.__almdina_stage_type = (r.message && r.message.stage_type) || null;
			});
	}

	function esc(value) {
		return frappe.utils.escape_html(String(value ?? ""));
	}

	function parsePlan(raw) {
		if (!raw) return {};
		if (typeof raw === "object") return raw;
		try {
			return JSON.parse(raw);
		} catch (error) {
			return {};
		}
	}

	function buildDrawingPanelHtml(plan, packingMode) {
		const modeOptions = PACKING_MODES.map(
			(mode) => `<option value="${esc(mode)}" ${packingMode === mode ? "selected" : ""}>${esc(mode)}</option>`
		).join("");
		return `
			<div class="dco-drawing-plan-panel" style="border:1px solid #dfe3e8;border-radius:14px;padding:12px;background:#f8fafc;margin-bottom:12px;direction:rtl;">
				<div style="font-weight:800;margin-bottom:8px;">${__("محرك خطة الرسم")}</div>
				<div style="font-size:12px;color:#555;margin-bottom:8px;">${__(
					"اختر خوارزمية لإعادة حساب خطة النظام التي أنشأها منشأ الطلب."
				)}</div>
				<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
					<select class="form-control input-sm" style="max-width:220px;" data-drawing-mode>
						${modeOptions}
					</select>
					<button type="button" class="btn btn-primary btn-sm" data-drawing-recalc>${__("إعادة الحساب")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Auto Pro">${__("أفضل توزيع متقدم")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Deep Search">${__("بحث معمق")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Optimal Search">${__("بحث أمثل")}</button>
				</div>
				${summaryCards(plan)}
			</div>
		`;
	}

	function bindDrawingPanel($root, orderName, detail, onSuccess) {
		$root.find("[data-drawing-recalc]").on("click", () =>
			recalcOrder(orderName, detail, $root.find("[data-drawing-mode]").val(), onSuccess)
		);
		$root.find("[data-drawing-mode-btn]").on("click", function onMode() {
			recalcOrder(orderName, detail, $(this).attr("data-drawing-mode-btn"), onSuccess);
		});
	}

	function recalcOrder(orderName, detail, packingMode, onSuccess) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan",
				args: {
					order_name: orderName,
					packing_mode: packingMode || (detail && detail.packing_mode) || "Auto Pro",
					cutting_machine_type: detail && detail.cutting_machine_type,
					kerf_mm: detail && detail.kerf_mm,
					trim_margin_mm: detail && detail.trim_margin_mm,
				},
				freeze: true,
				freeze_message: __("جاري حساب خطة القص..."),
			})
			.then((r) => {
				frappe.show_alert({ message: __("تم تحديث خطة النظام."), indicator: "green" });
				if (typeof onSuccess === "function") {
					return onSuccess(r.message || {}, packingMode);
				}
				return r.message;
			});
	}

	function renderInboxPanel($host, meta, detail, onSuccess) {
		if (!$host || !$host.length || !canUseDrawingOptimizerInbox(detail, meta)) {
			if ($host && $host.length) $host.empty();
			return;
		}
		let plan = {};
		try {
			plan =
				typeof detail.system_plan_json === "object"
					? detail.system_plan_json
					: JSON.parse(detail.system_plan_json || "{}");
		} catch (error) {
			plan = {};
		}
		$host.html(buildDrawingPanelHtml(plan, detail.packing_mode || "Auto Pro"));
		bindDrawingPanel($host, meta.order, detail, onSuccess);
	}

	function summaryCards(plan) {
		const sheets = (plan && plan.sheets) || [];
		const boards = sheets.length;
		const waste = Number(plan && plan.waste_area_m2 ? plan.waste_area_m2 : 0);
		const total = Number(plan && plan.total_board_area_m2 ? plan.total_board_area_m2 : 0);
		const wastePct = total > 0 ? ((waste / total) * 100).toFixed(1) : "0.0";
		return `
			<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:10px;">
				<div style="border:1px solid #dfe3e8;border-radius:10px;padding:8px;background:#fff;"><b>${__("الألواح")}</b><div style="font-size:18px;font-weight:800;">${boards}</div></div>
				<div style="border:1px solid #dfe3e8;border-radius:10px;padding:8px;background:#fff;"><b>${__("الهدر")}</b><div style="font-size:18px;font-weight:800;">${wastePct}%</div></div>
				<div style="border:1px solid #dfe3e8;border-radius:10px;padding:8px;background:#fff;"><b>${__("الخوارزمية")}</b><div style="font-size:13px;font-weight:700;">${esc(plan.method_label || plan.optimization_mode || "-")}</div></div>
			</div>
		`;
	}

	function renderPanel(frm, host) {
		const $host = host && host.length ? host : null;
		if (!$host && window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.shouldShowPlanTabs(frm)) {
			return;
		}
		if (!canUseDrawingOptimizer(frm)) {
			if ($host) $host.empty();
			return;
		}

		const plan = parsePlan(frm.doc.system_plan_json || frm.doc.cutting_plan_json);
		const html = buildDrawingPanelHtml(plan, frm.doc.packing_mode);

		if ($host) {
			$host.html(html);
		} else {
			const planHost = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
			if (!planHost) return;
			let panel = planHost.find(".dco-drawing-plan-panel");
			if (!panel.length) {
				planHost.prepend(html);
				panel = planHost.find(".dco-drawing-plan-panel");
			} else {
				panel.replaceWith($(html));
				panel = planHost.find(".dco-drawing-plan-panel");
			}
		}

		const panelRoot = $host || frm.fields_dict.cutting_plan_html.$wrapper.find(".dco-drawing-plan-panel");
		panelRoot.find("[data-drawing-recalc]").on("click", () => recalc(frm, panelRoot.find("[data-drawing-mode]").val()));
		panelRoot.find("[data-drawing-mode-btn]").on("click", function onMode() {
			recalc(frm, $(this).attr("data-drawing-mode-btn"));
		});
	}

	function refreshPlanView(frm) {
		frm.__almdina_active_plan_tab = "System";
		if (window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.renderDualTabs) {
			window.AlmdinaPlanTabsUX.renderDualTabs(frm);
			return;
		}
		if (window.AlmdinaCuttingPlanRender && typeof window.AlmdinaCuttingPlanRender.parse === "function") {
			const wrapper = frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper;
			const plan = parsePlan(frm.doc.system_plan_json || frm.doc.cutting_plan_json);
			if (wrapper && plan.sheets && plan.sheets.length) {
				wrapper.html(window.AlmdinaCuttingPlanRender.build(frm, plan));
			}
		}
		renderPanel(frm);
	}

	function recalc(frm, packingMode) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan",
				args: {
					order_name: frm.doc.name,
					packing_mode: packingMode || frm.doc.packing_mode || "Auto Pro",
					cutting_machine_type: frm.doc.cutting_machine_type,
					kerf_mm: frm.doc.kerf_mm,
					trim_margin_mm: frm.doc.trim_margin_mm,
				},
				freeze: true,
				freeze_message: __("جاري حساب خطة القص..."),
			})
			.then((r) => {
				const data = r.message || {};
				[
					"cutting_plan_json",
					"system_plan_json",
					"required_boards",
					"waste_area_m2",
					"waste_percent",
					"packing_method",
					"packing_score",
					"packing_mode",
					"engine_version",
					"mdf_cost_usd",
					"cutting_cost_usd",
					"total_cost_usd",
				].forEach((fieldname) => {
					if (Object.prototype.hasOwnProperty.call(data, fieldname)) {
						frm.doc[fieldname] = data[fieldname];
					}
				});
				frappe.show_alert({ message: __("تم تحديث خطة النظام."), indicator: "green" });
				return frm.reload_doc().then(() => {
					frm.__almdina_active_plan_tab = "System";
					refreshPlanView(frm);
				});
			});
	}

	window.AlmdinaDrawingPlanUX = {
		canUseDrawingOptimizer,
		canUseDrawingOptimizerInbox,
		renderPanel,
		renderInboxPanel,
		ensureStageType,
		refreshPlanView,
		printActivePlan(frm) {
			if (window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.printActivePlan) {
				window.AlmdinaPlanTabsUX.printActivePlan(frm);
				return;
			}
			if (window.AlmdinaCuttingPlanRender && window.AlmdinaCuttingPlanRender.print) {
				window.AlmdinaCuttingPlanRender.print(frm);
			}
		},
	};

	frappe.ui.form.on("Door Cutting Order", {
		refresh(frm) {
			ensureStageType(frm).finally(() => {
				if (
					!(window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.shouldShowPlanTabs(frm)) &&
					canUseDrawingOptimizer(frm)
				) {
					renderPanel(frm);
					return;
				}
				if (
					window.AlmdinaPlanTabsUX &&
					window.AlmdinaPlanTabsUX.shouldShowPlanTabs(frm) &&
					canUseDrawingOptimizer(frm)
				) {
					window.AlmdinaPlanTabsUX.renderDualTabs(frm);
				}
			});
		},
	});
})();
