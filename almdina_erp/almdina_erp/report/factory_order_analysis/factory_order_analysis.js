frappe.query_reports["Factory Order Analysis"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
        { fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nPending Review\nApproved\nCutting In Progress\nCut Completed\nEdge Banding In Progress\nProduction In Progress\nQuality Check\nCompleted\nRejected\nOn Hold\nCancelled\nReplacement Required\nPartially Completed" },
        { fieldname: "board_item", label: __("Board Item"), fieldtype: "Link", options: "Item", get_query: () => ({ filters: { custom_is_mdf: 1 } }) },
        { fieldname: "material", label: __("Material"), fieldtype: "Data" },
        { fieldname: "color", label: __("Color"), fieldtype: "Data" },
    ],
};
