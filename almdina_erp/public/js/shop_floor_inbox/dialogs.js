(() => {
    "use strict";

    function workerOptions(workers) {
        return (workers || []).map(worker => ({
            label: worker.full_name && worker.full_name !== worker.name
                ? `${worker.full_name} (${worker.name})`
                : worker.name,
            value: worker.name,
        }));
    }

    function create({ isCurrentGeneration } = {}) {
        const ownedSurfaces = new Map();
        let disposed = false;

        function isCurrent(generation) {
            return !disposed
                && typeof isCurrentGeneration === "function"
                && isCurrentGeneration(generation);
        }

        function close(key) {
            const surface = ownedSurfaces.get(key);
            ownedSurfaces.delete(key);
            if (surface && typeof surface.hide === "function") surface.hide();
        }

        function own(surface, key, generation) {
            if (!surface || typeof surface.hide !== "function") return surface;
            const resolvedKey = String(key || "shop-floor-child");
            if (!isCurrent(generation)) {
                surface.hide();
                return surface;
            }
            close(resolvedKey);
            ownedSurfaces.set(resolvedKey, surface);
            return surface;
        }

        function release(key, surface) {
            if (ownedSurfaces.get(key) === surface) ownedSurfaces.delete(key);
        }

        function confirm(message, generation, key, onYes) {
            if (!isCurrent(generation)) return null;
            let surface = null;
            let settled = false;
            const resolvedKey = String(key || "confirmation");
            surface = frappe.confirm(
                message,
                () => {
                    settled = true;
                    release(resolvedKey, surface);
                    if (isCurrent(generation) && typeof onYes === "function") onYes();
                },
                () => {
                    settled = true;
                    release(resolvedKey, surface);
                }
            );
            if (!settled) own(surface, resolvedKey, generation);
            return surface;
        }

        function promptWorker(handoff, generation, onSubmit) {
            if (!isCurrent(generation)) return null;
            const workers = Array.isArray(handoff && handoff.workers) ? handoff.workers : [];
            let surface = null;
            let settled = false;
            surface = frappe.prompt(
                [{
                    fieldname: "next_assignee",
                    fieldtype: "Select",
                    label: `${__("العامل التالي")} — ${handoff.next_department || handoff.next_stage_type || ""}`,
                    options: workerOptions(workers),
                    reqd: 1,
                }],
                values => {
                    settled = true;
                    release("handoff-worker", surface);
                    if (isCurrent(generation) && typeof onSubmit === "function") {
                        onSubmit(values.next_assignee);
                    }
                },
                __("إرسال للقسم التالي"),
                __("إرسال")
            );
            if (!settled) own(surface, "handoff-worker", generation);
            return surface;
        }

        function noWorkers(handoff, generation) {
            if (!isCurrent(generation)) return null;
            return own(frappe.msgprint(__("لا يوجد عمال متاحون للدور {0} في القسم التالي.", [
                (handoff && handoff.operational_role) || "",
            ])), "no-workers", generation);
        }

        function deactivate() {
            // The worker choice is availability-sensitive and has not mutated the
            // server yet, so an unsubmitted selection is explicitly discarded.
            for (const key of Array.from(ownedSurfaces.keys())) close(key);
        }

        function dispose() {
            if (disposed) return false;
            deactivate();
            disposed = true;
            return true;
        }

        return Object.freeze({
            own,
            confirmTerminal: (generation, onYes) => confirm(
                __("تأكيد إنهاء آخر مرحلة واعتبار الطلب جاهزًا للتسليم؟"),
                generation,
                "terminal-confirm",
                onYes
            ),
            confirmLogout: (generation, onYes) => confirm(
                __("تأكيد تسجيل الخروج؟"),
                generation,
                "logout-confirm",
                onYes
            ),
            promptWorker,
            noWorkers,
            success(message, generation) {
                if (!isCurrent(generation)) return null;
                return frappe.show_alert({ message, indicator: "green" });
            },
            error(message, generation) {
                if (!isCurrent(generation)) return null;
                return own(
                    frappe.msgprint(message || __("تعذر تنفيذ العملية.")),
                    "error",
                    generation
                );
            },
            deactivate,
            dispose,
        });
    }

    window.AlmdinaShopFloorInboxDialogs = Object.freeze({ create, workerOptions });
})();
