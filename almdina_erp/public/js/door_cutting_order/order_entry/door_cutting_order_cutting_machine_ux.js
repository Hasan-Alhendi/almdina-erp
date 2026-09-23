(() => {
    "use strict";

    if (window.AlmdinaOrderCuttingMachineUX) return;

    const STYLE_ID = "dco-cutting-machine-inline-row-css";
    const OPTIONS = Object.freeze([
        Object.freeze({ value: "CNC", label: "CNC" }),
        Object.freeze({ value: "مشرحة", label: "مشرحة" }),
    ]);
    const REQUIRED_MESSAGE = "يجب اختيار نوع آلة القص";

    function fieldNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cutting_machine;
        const wrapper = field && (field.$wrapper || field.wrapper);
        if (!wrapper) return null;
        return wrapper.nodeType ? wrapper : wrapper[0] || null;
    }

    function currentValue(frm) {
        return String((frm && frm.doc && frm.doc.order_cutting_machine) || "").trim();
    }

    function isEditable(frm) {
        if (!frm || !frm.doc) return false;
        if (frm.is_new && frm.is_new()) return true;
        const api = window.AlmdinaOrderRevisionUX;
        if (api && typeof api.isEditableDraft === "function") {
            return Boolean(api.isEditableDraft(frm));
        }
        return false;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .dco-cutting-machine-host.input-max-width,
                .dco-cutting-machine-host.frappe-control {
                    max-width: none !important;
                    width: auto !important;
                }
                .dco-cutting-machine-host .form-group {
                    display: flex !important;
                    flex-direction: column !important;
                    align-items: flex-start;
                    gap: 6px;
                    margin-bottom: 0 !important;
                }
                .dco-cutting-machine-host .form-group::before,
                .dco-cutting-machine-host .form-group::after {
                    display: none !important;
                    content: none !important;
                }
                .dco-cutting-machine-row {
                    display: flex !important;
                    flex-direction: row !important;
                    flex-wrap: nowrap !important;
                    align-items: center;
                    gap: 10px 14px;
                    width: max-content;
                    max-width: 100%;
                }
                .dco-cutting-machine-row .clearfix {
                    display: flex !important;
                    float: none !important;
                    width: auto !important;
                    min-width: 0;
                    flex: 0 0 auto;
                }
                .dco-cutting-machine-row .clearfix::before,
                .dco-cutting-machine-row .clearfix::after {
                    display: none !important;
                    content: none !important;
                }
                .dco-cutting-machine-host .control-label {
                    display: inline-block !important;
                    float: none !important;
                    margin: 0 !important;
                    white-space: nowrap;
                }
                .dco-cutting-machine-host .control-label::after {
                    content: " *";
                    color: var(--red,#e24c4c);
                    font-weight: 800;
                }
                .dco-cutting-machine-option::after {
                    content: none !important;
                }
                .dco-cutting-machine-host .control-input-wrapper {
                    display: none !important;
                }
                .dco-cutting-machine-host .control-input,
                .dco-cutting-machine-host select,
                .dco-cutting-machine-host .select-icon,
                .dco-cutting-machine-host .like-disabled-input,
                .dco-cutting-machine-host .control-value {
                    display: none !important;
                }
                .dco-cutting-machine-radios {
                    display: flex;
                    flex-wrap: nowrap !important;
                    align-items: center;
                    gap: 8px;
                    position: relative;
                    z-index: 1;
                    flex: 0 0 auto;
                }
                .dco-cutting-machine-option {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    min-height: 36px;
                    padding: 6px 14px;
                    border: 1px solid var(--border-color,#d5dbe3);
                    border-radius: 999px;
                    background: var(--card-bg,var(--fg-color,#fff));
                    color: var(--text-color,#26313b);
                    cursor: pointer;
                    font-size: 13px;
                    font-weight: 750;
                    user-select: none;
                }
                .dco-cutting-machine-option.is-selected {
                    border-color: var(--alm-primary,#172033);
                    background: rgba(36,144,239,.08);
                    color: var(--primary,#1b74c4);
                }
                .dco-cutting-machine-option input {
                    margin: 0;
                    accent-color: var(--alm-primary,#172033);
                }
                .dco-cutting-machine-radios.is-invalid .dco-cutting-machine-option {
                    border-color: var(--red,#e24c4c);
                }
                .dco-cutting-machine-error {
                    display: none;
                    margin: 0;
                    color: var(--red,#d83939);
                    font-size: 12px;
                    font-weight: 700;
                }
                .dco-cutting-machine-radios.is-invalid + .dco-cutting-machine-error,
                .dco-cutting-machine-host.is-invalid .dco-cutting-machine-error {
                    display: block;
                }
                .dco-order-notes-locked .dco-cutting-machine-option {
                    cursor: not-allowed;
                    background: var(--subtle-fg,#f6f8fa);
                }
            </style>
        `);
    }

    function hostOf(wrapper) {
        return wrapper.querySelector(".form-group") || wrapper;
    }

    function labelHostOf(wrapper) {
        return wrapper.querySelector(".clearfix") || wrapper.querySelector(".control-label");
    }

    function ensureInlineRow(wrapper, group) {
        const host = hostOf(wrapper);
        let row = wrapper.querySelector(".dco-cutting-machine-row");
        if (!row) {
            row = document.createElement("div");
            row.className = "dco-cutting-machine-row";
        }
        const error = wrapper.querySelector(".dco-cutting-machine-error");
        if (row.parentElement !== host) {
            if (error && error.parentElement === host) host.insertBefore(row, error);
            else if (group && group.parentElement === host) host.insertBefore(row, group);
            else host.appendChild(row);
        }
        const labelHost = labelHostOf(wrapper);
        if (labelHost && labelHost.parentElement !== row) {
            row.insertBefore(labelHost, row.firstChild);
        }
        if (group && group.parentElement !== row) row.appendChild(group);
        if (error && error.parentElement !== host) host.appendChild(error);
        return row;
    }

    function watchWrapper(frm, wrapper) {
        if (!wrapper || wrapper.__dcoMachineWatch) return;
        wrapper.__dcoMachineWatch = true;
        const observer = new MutationObserver(() => {
            if (!wrapper.isConnected) return;
            const group = wrapper.querySelector(".dco-cutting-machine-radios");
            const row = wrapper.querySelector(".dco-cutting-machine-row");
            const labelHost = wrapper.querySelector(".clearfix")
                || wrapper.querySelector(".control-label");
            if (group && row && (!labelHost || labelHost.parentElement === row)) return;
            schedule(frm);
        });
        observer.observe(wrapper, { childList: true, subtree: true });
    }

    function ensureRadios(frm) {
        const wrapper = fieldNode(frm);
        if (!wrapper) return null;
        installStyles();
        wrapper.classList.add("dco-cutting-machine-host");
        watchWrapper(frm, wrapper);
        const host = hostOf(wrapper);
        let group = wrapper.querySelector(".dco-cutting-machine-radios");
        if (!group) {
            group = document.createElement("div");
            group.className = "dco-cutting-machine-radios";
            group.setAttribute("role", "radiogroup");
            group.setAttribute("aria-label", __("نوع آلة القص"));
            group.setAttribute("aria-required", "true");
            OPTIONS.forEach((option) => {
                const label = document.createElement("label");
                label.className = "dco-cutting-machine-option";
                const input = document.createElement("input");
                input.type = "radio";
                input.name = "dco-order-cutting-machine";
                input.value = option.value;
                const text = document.createElement("span");
                text.textContent = __(option.label);
                label.appendChild(input);
                label.appendChild(text);
                group.appendChild(label);
            });
            group.addEventListener("change", (event) => {
                const active = window.cur_frm || frm;
                const input = event.target;
                if (!input || input.type !== "radio" || !isEditable(active)) return;
                const next = String(input.value || "").trim();
                if (!next || currentValue(active) === next) return;
                clearInvalid(active);
                active.set_value("order_cutting_machine", next);
            });
            host.appendChild(group);
            const error = document.createElement("div");
            error.className = "dco-cutting-machine-error";
            error.textContent = __(REQUIRED_MESSAGE);
            host.appendChild(error);
        }
        ensureInlineRow(wrapper, group);
        return group;
    }

    function clearInvalid(frm) {
        const wrapper = fieldNode(frm);
        const group = wrapper && wrapper.querySelector(".dco-cutting-machine-radios");
        if (wrapper) wrapper.classList.remove("is-invalid");
        if (group) {
            group.classList.remove("is-invalid");
            group.removeAttribute("aria-invalid");
        }
    }

    function markInvalid(frm) {
        const wrapper = fieldNode(frm);
        const group = ensureRadios(frm);
        if (wrapper) {
            wrapper.classList.add("is-invalid");
            if (wrapper.scrollIntoView) wrapper.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        if (group) {
            group.classList.add("is-invalid");
            group.setAttribute("aria-invalid", "true");
        }
    }

    function syncRadios(frm) {
        const group = ensureRadios(frm);
        if (!group) return;
        const value = currentValue(frm);
        const editable = isEditable(frm);
        group.querySelectorAll("input[type='radio']").forEach((input) => {
            input.checked = Boolean(value) && input.value === value;
            input.disabled = !editable;
            const option = input.closest(".dco-cutting-machine-option");
            if (option) option.classList.toggle("is-selected", input.checked);
        });
        if (value) clearInvalid(frm);
    }

    function validateSelection(frm) {
        if (!isEditable(frm)) return true;
        if (currentValue(frm)) {
            clearInvalid(frm);
            return true;
        }
        markInvalid(frm);
        frappe.throw(__(REQUIRED_MESSAGE));
        return false;
    }

    function apply(frm) {
        if (!frm || !frm.fields_dict || !frm.fields_dict.order_cutting_machine) return;
        syncRadios(frm);
    }

    function schedule(frm) {
        const run = () => apply(frm);
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "order-cutting-machine", () => {
                run();
                requestAnimationFrame(run);
            });
            return;
        }
        requestAnimationFrame(() => {
            run();
            requestAnimationFrame(run);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        after_save(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        order_cutting_machine(frm) { schedule(frm); },
        validate(frm) { validateSelection(frm); },
    });

    window.AlmdinaOrderCuttingMachineUX = Object.freeze({
        apply,
        schedule,
        validateSelection,
    });
})();
