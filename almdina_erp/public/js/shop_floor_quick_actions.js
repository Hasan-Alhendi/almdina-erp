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

    const SHOP_FLOOR_STYLESHEET_ID = "almdina-shop-floor-responsive-css";
    const SHOP_FLOOR_STYLESHEET_HREF = "/assets/almdina_erp/css/shop_floor_responsive.css";
    const WORKER_DROPDOWN_STYLESHEET_ID = "almdina-shop-floor-worker-dropdown-css";
    const WORKER_DROPDOWN_STYLESHEET_HREF = "/assets/almdina_erp/css/shop_floor_worker_dropdown.css";

    const METHODS = Object.freeze({
        start: "almdina_erp.almdina_erp.services.shop_floor_commands.start_my_stage",
        handoffContext: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
        handoff: "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
        deliver: "almdina_erp.almdina_erp.services.shop_floor_commands.mark_delivered",
    });

    let workerDropdownSequence = 0;

    function ensureStylesheet() {
        if (typeof document === "undefined" || !document.head) return;
        if (document.getElementById(SHOP_FLOOR_STYLESHEET_ID)) return;
        const link = document.createElement("link");
        link.id = SHOP_FLOOR_STYLESHEET_ID;
        link.rel = "stylesheet";
        link.href = SHOP_FLOOR_STYLESHEET_HREF;
        document.head.appendChild(link);
    }

    function ensureWorkerDropdownStylesheet() {
        if (typeof document === "undefined" || !document.head) return;
        if (document.getElementById(WORKER_DROPDOWN_STYLESHEET_ID)) return;
        const link = document.createElement("link");
        link.id = WORKER_DROPDOWN_STYLESHEET_ID;
        link.rel = "stylesheet";
        link.href = WORKER_DROPDOWN_STYLESHEET_HREF;
        document.head.appendChild(link);
    }

    function actionFor(context) {
        if (context && context.canDeliver === true) {
            return {
                kind: "deliver",
                label: translate("Delivered"),
                indicator: "success",
            };
        }
        if (context && context.canStart === true) {
            return {
                kind: "start",
                label: translate("Start work"),
                indicator: "primary",
            };
        }
        if (context && context.canHandoff === true) {
            return {
                kind: "handoff",
                label: translate("Finish and send"),
                indicator: "success",
            };
        }
        return null;
    }

    function setBusy(button, busy) {
        if (!button) return;
        button.disabled = Boolean(busy);
        button.setAttribute("aria-busy", busy ? "true" : "false");
        button.classList.toggle("is-loading", Boolean(busy));
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function workerOptions(workers) {
        const seen = new Set();
        const options = [];
        (workers || []).forEach(worker => {
            const value = String(worker && worker.name || "").trim();
            if (!value || seen.has(value)) return;
            seen.add(value);
            const fullName = String(worker.full_name || "").trim();
            const displayName = fullName && fullName !== value ? fullName : value;
            options.push(Object.freeze({
                value,
                label: displayName,
                name: displayName,
                meta: "",
            }));
        });
        return options;
    }

    function lifecycleBoundary(options = {}) {
        const owner = options.lifecycle && typeof options.lifecycle === "object"
            ? options.lifecycle
            : {};
        return Object.freeze({
            isCurrent: typeof owner.isCurrent === "function" ? owner.isCurrent : () => true,
            ownTransient: typeof owner.ownTransient === "function"
                ? owner.ownTransient
                : surface => surface,
            onStaleMutationSuccess: typeof owner.onStaleMutationSuccess === "function"
                ? owner.onStaleMutationSuccess
                : () => null,
        });
    }

    function notify(message, boundary) {
        if (!boundary.isCurrent()) return null;
        return frappe.show_alert({ message, indicator: "green" });
    }

    function runCommand({ method, args, button, successMessage, freezeMessage, onSuccess, onError, lifecycle }) {
        const boundary = lifecycleBoundary({ lifecycle });
        if (!boundary.isCurrent()) return Promise.resolve(null);
        setBusy(button, true);
        return frappe.call({
            method,
            args,
            freeze: true,
            freeze_message: freezeMessage || translate("Updating the production route..."),
        }).then(response => {
            const data = response.message || {};
            if (!boundary.isCurrent()) {
                return Promise.resolve(boundary.onStaleMutationSuccess(data)).then(() => data);
            }
            notify(successMessage, boundary);
            if (typeof onSuccess === "function") onSuccess(data);
            return data;
        }).catch(error => {
            if (!boundary.isCurrent()) return null;
            if (typeof onError === "function") {
                onError(error);
                return null;
            }
            throw error;
        }).finally(() => {
            if (boundary.isCurrent()) setBusy(button, false);
        });
    }

    function start(context, options) {
        return runCommand({
            method: METHODS.start,
            args: { stage_name: context.stage },
            button: options.button,
            successMessage: translate("Work has started."),
            onSuccess: options.onSuccess,
            onError: options.onError,
            lifecycle: options.lifecycle,
        });
    }

    function deliver(context, options) {
        return runCommand({
            method: METHODS.deliver,
            args: { order_name: context.order },
            button: options.button,
            successMessage: translate("The order was delivered to the customer."),
            freezeMessage: translate("Recording order delivery..."),
            onSuccess: options.onSuccess,
            onError: options.onError,
            lifecycle: options.lifecycle,
        });
    }

    function finishFinalStage(context, options) {
        const finish = () => runCommand({
            method: METHODS.handoff,
            args: { stage_name: context.stage },
            button: options.button,
            successMessage: translate("The order is ready for delivery."),
            onSuccess: options.onSuccess,
            onError: options.onError,
            lifecycle: options.lifecycle,
        });

        if (options.skipFinalConfirmation === true) {
            return finish();
        }

        const boundary = lifecycleBoundary(options);
        if (!boundary.isCurrent()) return null;
        const surface = frappe.confirm(
            translate("Confirm finishing the last stage and marking the order ready for delivery?"),
            () => {
                if (boundary.isCurrent()) finish();
            }
        );
        boundary.ownTransient(surface, "terminal-confirm");
        return null;
    }

    function workerDropdownMarkup(controlId, label, choices, selected) {
        const optionsMarkup = choices.map(choice => `
            <button
                type="button"
                class="almdina-worker-dropdown-option"
                role="option"
                data-value="${escapeHtml(choice.value)}"
                aria-selected="${selected && selected.value === choice.value ? "true" : "false"}"
            >
                <span class="almdina-worker-dropdown-option-name">${escapeHtml(choice.name)}</span>
                ${choice.meta ? `<span class="almdina-worker-dropdown-option-meta">${escapeHtml(choice.meta)}</span>` : ""}
            </button>
        `).join("");
        const displayValue = selected ? selected.label : translate("Choose a worker");

        return `
            <div class="almdina-worker-dropdown-field">
                <div class="almdina-worker-dropdown-label" id="${controlId}-label">${escapeHtml(label)}</div>
                <div class="almdina-worker-dropdown">
                    <button
                        type="button"
                        class="almdina-worker-dropdown-trigger"
                        aria-labelledby="${controlId}-label ${controlId}-value"
                        aria-haspopup="listbox"
                        aria-expanded="false"
                        aria-controls="${controlId}-menu"
                    >
                        <span
                            class="almdina-worker-dropdown-value${selected ? "" : " is-placeholder"}"
                            id="${controlId}-value"
                        >${escapeHtml(displayValue)}</span>
                        <span class="almdina-worker-dropdown-chevron" aria-hidden="true">⌄</span>
                    </button>
                    <div
                        class="almdina-worker-dropdown-menu"
                        id="${controlId}-menu"
                        role="listbox"
                        aria-labelledby="${controlId}-label"
                        hidden
                    >${optionsMarkup}</div>
                </div>
            </div>
        `;
    }

    function createWorkerDropdownDialog({ title, label, workers, primaryLabel, onSubmit, lifecycle }) {
        const boundary = lifecycleBoundary({ lifecycle });
        if (!boundary.isCurrent()) return null;
        ensureWorkerDropdownStylesheet();
        const choices = workerOptions(workers);
        let selected = choices.length === 1 ? choices[0] : null;
        let trigger = null;
        let menu = null;
        let control = null;
        let optionNodes = [];
        const controlId = `almdina-worker-dropdown-${++workerDropdownSequence}`;

        const dialog = new frappe.ui.Dialog({
            title,
            fields: [{
                fieldname: "next_assignee_dropdown",
                fieldtype: "HTML",
            }],
            primary_action_label: primaryLabel,
            primary_action() {
                if (!boundary.isCurrent()) {
                    dialog.hide();
                    return null;
                }
                if (!selected) {
                    frappe.show_alert({
                        message: translate("Choose the next worker first."),
                        indicator: "orange",
                    });
                    if (trigger) trigger.focus();
                    return null;
                }
                return onSubmit(selected.value, dialog);
            },
        });

        boundary.ownTransient(dialog, "worker-dialog");
        if (!boundary.isCurrent()) return dialog;
        dialog.show();
        if (dialog.$wrapper && typeof dialog.$wrapper.attr === "function") {
            dialog.$wrapper.attr("dir", uiDirection());
        }
        const field = dialog.fields_dict && dialog.fields_dict.next_assignee_dropdown;
        const root = field && field.$wrapper && field.$wrapper[0];
        if (!root) return dialog;

        root.innerHTML = workerDropdownMarkup(controlId, label, choices, selected);
        control = root.querySelector(".almdina-worker-dropdown");
        trigger = root.querySelector(".almdina-worker-dropdown-trigger");
        menu = root.querySelector(".almdina-worker-dropdown-menu");
        optionNodes = [...root.querySelectorAll(".almdina-worker-dropdown-option")];
        if (!control || !trigger || !menu) return dialog;

        const setOpen = open => {
            control.classList.toggle("is-open", Boolean(open));
            trigger.setAttribute("aria-expanded", open ? "true" : "false");
            menu.hidden = !open;
            if (!open) {
                control.classList.remove("is-drop-up");
                return;
            }

            const rect = control.getBoundingClientRect();
            const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
            const availableBelow = Math.max(0, viewportHeight - rect.bottom);
            const estimatedMenuHeight = Math.min(menu.scrollHeight || 240, 280);
            control.classList.toggle(
                "is-drop-up",
                availableBelow < estimatedMenuHeight + 16 && rect.top > availableBelow
            );
        };

        const selectChoice = choice => {
            selected = choice;
            const valueNode = trigger.querySelector(".almdina-worker-dropdown-value");
            if (valueNode) {
                valueNode.textContent = choice.label;
                valueNode.classList.remove("is-placeholder");
            }
            optionNodes.forEach(node => node.setAttribute(
                "aria-selected",
                node.dataset.value === choice.value ? "true" : "false"
            ));
            setOpen(false);
            trigger.focus();
        };

        const focusOption = index => {
            if (!optionNodes.length) return;
            const normalized = (index + optionNodes.length) % optionNodes.length;
            optionNodes[normalized].focus();
        };

        trigger.addEventListener("click", () => {
            if (!boundary.isCurrent()) return;
            const willOpen = trigger.getAttribute("aria-expanded") !== "true";
            setOpen(willOpen);
            if (willOpen) {
                const selectedIndex = optionNodes.findIndex(node => node.getAttribute("aria-selected") === "true");
                focusOption(selectedIndex >= 0 ? selectedIndex : 0);
            }
        });

        trigger.addEventListener("keydown", event => {
            if (!boundary.isCurrent()) return;
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                setOpen(true);
                focusOption(event.key === "ArrowUp" ? optionNodes.length - 1 : 0);
            } else if (event.key === "Escape") {
                setOpen(false);
            }
        });

        menu.addEventListener("click", event => {
            if (!boundary.isCurrent()) return;
            const optionNode = event.target.closest(".almdina-worker-dropdown-option");
            if (!optionNode) return;
            const choice = choices.find(item => item.value === optionNode.dataset.value);
            if (choice) selectChoice(choice);
        });

        menu.addEventListener("keydown", event => {
            if (!boundary.isCurrent()) return;
            const current = event.target.closest(".almdina-worker-dropdown-option");
            if (!current) return;
            const currentIndex = optionNodes.indexOf(current);
            if (event.key === "ArrowDown") {
                event.preventDefault();
                focusOption(currentIndex + 1);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                focusOption(currentIndex - 1);
            } else if (event.key === "Home") {
                event.preventDefault();
                focusOption(0);
            } else if (event.key === "End") {
                event.preventDefault();
                focusOption(optionNodes.length - 1);
            } else if (event.key === "Escape") {
                event.preventDefault();
                setOpen(false);
                trigger.focus();
            }
        });

        return dialog;
    }

    function promptNextWorker(context, options, handoffContext) {
        const boundary = lifecycleBoundary(options);
        if (!boundary.isCurrent()) return null;
        const workers = Array.isArray(handoffContext.workers)
            ? handoffContext.workers
            : [];
        if (!workers.length) {
            const surface = frappe.msgprint(
                translate("No workers are available for role {0} in the next department.", [
                    handoffContext.operational_role || "",
                ])
            );
            return boundary.ownTransient(surface, "no-workers");
        }

        const nextDepartment = handoffContext.next_department
            || handoffContext.next_stage_type
            || translate("Next department");
        return createWorkerDropdownDialog({
            title: translate("Finish and send"),
            label: `${translate("Next worker")} — ${nextDepartment}`,
            workers,
            primaryLabel: translate("Send"),
            lifecycle: options.lifecycle,
            onSubmit(nextAssignee, dialog) {
                if (!boundary.isCurrent()) return null;
                dialog.hide();
                return runCommand({
                    method: METHODS.handoff,
                    args: {
                        stage_name: context.stage,
                        next_assignee: nextAssignee,
                    },
                    button: options.button,
                    successMessage: translate("The stage was finished and the order was sent to the next department."),
                    onSuccess: options.onSuccess,
                    onError: options.onError,
                    lifecycle: options.lifecycle,
                });
            },
        });
    }

    function handoff(context, options) {
        const boundary = lifecycleBoundary(options);
        if (!boundary.isCurrent()) return Promise.resolve(null);
        setBusy(options.button, true);
        return frappe.call({
            method: METHODS.handoffContext,
            args: { stage_name: context.stage },
        }).then(response => {
            if (!boundary.isCurrent()) return null;
            setBusy(options.button, false);
            const handoffContext = response.message || {};
            if (handoffContext.final_stage === true) {
                return finishFinalStage(context, options);
            }
            promptNextWorker(context, options, handoffContext);
            return handoffContext;
        }).catch(error => {
            if (!boundary.isCurrent()) return null;
            setBusy(options.button, false);
            if (typeof options.onError === "function") {
                options.onError(error);
                return null;
            }
            throw error;
        });
    }

    function perform(context, options = {}) {
        const boundary = lifecycleBoundary(options);
        if (!boundary.isCurrent()) return null;
        const action = actionFor(context);
        if (!action) return;
        if (action.kind === "deliver") {
            return deliver(context, options);
        }
        if (!context.stage) return;

        const guard = frappe.call({
            method: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_current_stage_context",
            args: { order_name: context.order },
        }).then(response => {
            if (!boundary.isCurrent()) return null;
            const stage = response.message || {};
            const canOperateCurrentStage = stage.actor_can_operate_current_stage !== undefined
                ? stage.actor_can_operate_current_stage === true
                : stage.actor_holds_operational_role !== false;
            if (!canOperateCurrentStage) {
                const surface = frappe.msgprint(translate("You can view this order only. Its current stage is outside your operational roles."));
                boundary.ownTransient(surface, "not-operational-role");
                return null;
            }
            const stillAllowed = action.kind === "start"
                ? stage.can_start_stage === true
                : stage.can_handoff_stage === true;
            if (!stillAllowed) {
                const surface = frappe.msgprint(translate("This action is no longer available in the current order state."));
                boundary.ownTransient(surface, "action-unavailable");
                return null;
            }
            if (action.kind === "start") {
                return start(context, options);
            }
            return handoff(context, options);
        }).catch(error => {
            if (!boundary.isCurrent()) return null;
            if (typeof options.onError === "function") {
                options.onError(error);
                return null;
            }
            throw error;
        });
        return guard;
    }

    ensureStylesheet();

    window.AlmdinaShopFloorQuickActions = Object.freeze({
        actionFor,
        perform,
        createWorkerDropdownDialog,
    });
})();
