frappe.query_reports["Production Incidents and Replacements"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
        { fieldname: "order_name", label: __("Order"), fieldtype: "Link", options: "Door Cutting Order" },
        { fieldname: "worker", label: __("Worker"), fieldtype: "Link", options: "User" },
        { fieldname: "reason", label: __("Reason"), fieldtype: "Select", options: "\nMeasurement Error\nCutting Error\nEdge Banding Error\nDamage\nLost Piece\nMaterial Defect\nOther" },
        { fieldname: "status", label: __("Incident Status"), fieldtype: "Select", options: "\nOpen\nReplacement Created\nResolved" },
    ],
};
