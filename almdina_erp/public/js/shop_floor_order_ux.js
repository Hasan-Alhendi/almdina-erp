(() => {
	"use strict";

	const SHOP_FLOOR_ROLES = ["عامل رسم", "عامل شريون", "عامل CNC", "عامل تقشيط"];

	function has_role(role) {
		return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
	}

	function is_dispatcher() {
		return has_role("Order Entry") || has_role("Production Manager");
	}

	function is_shop_floor_only() {
		if (frappe.boot && frappe.boot.almdina_shop_floor_only) return true;
		const roles = frappe.user_roles || [];
		if (
			roles.some((r) =>
				["System Manager", "Production Manager", "Order Entry", "Accounts Management"].includes(r)
			)
		) {
			return false;
		}
		return roles.some((r) => SHOP_FLOOR_ROLES.includes(r));
	}

	function call_action(method, args, success_message, frm) {
		return frappe
			.call({
				method,
				args,
				freeze: true,
				freeze_message: __("Processing..."),
			})
			.then((r) => {
				if (success_message) {
					frappe.show_alert({ message: success_message, indicator: "green" });
				}
				if (frm) {
					return frm.reload_doc().then(() => r.message);
				}
				return r.message;
			});
	}

	const STATUS_LABELS = {
		Draft: "مسودة",
		"Pending Review": "بانتظار المراجعة",
		Approved: "معتمد",
		"At Sharyoun": "في الشريون",
		"At Drawing": "في الرسم",
		"At CNC": "في CNC",
		"At Sanding": "في التقشيط",
		"Ready for Delivery": "جاهز للتسليم",
		Delivered: "تم التسليم",
		Completed: "مكتمل",
		Rejected: "مرفوض",
		"On Hold": "معلّق",
		Cancelled: "ملغى",
	};

	const STATUS_COLORS = {
		Draft: "#6b7280",
		"Pending Review": "#b45309",
		Approved: "#2563eb",
		"At Sharyoun": "#7c3aed",
		"At Drawing": "#7c3aed",
		"At CNC": "#7c3aed",
		"At Sanding": "#7c3aed",
		"Ready for Delivery": "#0891b2",
		Delivered: "#15803d",
		Completed: "#15803d",
		Rejected: "#b91c1c",
		Cancelled: "#b91c1c",
		"On Hold": "#b45309",
	};

	const PATH_STEPS = {
		Sharyoun: ["شريون", "تقشيط", "تسليم"],
		Drawing: ["رسم", "CNC", "تقشيط", "تسليم"],
	};

	const STATUS_STEP = {
		"At Sharyoun": "شريون",
		"At Drawing": "رسم",
		"At CNC": "CNC",
		"At Sanding": "تقشيط",
		"Ready for Delivery": "تسليم",
		Delivered: "تسليم",
	};

	const DEPARTMENT_BY_STATUS = {
		"Ready for Delivery": "جاهز للتسليم",
		Delivered: "تم التسليم",
	};

	function status_label(status) {
		return __(STATUS_LABELS[status] || status || "");
	}

	function render_progress_steps(frm) {
		const path = frm.doc.production_path;
		const steps = PATH_STEPS[path];
		if (!steps) return "";

		const current = STATUS_STEP[frm.doc.status] || frm.doc.current_department || "";
		const delivered = frm.doc.status === "Delivered";
		let currentIndex = steps.indexOf(current);
		if (delivered) currentIndex = steps.length - 1;

		const chips = steps
			.map((step, index) => {
				const done = delivered ? true : index < currentIndex;
				const active = !delivered && index === currentIndex;
				const bg = done ? "#15803d" : active ? "#2490ef" : "var(--control-bg, #f3f4f6)";
				const color = done || active ? "#fff" : "var(--text-muted, #6b7280)";
				const mark = done ? "✓ " : "";
				return `<span style="display:inline-flex;align-items:center;gap:4px;background:${bg};color:${color};
					border-radius:999px;padding:5px 12px;font-size:12px;font-weight:700;white-space:nowrap">${mark}${__(step)}</span>`;
			})
			.join(
				`<span style="color:var(--text-muted,#9ca3af);font-size:13px">‹</span>`
			);

		return `<div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:10px">${chips}</div>`;
	}

	function render_tracking_strip(frm) {
		if (!frm.fields_dict.operator_status_strip) return;
		if (frm.is_new()) {
			frm.fields_dict.operator_status_strip.$wrapper.empty();
			return;
		}

		const status = frm.doc.status || "Draft";
		const color = STATUS_COLORS[status] || "#374151";
		const dept =
			DEPARTMENT_BY_STATUS[frm.doc.status] ||
			frm.doc.current_department ||
			"-";
		const assignee = frm.doc.current_assignee || "-";
		const deptStatus = frm.doc.department_status || "-";
		const esc = (v) => frappe.utils.escape_html(String(v ?? ""));

		const facts = [
			[__("القسم الحالي"), esc(dept)],
			[__("العامل"), esc(assignee)],
			[__("حالة القسم"), esc(deptStatus)],
		]
			.map(
				([label, value]) => `
				<div style="min-width:120px">
					<div style="font-size:11px;color:var(--text-muted,#6b7280);font-weight:700">${label}</div>
					<div style="font-size:14px;font-weight:700">${value}</div>
				</div>`
			)
			.join("");

		frm.fields_dict.operator_status_strip.$wrapper.html(`
			<div class="frappe-card" style="padding:14px 16px;margin-bottom:10px;border-inline-start:6px solid ${color}">
				<div style="display:flex;flex-wrap:wrap;align-items:center;gap:14px 22px">
					<div>
						<div style="font-size:11px;color:var(--text-muted,#6b7280);font-weight:700">${__("حالة الطلب")}</div>
						<div style="display:inline-block;background:${color};color:#fff;border-radius:999px;
							padding:5px 16px;font-size:15px;font-weight:800;margin-top:2px">${esc(status_label(status))}</div>
					</div>
					${facts}
				</div>
				${render_progress_steps(frm)}
			</div>
		`);
	}

	function strip_form_for_shop_floor(frm) {
		if (!is_shop_floor_only()) return;

		const keep = new Set(["operator_status_strip", "results_tab", "plan_section", "cutting_plan_html"]);

		(frm.meta.fields || []).forEach((df) => {
			if (!df || !df.fieldname) return;
			if (keep.has(df.fieldname)) {
				frm.set_df_property(df.fieldname, "hidden", 0);
				return;
			}
			frm.set_df_property(df.fieldname, "hidden", 1);
		});

		if (frm.fields_dict.results_tab) {
			frm.set_df_property("results_tab", "hidden", 0);
			try {
				frm.set_tab("results_tab");
			} catch (e) {
				/* ignore */
			}
		}
		if (frm.fields_dict.plan_section) {
			frm.set_df_property("plan_section", "hidden", 0);
			frm.set_df_property("plan_section", "label", __("خطة القص والرسومات"));
		}
		if (frm.fields_dict.cutting_plan_html) {
			frm.set_df_property("cutting_plan_html", "hidden", 0);
			frm.set_df_property("cutting_plan_html", "label", __("خطة القص"));
		}
		if (frm.fields_dict.operator_status_strip) {
			frm.set_df_property("operator_status_strip", "hidden", 0);
		}

		frm.disable_save();
		frm.page.clear_inner_toolbar();
		frm.add_custom_button(__("رجوع لصالة الإنتاج"), () => {
			frappe.set_route("shop-floor-inbox");
		});
	}

	function open_dispatch_dialog(frm) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.get_dispatch_options",
			})
			.then((r) => {
				const opts = r.message || {};
				const workers = opts.workers || {};
				const d = new frappe.ui.Dialog({
					title: __("إرسال للإنتاج"),
					fields: [
						{
							fieldname: "path",
							fieldtype: "Select",
							label: __("المسار"),
							options: "Sharyoun\nDrawing",
							reqd: 1,
							default: "Sharyoun",
							onchange() {
								const path = d.get_value("path");
								const list = workers[path] || [];
								d.set_df_property(
									"assignee",
									"options",
									list.map((w) => w.name).join("\n")
								);
								d.set_value("assignee", list[0] ? list[0].name : "");
							},
						},
						{
							fieldname: "assignee",
							fieldtype: "Select",
							label: __("العامل"),
							options: (workers.Sharyoun || []).map((w) => w.name).join("\n"),
							reqd: 1,
							default: (workers.Sharyoun || [])[0] ? workers.Sharyoun[0].name : "",
						},
					],
					primary_action_label: __("إرسال"),
					primary_action(values) {
						d.hide();
						call_action(
							"almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order",
							{
								order_name: frm.doc.name,
								path: values.path,
								assignee: values.assignee,
							},
							__("تم إرسال الطلب للإنتاج."),
							frm
						);
					},
				});
				d.show();
			});
	}

	frappe.provide("frappe.almdina");
	frappe.almdina.open_dispatch_dialog = open_dispatch_dialog;

	function add_dispatch_button(frm) {
		// Order Entry uses the workflow button on draft orders; keep this helper
		// only for legacy approved-but-not-dispatched rows.
		if (is_shop_floor_only()) return;
		if (frm.is_new() || frm.doc.status !== "Approved" || !is_dispatcher()) return;
		if (frm.doc.production_path || frm.doc.current_production_stage) return;

		frm.add_custom_button(__("إرسال للإنتاج"), () => open_dispatch_dialog(frm), __("صالة الإنتاج"));
	}

	function add_delivery_buttons(frm) {
		if (is_shop_floor_only() || frm.is_new() || !is_dispatcher()) return;

		if (frm.doc.status === "Ready for Delivery") {
			frm.add_custom_button(__("تم التسليم"), () => {
				frappe.confirm(__("تأكيد تسليم الطلب للعميل؟"), () =>
					call_action(
						"almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered",
						{ order_name: frm.doc.name },
						__("تم تسجيل التسليم."),
						frm
					)
				);
			}, __("صالة الإنتاج"));
		}

		if (frm.doc.production_path && frm.doc.status !== "Delivered") {
			frm.add_custom_button(__("إرجاع لمرحلة سابقة"), () => {
				frappe
					.call({
						method: "almdina_erp.almdina_erp.services.shop_floor_service.get_revert_targets",
						args: { order_name: frm.doc.name },
					})
					.then((r) => {
						const rows = r.message || [];
						if (!rows.length) {
							frappe.msgprint(__("لا توجد مراحل يمكن الرجوع إليها."));
							return;
						}
						const labelToType = {};
						const options = rows.map((row) => {
							const label = row.label || __(row.stage_type);
							labelToType[label] = row.stage_type;
							return label;
						});
						frappe.prompt(
							[
								{
									fieldname: "target_stage_label",
									fieldtype: "Select",
									label: __("المرحلة"),
									options: options.join("\n"),
									reqd: 1,
									default: options[0],
									description: __("اختر المرحلة بالاسم للعودة إليها."),
								},
							],
							(values) =>
								call_action(
									"almdina_erp.almdina_erp.services.shop_floor_service.revert_department",
									{
										order_name: frm.doc.name,
										target_stage_type: labelToType[values.target_stage_label] || values.target_stage_label,
									},
									__("تم إرجاع الطلب للمرحلة المحددة."),
									frm
								),
							__("إرجاع لمرحلة سابقة"),
							__("إرجاع")
						);
					});
			}, __("صالة الإنتاج"));
		}
	}

	function add_drawing_dxf_buttons(frm) {
		if (frm.is_new()) return;
		const atDrawing =
			frm.doc.status === "At Drawing" ||
			(frm.doc.production_path === "Drawing" && frm.doc.current_department === "رسم");
		if (!atDrawing) return;

		if (has_role("عامل رسم") || has_role("Production Manager")) {
			if (!frm.doc.approved_plan) {
				frm.add_custom_button(__("اعتماد خطة النظام"), () => {
					frappe.confirm(
						__("سيتم اعتماد خطة النظام الحالية كنسخة إنتاج ثابتة. هل تريد المتابعة؟"),
						() =>
							call_action(
								"almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan",
								{ order_name: frm.doc.name, plan_source: "System" },
								__("تم اعتماد خطة النظام."),
								frm
							)
					);
				}, __("الرسم / DXF"));

				if (frm.doc.custom_plan_json && frm.doc.production_dxf) {
					frm.add_custom_button(__("اعتماد الخطة المرفوعة"), () => {
						frappe.confirm(
							__("سيتم اعتماد الخطة المستوردة من DXF كنسخة إنتاج ثابتة. هل تريد المتابعة؟"),
							() =>
								call_action(
									"almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan",
									{ order_name: frm.doc.name, plan_source: "Custom" },
									__("تم اعتماد الخطة المرفوعة."),
									frm
								)
						);
					}, __("الرسم / DXF"));
				}
			}

			// Prefer the validated AutoCAD exporter when available.
			frm.add_custom_button(__("تصدير DXF للرسم"), () => {
				const exporter = frappe.almdina && frappe.almdina.export_order_dxf;
				const after = () =>
					frappe
						.call({
							method: "almdina_erp.almdina_erp.services.shop_floor_service.mark_dxf_exported",
							args: { order_name: frm.doc.name },
						})
						.then(() => frm.reload_doc());

				if (exporter) {
					return exporter(frm.doc.name).then(after);
				}
				frappe.show_alert({
					message: __("استخدم زر تصدير DXF الآمن من خطة القص، ثم ارفع الملف المعدّل."),
					indicator: "blue",
				});
				return after();
			}, __("الرسم / DXF"));

			frm.add_custom_button(__("رفع DXF معدّل"), () => {
				new frappe.ui.FileUploader({
					folder: "Home/Attachments",
					restrictions: { allowed_file_types: [".dxf"] },
					on_success(file) {
						call_action(
							"almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf",
							{ order_name: frm.doc.name, file_url: file.file_url },
							__("تم رفع ملف DXF."),
							frm
						);
					},
				});
			}, __("الرسم / DXF"));

			if (frm.doc.custom_plan_json && frm.doc.production_dxf && frm.doc.drawing_dxf_status !== "Approved by Drawing") {
				frm.add_custom_button(__("اعتماد الرسم"), () => {
					frappe.confirm(__("اعتماد الخطة المرفوعة من DXF كمصدر للإنتاج؟"), () =>
						call_action(
							"almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf",
							{ order_name: frm.doc.name },
							__("تم اعتماد الخطة المرفوعة."),
							frm
						)
					);
				}, __("الرسم / DXF"));
			}

			frm.add_custom_button(__("طباعة خطة القص"), () => {
				if (window.AlmdinaDrawingPlanUX && window.AlmdinaDrawingPlanUX.printActivePlan) {
					window.AlmdinaDrawingPlanUX.printActivePlan(frm);
					return;
				}
				if (window.AlmdinaCuttingPlanRender && window.AlmdinaCuttingPlanRender.print) {
					window.AlmdinaCuttingPlanRender.print(frm);
				}
			}, __("الرسم / DXF"));
		}

		if (frm.doc.production_dxf && (has_role("عامل CNC") || has_role("عامل رسم") || is_dispatcher())) {
			frm.add_custom_button(__("تنزيل DXF المعتمد"), () => {
				window.open(frm.doc.production_dxf, "_blank");
			}, __("الرسم / DXF"));
		}
	}

	function add_worker_stage_buttons(frm) {
		if (frm.is_new() || !frm.doc.current_production_stage) return;
		const stageName = frm.doc.current_production_stage;
		const assignedToMe = frm.doc.current_assignee === frappe.session.user;
		const canOperate =
			assignedToMe || has_role("Production Manager") || has_role("System Manager");
		if (!canOperate) return;

		frappe.db.get_value("Production Stage", stageName, ["status", "stage_type"]).then((r) => {
			const stageStatus = (r.message && r.message.status) || "";
			const stageType = (r.message && r.message.stage_type) || frm.doc.current_department;

			if (stageStatus === "Pending") {
				frm.add_custom_button(__("بدء العمل"), () => {
					call_action(
						"almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage",
						{ stage_name: stageName },
						__("تم بدء العمل."),
						frm
					);
				}, __("صالة الإنتاج"));
				return;
			}

			if (!["In Progress", "Paused"].includes(stageStatus)) {
				return;
			}

			const isSanding = stageType === "Sanding" || frm.doc.current_department === "تقشيط";
			frm.add_custom_button(isSanding ? __("جاهزة للتسليم") : __("إرسال للقسم التالي"), () => {
				if (isSanding) {
					frappe.confirm(__("تأكيد إنهاء التقشيط؟"), () =>
						call_action(
							"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
							{ stage_name: stageName },
							__("الطلب جاهز للتسليم."),
							frm
						)
					);
					return;
				}
				frappe
					.call({
						method: "almdina_erp.almdina_erp.services.shop_floor_service.get_handoff_workers",
						args: { stage_name: stageName },
					})
					.then((r) => {
						const workers = r.message || [];
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
								call_action(
									"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
									{
										stage_name: stageName,
										next_assignee: values.next_assignee,
									},
									__("تم إرسال الطلب."),
									frm
								),
							__("إرسال للقسم التالي"),
							__("إرسال")
						);
					});
			}, __("صالة الإنتاج"));
		});
	}

	frappe.ui.form.on("Door Cutting Order", {
		refresh(frm) {
			strip_form_for_shop_floor(frm);
			render_tracking_strip(frm);
			add_dispatch_button(frm);
			add_delivery_buttons(frm);
			add_drawing_dxf_buttons(frm);
			add_worker_stage_buttons(frm);
		},
	});
})();
