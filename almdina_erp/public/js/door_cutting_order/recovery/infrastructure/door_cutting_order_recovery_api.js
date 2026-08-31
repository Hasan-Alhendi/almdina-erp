(() => {
    "use strict";

    const root = window.AlmdinaDcoRecovery = window.AlmdinaDcoRecovery || Object.create(null);
    if (root.ServerReconciliation) return;

    const METHOD = "almdina_erp.almdina_erp.services.new_order_recovery_service.reconcile_new_order_creation";

    async function reconcileNewCreation(creationToken) {
        const response = await frappe.call({
            method: METHOD,
            args: { creation_token: String(creationToken || "") },
            freeze: false,
        });
        const result = response && response.message;
        if (!result || !["CREATED", "NOT_FOUND"].includes(result.status)) {
            const error = new Error("Server returned an invalid NEW recovery reconciliation result");
            error.code = "invalid_reconciliation";
            throw error;
        }
        if (result.status === "CREATED" && !String(result.door_cutting_order || "").trim()) {
            const error = new Error("Server reconciliation omitted the permanent DCO identity");
            error.code = "invalid_reconciliation";
            throw error;
        }
        return Object.freeze({ ...result });
    }

    root.ServerReconciliation = Object.freeze({ METHOD, reconcileNewCreation });
})();
