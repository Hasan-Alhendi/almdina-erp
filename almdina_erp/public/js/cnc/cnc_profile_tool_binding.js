(() => {
    "use strict";

    if (window.AlmdinaCncProfileToolBinding) return;

    const PROFILE_TOOL_FIELDS = Object.freeze([
        ["tool_number", "Tool Number"],
        ["stepdown_mm", "Stepdown"],
        ["stepover_size_mm", "Stepover Size (mm)"],
        ["feed_rate_mm_sec", "Feed Rate (mm/sec)"],
        ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)"],
        ["spindle_speed_rpm", "Spindle Speed (RPM)"],
    ]);

    function translate(message) {
        return typeof window.__ === "function" ? window.__(message) : String(message || "");
    }

    function profileLabel(message) {
        const labelsApi = window.AlmdinaCncLabels;
        if (labelsApi && typeof labelsApi.profileLabel === "function") return labelsApi.profileLabel(message);
        return translate(message);
    }

    function toolLabel(message) {
        const labelsApi = window.AlmdinaCncLabels;
        if (labelsApi && typeof labelsApi.toolLabel === "function") return labelsApi.toolLabel(message);
        return translate(message);
    }

    function documentKey(doc, docname) {
        if (docname) return String(docname);
        if (doc && doc.name) return String(doc.name);
        return "";
    }

    function storedTool(doc) {
        const raw = doc && doc.tool_values_json;
        if (raw && typeof raw === "object") return Object.assign({}, raw);
        if (typeof raw === "string" && raw.trim()) {
            try {
                const parsed = JSON.parse(raw);
                return parsed && typeof parsed === "object" ? parsed : {};
            } catch (_error) {
                return {};
            }
        }
        return {};
    }

    function displayToolNumber(value) {
        if (value == null || value === "") return "";
        const raw = String(value).trim();
        const match = raw.match(/^(?:T)?([1-9][0-9]{0,2})$/i);
        return match ? match[1] : raw;
    }

    function createRuntimeState() {
        return {
            ready: false,
            documentKey: "",
            toolName: "",
            tool: null,
            toolChoices: null,
            loadGeneration: 0,
        };
    }

    function resetRuntimeForDocument(state, nextKey) {
        const runtime = state || createRuntimeState();
        runtime.documentKey = String(nextKey || "");
        runtime.toolName = "";
        runtime.tool = null;
        runtime.loadGeneration = Number(runtime.loadGeneration || 0) + 1;
        return runtime;
    }

    function needsDocumentReset(state, nextKey) {
        return String((state && state.documentKey) || "") !== String(nextKey || "");
    }

    function seedToolFromDocument(state, doc) {
        const selected = String((doc && doc.tool_preset) || "");
        if (!selected) {
            state.tool = null;
            state.toolName = "";
            return state;
        }
        if (!state.tool || String(state.toolName || "") !== selected) {
            state.tool = storedTool(doc);
        }
        state.toolName = selected;
        return state;
    }

    function toolChoices(rows, doc, tool) {
        const selected = String((doc && doc.tool_preset) || "");
        const snapshot = tool || storedTool(doc);
        const choices = (rows || []).map(row => ({
            value: row.name,
            label: row.tool_name || row.name,
        }));
        if (selected && !choices.some(row => row.value === selected)) {
            choices.unshift({
                value: selected,
                label: snapshot.tool_name || snapshot.description || selected,
            });
        }
        return choices;
    }

    function toolHost(field) {
        if (!field || !field.$wrapper) return null;
        const native = field.$wrapper.find(".control-input-wrapper, .control-input");
        if (native && native.addClass) native.addClass("dco-tool-picker-native");
        let host = field.$wrapper.children("[data-tool-picker-host]");
        if (!host.length) {
            host = window.jQuery
                ? window.jQuery('<div data-tool-picker-host></div>')
                : null;
            if (!host) return null;
            field.$wrapper.append(host);
        }
        return host;
    }

    function clearToolHost(host) {
        if (!host) return;
        if (typeof host.removeData === "function") {
            host.removeData("picker");
            host.removeData("profileDocKey");
            host.removeData("profileDocTool");
        }
        if (typeof host.empty === "function") host.empty();
        else if (host.get && host.get(0)) host.get(0).innerHTML = "";
    }

    function collectOverrides(host) {
        const overrides = {};
        PROFILE_TOOL_FIELDS.forEach(([fieldname]) => {
            const input = host && host.find(`[data-profile-tool="${fieldname}"]`);
            if (!input || !input.length || input.val() === "") return;
            overrides[fieldname] = fieldname === "tool_number" ? input.val() : Number(input.val());
        });
        return overrides;
    }

    function toolPayloadFromPreset(doc) {
        return {
            description: doc.tool_name,
            tool_name: doc.tool_name,
            tool_preset: doc.name,
            tool_type: doc.tool_type,
            tool_number: displayToolNumber(doc.tool_number),
            tool_units: doc.tool_units,
            rate_units: doc.rate_units,
            notes: doc.notes || "",
            diameter_mm: doc.tool_diameter_mm,
            tool_diameter_mm: doc.tool_diameter_mm,
            stepdown_mm: doc.stepdown_mm,
            final_tool_offset_mm: doc.final_tool_offset_mm,
            stepover_size_mm: doc.stepover_size_mm,
            stepover_percent: doc.stepover_percent,
            spindle_speed_rpm: doc.spindle_speed_rpm,
            feed_rate_mm_sec: doc.feed_rate_mm_sec,
            plunge_rate_mm_sec: doc.plunge_rate_mm_sec,
            enabled: doc.enabled,
        };
    }

    function ensureToolChoices(state, loader) {
        if (Array.isArray(state.toolChoices)) return Promise.resolve(state.toolChoices);
        if (typeof loader !== "function") {
            state.toolChoices = [];
            return Promise.resolve(state.toolChoices);
        }
        return Promise.resolve(loader()).then(rows => {
            state.toolChoices = rows || [];
            return state.toolChoices;
        }).catch(() => {
            state.toolChoices = [];
            return state.toolChoices;
        });
    }

    function paint(host, state, doc, handlers) {
        const pickerApi = window.AlmdinaCncToolPicker;
        if (!host || !pickerApi || typeof pickerApi.mount !== "function") return null;
        clearToolHost(host);
        const selected = String((doc && doc.tool_preset) || "");
        const tool = state.tool || storedTool(doc);
        state.tool = selected ? tool : null;
        state.toolName = selected;
        const picker = pickerApi.mount(host.get(0), {
            showLabel: false,
            label: profileLabel("Tool"),
            changeLabel: profileLabel("Tool"),
            emptyLabel: profileLabel("Choose a tool"),
            selected,
            selectedLabel: (tool && (tool.description || tool.tool_name)) || selected,
            tools: toolChoices(state.toolChoices, doc, tool),
            settingAttribute: "data-profile-tool",
            selectAttribute: "data-profile-tool-select",
            fields: selected ? PROFILE_TOOL_FIELDS.map(([fieldname, label]) => ({
                name: fieldname,
                label: toolLabel(label),
                value: fieldname === "tool_number"
                    ? displayToolNumber(tool[fieldname])
                    : tool[fieldname],
            })) : [],
            onToolChange(value) {
                if (handlers && typeof handlers.onToolChange === "function") {
                    handlers.onToolChange(String(value || ""));
                }
            },
            onFieldInput(fieldname, value) {
                state.tool = state.tool || {};
                state.tool[fieldname] = fieldname === "tool_number" || value === ""
                    ? value
                    : Number(value);
                if (handlers && typeof handlers.onFieldInput === "function") {
                    handlers.onFieldInput(fieldname, state.tool[fieldname]);
                }
            },
        });
        host.data("picker", picker);
        host.data("profileDocKey", state.documentKey);
        host.data("profileDocTool", selected);
        return picker;
    }

    function sync(host, state, doc, options) {
        const settings = options || {};
        const nextKey = documentKey(doc, settings.docname);
        const selected = String((doc && doc.tool_preset) || "");
        const existing = host && typeof host.data === "function" ? host.data("picker") : null;
        const boundKey = host && typeof host.data === "function" ? host.data("profileDocKey") : "";
        const boundTool = host && typeof host.data === "function" ? host.data("profileDocTool") : "";

        if (needsDocumentReset(state, nextKey)) {
            resetRuntimeForDocument(state, nextKey);
            // Preserve catalog cache across documents in the same Desk session.
            if (settings.toolChoices) state.toolChoices = settings.toolChoices;
        } else {
            state.documentKey = nextKey;
        }

        seedToolFromDocument(state, doc);

        const sameBinding = existing
            && String(boundKey || "") === nextKey
            && String(boundTool || "") === selected
            && !settings.force;

        if (sameBinding) {
            return ensureToolChoices(state, settings.loadTools).then(rows => {
                if (state.documentKey !== nextKey) return existing;
                if (existing && typeof existing.setTools === "function") {
                    existing.setTools(toolChoices(rows, doc, state.tool), selected, {
                        selectedLabel: (state.tool && (state.tool.description || state.tool.tool_name)) || selected,
                        emptyLabel: profileLabel("Choose a tool"),
                    });
                }
                return existing;
            });
        }

        return ensureToolChoices(state, settings.loadTools).then(() => {
            if (state.documentKey !== nextKey) return null;
            return paint(host, state, doc, settings.handlers || {});
        });
    }

    function beginToolLoad(state) {
        state.loadGeneration = Number(state.loadGeneration || 0) + 1;
        return state.loadGeneration;
    }

    function isCurrentToolLoad(state, generation, doc, toolName) {
        return Number(state.loadGeneration || 0) === Number(generation || 0)
            && String((doc && doc.tool_preset) || "") === String(toolName || "");
    }

    window.AlmdinaCncProfileToolBinding = Object.freeze({
        PROFILE_TOOL_FIELDS,
        createRuntimeState,
        resetRuntimeForDocument,
        needsDocumentReset,
        documentKey,
        storedTool,
        displayToolNumber,
        toolChoices,
        toolHost,
        clearToolHost,
        collectOverrides,
        toolPayloadFromPreset,
        ensureToolChoices,
        paint,
        sync,
        beginToolLoad,
        isCurrentToolLoad,
        seedToolFromDocument,
    });
})();
