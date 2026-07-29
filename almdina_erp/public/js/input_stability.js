(() => {
    "use strict";

    const namespace = window.AlmdinaInputStability = window.AlmdinaInputStability || {};
    const state = namespace.state = namespace.state || {
        editingIdentity: "",
    };

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

    function synchronizeFormIdentity(form) {
        if (!form) return "";
        const identity = formIdentity(form);
        const previous = String(form._almdinaInputStabilityIdentity || "");

        if (previous && identity && previous !== identity) {
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

    function installCore() {
        installInputTracker();
        installRefreshFieldGuard();
        if (window.cur_frm) synchronizeFormIdentity(window.cur_frm);
    }

    function retryInstall() {
        let attempts = 0;
        const timer = window.setInterval(() => {
            attempts += 1;
            installCore();
            const prototype = window.frappe
                && frappe.ui
                && frappe.ui.form
                && frappe.ui.form.Form
                && frappe.ui.form.Form.prototype;
            if (
                attempts >= 40
                || (
                    namespace.inputTrackerInstalled
                    && prototype
                    && prototype._almdinaInputSafeRefreshPatched
                )
            ) {
                window.clearInterval(timer);
            }
        }, 100);
    }

    installCore();
    retryInstall();

    namespace.isEditableElement = isEditableElement;
    namespace.formIdentity = formIdentity;
    namespace.synchronizeFormIdentity = synchronizeFormIdentity;
    namespace.fieldContainsActiveElement = fieldContainsActiveElement;
})();
