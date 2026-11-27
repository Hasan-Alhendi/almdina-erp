frappe.ui.form.on("CNC Machining Profile", {
    refresh(frm) {
        const labels = {
            profile_id: "Profile ID",
            profile_name: "Profile Name",
            tool_preset: "Tool",
            final_depth_mm: "Final Depth (mm)",
            safe_z_mm: "Safe Z (mm)",
            home_x_mm: "Home X (mm)",
            home_y_mm: "Home Y (mm)",
            home_z_mm: "Home Z (mm)",
            enabled: "Enabled",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.get_field(fieldname);
            if (!field) return;
            const text = profile_label(label);
            frm.set_df_property(fieldname, "label", text);
            field.df.label = text;
            if (typeof field.set_label === "function") field.set_label(text);
        });
        frm.set_df_property("profile_id", "reqd", 0);
        frm.set_df_property("tool_values_json", "hidden", 1);
        frm.set_df_property("tool_values_json", "reqd", 0);
        const labelsApi = window.AlmdinaCncLabels;
        if (labelsApi && typeof labelsApi.ensureFormFieldsWritable === "function") {
            labelsApi.ensureFormFieldsWritable(frm, {
                keepHidden: ["tool_values_json"],
                keepReadOnly: ["profile_id"],
            });
        }
        sync_profile_tool_picker(frm);
    },
    tool_preset(frm) {
        const binding = profile_binding();
        const state = profile_runtime(frm);
        if (!state.ready) return;
        const selected = String(frm.doc.tool_preset || "");
        if (selected === String(state.toolName || "")) return;
        state.toolName = selected;
        if (!selected) {
            state.tool = null;
            paint_profile_tool_editor(frm, true);
            return;
        }
        copy_selected_tool(frm, selected);
    },
    before_save(frm) {
        const binding = profile_binding();
        if (!binding) {
            frm.doc.tool_values_json = {};
            return;
        }
        const host = binding.toolHost(frm.fields_dict && frm.fields_dict.tool_preset);
        frm.doc.tool_values_json = binding.collectOverrides(host);
    },
});

function profile_binding() {
    return window.AlmdinaCncProfileToolBinding || null;
}

function profile_label(message) {
    const labelsApi = window.AlmdinaCncLabels;
    if (labelsApi && typeof labelsApi.profileLabel === "function") return labelsApi.profileLabel(message);
    return typeof __ === "function" ? __(message) : message;
}

function profile_runtime(frm) {
    const binding = profile_binding();
    if (!frm._profile_tool_runtime) {
        frm._profile_tool_runtime = binding
            ? binding.createRuntimeState()
            : { ready: false, documentKey: "", toolName: "", tool: null, toolChoices: null, loadGeneration: 0 };
    }
    return frm._profile_tool_runtime;
}

function load_profile_tools() {
    const db = window.frappe && frappe.db;
    if (!db || typeof db.get_list !== "function") return Promise.resolve([]);
    return db.get_list("CNC Tool Preset", {
        fields: ["name", "tool_name"],
        filters: { enabled: 1 },
        limit: 500,
    }).then(rows => rows || []).catch(() => []);
}

function sync_profile_tool_picker(frm) {
    const binding = profile_binding();
    if (!binding) return;
    const state = profile_runtime(frm);
    state.ready = true;
    const host = binding.toolHost(frm.fields_dict && frm.fields_dict.tool_preset);
    if (!host) return;
    binding.sync(host, state, frm.doc, {
        docname: frm.docname || (frm.doc && frm.doc.name) || "",
        loadTools: load_profile_tools,
        handlers: {
            onToolChange(value) {
                const next = String(value || "");
                const current = String(frm.doc.tool_preset || "");
                if (next === current) return;
                frm.set_value("tool_preset", next || null);
            },
        },
    });
}

function paint_profile_tool_editor(frm, force) {
    const binding = profile_binding();
    if (!binding) return;
    const state = profile_runtime(frm);
    const host = binding.toolHost(frm.fields_dict && frm.fields_dict.tool_preset);
    if (!host) return;
    binding.sync(host, state, frm.doc, {
        docname: frm.docname || (frm.doc && frm.doc.name) || "",
        force: Boolean(force),
        loadTools: load_profile_tools,
        handlers: {
            onToolChange(value) {
                const next = String(value || "");
                const current = String(frm.doc.tool_preset || "");
                if (next === current) return;
                frm.set_value("tool_preset", next || null);
            },
        },
    });
}

function copy_selected_tool(frm, name) {
    const binding = profile_binding();
    if (!binding || !window.frappe || typeof frappe.db.get_doc !== "function") return;
    const state = profile_runtime(frm);
    const generation = binding.beginToolLoad(state);
    frappe.db.get_doc("CNC Tool Preset", name).then(doc => {
        if (!binding.isCurrentToolLoad(state, generation, frm.doc, name)) return;
        state.tool = binding.toolPayloadFromPreset(doc);
        state.toolName = name;
        paint_profile_tool_editor(frm, true);
    });
}
