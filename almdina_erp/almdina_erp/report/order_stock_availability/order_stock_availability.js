frappe.query_reports["Order Stock Availability"] = {
    filters: [
        { fieldname: "order_name", label: __("Order"), fieldtype: "Link", options: "Door Cutting Order" },
        { fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
        { fieldname: "shortage_only", label: __("Show Shortages Only"), fieldtype: "Check", default: 1 },
    ],
};
