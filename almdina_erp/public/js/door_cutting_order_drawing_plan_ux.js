(() => {
	"use strict";

	if (window.AlmdinaDrawingPlanUX) return;

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

	function can(capability, frm = null) {
		const permissions = window.AlmdinaPermissions;
		return Boolean(
			permissions &&
			(
				frm && typeof permissions.canDocument === "function"
					? permissions.canDocument(frm, capability)
					: permissions.can(capability)
			)
		);
	}

	function isAssignedToCurrentUser(value) {
		return Boolean(value && frappe.session.user && value === frappe.session.user);
	}

	function isDrawingStage(frm) {
		if (frm.doc.status === "At Drawing") return true;
		return frm.__almdina_stage_type === "Drawing" || frm.doc.current_department === "رسم";
	}

	function canUseDrawingOptimizer(frm) {
		return Boolean(
			frm &&
			!frm.is_new() &&
			can("recalculate_plan", frm) &&
			isDrawingStage(frm) &&
			!frm.doc.approved_plan
		);
	}

	function canUseDrawingOptimizerInbox(detail, meta) {
		return Boolean(
			detail &&
			meta &&
			can("recalculate_plan") &&
			meta.stageType === "Drawing" &&
			isAssignedToCurrentUser(detail.current_assignee) &&
			!detail.approved_plan &&
			(detail.current_department === "رسم" || detail.status === "At Drawing")
		);
	}

	function documentContext() {
		return window.AlmdinaDocumentContext;
	}

	function ensureStageType(frm) {
		const context = documentContext();
		const identity = context.capture(frm);
		const requestedStage = frm.doc.current_production_stage;
		if (!requestedStage) {
			frm.__almdina_stage_type = null;
			return Promise.resolve(context.isCurrent(frm, identity));
		}
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_current_stage_context",
				args: { order_name: frm.doc.name },
			})
			.then((response) => {
				if (!context.isCurrent(frm, identity)) return false;
				if (frm.doc.current_production_stage !== requestedStage) return false;
				frm.__almdina_stage_type = (response.message && response.message.active_stage_type) || null;
				return true;
			})
			.catch((error) => {
				console.error("Failed to load production stage type", error);
				return false;
			});
	}

	function escape(value) {
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

	function summaryCards(plan) {
		const sheets = (plan && plan.sheets) || [];
		const waste = Number((plan && plan.waste_area_m2) || 0);
		const total = Number((plan && plan.total_board_area_m2) || 0);
		const wastePercent = total > 0 ? ((waste / total) * 100).toFixed(1) : "0.0";
		return `
			<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:12px">
				<div class="frappe-card" style="padding:10px 12px"><span style="display:block;font-size:11px;color:var(--text-muted)">${__("الألواح")}</span><b style="font-size:19px">${sheets.length}</b></div>
				<div class="frappe-card" style="padding:10px 12px"><span style="display:block;font-size:11px;color:var(--text-muted)">${__("الهدر")}</span><b style="font-size:19px">${wastePercent}%</b></div>
				<div class="frappe-card" style="padding:10px 12px"><span style="display:block;font-size:11px;color:var(--text-muted)">${__("الخوارزمية")}</span><b style="font-size:13px">${escape(plan.method_label || plan.optimization_mode || "-")}</b></div>
			</div>`;
	}

	function buildDrawingPanelHtml(plan, packingMode) {
		const options = PACKING_MODES.map(
			(mode) => `<option value="${escape(mode)}" ${packingMode === mode ? "selected" : ""}>${escape(__(mode))}</option>`
		).join("");
		return `
			<div class="dco-drawing-plan-panel" style="direction:rtl;border:1px solid var(--border-color,#dfe3e8);border-radius:16px;padding:16px;background:linear-gradient(135deg,var(--card-bg,#fff),var(--subtle-fg,#f8fafc));margin-bottom:14px;box-shadow:0 8px 24px rgba(0,0,0,.035)">
				<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap">
					<div><h4 style="margin:0 0 5px;font-size:16px;font-weight:900">${__("محرك خطة الرسم")}</h4><p style="margin:0;color:var(--text-muted,#6b7280);font-size:12px">${__("إعادة الحساب متاحة للمصمم المسند إليه الطلب فقط.")}</p></div>
					<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(36,144,239,.1);color:#1769aa;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:800">✓ ${__("صلاحية فعالة")}</span>
				</div>
				<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px">
					<select class="form-control input-sm" style="max-width:240px;min-height:36px" data-drawing-mode>${options}</select>
					<button type="button" class="btn btn-primary btn-sm" data-drawing-recalc>${__("إعادة الحساب")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Auto Pro">${__("أفضل توزيع متقدم")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Deep Search">${__("بحث معمق")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Optimal Search">${__("بحث أمثل")}</button>
				</div>
				${summaryCards(plan)}
			</div>`;
	}

	function recalculationArgs(orderName, detail, packingMode) {
		return {
			order_name: orderName,
			packing_mode: packingMode || (detail && detail.packing_mode) || "Auto Pro",
			cutting_machine_type: detail && detail.cutting_machine_type,
			kerf_mm: detail && detail.kerf_mm,
			trim_margin_mm: detail && detail.trim_margin_mm,
		};
	}

	function recalcOrder(orderName, detail, packingMode, onSuccess) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan",
				args: recalculationArgs(orderName, detail, packingMode),
				freeze: true,
				freeze_message: __("جاري حساب خطة القص..."),
			})
			.then((response) => {
				frappe.show_alert({ message: __("تم تحديث خطة النظام."), indicator: "green" });
				if (typeof onSuccess === "function") {
					return onSuccess(response.message || {}, packingMode);
				}
				return response.message;
			});
	}

	function recalcCurrentOrder(frm, packingMode) {
		const context = documentContext();
		const identity = context.capture(frm);
		const orderName = frm.doc.name;
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan",
				args: recalculationArgs(orderName, frm.doc, packingMode),
				freeze: true,
				freeze_message: __("جاري حساب خطة القص..."),
			})
			.then((r) => {
				if (!context.isCurrent(frm, identity)) return r.message;
				frappe.show_alert({ message: __("تم تحديث خطة النظام."), indicator: "green" });
				return frm.reload_doc().then(() => r.message);
			});
	}

	function bindInboxPanel(root, orderName, detail, onSuccess) {
		root.find("[data-drawing-recalc]").on("click", () =>
			recalcOrder(orderName, detail, root.find("[data-drawing-mode]").val(), onSuccess)
		);
		root.find("[data-drawing-mode-btn]").on("click", function selectMode() {
			recalcOrder(orderName, detail, $(this).attr("data-drawing-mode-btn"), onSuccess);
		});
	}

	function bindFormPanel(root, frm) {
		root.find("[data-drawing-recalc]").on("click", () =>
			recalcCurrentOrder(frm, root.find("[data-drawing-mode]").val())
		);
		root.find("[data-drawing-mode-btn]").on("click", function selectMode() {
			recalcCurrentOrder(frm, $(this).attr("data-drawing-mode-btn"));
		});
	}

	function renderInboxPanel(host, meta, detail, onSuccess) {
		if (!host || !host.length || !canUseDrawingOptimizerInbox(detail, meta)) {
			if (host && host.length) host.empty();
			return;
		}
		const plan = parsePlan(detail.system_plan_json);
		host.html(buildDrawingPanelHtml(plan, detail.packing_mode || "Auto Pro"));
		bindInboxPanel(host, meta.order, detail, onSuccess);
	}

	function renderPanel(frm, host) {
		const target = host && host.length ? host : null;
		if (!target && window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.shouldShowPlanTabs(frm)) return;
		if (!canUseDrawingOptimizer(frm)) {
			if (target) target.empty();
			return;
		}
		const plan = parsePlan(frm.doc.system_plan_json || frm.doc.cutting_plan_json);
		const html = buildDrawingPanelHtml(plan, frm.doc.packing_mode);
		const root = target || (frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper);
		if (!root) return;
		if (target) {
			target.html(html);
		} else {
			const existing = root.find(".dco-drawing-plan-panel");
			if (existing.length) existing.replaceWith($(html));
			else root.prepend(html);
		}
		bindFormPanel(root.find(".dco-drawing-plan-panel"), frm);
	}

	function refreshPlanView(frm) {
		frm.__almdina_active_plan_tab = "System";
		if (window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.renderDualTabs) {
			window.AlmdinaPlanTabsUX.renderDualTabs(frm);
			return;
		}
		renderPanel(frm);
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
			const context = documentContext();
			const identity = context.capture(frm);
			ensureStageType(frm).then((stageTypeIsCurrent) => {
				if (!stageTypeIsCurrent || !context.isCurrent(frm, identity)) return;
				if (!canUseDrawingOptimizer(frm)) return;
				if (window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.shouldShowPlanTabs(frm)) {
					window.AlmdinaPlanTabsUX.renderDualTabs(frm);
					return;
				}
				renderPanel(frm);
			});
		},
	});
})();
