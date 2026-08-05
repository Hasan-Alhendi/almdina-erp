frappe.query_reports["Factory Order Analysis"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
        { fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nPending Review\nApproved\nCutting In Progress\nCut Completed\nEdge Banding In Progress\nProduction In Progress\nQuality Check\nCompleted\nRejected\nOn Hold\nCancelled\nReplacement Required\nPartially Completed" },
        { fieldname: "board_description", label: __("Board Description"), fieldtype: "Data" },
    ],
};
