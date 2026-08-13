(() => {
	"use strict";

	if (window.AlmdinaDrawingPlanUX) return;

	const SIMULATE_METHOD =
		"almdina_erp.almdina_erp.services.order_plan_permission_service.simulate_optimizer_plan";

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

	function holdsStageOperationalRole(frm) {
		const context = documentContext();
		if (context && typeof context.canMutateCurrentStage === "function") {
			return context.canMutateCurrentStage(frm);
		}
		if (context && typeof context.holdsStageOperationalRole === "function") {
			return context.holdsStageOperationalRole(frm);
		}
		return Boolean(frm && frm.__almdina_actor_holds_stage_role);
	}

	function canTuneCuttingAlgorithm(frm) {
		const context = documentContext();
		if (context && typeof context.canTuneCuttingAlgorithm === "function") {
			return context.canTuneCuttingAlgorithm(frm);
		}
		if (!frm || !frm.doc || frm.is_new() || frm.doc.approved_plan) return false;
		if (frm.doc.current_production_stage) return holdsStageOperationalRole(frm);
		return true;
	}

	// Writing the new plan into the order: stage-scoped and never on an approved
	// plan. Previewing it: capability only, because nothing is persisted.
	function canCommitDrawingPlan(frm) {
		return canTuneCuttingAlgorithm(frm) && can("recalculate_plan", frm);
	}

	function canPreviewDrawingOptimizer(frm = null) {
		const context = documentContext();
		const saved = context && typeof context.canPreviewCuttingAlgorithm === "function"
			? context.canPreviewCuttingAlgorithm(frm)
			: Boolean(frm && frm.doc && !frm.is_new());
		return saved && can("edit_optimizer_settings", frm);
	}

	function canUseDrawingOptimizer(frm) {
		return canCommitDrawingPlan(frm) || canPreviewDrawingOptimizer(frm);
	}

	function canEditDrawingOptimizer(frm = null) {
		// Packing algorithm only (never the rest of the document).
		return canPreviewDrawingOptimizer(frm)
			|| (canTuneCuttingAlgorithm(frm) && can("edit_optimizer_settings", frm));
	}

	function canUseDrawingOptimizerInbox(detail, meta) {
		return Boolean(
			detail &&
			meta &&
			can("recalculate_plan") &&
			detail.actor_holds_operational_role &&
			isAssignedToCurrentUser(detail.current_assignee) &&
			!detail.approved_plan
		);
	}

	function documentContext() {
		return window.AlmdinaDocumentContext;
	}

	function ensureStageType(frm) {
		const context = documentContext();
		if (!context || typeof context.ensureStageContext !== "function") {
			return Promise.resolve(Boolean(frm && frm.doc));
		}
		const token = context.capture(frm);
		return context.ensureStageContext(frm).then((ready) => (
			ready && context.isCurrent(frm, token)
		));
	}

	function scheduleDrawingPanel(frm) {
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

	function buildDrawingPanelHtml(plan, packingMode, mayEditSettings, previewOnly = false) {
		const disabled = mayEditSettings ? "" : "disabled";
		const options = PACKING_MODES.map(
			(mode) => `<option value="${escape(mode)}" ${packingMode === mode ? "selected" : ""}>${escape(__(mode))}</option>`
		).join("");
		const title = previewOnly ? __("تجربة خوارزميات القص") : __("محرك خطة الرسم");
		const intro = previewOnly
			? __("جرّب أي خوارزمية وقارن النتيجة. هذه معاينة فقط ولا تغيّر خطة الطلب المحفوظة.")
			: __("إعادة الحساب وتغيير الخوارزمية يتبعان صلاحيات خطة القص، ولا يحتاجان صلاحية التكلفة.");
		const badge = previewOnly
			? `<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(255,159,10,.12);color:#a15c00;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:800">${__("معاينة فقط")}</span>`
			: `<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(36,144,239,.1);color:#1769aa;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:800">✓ ${__("إعادة الحساب متاحة")}</span>`;
		return `
			<div class="dco-drawing-plan-panel" style="direction:rtl;border:1px solid var(--border-color,#dfe3e8);border-radius:16px;padding:16px;background:linear-gradient(135deg,var(--card-bg,#fff),var(--subtle-fg,#f8fafc));margin-bottom:14px;box-shadow:0 8px 24px rgba(0,0,0,.035)">
				<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap">
					<div><h4 style="margin:0 0 5px;font-size:16px;font-weight:900">${title}</h4><p style="margin:0;color:var(--text-muted,#6b7280);font-size:12px">${intro}</p></div>
					${badge}
				</div>
				<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px">
					<select class="form-control input-sm" style="max-width:240px;min-height:36px" data-drawing-mode ${disabled}>${options}</select>
					<button type="button" class="btn btn-primary btn-sm" data-drawing-recalc>${previewOnly ? __("عرض النتيجة") : __("إعادة الحساب")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Auto Pro" ${disabled}>${__("أفضل توزيع متقدم")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Deep Search" ${disabled}>${__("بحث معمق")}</button>
					<button type="button" class="btn btn-default btn-sm" data-drawing-mode-btn="Optimal Search" ${disabled}>${__("بحث أمثل")}</button>
				</div>
				${mayEditSettings ? "" : `<div class="text-muted" style="font-size:11px;margin-top:8px">${__("تغيير الخوارزمية يحتاج صلاحية «تعديل خوارزمية القص». يمكنك إعادة الحساب بالخوارزمية الحالية.")}</div>`}
				${summaryCards(plan)}
			</div>`;
	}

	function recalculationArgs(orderName, detail, packingMode, mayEditSettings) {
		return {
			order_name: orderName,
			packing_mode: mayEditSettings ? (packingMode || (detail && detail.packing_mode) || "Auto Pro") : (detail && detail.packing_mode),
			cutting_machine_type: detail && detail.cutting_machine_type,
			kerf_mm: detail && detail.kerf_mm,
			trim_margin_mm: detail && detail.trim_margin_mm,
			optimization_time_limit_sec: detail && detail.optimization_time_limit_sec,
		};
	}

	function recalcOrder(orderName, detail, packingMode, mayEditSettings, onSuccess) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan",
				args: recalculationArgs(orderName, detail, packingMode, mayEditSettings),
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

	function previewCurrentOrder(frm, packingMode) {
		const context = documentContext();
		const identity = context.capture(frm);
		const mode = packingMode || frm.doc.packing_mode || "Auto Pro";
		return frappe
			.call({
				method: SIMULATE_METHOD,
				args: recalculationArgs(frm.doc.name, frm.doc, mode, true),
				freeze: true,
				freeze_message: __("جاري تجربة الخوارزمية..."),
			})
			.then((r) => {
				if (!context.isCurrent(frm, identity)) return r.message;
				frm.__almdina_algorithm_preview = Object.assign({}, r.message || {}, {
					packing_mode: mode,
				});
				frappe.show_alert({
					message: __("هذه نتيجة معاينة. لم يطرأ أي تغيير على الطلب."),
					indicator: "orange",
				});
				renderPanel(frm);
				return r.message;
			});
	}

	function recalcCurrentOrder(frm, packingMode) {
		if (!canCommitDrawingPlan(frm)) return previewCurrentOrder(frm, packingMode);
		const context = documentContext();
		const identity = context.capture(frm);
		const orderName = frm.doc.name;
		const mayEditSettings = canEditDrawingOptimizer(frm);
		const revisionUx = window.AlmdinaOrderRevisionUX;
		const wasEditing = Boolean(
			revisionUx && typeof revisionUx.captureEditSessionPresence === "function"
				? revisionUx.captureEditSessionPresence(frm)
				: frm.__almdina_edit_session
		);
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan",
				args: recalculationArgs(orderName, frm.doc, packingMode, mayEditSettings),
				freeze: true,
				freeze_message: __("جاري حساب خطة القص..."),
			})
			.then((r) => {
				if (!context.isCurrent(frm, identity)) return r.message;
				frappe.show_alert({ message: __("تم تحديث خطة النظام."), indicator: "green" });
				return frm.reload_doc().then(() => {
					if (revisionUx && typeof revisionUx.restorePrimaryAfterPlanEngine === "function") {
						revisionUx.restorePrimaryAfterPlanEngine(frm, wasEditing);
					}
					return r.message;
				});
			});
	}

	function bindInboxPanel(root, orderName, detail, mayEditSettings, onSuccess) {
		root.find("[data-drawing-recalc]").on("click", () =>
			recalcOrder(orderName, detail, root.find("[data-drawing-mode]").val(), mayEditSettings, onSuccess)
		);
		root.find("[data-drawing-mode-btn]").on("click", function selectMode() {
			if (!mayEditSettings) return;
			recalcOrder(orderName, detail, $(this).attr("data-drawing-mode-btn"), true, onSuccess);
		});
	}

	function bindFormPanel(root, frm, mayEditSettings) {
		root.find("[data-drawing-recalc]").on("click", () =>
			recalcCurrentOrder(frm, root.find("[data-drawing-mode]").val())
		);
		root.find("[data-drawing-mode-btn]").on("click", function selectMode() {
			if (!mayEditSettings) return;
			recalcCurrentOrder(frm, $(this).attr("data-drawing-mode-btn"));
		});
	}

	function renderInboxPanel(host, meta, detail, onSuccess) {
		if (!host || !host.length || !canUseDrawingOptimizerInbox(detail, meta)) {
			if (host && host.length) host.empty();
			return;
		}
		const mayEditSettings = canEditDrawingOptimizer();
		const plan = parsePlan(detail.system_plan_json);
		host.html(buildDrawingPanelHtml(plan, detail.packing_mode || "Auto Pro", mayEditSettings));
		bindInboxPanel(host, meta.order, detail, mayEditSettings, onSuccess);
	}

	function renderPanel(frm, host) {
		const target = host && host.length ? host : null;
		if (!target && window.AlmdinaPlanTabsUX && window.AlmdinaPlanTabsUX.shouldShowPlanTabs(frm)) return;
		if (!canUseDrawingOptimizer(frm)) {
			if (target) target.empty();
			return;
		}
		const mayEditSettings = canEditDrawingOptimizer(frm);
		const previewOnly = !canCommitDrawingPlan(frm);
		const preview = previewOnly ? frm.__almdina_algorithm_preview : null;
		const plan = parsePlan(
			(preview && (preview.system_plan_json || preview.cutting_plan_json))
			|| frm.doc.system_plan_json
			|| frm.doc.cutting_plan_json
		);
		const html = buildDrawingPanelHtml(
			plan,
			(preview && preview.packing_mode) || frm.doc.packing_mode,
			mayEditSettings,
			previewOnly
		);
		const root = target || (frm.fields_dict.cutting_plan_html && frm.fields_dict.cutting_plan_html.$wrapper);
		if (!root) return;
		if (target) {
			target.html(html);
		} else {
			const existing = root.find(".dco-drawing-plan-panel");
			if (existing.length) existing.replaceWith($(html));
			else root.prepend(html);
		}
		bindFormPanel(root.find(".dco-drawing-plan-panel"), frm, mayEditSettings);
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
		canEditDrawingOptimizer,
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
		onload_post_render(frm) { scheduleDrawingPanel(frm); },
		refresh(frm) { scheduleDrawingPanel(frm); },
	});

	window.addEventListener("almdina:stage-context-ready", (event) => {
		const frm = event.detail && event.detail.frm;
		if (frm && frm === window.cur_frm) scheduleDrawingPanel(frm);
	});
})();
