(() => {
    "use strict";

    if (window.AlmdinaUi) return;

    const BUTTON_VARIANTS = Object.freeze({
        primary: "btn alm-btn-primary",
        secondary: "btn btn-default",
        danger: "btn alm-btn-danger",
        success: "btn alm-btn-success",
    });

    function escapeHtml(value) {
        const runtime = window.frappe;
        if (runtime && runtime.utils && typeof runtime.utils.escape_html === "function") {
            return runtime.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function htmlAttr(name, value) {
        if (value === undefined || value === null || value === false) return "";
        return ` ${String(name)}="${escapeHtml(value)}"`;
    }

    function button(options = {}) {
        const variant = String(options.variant || "secondary").trim();
        const size = String(options.size || "").trim();
        const className = String(options.className || "").trim();
        const label = String(options.label || "");
        const type = String(options.type || "button").trim() || "button";
        const disabled = options.disabled === true;
        const attrs = options.attrs && typeof options.attrs === "object" ? options.attrs : {};
        const classes = [
            BUTTON_VARIANTS[variant] || BUTTON_VARIANTS.secondary,
            size,
            className,
        ].filter(Boolean).join(" ");
        const extraAttrs = Object.entries(attrs)
            .map(([key, value]) => htmlAttr(key, value))
            .join("");

        return `<button type="${escapeHtml(type)}" class="${classes}"${disabled ? " disabled" : ""}${extraAttrs}>${escapeHtml(label)}</button>`;
    }

    function empty(options = {}) {
        const message = String(options.message || "");
        const title = String(options.title || "").trim();
        const className = String(options.className || "").trim();
        const action = String(options.actionHtml || "").trim();
        const classes = ["alm-empty", className].filter(Boolean).join(" ");
        const titleHtml = title ? `<strong>${escapeHtml(title)}</strong>` : "";
        const actionHtml = action ? `<div class="alm-empty-action">${action}</div>` : "";

        return `<div class="${classes}" role="status">${titleHtml}${escapeHtml(message)}${actionHtml}</div>`;
    }

    function resolveParent(parent) {
        if (!parent) return null;
        if (parent.jquery) return parent;
        if (parent instanceof Element) return $(parent);
        return $(parent);
    }

    function control(options = {}) {
        const runtime = window.frappe;
        if (!runtime || !runtime.ui || !runtime.ui.form || typeof runtime.ui.form.make_control !== "function") {
            throw new Error("frappe.ui.form.make_control is required for AlmdinaUi.control");
        }
        const $parent = resolveParent(options.parent);
        if (!$parent || !$parent.length) {
            throw new Error("AlmdinaUi.control requires a parent element");
        }

        const fieldname = String(options.fieldname || options.name || "control").trim() || "control";
        const fieldtype = String(options.fieldtype || "Data").trim() || "Data";
        const extraDf = options.df && typeof options.df === "object" ? options.df : {};
        const defaultValue = options.value !== undefined ? options.value : options.default;
        const df = Object.assign(
            {
                fieldname,
                fieldtype,
                label: options.label || "",
                placeholder: options.placeholder || "",
                read_only: options.readOnly ? 1 : 0,
                reqd: options.required ? 1 : 0,
            },
            extraDf,
            {
                fieldname,
                fieldtype,
            }
        );
        if (defaultValue !== undefined && defaultValue !== null && df.default === undefined) {
            df.default = defaultValue;
        }
        if (options.options !== undefined && df.options === undefined) {
            df.options = options.options;
        }

        const className = String(options.className || "").trim();
        const onlyInput = options.onlyInput !== false;
        $parent.empty().addClass("alm-control");
        if (className) $parent.addClass(className);

        const frappeControl = runtime.ui.form.make_control({
            df,
            parent: $parent,
            render_input: true,
            only_input: onlyInput,
        });
        frappeControl.refresh();
        if (defaultValue !== undefined && defaultValue !== null && String(defaultValue) !== "") {
            frappeControl.set_value(defaultValue);
        }

        const onChange = typeof options.onChange === "function" ? options.onChange : null;
        const input = frappeControl.$input;
        let restoreChange = null;
        if (onChange) {
            const notify = () => onChange(frappeControl.get_value(), frappeControl);
            if (input && typeof input.on === "function") {
                input.on("input change", notify);
            }
            const previousChange = frappeControl.change;
            frappeControl.change = function patchedChange() {
                if (typeof previousChange === "function") {
                    previousChange.apply(this, arguments);
                }
                notify();
            };
            restoreChange = () => {
                if (input && typeof input.off === "function") {
                    input.off("input change");
                }
                frappeControl.change = previousChange;
            };
        }

        function dispose() {
            if (restoreChange) restoreChange();
            $parent.empty().removeClass("alm-control");
            if (className) $parent.removeClass(className);
        }

        return Object.freeze({
            control: frappeControl,
            dispose,
            getValue() {
                return frappeControl.get_value();
            },
            setValue(value) {
                frappeControl.set_value(value);
            },
            focus() {
                if (input && typeof input.focus === "function") input.focus();
            },
        });
    }

    function filterGroup(options = {}) {
        const runtime = window.frappe;
        if (!runtime || !runtime.ui || typeof runtime.ui.FieldGroup !== "function") {
            throw new Error("frappe.ui.FieldGroup is required for AlmdinaUi.filterGroup");
        }
        const $parent = resolveParent(options.parent);
        if (!$parent || !$parent.length) {
            throw new Error("AlmdinaUi.filterGroup requires a parent element");
        }

        const className = String(options.className || "").trim();
        $parent.empty().addClass("alm-filter-group");
        if (className) $parent.addClass(className);

        const fields = Array.isArray(options.fields) ? options.fields.slice() : [];
        const fieldGroup = new runtime.ui.FieldGroup({
            parent: $parent,
            fields,
            no_submit_on_enter: options.noSubmitOnEnter !== false,
        });
        fieldGroup.make();

        const initialValues = options.values && typeof options.values === "object" ? options.values : {};
        Object.entries(initialValues).forEach(([fieldname, value]) => {
            if (fieldGroup.fields_dict[fieldname]) {
                fieldGroup.set_value(fieldname, value);
            }
        });

        const onChange = typeof options.onChange === "function" ? options.onChange : null;
        const restoreHandlers = [];
        if (onChange) {
            for (const field of fieldGroup.fields_list || []) {
                const previousChange = field.change;
                field.change = function patchedChange() {
                    if (typeof previousChange === "function") {
                        previousChange.apply(this, arguments);
                    }
                    onChange(field.df.fieldname, field.get_value(), getValues());
                };
                restoreHandlers.push(() => {
                    field.change = previousChange;
                });
            }
        }

        function getValues() {
            return fieldGroup.get_values(true) || {};
        }

        function setValue(fieldname, value) {
            if (fieldGroup.fields_dict[fieldname]) {
                fieldGroup.set_value(fieldname, value);
            }
        }

        function dispose() {
            while (restoreHandlers.length) restoreHandlers.pop()();
            $parent.empty().removeClass("alm-filter-group");
            if (className) $parent.removeClass(className);
        }

        return Object.freeze({
            fieldGroup,
            dispose,
            getValues,
            getValue(fieldname) {
                const field = fieldGroup.fields_dict[fieldname];
                return field && typeof field.get_value === "function" ? field.get_value() : undefined;
            },
            setValue,
            setValues(values = {}) {
                Object.entries(values).forEach(([fieldname, value]) => setValue(fieldname, value));
            },
            focus(fieldname) {
                const field = fieldGroup.fields_dict[fieldname];
                if (field && typeof field.set_focus === "function") field.set_focus();
            },
        });
    }

    const FILE_UPLOADER_PRESETS = Object.freeze({
        securePrivate: Object.freeze({
            folder: "Home/Attachments",
            make_attachments_public: false,
            allow_toggle_private: false,
            allow_multiple: false,
            disable_file_browser: true,
            allow_web_link: false,
            allow_take_photo: false,
        }),
    });

    function fileUploader(options = {}) {
        const runtime = window.frappe;
        if (!runtime || !runtime.ui || typeof runtime.ui.FileUploader !== "function") {
            throw new Error("frappe.ui.FileUploader is required for AlmdinaUi.fileUploader");
        }
        const presetName = String(options.preset || "").trim();
        const preset = presetName && FILE_UPLOADER_PRESETS[presetName]
            ? FILE_UPLOADER_PRESETS[presetName]
            : {};
        const merged = Object.assign({}, preset, options);
        delete merged.preset;
        return new runtime.ui.FileUploader(merged);
    }

    window.AlmdinaUi = Object.freeze({
        button,
        control,
        filterGroup,
        fileUploader,
        fileUploaderPresets: FILE_UPLOADER_PRESETS,
        empty,
        escapeHtml,
    });
})();
