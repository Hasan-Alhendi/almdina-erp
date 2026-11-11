(() => {
    "use strict";

    if (window.AlmdinaArtcamMachining) return;

    const METHOD = "almdina_erp.almdina_erp.services.cnc_operational_file_service";
    const PROFILE_FIELDS = Object.freeze([
        ["final_depth_mm", "Final Depth (mm)"],
        ["safe_z_mm", "Safe Z (mm)"],
    ]);
    const HOME_FIELDS = Object.freeze([
        ["home_x_mm", "X"],
        ["home_y_mm", "Y"],
        ["home_z_mm", "Z"],
    ]);
    const TOOL_FIELDS = Object.freeze([
        ["tool_number", "Tool Number"],
        ["diameter_mm", "Diameter (mm)"],
        ["stepdown_mm", "Stepdown"],
        ["final_tool_offset_mm", "Final Tool Offset"],
        ["stepover_size_mm", "Stepover Size"],
        ["stepover_percent", "Stepover Percent of D"],
        ["spindle_speed_rpm", "Spindle Speed (RPM)"],
        ["feed_rate_mm_sec", "Feed Rate (mm/sec)"],
        ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)"],
    ]);

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
        return (sheet && sheet.machining) || { profiles: [], associations: [], availability: {} };
    }

    function newId(prefix) {
        return `${prefix}:${Math.random().toString(36).slice(2, 12)}`;
    }

    function profilesOf(context) {
        const data = machining(context.sheet);
        const catalog = ((context.workspace && context.workspace.machining_profile_catalog) || [])
            .filter(row => row && row.enabled !== false);
        const seen = new Set();
        const rows = [];
        catalog.concat(data.profiles || []).forEach(row => {
            if (!row || !row.profile_id || seen.has(row.profile_id)) return;
            seen.add(row.profile_id);
            rows.push(row);
        });
        return rows;
    }

    function toolsOf(context) {
        const rows = [];
        const seen = new Set();
        ((context.workspace && context.workspace.presets) || []).forEach(row => {
            const name = row && (row.tool_name || row.name || row.preset_name);
            if (!name || seen.has(name)) return;
            seen.add(name);
            rows.push(row);
        });
        return rows;
    }

    function blankForm() {
        return {
            association_id: newId("association"),
            name: "",
            source: "",
            profile_id: "",
            tool_preset: "",
            fields: {},
            tool: {},
            toolOpen: false,
        };
    }

    function ensureForm(state) {
        if (!state.artcamForm || !state.artcamForm.association_id) state.artcamForm = blankForm();
        if (!Array.isArray(state.vectorSelection)) state.vectorSelection = [];
        return state.artcamForm;
    }

    function sourceOptions(context, form) {
        const availability = machining(context.sheet).availability || {};
        const connected = context.state && context.state.perimeterJoinMode === "connected";
        const options = [];
        (availability.layers || []).forEach(layer => {
            if (!layer || !layer.operation_key) return;
            const current = form && form.source === `layer:${layer.operation_key}`;
            if (layer.disabled && !current) return;
            options.push({ value: `layer:${layer.operation_key}`, label: layer.dxf_layer || layer.operation_key });
        });
        options.push({ value: "selected_vectors", label: "Selected Vectors" });
        const ownsPerimeter = form && form.source === "sheet_perimeter";
        if (connected || (availability.sheet_perimeter && !availability.sheet_perimeter.disabled) || ownsPerimeter) {
            options.push({ value: "sheet_perimeter", label: "Sheet Perimeter" });
        }
        return options;
    }

    function sourceLabel(value, context) {
        if (value === "sheet_perimeter") return "Sheet Perimeter";
        if (value === "selected_vectors") return "Selected Vectors";
        const layer = String(value || "").startsWith("layer:") ? String(value).slice(6) : "";
        const match = ((machining(context.sheet).availability || {}).layers || [])
            .find(row => row.operation_key === layer);
        return match ? (match.dxf_layer || layer) : layer;
    }

    function input(name, label, value) {
        return `<label class="dco-artcam-field">${escapeHtml(label)}
            <input class="form-control" data-field="${escapeHtml(name)}" value="${escapeHtml(value == null ? "" : value)}">
        </label>`;
    }

    function toolSummary(tool) {
        const number = tool.tool_number_display || tool.tool_number || "";
        const name = tool.description || tool.tool_preset || "";
        const diameter = tool.diameter_mm != null && tool.diameter_mm !== "" ? `${tool.diameter_mm} mm` : "";
        return [number && `T${String(number).replace(/^T/i, "")}`, name || "Ball Nose", diameter].filter(Boolean).join(" — ");
    }

    function editorMarkup(context) {
        const form = ensureForm(context.state);
        const tool = form.tool || {};
        const count = (context.state.vectorSelection || []).length;
        const selected = form.source === "selected_vectors";
        const options = sourceOptions(context, form);
        const editing = (machining(context.sheet).associations || [])
            .some(row => row.association_id === form.association_id);
        return `<form class="dco-artcam-editor" data-artcam-editor>
            ${editing ? `<p class="dco-artcam-note" data-artcam-editing>${escapeHtml(translate("Editing"))}: ${escapeHtml(form.name || form.association_id)}
                <button type="button" class="btn btn-default btn-xs" data-artcam-cancel>${escapeHtml(translate("New association"))}</button>
            </p>` : ""}
            <div class="dco-artcam-row dco-artcam-row--main">
                <label class="dco-artcam-field">${escapeHtml("Association Name")}
                    <input class="form-control" data-field="name" value="${escapeHtml(form.name || "")}">
                </label>
                <label class="dco-artcam-field">${escapeHtml("Vector Source")}
                    <select class="form-control" data-field="source">
                        <option value="">${escapeHtml(translate("Choose"))}</option>
                        ${options.map(option => `<option value="${escapeHtml(option.value)}"${option.value === form.source ? " selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
                    </select>
                </label>
                <label class="dco-artcam-field">${escapeHtml("Profile")}
                    <select class="form-control" data-field="profile_id">
                        <option value="">${escapeHtml(translate("Choose"))}</option>
                        ${profilesOf(context).map(row => `<option value="${escapeHtml(row.profile_id)}"${row.profile_id === form.profile_id ? " selected" : ""}>${escapeHtml(row.name || row.profile_id)}</option>`).join("")}
                    </select>
                </label>
            </div>
            <p class="dco-artcam-note" data-vector-hint${selected ? "" : " hidden"}>${escapeHtml(translate("Shift + Click to select vectors"))}</p>
            <p class="dco-artcam-note" data-vector-count${selected ? "" : " hidden"}>${escapeHtml(`${count} Vectors Selected`)}</p>
            <div class="dco-artcam-row dco-artcam-row--pair">
                ${PROFILE_FIELDS.map(([name, label]) => input(name, label, form.fields[name])).join("")}
            </div>
            <div class="dco-artcam-home">
                <span>${escapeHtml("Home Position (mm)")}</span>
                <div class="dco-artcam-row dco-artcam-row--home">
                    ${HOME_FIELDS.map(([name, label]) => input(name, label, form.fields[name])).join("")}
                </div>
            </div>
            <section class="dco-artcam-tool${form.toolOpen ? "" : " is-collapsed"}" data-artcam-tool>
                <div class="dco-artcam-tool__bar">
                    <span>${escapeHtml("Tool")}: ${escapeHtml(toolSummary(tool) || translate("Choose a profile"))}</span>
                    <button type="button" class="dco-sheet-acc__toggle" data-artcam-tool-toggle aria-expanded="${form.toolOpen ? "true" : "false"}" aria-label="${escapeHtml(translate("Tool details"))}"></button>
                </div>
                <div class="dco-artcam-tool__body">
                    <label class="dco-artcam-field">${escapeHtml("Choose Another Tool")}
                        <select class="form-control" data-field="replacement_tool">
                            <option value="">${escapeHtml(translate("Choose"))}</option>
                            ${toolsOf(context).map(row => {
                                const name = row.tool_name || row.name || row.preset_name;
                                return `<option value="${escapeHtml(name)}">${escapeHtml(`${name} · ${row.tool_number || ""} · ${row.tool_diameter_mm || ""} mm`)}</option>`;
                            }).join("")}
                        </select>
                    </label>
                    <div class="dco-artcam-row dco-artcam-row--tool">
                        ${TOOL_FIELDS.map(([name, label]) => input(name, label, tool[name])).join("")}
                    </div>
                    <label class="dco-artcam-field dco-artcam-field--notes">${escapeHtml("Notes")}
                        <textarea class="form-control" data-field="notes">${escapeHtml(tool.notes || "")}</textarea>
                    </label>
                </div>
            </section>
            <div class="dco-artcam-actions">
                <button type="submit" class="btn btn-primary btn-sm" data-artcam-calculate>${escapeHtml(translate("Calculate Now"))}</button>
            </div>
            <p class="dco-artcam-status" data-artcam-status role="status"></p>
        </form>`;
    }

    function loadAssociation(state, row) {
        const local = (row && row.local_values) || {};
        state.artcamForm = {
            association_id: row.association_id,
            name: row.name || "",
            source: row.selection && row.selection.kind === "layer"
                ? `layer:${row.selection.operation_key}`
                : ((row.selection && row.selection.kind) || ""),
            profile_id: row.profile_id || "",
            tool_preset: local.tool_preset || "",
            fields: {
                final_depth_mm: local.final_depth_mm,
                safe_z_mm: local.safe_z_mm,
                home_x_mm: local.home_x_mm,
                home_y_mm: local.home_y_mm,
                home_z_mm: local.home_z_mm,
            },
            tool: Object.assign({}, local.tool_values || {}),
            toolOpen: false,
        };
        state.vectorSelection = (row.selection && row.selection.vector_ids) || row.vector_ids || [];
    }

    function markup(workspace, sheet, state) {
        const context = { workspace, sheet, state: state || {} };
        return `<section class="dco-artcam" data-artcam-root>
            ${editorMarkup(context)}
        </section>`;
    }

    function readEditor(host, state) {
        const form = ensureForm(state);
        const value = name => {
            const node = host.querySelector(`[data-artcam-editor] [data-field="${name}"]`);
            return node ? node.value : "";
        };
        form.name = value("name").trim();
        form.source = value("source");
        form.profile_id = value("profile_id");
        PROFILE_FIELDS.concat(HOME_FIELDS).forEach(([name]) => {
            form.fields[name] = value(name);
        });
        form.tool = form.tool || {};
        TOOL_FIELDS.forEach(([name]) => {
            form.tool[name] = value(name);
        });
        form.tool.notes = value("notes");
        form.toolOpen = !host.querySelector("[data-artcam-tool]").classList.contains("is-collapsed");
        return form;
    }

    function selectionFor(form, state) {
        if (form.source === "sheet_perimeter") return { kind: "sheet_perimeter" };
        if (form.source === "selected_vectors") {
            return { kind: "selected_vectors", vector_ids: (state.vectorSelection || []).slice() };
        }
        if (String(form.source || "").startsWith("layer:")) {
            return { kind: "layer", operation_key: String(form.source).slice(6) };
        }
        return {};
    }

    function payloadFromForm(form, state, previous) {
        const tool = Object.assign({}, form.tool || {});
        TOOL_FIELDS.forEach(([name]) => {
            if (tool[name] !== "" && tool[name] != null && name !== "notes") tool[name] = Number(tool[name]);
        });
        tool.tool_type = "Ball Nose";
        tool.tool_units = "mm";
        tool.rate_units = "mm/sec";
        tool.description = form.tool_preset || tool.description || "";
        tool.tool_preset = form.tool_preset || tool.tool_preset || "";
        return {
            association_id: form.association_id,
            name: form.name,
            profile_id: form.profile_id,
            selection: selectionFor(form, state),
            local_values: {
                profile_id: form.profile_id,
                tool_preset: form.tool_preset || ((previous && previous.local_values) || {}).tool_preset || "",
                tool_values: tool,
                final_depth_mm: form.fields.final_depth_mm,
                safe_z_mm: form.fields.safe_z_mm,
                home_x_mm: form.fields.home_x_mm,
                home_y_mm: form.fields.home_y_mm,
                home_z_mm: form.fields.home_z_mm,
            },
            toolpath_id: previous ? previous.toolpath_id || "" : "",
            toolpath_name: form.name,
        };
    }

    function fillFromProfile(form, profile) {
        form.profile_id = profile.profile_id;
        form.tool_preset = profile.tool_preset || "";
        form.fields = {
            final_depth_mm: profile.final_depth_mm,
            safe_z_mm: profile.safe_z_mm,
            home_x_mm: profile.home_x_mm,
            home_y_mm: profile.home_y_mm,
            home_z_mm: profile.home_z_mm,
        };
        form.tool = Object.assign({}, (profile.tool_values) || {});
    }

    function fillFromTool(form, tool) {
        const perSec = value => (value == null || value === "" ? "" : Number(value));
        form.tool_preset = tool.tool_name || tool.name || tool.preset_name || "";
        form.tool = {
            description: form.tool_preset,
            tool_preset: form.tool_preset,
            tool_number: tool.tool_number,
            diameter_mm: tool.tool_diameter_mm,
            stepdown_mm: tool.stepdown_mm,
            final_tool_offset_mm: tool.final_tool_offset_mm,
            stepover_size_mm: tool.stepover_size_mm,
            stepover_percent: tool.stepover_percent,
            spindle_speed_rpm: tool.spindle_speed_rpm,
            feed_rate_mm_sec: tool.feed_rate_mm_sec != null ? tool.feed_rate_mm_sec : perSec(tool.feed_rate_mm_min) / 60,
            plunge_rate_mm_sec: tool.plunge_rate_mm_sec != null ? tool.plunge_rate_mm_sec : perSec(tool.plunge_rate_mm_min) / 60,
            notes: tool.notes || "",
        };
    }

    function status(host, message, failed) {
        const node = host.querySelector("[data-artcam-status]");
        if (!node) return;
        node.textContent = message || "";
        node.classList.toggle("is-error", Boolean(failed));
    }

    function call(method, args) {
        return new Promise((resolve, reject) => {
            frappe.call({
                method,
                args,
                callback(response) { resolve((response && response.message) || {}); },
                error: reject,
            });
        });
    }

    function bind(root, context) {
        if (!root || !context || !context.state) return;
        const host = root.querySelector("[data-artcam-root]");
        if (!host || host.dataset.artcamBound === "1") return;
        host.dataset.artcamBound = "1";
        ensureForm(context.state);
        host.addEventListener("input", () => readEditor(host, context.state));
        host.addEventListener("change", event => {
            const previousProfile = ensureForm(context.state).profile_id;
            readEditor(host, context.state);
            const form = context.state.artcamForm;
            if (event.target.matches("[data-field=\"source\"]")) {
                const selected = form.source === "selected_vectors";
                if (!selected) context.state.vectorSelection = [];
                const hint = host.querySelector("[data-vector-hint]");
                const count = host.querySelector("[data-vector-count]");
                if (hint) hint.hidden = !selected;
                if (count) {
                    count.hidden = !selected;
                    count.textContent = `${(context.state.vectorSelection || []).length} Vectors Selected`;
                }
            }
            if (event.target.matches("[data-field=\"profile_id\"]")) {
                const profile = profilesOf(context).find(row => row.profile_id === event.target.value);
                if (!profile) return;
                const dirty = Object.keys(form.fields || {}).some(key => form.fields[key] !== "" && form.fields[key] != null);
                if (dirty && previousProfile && previousProfile !== profile.profile_id
                    && !window.confirm(translate("Changing the profile replaces the local settings on this association."))) {
                    event.target.value = previousProfile;
                    form.profile_id = previousProfile;
                    return;
                }
                fillFromProfile(form, profile);
                if (typeof context.refresh === "function") context.refresh();
            }
            if (event.target.matches("[data-field=\"replacement_tool\"]") && event.target.value) {
                const tool = toolsOf(context).find(row => (row.tool_name || row.name || row.preset_name) === event.target.value);
                if (!tool) return;
                fillFromTool(form, tool);
                form.toolOpen = true;
                if (typeof context.refresh === "function") context.refresh();
            }
        });
        host.addEventListener("click", event => {
            const toggle = event.target.closest("[data-artcam-tool-toggle]");
            if (toggle) {
                const section = toggle.closest("[data-artcam-tool]");
                const open = section.classList.contains("is-collapsed");
                section.classList.toggle("is-collapsed", !open);
                toggle.setAttribute("aria-expanded", open ? "true" : "false");
                ensureForm(context.state).toolOpen = open;
                return;
            }
            const cancel = event.target.closest("[data-artcam-cancel]");
            if (cancel) {
                context.state.artcamForm = blankForm();
                context.state.vectorSelection = [];
                if (typeof context.refresh === "function") context.refresh();
                return;
            }
            const remove = event.target.closest("[data-artcam-remove-association]");
            if (remove) {
                event.preventDefault();
                if (!window.confirm(translate("Remove this association from the operation order?"))) return;
                const id = remove.getAttribute("data-artcam-remove-association");
                const saved = (machining(context.sheet).associations || []).filter(row => row.association_id !== id);
                call(`${METHOD}.save_cnc_operational_sheet`, Object.assign({}, context.getArgs ? context.getArgs() : {}, {
                    machining_profiles: machining(context.sheet).profiles || [],
                    vector_associations: saved,
                })).then(workspace => {
                    if (context.state.artcamForm && context.state.artcamForm.association_id === id) {
                        context.state.artcamForm = blankForm();
                        context.state.vectorSelection = [];
                    }
                    if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                }).catch(() => status(host, translate("The association could not be removed."), true));
            }
        });
        host.addEventListener("submit", event => {
            event.preventDefault();
            calculate(host, context);
        });
    }

    function orderedAssociations(rows, next) {
        const list = (Array.isArray(rows) ? rows : []).slice();
        const index = list.findIndex(row => row && row.association_id === next.association_id);
        if (index >= 0) {
            list[index] = next;
            return list;
        }
        list.push(next);
        return list;
    }

    function calculate(host, context) {
        const state = context.state;
        if (state.artcamBusy) return;
        const form = readEditor(host, state);
        if (!form.name || !form.source || !form.profile_id) {
            status(host, translate("Enter the association name, vector source, and profile before calculating."), true);
            return;
        }
        if (form.source === "selected_vectors" && !(state.vectorSelection || []).length) {
            status(host, translate("Select at least one vector on the board."), true);
            return;
        }
        const previous = (machining(context.sheet).associations || [])
            .find(row => row.association_id === form.association_id) || null;
        const next = payloadFromForm(form, state, previous);
        const rows = orderedAssociations(machining(context.sheet).associations || [], next);
        state.artcamBusy = true;
        const button = host.querySelector("[data-artcam-calculate]");
        if (button) button.disabled = true;
        status(host, translate("Saving associations..."), false);
        const args = context.getArgs ? context.getArgs() : {};
        call(`${METHOD}.save_cnc_operational_sheet`, Object.assign({}, args, {
            machining_profiles: machining(context.sheet).profiles || [],
            vector_associations: rows,
        })).then(workspace => {
            const sheet = ((workspace.sheets || []).find(item => Number(item.sheet_no) === Number((context.sheet || {}).sheet_no))) || {};
            const saved = ((sheet.machining || {}).associations || []).find(row => row.association_id === next.association_id) || next;
            if (saved.conflict || saved.geometry_ready === false || !(saved.vector_ids || []).length) {
                status(host, translate("The association was saved, but its vectors are not ready to calculate."), true);
                state.artcamBusy = false;
                if (button) button.disabled = false;
                if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                return null;
            }
            return call(`${METHOD}.calculate_cnc_association_toolpath`, Object.assign({}, args, {
                association_id: saved.association_id,
                toolpath_name: saved.name || form.name,
                machining_profiles: (sheet.machining || {}).profiles || [],
                vector_associations: (sheet.machining || {}).associations || [],
            })).then(calculated => {
                state.artcamForm = blankForm();
                state.vectorSelection = [];
                state.artcamBusy = false;
                status(host, translate("The association was saved and calculated."), false);
                if (typeof context.onWorkspace === "function") context.onWorkspace(calculated || workspace);
            });
        }).catch(() => {
            state.artcamBusy = false;
            if (button) button.disabled = false;
            status(host, translate("The association was not calculated. The values on this page are still here."), true);
        });
    }

    window.AlmdinaArtcamMachining = Object.freeze({
        markup,
        bind,
        ensureForm,
        loadAssociation,
        orderedAssociations,
    });
})();
