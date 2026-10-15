(() => {
    "use strict";


    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function workerOptions(workers) {
        return (workers || []).map(worker => {
            const id = String(worker && worker.name || "").trim();
            const fullName = String(worker && worker.full_name || "").trim();
            return {
                label: fullName && fullName !== id ? fullName : (id || worker.name),
                value: worker.name,
            };
        });
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
            const quickActions = window.AlmdinaShopFloorQuickActions;
            if (!quickActions || typeof quickActions.createWorkerDropdownDialog !== "function") {
                throw new Error("Shop Floor worker dropdown dialog is unavailable");
            }
            const workers = Array.isArray(handoff && handoff.workers) ? handoff.workers : [];
            const nextDepartment = handoff.next_department || handoff.next_stage_type || translate("Next department");
            const lifecycle = {
                isCurrent: () => isCurrent(generation),
                ownTransient: surface => own(surface, "handoff-worker", generation),
            };
            return quickActions.createWorkerDropdownDialog({
                title: translate("Send to the next department"),
                label: `${translate("Next worker")} — ${nextDepartment}`,
                workers,
                primaryLabel: translate("Send"),
                lifecycle,
                onSubmit(nextAssignee, dialogSurface) {
                    if (!isCurrent(generation)) {
                        if (dialogSurface && typeof dialogSurface.hide === "function") dialogSurface.hide();
                        return null;
                    }
                    release("handoff-worker", dialogSurface);
                    if (typeof onSubmit === "function") onSubmit(nextAssignee);
                    if (dialogSurface && typeof dialogSurface.hide === "function") dialogSurface.hide();
                    return null;
                },
            });
        }

        function noWorkers(handoff, generation) {
            if (!isCurrent(generation)) return null;
            return own(frappe.msgprint(translate("No workers are available for role {0} in the next department.", [
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
                translate("Confirm finishing the last stage and marking the order ready for delivery?"),
                generation,
                "terminal-confirm",
                onYes
            ),
            confirmLogout: (generation, onYes) => confirm(
                translate("Confirm sign-out?"),
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
            whatsapp(result, generation) {
                if (!isCurrent(generation) || !result) return null;
                return frappe.show_alert({
                    message: result.ok
                        ? translate("A WhatsApp message was sent to the customer.")
                        : (result.message || translate("The stage completed without sending WhatsApp.")),
                    indicator: result.ok ? "green" : "orange",
                }, 6);
            },
            error(message, generation) {
                if (!isCurrent(generation)) return null;
                return own(
                    frappe.msgprint(message || translate("Could not complete the operation.")),
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
