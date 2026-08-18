(() => {
    "use strict";

    if (window.AlmdinaWorkspaceFieldEditor) return;

    const ROOT_CLASS = "almdina-workspace-field-editor";
    const NATIVE_HIDDEN_ATTR = "data-almdina-workspace-native-hidden";

    function normalizeNumber(value, integer = false) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return 0;
        return integer ? Math.trunc(parsed) : parsed;
    }

    function fieldValue(field, raw) {
        const type = String(field && field.df && field.df.fieldtype || "");
        if (type === "Int") return normalizeNumber(raw, true);
        if (["Float", "Currency", "Percent"].includes(type)) return normalizeNumber(raw);
        return raw;
    }

    function selectOptions(field, selected) {
        const raw = field && field.df ? field.df.options : null;
        const options = Array.isArray(raw)
            ? raw.map((item) => String(item == null ? "" : item))
            : String(raw || "").split("\n").map((item) => item.trim());
        const normalized = String(selected == null ? "" : selected);
        if (normalized && !options.includes(normalized)) options.push(normalized);
        return options;
    }

    function buildControl(field, value) {
        const type = String(field && field.df && field.df.fieldtype || "Data");
        let control;
        if (type === "Select") {
            control = document.createElement("select");
            control.className = "form-control";
            selectOptions(field, value).forEach((optionValue) => {
                const option = document.createElement("option");
                option.value = optionValue;
                option.textContent = optionValue;
                control.appendChild(option);
            });
            control.value = String(value == null ? "" : value);
        } else {
            control = document.createElement("input");
            control.className = "form-control";
            control.type = ["Int", "Float", "Currency", "Percent"].includes(type)
                ? "number"
                : "text";
            if (control.type === "number") control.step = type === "Int" ? "1" : "any";
            control.value = value == null ? "" : String(value);
        }
        control.setAttribute("autocomplete", "off");
        return control;
    }

    function nativeNodes(field) {
        const wrapper = field && field.$wrapper;
        const nodes = [];
        if (wrapper && wrapper.length) {
            wrapper.find(".control-input, .control-value").each((_, node) => nodes.push(node));
        }
        if (!nodes.length && field && field.$input && field.$input.length) {
            nodes.push(field.$input.get(0));
        }
        return Array.from(new Set(nodes.filter(Boolean)));
    }

    function hideNative(field) {
        nativeNodes(field).forEach((node) => {
            if (node.hasAttribute(NATIVE_HIDDEN_ATTR)) return;
            node.setAttribute(NATIVE_HIDDEN_ATTR, node.style.display || "");
            node.style.display = "none";
        });
    }

    function showNative(field) {
        nativeNodes(field).forEach((node) => {
            if (!node.hasAttribute(NATIVE_HIDDEN_ATTR)) return;
            node.style.display = node.getAttribute(NATIVE_HIDDEN_ATTR) || "";
            node.removeAttribute(NATIVE_HIDDEN_ATTR);
        });
    }

    function removeEditor(field) {
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return;
        wrapper.find(`.${ROOT_CLASS}`).remove();
        showNative(field);
    }

    function hostFor(field) {
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return null;
        // Frappe hides `.control-input` whenever the field status is Read. The
        // detached editor must therefore be a sibling of both native Read/Write
        // surfaces, not a child of the native input container.
        const inputWrapper = wrapper.find(".control-input-wrapper").first();
        return inputWrapper.length ? inputWrapper.get(0) : wrapper.get(0);
    }

    function mountField(frm, fieldname, value, onPatch) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        if (!field) return null;
        removeEditor(field);
        const host = hostFor(field);
        if (!host) return null;

        hideNative(field);
        const root = document.createElement("div");
        root.className = ROOT_CLASS;
        root.dataset.fieldname = fieldname;
        root.style.width = "100%";
        const control = buildControl(field, value);
        root.appendChild(control);
        host.appendChild(root);

        const update = () => {
            if (typeof onPatch !== "function") return;
            onPatch({ [fieldname]: fieldValue(field, control.value) });
        };
        control.addEventListener("input", update);
        control.addEventListener("change", update);
        return control;
    }

    function mount(frm, fieldnames, values, onPatch) {
        const controls = {};
        (fieldnames || []).forEach((fieldname) => {
            const control = mountField(
                frm,
                fieldname,
                values ? values[fieldname] : undefined,
                onPatch
            );
            if (control) controls[fieldname] = control;
        });
        return controls;
    }

    function unmount(frm, fieldnames) {
        (fieldnames || []).forEach((fieldname) => {
            const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
            if (field) removeEditor(field);
        });
    }

    function project(frm, values, fieldnames = null) {
        if (!frm || !frm.doc || !values) return false;
        const names = fieldnames || Object.keys(values);
        names.forEach((fieldname) => {
            if (!Object.prototype.hasOwnProperty.call(values, fieldname)) return;
            frm.doc[fieldname] = values[fieldname];
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (field && typeof field.refresh === "function") field.refresh();
        });
        return true;
    }

    function focus(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const wrapper = field && field.$wrapper;
        const control = wrapper && wrapper.find(`.${ROOT_CLASS} .form-control`).first();
        if (control && control.length) control.trigger("focus");
    }

    window.AlmdinaWorkspaceFieldEditor = Object.freeze({
        mount,
        unmount,
        project,
        focus,
    });
})();
