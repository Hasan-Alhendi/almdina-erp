(() => {
	"use strict";

	const ACTION_GROUP = __("الرسم / DXF");
	const APPROVE_LABEL = __("اعتماد الرسم");
	const REAPPROVE_LABEL = __("إعادة اعتماد الرسم");

	function canApprove() {
		return Boolean(
			window.AlmdinaPermissions &&
			window.AlmdinaPermissions.can("approve_dxf")
		);
	}

	function isAtDrawing(frm) {
		return Boolean(
			frm &&
			(
				frm.doc.status === "At Drawing" ||
				(
					frm.doc.production_path === "Drawing" &&
					frm.doc.current_department === "رسم"
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
			sources.push({ value: "System", label: __("خطة النظام") });
		}
		if (hasPlan(frm.doc.custom_plan_json) && frm.doc.production_dxf) {
			sources.push({ value: "Custom", label: __("الخطة المرفوعة من DXF") });
		}
		return sources;
	}

	function submitApproval(frm, source) {
		return frappe.call({
			method: "almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf",
			args: { order_name: frm.doc.name, plan_source: source },
			freeze: true,
			freeze_message: __("جاري اعتماد خطة الرسم..."),
		}).then((response) => {
			const result = response.message || {};
			frappe.show_alert({
				message: result.was_previously_approved
					? __("تم تحديث اعتماد الرسم واستبدال الخطة المعتمدة السابقة.")
					: __("تم اعتماد الرسم للإنتاج."),
				indicator: "green",
			}, 6);
			return frm.reload_doc();
		});
	}

	function chooseSource(frm) {
		const sources = approvalSources(frm);
		if (!sources.length) {
			frappe.msgprint(__("لا توجد خطة صالحة للاعتماد."));
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
				label: __("الخطة المعتمدة للإنتاج"),
				options: [...labels.keys()].join("\n"),
				reqd: 1,
				description: __("اختر النسخة النهائية التي تريد اعتمادها للإنتاج."),
			}],
			(values) => submitApproval(frm, labels.get(values.source)),
			APPROVE_LABEL,
			__("اعتماد للإنتاج")
		);
	}

	function approve(frm) {
		if (!frm.doc.approved_plan) {
			chooseSource(frm);
			return;
		}
		frappe.confirm(
			__(
				"تنبيه: تم اعتماد خطة لهذا الطلب سابقًا. المتابعة ستنشئ اعتمادًا جديدًا وتستبدل الخطة المعتمدة الحالية. هل تريد المتابعة؟"
			),
			() => chooseSource(frm)
		);
	}

	function installButton(frm) {
		frm.remove_custom_button(APPROVE_LABEL, ACTION_GROUP);
		frm.remove_custom_button(REAPPROVE_LABEL, ACTION_GROUP);
		if (
			frm.is_new() ||
			!canApprove() ||
			!isAtDrawing(frm) ||
			!approvalSources(frm).length
		) {
			return;
		}
		frm.add_custom_button(
			frm.doc.approved_plan ? REAPPROVE_LABEL : APPROVE_LABEL,
			() => approve(frm),
			ACTION_GROUP
		);
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
