(() => {
    "use strict";

    if (window.AlmdinaArtcamMachining) return;

    const METHOD = "almdina_erp.almdina_erp.services.cnc_operational_file_service";
    const PROFILE_FIELDS = Object.freeze([
        ["final_depth_mm", "Final Depth (mm)"],
        ["safe_z_mm", "Safe Z (mm)"],
        ["home_x_mm", "Home X (mm)"],
        ["home_y_mm", "Home Y (mm)"],
        ["home_z_mm", "Home Z (mm)"],
    ]);
    const TOOL_FIELDS = Object.freeze([
        ["tool_number", "Tool Number"],
        ["diameter_mm", "Tool Diameter (mm)"],
        ["stepdown_mm", "Stepdown"],
        ["final_tool_offset_mm", "Final Tool Offset"],
        ["stepover_size_mm", "Stepover Size"],
        ["stepover_percent", "Stepover Percent of D"],
        ["spindle_speed_rpm", "Spindle Speed (RPM)"],
        ["feed_rate_mm_sec", "Feed Rate (mm/sec)"],
        ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)"],
        ["notes", "Notes"],
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
        const token = Math.random().toString(36).slice(2, 12);
        return `${prefix}:${token}`;
    }

    function profileRecords(context) {
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

    function drafts(state) {
        return (state && state.artcamDrafts) || [];
    }

    function rowsFor(context) {
        const saved = machining(context.sheet).associations || [];
        const ids = new Set(saved.map(row => row && row.association_id));
        return saved.concat(drafts(context.state).filter(row => row && !ids.has(row.association_id)));
    }

    function sourceOptions(context, row) {
        const availability = machining(context.sheet).availability || {};
        const options = [];
        (availability.layers || []).forEach(layer => {
            if (!layer || !layer.operation_key) return;
            if (layer.disabled && !(row && row.selection && row.selection.operation_key === layer.operation_key)) return;
            options.push({
                value: `layer:${layer.operation_key}`,
                label: layer.dxf_layer || layer.operation_key,
            });
        });
        options.push({ value: "selected_vectors", label: "Selected Vectors" });
        const perimeter = availability.sheet_perimeter;
        const ownsPerimeter = row && row.selection && row.selection.kind === "sheet_perimeter";
        if (perimeter || ownsPerimeter) {
            options.push({ value: "sheet_perimeter", label: "Sheet Perimeter" });
        }
        return options;
    }

    function sourceValue(row) {
        const selection = (row && row.selection) || {};
        if (selection.kind === "sheet_perimeter") return "sheet_perimeter";
        if (selection.kind === "selected_vectors" || selection.kind === "vectors") return "selected_vectors";
        if (selection.kind === "layer" && selection.operation_key) return `layer:${selection.operation_key}`;
        return "";
    }

    function sourceLabel(context, row) {
        const value = sourceValue(row);
        const match = sourceOptions(context, row).find(option => option.value === value);
        return match ? match.label : "";
    }

    function selectionFromValue(value) {
        if (value === "sheet_perimeter") return { kind: "sheet_perimeter" };
        if (value === "selected_vectors") return { kind: "selected_vectors", vector_ids: [] };
        if (String(value || "").startsWith("layer:")) {
            return { kind: "layer", operation_key: String(value).slice(6) };
        }
        return {};
    }

    function localOf(row, profile) {
        const local = (row && row.local_values) || {};
        if (local && (local.final_depth_mm != null || local.tool_values)) return local;
        return profile || {};
    }

    function fieldMarkup(name, label, value, wide) {
        const text = value == null ? "" : value;
        return `<label class="${wide ? "dco-artcam-field dco-artcam-field--wide" : "dco-artcam-field"}">${escapeHtml(label)}
            <input data-field="${escapeHtml(name)}" value="${escapeHtml(text)}">
        </label>`;
    }

    function cardMarkup(context, row, open) {
        const profile = profileRecords(context).find(item => item.profile_id === row.profile_id) || {};
        const local = localOf(row, profile);
        const tool = local.tool_values || profile.tool_values || {};
        const options = sourceOptions(context, row);
        const selected = sourceValue(row);
        const conflict = row.conflict === "sheet_perimeter_unavailable"
            ? "Connected Perimeter is off. This Sheet Perimeter association must be changed before calculation."
            : (selected === "selected_vectors"
                ? "Direct vector selection will be available later. This association cannot be calculated until vectors are selected on the board."
                : "");
        return `<article class="dco-artcam-card${open ? " is-open" : ""}" data-association-id="${escapeHtml(row.association_id)}" data-open="${open ? "1" : "0"}">
            <header class="dco-artcam-card__head">
                <button type="button" class="dco-artcam-card__toggle" data-artcam-card-toggle aria-expanded="${open ? "true" : "false"}">
                    <span>
                        <strong data-artcam-card-title>${escapeHtml(row.name || "Association")}</strong>
                        <small>${escapeHtml(sourceLabel(context, row) || "Vector Source")}</small>
                    </span>
                    <span class="dco-sheet-acc__chevron" aria-hidden="true"></span>
                </button>
                <button type="button" class="btn btn-default btn-xs" data-artcam-remove-association="${escapeHtml(row.association_id)}">${escapeHtml(translate("Remove"))}</button>
            </header>
            <div class="dco-artcam-card__body"${open ? "" : " hidden"}>
                <label class="dco-artcam-field dco-artcam-field--wide">${escapeHtml("Association Name")}
                    <input data-field="name" value="${escapeHtml(row.name || "")}">
                </label>
                <label class="dco-artcam-field">${escapeHtml("Vector Source")}
                    <select data-field="source">
                        <option value="">${escapeHtml(translate("Choose"))}</option>
                        ${options.map(option => `<option value="${escapeHtml(option.value)}"${option.value === selected ? " selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
                    </select>
                </label>
                <label class="dco-artcam-field">${escapeHtml("Profile")}
                    <select data-field="profile_id">
                        <option value="">${escapeHtml(translate("Choose"))}</option>
                        ${profileRecords(context).map(item => `<option value="${escapeHtml(item.profile_id)}"${item.profile_id === row.profile_id ? " selected" : ""}>${escapeHtml(item.name || item.profile_id)}</option>`).join("")}
                    </select>
                </label>
                ${conflict ? `<p class="dco-artcam-note" role="status">${escapeHtml(conflict)}</p>` : ""}
                <div class="dco-artcam-fields">
                    ${PROFILE_FIELDS.map(([name, label]) => fieldMarkup(name, label, local[name])).join("")}
                </div>
                <section class="dco-artcam-tool" data-open="0">
                    <button type="button" class="dco-artcam-tool__toggle" data-artcam-tool-toggle aria-expanded="false">
                        <span>${escapeHtml("Tool Details")}</span>
                        <span class="dco-sheet-acc__chevron" aria-hidden="true"></span>
                    </button>
                    <div class="dco-artcam-fields" hidden>
                        <p class="dco-artcam-note">${escapeHtml(tool.description || tool.tool_preset || profile.tool_preset || "")}</p>
                        ${TOOL_FIELDS.map(([name, label]) => fieldMarkup(name, label, tool[name], name === "notes")).join("")}
                    </div>
                </section>
            </div>
        </article>`;
    }

    function markup(workspace, sheet, state) {
        const context = { workspace, sheet, state };
        const openMap = (state && state.artcamOpen) || {};
        const rows = rowsFor(context);
        const cards = rows.map((row, index) => cardMarkup(
            context,
            row,
            openMap[row.association_id] !== undefined ? Boolean(openMap[row.association_id]) : index === 0
        )).join("");
        return `<section class="dco-artcam" data-artcam-root>
            <div class="dco-artcam-list">${cards || `<p class="dco-artcam-note">${escapeHtml(translate("Add an association to define the machining for this sheet."))}</p>`}</div>
            <div class="dco-artcam-actions">
                <button type="button" class="btn btn-default btn-sm" data-artcam-add>${escapeHtml(translate("Add association"))}</button>
                <button type="button" class="btn btn-primary btn-sm" data-artcam-calculate>${escapeHtml(translate("Calculate Now"))}</button>
            </div>
            <p class="dco-artcam-status" data-artcam-status role="status"></p>
        </section>`;
    }

    function readCard(card, previous) {
        const value = name => {
            const input = card.querySelector(`[data-field="${name}"]`);
            return input ? input.value : "";
        };
        const profileId = value("profile_id");
        const selection = selectionFromValue(value("source"));
        if (previous && previous.selection && previous.selection.kind === "vectors" && selection.kind === "selected_vectors") {
            selection.kind = "vectors";
            selection.vector_ids = (previous.selection.vector_ids || previous.vector_ids || []).slice();
        }
        const tool = Object.assign({}, ((previous && previous.local_values) || {}).tool_values || {});
        TOOL_FIELDS.forEach(([name]) => {
            const next = value(name);
            if (next !== "") tool[name] = name === "notes" ? next : Number(next);
        });
        tool.tool_type = "Ball Nose";
        tool.tool_units = "mm";
        tool.rate_units = "mm/sec";
        if (tool.tool_number != null && tool.tool_number !== "") tool.tool_number_display = Number(tool.tool_number);
        return {
            association_id: card.getAttribute("data-association-id"),
            name: value("name").trim(),
            profile_id: profileId,
            selection,
            local_values: {
                profile_id: profileId,
                name: value("name").trim(),
                tool_preset: ((previous && previous.local_values) || {}).tool_preset || "",
                tool_values: tool,
                final_depth_mm: value("final_depth_mm"),
                safe_z_mm: value("safe_z_mm"),
                home_x_mm: value("home_x_mm"),
                home_y_mm: value("home_y_mm"),
                home_z_mm: value("home_z_mm"),
            },
            toolpath_id: previous ? previous.toolpath_id || "" : "",
            toolpath_name: previous ? previous.toolpath_name || value("name").trim() : value("name").trim(),
            vector_ids: previous ? previous.vector_ids || [] : [],
        };
    }

    function rememberOpen(host, state) {
        if (!state) return;
        state.artcamOpen = {};
        host.querySelectorAll("[data-association-id]").forEach(card => {
            state.artcamOpen[card.getAttribute("data-association-id")] = card.getAttribute("data-open") === "1";
        });
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
                error(response) { reject(response); },
            });
        });
    }

    function bind(root, context) {
        if (!root || !context) return;
        const host = root.querySelector("[data-artcam-root]");
        if (!host || host.dataset.artcamBound === "1") return;
        host.dataset.artcamBound = "1";
        host.addEventListener("click", event => {
            const toggle = event.target.closest("[data-artcam-card-toggle]");
            if (toggle) {
                const card = toggle.closest("[data-association-id]");
                const body = card && card.querySelector(".dco-artcam-card__body");
                const open = card.getAttribute("data-open") !== "1";
                card.setAttribute("data-open", open ? "1" : "0");
                card.classList.toggle("is-open", open);
                if (body) body.hidden = !open;
                toggle.setAttribute("aria-expanded", open ? "true" : "false");
                rememberOpen(host, context.state);
                return;
            }
            const toolToggle = event.target.closest("[data-artcam-tool-toggle]");
            if (toolToggle) {
                const section = toolToggle.closest(".dco-artcam-tool");
                const body = section && section.querySelector(".dco-artcam-fields");
                const open = section.getAttribute("data-open") !== "1";
                section.setAttribute("data-open", open ? "1" : "0");
                if (body) body.hidden = !open;
                toolToggle.setAttribute("aria-expanded", open ? "true" : "false");
                return;
            }
            const remove = event.target.closest("[data-artcam-remove-association]");
            if (remove) {
                event.preventDefault();
                if (!window.confirm(translate("Remove this association from the operation order?"))) return;
                const id = remove.getAttribute("data-artcam-remove-association");
                if (context.state) {
                    context.state.artcamDrafts = drafts(context.state).filter(row => row.association_id !== id);
                }
                const saved = (machining(context.sheet).associations || []).filter(row => row.association_id !== id);
                call(`${METHOD}.save_cnc_operational_sheet`, Object.assign({}, context.getArgs ? context.getArgs() : {}, {
                    machining_profiles: machining(context.sheet).profiles || [],
                    vector_associations: saved,
                })).then(workspace => {
                    if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                }).catch(() => status(host, translate("The association could not be removed."), true));
                return;
            }
            if (event.target.closest("[data-artcam-add]")) {
                event.preventDefault();
                const draft = {
                    association_id: newId("association"),
                    name: "",
                    profile_id: "",
                    selection: {},
                    local_values: {},
                };
                if (context.state) {
                    context.state.artcamDrafts = drafts(context.state).concat([draft]);
                    context.state.artcamOpen = Object.assign({}, context.state.artcamOpen, { [draft.association_id]: true });
                }
                if (typeof context.refresh === "function") context.refresh();
                return;
            }
            if (event.target.closest("[data-artcam-calculate]")) {
                event.preventDefault();
                calculate(host, context);
            }
        });
        host.addEventListener("change", event => {
            const profile = event.target.closest("[data-field=\"profile_id\"]");
            if (!profile) return;
            const card = profile.closest("[data-association-id]");
            const next = profileRecords(context).find(row => row.profile_id === profile.value);
            if (!next) return;
            const current = rowsFor(context).find(row => row.association_id === card.getAttribute("data-association-id"));
            const dirty = current && current.local_values && current.profile_id && current.profile_id !== next.profile_id;
            if (dirty && !window.confirm(translate("Changing the profile replaces the local settings on this association."))) {
                profile.value = current.profile_id;
                return;
            }
            const replacement = Object.assign({}, current || {}, {
                profile_id: next.profile_id,
                local_values: {
                    profile_id: next.profile_id,
                    tool_preset: next.tool_preset,
                    tool_values: Object.assign({}, next.tool_values || {}),
                    final_depth_mm: next.final_depth_mm,
                    safe_z_mm: next.safe_z_mm,
                    home_x_mm: next.home_x_mm,
                    home_y_mm: next.home_y_mm,
                    home_z_mm: next.home_z_mm,
                },
            });
            if (context.state) {
                context.state.artcamDrafts = drafts(context.state)
                    .filter(row => row.association_id !== replacement.association_id)
                    .concat(current && (machining(context.sheet).associations || []).some(row => row.association_id === current.association_id) ? [] : [replacement]);
                const saved = machining(context.sheet).associations || [];
                const index = saved.findIndex(row => row.association_id === replacement.association_id);
                if (index >= 0) saved.splice(index, 1, replacement);
            }
            if (typeof context.refresh === "function") context.refresh();
        });
    }

    function calculate(host, context) {
        const known = rowsFor(context);
        const cards = Array.from(host.querySelectorAll("[data-association-id]"));
        const associations = cards.map(card => {
            const previous = known.find(row => row.association_id === card.getAttribute("data-association-id")) || {};
            return readCard(card, previous);
        });
        if (associations.some(row => !row.name || !row.profile_id || !row.selection || !row.selection.kind)) {
            status(host, translate("Enter the association name, vector source, and profile before calculating."), true);
            return;
        }
        const ids = new Set();
        if (associations.some(row => ids.has(row.association_id) || !ids.add(row.association_id))) {
            status(host, translate("Each association must keep its own identity."), true);
            return;
        }
        status(host, translate("Saving associations..."), false);
        const args = context.getArgs ? context.getArgs() : {};
        call(`${METHOD}.save_cnc_operational_sheet`, Object.assign({}, args, {
            machining_profiles: machining(context.sheet).profiles || [],
            vector_associations: associations,
        })).then(workspace => {
            if (context.state) context.state.artcamDrafts = [];
            const sheet = ((workspace.sheets || []).find(item => Number(item.sheet_no) === Number((context.sheet || {}).sheet_no))) || {};
            const saved = ((sheet.machining || {}).associations) || associations;
            const ready = saved.filter(row => row && row.geometry_ready !== false && !row.conflict && (row.vector_ids || []).length);
            const pending = saved.filter(row => !ready.includes(row));
            if (!ready.length) {
                status(host, pending.length
                    ? translate("The associations were saved. Direct selection or Sheet Perimeter must be resolved before calculation.")
                    : translate("There is no association ready to calculate."), true);
                if (typeof context.onWorkspace === "function") context.onWorkspace(workspace);
                return null;
            }
            return ready.reduce((chain, row) => chain.then(() => call(
                `${METHOD}.calculate_cnc_association_toolpath`,
                Object.assign({}, args, {
                    association_id: row.association_id,
                    toolpath_name: row.name,
                    machining_profiles: (sheet.machining || {}).profiles || [],
                    vector_associations: saved,
                })
            )), Promise.resolve(workspace)).then(last => {
                status(host, translate("The associations were saved and calculated."), false);
                if (typeof context.onWorkspace === "function") context.onWorkspace(last || workspace);
            });
        }).catch(() => {
            status(host, translate("The associations were not saved. The values on this page are still here."), true);
        });
    }

    window.AlmdinaArtcamMachining = Object.freeze({ markup, bind });
})();
