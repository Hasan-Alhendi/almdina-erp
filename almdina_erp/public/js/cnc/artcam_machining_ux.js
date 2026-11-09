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

    function optionState(disabled) {
        return disabled ? " disabled" : "";
    }

    function usedLabel(row) {
        return row && row.used ? ` — ${translate("Already used")}` : "";
    }

    function markup(workspace, sheet) {
        const data = machining(sheet);
        const availability = data.availability || {};
        const presets = (workspace && workspace.presets) || [];
        const profiles = data.profiles || [];
        const associations = data.associations || [];
        const toolpaths = data.toolpaths || [];
        const perimeter = availability.sheet_perimeter;
        const profileOptions = profiles.map(profile => (
            `<option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.name)}</option>`
        )).join("");
        const toolOptions = presets.filter(preset => preset && preset.enabled !== false).map(preset => (
            `<option value="${escapeHtml(preset.name)}">${escapeHtml(preset.description || preset.tool_name || preset.name)}</option>`
        )).join("");
        const layerOptions = (availability.layers || []).map(layer => (
            `<option value="${escapeHtml(layer.operation_key)}"${optionState(layer.disabled)}>${escapeHtml(layer.dxf_layer || layer.operation_key)}${escapeHtml(usedLabel(layer))}</option>`
        )).join("");
        const vectorOptions = (availability.vectors || []).map(vector => (
            `<option value="${escapeHtml(vector.vector_id)}"${optionState(vector.disabled)}>${escapeHtml(vector.label || vector.vector_id)}${escapeHtml(usedLabel(vector))}</option>`
        )).join("");
        const perimeterOption = perimeter
            ? `<option value="sheet_perimeter"${optionState(perimeter.disabled)}>${escapeHtml(translate("Sheet Perimeter"))}${escapeHtml(usedLabel(perimeter))}</option>`
            : "";
        const profileCards = profiles.map(profile => `
            <article class="dco-artcam-card" data-profile-id="${escapeHtml(profile.profile_id)}">
                <header><strong>${escapeHtml(profile.name)}</strong><span>${escapeHtml(profile.tool_preset || "")}</span></header>
                <p>${escapeHtml(translate("Final Depth"))}: ${escapeHtml(profile.final_depth_mm)} mm · ${escapeHtml(translate("Safe Z"))}: ${escapeHtml(profile.safe_z_mm)} mm</p>
                <p>${escapeHtml(translate("Home position"))}: X ${escapeHtml(profile.home_x_mm)} · Y ${escapeHtml(profile.home_y_mm)} · Z ${escapeHtml(profile.home_z_mm)} mm</p>
                <button type="button" class="btn btn-default btn-xs" data-artcam-edit-profile="${escapeHtml(profile.profile_id)}">${escapeHtml(translate("Edit profile"))}</button>
            </article>
        `).join("");
        const associationCards = associations.map(row => `
            <article class="dco-artcam-card" data-association-id="${escapeHtml(row.association_id)}">
                <header><strong>${escapeHtml((row.vector_ids || []).join(", "))}</strong></header>
                <p>${escapeHtml(translate("Profile"))}: ${escapeHtml(row.profile_id || "")}</p>
                ${row.toolpath_name ? `<p>${escapeHtml(row.toolpath_name)}</p>` : ""}
                <button type="button" class="btn btn-default btn-xs" data-artcam-remove-association="${escapeHtml(row.association_id)}">${escapeHtml(translate("Remove"))}</button>
            </article>
        `).join("");
        const toolpathItems = toolpaths.map(row => (
            `<li data-toolpath-id="${escapeHtml(row.toolpath_id)}">${escapeHtml(row.name)}</li>`
        )).join("");
        return `
            <section class="dco-artcam" data-artcam-root>
                <section class="dco-artcam-block">
                    <h4>${escapeHtml(translate("Profiles"))}</h4>
                    <div class="dco-artcam-list">${profileCards || `<p>${escapeHtml(translate("No profiles yet."))}</p>`}</div>
                    <form data-artcam-profile-form>
                        <label>${escapeHtml(translate("Profile name"))}<input name="name" required></label>
                        <label>${escapeHtml(translate("Tool"))}<select name="tool_preset" required><option value="">${escapeHtml(translate("Choose"))}</option>${toolOptions}</select></label>
                        <label>${escapeHtml(translate("Final Depth"))}<input name="final_depth_mm" type="number" min="0" step="0.001" required> <span>mm</span></label>
                        <label>${escapeHtml(translate("Safe Z"))}<input name="safe_z_mm" type="number" min="0" step="0.001" required> <span>mm</span></label>
                        <fieldset>
                            <legend>${escapeHtml(translate("Home position"))}</legend>
                            <label>X<input name="home_x_mm" type="number" step="0.001" required> <span>mm</span></label>
                            <label>Y<input name="home_y_mm" type="number" step="0.001" required> <span>mm</span></label>
                            <label>Z<input name="home_z_mm" type="number" min="0" step="0.001" required> <span>mm</span></label>
                        </fieldset>
                        <button type="submit" class="btn btn-primary btn-sm">${escapeHtml(translate("Save profile"))}</button>
                    </form>
                </section>
                <section class="dco-artcam-block" data-vector-association>
                    <h4>${escapeHtml(translate("Vector Association"))}</h4>
                    <div class="dco-artcam-list">${associationCards}</div>
                    <form data-artcam-association-form>
                        <label>${escapeHtml(translate("Vectors"))}
                            <select name="vector_choice" required>
                                <option value="">${escapeHtml(translate("Choose"))}</option>
                                ${layerOptions}
                                <optgroup label="${escapeHtml(translate("Selected Vectors"))}">${vectorOptions}</optgroup>
                                ${perimeterOption}
                            </select>
                        </label>
                        <label>${escapeHtml(translate("Profile"))}
                            <select name="profile_id" required><option value="">${escapeHtml(translate("Choose"))}</option>${profileOptions}</select>
                        </label>
                        <label>${escapeHtml(translate("Final Depth"))}<input name="final_depth_mm" type="number" min="0" step="0.001"> <span>mm</span></label>
                        <label>${escapeHtml(translate("Safe Z"))}<input name="safe_z_mm" type="number" min="0" step="0.001"> <span>mm</span></label>
                        <fieldset>
                            <legend>${escapeHtml(translate("Home position"))}</legend>
                            <label>X<input name="home_x_mm" type="number" step="0.001"> <span>mm</span></label>
                            <label>Y<input name="home_y_mm" type="number" step="0.001"> <span>mm</span></label>
                            <label>Z<input name="home_z_mm" type="number" min="0" step="0.001"> <span>mm</span></label>
                        </fieldset>
                        <fieldset>
                            <legend>${escapeHtml(translate("Tool copy"))}</legend>
                            <label>${escapeHtml(translate("Diameter (D)"))}<input name="diameter_mm" type="number" min="0" step="0.001"> <span>mm</span></label>
                            <label>${escapeHtml(translate("Stepdown"))}<input name="stepdown_mm" type="number" min="0" step="0.001"> <span>mm</span></label>
                            <label>${escapeHtml(translate("Spindle Speed (rpm)"))}<input name="spindle_speed_rpm" type="number" min="1" step="1"></label>
                            <label>${escapeHtml(translate("Feed Rate (mm/sec)"))}<input name="feed_rate_mm_sec" type="number" min="0" step="0.001"></label>
                            <label>${escapeHtml(translate("Plunge Rate (mm/sec)"))}<input name="plunge_rate_mm_sec" type="number" min="0" step="0.001"></label>
                        </fieldset>
                        <button type="submit" class="btn btn-default btn-sm">${escapeHtml(translate("Assign"))}</button>
                    </form>
                    <form data-artcam-calculate-form>
                        <label>${escapeHtml(translate("Toolpath name"))}<input name="toolpath_name" required></label>
                        <label>${escapeHtml(translate("Vector Association"))}
                            <select name="association_id" required>
                                <option value="">${escapeHtml(translate("Choose"))}</option>
                                ${associations.map(row => `<option value="${escapeHtml(row.association_id)}">${escapeHtml((row.vector_ids || []).join(", "))}</option>`).join("")}
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
        new FormData(form).forEach((value, key) => {
            data[key] = value;
        });
        return data;
    }

    function bind(root, context) {
        if (!root || !context) return;
        const host = root.querySelector("[data-artcam-root]");
        if (!host || host.dataset.artcamBound === "1") return;
        host.dataset.artcamBound = "1";
        host.addEventListener("submit", event => {
            const form = event.target;
            if (!(form instanceof HTMLFormElement)) return;
            event.preventDefault();
            if (form.matches("[data-artcam-profile-form]")) saveProfile(form, context);
            if (form.matches("[data-artcam-association-form]")) saveAssociation(form, context);
            if (form.matches("[data-artcam-calculate-form]")) calculate(form, context);
        });
        host.addEventListener("click", event => {
            const button = event.target.closest("[data-artcam-remove-association]");
            if (button) {
                event.preventDefault();
                removeAssociation(button.getAttribute("data-artcam-remove-association"), context);
                return;
            }
            const edit = event.target.closest("[data-artcam-edit-profile]");
            if (!edit) return;
            event.preventDefault();
            fillProfileForm(host, edit.getAttribute("data-artcam-edit-profile"), context);
        });
    }

    function currentMachining(context) {
        const sheet = context.sheet || {};
        return machining(sheet);
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

    function toolCopy(preset, toolPreset) {
        if (!preset) return undefined;
        return Object.assign({}, preset, {
            tool_preset: toolPreset,
            description: preset.description || preset.tool_name,
        });
    }

    function fillProfileForm(host, profileId, context) {
        const profile = (currentMachining(context).profiles || []).find(row => row.profile_id === profileId);
        const form = host.querySelector("[data-artcam-profile-form]");
        if (!profile || !form) return;
        form.dataset.profileId = profile.profile_id;
        form.elements.name.value = profile.name || "";
        form.elements.tool_preset.value = profile.tool_preset || "";
        form.elements.final_depth_mm.value = profile.final_depth_mm;
        form.elements.safe_z_mm.value = profile.safe_z_mm;
        form.elements.home_x_mm.value = profile.home_x_mm;
        form.elements.home_y_mm.value = profile.home_y_mm;
        form.elements.home_z_mm.value = profile.home_z_mm;
    }

    function saveProfile(form, context) {
        const values = formData(form);
        const data = currentMachining(context);
        const preset = ((context.workspace && context.workspace.presets) || []).find(row => row.name === values.tool_preset);
        const editing = form.dataset.profileId || "";
        const next = {
            name: values.name,
            tool_preset: values.tool_preset,
            final_depth_mm: values.final_depth_mm,
            safe_z_mm: values.safe_z_mm,
            home_x_mm: values.home_x_mm,
            home_y_mm: values.home_y_mm,
            home_z_mm: values.home_z_mm,
        };
        let profiles;
        if (editing) {
            profiles = (data.profiles || []).map(row => {
                if (row.profile_id !== editing) return row;
                const sameTool = row.tool_preset === values.tool_preset;
                return Object.assign({}, row, next, {
                    tool_values: sameTool ? row.tool_values : toolCopy(preset, values.tool_preset),
                });
            });
        } else {
            profiles = (data.profiles || []).concat([Object.assign({
                profile_id: newId("profile"),
                tool_values: toolCopy(preset, values.tool_preset),
            }, next)]);
        }
        callSave(context, profiles, data.associations || []).then(() => {
            delete form.dataset.profileId;
        });
    }

    function selectionFromChoice(value, availability) {
        if (value === "sheet_perimeter") return { kind: "sheet_perimeter" };
        const layer = (availability.layers || []).find(row => row.operation_key === value);
        if (layer) return { kind: "layer", operation_key: value };
        return { kind: "vectors", vector_ids: [value] };
    }

    function saveAssociation(form, context) {
        const values = formData(form);
        const data = currentMachining(context);
        const profile = (data.profiles || []).find(row => row.profile_id === values.profile_id);
        if (!profile) return;
        const toolValues = Object.assign({}, profile.tool_values || {});
        if (values.diameter_mm !== "") toolValues.diameter_mm = values.diameter_mm;
        if (values.stepdown_mm !== "") toolValues.stepdown_mm = values.stepdown_mm;
        if (values.spindle_speed_rpm !== "") toolValues.spindle_speed_rpm = values.spindle_speed_rpm;
        if (values.feed_rate_mm_sec !== "" && toolValues.rate_units === "mm/sec") {
            toolValues.feed_rate_mm_sec = values.feed_rate_mm_sec;
        }
        if (values.plunge_rate_mm_sec !== "" && toolValues.rate_units === "mm/sec") {
            toolValues.plunge_rate_mm_sec = values.plunge_rate_mm_sec;
        }
        const local = Object.assign({}, profile, {
            tool_values: toolValues,
            final_depth_mm: values.final_depth_mm || profile.final_depth_mm,
            safe_z_mm: values.safe_z_mm || profile.safe_z_mm,
            home_x_mm: values.home_x_mm === "" ? profile.home_x_mm : values.home_x_mm,
            home_y_mm: values.home_y_mm === "" ? profile.home_y_mm : values.home_y_mm,
            home_z_mm: values.home_z_mm === "" ? profile.home_z_mm : values.home_z_mm,
        });
        const associations = (data.associations || []).concat([{
            association_id: newId("association"),
            profile_id: profile.profile_id,
            selection: selectionFromChoice(values.vector_choice, data.availability || {}),
            local_values: local,
        }]);
        callSave(context, data.profiles || [], associations);
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
