(() => {
    "use strict";

    if (window.AlmdinaArtcamMachining) return;

    const METHOD = "almdina_erp.almdina_erp.services.cnc_operational_file_service";

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof __ === "function") return __(message);
        return String(message || "");
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function machining(sheet) {
        return (sheet && sheet.machining) || { profiles: [], associations: [], toolpaths: [], availability: {} };
    }

    function newId(prefix) {
        const token = Math.random().toString(36).slice(2, 10);
        return `${prefix}:${token}`;
    }

    const TOOL_FIELDS = Object.freeze([
        ["description", "Description", "Data", false],
        ["tool_number", "Tool Number", "Int", false],
        ["tool_type", "Tool Type", "Data", true],
        ["tool_units", "Tool Units", "Data", true],
        ["rate_units", "Rate Units", "Data", true],
        ["notes", "Notes", "Small Text", false],
        ["diameter_mm", "Diameter (D)", "Float", false],
        ["stepdown_mm", "Stepdown (mm)", "Float", false],
        ["final_tool_offset_mm", "Final Tool Offset (mm)", "Float", false],
        ["stepover_size_mm", "Stepover size (mm)", "Float", false],
        ["stepover_percent", "Stepover percent of D", "Float", false],
        ["spindle_speed_rpm", "Spindle Speed (rpm)", "Int", false],
        ["feed_rate_mm_sec", "Feed Rate (mm/sec)", "Float", false],
        ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)", "Float", false],
    ]);

    const PROFILE_FIELDS = Object.freeze([
        ["final_depth_mm", "Final Depth (mm)", "Float"],
        ["safe_z_mm", "Safe Z (mm)", "Float"],
    ]);

    const HOME_FIELDS = Object.freeze([
        ["home_x_mm", "X (mm)", "Float"],
        ["home_y_mm", "Y (mm)", "Float"],
        ["home_z_mm", "Z (mm)", "Float"],
    ]);

    function profileRecords(context) {
        const sheet = context.sheet || {};
        const data = machining(sheet);
        const catalog = ((context.workspace && context.workspace.machining_profile_catalog) || [])
            .filter(row => row && row.enabled !== false);
        const seen = new Set();
        const rows = [];
        catalog.forEach(row => {
            if (!row.profile_id || seen.has(row.profile_id)) return;
            seen.add(row.profile_id);
            rows.push(row);
        });
        (data.profiles || []).forEach(row => {
            if (!row || !row.profile_id || seen.has(row.profile_id)) return;
            seen.add(row.profile_id);
            rows.push(row);
        });
        return rows;
    }

    function vectorChoices(context, editingId) {
        const availability = machining(context.sheet).availability || {};
        const editing = (machining(context.sheet).associations || [])
            .find(row => row && row.association_id === editingId);
        const owned = new Set((editing && editing.vector_ids) || []);
        if (editing && editing.selection && editing.selection.kind === "layer") {
            owned.add(editing.selection.operation_key);
        }
        if (editing && editing.selection && editing.selection.kind === "sheet_perimeter") {
            owned.add("sheet_perimeter");
        }
        const rows = [];
        (availability.layers || []).forEach(layer => {
            if (layer.disabled && !owned.has(layer.operation_key)) return;
            rows.push({
                value: layer.operation_key,
                label: layer.dxf_layer || layer.operation_key,
            });
        });
        (availability.vectors || []).forEach(vector => {
            if (vector.disabled && !owned.has(vector.vector_id)) return;
            rows.push({
                value: vector.vector_id,
                label: vector.label || vector.vector_id,
            });
        });
        const perimeter = availability.sheet_perimeter;
        if (perimeter && (!perimeter.disabled || owned.has("sheet_perimeter"))) {
            rows.push({ value: "sheet_perimeter", label: "Sheet Perimeter" });
        }
        return rows;
    }

    function choiceLabel(context, value) {
        const match = vectorChoices(context, "").find(row => row.value === value);
        return match ? match.label : value;
    }

    function markup(workspace, sheet) {
        const data = machining(sheet);
        const associations = data.associations || [];
        const toolpaths = data.toolpaths || [];
        const associationCards = associations.map(row => {
            const labels = (row.vector_ids || []).map(id => choiceLabel({ workspace, sheet }, id));
            const profile = profileRecords({ workspace, sheet }).find(item => item.profile_id === row.profile_id);
            return `
            <article class="dco-artcam-card" data-association-id="${escapeHtml(row.association_id)}">
                <header><strong>${escapeHtml(labels.join(", "))}</strong></header>
                <p>Profile: ${escapeHtml((profile && profile.name) || row.profile_id || "")}</p>
                <button type="button" class="btn btn-default btn-xs" data-artcam-edit-association="${escapeHtml(row.association_id)}">Edit</button>
                <button type="button" class="btn btn-default btn-xs" data-artcam-remove-association="${escapeHtml(row.association_id)}">Remove</button>
            </article>`;
        }).join("");
        const toolpathItems = toolpaths.map(row => (
            `<li data-toolpath-id="${escapeHtml(row.toolpath_id)}">${escapeHtml(row.name)}${row.active ? "" : ` <span>${escapeHtml(translate("Not the active toolpath"))}</span>`}</li>`
        )).join("");
        return `
            <section class="dco-artcam" data-artcam-root>
                <section class="dco-artcam-block" data-vector-association>
                    <h4>Vector Association</h4>
                    <div class="dco-artcam-list">${associationCards}</div>
                    <div data-artcam-association>
                        <div class="dco-artcam-assoc__row">
                            <div data-artcam-vectors-host></div>
                            <div data-artcam-profile-host></div>
                        </div>
                        <div data-artcam-association-detail hidden>
                            <div class="form-section">
                                <div class="section-head">Tool</div>
                                <div class="section-body dco-artcam-fields" data-artcam-tool-fields></div>
                            </div>
                            <div class="form-section">
                                <div class="section-head">Profile</div>
                                <div class="section-body dco-artcam-fields dco-artcam-fields--pair" data-artcam-profile-fields></div>
                            </div>
                            <div class="form-section">
                                <div class="section-head">Home</div>
                                <div class="section-body dco-artcam-fields dco-artcam-fields--home" data-artcam-home-fields></div>
                            </div>
                            <p class="dco-artcam-note">Stepover and the final tool offset are stored on this association copy. This calculation follows the approved cutter-center path and does not build a pocket or raster.</p>
                        </div>
                        <button type="button" class="btn btn-primary btn-sm" data-artcam-assign>Assign</button>
                    </div>
                    <form data-artcam-calculate-form>
                        <label>${escapeHtml(translate("Toolpath name"))}<input name="toolpath_name" required></label>
                        <label>${escapeHtml(translate("Vector Association"))}
                            <select name="association_id" required>
                                <option value="">${escapeHtml(translate("Choose"))}</option>
                                ${associations.map(row => `<option value="${escapeHtml(row.association_id)}">${escapeHtml((row.vector_ids || []).map(id => choiceLabel({ workspace, sheet }, id)).join(", "))}</option>`).join("")}
                            </select>
                        </label>
                        <button type="submit" class="btn btn-primary btn-sm">${escapeHtml(translate("Calculate Now"))}</button>
                    </form>
                </section>
                <section class="dco-artcam-block">
                    <h4>${escapeHtml(translate("Toolpaths"))}</h4>
                    <ol class="dco-artcam-toolpaths">${toolpathItems}</ol>
                </section>
            </section>
        `;
    }

    function formData(form) {
        const data = {};
        Array.from(form.elements).forEach(element => {
            if (!element.name) return;
            data[element.name] = element.value;
        });
        return data;
    }

    function applyToolInputs(target, values) {
        TOOL_FIELDS.forEach(([name]) => {
            if (values[name] !== undefined && values[name] !== "") target[name] = values[name];
        });
        if (target.tool_type === "Ball Nose" || target.rate_units === "mm/sec") {
            target.tool_type = "Ball Nose";
            target.tool_units = "mm";
            target.rate_units = "mm/sec";
        }
        return target;
    }

    let mounted = [];

    function disposeMounted() {
        mounted.forEach(control => {
            if (control && typeof control.dispose === "function") control.dispose();
        });
        mounted = [];
    }

    function pinLabel(control, label) {
        const wrapper = control && control.control && control.control.$wrapper;
        if (!wrapper) return;
        wrapper.find(".control-label").first().text(label);
    }

    function mountField(parent, name, label, fieldtype, value, readOnly) {
        const ui = window.AlmdinaUi;
        const host = document.createElement("div");
        parent.appendChild(host);
        const control = ui.control({
            parent: host,
            fieldname: name,
            fieldtype,
            label,
            onlyInput: false,
            readOnly: Boolean(readOnly),
            value: value == null ? "" : value,
            df: fieldtype === "Float" ? { precision: 3 } : {},
        });
        pinLabel(control, label);
        mounted.push(control);
        return control;
    }

    function readControl(control) {
        if (!control || typeof control.getValue !== "function") return "";
        const value = control.getValue();
        return value == null ? "" : value;
    }

    function bind(root, context) {
        if (!root || !context) return;
        const host = root.querySelector("[data-artcam-root]");
        if (!host || host.dataset.artcamBound === "1") return;
        host.dataset.artcamBound = "1";
        disposeMounted();
        const ui = window.AlmdinaUi;
        const state = { editingId: "", fields: {} };
        if (ui && typeof ui.control === "function") mountAssociation(host, context, state);
        host.addEventListener("submit", event => {
            const form = event.target;
            if (!(form instanceof HTMLFormElement)) return;
            event.preventDefault();
            if (form.matches("[data-artcam-calculate-form]")) calculate(form, context);
        });
        host.addEventListener("click", event => {
            const button = event.target.closest("[data-artcam-remove-association]");
            if (button) {
                event.preventDefault();
                removeAssociation(button.getAttribute("data-artcam-remove-association"), context);
                return;
            }
            const editAssociation = event.target.closest("[data-artcam-edit-association]");
            if (editAssociation) {
                event.preventDefault();
                fillAssociation(host, editAssociation.getAttribute("data-artcam-edit-association"), context, state);
                return;
            }
            const assign = event.target.closest("[data-artcam-assign]");
            if (!assign) return;
            event.preventDefault();
            saveAssociation(host, context, state);
        });
    }

    function mountAssociation(host, context, state) {
        const vectorsHost = host.querySelector("[data-artcam-vectors-host]");
        const profileHost = host.querySelector("[data-artcam-profile-host]");
        const ui = window.AlmdinaUi;
        state.vectors = ui.control({
            parent: vectorsHost,
            fieldname: "vector_choice",
            fieldtype: "MultiSelectList",
            label: "Vectors",
            onlyInput: false,
            df: {
                get_data(txt) {
                    const query = String(txt || "").trim().toLowerCase();
                    return vectorChoices(context, state.editingId).filter(row => (
                        !query || String(row.label || "").toLowerCase().includes(query)
                    ));
                },
            },
        });
        pinLabel(state.vectors, "Vectors");
        if (state.vectors.control && state.vectors.control.$wrapper) {
            state.vectors.control.$wrapper.find(".select-all-options").text("Select All");
            state.vectors.control.$wrapper.find(".clear-selections").text("Clear All");
        }
        mounted.push(state.vectors);
        const profiles = profileRecords(context);
        state.profile = ui.control({
            parent: profileHost,
            fieldname: "profile_id",
            fieldtype: "Select",
            label: "Profile",
            onlyInput: false,
            options: [{ value: "", label: "Choose" }].concat(profiles.map(row => ({
                value: row.profile_id,
                label: row.name || row.profile_id,
            }))),
            onChange(value) {
                if (state.silent) return;
                const profile = profileRecords(context).find(row => row.profile_id === value);
                if (!profile) {
                    hideDetail(host);
                    return;
                }
                showDetail(host, context, state, profile);
            },
        });
        pinLabel(state.profile, "Profile");
        rewriteSelect(state.profile, [{ value: "", label: "Choose" }].concat(profiles.map(row => ({
            value: row.profile_id,
            label: row.name || row.profile_id,
        }))));
        mounted.push(state.profile);
    }

    function rewriteSelect(control, rows) {
        const input = control && control.control && control.control.$input && control.control.$input.get(0);
        if (!input) return;
        const selected = input.value;
        input.innerHTML = "";
        rows.forEach(row => {
            const option = document.createElement("option");
            option.value = row.value;
            option.textContent = row.label;
            input.appendChild(option);
        });
        if (selected) input.value = selected;
    }

    function hideDetail(host) {
        const detail = host.querySelector("[data-artcam-association-detail]");
        if (detail) detail.hidden = true;
    }

    function showDetail(host, context, state, source) {
        const detail = host.querySelector("[data-artcam-association-detail]");
        if (!detail) return;
        detail.hidden = false;
        const toolHost = detail.querySelector("[data-artcam-tool-fields]");
        const profileHost = detail.querySelector("[data-artcam-profile-fields]");
        const homeHost = detail.querySelector("[data-artcam-home-fields]");
        [toolHost, profileHost, homeHost].forEach(node => {
            if (node) node.innerHTML = "";
        });
        state.fields = {};
        const tool = (source && source.tool_values) || source || {};
        const values = Object.assign({}, source || {}, tool);
        TOOL_FIELDS.forEach(([name, label, fieldtype, readOnly]) => {
            state.fields[name] = mountField(toolHost, name, label, fieldtype, values[name], readOnly);
        });
        PROFILE_FIELDS.forEach(([name, label, fieldtype]) => {
            state.fields[name] = mountField(profileHost, name, label, fieldtype, source && source[name], false);
        });
        HOME_FIELDS.forEach(([name, label, fieldtype]) => {
            state.fields[name] = mountField(homeHost, name, label, fieldtype, source && source[name], false);
        });
    }

    function currentMachining(context) {
        return machining(context.sheet || {});
    }

    function callSave(context, profiles, associations) {
        const args = context.getArgs ? context.getArgs() : {};
        return new Promise((resolve, reject) => {
            frappe.call({
                method: `${METHOD}.save_cnc_operational_sheet`,
                args: Object.assign({}, args, {
                    machining_profiles: profiles,
                    vector_associations: associations,
                }),
                callback(response) { resolve((response && response.message) || {}); },
                error: reject,
            });
        }).then(workspace => {
            if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
            return workspace;
        });
    }

    function fieldValues(state) {
        const values = {};
        Object.keys(state.fields || {}).forEach(name => {
            values[name] = readControl(state.fields[name]);
        });
        return values;
    }

    function selectionFromChoices(chosen, availability) {
        const values = (chosen || []).filter(Boolean);
        if (values.length === 1 && values[0] === "sheet_perimeter") return { kind: "sheet_perimeter" };
        const layer = (availability.layers || []).find(row => row.operation_key === values[0]);
        if (values.length === 1 && layer) return { kind: "layer", operation_key: values[0] };
        return { kind: "vectors", vector_ids: values };
    }

    function profileSnapshot(profile) {
        return {
            profile_id: profile.profile_id,
            name: profile.name,
            tool_preset: profile.tool_preset,
            tool_values: Object.assign({}, profile.tool_values || {}),
            final_depth_mm: profile.final_depth_mm,
            safe_z_mm: profile.safe_z_mm,
            home_x_mm: profile.home_x_mm,
            home_y_mm: profile.home_y_mm,
            home_z_mm: profile.home_z_mm,
        };
    }

    function fillAssociation(host, associationId, context, state) {
        const row = (currentMachining(context).associations || []).find(item => item.association_id === associationId);
        if (!row || !state.profile) return;
        state.editingId = row.association_id;
        state.silent = true;
        const chosen = (row.vector_ids || []).slice();
        if (row.selection && row.selection.kind === "layer" && row.selection.operation_key) {
            chosen.splice(0, chosen.length, row.selection.operation_key);
        }
        if (row.selection && row.selection.kind === "sheet_perimeter") {
            chosen.splice(0, chosen.length, "sheet_perimeter");
        }
        const prepareVectors = state.vectors.control && typeof state.vectors.control.set_options === "function"
            ? state.vectors.control.set_options()
            : null;
        Promise.resolve(prepareVectors).then(() => state.vectors.setValue(chosen)).finally(() => {
            state.silent = false;
        });
        state.profile.setValue(row.profile_id || "");
        const profile = profileRecords(context).find(item => item.profile_id === row.profile_id) || {};
        showDetail(host, context, state, Object.assign({}, profile, row.local_values || {}));
        const button = host.querySelector("[data-artcam-assign]");
        if (button) button.textContent = "Save association";
    }

    function saveAssociation(host, context, state) {
        const values = fieldValues(state);
        const data = currentMachining(context);
        const profileId = readControl(state.profile);
        const profile = profileRecords(context).find(row => row.profile_id === profileId);
        if (!profile) return;
        const editing = state.editingId || "";
        const current = (data.associations || []).find(row => row.association_id === editing);
        const baseTool = current && current.profile_id === profileId
            ? (current.local_values && current.local_values.tool_values)
            : profile.tool_values;
        const local = Object.assign({}, profile, {
            tool_values: applyToolInputs(Object.assign({}, baseTool || profile.tool_values || {}), values),
            final_depth_mm: values.final_depth_mm,
            safe_z_mm: values.safe_z_mm,
            home_x_mm: values.home_x_mm,
            home_y_mm: values.home_y_mm,
            home_z_mm: values.home_z_mm,
        });
        const vectorValue = readControl(state.vectors);
        const next = {
            association_id: editing || newId("association"),
            profile_id: profile.profile_id,
            selection: selectionFromChoices(
                Array.isArray(vectorValue) ? vectorValue : [vectorValue],
                data.availability || {}
            ),
            local_values: local,
            toolpath_id: current ? current.toolpath_id || "" : "",
            toolpath_name: current ? current.toolpath_name || "" : "",
        };
        const associations = editing
            ? (data.associations || []).map(row => row.association_id === editing ? next : row)
            : (data.associations || []).concat([next]);
        const profiles = (data.profiles || []).some(row => row.profile_id === profile.profile_id)
            ? (data.profiles || [])
            : (data.profiles || []).concat([profileSnapshot(profile)]);
        callSave(context, profiles, associations);
    }

    function removeAssociation(associationId, context) {
        const data = currentMachining(context);
        const associations = (data.associations || []).filter(row => row.association_id !== associationId);
        callSave(context, data.profiles || [], associations);
    }

    function calculate(form, context) {
        const values = formData(form);
        const args = context.getArgs ? context.getArgs() : {};
        const data = currentMachining(context);
        frappe.call({
            method: `${METHOD}.calculate_cnc_association_toolpath`,
            args: Object.assign({}, args, {
                association_id: values.association_id,
                toolpath_name: values.toolpath_name,
                machining_profiles: data.profiles || [],
                vector_associations: data.associations || [],
            }),
            callback(response) {
                if (typeof context.onWorkspace === "function") {
                    context.onWorkspace((response && response.message) || {});
                }
            },
        });
    }

    window.AlmdinaArtcamMachining = Object.freeze({ markup, bind });
})();
