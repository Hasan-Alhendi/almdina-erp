frappe.listview_settings["Door Cutting Order"] = {
	onload(listview) {
		// Ensure delivery states never collapse to a vague "تسليم" in the list.
		this._patch_department_column(listview);
	},

	formatters: {
		current_department(value, df, doc) {
			if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
			if (doc.status === "Delivered") return __("تم التسليم");
			if (value === "تسليم") {
				// Legacy rows that still store the vague label.
				if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
				if (doc.status === "Delivered") return __("تم التسليم");
			}
			return value || "";
		},
	},

	_patch_department_column(listview) {
		if (!listview || listview.__almdina_dept_patch) return;
		listview.__almdina_dept_patch = true;
	},
};
