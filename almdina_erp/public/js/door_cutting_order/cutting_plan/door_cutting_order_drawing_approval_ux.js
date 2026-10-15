(() => {
	"use strict";

	const ACTION_GROUP_ID = "Drawing / DXF";
	const APPROVE_LABEL_ID = "Approve drawing";
	const REAPPROVE_LABEL_ID = "Re-approve drawing";
	// Compatibility: historical department value and toolbar labels used only for removal.
	const DRAWING_DEPARTMENT = "رسم";
	const LEGACY_ACTION_GROUP = "الرسم / DXF";
	const LEGACY_APPROVAL_LABELS = Object.freeze(["اعتماد الرسم", "إعادة اعتماد الرسم"]);

	function translate(message, replacements) {
		const locale = window.AlmdinaLocale;
		if (locale && typeof locale.translate === "function") {
			return locale.translate(message, replacements);
		}
		if (typeof __ === "function") {
			return replacements === undefined ? __(message) : __(message, replacements);
		}
		return String(message == null ? "" : message);
	}

	function canApprove(frm) {
		const permissions = window.AlmdinaPermissions;
		return Boolean(
			permissions &&
			(
				typeof permissions.canDocument === "function"
					? permissions.canDocument(frm, "approve_dxf")
					: permissions.can("approve_dxf")
			)
		);
	}

	function isAtDrawing(frm) {
		return Boolean(
			frm &&
			(
				frm.doc.status === "At Drawing" ||
				(
					frm.doc.production_path === "Drawing" &&
					frm.doc.current_department === DRAWING_DEPARTMENT
				)
			)
		);
	}

	function parseJson(raw) {
		if (!raw) return null;
		if (typeof raw === "object") return raw;
		try {
			return JSON.parse(raw);
		} catch (error) {
			return null;
		}
	}

	function hasPlan(raw) {
		const plan = parseJson(raw);
		return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
	}

	function approvalSources(frm) {
		const sources = [];
		if (hasPlan(frm.doc.system_plan_json) || hasPlan(frm.doc.cutting_plan_json)) {
			sources.push({ value: "System", label: translate("System plan") });
		}
		if (hasPlan(frm.doc.custom_plan_json) && frm.doc.production_dxf) {
			sources.push({ value: "Custom", label: translate("Plan uploaded from DXF") });
		}
		return sources;
	}

	function submitApproval(frm, source) {
		return frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf",
			args: { order_name: frm.doc.name, plan_source: source },
			freeze: true,
			freeze_message: translate("Approving the drawing plan..."),
		}).then((response) => {
			const result = response.message || {};
			frappe.show_alert({
				message: result.was_previously_approved
					? translate("The drawing approval was updated and replaced the previous approved plan.")
					: translate("The drawing was approved for production."),
				indicator: "green",
			}, 6);
			return frm.reload_doc();
		});
	}

	function chooseSource(frm) {
		const sources = approvalSources(frm);
		if (!sources.length) {
			frappe.msgprint(translate("There is no valid plan to approve."));
			return;
		}
		if (sources.length === 1) {
			submitApproval(frm, sources[0].value);
			return;
		}
		const labels = new Map(sources.map((source) => [source.label, source.value]));
		frappe.prompt(
			[{
				fieldname: "source",
				fieldtype: "Select",
				label: translate("Plan approved for production"),
				options: [...labels.keys()].join("\n"),
				reqd: 1,
				description: translate("Choose the final version you want to approve for production."),
			}],
			(values) => submitApproval(frm, labels.get(values.source)),
			translate(APPROVE_LABEL_ID),
			translate("Approve for production")
		);
	}

	function approve(frm) {
		if (!frm.doc.approved_plan) {
			chooseSource(frm);
			return;
		}
		frappe.confirm(
			translate("Warning: a plan was already approved for this order. Continuing creates a new approval and replaces the current approved plan. Do you want to continue?"),
			() => chooseSource(frm)
		);
	}

	function installButton(frm) {
		const groups = [translate(ACTION_GROUP_ID), LEGACY_ACTION_GROUP];
		const labels = [translate(APPROVE_LABEL_ID), translate(REAPPROVE_LABEL_ID), ...LEGACY_APPROVAL_LABELS];
		labels.forEach((label) => {
			groups.forEach((group) => frm.remove_custom_button(label, group));
		});
		// Drawing approval actions stay in the form sections, not the page toolbar.
	}

	frappe.ui.form.on("Door Cutting Order", {
		refresh(frm) {
			setTimeout(() => installButton(frm), 0);
		},
	});

	window.AlmdinaDrawingApprovalUX = Object.freeze({
		approvalSources,
		canApprove,
		installButton,
	});
})();
