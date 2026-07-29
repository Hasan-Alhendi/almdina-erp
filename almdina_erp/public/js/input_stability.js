(() => {
    "use strict";

    const PREVIEW_METHOD = "almdina_erp.almdina_erp.api.preview_door_cutting_order";
    const namespace = window.AlmdinaInputStability = window.AlmdinaInputStability || {};
    const state = namespace.state = namespace.state || {
        generation: 0,
        composing: false,
        lastInputAt: 0,
        editingIdentity: "",
    };

    function now() {
        return Date.now();
    }

    function formIdentity(form) {
        const doc = form && form.doc;
        if (!doc) return "";
        const doctype = String(doc.doctype || form.doctype || "").trim();
        const name = String(doc.name || "__new__").trim();
        return `${doctype}::${name}`;
    }

    function isEditableElement(element) {
        if (!element || element === document.body) return false;
        if (element.isContentEditable) return true;
        return ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName)
            && !element.disabled
            && !element.readOnly;
    }

    function formWrapper(form) {
        if (!form || !form.wrapper) return null;
        return form.wrapper.jquery ? form.wrapper.get(0) : (form.wrapper[0] || form.wrapper);
    }

    function identityForElement(element) {
        return String(
            element
            && element.dataset
            && element.dataset.almdinaFormIdentity
            || ""
        );
    }

    function rememberEditingIdentity(element) {
        if (!isEditableElement(element)) return "";
        const form = window.cur_frm || null;
        const wrapper = formWrapper(form);
        if (!form || !wrapper || !wrapper.contains(element)) return "";
        const identity = synchronizeFormIdentity(form);
        if (!identity) return "";
        if (element.dataset) element.dataset.almdinaFormIdentity = identity;
        state.editingIdentity = identity;
        return identity;
    }

    function markInputActivity(event) {
        if (!isEditableElement(event.target)) return;
        rememberEditingIdentity(event.target);
        state.generation += 1;
        state.lastInputAt = now();
    }

    function synchronizeFormIdentity(form) {
        if (!form) return "";
        const identity = formIdentity(form);
        const previous = String(form._almdinaInputStabilityIdentity || "");

        if (previous && identity && previous !== identity) {
            state.generation += 1;
            state.composing = false;
            if (state.editingIdentity === previous) state.editingIdentity = "";
            if (form._almdinaDeferredFieldRefreshes instanceof Set) {
                form._almdinaDeferredFieldRefreshes.clear();
            }
            form._almdinaDeferredRefreshIdentity = identity;
        }

        if (identity) form._almdinaInputStabilityIdentity = identity;
        return identity;
    }

    function installInputTracker() {
        if (namespace.inputTrackerInstalled) return;
        namespace.inputTrackerInstalled = true;

        document.addEventListener("focusin", event => {
            rememberEditingIdentity(event.target);
        }, true);
        document.addEventListener("beforeinput", markInputActivity, true);
        document.addEventListener("input", markInputActivity, true);
        document.addEventListener("paste", markInputActivity, true);
        document.addEventListener("cut", markInputActivity, true);
        document.addEventListener("drop", markInputActivity, true);
        document.addEventListener("compositionstart", event => {
            if (!isEditableElement(event.target)) return;
            rememberEditingIdentity(event.target);
            state.composing = true;
            markInputActivity(event);
        }, true);
        document.addEventListener("compositionend", event => {
            if (!isEditableElement(event.target)) return;
            state.composing = false;
            markInputActivity(event);
        }, true);
    }

    function activeElementBelongsToForm(form) {
        const active = document.activeElement;
        const wrapper = formWrapper(form);
        const currentIdentity = synchronizeFormIdentity(form);
        if (!wrapper || !isEditableElement(active) || !wrapper.contains(active)) return false;

        let activeIdentity = identityForElement(active) || state.editingIdentity;
        if (!activeIdentity && currentIdentity) {
            activeIdentity = currentIdentity;
            if (active.dataset) active.dataset.almdinaFormIdentity = currentIdentity;
            state.editingIdentity = currentIdentity;
        }
        return !activeIdentity || !currentIdentity || activeIdentity === currentIdentity;
    }

    function fieldContainsActiveElement(form, fieldname) {
        if (!fieldname || !activeElementBelongsToForm(form)) return false;
        const active = document.activeElement;
        const wrapper = formWrapper(form);
        if (!active || !wrapper) return false;

        let node = active;
        while (node && node !== wrapper) {
            if (node.dataset && node.dataset.fieldname === fieldname) return true;
            node = node.parentElement;
        }

        const field = form.fields_dict && form.fields_dict[fieldname];
        const fieldRoot = field && field.$wrapper
            ? field.$wrapper.get(0)
            : (field && field.wrapper ? (field.wrapper[0] || field.wrapper) : null);
        return Boolean(fieldRoot && fieldRoot.contains(active));
    }

    function installRefreshFieldGuard() {
        if (!window.frappe || !frappe.ui || !frappe.ui.form || !frappe.ui.form.Form) {
            return false;
        }

        const prototype = frappe.ui.form.Form.prototype;
        if (!prototype || prototype._almdinaInputSafeRefreshPatched) return true;

        const originalRefreshField = prototype.refresh_field;
        if (typeof originalRefreshField !== "function") return false;

        prototype.refresh_field = function inputSafeRefreshField(fieldname, ...args) {
            const currentIdentity = synchronizeFormIdentity(this);
            const names = Array.isArray(fieldname) ? fieldname : [fieldname];
            const blocked = names.filter(name => typeof name === "string" && fieldContainsActiveElement(this, name));
            const safe = names.filter(name => !blocked.includes(name));

            if (blocked.length) {
                this._almdinaDeferredFieldRefreshes = this._almdinaDeferredFieldRefreshes || new Set();
                this._almdinaDeferredRefreshIdentity = currentIdentity;
                blocked.forEach(name => this._almdinaDeferredFieldRefreshes.add(name));
                installDeferredRefreshFlush(this, originalRefreshField);
            }

            if (!safe.length) return this;
            return originalRefreshField.call(this, Array.isArray(fieldname) ? safe : safe[0], ...args);
        };
        prototype._almdinaInputSafeRefreshPatched = true;
        prototype._almdinaOriginalRefreshField = originalRefreshField;
        return true;
    }

    function installDeferredRefreshFlush(form, originalRefreshField) {
        const wrapper = formWrapper(form);
        if (!wrapper || wrapper._almdinaDeferredRefreshFlushInstalled) return;
        wrapper._almdinaDeferredRefreshFlushInstalled = true;

        wrapper.addEventListener("focusout", () => {
            window.setTimeout(() => {
                const pending = form._almdinaDeferredFieldRefreshes;
                if (!pending || !pending.size) return;

                const currentIdentity = synchronizeFormIdentity(form);
                if (
                    form._almdinaDeferredRefreshIdentity
                    && currentIdentity
                    && form._almdinaDeferredRefreshIdentity !== currentIdentity
                ) {
                    pending.clear();
                    form._almdinaDeferredRefreshIdentity = currentIdentity;
                    return;
                }

                [...pending].forEach(fieldname => {
                    if (fieldContainsActiveElement(form, fieldname)) return;
                    pending.delete(fieldname);
                    originalRefreshField.call(form, fieldname);
                });
            }, 40);
        }, true);
    }

    function installPreviewResponseGuard() {
        if (!window.frappe || typeof frappe.call !== "function") return false;
        if (frappe.call._almdinaInputSafePatched) return true;

        const originalCall = frappe.call;
        const guardedCall = function inputSafeFrappeCall(options, ...args) {
            if (!options || typeof options !== "object" || options.method !== PREVIEW_METHOD) {
                return originalCall.call(this, options, ...args);
            }

            const requestGeneration = state.generation;
            const requestForm = window.cur_frm || null;
            const requestIdentity = formIdentity(requestForm);
            const originalCallback = options.callback;
            const guardedOptions = {
                ...options,
                callback(response) {
                    const inputChanged = state.generation !== requestGeneration;
                    const editing = requestForm && activeElementBelongsToForm(requestForm);
                    const documentChanged = Boolean(
                        requestIdentity
                        && (
                            formIdentity(requestForm) !== requestIdentity
                            || (window.cur_frm && formIdentity(window.cur_frm) !== requestIdentity)
                        )
                    );
                    if (inputChanged || state.composing || editing || documentChanged) {
                        return;
                    }
                    if (typeof originalCallback === "function") {
                        return originalCallback(response);
                    }
                },
            };
            return originalCall.call(this, guardedOptions, ...args);
        };

        guardedCall._almdinaInputSafePatched = true;
        guardedCall._almdinaOriginalCall = originalCall;
        frappe.call = guardedCall;
        return true;
    }

    function isLegacyLivePreviewHandler(handler) {
        if (typeof handler !== "function") return false;
        const source = Function.prototype.toString.call(handler);
        return source.includes("schedule_recalculate")
            || source.includes("scheduleRecalculate");
    }

    function removeHandler(registry, eventName) {
        if (!registry || !Object.prototype.hasOwnProperty.call(registry, eventName)) return;
        const handlers = registry[eventName];
        if (Array.isArray(handlers)) {
            registry[eventName] = handlers.filter(handler => !isLegacyLivePreviewHandler(handler));
            return;
        }
        if (isLegacyLivePreviewHandler(handlers)) {
            delete registry[eventName];
        }
    }

    function removeDoorOrderLivePreviewHandlers() {
        if (!window.frappe || !frappe.ui || !frappe.ui.form || !frappe.ui.form.handlers) return false;

        const orderHandlers = frappe.ui.form.handlers["Door Cutting Order"];
        const detailHandlers = frappe.ui.form.handlers["Door Cutting Order Detail"];
        const orderEvents = [
            "customer",
            "board_description",
            "board_length_cm",
            "board_width_cm",
            "board_rate_usd",
            "default_edge_type",
            "cutting_cost_per_board_usd",
            "kerf_mm",
            "trim_margin_mm",
            "packing_mode",
            "pieces_add",
            "pieces_remove",
        ];
        const detailEvents = [
            "width_cm",
            "length_cm",
            "qty",
            "allow_rotation",
            "edge_long_right",
            "edge_long_left",
            "edge_width_top",
            "edge_width_bottom",
            "edge_type",
            "piece_type",
            "clipped_corner_position",
            "clipped_corner_width_cm",
            "clipped_corner_length_cm",
            "notes",
        ];

        orderEvents.forEach(eventName => removeHandler(orderHandlers, eventName));
        detailEvents.forEach(eventName => removeHandler(detailHandlers, eventName));
        return true;
    }

    function installCore() {
        installInputTracker();
        installRefreshFieldGuard();
        installPreviewResponseGuard();
        if (window.cur_frm) synchronizeFormIdentity(window.cur_frm);
    }

    function retryInstall() {
        let attempts = 0;
        const timer = window.setInterval(() => {
            attempts += 1;
            installCore();
            removeDoorOrderLivePreviewHandlers();
            if (attempts >= 40 || (
                namespace.inputTrackerInstalled
                && window.frappe
                && frappe.call
                && frappe.call._almdinaInputSafePatched
                && frappe.ui
                && frappe.ui.form
                && frappe.ui.form.Form
                && frappe.ui.form.Form.prototype._almdinaInputSafeRefreshPatched
            )) {
                window.clearInterval(timer);
            }
        }, 100);
    }

    installCore();
    removeDoorOrderLivePreviewHandlers();
    window.setTimeout(removeDoorOrderLivePreviewHandlers, 0);
    window.setTimeout(removeDoorOrderLivePreviewHandlers, 250);
    retryInstall();

    namespace.markInputActivity = markInputActivity;
    namespace.isEditableElement = isEditableElement;
    namespace.formIdentity = formIdentity;
    namespace.synchronizeFormIdentity = synchronizeFormIdentity;
    namespace.fieldContainsActiveElement = fieldContainsActiveElement;
    namespace.removeDoorOrderLivePreviewHandlers = removeDoorOrderLivePreviewHandlers;
})();
