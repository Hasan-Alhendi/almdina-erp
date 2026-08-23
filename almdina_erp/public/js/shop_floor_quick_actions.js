(() => {
    "use strict";

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
                label: __("تم التسليم"),
                indicator: "success",
            };
        }
        if (context && context.canStart === true) {
            return {
                kind: "start",
                label: __("بدء العمل"),
                indicator: "primary",
            };
        }
        if (context && context.canHandoff === true) {
            return {
                kind: "handoff",
                label: __("إنهاء وإرسال"),
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
            options.push(Object.freeze({
                value,
                label: fullName && fullName !== value ? `${fullName} (${value})` : value,
                name: fullName || value,
                meta: fullName && fullName !== value ? value : "",
            }));
        });
        return options;
    }

    function notify(message) {
        frappe.show_alert({ message, indicator: "green" });
    }

    function runCommand({ method, args, button, successMessage, freezeMessage, onSuccess }) {
        setBusy(button, true);
        return frappe.call({
            method,
            args,
            freeze: true,
            freeze_message: freezeMessage || __("جاري تحديث مسار الإنتاج..."),
        }).then(response => {
            notify(successMessage);
            if (typeof onSuccess === "function") {
                onSuccess(response.message || {});
            }
            return response.message || {};
        }).finally(() => setBusy(button, false));
    }

    function start(context, options) {
        return runCommand({
            method: METHODS.start,
            args: { stage_name: context.stage },
            button: options.button,
            successMessage: __("تم بدء العمل."),
            onSuccess: options.onSuccess,
        });
    }

    function deliver(context, options) {
        return runCommand({
            method: METHODS.deliver,
            args: { order_name: context.order },
            button: options.button,
            successMessage: __("تم تسليم الطلب للعميل."),
            freezeMessage: __("جاري تسجيل تسليم الطلب..."),
            onSuccess: options.onSuccess,
        });
    }

    function finishFinalStage(context, options) {
        const finish = () => runCommand({
            method: METHODS.handoff,
            args: { stage_name: context.stage },
            button: options.button,
            successMessage: __("الطلب جاهز للتسليم."),
            onSuccess: options.onSuccess,
        });

        if (options.skipFinalConfirmation === true) {
            return finish();
        }

        frappe.confirm(
            __("تأكيد إنهاء آخر مرحلة واعتبار الطلب جاهزًا للتسليم؟"),
            finish
        );
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
        const displayValue = selected ? selected.label : __("اختر العامل");

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

    function createWorkerDropdownDialog({ title, label, workers, primaryLabel, onSubmit }) {
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
                if (!selected) {
                    frappe.show_alert({
                        message: __("اختر العامل التالي أولاً."),
                        indicator: "orange",
                    });
                    if (trigger) trigger.focus();
                    return null;
                }
                return onSubmit(selected.value, dialog);
            },
        });

        dialog.show();
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
            const willOpen = trigger.getAttribute("aria-expanded") !== "true";
            setOpen(willOpen);
            if (willOpen) {
                const selectedIndex = optionNodes.findIndex(node => node.getAttribute("aria-selected") === "true");
                focusOption(selectedIndex >= 0 ? selectedIndex : 0);
            }
        });

        trigger.addEventListener("keydown", event => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                setOpen(true);
                focusOption(event.key === "ArrowUp" ? optionNodes.length - 1 : 0);
            } else if (event.key === "Escape") {
                setOpen(false);
            }
        });

        menu.addEventListener("click", event => {
            const optionNode = event.target.closest(".almdina-worker-dropdown-option");
            if (!optionNode) return;
            const choice = choices.find(item => item.value === optionNode.dataset.value);
            if (choice) selectChoice(choice);
        });

        menu.addEventListener("keydown", event => {
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
        const workers = Array.isArray(handoffContext.workers)
            ? handoffContext.workers
            : [];
        if (!workers.length) {
            frappe.msgprint(
                __("لا يوجد عمال متاحون للدور {0} في القسم التالي.", [
                    handoffContext.operational_role || "",
                ])
            );
            return;
        }

        const nextDepartment = handoffContext.next_department
            || handoffContext.next_stage_type
            || __("القسم التالي");
        return createWorkerDropdownDialog({
            title: __("إنهاء وإرسال"),
            label: `${__("العامل التالي")} — ${nextDepartment}`,
            workers,
            primaryLabel: __("إرسال"),
            onSubmit(nextAssignee, dialog) {
                dialog.hide();
                return runCommand({
                    method: METHODS.handoff,
                    args: {
                        stage_name: context.stage,
                        next_assignee: nextAssignee,
                    },
                    button: options.button,
                    successMessage: __("تم إنهاء المرحلة وإرسال الطلب للقسم التالي."),
                    onSuccess: options.onSuccess,
                });
            },
        });
    }

    function handoff(context, options) {
        setBusy(options.button, true);
        return frappe.call({
            method: METHODS.handoffContext,
            args: { stage_name: context.stage },
        }).then(response => {
            setBusy(options.button, false);
            const handoffContext = response.message || {};
            if (handoffContext.final_stage === true) {
                return finishFinalStage(context, options);
            }
            promptNextWorker(context, options, handoffContext);
            return handoffContext;
        }).catch(error => {
            setBusy(options.button, false);
            throw error;
        });
    }

    function perform(context, options = {}) {
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
            const stage = response.message || {};
            if (stage.actor_holds_operational_role === false) {
                frappe.msgprint(__(
                    "يمكنك عرض هذا الطلب فقط. مرحلته الحالية ليست ضمن أدوارك التشغيلية."
                ));
                return null;
            }
            const stillAllowed = action.kind === "start"
                ? stage.can_start_stage === true
                : stage.can_handoff_stage === true;
            if (!stillAllowed) {
                frappe.msgprint(__("لم يعد هذا الإجراء متاحًا في حالة الطلب الحالية."));
                return null;
            }
            if (action.kind === "start") {
                return start(context, options);
            }
            return handoff(context, options);
        });
        return guard;
    }

    ensureStylesheet();

    window.AlmdinaShopFloorQuickActions = Object.freeze({
        actionFor,
        perform,
    });
})();