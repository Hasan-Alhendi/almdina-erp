frappe.pages["shop-floor-inbox"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("صالة الإنتاج"),
		single_column: true,
	});

	const $section = $(wrapper).find(".layout-main-section");
	$section.html(`
		<div class="almdina-sf-tabs">
			<button type="button" class="almdina-sf-tab is-active" data-sf-mode="inbox">${__("الطلبات الواردة")}</button>
			<button type="button" class="almdina-sf-tab" data-sf-mode="archive">${__("الطلبات المؤرشفة")}</button>
			<button type="button" class="almdina-sf-tab" data-sf-mode="account">${__("الحساب")}</button>
			<button type="button" class="btn btn-default almdina-sf-refresh">${__("تحديث")}</button>
		</div>
		<div class="almdina-sf-content"></div>
	`);

	const $tabs = $section.find(".almdina-sf-tabs");
	const $content = $section.find(".almdina-sf-content");

	let mode = "inbox";
	let selectedOrder = null;
	let selectedStage = null;

	function esc(value) {
		return frappe.utils.escape_html(String(value ?? ""));
	}

	function status_label(status) {
		const map = {
			Pending: __("بحاجة للعمل"),
			"In Progress": __("قيد العمل"),
			Paused: __("متوقف"),
			Completed: __("مكتمل"),
		};
		return map[status] || __(status || "");
	}

	// Hard role gate — do not rely only on stage type (CNC must never see export).
	function can_export_dxf() {
		const roles = frappe.user_roles || (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		if (roles.includes("عامل رسم") || roles.includes("Production Manager") || roles.includes("System Manager")) {
			return true;
		}
		if (frappe.almdina && typeof frappe.almdina.can_export_dxf === "function") {
			return Boolean(frappe.almdina.can_export_dxf());
		}
		return false;
	}

	function sync_tabs() {
		$tabs.find(".almdina-sf-tab").each(function () {
			$(this).toggleClass("is-active", $(this).attr("data-sf-mode") === mode);
		});
		$tabs.find(".almdina-sf-refresh").toggle(mode !== "account");
	}

	function set_mode(next) {
		mode = next;
		sync_tabs();
		if (mode === "account") {
			render_account();
			return;
		}
		load();
	}

	function load() {
		if (mode === "account") {
			render_account();
			return;
		}
		selectedOrder = null;
		selectedStage = null;
		const method =
			mode === "inbox"
				? "almdina_erp.almdina_erp.services.shop_floor_service.get_my_inbox"
				: "almdina_erp.almdina_erp.services.shop_floor_service.get_my_archive";
		$content.html(
			`<div class="almdina-sf-shell"><div class="text-muted">${__("جاري التحميل...")}</div></div>`
		);
		return frappe.call({ method, freeze: false }).then((r) => render(r.message || []));
	}

	function render(rows) {
		const title = mode === "inbox" ? __("الطلبات الواردة") : __("الطلبات المؤرشفة");
		if (!rows.length) {
			$content.html(`
				<div class="almdina-sf-shell">
					<div class="almdina-sf-list-title">${esc(title)}</div>
					<p class="text-muted">${__("لا توجد طلبات.")}</p>
				</div>
			`);
			return;
		}

		let html = `
			<div class="almdina-sf-shell">
				<div class="almdina-sf-list-title">${esc(title)}</div>
				<div class="almdina-sf-list">`;

		rows.forEach((row) => {
			html += `
				<div class="frappe-card almdina-sf-order-card shop-floor-order-card"
					data-order="${esc(row.door_cutting_order)}"
					data-stage="${esc(row.name)}"
					data-status="${esc(row.status)}"
					data-stage-type="${esc(row.stage_type)}"
					data-next="${esc(row.can_handoff_to || "")}">
					<div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
						<div style="min-width:0;flex:1">
							<div style="font-size:1.05rem;font-weight:800">${esc(row.door_cutting_order)}</div>
							<div class="text-muted" style="font-size:13px;margin:4px 0">${esc(row.customer || "")} · ${esc(
				row.order_date || ""
			)}</div>
							<div style="font-size:13px">${__("القسم")}: <b>${esc(row.department_label || row.stage_type)}</b></div>
							<div style="font-size:13px">${__("الحالة")}: <b>${esc(status_label(row.status))}</b></div>
						</div>
						<button type="button" class="btn btn-primary sf-open-btn open-detail">${__("فتح")}</button>
					</div>
				</div>`;
		});
		html += `</div><div class="shop-floor-detail" style="display:none"></div></div>`;
		$content.html(html);
		bind_list_actions();
	}

	function render_account() {
		const user = frappe.session.user || "";
		const boot_user = frappe.boot.user || {};
		const fullname = boot_user.full_name || frappe.user.full_name?.() || user;
		const roles = boot_user.roles || [];
		const shop_roles = ["عامل رسم", "عامل شريون", "عامل CNC", "عامل تقشيط"].filter((r) =>
			roles.includes(r)
		);
		$content.html(`
			<div class="almdina-sf-shell">
				<div class="almdina-sf-account-card">
					<h4 style="margin:0 0 12px">${__("معلومات الحساب")}</h4>
					<div class="almdina-sf-account-row"><span class="text-muted">${__("الاسم")}</span><b>${esc(
						fullname
					)}</b></div>
					<div class="almdina-sf-account-row"><span class="text-muted">${__(
						"المستخدم"
					)}</span><b dir="ltr">${esc(user)}</b></div>
					<div class="almdina-sf-account-row"><span class="text-muted">${__("القسم")}</span><b>${esc(
						shop_roles.join(" · ") || "—"
					)}</b></div>
					<button type="button" class="btn btn-danger almdina-sf-logout">${__("تسجيل الخروج")}</button>
				</div>
			</div>
		`);
		$content.find(".almdina-sf-logout").on("click", confirm_logout);
	}

	function confirm_logout() {
		frappe.confirm(__("تأكيد تسجيل الخروج؟"), () => {
			frappe.call({
				method: "logout",
				freeze: true,
				freeze_message: __("جاري تسجيل الخروج..."),
				always() {
					window.location.href = "/login";
				},
			});
		});
	}

	function bind_list_actions() {
		$content.find(".shop-floor-order-card").on("click", function (e) {
			if ($(e.target).closest("button").length && !$(e.target).hasClass("open-detail")) return;
			const $card = $(this);
			open_detail({
				order: $card.data("order"),
				stage: $card.data("stage"),
				status: $card.data("status"),
				stageType: $card.data("stage-type"),
				next: $card.data("next"),
			});
		});
	}

	function has_custom_plan(d) {
		if (!d || !d.custom_plan_json) return false;
		try {
			const plan = typeof d.custom_plan_json === "object" ? d.custom_plan_json : JSON.parse(d.custom_plan_json);
			return Boolean(plan && plan.sheets && plan.sheets.length);
		} catch (error) {
			return false;
		}
	}

	function empty_custom_plan_html() {
		return `<div style="padding:16px;color:#666;text-align:center;border:1px dashed #ccd3da;border-radius:12px;background:#fafafa;">${__(
			"لا يوجد خطة مرفوعة"
		)}</div>`;
	}

	function build_plan_tabs_html(d) {
		if (!d.show_dual_tabs) {
			return d.cutting_plan_html || `<div class="text-muted">${__("لا توجد خطة قص للعرض.")}</div>`;
		}
		const approved = d.approved_plan_source || "System";
		const badge = (tab) =>
			d.approved_plan && approved === tab
				? '<span style="margin-right:6px;font-size:10px;background:#15803d;color:#fff;border-radius:999px;padding:2px 8px;">معتمدة للإنتاج</span>'
				: "";
		const active = d.active_plan_source === "Custom" && has_custom_plan(d) ? "Custom" : "System";
		const systemHtml = d.system_plan_html || `<div class="text-muted">${__("لا توجد خطة نظام.")}</div>`;
		const customHtml = has_custom_plan(d) ? d.custom_plan_html || empty_custom_plan_html() : empty_custom_plan_html();
		return `
			<div class="dco-drawing-plan-inbox-host"></div>
			<div class="almdina-sf-plan-tabs" data-active-tab="${active}">
				<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
					<button type="button" class="btn btn-sm btn-default sf-plan-tab ${active === "System" ? "btn-primary" : ""}" data-plan-tab="System">
						${badge("System")}${__("خطة النظام")}
					</button>
					<button type="button" class="btn btn-sm btn-default sf-plan-tab ${active === "Custom" ? "btn-primary" : ""}" data-plan-tab="Custom">
						${badge("Custom")}${__("الخطة المرفوعة")}
					</button>
				</div>
				<div class="sf-plan-tab-panel" data-plan-panel="System" style="${active === "System" ? "" : "display:none;"}">${systemHtml}</div>
				<div class="sf-plan-tab-panel" data-plan-panel="Custom" style="${active === "Custom" ? "" : "display:none;"}">${customHtml}</div>
			</div>
		`;
	}

	function bind_plan_tabs($detail, d) {
		$detail.find(".sf-plan-tab").on("click", function onTab() {
			const tab = $(this).attr("data-plan-tab");
			$detail.find(".sf-plan-tab").removeClass("btn-primary");
			$(this).addClass("btn-primary");
			$detail.find(".sf-plan-tab-panel").hide();
			$detail.find(`[data-plan-panel="${tab}"]`).show();
			$detail.find(".almdina-sf-plan-tabs").attr("data-active-tab", tab);
		});
		$detail.find(".print-plan").on("click", () => {
			const tab = $detail.find(".almdina-sf-plan-tabs").attr("data-active-tab") || "System";
			const html =
				tab === "Custom"
					? has_custom_plan(d)
						? d.custom_plan_html
						: ""
					: d.system_plan_html || d.cutting_plan_html;
			if (!html) {
				frappe.msgprint(__("لا يوجد مخطط قص للطباعة."));
				return;
			}
			const win = window.open("", "_blank");
			if (!win) {
				frappe.msgprint(__("المتصفح منع فتح نافذة الطباعة."));
				return;
			}
			win.document.open();
			win.document.write(`<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>${esc(
				__("خطة قص")
			)}</title><style>@page{size:A4 portrait;margin:6mm}body{font-family:Arial,Tahoma,sans-serif;direction:rtl;padding:5mm}</style></head><body>${html}<script>window.onload=function(){setTimeout(function(){window.focus();window.print();},700);};<\/script></body></html>`);
			win.document.close();
		});
	}

	function resolveStageContext(d, meta) {
		return {
			order: d.name || meta.order,
			stage: d.active_stage_name || d.current_production_stage || meta.stage,
			status: d.active_stage_status || meta.status,
			stageType: d.current_stage_type || meta.stageType,
			next: d.can_handoff_to || meta.next,
		};
	}

	function buildDetailActionsHtml(d, meta) {
		const ctx = resolveStageContext(d, meta);
		const canStart = mode === "inbox" && Boolean(d.can_start_stage);
		const canHandoff = mode === "inbox" && Boolean(d.can_handoff_stage);
		const isSanding = ctx.stageType === "Sanding";

		let actions = `<button type="button" class="btn btn-default back-to-list">${__("رجوع")}</button>`;
		if (canStart) {
			actions += ` <button type="button" class="btn btn-primary start-stage">${__("بدء العمل")}</button>`;
		}
		if (canHandoff) {
			actions += ` <button type="button" class="btn btn-success handoff-stage">${
				isSanding ? __("جاهزة للتسليم") : __("إرسال للقسم التالي")
			}</button>`;
		}
		if (ctx.stageType === "Drawing" && mode === "inbox" && can_export_dxf()) {
			actions += ` <button type="button" class="btn btn-default export-dxf">${__(
				"تصدير DXF للتعديل"
			)}</button>`;
			actions += ` <button type="button" class="btn btn-default upload-dxf">${__("رفع DXF")}</button>`;
			actions += ` <button type="button" class="btn btn-default print-plan">${__("طباعة خطة القص")}</button>`;
			if (!d.approved_plan) {
				actions += ` <button type="button" class="btn btn-primary approve-system-plan">${__(
					"اعتماد خطة النظام"
				)}</button>`;
			}
			if (has_custom_plan(d) && d.production_dxf && d.drawing_dxf_status !== "Approved by Drawing") {
				actions += ` <button type="button" class="btn btn-primary approve-dxf">${__(
					"اعتماد الخطة المرفوعة"
				)}</button>`;
			}
		}
		return actions;
	}

	function stageStatusLabel(d, meta) {
		const ctx = resolveStageContext(d, meta);
		if (d.department_status) return d.department_status;
		return status_label(ctx.status);
	}

	function bindDetailActions($detail, d, meta) {
		const ctx = resolveStageContext(d, meta);
		meta = { ...meta, ...ctx };
		$detail.find(".back-to-list").on("click", () => {
			$detail.hide().empty();
			$content.find(".almdina-sf-list-title, .almdina-sf-list").show();
		});
		$detail.find(".start-stage").on("click", () => start_stage(meta));
		$detail.find(".handoff-stage").on("click", () => handoff_stage(meta));
		$detail.find(".export-dxf").on("click", () => export_dxf(meta.order));
		$detail.find(".upload-dxf").on("click", () => upload_dxf(meta.order));
		$detail.find(".approve-dxf").on("click", () => approve_dxf(meta.order));
		$detail.find(".approve-system-plan").on("click", () => approve_system_plan(meta.order));
	}

	function open_detail(meta) {
		selectedOrder = meta.order;
		selectedStage = meta.stage;
		const $detail = $content.find(".shop-floor-detail");
		$detail.html(`<div class="text-muted">${__("جاري تحميل خطة القص...")}</div>`).show();
		$content.find(".almdina-sf-list-title, .almdina-sf-list").hide();

		frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.get_order_shop_floor_detail",
				args: { order_name: meta.order },
			})
			.then((r) => {
				const d = r.message || {};
				const actions = buildDetailActionsHtml(d, meta);
				const ctx = resolveStageContext(d, meta);
				meta = { ...meta, ...ctx };
				const showDxf =
					Boolean(d.production_dxf) &&
					(ctx.stageType === "Drawing" ||
						ctx.stageType === "CNC" ||
						d.drawing_dxf_status === "Approved by Drawing");

				$detail.html(`
					<div class="frappe-card" style="padding:14px;border-radius:14px">
						<div style="margin-bottom:10px">
							<h3 class="almdina-sf-detail-title">${esc(d.name || meta.order)}</h3>
							<div class="text-muted">${esc(d.customer || "")}</div>
							<div style="font-size:13px;margin-top:4px">${__("القسم")}: <b>${esc(
								d.current_department || ctx.stageType || ""
							)}</b> · ${__("الحالة")}: <b>${esc(stageStatusLabel(d, meta))}</b></div>
						</div>
						<div class="almdina-sf-actions">${actions}</div>
						${
							showDxf
								? `<div style="margin-bottom:10px"><a class="btn btn-default" href="${esc(
										d.production_dxf
								  )}" target="_blank">${__("تنزيل DXF الإنتاج")}</a>
								<span class="text-muted"> · ${esc(__(d.drawing_dxf_status || ""))}</span></div>`
								: ""
						}
						${
							d.pieces_html
								? `<div class="almdina-sf-pieces-wrap" style="margin:8px 0 14px">${d.pieces_html}</div>`
								: `<div class="text-muted" style="margin:8px 0 14px">${__("لا توجد قطع مسجّلة.")}</div>`
						}
						<div style="margin:8px 0 10px"><b>${__("خطة القص والرسومات")}</b></div>
						<div class="almdina-sf-plan-wrap cutting-plan-wrap">
							${build_plan_tabs_html(d)}
						</div>
					</div>
				`);

				bindDetailActions($detail, d, meta);
				bind_plan_tabs($detail, d);
				if (window.AlmdinaDrawingPlanUX && window.AlmdinaDrawingPlanUX.renderInboxPanel) {
					const refreshInboxPlan = (preview) => {
						if (preview) {
							if (preview.system_plan_json) d.system_plan_json = preview.system_plan_json;
							if (preview.cutting_plan_json) d.cutting_plan_json = preview.cutting_plan_json;
							if (preview.packing_mode) d.packing_mode = preview.packing_mode;
						}
						return frappe
							.call({
								method: "almdina_erp.almdina_erp.services.shop_floor_service.get_order_shop_floor_detail",
								args: { order_name: meta.order },
							})
							.then((response) => {
								const fresh = response.message || {};
								Object.assign(d, fresh);
								$detail.find(".almdina-sf-plan-wrap").html(build_plan_tabs_html(d));
								bind_plan_tabs($detail, d);
								window.AlmdinaDrawingPlanUX.renderInboxPanel(
									$detail.find(".dco-drawing-plan-inbox-host"),
									meta,
									d,
									refreshInboxPlan
								);
							});
					};
					window.AlmdinaDrawingPlanUX.renderInboxPanel(
						$detail.find(".dco-drawing-plan-inbox-host"),
						meta,
						d,
						refreshInboxPlan
					);
				}
			});
	}

	function start_stage(meta) {
		frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage",
				args: { stage_name: meta.stage },
				freeze: true,
				freeze_message: __("بدء العمل..."),
			})
			.then(() => {
				frappe.show_alert({ message: __("تم بدء العمل."), indicator: "green" });
				load();
				open_detail({ ...meta, status: "In Progress" });
			});
	}

	function handoff_stage(meta) {
		if (meta.stageType === "Sanding" || !meta.next) {
			frappe.confirm(__("تأكيد إنهاء التقشيط واعتبار الطلب جاهزًا للتسليم؟"), () =>
				frappe
					.call({
						method: "almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
						args: { stage_name: meta.stage },
						freeze: true,
					})
					.then(() => {
						frappe.show_alert({ message: __("الطلب جاهز للتسليم."), indicator: "green" });
						load();
					})
			);
			return;
		}

		frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.get_handoff_workers",
				args: { stage_name: meta.stage },
			})
			.then((r) => {
				const workers = r.message || [];
				if (!workers.length) {
					frappe.msgprint(__("لا يوجد عمال متاحون للقسم التالي."));
					return;
				}
				frappe.prompt(
					[
						{
							fieldname: "next_assignee",
							fieldtype: "Select",
							label: __("العامل التالي"),
							options: workers.map((w) => w.name).join("\n"),
							reqd: 1,
						},
					],
					(values) =>
						frappe
							.call({
								method: "almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
								args: { stage_name: meta.stage, next_assignee: values.next_assignee },
								freeze: true,
							})
							.then(() => {
						frappe.show_alert({
							message: __("تم إرسال الطلب للقسم التالي."),
							indicator: "green",
						});
						load();
						$content.find(".shop-floor-detail").hide().empty();
						$content.find(".almdina-sf-list-title, .almdina-sf-list").show();
					}),
					__("إرسال للقسم التالي"),
					__("إرسال")
				);
			});
	}

	function export_dxf(orderName) {
		const exporter = frappe.almdina && frappe.almdina.export_order_dxf;
		if (!exporter) {
			frappe.msgprint(__("أداة تصدير DXF غير متاحة. حدّث الصفحة ثم أعد المحاولة."));
			return;
		}
		exporter(orderName).then(() =>
			frappe.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.mark_dxf_exported",
				args: { order_name: orderName },
			})
		);
	}

	function upload_dxf(orderName) {
		new frappe.ui.FileUploader({
			folder: "Home/Attachments",
			restrictions: { allowed_file_types: [".dxf"] },
			on_success(file) {
				frappe
					.call({
						method: "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf",
						args: { order_name: orderName, file_url: file.file_url },
						freeze: true,
					})
					.then(() => {
						frappe.show_alert({ message: __("تم رفع ملف DXF."), indicator: "green" });
						open_detail({
							order: selectedOrder,
							stage: selectedStage,
							status: "In Progress",
							stageType: "Drawing",
							next: "CNC",
						});
					});
			},
		});
	}

	function approve_system_plan(orderName) {
		frappe.confirm(__("اعتماد خطة النظام الحالية كنسخة إنتاج ثابتة؟"), () =>
			frappe
				.call({
					method: "almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan",
					args: { order_name: orderName, plan_source: "System" },
					freeze: true,
				})
				.then(() => {
					frappe.show_alert({ message: __("تم اعتماد خطة النظام."), indicator: "green" });
					open_detail({
						order: selectedOrder,
						stage: selectedStage,
						status: "In Progress",
						stageType: "Drawing",
						next: "CNC",
					});
				})
		);
	}

	function approve_dxf(orderName) {
		frappe.confirm(__("اعتماد الخطة المرفوعة من DXF كمصدر للإنتاج؟"), () =>
			frappe
				.call({
					method: "almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf",
					args: { order_name: orderName },
					freeze: true,
				})
				.then(() => {
					frappe.show_alert({ message: __("تم اعتماد الخطة المرفوعة."), indicator: "green" });
					open_detail({
						order: selectedOrder,
						stage: selectedStage,
						status: "In Progress",
						stageType: "Drawing",
						next: "CNC",
					});
				})
		);
	}

	$tabs.on("click", ".almdina-sf-tab", function () {
		set_mode($(this).attr("data-sf-mode"));
	});
	$tabs.on("click", ".almdina-sf-refresh", () => load());

	try {
		page.clear_primary_action();
		page.clear_inner_toolbar();
	} catch (e) {
		/* ignore */
	}

	sync_tabs();
	load();
};
