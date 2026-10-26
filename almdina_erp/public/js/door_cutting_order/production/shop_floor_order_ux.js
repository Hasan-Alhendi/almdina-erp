(() => {
	"use strict";


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
                text = text.split("{" + index + "}").join(String(value));
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

	const ACTIVE_STAGE_STATUSES = new Set(["Pending", "In Progress", "Paused"]);
	const NON_REVERTABLE_ORDER_STATUSES = new Set(["Draft", "Rejected", "Delivered", "Cancelled"]);
	const PRODUCTION_ACTION_IDS = Object.freeze([
		"Send to production",
		"Delivered",
		"Return to a previous stage",
		"Start work",
		"Send to the next department",
		"Ready for delivery",
		"Finish and send",
		"Change worker",
	]);
	const LEGACY_PRODUCTION_ACTION_LABELS = Object.freeze([
		"إرسال للإنتاج",
		"تم التسليم",
		"إرجاع لمرحلة سابقة",
		"بدء العمل",
		"إرسال للقسم التالي",
		"جاهزة للتسليم",
		"إنهاء وإرسال",
		"تغيير العامل",
		"رجوع لصالة الإنتاج",
		"العودة إلى الطلبات",
	]);

	function drawingActionGroup() {
		return translate("Drawing / DXF");
	}

	function productionActionGroup() {
		return translate("Production floor");
	}

	function matchesProductionLabel(label, messageId) {
		return label === messageId || label === translate(messageId);
	}

	function isOwnedProductionLabel(label) {
		if (LEGACY_PRODUCTION_ACTION_LABELS.includes(label)) return true;
		return PRODUCTION_ACTION_IDS.some((messageId) => matchesProductionLabel(label, messageId));
	}

	function permissionContext() {
		return window.AlmdinaPermissions || null;
	}

	function documentContext() {
		return window.AlmdinaDocumentContext || null;
	}

	function capture(frm) {
		const context = documentContext();
		if (context && typeof context.capture === "function") {
			return context.capture(frm);
		}
		return `${frm.doctype || ""}::${frm.doc && frm.doc.name || "__new__"}`;
	}

	function isCurrent(frm, identity) {
		const context = documentContext();
		if (context && typeof context.isCurrent === "function") {
			return context.isCurrent(frm, identity);
		}
		return Boolean(window.cur_frm === frm && capture(frm) === identity);
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

	function canOperateCurrentStage(stage) {
		if (stage && stage.actor_can_operate_current_stage !== undefined) {
			return Boolean(stage.actor_can_operate_current_stage);
		}
		const assignedTo = stage && stage.active_stage_assigned_to;
		return Boolean(assignedTo && assignedTo === frappe.session.user);
	}

	function canShowStartAction(frm, stage) {
		return Boolean(
			canOperateCurrentStage(stage)
			&& stage.can_start_stage
			&& stage.active_stage_status === "Pending"
			&& can(frm, "start_assigned_stage")
		);
	}

	function canShowHandoffAction(frm, stage) {
		// Visibility follows the server decision. Direct handoff from Pending is
		// allowed when the worker has handoff without start; do not re-encode
		// In Progress/Paused here or that case stays hidden.
		return Boolean(
			canOperateCurrentStage(stage)
			&& stage.can_handoff_stage
			&& can(frm, "handoff_assigned_stage")
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

	function grantedCapability(frm, capability) {
		const context = permissionContext();
		if (context && typeof context.can === "function") {
			return context.can(capability) === true;
		}
		return can(frm, capability);
	}

	function canKeepViewingAfterLeavingAssignment(frm) {
		return Boolean(
			grantedCapability(frm, "view_all_orders")
			|| grantedCapability(frm, "view_shop_floor_history")
		);
	}

	function productionActionLeavesCurrentView(method) {
		return (
			method === "almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order"
			|| method === "almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next"
			|| method === "almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered"
		);
	}

	function shouldReturnToOrderList(method, frm) {
		return productionActionLeavesCurrentView(method)
			&& !canKeepViewingAfterLeavingAssignment(frm);
	}

	function returnToOrderList() {
		if (typeof frappe.set_route === "function") {
			return Promise.resolve(frappe.set_route("List", "Door Cutting Order"));
		}
		return Promise.resolve();
	}

	function callAction(method, args, successMessage, frm) {
		const documentName = frm && frm.doc ? frm.doc.name : null;
		return frappe
			.call({
				method,
				args,
				freeze: true,
				freeze_message: translate("Running the operation..."),
			})
			.then((response) => {
				if (successMessage) {
					frappe.show_alert({ message: successMessage, indicator: "green" });
				}
				if (frm && frm.doc && frm.doc.name === documentName) {
					if (shouldReturnToOrderList(method, frm)) {
						return returnToOrderList().then(() => response.message);
					}
					return frm.reload_doc().then(() => response.message);
				}
				return response.message;
			});
	}

	const STATUS_LABELS = {
		Draft: "Draft",
		"Pending Review": "Pending Review",
		Approved: "Approved",
		"At Sharyoun": "At Sharyoun",
		"At Drawing": "At Drawing",
		"At CNC": "At CNC",
		"At Sanding": "At Sanding",
		"Ready for Delivery": "Ready for delivery",
		Delivered: "Delivered",
		Completed: "Completed",
		Rejected: "Rejected",
		"On Hold": "On Hold",
		Cancelled: "Cancelled",
	};

	const STATUS_COLORS = {
		Draft: "#b45309",
		"Pending Review": "#b45309",
		Approved: "#172033",
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
		return translate(STATUS_LABELS[status] || status || "");
	}

	function looksLikeEmail(value) {
		return String(value || "").includes("@");
	}

	function workerDisplayName(worker) {
		const id = String((worker && worker.name) || "").trim();
		const fullName = String((worker && worker.full_name) || "").trim();
		if (fullName && fullName !== id) return fullName;
		return id;
	}

	function workerSelectOptions(workers) {
		return (workers || []).map((worker) => ({
			label: workerDisplayName(worker),
			value: worker.name,
		}));
	}

	function userFullNameFromBoot(userId) {
		const id = String(userId || "").trim();
		if (!id) return "";
		let name = "";
		if (typeof frappe.user_info === "function") {
			const info = frappe.user_info(id) || {};
			name = String(info.fullname || info.full_name || "").trim();
		}
		if (!name || name === id || looksLikeEmail(name)) return "";
		return name;
	}

	function currentAssigneeDisplayName(userId) {
		const id = String(userId || "").trim();
		if (!id) return "-";
		return userFullNameFromBoot(id) || id;
	}

	function rememberUserFullName(userId, fullName) {
		const id = String(userId || "").trim();
		const name = String(fullName || "").trim();
		if (!id || !name || name === id || looksLikeEmail(name)) return false;
		const entry = {};
		entry[id] = { fullname: name, email: id };
		if (typeof frappe.update_user_info === "function") {
			frappe.update_user_info(entry);
			return true;
		}
		frappe.boot = frappe.boot || {};
		frappe.boot.user_info = Object.assign({}, frappe.boot.user_info || {}, entry);
		return true;
	}

	function hydrateCurrentAssigneeName(frm) {
		const id = String(frm && frm.doc && frm.doc.current_assignee || "").trim();
		if (!id || userFullNameFromBoot(id)) return;
		if (!frappe.db || typeof frappe.db.get_value !== "function") return;
		if (frm.__almdinaAssigneeNameRequest === id) return;
		frm.__almdinaAssigneeNameRequest = id;
		frappe.db.get_value("User", id, "full_name")
			.then((response) => {
				const fullName = String(
					(response && response.message && response.message.full_name)
					|| (response && response.full_name)
					|| ""
				).trim();
				if (!rememberUserFullName(id, fullName)) return;
				if (!frm.doc || String(frm.doc.current_assignee || "").trim() !== id) return;
				const field = frm.fields_dict && frm.fields_dict.operator_status_strip;
				const root = field && field.$wrapper && typeof field.$wrapper.get === "function"
					? field.$wrapper.get(0)
					: null;
				if (root) root._almdinaTrackingStripHtml = "";
				renderTrackingStrip(frm);
			})
			.catch(() => {
				if (frm.__almdinaAssigneeNameRequest === id) {
					frm.__almdinaAssigneeNameRequest = null;
				}
			});
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
		return `<div class="dco-order-tracking-strip__path" role="list" aria-label="${frappe.utils.escape_html(String(translate("Order route")))}">${steps
			.map((step, index) => {
				const done = delivered || index < currentIndex;
				const active = !delivered && index === currentIndex;
				const state = done ? "done" : active ? "current" : "upcoming";
				return (
					`<span class="dco-order-tracking-strip__step is-${state}" role="listitem"${active ? ' aria-current="step"' : ""}>`
					+ `${done ? "✓ " : ""}${frappe.utils.escape_html(String(step))}`
					+ `</span>`
				);
			})
			.join('<span class="dco-order-tracking-strip__path-sep" aria-hidden="true">‹</span>')}</div>`;
	}

	function renderTrackingStrip(frm) {
		const field = frm.fields_dict.operator_status_strip;
		if (!field || !field.$wrapper) return;
		if (frm.is_new()) {
			if (field.$wrapper.children().length) field.$wrapper.empty();
			return;
		}
		const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
		const status = frm.doc.status || "Draft";
		const color = STATUS_COLORS[status] || "#374151";
		const factItem = (label, value, kind = "value") => {
			const text = String(value ?? "").trim() || "-";
			const empty = text === "-";
			return (
				`<div class="dco-order-tracking-strip__item${empty ? " is-empty" : ""}">`
				+ `<span class="dco-order-tracking-strip__label">${escape(label)}</span>`
				+ `<span class="dco-order-tracking-strip__${kind}">${escape(text)}</span>`
				+ `</div>`
			);
		};
		const pathHtml = status === "Draft" ? "" : renderProgressSteps(frm);
		const html = `
			<div class="frappe-card dco-order-tracking-strip" style="--dco-status-color:${escape(color)}" data-order-status="${escape(status)}">
				<div class="dco-order-tracking-strip__layout">
					<div class="dco-order-tracking-strip__lead">
						${factItem(translate("Order status"), statusLabel(status), "badge")}
						${pathHtml}
					</div>
					<div class="dco-order-tracking-strip__facts">
						${factItem(translate("Worker"), currentAssigneeDisplayName(frm.doc.current_assignee))}
						${factItem(translate("Department status"), frm.doc.department_status || "-")}
					</div>
				</div>
			</div>`;
		const root = field.$wrapper.get(0);
		if (!(root && root._almdinaTrackingStripHtml === html && field.$wrapper.children().length)) {
			field.$wrapper.html(html);
			if (root) root._almdinaTrackingStripHtml = html;
		}
		hydrateCurrentAssigneeName(frm);
	}

	function applyShopFloorPresentation(frm) {
		// Every role uses the canonical Door Cutting Order form.  Permissions may
		// hide individual tabs/actions, but a profile must never replace the form
		// with a different layout.  Restore metadata visibility left by older page
		// visits before the focused permission modules apply their own rules.
		const original = frm.__almdinaShopFloorHiddenState;
		if (original) {
			Object.entries(original).forEach(([fieldname, hidden]) => {
				frm.set_df_property(fieldname, "hidden", hidden ? 1 : 0);
			});
			frm.__almdinaShopFloorHiddenState = null;
		}

		// RevisionUX is the single owner of the primary Save/Edit action and of
		// the document edit session. A production-profile renderer must never
		// call enable_save()/disable_save(), otherwise Frappe alternates the
		// primary label while permission requests settle.

		if (!isShopFloorProfile(frm)) return false;
		frm.remove_custom_button(translate("Back to the shop floor"));
		frm.remove_custom_button(translate("Back to orders"));
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
					frappe.msgprint(translate("No production route is enabled. Create a route from master data first."));
					return;
				}
				const pathOptions = paths.map((path) => ({
					label: `${path.label} · ${path.stage_count || 0} ${translate("Stages")}`,
					value: path.value,
				}));
				const workerOptions = (path) => workerSelectOptions(workers[path] || []);
				const routePreview = (pathName) => {
					const route = paths.find((row) => row.value === pathName) || paths[0];
					const stages = (route.stages || []).map((stage, index) => `
						<span title="${frappe.utils.escape_html(stage.operational_role || "")}" style="display:inline-flex;flex-direction:column;align-items:flex-start;gap:2px;padding:7px 10px;border-radius:12px;background:var(--subtle-fg,#f3f5f7);font-size:12px;font-weight:700">
							<span>${index + 1}. ${frappe.utils.escape_html(stage.department || stage.stage_type)}</span>
							<small style="font-weight:500;color:var(--text-muted,#667085)">${frappe.utils.escape_html(stage.operational_role || "")}</small>
						</span>`).join('<span style="color:var(--text-muted,#98a2b3)">←</span>');
					return `<div style="direction:${uiDirection()};padding:11px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;background:var(--fg-color,#fff)">
						<div style="font-weight:800;margin-bottom:8px">${frappe.utils.escape_html(route.label || route.value)}</div>
						<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${stages}</div>
					</div>`;
				};
				const firstPath = paths.some((path) => path.value === payload.default_path)
					? payload.default_path
					: paths[0].value;
				const firstWorkers = workerOptions(firstPath);
				const dialog = new frappe.ui.Dialog({
					title: translate("Send to production"),
					size: "large",
					fields: [
						{
							fieldname: "path",
							fieldtype: "Select",
							label: translate("Route"),
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
							label: translate("Worker responsible for the first stage"),
							options: firstWorkers,
							default: firstWorkers[0] ? firstWorkers[0].value : "",
							reqd: 1,
						},
					],
					primary_action_label: translate("Send"),
					primary_action(values) {
						dialog.hide();
						callAction(
							"almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order",
							{ order_name: frm.doc.name, path: values.path, assignee: values.assignee },
							translate("The order was sent to production."),
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

	const DISPATCHABLE_STATUSES = new Set([
		"Draft",
		"Rejected",
		"Pending Review",
		"Approved",
	]);

	function addDispatchButton(frm) {
		if (frm.is_new() || !can(frm, "dispatch_order")) return;
		// Review/approve were retired: dispatch opens from draft (and leftovers).
		if (
			!DISPATCHABLE_STATUSES.has(frm.doc.status || "Draft")
			|| frm.doc.production_path
			|| frm.doc.current_production_stage
		) {
			return;
		}
		// Standalone toolbar button — not nested under «صالة الإنتاج».
		// Keep the Frappe button reference; never re-find by visible label.
		const button = frm.add_custom_button(translate("Send to production"), () => openDispatchDialog(frm));
		if (button && typeof button.addClass === "function") {
			button.addClass("dco-dispatch-toolbar-button");
		}
	}

	function revertTargetsKey(frm) {
		if (!frm || !frm.doc) return "";
		return [
			frm.doc.name || "",
			frm.doc.status || "",
			frm.doc.production_path || "",
			frm.doc.current_production_stage || "",
		].join("::");
	}

	function canCheckRevertTargets(frm) {
		if (!frm || !frm.doc || frm.is_new() || !can(frm, "revert_department")) return false;
		const status = String(frm.doc.status || "Draft");
		return Boolean(
			!NON_REVERTABLE_ORDER_STATUSES.has(status)
			&& frm.doc.production_path
			&& frm.doc.current_production_stage
		);
	}

	function ensureRevertTargets(frm) {
		const key = revertTargetsKey(frm);
		if (!canCheckRevertTargets(frm)) {
			frm.__almdinaRevertTargetsKey = key;
			frm.__almdinaRevertTargets = [];
			return Promise.resolve([]);
		}
		if (
			frm.__almdinaRevertTargetsKey === key
			&& Array.isArray(frm.__almdinaRevertTargets)
		) {
			return Promise.resolve(frm.__almdinaRevertTargets);
		}
		if (
			frm.__almdinaRevertTargetsPromise
			&& frm.__almdinaRevertTargetsPromiseKey === key
		) {
			return frm.__almdinaRevertTargetsPromise;
		}

		const identity = capture(frm);
		const request = Promise.resolve(frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_service.get_revert_targets",
			args: { order_name: frm.doc.name },
		})).then((response) => {
			if (!isCurrent(frm, identity) || revertTargetsKey(frm) !== key) return [];
			const rows = Array.isArray(response.message) ? response.message : [];
			frm.__almdinaRevertTargetsKey = key;
			frm.__almdinaRevertTargets = rows;
			return rows;
		}).catch((error) => {
			if (isCurrent(frm, identity) && revertTargetsKey(frm) === key) {
				console.error("Failed to load previous production stages", error);
				frm.__almdinaRevertTargetsKey = key;
				frm.__almdinaRevertTargets = [];
			}
			return [];
		}).finally(() => {
			if (frm.__almdinaRevertTargetsPromise === request) {
				frm.__almdinaRevertTargetsPromise = null;
				frm.__almdinaRevertTargetsPromiseKey = null;
			}
		});
		frm.__almdinaRevertTargetsPromiseKey = key;
		frm.__almdinaRevertTargetsPromise = request;
		return request;
	}

	function addRevertButton(frm, generation) {
		return ensureRevertTargets(frm).then((rows) => {
			const current = isCurrent(frm, capture(frm))
				&& frm.__almdinaRevertButtonGeneration === generation;
			if (current && rows.length) {
				// Standalone toolbar button — rendered only after the server confirms
				// that at least one earlier stage really exists.
				frm.add_custom_button(translate("Return to a previous stage"), () => openRevertDialog(frm));
			}
			if (current) {
				const owner = documentContext();
				if (owner && typeof owner.settleSurfaces === "function") {
					owner.settleSurfaces(frm, 0);
				}
			}
			return rows;
		});
	}

	function addDeliveryButtons(frm) {
		if (frm.is_new()) return;
		const deliveryContext = frm.__almdina_stage_context || {};
		const serverAllowsDelivery = Boolean(
			deliveryContext.can_mark_delivered
			|| (
				deliveryContext.production_actions
				&& deliveryContext.production_actions.mark_delivered
				&& deliveryContext.production_actions.mark_delivered.allowed
			)
		);
		if (
			(serverAllowsDelivery || frm.doc.status === "Ready for Delivery")
			&& can(frm, "mark_delivered")
		) {
			frm.add_custom_button(translate("Delivered"), () => {
				frappe.confirm(translate("Confirm delivery of the order to the customer?"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered",
						{ order_name: frm.doc.name },
						translate("Delivery was recorded."),
						frm
					)
				);
			}, productionActionGroup());
		}
	}

	function showRevertDialog(frm, rows) {
		const labels = new Map(rows.map((row) => [row.label || row.stage_type, row.stage_type]));
		frappe.prompt(
			[{ fieldname: "target", fieldtype: "Select", label: translate("Stage"), options: [...labels.keys()].join("\n"), reqd: 1 }],
			(values) => callAction(
				"almdina_erp.almdina_erp.services.shop_floor_service.revert_department",
				{ order_name: frm.doc.name, target_stage_type: labels.get(values.target) },
				translate("The order was returned to the selected stage."),
				frm
			),
			translate("Return to a previous stage"),
			translate("Revert")
		);
	}

	function openRevertDialog(frm) {
		return ensureRevertTargets(frm).then((rows) => {
			if (!rows.length) {
				frappe.msgprint(translate("There are no stages that can be reverted to."));
				return;
			}
			showRevertDialog(frm, rows);
		});
	}

	function availableApprovalSources(frm) {
		const sources = [];
		if (frm.doc.system_plan_json || frm.doc.cutting_plan_json) {
			sources.push({ value: "System", label: translate("System plan") });
		}
		if (frm.doc.custom_plan_json && frm.doc.production_dxf) {
			sources.push({ value: "Custom", label: translate("Uploaded DXF plan") });
		}
		return sources;
	}

	function approveDrawing(frm) {
		const sources = availableApprovalSources(frm);
		if (!sources.length) {
			frappe.msgprint(translate("There is no valid plan to approve."));
			return;
		}
		const submit = (source) =>
			callAction(
				"almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf",
				{ order_name: frm.doc.name, plan_source: source },
				translate("The drawing was approved and the approved designer was recorded."),
				frm
			);
		if (sources.length === 1) {
			frappe.confirm(
				translate("{0} will be fixed as the final production copy under your name. Do you want to continue?", [sources[0].label]),
				() => submit(sources[0].value)
			);
			return;
		}
		const labels = new Map(sources.map((source) => [source.label, source.value]));
		frappe.prompt(
			[{
				fieldname: "source",
				fieldtype: "Select",
				label: translate("Approved production plan"),
				options: [...labels.keys()].join("\n"),
				reqd: 1,
				description: translate("Choose the plan you reviewed. Your approval will be recorded under the current user."),
			}],
			(values) => submit(labels.get(values.source)),
			translate("Approve the drawing"),
			translate("Approve for production")
		);
	}

	function uploadDrawingDxf(frm) {
		if (frm.is_new()) {
			frappe.msgprint(translate("Save the order before uploading a DXF file."));
			return;
		}
		const context = documentContext();
		if (context && typeof context.canMutateCurrentStage === "function" && !context.canMutateCurrentStage(frm)) {
			const reason = typeof context.stageMutationBlockReason === "function"
				? context.stageMutationBlockReason(frm)
				: "";
			frappe.msgprint(translate(reason || "You can view this order only. Its current stage is outside your operational roles."));
			return;
		}
		const replacing = Boolean(frm.doc.production_dxf);
		const capability = replacing ? "replace_dxf" : "upload_dxf";
		if (!can(frm, capability)) {
			frappe.msgprint(translate("You do not have permission to upload the cutting plan as a DXF file."));
			return;
		}
		const core = frappe.almdina && frappe.almdina.__uploadProductionDxfCore;
		if (typeof core === "function") {
			return core(frm);
		}
		const ui = window.AlmdinaUi;
		if (!ui || typeof ui.fileUploader !== "function") {
			frappe.msgprint(translate("Could not open DXF upload."));
			return null;
		}
		return ui.fileUploader({
			preset: "securePrivate",
			restrictions: { allowed_file_types: [".dxf"], max_file_size: 10 * 1024 * 1024 },
			on_success(file) {
				callAction(
					"almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf",
					{ order_name: frm.doc.name, file_url: file.file_url },
					replacing ? translate("The DXF file was replaced and validated.") : translate("The DXF file was uploaded and validated."),
					frm
				);
			},
		});
	}

	function removeDrawingDxfToolbarButtons(frm) {
		if (frm.is_new()) return;

		[
			translate("Export DXF for drawing"),
			translate("Export DXF for AutoCAD"),
			translate("Export DXF"),
			translate("Print cutting plan"),
			translate("Download production DXF"),
			translate("Upload a DXF plan"),
			translate("Replace the uploaded plan"),
			translate("Approve the drawing"),
			translate("Re-approve the drawing"),
		].forEach(label => {
			frm.remove_custom_button(label);
			frm.remove_custom_button(label, drawingActionGroup());
		});
		// Drawing/DXF actions belong in the form sections, not the page toolbar.
	}

	function openHandoffDialog(frm, stageName) {
		frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
			args: { stage_name: stageName },
		}).then((response) => {
			const handoff = response.message || {};
			if (handoff.final_stage) {
				frappe.confirm(translate("Confirm finishing the last stage and marking the order ready for delivery?"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
						{ stage_name: stageName },
						translate("The order is ready for delivery."),
						frm
					)
				);
				return;
			}
			const workers = handoff.workers || [];
			if (!workers.length) {
				frappe.msgprint(translate("No workers are available for role {0} in the next department.", [handoff.operational_role || ""]));
				return;
			}
			frappe.prompt(
				[{
					fieldname: "next_assignee",
					fieldtype: "Select",
					label: `${translate("Next worker")} — ${handoff.next_department || handoff.next_stage_type || ""}`,
					options: workerSelectOptions(workers),
					reqd: 1,
				}],
				(values) => callAction(
					"almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next",
					{ stage_name: stageName, next_assignee: values.next_assignee },
					translate("The order was sent."),
					frm
				),
				translate("Send to the next department"),
				translate("Send")
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
					frappe.msgprint(translate("No other worker is available for this department."));
					return;
				}
				frappe.prompt(
					[{
						fieldname: "worker",
						fieldtype: "Select",
						label: translate("New worker"),
						options: workerSelectOptions(workers),
						reqd: 1,
						description: translate("The new worker will be responsible for starting and handing off the stage."),
					}],
					(values) => callAction(
						"almdina_erp.almdina_erp.services.shop_floor_commands.reassign_worker",
						{ stage_name: stageName, assignee: values.worker },
						translate("The worker responsible for the stage was changed."),
						frm
					),
					translate("Change worker"),
					translate("Assign")
				);
			});
	}

	function productionActionsKey(frm) {
		if (!frm || !frm.doc) return "";
		return [
			frm.doc.name || "",
			frm.doc.current_production_stage || "",
			frm.doc.status || "",
			frm.doc.production_path || "",
		].join("::");
	}

	function markProductionActionsRendered(frm) {
		frm.__almdinaProductionActionsKey = productionActionsKey(frm);
	}

	function renderedButtonLabels(frm) {
		const labels = new Set();
		const root = frm && frm.page && frm.page.wrapper;
		const node = root && (root.nodeType ? root : root[0]);
		const hasRenderedToolbar = Boolean(node && typeof node.querySelectorAll === "function");
		if (hasRenderedToolbar) {
			node.querySelectorAll(
				".custom-actions button, .custom-actions a, .page-actions button, .page-actions a, .page-actions .dropdown-item"
			).forEach((button) => {
				const label = String(button.textContent || "").replace(/\s+/g, " ").trim();
				if (label) labels.add(label);
			});
		}
		// Test/minimal form adapters may not expose a DOM. In the real desk, trust
		// the rendered toolbar only: Frappe can leave custom_buttons cached while
		// rebuilding and temporarily removing the actual buttons.
		if (!hasRenderedToolbar) {
			Object.keys((frm && frm.custom_buttons) || {}).forEach(label => labels.add(String(label).trim()));
		}
		return labels;
	}

	function expectedProductionActionLabels(frm) {
		if (!frm || !frm.doc || frm.is_new()) return [];
		const labels = [];
		const status = frm.doc.status || "Draft";
		if (
			can(frm, "dispatch_order")
			&& DISPATCHABLE_STATUSES.has(status)
			&& !frm.doc.production_path
			&& !frm.doc.current_production_stage
		) labels.push(translate("Send to production"));
		const deliveryContext = frm.__almdina_stage_context || {};
		const serverAllowsDelivery = Boolean(
			deliveryContext.can_mark_delivered
			|| (
				deliveryContext.production_actions
				&& deliveryContext.production_actions.mark_delivered
				&& deliveryContext.production_actions.mark_delivered.allowed
			)
		);
		if (
			(serverAllowsDelivery || status === "Ready for Delivery")
			&& can(frm, "mark_delivered")
		) {
			labels.push(translate("Delivered"));
		}
		if (
			canCheckRevertTargets(frm)
			&& frm.__almdinaRevertTargetsKey === revertTargetsKey(frm)
			&& Array.isArray(frm.__almdinaRevertTargets)
			&& frm.__almdinaRevertTargets.length
		) {
			labels.push(translate("Return to a previous stage"));
		}

		const stage = frm.__almdina_stage_context || {};
		const stageStatus = stage.active_stage_status || "";
		if (
			stage.can_reassign_worker
			&& ACTIVE_STAGE_STATUSES.has(stageStatus)
			&& can(frm, "reassign_worker")
		) labels.push(translate("Change worker"));
		if (canShowStartAction(frm, stage)) {
			labels.push(translate("Start work"));
		}
		if (canShowHandoffAction(frm, stage)) {
			labels.push(translate("Finish and send"));
		}
		return labels;
	}

	function productionActionsReady(frm) {
		if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return true;
		if (
			frm.__almdinaRevertTargetsPromise
			&& frm.__almdinaRevertTargetsPromiseKey === revertTargetsKey(frm)
		) return false;
		if (frm.__almdinaProductionActionsKey !== productionActionsKey(frm)) return false;
		const expected = new Set(expectedProductionActionLabels(frm));
		const rendered = renderedButtonLabels(frm);
		const renderedOwned = [...rendered].filter(label => isOwnedProductionLabel(label));
		return (
			[...expected].every(label => rendered.has(label))
			&& renderedOwned.every(label => expected.has(label))
		);
	}

	function capabilitiesResolved() {
		const permissions = permissionContext();
		return Boolean(
			permissions
			&& typeof permissions.version === "function"
			&& permissions.version() > 0
		);
	}

	function addWorkerStageButtons(frm) {
		if (frm.is_new() || !frm.doc.current_production_stage) {
			markProductionActionsRendered(frm);
			return;
		}
		if (!["start_assigned_stage", "handoff_assigned_stage", "reassign_worker"].some((capability) => can(frm, capability))) {
			// An empty toolbar is only a final answer once the capability matrix
			// has actually arrived; otherwise leave the surface pending so the
			// settle loop retries after it loads.
			if (capabilitiesResolved()) markProductionActionsRendered(frm);
			return;
		}
		if (
			frm.__almdinaProductionActionsPromise
			&& isCurrent(frm, frm.__almdinaProductionActionsContext)
		) {
			// The caller already cleared the action surface, so the in-flight pass
			// would leave it empty. Reconcile again once it settles instead of
			// dropping this request.
			const inFlight = frm.__almdinaProductionActionsPromise;
			return inFlight.then(() => {
				if (frm.__almdinaProductionActionsPromise === inFlight) return false;
				if (!isCurrent(frm, capture(frm))) return false;
				return reconcileProductionActions(frm);
			});
		}
		const identity = capture(frm);
		const documentName = frm.doc.name;
		const stageName = frm.doc.current_production_stage;
		const context = documentContext();
		const loader = context && typeof context.ensureStageContext === "function"
			? context.ensureStageContext(frm)
			: Promise.resolve(frappe.call({
				method: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_current_stage_context",
				args: { order_name: documentName },
			}).then((response) => {
				if (context && typeof context.isCurrent === "function" && !context.isCurrent(frm, identity)) {
					return false;
				}
				const stage = response.message || {};
				frm.__almdina_stage_type = stage.active_stage_type || null;
				frm.__almdina_actor_holds_stage_role = Boolean(stage.actor_holds_operational_role);
				frm.__almdina_stage_operational_role = stage.active_stage_operational_role || null;
				frm.__almdina_stage_context = stage;
				return true;
			}));
		const actionPromise = Promise.resolve(loader).then((ready) => {
			if (
				!ready
				|| !isCurrent(frm, identity)
				|| !frm.doc
				|| frm.doc.name !== documentName
				|| frm.doc.current_production_stage !== stageName
			) return;
			markProductionActionsRendered(frm);
			const stage = frm.__almdina_stage_context || {};
			frm.__almdinaProductionRouteName = frm.doc.production_path;
			frm.__almdinaProductionRouteSteps = Array.isArray(stage.route_stages) ? stage.route_stages : [];
			renderTrackingStrip(frm);
			const stageStatus = stage.active_stage_status || "";
			const assignedTo = stage.active_stage_assigned_to || "";

			if (stage.can_reassign_worker && ACTIVE_STAGE_STATUSES.has(stageStatus) && can(frm, "reassign_worker")) {
				frm.add_custom_button(
					translate("Change worker"),
					() => openReassignDialog(frm, stageName, assignedTo)
				);
			}

			if (!canOperateCurrentStage(stage)) return;
			if (canShowStartAction(frm, stage)) {
				// The worker's current stage action is intentionally top-level: it is
				// the primary next step, not a category that needs another tap.
				frm.add_custom_button(translate("Start work"), () =>
					callAction(
						"almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage",
						{ stage_name: stageName },
						translate("Work has started."),
						frm
					));
			}
			if (!canShowHandoffAction(frm, stage)) return;
			// Keep the handoff dialog and server authorization unchanged; only the
			// toolbar placement is direct so the worker reaches it in one tap.
			frm.add_custom_button(translate("Finish and send"), () => {
				openHandoffDialog(frm, stageName);
			});
		}).catch((error) => {
			if (isCurrent(frm, identity)) {
				console.error("Failed to load production actions", error);
			}
		}).finally(() => {
			if (frm.__almdinaProductionActionsPromise === actionPromise) {
				frm.__almdinaProductionActionsPromise = null;
				frm.__almdinaProductionActionsContext = null;
			}
		});
		frm.__almdinaProductionActionsContext = identity;
		frm.__almdinaProductionActionsPromise = actionPromise;
		return actionPromise;
	}

	function removeProductionButtons(frm) {
		const group = productionActionGroup();
		PRODUCTION_ACTION_IDS.forEach((messageId) => {
			const localized = translate(messageId);
			frm.remove_custom_button(messageId, group);
			frm.remove_custom_button(localized, group);
			frm.remove_custom_button(messageId);
			frm.remove_custom_button(localized);
		});
		LEGACY_PRODUCTION_ACTION_LABELS.forEach((label) => {
			frm.remove_custom_button(label, group);
			frm.remove_custom_button(label);
		});
	}

	function reconcileProductionActions(frm) {
		if (!frm || frm.doctype !== "Door Cutting Order" || !frm.doc) return false;
		if (
			frm.__almdinaProductionActionsKey === productionActionsKey(frm)
			&& productionActionsReady(frm)
		) return true;

		frm.__almdinaProductionActionsKey = null;
		frm.__almdinaRevertButtonGeneration = Number(frm.__almdinaRevertButtonGeneration || 0) + 1;
		const revertGeneration = frm.__almdinaRevertButtonGeneration;
		removeProductionButtons(frm);
		addDispatchButton(frm);
		addRevertButton(frm, revertGeneration);
		addDeliveryButtons(frm);
		addWorkerStageButtons(frm);
		return true;
	}

	function recoverProductionActions(frm) {
		if (!frm || frm.doctype !== "Door Cutting Order" || !frm.doc) {
			return Promise.resolve(false);
		}
		if (
			frm.__almdinaProductionRecoveryPromise
			&& isCurrent(frm, frm.__almdinaProductionRecoveryContext)
		) {
			return frm.__almdinaProductionRecoveryPromise;
		}

		const identity = capture(frm);
		// PermissionRefreshUX is the sole owner of the permission request. This
		// recovery pass only reconciles the actions against the current snapshot.
		const recoveryPromise = Promise.resolve()
			.then(() => isCurrent(frm, identity) && reconcileProductionActions(frm))
			.finally(() => {
				if (frm.__almdinaProductionRecoveryPromise === recoveryPromise) {
					frm.__almdinaProductionRecoveryPromise = null;
					frm.__almdinaProductionRecoveryContext = null;
				}
			});

		frm.__almdinaProductionRecoveryContext = identity;
		frm.__almdinaProductionRecoveryPromise = recoveryPromise;
		return recoveryPromise;
	}

	frappe.ui.form.on("Door Cutting Order", {
		onload_post_render(frm) {
			reconcileProductionActions(frm);
		},
		refresh(frm) {
			applyShopFloorPresentation(frm);
			renderTrackingStrip(frm);
			reconcileProductionActions(frm);
			removeDrawingDxfToolbarButtons(frm);
		},
	});

	window.addEventListener("almdina:permissions-updated", () => {
		const frm = window.cur_frm;
		if (frm && frm.doctype === "Door Cutting Order") {
			applyShopFloorPresentation(frm);
			renderTrackingStrip(frm);
			reconcileProductionActions(frm);
		}
	});

	frappe.almdina = frappe.almdina || {};
	frappe.almdina.upload_production_dxf = uploadDrawingDxf;
	window.AlmdinaShopFloorOrderUX = Object.freeze({
		applyShopFloorPresentation,
		expectedProductionActionLabels,
		productionActionsReady,
		reconcileProductionActions,
		recoverProductionActions,
		renderTrackingStrip,
	});

	const surfaceOwner = documentContext();
	if (surfaceOwner && typeof surfaceOwner.registerSurface === "function") {
		surfaceOwner.registerSurface("production-actions", {
			isReady(frm) {
				return productionActionsReady(frm);
			},
			recover(frm) { return reconcileProductionActions(frm); },
		});
	}

	window.setTimeout(() => {
		const frm = window.cur_frm;
		if (frm && frm.doctype === "Door Cutting Order") {
			reconcileProductionActions(frm);
		}
	}, 0);
})();
