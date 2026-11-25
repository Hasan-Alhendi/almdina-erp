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
        width_stop_side: "Width Stop Side",
        length_stop_side: "Length Stop Side",
        post_processor: "Post Processor",
        left_stop_cm: "Left Stop (cm)",
        right_stop_cm: "Right Stop (cm)",
        bottom_stop_cm: "Bottom Stop (cm)",
        top_stop_cm: "Top Stop (cm)",
        enabled: "Enabled",
    });

    const PROFILE_FIELDS = Object.freeze({
        profile_name: "Profile Name",
        tool_preset: "Tool",
        final_depth_mm: "Final Depth (mm)",
        safe_z_mm: "Safe Z (mm)",
        home_x_mm: "Home X (mm)",
        home_y_mm: "Home Y (mm)",
        home_z_mm: "Home Z (mm)",
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
        width_stop_side: "Side of the width stop. It is independent of the work zero. The gap is calculated from the machine width and the full board width.",
        length_stop_side: "Side of the length stop. It is independent of the work zero. The gap is calculated from the machine length and the full board length.",
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

    function applyProfileFieldLabels(target) {
        Object.keys(PROFILE_FIELDS).forEach(fieldname => {
            setFieldLabel(target, fieldname, profileLabel(PROFILE_FIELDS[fieldname]));
        });
    }

    function loadProfileToolChoices() {
        const db = window.frappe && frappe.db;
        if (!db || typeof db.get_list !== "function") return Promise.resolve([]);
        return db.get_list("CNC Tool Preset", {
            fields: ["name", "tool_name"],
            filters: { enabled: 1 },
            limit: 500,
        }).then(rows => rows || []).catch(() => []);
    }

    function profileToolRuntime(target) {
        if (!target._profile_tool_runtime) {
            const binding = window.AlmdinaCncProfileToolBinding;
            target._profile_tool_runtime = binding
                ? binding.createRuntimeState()
                : {
                    ready: false,
                    documentKey: "",
                    toolName: "",
                    tool: null,
                    toolChoices: null,
                    loadGeneration: 0,
                };
        }
        return target._profile_tool_runtime;
    }

    function writeProfileToolValue(target, field, value) {
        const next = String(value || "");
        if (target && target.doc) target.doc.tool_preset = next || null;
        if (field && typeof field.set_value === "function") field.set_value(next || null);
        else if (field && field.$input && typeof field.$input.val === "function") {
            field.$input.val(next || "");
        }
    }

    function remountProfileToolPicker(target, force) {
        const binding = window.AlmdinaCncProfileToolBinding;
        if (!binding || !target || !target.doc) return null;
        const field = fieldOf(target, "tool_preset");
        const host = binding.toolHost(field);
        if (!host) return null;
        const state = profileToolRuntime(target);
        state.ready = true;
        return binding.sync(host, state, target.doc, {
            docname: binding.documentKey(target.doc, target.doc.name),
            force: Boolean(force),
            loadTools: loadProfileToolChoices,
            handlers: {
                onToolChange(value) {
                    const next = String(value || "");
                    if (next === String(target.doc.tool_preset || "")) return;
                    writeProfileToolValue(target, field, next);
                    if (!next) {
                        state.tool = null;
                        state.toolName = "";
                        remountProfileToolPicker(target, true);
                        return;
                    }
                    const generation = binding.beginToolLoad(state);
                    if (!window.frappe || typeof frappe.db.get_doc !== "function") return;
                    frappe.db.get_doc("CNC Tool Preset", next).then(doc => {
                        if (!binding.isCurrentToolLoad(state, generation, target.doc, next)) return;
                        state.tool = binding.toolPayloadFromPreset(doc);
                        state.toolName = next;
                        remountProfileToolPicker(target, true);
                    });
                },
            },
        });
    }

    function bindProfileToolPicker(target) {
        return remountProfileToolPicker(target, false);
    }

    function captureProfileToolOverrides(target) {
        const binding = window.AlmdinaCncProfileToolBinding;
        if (!binding || !target) return {};
        const host = binding.toolHost(fieldOf(target, "tool_preset"));
        return binding.collectOverrides(host);
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

    const STOP_SIDE_GROUPS = Object.freeze([
        { field: "width_stop_side", options: ["Left Side", "Right Side"] },
        { field: "length_stop_side", options: ["Bottom Side", "Top Side"] },
    ]);

    function currentStopSide(target, fieldname) {
        const field = fieldOf(target, fieldname);
        const input = field && field.$input && typeof field.$input.val === "function"
            ? String(field.$input.val() || "")
            : "";
        if (input) return input;
        const docValue = target && target.doc ? String(target.doc[fieldname] || "") : "";
        if (docValue) return docValue;
        return field && typeof field.get_value === "function" ? String(field.get_value() || "") : "";
    }

    function applyStopSideRadios(target) {
        if (!target) return;
        STOP_SIDE_GROUPS.forEach(group => {
            const field = fieldOf(target, group.field);
            const wrapper = field && field.$wrapper && typeof field.$wrapper.get === "function"
                ? field.$wrapper.get(0)
                : null;
            if (!wrapper || typeof wrapper.querySelector !== "function") return;
            const select = wrapper.querySelector("select");
            if (select) select.hidden = true;
            let box = wrapper.querySelector(`[data-stop-side-radios="${group.field}"]`);
            if (!box && typeof document !== "undefined" && document.createElement) {
                box = document.createElement("div");
                box.className = "dco-cnc-stop-sides";
                box.setAttribute("data-stop-side-radios", group.field);
                box.setAttribute("role", "radiogroup");
                group.options.forEach(option => {
                    const label = document.createElement("label");
                    label.className = "dco-cnc-stop-sides__choice";
                    const input = document.createElement("input");
                    input.type = "radio";
                    input.name = `cnc-${group.field}`;
                    input.value = option;
                    const text = document.createElement("span");
                    text.textContent = profileLabel(option);
                    label.appendChild(input);
                    label.appendChild(text);
                    box.appendChild(label);
                });
                wrapper.appendChild(box);
                box.addEventListener("change", () => {
                    const chosen = box.querySelector("input:checked");
                    const value = chosen ? chosen.value : "";
                    if (select) select.value = value;
                    if (field.$input && typeof field.$input.val === "function") field.$input.val(value);
                    if (target.doc) target.doc[group.field] = value;
                    if (typeof field.set_value === "function") field.set_value(value);
                });
            }
            if (!box) return;
            const current = currentStopSide(target, group.field);
            box.querySelectorAll("input").forEach(input => {
                input.checked = input.value === current;
            });
        });
    }

    function applyCornerStops(target) {
        if (!target) return;
        const position = workZeroPosition(target);
        STOP_FIELD_NAMES.forEach(fieldname => {
            const field = fieldOf(target, fieldname);
            if (field) pinStopField(field, false);
            if (typeof target.toggle_display === "function") target.toggle_display(fieldname, false);
            if (typeof target.toggle_reqd === "function") target.toggle_reqd(fieldname, false);
            if (typeof target.set_df_property === "function") {
                target.set_df_property(fieldname, "hidden", 1);
                target.set_df_property(fieldname, "reqd", 0);
            }
            if (field) paintStopField(field, false);
        });
        applyStopSideRadios(target);
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

    function canMaintainFactoryCnc() {
        const permissions = window.AlmdinaPermissions;
        if (permissions && typeof permissions.can === "function"
            && permissions.can("edit_factory_cnc_defaults")) {
            return true;
        }
        return !!(window.frappe && frappe.session && frappe.session.user === "Administrator");
    }

    // Desk Form has the same hide_empty_read_only_fields trap as Quick Entry when
    // Custom DocPerm write=0. Restore writable controls for maintainers; server
    // has_permission still gates save.
    function ensureFormFieldsWritable(frm, options) {
        if (!frm || !canMaintainFactoryCnc()) return false;
        const settings = options || {};
        const keepHidden = new Set(settings.keepHidden || []);
        const keepReadOnly = new Set(settings.keepReadOnly || []);
        if (Array.isArray(frm.perm) && frm.perm[0]) {
            frm.perm[0] = Object.assign({}, frm.perm[0], {
                read: 1,
                select: 1,
                write: 1,
                create: 1,
            });
        }
        Object.keys(frm.fields_dict || {}).forEach(name => {
            if (keepHidden.has(name)) return;
            const field = frm.fields_dict[name];
            if (!field || !field.df) return;
            if (Number(field.df.hidden || 0) || Number(field.df.hidden_due_to_dependency || 0)) return;
            field.df.get_status = function getFormStatus(control) {
                const df = control && control.df ? control.df : field.df;
                if (Number(df.hidden || 0) || Number(df.hidden_due_to_dependency || 0)) {
                    return "None";
                }
                if (keepReadOnly.has(name) || Number(df.read_only || 0) || df.fieldtype === "Read Only") {
                    return "Read";
                }
                return "Write";
            };
            if (field.df.fieldtype === "Select") field.last_options = null;
            if (typeof field.refresh === "function") field.refresh();
            if (field.df.fieldtype === "Select" && typeof field.set_options === "function") {
                field.last_options = null;
                const selected = field.doc && name in field.doc ? field.doc[name] : field.value;
                field.set_options(selected);
                if (selected != null && field.$input && typeof field.$input.val === "function") {
                    field.$input.val(selected);
                }
            }
        });
        return true;
    }

    // Quick Entry attaches doctype/docname then refreshes controls. When the
    // client-side Custom DocPerm for CNC Machine / CNC Tool Preset is
    // read-only (write=0) and System Settings hide_empty_read_only_fields is
    // on, empty create fields become disp_status None and disappear. Keep
    // Quick Entry candidates writable/visible; server has_permission still
    // gates save.
    function ensureQuickEntryFieldsWritable(dialog) {
        if (!dialog) return;
        const allowed = new Set(
            (dialog.docfields || [])
                .map(df => (df && df.fieldname) || "")
                .filter(Boolean)
        );
        Object.keys(dialog.fields_dict || {}).forEach(name => {
            if (!allowed.has(name) || STOP_FIELD_NAMES.includes(name)) return;
            const field = dialog.fields_dict[name];
            if (!field || !field.df) return;
            field.df.get_status = function getQuickEntryStatus(control) {
                const df = control && control.df ? control.df : field.df;
                if (Number(df.hidden || 0) || Number(df.hidden_due_to_dependency || 0)) {
                    return "None";
                }
                return "Write";
            };
            // Select.set_options records last_options even when $input is missing
            // (Read-only path). Later make_input skips rebuild and leaves an empty
            // <select>. Clear the cache and force options back onto the DOM.
            if (field.df.fieldtype === "Select") field.last_options = null;
            if (typeof field.refresh === "function") field.refresh();
            if (field.df.fieldtype === "Select" && typeof field.set_options === "function") {
                field.last_options = null;
                const selected = field.doc && name in field.doc
                    ? field.doc[name]
                    : field.value;
                field.set_options(selected);
                if (selected != null && field.$input && typeof field.$input.val === "function") {
                    field.$input.val(selected);
                }
            }
        });
    }

    function finishQuickEntry(doctype, entry) {
        const dialog = entry || (window.frappe && window.frappe.quick_entry);
        if (!dialog) return;
        if (doctype === "CNC Tool Preset") {
            applyToolFieldLabels(dialog);
            ensureQuickEntryFieldsWritable(dialog);
        }
        if (doctype === "CNC Machine") {
            applyMachineFieldLabels(dialog);
            ensureQuickEntryFieldsWritable(dialog);
            applyCornerStops(dialog);
            bindMachineWorkZero(dialog);
            applyPostProcessorChoice(dialog);
        }
        if (doctype === "CNC Machining Profile") {
            applyProfileFieldLabels(dialog);
            ensureQuickEntryFieldsWritable(dialog);
            bindProfileToolPicker(dialog);
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
        if (!form.CNCMachiningProfileQuickEntryForm) {
            form.CNCMachiningProfileQuickEntryForm = class CNCMachiningProfileQuickEntryForm extends form.QuickEntryForm {
                render_dialog() {
                    // Fresh runtime per modal so cancel/save never leaks tool state.
                    this._profile_tool_runtime = null;
                    copyQuickEntryFields(this);
                    const rendered = super.render_dialog();
                    scheduleQuickEntry(this.doctype, this);
                    return rendered;
                }

                update_doc(data) {
                    const values = typeof data === "undefined" ? this.get_values(true) : data;
                    const result = super.update_doc(values);
                    this.doc.tool_values_json = captureProfileToolOverrides(this);
                    if (!this.doc.tool_preset) {
                        const field = fieldOf(this, "tool_preset");
                        const host = window.AlmdinaCncProfileToolBinding
                            && window.AlmdinaCncProfileToolBinding.toolHost(field);
                        const picker = host && typeof host.data === "function" ? host.data("picker") : null;
                        if (picker && typeof picker.getValues === "function") {
                            const selected = picker.getValues();
                            if (selected && selected.tool) this.doc.tool_preset = selected.tool;
                        }
                    }
                    return result;
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
        applyProfileFieldLabels,
        applyCornerStops,
        ensureFormFieldsWritable,
        canMaintainFactoryCnc,
        installQuickEntryForms,
        bindProfileToolPicker,
        captureProfileToolOverrides,
        POST_PROCESSOR_ID,
        POST_PROCESSOR_LABEL,
    });

    installQuickEntryForms();
    if (window.frappe && typeof window.frappe.ready === "function") {
        window.frappe.ready(installQuickEntryForms);
    }
})();
