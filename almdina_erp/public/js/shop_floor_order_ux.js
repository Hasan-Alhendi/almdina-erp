(() => {
	"use strict";

	const ACTION_GROUP = __("الرسم / DXF");

	function permissionContext() {
		return window.AlmdinaPermissions || null;
	}

	function can(capability) {
		const context = permissionContext();
		return Boolean(context && context.can(capability));
	}

	function isShopFloorProfile() {
		const context = permissionContext();
		return Boolean(context && context.profile() === "shop_floor");
	}

	function isAssignedToCurrentUser(frm) {
		return Boolean(
			frm.doc.current_assignee &&
			frappe.session.user &&
			frm.doc.current_assignee === frappe.session.user
		);
	}

	function isAtDrawing(frm) {
		return (
			frm.doc.status === "At Drawing" ||
			(frm.doc.production_path === "Drawing" && frm.doc.current_department === "رسم")
		);
	}

	function callAction(method, args, successMessage, frm) {
		return frappe
			.call({
				method,
				args,
				freeze: true,
				freeze_message: __("Processing..."),
			})
			.then((response) => {
				if (successMessage) {
					frappe.show_alert({ message: successMessage, indicator: "green" });
				}
				if (frm) {
					return frm.reload_doc().then(() => response.message);
				}
				return response.message;
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

	function statusLabel(status) {
		return __(STATUS_LABELS[status] || status || "");
	}

	function renderProgressSteps(frm) {
		const steps = PATH_STEPS[frm.doc.production_path];
		if (!steps) return "";
		const current = STATUS_STEP[frm.doc.status] || frm.doc.current_department || "";
		const delivered = frm.doc.status === "Delivered";
		const currentIndex = delivered ? steps.length - 1 : steps.indexOf(current);
		return `<div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:10px">${steps
			.map((step, index) => {
				const done = delivered || index < currentIndex;
				const active = !delivered && index === currentIndex;
				const background = done ? "#15803d" : active ? "#2490ef" : "var(--control-bg,#f3f4f6)";
				const color = done || active ? "#fff" : "var(--text-muted,#6b7280)";
				return `<span style="display:inline-flex;align-items:center;gap:4px;background:${background};color:${color};border-radius:999px;padding:5px 12px;font-size:12px;font-weight:700;white-space:nowrap">${done ? "✓ " : ""}${__(step)}</span>`;
			})
			.join('<span style="color:var(--text-muted,#9ca3af);font-size:13px">‹</span>')}</div>`;
	}

	function renderTrackingStrip(frm) {
		const field = frm.fields_dict.operator_status_strip;
		if (!field || !field.$wrapper) return;
		if (frm.is_new()) {
			field.$wrapper.empty();
			return;
		}
		const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
		const status = frm.doc.status || "Draft";
		const color = STATUS_COLORS[status] || "#374151";
		const facts = [
			[__("القسم الحالي"), frm.doc.current_department || "-"],
			[__("العامل"), frm.doc.current_assignee || "-"],
			[__("حالة القسم"), frm.doc.department_status || "-"],
		]
			.map(
				([label, value]) => `<div style="min-width:120px"><div style="font-size:11px;color:var(--text-muted,#6b7280);font-weight:700">${escape(label)}</div><div style="font-size:14px;font-weight:700">${escape(value)}</div></div>`
			)
			.join("");
		field.$wrapper.html(`
			<div class="frappe-card" style="padding:14px 16px;margin-bottom:10px;border-inline-start:6px solid ${color}">
				<div style="display:flex;flex-wrap:wrap;align-items:center;gap:14px 22px">
					<div><div style="font-size:11px;color:var(--text-muted,#6b7280);font-weight:700">${__("حالة الطلب")}</div><div style="display:inline-block;background:${color};color:#fff;border-radius:999px;padding:5px 16px;font-size:15px;font-weight:800;margin-top:2px">${escape(statusLabel(status))}</div></div>
					${facts}
				</div>
				${renderProgressSteps(frm)}
			</div>`);
	}

	function applyShopFloorPresentation(frm) {
		if (!isShopFloorProfile()) return;
		const keep = new Set([
			"operator_status_strip",
			"results_tab",
			"plan_section",
			"cutting_plan_html",
			"shop_floor_section",
			"production_path",
			"current_department",
			"shop_floor_column",
			"current_assignee",
			"department_status",
			"current_production_stage",
			"production_dxf",
			"drawing_dxf_status",
		]);
		(frm.meta.fields || []).forEach((field) => {
			if (!field || !field.fieldname) return;
			frm.set_df_property(field.fieldname, "hidden", keep.has(field.fieldname) ? 0 : 1);
		});
		if (frm.fields_dict.results_tab) {
			try {
				frm.set_tab("results_tab");
			} catch (error) {
				console.debug("Could not focus cutting-plan tab", error);
			}
		}
		frm.disable_save();
		frm.page.clear_inner_toolbar();
		frm.add_custom_button(__("رجوع لصالة الإنتاج"), () => frappe.set_route("shop-floor-inbox"));
	}

	function openDispatchDialog(frm) {
		return frappe
			.call({ method: "almdina_erp.almdina_erp.services.shop_floor_service.get_dispatch_options" })
			.then((response) => {
				const workers = (response.message && response.message.workers) || {};
				const dialog = new frappe.ui.Dialog({
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
								const list = workers[dialog.get_value("path")] || [];
								dialog.set_df_property("assignee", "options", list.map((row) => row.name).join("\n"));
								dialog.set_value("assignee", list[0] ? list[0].name : "");
							},
						},
						{
							fieldname: "assignee",
							fieldtype: "Select",
							label: __("العامل"),
							options: (workers.Sharyoun || []).map((row) => row.name).join("\n"),
							reqd: 1,
						},
					],
					primary_action_label: __("إرسال"),
					primary_action(values) {
						dialog.hide();
						callAction(
							"almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order",
							{ order_name: frm.doc.name, path: values.path, assignee: values.assignee },
							__("تم إرسال الطلب للإنتاج."),
							frm
						);
					},
				});
				dialog.show();
			});
	}

	frappe.provide("frappe.almdina");
	frappe.almdina.open_dispatch_dialog = openDispatchDialog;

	function addDispatchButton(frm) {
		if (isShopFloorProfile() || frm.is_new() || !can("dispatch_order")) return;
		if (frm.doc.status !== "Approved" || frm.doc.production_path || frm.doc.current_production_stage) return;
		frm.add_custom_button(__("إرسال للإنتاج"), () => openDispatchDialog(frm), __("صالة الإنتاج"));
	}

	function addDeliveryButtons(frm) {
		if (isShopFloorProfile() || frm.is_new()) return;
		if (frm.doc.status === "Ready for Delivery" && can("mark_delivered")) {
			frm.add_custom_button(__("تم التسليم"), () => {
				frappe.confirm(__("تأكيد تسليم الطلب للعميل؟"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered",
						{ order_name: frm.doc.name },
						__("تم تسجيل التسليم."),
						frm
					)
				);
			}, __("صالة الإنتاج"));
		}
		if (frm.doc.production_path && frm.doc.status !== "Delivered" && can("revert_department")) {
			frm.add_custom_button(__("إرجاع لمرحلة سابقة"), () => openRevertDialog(frm), __("صالة الإنتاج"));
		}
	}

	function openRevertDialog(frm) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.get_revert_targets",
				args: { order_name: frm.doc.name },
			})
			.then((response) => {
				const rows = response.message || [];
				if (!rows.length) {
					frappe.msgprint(__("لا توجد مراحل يمكن الرجوع إليها."));
					return;
				}
				const labels = new Map(rows.map((row) => [row.label || __(row.stage_type), row.stage_type]));
				frappe.prompt(
					[{ fieldname: "target", fieldtype: "Select", label: __("المرحلة"), options: [...labels.keys()].join("\n"), reqd: 1 }],
					(values) => callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.revert_department",
						{ order_name: frm.doc.name, target_stage_type: labels.get(values.target) },
						__("تم إرجاع الطلب للمرحلة المحددة."),
						frm
					),
					__("إرجاع لمرحلة سابقة"),
					__("إرجاع")
				);
			});
	}

	function availableApprovalSources(frm) {
		const sources = [];
		if (frm.doc.system_plan_json || frm.doc.cutting_plan_json) {
			sources.push({ value: "System", label: __("خطة النظام") });
		}
		if (frm.doc.custom_plan_json && frm.doc.production_dxf) {
			sources.push({ value: "Custom", label: __("الخطة المرفوعة من DXF") });
		}
		return sources;
	}

	function approveDrawing(frm) {
		const sources = availableApprovalSources(frm);
		if (!sources.length) {
			frappe.msgprint(__("لا توجد خطة صالحة للاعتماد."));
			return;
		}
		const submit = (source) =>
			callAction(
				"almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf",
				{ order_name: frm.doc.name, plan_source: source },
				__("تم اعتماد الرسم وإثبات المصمم المعتمد."),
				frm
			);
		if (sources.length === 1) {
			frappe.confirm(
				__("سيتم تثبيت {0} كنسخة الإنتاج النهائية باسمك. هل تريد المتابعة؟", [sources[0].label]),
				() => submit(sources[0].value)
			);
			return;
		}
		const labels = new Map(sources.map((source) => [source.label, source.value]));
		frappe.prompt(
			[{
				fieldname: "source",
				fieldtype: "Select",
				label: __("الخطة المعتمدة للإنتاج"),
				options: [...labels.keys()].join("\n"),
				reqd: 1,
				description: __("اختر الخطة التي راجعتها. سيتم تسجيل اعتمادك باسم المستخدم الحالي."),
			}],
			(values) => submit(labels.get(values.source)),
			__("اعتماد الرسم"),
			__("اعتماد للإنتاج")
		);
	}

	function uploadDrawingDxf(frm) {
		const replacing = Boolean(frm.doc.production_dxf);
		new frappe.ui.FileUploader({
			doctype: "Door Cutting Order",
			docname: frm.doc.name,
			folder: "Home/Attachments",
			is_private: 1,
			restrictions: { allowed_file_types: [".dxf"], max_file_size: 10 * 1024 * 1024 },
			on_success(file) {
				callAction(
					"almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf",
					{ order_name: frm.doc.name, file_url: file.file_url },
					replacing ? __("تم استبدال ملف DXF والتحقق منه.") : __("تم رفع ملف DXF والتحقق منه."),
					frm
				);
			},
		});
	}

	function addDrawingDxfButtons(frm) {
		if (frm.is_new()) return;

		if (frm.doc.production_dxf && can("export_dxf")) {
			frm.add_custom_button(__("تنزيل DXF للإنتاج"), () => window.open(frm.doc.production_dxf, "_blank"), ACTION_GROUP);
		}
		if (!isAtDrawing(frm) || !isAssignedToCurrentUser(frm) || frm.doc.approved_plan) return;

		if (can("export_dxf")) {
			frm.add_custom_button(__("تصدير DXF للرسم"), () => {
				const exporter = frappe.almdina && frappe.almdina.export_order_dxf;
				const markExported = () => frappe.call({
					method: "almdina_erp.almdina_erp.services.shop_floor_service.mark_dxf_exported",
					args: { order_name: frm.doc.name },
				}).then(() => frm.reload_doc());
				if (exporter) return exporter(frm.doc.name).then(markExported);
				frappe.msgprint(__("تعذر تشغيل مصدر DXF الآمن."));
				return null;
			}, ACTION_GROUP);
		}

		const uploadCapability = frm.doc.production_dxf ? "replace_dxf" : "upload_dxf";
		if (can(uploadCapability)) {
			frm.add_custom_button(
				frm.doc.production_dxf ? __("استبدال ملف DXF") : __("رفع ملف DXF"),
				() => uploadDrawingDxf(frm),
				ACTION_GROUP
			);
		}

		if (can("approve_dxf") && availableApprovalSources(frm).length) {
			frm.add_custom_button(__("اعتماد الرسم"), () => approveDrawing(frm), ACTION_GROUP);
		}
		if (can("print_cutting_plan")) {
			frm.add_custom_button(__("طباعة خطة القص"), () => {
				if (window.AlmdinaDrawingPlanUX && window.AlmdinaDrawingPlanUX.printActivePlan) {
					window.AlmdinaDrawingPlanUX.printActivePlan(frm);
				}
			}, ACTION_GROUP);
		}
	}

	function addWorkerStageButtons(frm) {
		if (frm.is_new() || !frm.doc.current_production_stage) return;
		const assignedToMe = isAssignedToCurrentUser(frm);
		const canOverrideAssignment = can("reassign_worker");
		if (!assignedToMe && !canOverrideAssignment) return;
		const stageName = frm.doc.current_production_stage;
		frappe.db.get_value("Production Stage", stageName, ["status", "stage_type"]).then((response) => {
			const stageStatus = (response.message && response.message.status) || "";
			const stageType = (response.message && response.message.stage_type) || frm.doc.current_department;
			if (stageStatus === "Pending" && can("start_assigned_stage")) {
				frm.add_custom_button(__("بدء العمل"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage",
						{ stage_name: stageName },
						__("تم بدء العمل."),
						frm
					), __("صالة الإنتاج"));
				return;
			}
			if (!["In Progress", "Paused"].includes(stageStatus) || !can("handoff_assigned_stage")) return;
			const isSanding = stageType === "Sanding" || frm.doc.current_department === "تقشيط";
			frm.add_custom_button(isSanding ? __("جاهزة للتسليم") : __("إرسال للقسم التالي"), () => {
				if (isSanding) {
					frappe.confirm(__("تأكيد إنهاء التقشيط؟"), () =>
						callAction(
							"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
							{ stage_name: stageName },
							__("الطلب جاهز للتسليم."),
							frm
						)
					);
					return;
				}
				openHandoffDialog(frm, stageName);
			}, __("صالة الإنتاج"));
		});
	}

	function openHandoffDialog(frm, stageName) {
		frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_service.get_handoff_workers",
			args: { stage_name: stageName },
		}).then((response) => {
			const workers = response.message || [];
			frappe.prompt(
				[{ fieldname: "next_assignee", fieldtype: "Select", label: __("العامل التالي"), options: workers.map((worker) => worker.name).join("\n"), reqd: 1 }],
				(values) => callAction(
					"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
					{ stage_name: stageName, next_assignee: values.next_assignee },
					__("تم إرسال الطلب."),
					frm
				),
				__("إرسال للقسم التالي"),
				__("إرسال")
			);
		});
	}

	frappe.ui.form.on("Door Cutting Order", {
		refresh(frm) {
			applyShopFloorPresentation(frm);
			renderTrackingStrip(frm);
			addDispatchButton(frm);
			addDeliveryButtons(frm);
			addDrawingDxfButtons(frm);
			addWorkerStageButtons(frm);
		},
	});
})();
