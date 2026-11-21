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
        ["stepdown_mm", "Stepdown"],
        ["stepover_size_mm", "Stepover Size (mm)"],
        ["spindle_speed_rpm", "Spindle Speed (RPM)"],
    ]);
    const ALLOWED_TOOL_FIELDS = Object.freeze([
        "tool_number",
        "stepdown_mm",
        "stepover_size_mm",
        "spindle_speed_rpm",
        "feed_rate_mm_sec",
        "plunge_rate_mm_sec",
        "feed_rate_mm_min",
        "plunge_rate_mm_min",
    ]);

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof __ === "function") return __(message);
        return String(message || "");
    }

    function toolsOf(context) {
        return ((context.workspace && context.workspace.presets) || [])
            .filter(row => row && row.name && row.enabled !== false);
    }

    function toolOptions(context, form) {
        const rows = toolsOf(context).slice();
        const current = String((form && form.tool_preset) || "");
        if (current && !rows.some(row => row.name === current)) {
            const tool = (form && form.tool) || {};
            rows.unshift({
                name: current,
                description: tool.description || tool.tool_name || current,
                enabled: true,
            });
        }
        return rows;
    }

    function toolPayload(preset) {
        const source = preset || {};
        const number = displayToolNumber(source.tool_number);
        return {
            description: source.description || source.tool_name || source.name || "",
            tool_name: source.tool_name || source.description || source.name || "",
            tool_type: source.tool_type || "",
            tool_number: number,
            tool_units: source.tool_units || "mm",
            rate_units: source.rate_units || "mm/sec",
            notes: source.notes || "",
            diameter_mm: source.diameter_mm != null ? source.diameter_mm : source.tool_diameter_mm,
            stepdown_mm: source.stepdown_mm != null ? source.stepdown_mm : source.pass_depth_mm,
            final_tool_offset_mm: source.final_tool_offset_mm,
            stepover_size_mm: source.stepover_size_mm,
            stepover_percent: source.stepover_percent,
            spindle_speed_rpm: source.spindle_speed_rpm,
            feed_rate_mm_sec: source.feed_rate_mm_sec,
            plunge_rate_mm_sec: source.plunge_rate_mm_sec,
            feed_rate_mm_min: source.feed_rate_mm_min,
            plunge_rate_mm_min: source.plunge_rate_mm_min,
        };
    }

    function displayToolNumber(value) {
        if (value == null || value === "") return "";
        const raw = String(value).trim();
        const match = raw.match(/^(?:T)?([1-9][0-9]{0,2})$/i);
        return match ? match[1] : raw;
    }

    function rateFields(tool) {
        if (String((tool && tool.rate_units) || "") === "mm/min") {
            return [
                ["feed_rate_mm_min", "Feed Rate (mm/min)"],
                ["plunge_rate_mm_min", "Plunge Rate (mm/min)"],
            ];
        }
        return [
            ["feed_rate_mm_sec", "Feed Rate (mm/sec)"],
            ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)"],
        ];
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

    function formAfterCalculation(form) {
        const current = form || blankForm();
        return {
            association_id: newId("association"),
            name: "",
            source: "",
            profile_id: current.profile_id || "",
            tool_preset: current.tool_preset || "",
            fields: Object.assign({}, current.fields || {}),
            tool: Object.assign({}, current.tool || {}),
            toolOpen: false,
        };
    }

    function ensureForm(state) {
        if (!state.artcamForm || !state.artcamForm.association_id) state.artcamForm = blankForm();
        if (!Array.isArray(state.vectorSelection)) state.vectorSelection = [];
        return state.artcamForm;
    }

    function sourceOptions(context, form) {
        const data = machining(context.sheet);
        const availability = data.availability || {};
        const editingId = String((form && form.association_id) || "");
        const vectorOperations = new Map(
            (availability.vectors || []).map(row => [String(row.vector_id || ""), String(row.operation_key || "")])
        );
        const ownedOperations = new Set();
        let perimeterOwned = false;
        (data.associations || []).forEach(row => {
            if (!row || String(row.association_id || "") === editingId) return;
            const selection = row.selection || {};
            if (selection.kind === "layer" && selection.operation_key) {
                ownedOperations.add(String(selection.operation_key));
            }
            if (selection.kind === "sheet_perimeter") perimeterOwned = true;
            (row.vector_ids || []).forEach(id => {
                const vectorId = String(id);
                if (vectorId === "cut_path:sheet_perimeter") perimeterOwned = true;
                const operation = vectorOperations.get(vectorId)
                    || (vectorId === "cut_path:sheet_perimeter" ? "" : vectorId.split(":", 1)[0]);
                if (operation) ownedOperations.add(operation);
            });
        });
        const options = [];
        (availability.layers || []).forEach(layer => {
            if (!layer || !layer.operation_key) return;
            const current = form && form.source === `layer:${layer.operation_key}`;
            if ((layer.disabled || ownedOperations.has(String(layer.operation_key))) && !current) return;
            options.push({ value: `layer:${layer.operation_key}`, label: layer.dxf_layer || layer.operation_key });
        });
        options.push({ value: "selected_vectors", label: "Selected Vectors" });
        const perimeter = availability.sheet_perimeter;
        const serverAvailable = Boolean(perimeter && !perimeter.disabled);
        const ready = context.state ? context.state.perimeterGeometryReady : null;
        const geometryOk = ready === true || (ready == null && serverAvailable);
        if (perimeterMode(context) === "connected" && geometryOk && !perimeterOwned) {
            options.push({ value: "sheet_perimeter", label: "SHEET_PERIMETER" });
        }
        return options;
    }

    function sourceLabel(value, context) {
        if (value === "sheet_perimeter") return "SHEET_PERIMETER";
        if (value === "selected_vectors") return "Selected Vectors";
        const layer = String(value || "").startsWith("layer:") ? String(value).slice(6) : "";
        const match = ((machining(context.sheet).availability || {}).layers || [])
            .find(row => row.operation_key === layer);
        return match ? (match.dxf_layer || layer) : layer;
    }

    function toolPickerMarkup(context, form) {
        const picker = window.AlmdinaCncToolPicker;
        const tool = form.tool || {};
        const selected = String(form.tool_preset || "");
        const rows = toolOptions(context, form).map(row => ({
            value: row.name,
            label: row.description || row.tool_name || row.name,
        }));
        const selectedRow = rows.find(row => row.value === selected);
        const fields = selected ? TOOL_FIELDS.concat(rateFields(tool)).map(([name, label]) => ({
            name,
            label: fieldLabel("tool", label),
            value: tool[name],
        })) : [];
        const spec = {
            label: fieldLabel("profile", "Tool"),
            changeLabel: fieldLabel("profile", "Tool"),
            emptyLabel: translate("Choose a tool"),
            selected,
            selectedLabel: (selectedRow && selectedRow.label) || tool.description || tool.tool_name || selected,
            tools: rows,
            fields,
            valueAttribute: "data-artcam-tool-summary",
            readOnly: selected ? [{
                label: fieldLabel("tool", "Diameter (mm)"),
                value: tool.diameter_mm == null ? "" : tool.diameter_mm,
            }] : [],
        };
        if (picker && typeof picker.markup === "function") return picker.markup(spec);
        return "";
    }

    function fieldLabel(kind, english) {
        const labels = window.AlmdinaCncLabels;
        if (kind === "tool" && labels && typeof labels.toolLabel === "function") return labels.toolLabel(english);
        if (labels && typeof labels.profileLabel === "function") return labels.profileLabel(english);
        return translate(english);
    }

    function input(name, label, value, kind) {
        return `<label class="dco-artcam-field">${escapeHtml(fieldLabel(kind || "profile", label))}
            <input class="form-control" data-field="${escapeHtml(name)}" value="${escapeHtml(value == null ? "" : value)}">
        </label>`;
    }

    function perimeterMode(context) {
        return context && context.state && context.state.perimeterJoinMode === "connected"
            ? "connected"
            : "disconnected";
    }

    function perimeterHeld(context, form) {
        const editingId = String((form && form.association_id) || "");
        return (machining(context.sheet).associations || []).some(row => {
            if (!row || String(row.association_id || "") === editingId) return false;
            if (row.selection && row.selection.kind === "sheet_perimeter") return true;
            return (row.vector_ids || []).some(id => String(id) === "cut_path:sheet_perimeter");
        });
    }

    function perimeterSourceNote(context, form) {
        const mode = perimeterMode(context);
        const ready = context.state ? context.state.perimeterGeometryReady : null;
        const cleared = Boolean(form && form.perimeterSourceCleared);
        const held = perimeterHeld(context, form);
        if (mode !== "connected" && (cleared || held)) {
            return translate("The sheet perimeter is disconnected, so it cannot be chosen as a vector source. Existing assignments keep their settings and their place in the operation order. Reconnect the perimeter, or edit the assignment and release the sheet perimeter.");
        }
        if (mode === "connected" && ready === false && (cleared || held)) {
            return translate("The sheet perimeter is not valid for assignment. Existing assignments keep their settings. Fix the perimeter geometry before choosing it again.");
        }
        return "";
    }

    function clearEditingPerimeterSource(state) {
        const form = state && state.artcamForm;
        if (!form || form.source !== "sheet_perimeter") return false;
        form.source = "";
        form.perimeterSourceCleared = true;
        return true;
    }

    function editorMarkup(context) {
        const form = ensureForm(context.state);
        const profileChosen = Boolean(form.profile_id);
        const count = (context.state.vectorSelection || []).length;
        const selected = form.source === "selected_vectors";
        const options = sourceOptions(context, form);
        const editingRow = (machining(context.sheet).associations || [])
            .find(row => row.association_id === form.association_id) || null;
        const editing = Boolean(editingRow);
        const ownsSavedPerimeter = Boolean(
            editingRow
            && (editingRow.vector_ids || []).some(id => String(id) === "cut_path:sheet_perimeter")
        );
        return `<form class="dco-artcam-editor" data-artcam-editor>
            ${editing ? `<p class="dco-artcam-note" data-artcam-editing>${escapeHtml(translate("Editing"))}: ${escapeHtml(form.name || form.association_id)}
                <button type="button" class="btn btn-default btn-xs" data-artcam-cancel>${escapeHtml(translate("New association"))}</button>
            </p>` : ""}
            <div class="dco-artcam-row dco-artcam-row--main">
                <label class="dco-artcam-field">${escapeHtml(fieldLabel("profile", "Association Name"))}
                    <input class="form-control" data-field="name" value="${escapeHtml(form.name || "")}">
                </label>
                <label class="dco-artcam-field">${escapeHtml(fieldLabel("profile", "Vector Source"))}
                    <select class="form-control" data-field="source">
                        <option value="">${escapeHtml(translate("Choose"))}</option>
                        ${options.map(option => `<option value="${escapeHtml(option.value)}"${option.value === form.source ? " selected" : ""}>${escapeHtml(option.value === "sheet_perimeter" || option.value === "selected_vectors" ? translate(option.label) : option.label)}</option>`).join("")}
                    </select>
                </label>
                <p class="dco-artcam-note" data-perimeter-source-note${perimeterSourceNote(context, form) ? "" : " hidden"}>${escapeHtml(perimeterSourceNote(context, form))}</p>
                <label class="dco-artcam-field">${escapeHtml(fieldLabel("profile", "Profile"))}
                    <select class="form-control" data-field="profile_id">
                        <option value="">${escapeHtml(translate("Choose"))}</option>
                        ${profilesOf(context).map(row => `<option value="${escapeHtml(row.profile_id)}"${row.profile_id === form.profile_id ? " selected" : ""}>${escapeHtml(row.name || row.profile_id)}</option>`).join("")}
                    </select>
                </label>
            </div>
            ${ownsSavedPerimeter ? `<label class="dco-artcam-note"><input type="checkbox" data-field="release_perimeter"> ${escapeHtml(translate("Release the sheet perimeter from this association"))}</label>` : ""}
            <p class="dco-artcam-note" data-vector-hint${selected ? "" : " hidden"}>${escapeHtml(translate("Shift + Click to select vectors"))}</p>
            <p class="dco-artcam-note" data-vector-count${selected ? "" : " hidden"}>${escapeHtml(`${count} Vectors Selected`)}</p>
            ${profileChosen ? `<div class="dco-artcam-row dco-artcam-row--pair">
                ${PROFILE_FIELDS.map(([name, label]) => input(name, label, form.fields[name], "profile")).join("")}
            </div>
            <div class="dco-artcam-home">
                <span>${escapeHtml(fieldLabel("profile", "Home Position (mm)"))}</span>
                <div class="dco-artcam-row dco-artcam-row--home">
                    ${HOME_FIELDS.map(([name, label]) => input(name, label, form.fields[name], "profile")).join("")}
                </div>
            </div>
            ${toolPickerMarkup(context, form)}` : ""}
            <div class="dco-artcam-actions almdina-ui">
                <button type="submit" class="btn alm-btn-primary btn-sm" data-artcam-calculate>${escapeHtml(translate("Calculate Now"))}</button>
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
            tool: toolPayload(local.tool_values || {}),
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
        const toolNode = host.querySelector("[data-artcam-editor] [data-field=\"tool_preset\"]");
        if (toolNode) form.tool_preset = toolNode.value;
        PROFILE_FIELDS.concat(HOME_FIELDS).forEach(([name]) => {
            form.fields[name] = value(name);
        });
        const previousTool = Object.assign({}, form.tool || {});
        form.tool = previousTool;
        TOOL_FIELDS.concat(rateFields(previousTool)).forEach(([name]) => {
            form.tool[name] = value(name);
        });
        const release = host.querySelector("[data-artcam-editor] [data-field=\"release_perimeter\"]");
        form.releasePerimeter = Boolean(release && release.checked);
        const panel = host.querySelector("[data-tool-picker-panel]");
        form.toolOpen = Boolean(panel && !panel.hidden);
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
        const sourceTool = form.tool || {};
        const tool = {};
        ALLOWED_TOOL_FIELDS.forEach(name => {
            if (sourceTool[name] !== "" && sourceTool[name] != null) tool[name] = Number(sourceTool[name]);
        });
        const payload = {
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
        if (previous && Array.isArray(previous.vector_ids)) {
            payload.vector_ids = previous.vector_ids.filter(id => !(
                form.releasePerimeter && String(id) === "cut_path:sheet_perimeter"
            ));
        }
        return payload;
    }

    function fillFromProfile(form, profile) {
        form.profile_id = profile.profile_id;
        form.tool_preset = profile.tool_preset || "";
        form.toolOpen = false;
        form.fields = {
            final_depth_mm: profile.final_depth_mm,
            safe_z_mm: profile.safe_z_mm,
            home_x_mm: profile.home_x_mm,
            home_y_mm: profile.home_y_mm,
            home_z_mm: profile.home_z_mm,
        };
        form.tool = toolPayload(profile.tool_values || {});
    }

    function reportFailure(title, fallback, error) {
        const signature = `${title}|${fallback}`;
        const now = Date.now();
        if (reportFailure.lastSignature === signature && now - reportFailure.lastAt < 1000) return;
        reportFailure.lastSignature = signature;
        reportFailure.lastAt = now;
        const show = () => {
            if (window.frappe && frappe.error_dialog && typeof frappe.error_dialog.hide === "function") {
                frappe.error_dialog.hide();
            }
            const board = window.AlmdinaOperationalFilesUX;
            if (board && typeof board.showSheetIssueDialog === "function") {
                const lines = String(fallback || "").split("\n").map(line => line.trim()).filter(Boolean);
                const issue = lines.length >= 3
                    ? { problem: lines[0], target: lines[1], action: lines[2], code: "tool_diameter_plan_mismatch" }
                    : {
                        problem: fallback,
                        action: translate("Correct the listed issue, then generate the NC file again."),
                    };
                board.showSheetIssueDialog(title, [issue], lines.length >= 3 ? {} : { error });
                return;
            }
            if (window.frappe && frappe.msgprint) frappe.msgprint(fallback);
        };
        if (window.setTimeout) window.setTimeout(show, 0);
        else show();
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
                silent: true,
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
            const previousTool = ensureForm(context.state).tool_preset;
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
                if (typeof context.paintBoard === "function") context.paintBoard();
            }
            if (event.target.matches("[data-field=\"profile_id\"]")) {
                const profile = profilesOf(context).find(row => row.profile_id === event.target.value);
                if (!profile) {
                    form.profile_id = "";
                    form.tool_preset = "";
                    form.fields = {};
                    form.tool = {};
                    form.toolOpen = false;
                    if (typeof context.refresh === "function") context.refresh();
                    return;
                }
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
            if (event.target.matches("[data-field=\"tool_preset\"]") && form.tool_preset !== previousTool) {
                const preset = toolsOf(context).find(row => row.name === form.tool_preset);
                form.tool = preset ? toolPayload(preset) : {};
                form.toolOpen = false;
                if (typeof context.refresh === "function") context.refresh();
            }
            if (event.target.matches("[data-field=\"stepover_size_mm\"]")) readEditor(host, context.state);
        });
        const pickerApi = window.AlmdinaCncToolPicker;
        if (pickerApi && typeof pickerApi.bind === "function") pickerApi.bind(host);
        host.addEventListener("click", event => {
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
                const mutationRequest = context.beginMutation ? context.beginMutation() : 1;
                if (!mutationRequest) return;
                call(`${METHOD}.delete_cnc_association`, Object.assign({}, context.getArgs ? context.getArgs() : {}, {
                    association_id: id,
                })).then(workspace => {
                    if (context.finishMutation && !context.finishMutation(mutationRequest)) return;
                    if (context.state.artcamForm && context.state.artcamForm.association_id === id) {
                        context.state.artcamForm = blankForm();
                        context.state.vectorSelection = [];
                    }
                    if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                }).catch(() => {
                    if (context.finishMutation && !context.finishMutation(mutationRequest)) return;
                    status(host, translate("The association could not be removed."), true);
                });
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
            reportFailure(translate("The association was not calculated."), translate("Select at least one vector on the board."));
            return;
        }
        const owned = new Set();
        (machining(context.sheet).associations || []).forEach(row => {
            if (!row || row.association_id === form.association_id) return;
            (row.vector_ids || []).forEach(id => owned.add(String(id)));
        });
        const candidateVectorIds = form.source === "selected_vectors"
            ? (state.vectorSelection || []).slice()
            : String(form.source || "").startsWith("layer:")
                ? (((machining(context.sheet).availability || {}).vectors || [])
                    .filter(row => row && row.operation_key === String(form.source).slice(6))
                    .map(row => row.vector_id))
                : [];
        const clash = candidateVectorIds.filter(id => owned.has(String(id)));
        if ((form.source === "selected_vectors" || String(form.source || "").startsWith("layer:")) && clash.length) {
            const message = translate("That vector or layer is already assigned.");
            status(host, message, true);
            reportFailure(translate("The association was not calculated."), `${message} ${clash.join(", ")}`);
            return;
        }
        if (form.source === "sheet_perimeter") {
            const owner = (machining(context.sheet).associations || []).find(row => (
                row
                && row.association_id !== form.association_id
                && (row.vector_ids || []).some(id => String(id) === "cut_path:sheet_perimeter")
            ));
            if (owner) {
                const message = translate("The sheet perimeter already belongs to {0}. Edit that association and release the sheet perimeter before assigning it on its own.")
                    .split("{0}").join(owner.name || owner.association_id);
                status(host, message, true);
                reportFailure(translate("The association was not calculated."), message);
                return;
            }
        }
        const previous = (machining(context.sheet).associations || [])
            .find(row => row.association_id === form.association_id) || null;
        const next = payloadFromForm(form, state, previous);
        const rows = orderedAssociations(machining(context.sheet).associations || [], next);
        const mutationRequest = context.beginMutation ? context.beginMutation() : 1;
        if (!mutationRequest) return;
        state.artcamBusy = true;
        const button = host.querySelector("[data-artcam-calculate]");
        if (button) button.disabled = true;
        if (!state.calculationRequestId || state.calculationAssociationId !== next.association_id) {
            state.calculationRequestId = newId();
            state.calculationAssociationId = next.association_id;
        }
        status(host, translate("Calculating the toolpath..."), false);
        const args = context.getArgs ? context.getArgs() : {};
        call(`${METHOD}.calculate_cnc_association_toolpath`, Object.assign({}, args, {
            association_id: next.association_id,
            toolpath_name: next.name || form.name,
            machining_profiles: machining(context.sheet).profiles || [],
            vector_associations: rows,
            calculation_request_id: state.calculationRequestId,
        })).then(workspace => {
            if (context.finishMutation && !context.finishMutation(mutationRequest)) return;
            state.artcamForm = formAfterCalculation(form);
            state.vectorSelection = [];
            state.calculationRequestId = "";
            state.artcamBusy = false;
            status(host, translate("The association was saved and calculated."), false);
            if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
        }).catch(error => {
            const problem = window.AlmdinaFrontend && window.AlmdinaFrontend.normalizeError
                ? window.AlmdinaFrontend.normalizeError(error)
                : { outcome: "unknown", message: "" };
            const release = () => {
                if (context.finishMutation && !context.finishMutation(mutationRequest)) return false;
                state.artcamBusy = false;
                if (button) button.disabled = false;
                return true;
            };
            if (problem.outcome === "unknown") {
                call(`${METHOD}.get_cnc_operational_workspace`, args).then(workspace => {
                    const sheet = ((workspace.sheets || []).find(item => Number(item.sheet_no) === Number((context.sheet || {}).sheet_no))) || {};
                    const saved = ((sheet.machining || {}).associations || []).find(row => row.association_id === next.association_id);
                    if (!release()) return;
                    if (saved && saved.toolpath_id) {
                        state.artcamForm = formAfterCalculation(form);
                        state.vectorSelection = [];
                        state.calculationRequestId = "";
                        status(host, translate("The association was saved and calculated."), false);
                        if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                        return;
                    }
                    status(host, translate("The result could not be confirmed. Check the current status before repeating the operation."), true);
                    if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                }).catch(() => {
                    if (!release()) return;
                    status(host, translate("The result could not be confirmed. Check the current status before repeating the operation."), true);
                });
                return;
            }
            state.calculationRequestId = "";
            if (!release()) return;
            status(host, problem.message || translate("The association was not calculated. The values on this page are still here."), true);
            reportFailure(
                translate("The association was not calculated."),
                problem.message || translate("The association was not calculated. The values on this page are still here."),
                error
            );
        });
    }

    function syncPerimeterSource(host, context) {
        const state = (context && context.state) || {};
        const form = state.artcamForm || null;
        const mode = perimeterMode(context);
        const ready = state.perimeterGeometryReady;
        if (form && form.source === "sheet_perimeter" && (mode !== "connected" || ready === false)) {
            clearEditingPerimeterSource(state);
        }
        const options = sourceOptions(context, state.artcamForm || form);
        const select = host && host.querySelector
            ? host.querySelector('[data-artcam-editor] [data-field="source"]')
            : null;
        if (select) {
            const current = String((state.artcamForm && state.artcamForm.source) || "");
            select.innerHTML = `<option value="">${escapeHtml(translate("Choose"))}</option>${options.map(option => {
                const label = option.value === "sheet_perimeter" || option.value === "selected_vectors"
                    ? translate(option.label)
                    : option.label;
                return `<option value="${escapeHtml(option.value)}"${option.value === current ? " selected" : ""}>${escapeHtml(label)}</option>`;
            }).join("")}`;
            select.value = options.some(option => option.value === current) ? current : "";
            if (state.artcamForm && select.value !== current) state.artcamForm.source = select.value;
        }
        const note = host && host.querySelector ? host.querySelector("[data-perimeter-source-note]") : null;
        const text = perimeterSourceNote(context, state.artcamForm || form);
        if (note) {
            note.hidden = !text;
            note.textContent = text;
        }
        return options;
    }

    window.AlmdinaArtcamMachining = Object.freeze({
        markup,
        bind,
        ensureForm,
        loadAssociation,
        formAfterCalculation,
        orderedAssociations,
        sourceOptions,
        syncPerimeterSource,
        clearEditingPerimeterSource,
    });
})();
