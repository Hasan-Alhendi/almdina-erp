frappe.query_reports["Production Stage Performance"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
        { fieldname: "worker", label: __("Worker"), fieldtype: "Link", options: "User" },
        { fieldname: "stage_type", label: __("Stage Type"), fieldtype: "Select", options: "\nReview / Preparation\nCutting\nEdge Banding\nDrilling\nAssembly\nQuality Check\nPacking" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nPending\nIn Progress\nPaused\nCompleted\nCancelled" },
    ],
};
