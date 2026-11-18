(() => {
    "use strict";

    if (window.AlmdinaCncLabels) return;

    const TOOL_ARABIC_ONLY = new Set([
        "Tool Name",
        "Tool Number",
        "Tool Diameter (mm)",
        "Diameter (D)",
        "Diameter (mm)",
        "Spindle Speed (RPM)",
        "Spindle Speed (rpm)",
    ]);

    const TOOL_ENGLISH_NAME = {
        "Stepdown": "Stepdown",
        "Stepdown (mm)": "Stepdown",
        "Final Tool Offset": "Final Tool Offset",
        "Final Tool Offset (mm)": "Final Tool Offset",
        "Stepover Size": "Stepover - mm",
        "Stepover Size (mm)": "Stepover - mm",
        "Stepover size (mm)": "Stepover - mm",
        "Stepover size": "Stepover - mm",
        "Stepover Percent of D": "Stepover - %",
        "Stepover percent of D": "Stepover - %",
        "Stepover Percent": "Stepover - %",
        "Feed Rate (mm/sec)": "Feed Rate",
        "Feed Rate (mm/min)": "Feed Rate",
        "Plunge Rate (mm/sec)": "Plunge Rate",
        "Plunge Rate (mm/min)": "Plunge Rate",
        "Notes": "Notes",
        "Enabled": "Enabled",
    };

    // Catalog keys whose Arabic text is the label itself, without a second unit clause.
    const TOOL_ARABIC_KEY = {
        "Feed Rate (mm/sec)": "Feed Rate",
        "Feed Rate (mm/min)": "Feed Rate",
        "Plunge Rate (mm/sec)": "Plunge Rate",
        "Plunge Rate (mm/min)": "Plunge Rate",
    };

    const STOP_FIELDS = Object.freeze({
        "Bottom Left": ["left_stop_cm", "bottom_stop_cm"],
        "Bottom Right": ["right_stop_cm", "bottom_stop_cm"],
        "Top Left": ["left_stop_cm", "top_stop_cm"],
        "Top Right": ["right_stop_cm", "top_stop_cm"],
    });

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function pageLanguageIsArabic() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.currentLanguage === "function") {
            return String(locale.currentLanguage()).toLowerCase().split("-")[0] === "ar";
        }
        const boot = window.frappe && window.frappe.boot;
        const language = boot && (boot.lang || (boot.user && boot.user.language));
        if (language) return String(language).toLowerCase().split("-")[0] === "ar";
        const htmlLanguage = document.documentElement && document.documentElement.lang;
        if (htmlLanguage) return String(htmlLanguage).toLowerCase().split("-")[0] === "ar";
        return true;
    }

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof window.__ === "function") return window.__(message);
        return String(message == null ? "" : message);
    }

    function profileLabel(english) {
        const source = String(english || "");
        if (!pageLanguageIsArabic()) return source;
        return translate(source);
    }

    function toolLabel(english) {
        const source = String(english || "");
        if (!pageLanguageIsArabic()) return source;
        const arabic = translate(TOOL_ARABIC_KEY[source] || source);
        if (TOOL_ARABIC_ONLY.has(source)) return arabic;
        const englishName = TOOL_ENGLISH_NAME[source] || source.replace(/\s*\([^)]*\)\s*$/, "");
        return `${arabic} (${englishName})`;
    }

    function activeStopFields(position) {
        return (STOP_FIELDS[String(position || "")] || []).slice();
    }

    function toolDisclosureButton(label, open) {
        const expanded = open !== false;
        return `<button type="button" class="dco-tool-disclosure" data-tool-settings-toggle aria-expanded="${expanded ? "true" : "false"}">
            <span class="dco-tool-disclosure__chevron" aria-hidden="true"></span>
            <span class="dco-tool-disclosure__label">${escapeHtml(label)}</span>
        </button>`;
    }

    const TOOL_PRESET_FIELDS = Object.freeze({
        tool_name: "Tool Name",
        tool_number: "Tool Number",
        tool_diameter_mm: "Tool Diameter (mm)",
        spindle_speed_rpm: "Spindle Speed (RPM)",
        notes: "Notes",
        stepdown_mm: "Stepdown",
        final_tool_offset_mm: "Final Tool Offset",
        stepover_size_mm: "Stepover Size",
        stepover_percent: "Stepover Percent of D",
        feed_rate_mm_sec: "Feed Rate (mm/sec)",
        plunge_rate_mm_sec: "Plunge Rate (mm/sec)",
        enabled: "Enabled",
    });

    const MACHINE_FIELDS = Object.freeze({
        machine_name: "Machine Name",
        width_cm: "Machine Width (cm)",
        length_cm: "Machine Length (cm)",
        work_zero_position: "Work Zero Position",
        post_processor: "Post Processor",
        left_stop_cm: "Left Stop (cm)",
        right_stop_cm: "Right Stop (cm)",
        bottom_stop_cm: "Bottom Stop (cm)",
        top_stop_cm: "Top Stop (cm)",
        enabled: "Enabled",
    });

    const POST_PROCESSOR_ID = "ima_wh_ncstudio";
    const POST_PROCESSOR_LABEL = "IMA-WH (*.nc)";
    const STOP_FIELD_NAMES = ["left_stop_cm", "right_stop_cm", "bottom_stop_cm", "top_stop_cm"];
    const TOOL_DESCRIPTIONS = Object.freeze({
        tool_number: "Positive whole number, for example 9. One board file uses one tool number.",
    });
    const MACHINE_DESCRIPTIONS = Object.freeze({
        width_cm: "Usable machine bed width on the X axis. Entered in centimetres.",
        length_cm: "Usable machine bed length on the Y axis. Entered in centimetres.",
        work_zero_position: "G54 origin used when NC coordinates are written. It does not move the sheet, reverse the axes, or change path geometry.",
        post_processor: "NC dialect used when a new file is generated for this machine.",
        left_stop_cm: "Used only for Bottom Left and Top Left. Distance from the machine left edge to the sheet left edge, in centimetres. Zero is valid.",
        right_stop_cm: "Used only for Bottom Right and Top Right. Distance from the machine right edge to the sheet right edge, in centimetres. Zero is valid.",
        bottom_stop_cm: "Used only for Bottom Left and Bottom Right. Distance from the machine bottom edge to the sheet bottom edge, in centimetres. Zero is valid.",
        top_stop_cm: "Used only for Top Left and Top Right. Distance from the machine top edge to the sheet top edge, in centimetres. Zero is valid.",
    });

    function fieldOf(target, name) {
        if (!target) return null;
        if (target.fields_dict && target.fields_dict[name]) return target.fields_dict[name];
        if (typeof target.get_field === "function") return target.get_field(name);
        return null;
    }

    function writeControlLabel(field, text) {
        if (!field) return;
        field.labelText = text;
        const node = field.label_span
            || (field.$wrapper && typeof field.$wrapper.find === "function"
                ? field.$wrapper.find("label").get(0)
                : null);
        if (node) node.textContent = text;
        const wrapper = field.$wrapper;
        const label = wrapper && typeof wrapper.find === "function" ? wrapper.find(".control-label").first() : null;
        if (label && typeof label.text === "function") label.text(text);
    }

    function pinControlLabel(field, text) {
        if (!field || !field.df) return;
        field.df._almdina_display_label = text;
        field.df.label = text;
        if (!field.__almdinaLabelPinned) {
            field.__almdinaLabelPinned = true;
            const original = typeof field.set_label === "function" ? field.set_label : null;
            field.set_label = function pinnedLabel() {
                const display = this.df && this.df._almdina_display_label;
                if (!display) {
                    if (typeof original === "function") return original.apply(this, arguments);
                    return undefined;
                }
                this.df.label = display;
                this._label = display;
                if (typeof original === "function") original.call(this, display);
                writeControlLabel(this, display);
                return undefined;
            };
        }
        field.set_label(text);
    }

    function writeControlDescription(field, text) {
        if (!field) return;
        field.helpText = text;
        const help = field.$wrapper && typeof field.$wrapper.find === "function"
            ? field.$wrapper.find(".help-box").get(0)
            : null;
        if (help) help.textContent = text;
    }

    function pinControlDescription(field, source) {
        if (!field || !field.df || !source) return;
        field.df._almdina_description_source = source;
        if (!field.__almdinaDescriptionPinned) {
            field.__almdinaDescriptionPinned = true;
            const original = typeof field.set_description === "function" ? field.set_description : null;
            field.set_description = function pinnedDescription() {
                const english = this.df && this.df._almdina_description_source;
                const text = pageLanguageIsArabic() ? translate(english) : english;
                this.df.description = text;
                this._description = text;
                if (typeof original === "function") original.call(this, text);
                writeControlDescription(this, text);
            };
        }
        field.set_description();
    }

    function setFieldLabel(target, fieldname, text) {
        const field = fieldOf(target, fieldname);
        if (!field) return;
        pinControlLabel(field, text);
    }

    function applyDescribedFields(target, descriptions) {
        Object.keys(descriptions).forEach(fieldname => {
            pinControlDescription(fieldOf(target, fieldname), descriptions[fieldname]);
        });
    }

    function applyToolFieldLabels(target) {
        Object.keys(TOOL_PRESET_FIELDS).forEach(fieldname => {
            setFieldLabel(target, fieldname, toolLabel(TOOL_PRESET_FIELDS[fieldname]));
        });
        applyDescribedFields(target, TOOL_DESCRIPTIONS);
    }

    function applyPostProcessorChoice(target) {
        const field = fieldOf(target, "post_processor");
        if (!field) return;
        const text = profileLabel(POST_PROCESSOR_LABEL);
        const input = field.$input && typeof field.$input.get === "function" ? field.$input.get(0) : null;
        const options = input && input.options;
        if (!options || typeof options.length !== "number") return;
        for (let index = 0; index < options.length; index += 1) {
            if (options[index].value === POST_PROCESSOR_ID) options[index].textContent = text;
        }
    }

    function applyMachineFieldLabels(target) {
        Object.keys(MACHINE_FIELDS).forEach(fieldname => {
            setFieldLabel(target, fieldname, profileLabel(MACHINE_FIELDS[fieldname]));
        });
        applyDescribedFields(target, MACHINE_DESCRIPTIONS);
        applyPostProcessorChoice(target);
    }

    function knownWorkZero(value) {
        return Object.prototype.hasOwnProperty.call(STOP_FIELDS, String(value || ""));
    }

    function workZeroPosition(target) {
        const field = fieldOf(target, "work_zero_position");
        const input = field && field.$input && typeof field.$input.val === "function"
            ? String(field.$input.val() || "")
            : "";
        if (knownWorkZero(input)) return input;
        const docValue = target && target.doc ? String(target.doc.work_zero_position || "") : "";
        if (knownWorkZero(docValue)) return docValue;
        const getter = field && typeof field.get_value === "function" ? String(field.get_value() || "") : "";
        if (knownWorkZero(getter)) return getter;
        const fallback = field && field.df ? String(field.df.default || "") : "";
        return knownWorkZero(fallback) ? fallback : "";
    }

    function paintStopField(field, show) {
        if (!field) return;
        if (field.df) {
            field.df.hidden = show ? 0 : 1;
            field.df.reqd = show ? 1 : 0;
            field.df._almdina_stop_visible = show;
        }
        const wrapper = field.$wrapper;
        if (wrapper && typeof wrapper.toggle === "function") wrapper.toggle(Boolean(show));
        if (wrapper && typeof wrapper.toggleClass === "function") wrapper.toggleClass("hide-control", !show);
        const node = wrapper && typeof wrapper.get === "function" ? wrapper.get(0) : field.wrapper;
        if (node && node.style) node.style.display = show ? "" : "none";
    }

    function pinStopField(field, show) {
        if (!field || !field.df) return;
        field.df._almdina_stop_visible = show;
        if (!field.__almdinaStopPinned) {
            field.__almdinaStopPinned = true;
            const original = typeof field.refresh === "function" ? field.refresh : null;
            field.refresh = function pinnedRefresh() {
                if (typeof original === "function") original.call(this);
                const visible = Boolean(this.df && this.df._almdina_stop_visible);
                paintStopField(this, visible);
            };
        }
        paintStopField(field, show);
    }

    function applyCornerStops(target) {
        if (!target) return;
        const position = workZeroPosition(target);
        const active = activeStopFields(position);
        STOP_FIELD_NAMES.forEach(fieldname => {
            const show = active.indexOf(fieldname) >= 0;
            const field = fieldOf(target, fieldname);
            if (field) pinStopField(field, show);
            if (typeof target.toggle_display === "function") target.toggle_display(fieldname, show);
            if (typeof target.toggle_reqd === "function") target.toggle_reqd(fieldname, show);
            if (typeof target.set_df_property === "function") {
                target.set_df_property(fieldname, "hidden", show ? 0 : 1);
                target.set_df_property(fieldname, "reqd", show ? 1 : 0);
            }
            if (field) paintStopField(field, show);
        });
        const retired = position === "Center";
        if (typeof target.set_intro === "function") {
            target.set_intro(retired
                ? translate("This CNC machine still uses Center as its work zero. Choose Bottom Left, Bottom Right, Top Left, or Top Right before generating a new file.")
                : "");
        }
    }

    function rawWorkZero(field) {
        const input = field && field.$input;
        if (input && typeof input.val === "function" && knownWorkZero(input.val())) return String(input.val());
        const element = input && typeof input.get === "function" ? input.get(0) : null;
        if (element && knownWorkZero(element.value)) return String(element.value);
        if (field && typeof field.get_value === "function" && knownWorkZero(field.get_value())) {
            return String(field.get_value());
        }
        return "";
    }

    function bindMachineWorkZero(target) {
        const field = fieldOf(target, "work_zero_position");
        if (!field || !field.df) return;
        if (!field.df.__almdinaStopsBound) {
            field.df.__almdinaStopsBound = true;
            const previous = field.df.change;
            field.df.change = function changed() {
                const value = rawWorkZero(field);
                if (target.doc && knownWorkZero(value)) target.doc.work_zero_position = value;
                applyCornerStops(target);
                if (typeof previous === "function") return previous.apply(this, arguments);
            };
        }
        const input = field.$input;
        if (input && typeof input.on === "function" && !input.__almdinaStopsBound) {
            input.__almdinaStopsBound = true;
            input.on("change", () => field.df.change.call(field));
        }
        const element = input && typeof input.get === "function" ? input.get(0) : null;
        if (element && typeof element.addEventListener === "function" && !element.__almdinaStopsBound) {
            element.__almdinaStopsBound = true;
            element.addEventListener("change", () => field.df.change.call(field));
        }
    }

    function copyQuickEntryFields(entry) {
        entry.docfields = (entry.docfields || []).map(df => Object.assign({}, df));
    }

    function finishQuickEntry(doctype, entry) {
        const dialog = entry || (window.frappe && window.frappe.quick_entry);
        if (!dialog) return;
        if (doctype === "CNC Tool Preset") applyToolFieldLabels(dialog);
        if (doctype === "CNC Machine") {
            applyMachineFieldLabels(dialog);
            applyCornerStops(dialog);
            bindMachineWorkZero(dialog);
            applyPostProcessorChoice(dialog);
        }
    }

    function scheduleQuickEntry(doctype, entry) {
        finishQuickEntry(doctype, entry);
        const again = () => finishQuickEntry(doctype, entry || (window.frappe && window.frappe.quick_entry));
        if (window.Promise && typeof window.Promise.resolve === "function") window.Promise.resolve().then(again);
        if (typeof window.setTimeout === "function") window.setTimeout(again, 0);
    }

    function wrapMakeQuickEntry(form) {
        if (typeof form.make_quick_entry !== "function" || form.make_quick_entry.__almdinaQuickEntry) return;
        const original = form.make_quick_entry;
        function wrapped(doctype) {
            const result = original.apply(this, arguments);
            const applyNow = () => scheduleQuickEntry(doctype, window.frappe && window.frappe.quick_entry);
            if (result && typeof result.then === "function") {
                return result.then(value => {
                    applyNow();
                    return value;
                });
            }
            applyNow();
            return result;
        }
        wrapped.__almdinaQuickEntry = true;
        form.make_quick_entry = wrapped;
    }

    function installQuickEntryForms() {
        const form = window.frappe && window.frappe.ui && window.frappe.ui.form;
        if (!form || typeof form.QuickEntryForm !== "function") return false;
        if (!form.CNCToolPresetQuickEntryForm) {
            form.CNCToolPresetQuickEntryForm = class CNCToolPresetQuickEntryForm extends form.QuickEntryForm {
                render_dialog() {
                    copyQuickEntryFields(this);
                    const rendered = super.render_dialog();
                    scheduleQuickEntry(this.doctype, this);
                    return rendered;
                }
            };
        }
        if (!form.CNCMachineQuickEntryForm) {
            form.CNCMachineQuickEntryForm = class CNCMachineQuickEntryForm extends form.QuickEntryForm {
                render_dialog() {
                    copyQuickEntryFields(this);
                    const rendered = super.render_dialog();
                    scheduleQuickEntry(this.doctype, this);
                    return rendered;
                }
            };
        }
        wrapMakeQuickEntry(form);
        return true;
    }

    window.AlmdinaCncLabels = Object.freeze({
        pageLanguageIsArabic,
        profileLabel,
        toolLabel,
        activeStopFields,
        toolDisclosureButton,
        escapeHtml,
        applyToolFieldLabels,
        applyMachineFieldLabels,
        applyCornerStops,
        installQuickEntryForms,
        POST_PROCESSOR_ID,
        POST_PROCESSOR_LABEL,
    });

    installQuickEntryForms();
    if (window.frappe && typeof window.frappe.ready === "function") {
        window.frappe.ready(installQuickEntryForms);
    }
})();
