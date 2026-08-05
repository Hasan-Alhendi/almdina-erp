(() => {
	"use strict";

	const DRAWING_ACTION_GROUP = __("الرسم / DXF");
	const PRODUCTION_ACTION_GROUP = __("صالة الإنتاج");
	const ACTIVE_STAGE_STATUSES = new Set(["Pending", "In Progress", "Paused"]);

	function permissionContext() {
		return window.AlmdinaPermissions || null;
	}

	function can(frm, capability) {
		const context = permissionContext();
		return Boolean(
			context &&
			(
				typeof context.canDocument === "function"
					? context.canDocument(frm, capability)
					: context.can(capability)
			)
		);
	}

	function isShopFloorProfile(frm) {
		const context = permissionContext();
		return Boolean(
			context &&
			context.profile() === "shop_floor" &&
			!can(frm, "create_order") &&
			!can(frm, "edit_order")
		);
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
		const documentName = frm && frm.doc ? frm.doc.name : null;
		return frappe
			.call({
				method,
				args,
				freeze: true,
				freeze_message: __("جاري تنفيذ العملية..."),
			})
			.then((response) => {
				if (successMessage) {
					frappe.show_alert({ message: successMessage, indicator: "green" });
				}
				if (frm && frm.doc && frm.doc.name === documentName) {
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
		const configured = frm.__almdinaProductionRouteName === frm.doc.production_path && Array.isArray(frm.__almdinaProductionRouteSteps)
			? frm.__almdinaProductionRouteSteps.map((stage) => stage.department || stage.stage_type).filter(Boolean)
			: [];
		const steps = configured.length
			? [...configured, "تسليم"]
			: PATH_STEPS[frm.doc.production_path] || (frm.doc.current_department ? [frm.doc.current_department, "تسليم"] : null);
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
		if (!isShopFloorProfile(frm)) {
			const original = frm.__almdinaShopFloorHiddenState;
			if (!original) return false;
			Object.entries(original).forEach(([fieldname, hidden]) => {
				frm.set_df_property(fieldname, "hidden", hidden ? 1 : 0);
			});
			frm.__almdinaShopFloorHiddenState = null;
			const editable = frm.is_new()
				? can(frm, "create_order")
				: can(frm, "edit_order") && ["Draft", "Pending Review", "Rejected"].includes(frm.doc.status || "Draft");
			if (editable && typeof frm.enable_save === "function") frm.enable_save();
			return false;
		}
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
		if (!frm.__almdinaShopFloorHiddenState) {
			frm.__almdinaShopFloorHiddenState = Object.fromEntries(
				(frm.meta.fields || [])
					.filter(field => field && field.fieldname)
					.map(field => [field.fieldname, Boolean(field.hidden)])
			);
		}
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
		return true;
	}

	function openDispatchDialog(frm) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_service.get_dispatch_options",
				args: { order_name: frm.doc.name },
			})
			.then((response) => {
				const payload = response.message || {};
				const paths = Array.isArray(payload.paths) ? payload.paths : [];
				const workers = payload.workers || {};
				if (!paths.length) {
					frappe.msgprint(__("لا يوجد مسار إنتاج مفعّل. أنشئ مسارًا من البيانات الأساسية أولًا."));
					return;
				}
				const pathOptions = paths.map((path) => ({
					label: `${path.label} · ${path.stage_count || 0} ${__("مراحل")}`,
					value: path.value,
				}));
				const workerOptions = (path) => (workers[path] || []).map((worker) => ({
					label: worker.full_name && worker.full_name !== worker.name
						? `${worker.full_name} — ${worker.name}`
						: worker.name,
					value: worker.name,
				}));
				const routePreview = (pathName) => {
					const route = paths.find((row) => row.value === pathName) || paths[0];
					const stages = (route.stages || []).map((stage, index) => `
						<span title="${frappe.utils.escape_html(stage.operational_role || "")}" style="display:inline-flex;flex-direction:column;align-items:flex-start;gap:2px;padding:7px 10px;border-radius:12px;background:var(--subtle-fg,#f3f5f7);font-size:12px;font-weight:700">
							<span>${index + 1}. ${frappe.utils.escape_html(stage.department || stage.stage_type)}</span>
							<small style="font-weight:500;color:var(--text-muted,#667085)">${frappe.utils.escape_html(stage.operational_role || "")}</small>
						</span>`).join('<span style="color:var(--text-muted,#98a2b3)">←</span>');
					return `<div style="direction:rtl;padding:11px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;background:var(--fg-color,#fff)">
						<div style="font-weight:800;margin-bottom:8px">${frappe.utils.escape_html(route.label || route.value)}</div>
						<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${stages}</div>
					</div>`;
				};
				const firstPath = paths.some((path) => path.value === payload.default_path)
					? payload.default_path
					: paths[0].value;
				const firstWorkers = workerOptions(firstPath);
				const dialog = new frappe.ui.Dialog({
					title: __("إرسال للإنتاج"),
					size: "large",
					fields: [
						{
							fieldname: "path",
							fieldtype: "Select",
							label: __("المسار"),
							options: pathOptions,
							reqd: 1,
							default: firstPath,
							onchange() {
								const path = dialog.get_value("path");
								const list = workerOptions(path);
								dialog.set_df_property("assignee", "options", list);
								dialog.set_value("assignee", list[0] ? list[0].value : "");
								dialog.fields_dict.route_preview.$wrapper.html(routePreview(path));
							},
						},
						{ fieldname: "route_preview", fieldtype: "HTML" },
						{
							fieldname: "assignee",
							fieldtype: "Select",
							label: __("العامل المسؤول عن أول مرحلة"),
							options: firstWorkers,
							default: firstWorkers[0] ? firstWorkers[0].value : "",
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
				dialog.fields_dict.route_preview.$wrapper.html(routePreview(firstPath));
			});
	}

	frappe.provide("frappe.almdina");
	frappe.almdina.open_dispatch_dialog = openDispatchDialog;

	function addDispatchButton(frm) {
		if (isShopFloorProfile(frm) || frm.is_new() || !can(frm, "dispatch_order")) return;
		if (frm.doc.status !== "Approved" || frm.doc.production_path || frm.doc.current_production_stage) return;
		frm.add_custom_button(__("إرسال للإنتاج"), () => openDispatchDialog(frm), PRODUCTION_ACTION_GROUP);
	}

	function addDeliveryButtons(frm) {
		if (isShopFloorProfile(frm) || frm.is_new()) return;
		if (frm.doc.status === "Ready for Delivery" && can(frm, "mark_delivered")) {
			frm.add_custom_button(__("تم التسليم"), () => {
				frappe.confirm(__("تأكيد تسليم الطلب للعميل؟"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered",
						{ order_name: frm.doc.name },
						__("تم تسجيل التسليم."),
						frm
					)
				);
			}, PRODUCTION_ACTION_GROUP);
		}
		if (frm.doc.production_path && frm.doc.status !== "Delivered" && can(frm, "revert_department")) {
			frm.add_custom_button(__("إرجاع لمرحلة سابقة"), () => openRevertDialog(frm), PRODUCTION_ACTION_GROUP);
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

		if (frm.doc.production_dxf && can(frm, "export_dxf")) {
			frm.add_custom_button(__("تنزيل DXF للإنتاج"), () => window.open(frm.doc.production_dxf, "_blank"), DRAWING_ACTION_GROUP);
		}
		if (!isAtDrawing(frm) || !isAssignedToCurrentUser(frm) || frm.doc.approved_plan) return;

		if (can(frm, "export_dxf")) {
			frm.add_custom_button(__("تصدير DXF للرسم"), () => {
				const exporter = frappe.almdina && frappe.almdina.export_order_dxf;
				const markExported = () => frappe.call({
					method: "almdina_erp.almdina_erp.services.shop_floor_service.mark_dxf_exported",
					args: { order_name: frm.doc.name },
				}).then(() => frm.reload_doc());
				if (exporter) return exporter(frm.doc.name).then(markExported);
				frappe.msgprint(__("تعذر تشغيل مصدر DXF الآمن."));
				return null;
			}, DRAWING_ACTION_GROUP);
		}

		const uploadCapability = frm.doc.production_dxf ? "replace_dxf" : "upload_dxf";
		if (can(frm, uploadCapability)) {
			frm.add_custom_button(
				frm.doc.production_dxf ? __("استبدال ملف DXF") : __("رفع ملف DXF"),
				() => uploadDrawingDxf(frm),
				DRAWING_ACTION_GROUP
			);
		}

		if (can(frm, "approve_dxf") && availableApprovalSources(frm).length) {
			frm.add_custom_button(__("اعتماد الرسم"), () => approveDrawing(frm), DRAWING_ACTION_GROUP);
		}
		// Print and AutoCAD DXF export live in the cutting-plan section.
	}

	function openHandoffDialog(frm, stageName) {
		frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
			args: { stage_name: stageName },
		}).then((response) => {
			const handoff = response.message || {};
			if (handoff.final_stage) {
				frappe.confirm(__("تأكيد إنهاء آخر مرحلة واعتبار الطلب جاهزًا للتسليم؟"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
						{ stage_name: stageName },
						__("الطلب جاهز للتسليم."),
						frm
					)
				);
				return;
			}
			const workers = handoff.workers || [];
			if (!workers.length) {
				frappe.msgprint(__("لا يوجد عمال متاحون للدور {0} في القسم التالي.", [handoff.operational_role || ""]));
				return;
			}
			frappe.prompt(
				[{
					fieldname: "next_assignee",
					fieldtype: "Select",
					label: `${__("العامل التالي")} — ${handoff.next_department || handoff.next_stage_type || ""}`,
					options: workers.map((worker) => ({
						label: worker.full_name && worker.full_name !== worker.name ? `${worker.full_name} — ${worker.name}` : worker.name,
						value: worker.name,
					})),
					reqd: 1,
				}],
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

	function openReassignDialog(frm, stageName, currentAssignee) {
		return frappe
			.call({
				method: "almdina_erp.almdina_erp.services.production_worker_service.get_reassignment_workers",
				args: { stage_name: stageName },
			})
			.then((response) => {
				const workers = (response.message || []).filter((worker) => worker.name !== currentAssignee);
				if (!workers.length) {
					frappe.msgprint(__("لا يوجد عامل آخر متاح لهذا القسم."));
					return;
				}
				const labels = new Map(
					workers.map((worker) => [
						`${worker.full_name || worker.name} — ${worker.name}`,
						worker.name,
					])
				);
				frappe.prompt(
					[{
						fieldname: "worker",
						fieldtype: "Select",
						label: __("العامل الجديد"),
						options: [...labels.keys()].join("\n"),
						reqd: 1,
						description: __("سيصبح العامل الجديد مسؤولًا عن بدء المرحلة وتسليمها."),
					}],
					(values) => callAction(
						"almdina_erp.almdina_erp.services.shop_floor_commands.reassign_worker",
						{ stage_name: stageName, assignee: labels.get(values.worker) },
						__("تم تغيير العامل المسؤول عن المرحلة."),
						frm
					),
					__("تغيير العامل"),
					__("إسناد")
				);
			});
	}

	function addWorkerStageButtons(frm) {
		if (frm.is_new() || !frm.doc.current_production_stage) return;
		if (!["start_assigned_stage", "handoff_assigned_stage", "reassign_worker"].some((capability) => can(frm, capability))) return;
		const documentName = frm.doc.name;
		const stageName = frm.doc.current_production_stage;
		frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_current_stage_context",
			args: { order_name: documentName },
		}).then((response) => {
			if (!frm.doc || frm.doc.name !== documentName || frm.doc.current_production_stage !== stageName) return;
			const stage = response.message || {};
			frm.__almdinaProductionRouteName = frm.doc.production_path;
			frm.__almdinaProductionRouteSteps = Array.isArray(stage.route_stages) ? stage.route_stages : [];
			renderTrackingStrip(frm);
			const stageStatus = stage.active_stage_status || "";
			const assignedTo = stage.active_stage_assigned_to || "";
			const assignedToMe = Boolean(assignedTo && assignedTo === frappe.session.user);

			if (stage.can_reassign_worker && ACTIVE_STAGE_STATUSES.has(stageStatus) && can(frm, "reassign_worker")) {
				frm.add_custom_button(
					__("تغيير العامل"),
					() => openReassignDialog(frm, stageName, assignedTo),
					PRODUCTION_ACTION_GROUP
				);
			}

			if (!assignedToMe) return;
			if (stage.can_start_stage && stageStatus === "Pending" && can(frm, "start_assigned_stage")) {
				frm.add_custom_button(__("بدء العمل"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage",
						{ stage_name: stageName },
						__("تم بدء العمل."),
						frm
					), PRODUCTION_ACTION_GROUP);
			}
			if (!stage.can_handoff_stage || !["In Progress", "Paused"].includes(stageStatus) || !can(frm, "handoff_assigned_stage")) return;
			frm.add_custom_button(__("إنهاء وإرسال"), () => {
				openHandoffDialog(frm, stageName);
			}, PRODUCTION_ACTION_GROUP);
		});
	}

	function removeProductionButtons(frm) {
		[
			"إرسال للإنتاج",
			"تم التسليم",
			"إرجاع لمرحلة سابقة",
			"بدء العمل",
			"إرسال للقسم التالي",
			"جاهزة للتسليم",
			"إنهاء وإرسال",
			"تغيير العامل",
		].forEach((label) => frm.remove_custom_button(__(label), PRODUCTION_ACTION_GROUP));
	}

	frappe.ui.form.on("Door Cutting Order", {
		refresh(frm) {
			applyShopFloorPresentation(frm);
			renderTrackingStrip(frm);
			removeProductionButtons(frm);
			addDispatchButton(frm);
			addDeliveryButtons(frm);
			addDrawingDxfButtons(frm);
			addWorkerStageButtons(frm);
		},
	});

	window.addEventListener("almdina:permissions-updated", () => {
		const frm = window.cur_frm;
		if (frm && frm.doctype === "Door Cutting Order") {
			applyShopFloorPresentation(frm);
		}
	});
})();
