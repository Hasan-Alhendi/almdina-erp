(() => {
    "use strict";

    if (window.AlmdinaOperationalFilesUX) return;

    const METHOD = "almdina_erp.almdina_erp.services.cnc_operational_file_service";
    const OPERATION_LABELS = Object.freeze({
        cut_path: "Cut between pieces",
        liner: "Liner operation",
        back_groove: "Rear groove",
        recessed_handle_cutout: "Handle recess",
    });
    const STATUS_LABELS = Object.freeze({
        "Not Generated": "Not generated",
        Generated: "Generated",
        "Needs Regeneration": "Needs regeneration",
    });
    const INTERNAL_OPERATIONS = Object.freeze([
        "liner",
        "recessed_handle_cutout",
        "back_groove",
    ]);
    const CONFLICT_MESSAGES = Object.freeze({
        number: "One board file must keep the same physical tool number.",
        diameter: "The same tool cannot use two diameters in one operational file.",
        disabled: "The selected CNC tool preset is disabled.",
        missing: "The selected CNC tool preset does not exist.",
    });

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function cutPathIsEarly(order) {
        const keys = Array.isArray(order) ? order.map(key => String(key)) : [];
        const cutAt = keys.indexOf("cut_path");
        if (cutAt < 0) return false;
        return INTERNAL_OPERATIONS.some(key => keys.indexOf(key) > cutAt);
    }

    function host(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.operational_files_html;
        const wrapper = field && (field.$wrapper || field.wrapper);
        if (!wrapper) return null;
        return wrapper[0] || wrapper;
    }

    function capture(frm) {
        const context = window.AlmdinaDocumentContext;
        return context && typeof context.capture === "function" ? context.capture(frm) : null;
    }

    function stillCurrent(frm, identity) {
        const context = window.AlmdinaDocumentContext;
        if (identity && context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, identity);
        }
        return window.cur_frm === frm;
    }

    function operationLabel(key) {
        return translate(OPERATION_LABELS[key] || key);
    }

    function statusLabel(status) {
        return translate(STATUS_LABELS[status] || status || "Not generated");
    }

    function sourceLabel(source) {
        if (source === "System") return escapeHtml(translate("System plan"));
        if (source === "Uploaded DXF") return escapeHtml(translate("Uploaded plan"));
        return escapeHtml(source || "");
    }

    function presetByName(workspace) {
        const map = new Map();
        (workspace.presets || []).forEach(preset => {
            if (preset && preset.name) map.set(preset.name, preset);
        });
        return map;
    }

    function presetLabel(workspace, name) {
        if (!name) return translate("Not specified");
        const preset = presetByName(workspace).get(name);
        if (!preset) return name;
        return `${preset.preset_name || preset.name} · ${preset.tool_number || ""}`;
    }

    function disposePresetLinks(dialog) {
        (dialog && dialog._cncPresetLinks || []).forEach(link => {
            if (link && typeof link.dispose === "function") link.dispose();
        });
        if (dialog) dialog._cncPresetLinks = [];
    }

    function mountPresetLink(host, options = {}) {
        const ui = window.AlmdinaUi;
        if (!host || !ui || typeof ui.control !== "function") return null;
        return ui.control({
            parent: host,
            fieldname: options.fieldname || "tool_preset",
            fieldtype: "Link",
            options: "CNC Tool Preset",
            value: options.value || "",
            readOnly: Boolean(options.readOnly),
            onlyInput: true,
            className: "dco-operational-preset-link",
            df: {
                get_query() {
                    return { filters: { enabled: 1 } };
                },
            },
            onChange(value) {
                if (typeof options.onChange === "function") {
                    options.onChange(String(value || ""));
                }
            },
        });
    }

    function sheetState(sheet) {
        const operations = {};
        const sources = {};
        const factoryPresets = {};
        const order = [];
        (sheet.operations || []).forEach(operation => {
            const key = String(operation.operation_key || "");
            if (!key) return;
            order.push(key);
            operations[key] = String(operation.tool_preset || "");
            sources[key] = operation.preset_source === "sheet" ? "sheet" : "factory";
            factoryPresets[key] = String(operation.factory_preset || "");
        });
        const overrides = {};
        (sheet.paths || []).forEach(path => {
            const preset = String(path.tool_preset || "");
            if (preset) overrides[path.path_key] = preset;
        });
        return {
            operations,
            sources,
            factoryPresets,
            overrides,
            order,
            confirmed: Boolean(sheet.cut_path_early_confirmed),
            expanded: {},
            customizing: {},
            selectedPathKey: "",
        };
    }

    function stateSnapshot(state) {
        return JSON.stringify({
            operations: state.order.map(key => [key, state.operations[key] || ""]),
            sources: state.order.map(key => [key, (state.sources && state.sources[key]) || "factory"]),
            overrides: Object.keys(state.overrides).sort().map(key => [key, state.overrides[key] || ""]),
            order: state.order.slice(),
            confirmed: Boolean(state.confirmed) && cutPathIsEarly(state.order),
        });
    }

    function applyLayerPreset(state, key, name) {
        state.operations[key] = String(name || "");
        state.sources[key] = "sheet";
        return state;
    }

    function restoreLayerPreset(state, key) {
        state.sources[key] = "factory";
        state.operations[key] = String((state.factoryPresets && state.factoryPresets[key]) || "");
        return state;
    }

    function restoreFactoryPresets(state) {
        (state.order || []).forEach(key => restoreLayerPreset(state, key));
        return state;
    }

    function customizePath(state, pathKey, name, layerPreset) {
        const chosen = String(name || "");
        if (chosen && chosen !== String(layerPreset || "")) state.overrides[pathKey] = chosen;
        else delete state.overrides[pathKey];
        if (state.customizing) delete state.customizing[pathKey];
        return state;
    }

    function clearPathPreset(state, pathKey) {
        delete state.overrides[pathKey];
        if (state.customizing) delete state.customizing[pathKey];
        return state;
    }

    function effectivePreset(state, path) {
        const override = state.overrides[path.path_key];
        if (override) return override;
        return state.operations[path.operation_key] || "";
    }

    function toolConflict(workspace, sheet, state) {
        const known = presetByName(workspace);
        const used = [];
        for (const path of sheet.paths || []) {
            const name = effectivePreset(state, path);
            if (!name) continue;
            const preset = known.get(name);
            if (!preset) return "missing";
            if (!preset.enabled) return "disabled";
            used.push(preset);
        }
        const numbers = new Set(used.map(preset => String(preset.tool_number || "")));
        const diameters = new Set(used.map(preset => String(preset.tool_diameter_mm)));
        if (numbers.size > 1) return "number";
        if (diameters.size > 1) return "diameter";
        return "";
    }

    function fitBoard(board) {
        const width = parseFloat(board.style.width) || 560;
        const height = parseFloat(board.style.height) || 260;
        board.style.width = "100%";
        board.style.maxWidth = "100%";
        board.style.height = "auto";
        board.style.aspectRatio = `${width} / ${height}`;
    }

    function boardsBySheet(frm, layout) {
        const boards = new Map();
        const render = window.AlmdinaCuttingPlanRender;
        if (!layout || !render || typeof render.build !== "function") return boards;
        let html = "";
        try {
            html = window.AlmdinaCuttingPlanRender.build(frm, layout) || "";
        } catch (error) {
            return boards;
        }
        const holder = document.createElement("div");
        holder.innerHTML = html;
        const cards = holder.querySelectorAll(".dco-sheet-card");
        (layout.sheets || []).forEach((sheet, index) => {
            const card = cards[index];
            const board = card && card.querySelector(".dco-sheet-board");
            if (!board) return;
            const pieces = Array.isArray(sheet.pieces) ? sheet.pieces : [];
            board.querySelectorAll(".dco-piece").forEach((node, pieceIndex) => {
                const piece = pieces[pieceIndex] || {};
                if (piece.piece_instance_id) node.dataset.pieceInstanceId = String(piece.piece_instance_id);
                if (piece.label != null && piece.label !== "") node.dataset.pieceLabel = String(piece.label);
            });
            fitBoard(board);
            boards.set(Number(sheet.sheet_no), board);
        });
        return boards;
    }

    function mountBoard(target, board) {
        target.replaceChildren();
        if (!board) {
            target.innerHTML = `<p class="dco-operational-files__note">${escapeHtml(translate("Board preview is not available."))}</p>`;
            return;
        }
        target.appendChild(board.cloneNode(true));
    }

    function downloadServerNc(frm, operationalFile, fileUrl) {
        if (!operationalFile || !frm || !frm.doc || !frm.doc.name) return;
        const params = new URLSearchParams({
            order_name: String(frm.doc.name),
            operational_file_name: String(operationalFile),
        });
        if (fileUrl) params.set("file_url", String(fileUrl));
        window.open(`/api/method/${METHOD}.download_cnc_sheet_nc?${params.toString()}`, "_blank");
    }

    function sheetCardActions(sheet) {
        const status = String(sheet.status || "");
        const notes = [];
        if (status === "Needs Regeneration") {
            notes.push(`<p class="dco-operational-files__note" role="status">${escapeHtml(translate("The stored simulation NC needs regeneration."))}</p>`);
        }
        notes.push(`<p class="dco-operational-files__note">${escapeHtml(translate("Simulation NC is for review only. It is not approved for a workshop machine."))}</p>`);
        let download = "";
        if (sheet.can_download_current && sheet.operational_file) {
            const label = sheet.download_is_previous
                ? translate("Download previous simulation NC")
                : translate("Download simulation NC");
            download = `<button type="button" class="btn btn-primary btn-sm" data-cnc-card-download="${escapeHtml(sheet.operational_file)}" data-file-url="${escapeHtml(sheet.generated_file || "")}">${escapeHtml(label)}</button>`;
        }
        return `${notes.join("")}
            <div class="dco-operational-files__actions">
                <button type="button" class="btn btn-default btn-sm dco-operational-files__open" data-sheet-no="${escapeHtml(sheet.sheet_no)}">${escapeHtml(translate("Open sheet settings"))}</button>
                ${download}
            </div>`;
    }

    function historicalHtml(rows) {
        if (!Array.isArray(rows) || !rows.length) return "";
        const body = rows.map(row => {
            const download = row.can_download && row.name
                ? `<button type="button" class="btn btn-default btn-xs" data-cnc-history-download="${escapeHtml(row.name)}" data-file-url="${escapeHtml(row.generated_file || "")}">${escapeHtml(translate("Download previous simulation NC"))}</button>`
                : "";
            return `<tr>
            <td>${escapeHtml(row.cutting_plan || "")}</td>
            <td>${escapeHtml(row.plan_revision || "")}</td>
            <td>${escapeHtml(row.sheet_no || "")}</td>
            <td>${escapeHtml(statusLabel(row.status))}</td>
            <td>${download}</td>
        </tr>`;
        }).join("");
        return `<section class="dco-operational-files__history">
            <h3>${escapeHtml(translate("Earlier operational files"))}</h3>
            <p>${escapeHtml(translate("These files stay linked to the plan revision they were prepared for."))}</p>
            <table class="dco-operational-files__table">
                <thead><tr><th>${escapeHtml(translate("Cutting plan"))}</th><th>${escapeHtml(translate("Plan revision"))}</th><th>${escapeHtml(translate("Sheet"))}</th><th>${escapeHtml(translate("Status"))}</th><th>${escapeHtml(translate("Download"))}</th></tr></thead>
                <tbody>${body}</tbody>
            </table>
        </section>`;
    }

    function paint(frm, root, workspace) {
        if (!workspace.eligible) {
            root.innerHTML = `<div class="dco-operational-files" role="status"><p>${escapeHtml(workspace.message || translate("This order has no approved cutting plan. Operational files can be prepared only from the current approved plan, whether the system calculated it or it was uploaded and then approved."))}</p></div>`;
            return;
        }
        const sheets = Array.isArray(workspace.sheets) ? workspace.sheets : [];
        const approval = workspace.machine_profile_production_approved
            ? translate("The stored machine profile is marked approved for production.")
            : translate("The stored machine profile is a sample and is not approved for production.");
        const cards = sheets.map(sheet => `<article class="dco-operational-files__sheet" data-sheet-no="${escapeHtml(sheet.sheet_no)}">
            <header class="dco-operational-files__sheet-head">
                <h3>${escapeHtml(translate("Sheet {0}", [sheet.sheet_no]))}</h3>
                <span class="dco-operational-files__status" data-status="${escapeHtml(sheet.status || "")}">${escapeHtml(statusLabel(sheet.status))}</span>
            </header>
            <div class="dco-operational-files__board" data-sheet-board="${escapeHtml(sheet.sheet_no)}"></div>
            ${sheetCardActions(sheet)}
        </article>`).join("");
        root.innerHTML = `<div class="dco-operational-files">
            <p class="dco-operational-files__banner" role="status">${escapeHtml(approval)} ${escapeHtml(translate("Simulation NC is for review only. It is not approved for a workshop machine."))}</p>
            <p class="dco-operational-files__meta">${escapeHtml(translate("Approved plan"))}: ${escapeHtml(workspace.cutting_plan || "")} · ${escapeHtml(translate("Plan revision"))} ${escapeHtml(workspace.plan_revision || "")} · ${sourceLabel(workspace.plan_source_type)}</p>
            <div class="dco-operational-files__gallery">${cards}</div>
            ${historicalHtml(workspace.historical_files)}
        </div>`;
        const boards = boardsBySheet(frm, workspace.layout);
        root.querySelectorAll("[data-sheet-board]").forEach(target => {
            mountBoard(target, boards.get(Number(target.getAttribute("data-sheet-board"))));
        });
        root.querySelectorAll(".dco-operational-files__open").forEach(button => {
            button.addEventListener("click", () => {
                const sheetNo = Number(button.getAttribute("data-sheet-no"));
                const sheet = sheets.find(item => Number(item.sheet_no) === sheetNo);
                if (sheet) openSheetDialog(frm, workspace, sheet, boards.get(sheetNo) || null);
            });
        });
        root.querySelectorAll("[data-cnc-card-download], [data-cnc-history-download]").forEach(button => {
            button.addEventListener("click", () => {
                const name = button.getAttribute("data-cnc-card-download") || button.getAttribute("data-cnc-history-download");
                downloadServerNc(frm, name, button.getAttribute("data-file-url"));
            });
        });
    }

    function selectionText(workspace, sheet, state) {
        const path = (sheet.paths || []).find(item => item.path_key === state.selectedPathKey);
        if (!path) return translate("Select a path to see its piece, layer, and preset.");
        const piece = path.piece_label ? translate("Piece {0}", [path.piece_label]) : translate("Piece number is not available");
        return `${piece} · ${operationLabel(path.operation_key)} · ${presetLabel(workspace, effectivePreset(state, path))}`;
    }

    function highlightBoard(preview, sheet, state) {
        const path = (sheet.paths || []).find(item => item.path_key === state.selectedPathKey);
        preview.querySelectorAll(".dco-piece").forEach(node => {
            const selected = Boolean(path) && node.dataset.pieceInstanceId === path.piece_instance_id;
            node.classList.toggle("is-cnc-path-selected", selected);
        });
        preview.querySelectorAll("[data-overlay-kind]").forEach(node => {
            const piece = node.closest(".dco-piece");
            const selected = Boolean(path)
                && piece
                && piece.dataset.pieceInstanceId === path.piece_instance_id
                && node.getAttribute("data-overlay-kind") === path.operation_key;
            node.classList.toggle("is-cnc-path-selected", selected);
        });
    }

    function presetFacts(workspace, name) {
        const preset = name ? presetByName(workspace).get(name) : null;
        if (!preset) return "";
        return [
            preset.tool_name || preset.preset_name || preset.name || "",
            preset.tool_number || "",
            preset.tool_diameter_mm ? translate("Diameter {0} mm", [preset.tool_diameter_mm]) : "",
            preset.final_depth_mm ? translate("Depth {0} mm", [preset.final_depth_mm]) : "",
            preset.spindle_speed_rpm ? translate("{0} RPM", [preset.spindle_speed_rpm]) : "",
            preset.feed_rate_mm_min ? translate("Feed {0} mm/min", [preset.feed_rate_mm_min]) : "",
        ].filter(Boolean).join(" · ");
    }

    function presetIssue(workspace, name) {
        if (!name) return "";
        const preset = presetByName(workspace).get(name);
        if (!preset) {
            return translate("This tool preset is no longer available. It remains visible for history and cannot be used for new machining.");
        }
        if (!preset.enabled) {
            return translate("This tool preset is disabled. It remains visible for history and cannot be used for new machining.");
        }
        return "";
    }

    function presetAvailability(workspace) {
        const presets = Array.isArray(workspace.presets) ? workspace.presets : [];
        const enabled = presets.filter(preset => preset && preset.enabled);
        if (enabled.length) return "";
        if (!presets.length) {
            return workspace.can_edit_factory_cnc
                ? translate("No CNC tool presets have been created yet.")
                : translate("No CNC tool presets have been created yet. A factory settings manager must create them.");
        }
        return translate("Every saved tool preset is disabled. Enable one before preparing new machining.");
    }

    function orderMoveIcon(name) {
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "sm");
        }
        return name === "up-line" ? "↑" : "↓";
    }

    function dialogMarkup(workspace, sheet, state) {
        const canPrepare = Boolean(workspace.can_prepare);
        const disabled = canPrepare ? "" : " disabled";
        const early = cutPathIsEarly(state.order);
        const lastIndex = Math.max(0, state.order.length - 1);
        const orderItems = state.order.map((key, index) => {
            const earlierDisabled = !canPrepare || index === 0 ? " disabled" : "";
            const laterDisabled = !canPrepare || index === lastIndex ? " disabled" : "";
            return `<li class="dco-operational-order__item" tabindex="0" draggable="${canPrepare ? "true" : "false"}" data-operation-key="${escapeHtml(key)}">
            <span class="dco-operational-order__label">${escapeHtml(operationLabel(key))}</span>
            <span class="dco-operational-order__moves">
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-move="earlier" title="${escapeHtml(translate("Move the operation earlier"))}" aria-label="${escapeHtml(translate("Move the operation earlier"))}"${earlierDisabled}>${orderMoveIcon("up-line")}</button>
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-move="later" title="${escapeHtml(translate("Move the operation later"))}" aria-label="${escapeHtml(translate("Move the operation later"))}"${laterDisabled}>${orderMoveIcon("down-line")}</button>
            </span>
        </li>`;
        }).join("");
        const layers = state.order.map(key => {
            const operation = (sheet.operations || []).find(item => item.operation_key === key) || {};
            const paths = (sheet.paths || []).filter(path => path.operation_key === key);
            const expanded = Boolean(state.expanded[key]);
            const selectedLayer = state.operations[key] || "";
            const source = (state.sources && state.sources[key]) === "sheet" ? "sheet" : "factory";
            const issue = presetIssue(workspace, selectedLayer);
            const facts = presetFacts(workspace, selectedLayer);
            const pathRows = paths.map(path => {
                const custom = Boolean(state.overrides[path.path_key]);
                const editing = canPrepare && (custom || Boolean(state.customizing && state.customizing[path.path_key]));
                const selected = effectivePreset(state, path);
                const control = editing
                    ? `<div class="dco-operational-path__preset">
                        <div data-path-preset-host="${escapeHtml(path.path_key)}"></div>
                        <button type="button" class="btn btn-default btn-xs" data-reset-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Use the layer preset"))}</button>
                       </div>`
                    : `<span class="dco-operational-path__effective">${escapeHtml(presetLabel(workspace, selected))}</span>
                        ${canPrepare ? `<button type="button" class="btn btn-default btn-xs" data-customize-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Customize this path"))}</button>` : ""}`;
                return `<div class="dco-operational-path${custom ? " is-custom" : ""}${path.path_key === state.selectedPathKey ? " is-selected" : ""}" data-path-key="${escapeHtml(path.path_key)}" data-path-operation="${escapeHtml(key)}" data-custom="${custom ? "1" : "0"}">
                    <button type="button" class="btn btn-link btn-xs dco-operational-path__pick" data-select-path="${escapeHtml(path.path_key)}">${escapeHtml(path.piece_label ? translate("Piece {0}", [path.piece_label]) : translate("Piece number is not available"))}</button>
                    <span class="dco-operational-path__badge">${escapeHtml(translate(custom ? "Custom preset" : "Uses the layer preset"))}</span>
                    ${control}
                </div>`;
            }).join("");
            const restore = canPrepare
                ? `<button type="button" class="btn btn-default btn-xs" data-restore-layer="${escapeHtml(key)}">${escapeHtml(translate("Restore the factory preset"))}</button>`
                : "";
            return `<article class="dco-operational-layer" data-layer="${escapeHtml(key)}">
                <header class="dco-operational-layer__head">
                    <div>
                        <strong>${escapeHtml(operationLabel(key))}</strong>
                        <code>${escapeHtml(operation.dxf_layer || "")}</code>
                        <span>${escapeHtml(translate("{0} paths", [paths.length || operation.path_count || 0]))}</span>
                    </div>
                    <p class="dco-operational-layer__source" data-layer-source="${escapeHtml(source)}">${escapeHtml(translate(source === "sheet" ? "Sheet choice" : "Factory default"))}</p>
                    <label class="dco-operational-layer__choice">${escapeHtml(translate("Tool preset"))}
                        <div data-operation-preset-host="${escapeHtml(key)}" data-readonly="${canPrepare ? "0" : "1"}"></div>
                    </label>
                    ${restore}
                </header>
                ${facts ? `<p class="dco-operational-layer__facts">${escapeHtml(facts)}</p>` : ""}
                ${issue ? `<p class="dco-operational-layer__issue" role="status">${escapeHtml(issue)}</p>` : ""}
                <button type="button" class="btn btn-default btn-xs" data-toggle-layer="${escapeHtml(key)}" aria-expanded="${expanded ? "true" : "false"}">${escapeHtml(translate(expanded ? "Hide paths" : "Show paths"))}</button>
                <div class="dco-operational-layer__paths"${expanded ? "" : " hidden"}>${pathRows}</div>
            </article>`;
        }).join("");
        const warning = early
            ? `<p class="dco-operational-sheet__warning" role="alert">${escapeHtml(translate("Cutting first may let the pieces move after they separate from the board."))}</p>
                <label class="dco-operational-sheet__confirm"><input type="checkbox" data-cut-confirm${state.confirmed ? " checked" : ""}${disabled}> ${escapeHtml(translate("I understand and want to keep this operation order."))}</label>`
            : "";
        const availability = presetAvailability(workspace);
        const availabilityHtml = availability
            ? `<p class="dco-operational-sheet__note" role="status">${escapeHtml(availability)}</p>`
            : "";
        const permissionNote = canPrepare
            ? ""
            : `<p class="dco-operational-sheet__note" role="status">${escapeHtml(translate("You can review these settings. Preparing operational files is not available for your current permissions."))}</p>`;
        const restoreSheet = canPrepare
            ? `<button type="button" class="btn btn-default btn-sm" data-restore-sheet>${escapeHtml(translate("Restore factory presets for this sheet"))}</button>`
            : "";
        return `<div class="dco-operational-sheet">
            <div class="dco-operational-sheet__body">
                <div class="dco-operational-sheet__preview">
                    <div data-sheet-preview></div>
                    <p class="dco-operational-sheet__selection" role="status">${escapeHtml(selectionText(workspace, sheet, state))}</p>
                    <p class="dco-operational-files__status" data-sheet-nc-status="${escapeHtml(sheet.status || "")}">${escapeHtml(statusLabel(sheet.status))}</p>
                </div>
                <div class="dco-operational-sheet__settings">
                    <section class="dco-operational-sheet__order">
                        <h4>${escapeHtml(translate("Operation order"))}</h4>
                        <ol class="dco-operational-order">${orderItems}</ol>
                        ${warning}
                    </section>
                    <section class="dco-operational-layers">
                        <div class="dco-operational-layers__tools">
                            <h4>${escapeHtml(translate("Layer presets"))}</h4>
                            ${restoreSheet}
                        </div>
                        ${permissionNote}
                        ${availabilityHtml}
                        <div class="dco-operational-layers__list">${layers}</div>
                    </section>
                </div>
            </div>
        </div>`;
    }

    function generateNcControlState({ canPrepare }) {
        if (!canPrepare) {
            return {
                disabled: true,
                reason: translate("You can review these settings. Preparing operational files is not available for your current permissions."),
            };
        }
        return {
            disabled: false,
            reason: translate("Simulation NC is for review only. It is not approved for a workshop machine."),
        };
    }

    function bindDialog(frm, dialog, workspace, sheet, state, board) {
        const body = dialogRoot(dialog);
        if (!body) return;
        const canPrepare = Boolean(workspace.can_prepare);
        const preview = body.querySelector("[data-sheet-preview]");
        mountBoard(preview, board);
        highlightBoard(preview, sheet, state);
        syncSheetFooter(dialog, workspace, sheet, state);
        preview.addEventListener("click", event => {
            const overlay = event.target.closest && event.target.closest("[data-overlay-kind]");
            const piece = event.target.closest && event.target.closest(".dco-piece");
            if (!piece || !piece.dataset.pieceInstanceId) return;
            const operationKey = overlay ? overlay.getAttribute("data-overlay-kind") : "cut_path";
            const match = (sheet.paths || []).find(path => path.piece_instance_id === piece.dataset.pieceInstanceId && path.operation_key === operationKey)
                || (sheet.paths || []).find(path => path.piece_instance_id === piece.dataset.pieceInstanceId);
            if (!match) return;
            state.selectedPathKey = match.path_key;
            state.expanded[match.operation_key] = true;
            refreshDialog(frm, dialog, workspace, sheet, state, board);
        });

        function refreshSelection() {
            const selection = body.querySelector(".dco-operational-sheet__selection");
            if (selection) selection.textContent = selectionText(workspace, sheet, state);
            highlightBoard(preview, sheet, state);
            body.querySelectorAll(".dco-operational-path").forEach(row => {
                row.classList.toggle("is-selected", row.getAttribute("data-path-key") === state.selectedPathKey);
            });
        }

        body.querySelectorAll("[data-select-path]").forEach(button => {
            button.addEventListener("click", () => {
                state.selectedPathKey = button.getAttribute("data-select-path");
                refreshSelection();
            });
        });
        body.querySelectorAll("[data-toggle-layer]").forEach(button => {
            button.addEventListener("click", () => {
                const key = button.getAttribute("data-toggle-layer");
                state.expanded[key] = !state.expanded[key];
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        });
        mountPresetControls(frm, dialog, workspace, sheet, state, board);
        if (!canPrepare) return;

        body.querySelectorAll("[data-restore-layer]").forEach(button => {
            button.addEventListener("click", () => {
                restoreLayerPreset(state, button.getAttribute("data-restore-layer"));
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        });
        const restoreSheet = body.querySelector("[data-restore-sheet]");
        if (restoreSheet) {
            restoreSheet.addEventListener("click", () => {
                restoreFactoryPresets(state);
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        }
        body.querySelectorAll("[data-customize-path]").forEach(button => {
            button.addEventListener("click", () => {
                const pathKey = button.getAttribute("data-customize-path");
                state.customizing[pathKey] = true;
                const row = button.closest(".dco-operational-path");
                const operationKey = row && row.getAttribute("data-path-operation");
                if (operationKey) state.expanded[operationKey] = true;
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        });
        body.querySelectorAll("[data-reset-path]").forEach(button => {
            button.addEventListener("click", () => {
                clearPathPreset(state, button.getAttribute("data-reset-path"));
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        });
        body.querySelectorAll("[data-move]").forEach(button => {
            button.addEventListener("click", () => {
                const item = button.closest("[data-operation-key]");
                const key = item.getAttribute("data-operation-key");
                const direction = button.getAttribute("data-move");
                moveOperation(state, key, direction === "earlier" ? -1 : 1);
                refreshDialog(frm, dialog, workspace, sheet, state, board);
                const current = dialogRoot(dialog);
                const moved = current && current.querySelector(`[data-operation-key="${key}"] [data-move="${direction}"]`);
                if (moved) moved.focus();
            });
        });
        let dragKey = "";
        body.querySelectorAll(".dco-operational-order__item").forEach(item => {
            item.addEventListener("dragstart", () => {
                dragKey = item.getAttribute("data-operation-key");
                item.classList.add("is-dragging");
            });
            item.addEventListener("dragend", () => item.classList.remove("is-dragging"));
            item.addEventListener("dragover", event => event.preventDefault());
            item.addEventListener("drop", event => {
                event.preventDefault();
                const target = item.getAttribute("data-operation-key");
                if (!dragKey || dragKey === target) return;
                const next = state.order.filter(key => key !== dragKey);
                next.splice(next.indexOf(target), 0, dragKey);
                state.order = next;
                if (!cutPathIsEarly(next)) state.confirmed = false;
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        });
        const confirm = body.querySelector("[data-cut-confirm]");
        if (confirm) {
            confirm.addEventListener("change", () => {
                state.confirmed = confirm.checked;
            });
        }
    }

    function moveOperation(state, key, direction) {
        const index = state.order.indexOf(key);
        const target = index + direction;
        if (index < 0 || target < 0 || target >= state.order.length) return;
        const next = state.order.slice();
        const [item] = next.splice(index, 1);
        next.splice(target, 0, item);
        state.order = next;
        if (!cutPathIsEarly(next)) state.confirmed = false;
    }

    function dialogRoot(dialog) {
        const wrapper = dialog && dialog.fields_dict && dialog.fields_dict.body && dialog.fields_dict.body.$wrapper;
        if (!wrapper) return null;
        return wrapper[0] || wrapper;
    }

    function syncWorkspacePresets(frm, dialog, workspace, sheet, state, board, selectedName, applySelected) {
        const request = (dialog._cncPresetRequest || 0) + 1;
        dialog._cncPresetRequest = request;
        frappe.call({
            method: `${METHOD}.get_cnc_operational_workspace`,
            args: { order_name: frm.doc.name },
            callback(response) {
                if (dialog._cncPresetRequest !== request) return;
                const message = (response && response.message) || {};
                workspace.presets = message.presets || workspace.presets;
                workspace.can_edit_factory_cnc = message.can_edit_factory_cnc;
                const saved = (message.sheets || []).find(item => Number(item.sheet_no) === Number(sheet.sheet_no));
                if (saved) {
                    const next = sheetState(saved);
                    state.order.forEach(key => {
                        const previousFactory = state.factoryPresets[key] || "";
                        state.factoryPresets[key] = next.factoryPresets[key] || "";
                        if (state.sources[key] !== "sheet" && (state.operations[key] || "") === previousFactory) {
                            state.operations[key] = state.factoryPresets[key];
                        }
                    });
                }
                if (typeof applySelected === "function") applySelected(selectedName || "");
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            },
            error() {
                if (dialog._cncPresetRequest !== request) return;
                if (typeof applySelected === "function") applySelected(selectedName || "");
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            },
        });
    }

    function onPresetChosen(frm, dialog, workspace, sheet, state, board, applySelected, name) {
        const selected = String(name || "");
        if (selected && !presetByName(workspace).has(selected)) {
            syncWorkspacePresets(frm, dialog, workspace, sheet, state, board, selected, applySelected);
            return;
        }
        applySelected(selected);
        refreshDialog(frm, dialog, workspace, sheet, state, board);
    }

    function mountPresetControls(frm, dialog, workspace, sheet, state, board) {
        const body = dialogRoot(dialog);
        if (!body) return;
        disposePresetLinks(dialog);
        const links = [];
        const canPrepare = Boolean(workspace.can_prepare);
        body.querySelectorAll("[data-operation-preset-host]").forEach(host => {
            const key = host.getAttribute("data-operation-preset-host");
            const readOnly = !canPrepare || host.getAttribute("data-readonly") === "1";
            const link = mountPresetLink(host, {
                fieldname: `operation_preset_${key}`,
                value: state.operations[key] || "",
                readOnly,
                onChange(value) {
                    onPresetChosen(
                        frm,
                        dialog,
                        workspace,
                        sheet,
                        state,
                        board,
                        next => applyLayerPreset(state, key, next),
                        value
                    );
                },
            });
            if (link) links.push(link);
        });
        body.querySelectorAll("[data-path-preset-host]").forEach(host => {
            const pathKey = host.getAttribute("data-path-preset-host");
            const row = host.closest(".dco-operational-path");
            const operationKey = row && row.getAttribute("data-path-operation");
            const link = mountPresetLink(host, {
                fieldname: `path_preset_${pathKey}`,
                value: effectivePreset(state, { path_key: pathKey, operation_key: operationKey }),
                readOnly: !canPrepare,
                onChange(value) {
                    onPresetChosen(
                        frm,
                        dialog,
                        workspace,
                        sheet,
                        state,
                        board,
                        next => customizePath(state, pathKey, next, state.operations[operationKey] || ""),
                        value
                    );
                },
            });
            if (link) links.push(link);
        });
        dialog._cncPresetLinks = links;
    }

    function sheetGenerateArgs(frm, workspace, sheet, state) {
        const overrides = {};
        Object.keys(state.overrides || {}).forEach(key => {
            if (state.overrides[key]) overrides[key] = state.overrides[key];
        });
        return {
            order_name: frm.doc.name,
            sheet_no: sheet.sheet_no,
            operation_presets: state.operations,
            path_overrides: overrides,
            operation_order: state.order,
            cut_path_early_confirmed: state.confirmed ? 1 : 0,
            viewed_plan_token: `${workspace.cutting_plan}::${workspace.plan_revision}`,
            operation_sources: state.sources || {},
        };
    }

    function issueAction(code) {
        const actions = {
            tool_diameter_kerf_mismatch: translate("Choose a tool preset whose diameter matches the approved kerf."),
            finished_geometry_missing: translate("Recalculate or re-approve the cutting plan so finished geometry is available."),
            geometry_invalid: translate("Fix the path geometry in the approved plan, then open this sheet again."),
            preset_disabled: translate("Enable the tool preset in factory settings, or choose another enabled preset."),
            preset_not_found: translate("Choose an available CNC tool preset."),
            tool_identity_conflict: translate("Use one physical tool number for every operation on this sheet."),
            tool_diameter_conflict: translate("Use one tool diameter for every operation on this sheet."),
            geometry_not_ready: translate("Resolve the listed geometry problems, then generate the NC file again."),
            mill_parameters_missing: translate("Complete the milling parameters on the approved plan, then try again."),
            liner_narrower_than_cutter: translate("Choose a narrower tool, or widen the milling band on the approved plan."),
        };
        return actions[code] || translate("Correct the listed issue, then generate the NC file again.");
    }

    function collectProgramIssues(program, sheetNo) {
        const drawing = program || {};
        const unique = new Map();
        function remember(entry) {
            const code = String(entry.code || "").trim();
            if (!code) return;
            const pathKey = String(entry.path_key || "").trim();
            const pieceLabel = String(entry.piece_label || "").trim();
            const key = `${code}::${pathKey || pieceLabel || entry.layer || ""}`;
            if (unique.has(key)) return;
            unique.set(key, {
                code: (/^[A-Z][A-Z0-9_]{0,79}$/.test(code)
                    ? code
                    : `CNC_${String(code).toUpperCase().replace(/[^A-Z0-9]+/g, "_")}`).slice(0, 80),
                rawCode: code,
                problem: entry.message || code,
                target: [
                    sheetNo ? translate("Sheet {0}", [sheetNo]) : "",
                    entry.layer || "",
                    pieceLabel ? translate("Piece {0}", [pieceLabel]) : "",
                ].filter(Boolean).join(" — "),
                action: issueAction(code),
                path_key: pathKey,
                piece_label: pieceLabel,
            });
        }
        (Array.isArray(drawing.issues) ? drawing.issues : []).forEach(issue => {
            if (!issue) return;
            remember({
                code: issue.code || "",
                message: issue.message || issue.code || "",
                layer: issue.operation_key ? operationLabel(issue.operation_key) : translate("Sheet"),
                piece_label: issue.piece_label || "",
                path_key: issue.path_key || "",
            });
        });
        (Array.isArray(drawing.operations) ? drawing.operations : []).forEach(operation => {
            (operation.toolpaths || []).forEach(path => {
                const codes = Array.isArray(path.issues) ? path.issues : [];
                const messages = Array.isArray(path.issue_messages) && path.issue_messages.length
                    ? path.issue_messages
                    : codes;
                codes.forEach((code, index) => {
                    remember({
                        code,
                        message: messages[index] || code,
                        layer: operationLabel(path.operation_key || operation.operation_key),
                        piece_label: path.piece_label || "",
                        path_key: path.path_key || "",
                    });
                });
            });
        });
        const grouped = new Map();
        unique.forEach(item => {
            const bucket = grouped.get(item.rawCode) || [];
            bucket.push(item);
            grouped.set(item.rawCode, bucket);
        });
        const issues = [];
        grouped.forEach((items, rawCode) => {
            const first = items[0];
            const affected = items
                .map(item => [item.target, item.path_key].filter(Boolean).join(" · "))
                .filter(Boolean);
            issues.push({
                code: first.code,
                problem: items.length === 1
                    ? first.problem
                    : translate("{0} problems: {1}", [items.length, first.problem]),
                target: first.target,
                action: first.action,
                details: affected.length > 1 ? affected : [],
            });
        });
        return {
            uniqueCount: unique.size,
            pathCount: unique.size,
            issues,
        };
    }

    function showGenerationIssueDialog(error, program, sheetNo) {
        const ui = window.AlmdinaUi;
        if (ui && typeof ui.errorDialog === "function" && error) {
            const shown = ui.errorDialog(error, {
                title: translate("NC generation could not be completed"),
                fallback: translate("The NC file could not be prepared."),
                outcomeMessages: {
                    rejected: translate("No NC file was created."),
                },
            });
            const normalized = window.AlmdinaFrontend
                && typeof window.AlmdinaFrontend.normalizeError === "function"
                ? window.AlmdinaFrontend.normalizeError(error)
                : null;
            if (shown && normalized && normalized.issues && normalized.issues.length) return shown;
        }
        const collected = collectProgramIssues(program, sheetNo);
        if (!collected.issues.length && error && ui && typeof ui.errorDialog === "function") {
            return ui.errorDialog(error, {
                title: translate("NC generation could not be completed"),
                fallback: translate("The NC file could not be prepared."),
            });
        }
        if (!window.frappe || !frappe.ui || !frappe.ui.Dialog) return null;
        const cards = collected.issues.map(item => {
            const details = item.details.length
                ? `<details><summary>${escapeHtml(translate("Affected paths"))}</summary><ul>${item.details.map(line => `<li>${escapeHtml(line)}</li>`).join("")}</ul></details>`
                : "";
            return `<section class="alm-error-card">
                <p><strong>${escapeHtml(translate("What is the problem?"))}</strong> ${escapeHtml(item.problem)}</p>
                ${item.target ? `<p><strong>${escapeHtml(translate("Where is it?"))}</strong> ${escapeHtml(item.target)}</p>` : ""}
                ${item.action ? `<p><strong>${escapeHtml(translate("What should I do?"))}</strong> ${escapeHtml(item.action)}</p>` : ""}
                ${details}
                <small>${escapeHtml(item.code)}</small>
            </section>`;
        }).join("");
        const countNote = collected.uniqueCount
            ? `<p>${escapeHtml(translate("{0} unique validation problems must be fixed before NC generation.", [collected.uniqueCount]))}</p>`
            : "";
        const dialog = new frappe.ui.Dialog({
            title: translate("NC generation could not be completed"),
            size: "large",
            secondary_action_label: translate("Close"),
            secondary_action() { dialog.hide(); },
        });
        dialog.$body.html(`<div class="almdina-ui"><div class="alm-error-summary" role="alert">${countNote}${cards || `<p>${escapeHtml(translate("The NC file could not be prepared."))}</p>`}<p>${escapeHtml(translate("No NC file was created."))}</p></div></div>`);
        dialog.show();
        return dialog;
    }

    function syncSheetFooter(dialog, workspace, sheet, state) {
        if (!dialog || !dialog.$wrapper) return;
        const actions = dialog.$wrapper.find(".modal-footer .standard-actions");
        if (!actions.length) return;
        actions.find("[data-cnc-footer-action]").remove();
        const canPrepare = Boolean(workspace && workspace.can_prepare);
        const control = generateNcControlState({ canPrepare });
        const generate = $(`<button type="button" class="btn btn-default btn-sm" data-cnc-footer-action="generate" data-cnc-generate-nc title="${escapeHtml(control.reason)}"></button>`);
        generate.text(translate("Generate NC file"));
        generate.prop("disabled", Boolean(control.disabled));
        if (sheet && sheet.can_download_current && sheet.operational_file) {
            const download = $(`<button type="button" class="btn btn-default btn-sm" data-cnc-footer-action="download" data-cnc-dialog-download="${escapeHtml(sheet.operational_file)}" data-file-url="${escapeHtml(sheet.generated_file || "")}"></button>`);
            download.text(translate(
                sheet.download_is_previous ? "Download previous simulation NC" : "Download NC file"
            ));
            actions.prepend(download);
        }
        actions.prepend(generate);
        const live = dialog._almdinaSheet;
        if (!live) return;
        bindGenerateNc(dialog, dialog.$wrapper[0], {
            canPrepare,
            args: sheetGenerateArgs(live.frm, live.workspace || workspace, live.sheet || sheet, live.state || state),
            sheetNo: (live.sheet || sheet).sheet_no,
            frm: live.frm,
            state: live.state || state,
            sheet: live.sheet || sheet,
            workspace: live.workspace || workspace,
        });
    }

    function refreshDialog(frm, dialog, workspace, sheet, state, board) {
        const wrapper = dialogRoot(dialog);
        if (!wrapper) return;
        disposePresetLinks(dialog);
        dialog._almdinaSheet = { frm, workspace, sheet, state, board };
        wrapper.innerHTML = dialogMarkup(workspace, sheet, state);
        bindDialog(frm, dialog, workspace, sheet, state, board);
    }

    function openSheetDialog(frm, workspace, sheet, board) {
        const state = sheetState(sheet);
        const baseline = stateSnapshot(state);
        let allowHide = false;
        const dialog = new frappe.ui.Dialog({
            title: translate("Sheet {0}", [sheet.sheet_no]),
            size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "body" }],
            primary_action_label: translate("Save sheet settings"),
            primary_action() {
                saveDialog(frm, dialog, workspace, sheet, state, baselineHolder);
            },
        });
        const baselineHolder = { value: baseline, state };
        const originalHide = dialog.hide.bind(dialog);
        dialog.hide = () => {
            if (allowHide || stateSnapshot(state) === baselineHolder.value) {
                allowHide = false;
                originalHide();
                return;
            }
            frappe.confirm(translate("Discard the unsaved changes?"), () => {
                allowHide = true;
                originalHide();
            });
        };
        dialog.show();
        dialog.$wrapper.addClass("dco-operational-sheet-dialog");
        const locale = window.AlmdinaLocale;
        const dir = locale && typeof locale.direction === "function"
            ? locale.direction()
            : (document.documentElement && document.documentElement.getAttribute("dir")) || "rtl";
        dialog.$wrapper.attr("dir", dir === "ltr" ? "ltr" : "rtl");
        dialog.$wrapper.on("keydown", event => {
            const live = dialog._almdinaSheet;
            const target = event.target;
            if (!live || !live.workspace.can_prepare) return;
            if (target && target.matches && target.matches("select, input, textarea")) return;
            if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
            const item = target && target.closest && target.closest("[data-operation-key]");
            if (!item) return;
            event.preventDefault();
            const key = item.getAttribute("data-operation-key");
            moveOperation(live.state, key, event.key === "ArrowUp" ? -1 : 1);
            refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
            const row = dialogRoot(dialog) && dialogRoot(dialog).querySelector(`[data-operation-key="${key}"]`);
            if (row) row.focus();
        });
        if (!workspace.can_prepare) dialog.get_primary_btn().hide();
        refreshDialog(frm, dialog, workspace, sheet, state, board);
    }

    function saveDialog(frm, dialog, workspace, sheet, state, baselineHolder) {
        if (cutPathIsEarly(state.order) && !state.confirmed) {
            frappe.msgprint(translate("Cutting first may let the pieces move after they separate from the board."));
            return;
        }
        const conflict = toolConflict(workspace, sheet, state);
        if (conflict) {
            frappe.msgprint(translate(CONFLICT_MESSAGES[conflict]));
            return;
        }
        const requestId = (frm.__almdinaOperationalFilesRequest || 0) + 1;
        frm.__almdinaOperationalFilesRequest = requestId;
        const identity = capture(frm);
        const button = dialog.get_primary_btn();
        button.prop("disabled", true);
        const overrides = {};
        Object.keys(state.overrides).forEach(key => {
            if (state.overrides[key]) overrides[key] = state.overrides[key];
        });
        frappe.call({
            method: `${METHOD}.save_cnc_operational_sheet`,
            args: {
                order_name: frm.doc.name,
                sheet_no: sheet.sheet_no,
                operation_presets: state.operations,
                operation_sources: state.sources,
                path_overrides: overrides,
                operation_order: state.order,
                cut_path_early_confirmed: state.confirmed ? 1 : 0,
                viewed_plan_token: `${workspace.cutting_plan}::${workspace.plan_revision}`,
            },
            callback(response) {
                if (frm.__almdinaOperationalFilesRequest !== requestId) return;
                if (!stillCurrent(frm, identity)) return;
                const message = (response && response.message) || {};
                const root = host(frm);
                if (root) paint(frm, root, message);
                const saved = (message.sheets || []).find(item => Number(item.sheet_no) === Number(sheet.sheet_no));
                if (saved) {
                    const next = sheetState(saved);
                    state.operations = next.operations;
                    state.sources = next.sources;
                    state.factoryPresets = next.factoryPresets;
                    state.overrides = next.overrides;
                    state.order = next.order;
                    state.confirmed = next.confirmed;
                    baselineHolder.value = stateSnapshot(state);
                    const boards = boardsBySheet(frm, message.layout);
                    refreshDialog(frm, dialog, message, saved, state, boards.get(Number(saved.sheet_no)) || null);
                }
                button.prop("disabled", false);
                if (window.frappe && frappe.show_alert) {
                    frappe.show_alert({ message: translate("Operational files saved."), indicator: "green" });
                }
            },
            error() {
                if (frm.__almdinaOperationalFilesRequest !== requestId) return;
                button.prop("disabled", false);
            },
        });
    }

    function render(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const root = host(frm);
        if (!root) return;
        if (typeof frm.is_new === "function" && frm.is_new()) {
            root.innerHTML = `<div class="dco-operational-files" role="status"><p>${escapeHtml(translate("Save the order before preparing operational files."))}</p></div>`;
            return;
        }
        const requestId = (frm.__almdinaOperationalFilesRequest || 0) + 1;
        frm.__almdinaOperationalFilesRequest = requestId;
        const identity = capture(frm);
        root.innerHTML = `<div class="dco-operational-files" role="status"><p>${escapeHtml(translate("Loading operational files..."))}</p></div>`;
        frappe.call({
            method: `${METHOD}.get_cnc_operational_workspace`,
            args: { order_name: frm.doc.name },
            callback(response) {
                if (frm.__almdinaOperationalFilesRequest !== requestId) return;
                if (!stillCurrent(frm, identity)) return;
                const current = host(frm);
                if (!current) return;
                paint(frm, current, (response && response.message) || {});
            },
            error() {
                if (frm.__almdinaOperationalFilesRequest !== requestId) return;
                const current = host(frm);
                if (!current) return;
                current.innerHTML = `<div class="dco-operational-files" role="alert"><p>${escapeHtml(translate("Operational files could not be loaded."))}</p></div>`;
            },
        });
    }

    const PROGRAM_COLORS = Object.freeze({
        liner: "#1d4e89",
        recessed_handle_cutout: "#c45c12",
        back_groove: "#5c4d2e",
        cut_path: "#a61b1b",
    });
    const DIRECTION_LABELS = Object.freeze({
        ccw: "Counterclockwise",
        cw: "Clockwise",
        start_to_end: "Start to end",
    });

    function formatPoint(point) {
        if (!Array.isArray(point) || point.length < 2) return "";
        return `${Number(point[0]).toFixed(1)}, ${Number(point[1]).toFixed(1)}`;
    }

    function programMarkup(program) {
        const drawing = program || {};
        const width = Number(drawing.sheet_width_mm);
        const length = Number(drawing.sheet_length_mm);
        const operations = Array.isArray(drawing.operations) ? drawing.operations : [];
        const boardIssues = Array.isArray(drawing.issues) ? drawing.issues : [];
        const steps = [];
        const paths = [];
        let execution = 0;
        operations.forEach(operation => {
            (operation.toolpaths || []).forEach(path => {
                execution += 1;
                steps.push({ execution, operation, path });
                if (Array.isArray(path.points) && path.points.length >= 2) paths.push({ execution, path });
            });
        });
        const geometryReady = Boolean(drawing.geometry_ready || drawing.ready);
        const machineReady = Boolean(drawing.machine_ready);
        const readiness = [
            geometryReady ? translate("Geometry ready") : translate("Geometry not ready"),
            machineReady ? translate("Machine ready") : translate("Machine not ready"),
            drawing.nc_export_ready ? translate("Simulation NC export ready") : translate("Simulation NC export not ready"),
        ].join(" · ");
        const uniqueIssues = new Map();
        function rememberIssue(entry) {
            const code = String(entry.code || entry.message || "").trim();
            const pathKey = String(entry.path_key || "").trim();
            const pieceLabel = String(entry.piece_label || "").trim();
            const key = `${code}::${pathKey || pieceLabel || entry.layer || ""}`;
            if (!code || uniqueIssues.has(key)) return;
            uniqueIssues.set(key, {
                code,
                message: entry.message || code,
                layer: entry.layer || "",
                piece_label: pieceLabel,
                path_key: pathKey,
            });
        }
        steps.forEach(step => {
            const path = step.path || {};
            const codes = Array.isArray(path.issues) ? path.issues : [];
            const messages = Array.isArray(path.issue_messages) && path.issue_messages.length
                ? path.issue_messages
                : codes;
            codes.forEach((code, index) => {
                rememberIssue({
                    code,
                    message: messages[index] || code,
                    layer: operationLabel(path.operation_key),
                    piece_label: path.piece_label || "",
                    path_key: path.path_key || "",
                });
            });
        });
        boardIssues.forEach(issue => {
            if (!issue) return;
            rememberIssue({
                code: issue.code || issue.message || "",
                message: issue.message || issue.code || "",
                layer: issue.operation_key ? operationLabel(issue.operation_key) : translate("Sheet"),
                piece_label: issue.piece_label || "",
                path_key: issue.path_key || "",
            });
        });
        const grouped = new Map();
        uniqueIssues.forEach(item => {
            const bucket = grouped.get(item.code) || [];
            bucket.push(item);
            grouped.set(item.code, bucket);
        });
        const uniqueCount = uniqueIssues.size;
        const groupHtml = Array.from(grouped.entries()).map(([code, items]) => {
            let title = translate("{0} geometry problems block simulation NC generation.", [items.length]);
            if (code === "finished_geometry_missing") {
                title = translate(
                    "Cut paths for {0} pieces could not be prepared because finished geometry is missing from the approved plan.",
                    [items.length]
                );
            } else if (items.length === 1) {
                title = items[0].message;
            } else {
                title = translate("{0} problems: {1}", [items.length, items[0].message || code]);
            }
            const details = items.map(item => {
                const piece = item.piece_label
                    ? translate("Piece {0}", [item.piece_label])
                    : "";
                const tech = item.path_key
                    ? ` title="${escapeHtml(item.path_key)}"`
                    : "";
                return `<li${tech}>${escapeHtml(item.layer || "")}${piece ? ` · ${escapeHtml(piece)}` : ""} — ${escapeHtml(item.message)}</li>`;
            }).join("");
            return `<details class="dco-cnc-program__issue-group">
                <summary class="dco-cnc-program__error">${escapeHtml(title)}</summary>
                <ul>${details}</ul>
            </details>`;
        }).join("");
        const blockingHtml = !geometryReady && uniqueCount
            ? `<div class="dco-cnc-program__blockers" role="status">
                <p class="dco-cnc-program__error">${escapeHtml(translate("{0} geometry problems block simulation NC generation.", [uniqueCount]))}</p>
                ${groupHtml}
               </div>`
            : (!geometryReady
                ? `<p class="dco-cnc-program__error" role="status">${escapeHtml(translate("Geometry is not ready, so simulation NC generation stays disabled."))}</p>`
                : "");
        const rows = steps.map(step => {
            const path = step.path;
            const preset = path.preset || {};
            const depth = preset.final_depth_mm;
            const passes = (path.motions || []).filter(motion => motion.kind === "plunge").length;
            const codes = Array.isArray(path.issues) ? path.issues : [];
            const messages = Array.isArray(path.issue_messages) && path.issue_messages.length
                ? path.issue_messages
                : codes;
            const details = [
                operationLabel(path.operation_key),
                path.piece_label ? translate("Piece {0}", [path.piece_label]) : translate("Piece number is not available"),
                path.preset_name || translate("Not specified"),
                preset.tool_diameter_mm ? translate("Tool diameter {0} mm", [preset.tool_diameter_mm]) : "",
                depth ? translate("Depth {0} mm", [depth]) : "",
                preset.spindle_speed_rpm ? translate("{0} RPM", [preset.spindle_speed_rpm]) : "",
                preset.feed_rate_mm_min ? translate("Feed {0} mm/min", [preset.feed_rate_mm_min]) : "",
                preset.plunge_rate_mm_min ? translate("Plunge {0} mm/min", [preset.plunge_rate_mm_min]) : "",
                passes > 1 ? translate("{0} passes", [passes]) : "",
                DIRECTION_LABELS[path.direction] ? translate(DIRECTION_LABELS[path.direction]) : "",
                path.start ? `${translate("Path start")} ${formatPoint(path.start)}` : "",
                path.end && !path.closed ? `${translate("Path end")} ${formatPoint(path.end)}` : "",
            ].filter(Boolean).join(" · ");
            const errors = messages
                .map((message, index) => ({ message, code: codes[index] || message }))
                .filter(item => item.code !== "finished_geometry_missing")
                .map(item => `<p class="dco-cnc-program__error">${escapeHtml(item.message)}</p>`)
                .join("");
            return `<li><span>${escapeHtml(step.execution)}</span> ${escapeHtml(details)}${errors}</li>`;
        }).join("");
        const list = `<div class="dco-cnc-program">
            <h4>${escapeHtml(translate("Machining preview"))}</h4>
            <p class="dco-cnc-program__note">${escapeHtml(readiness)}</p>
            ${blockingHtml}
            ${rows ? `<ol class="dco-cnc-program__steps">${rows}</ol>` : `<p class="dco-cnc-program__note">${escapeHtml(translate("The machining preview could not be prepared."))}</p>`}
            <p class="dco-cnc-program__note">${escapeHtml(translate("This preview uses positive depths in millimetres. The machine origin is not established, so it is not a machine file."))}</p>
        </div>`;
        let svg = "";
        if (width > 0 && length > 0 && paths.length) {
            const strokes = paths.map((item, index) => {
                const color = PROGRAM_COLORS[item.path.operation_key] || "#333";
                const points = item.path.points.map(point => `${Number(point[0])},${Number(point[1])}`).join(" ");
                const start = item.path.points[0];
                return `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke" marker-end="url(#cnc-arrow-${index})"/>
                    <circle cx="${Number(start[0])}" cy="${Number(start[1])}" r="2.2" fill="${color}"/>
                    ${item.path.closed || !item.path.end ? "" : `<rect x="${Number(item.path.end[0]) - 1.6}" y="${Number(item.path.end[1]) - 1.6}" width="3.2" height="3.2" fill="${color}"/>`}`;
            }).join("");
            const labels = paths.map(item => {
                const start = item.path.points[0];
                return `<text class="dco-cnc-program__label" x="${Number(start[0])}" y="${length - Number(start[1])}">${item.execution}</text>`;
            }).join("");
            const markers = paths.map((item, index) => {
                const color = PROGRAM_COLORS[item.path.operation_key] || "#333";
                return `<marker id="cnc-arrow-${index}" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="${color}"/></marker>`;
            }).join("");
            svg = `<svg class="dco-cnc-program__drawing" viewBox="0 0 ${width} ${length}" preserveAspectRatio="none" aria-hidden="true"><defs>${markers}</defs><g transform="translate(0,${length}) scale(1,-1)">${strokes}</g>${labels}</svg>`;
        }
        return { list, drawing: svg };
    }

    function paintNcPanel(host, packagePayload, context) {
        if (!host) return;
        const payload = packagePayload || {};
        const verification = payload.verification || {};
        const summary = [
            translate("Simulation NC"),
            payload.tool_number || "",
            payload.spindle_speed_rpm ? translate("{0} RPM", [payload.spindle_speed_rpm]) : "",
            payload.path_count ? translate("{0} paths", [payload.path_count]) : "",
            payload.pass_count ? translate("{0} depth passes", [payload.pass_count]) : "",
            verification.ok ? translate("NC matches the intermediate program") : translate("NC verification failed"),
            payload.status ? statusLabel(payload.status) : "",
        ].filter(Boolean).join(" · ");
        const warnings = (payload.warnings || []).map(code => `<p class="dco-cnc-program__error">${escapeHtml(translate(String(code)))}</p>`).join("");
        const canDownload = Boolean(payload.operational_file && payload.file_url);
        host.innerHTML = `
            <p class="dco-cnc-program__note">${escapeHtml(summary)}</p>
            ${warnings}
            <p class="dco-cnc-program__note">${escapeHtml(payload.message || translate("Simulation NC prepared. This file is not approved for a workshop machine."))}</p>
            ${payload.text ? `<pre class="dco-cnc-program__nc" tabindex="0">${escapeHtml(payload.text || "")}</pre>` : ""}
            ${canDownload ? `<button type="button" class="btn btn-primary btn-sm" data-cnc-download-nc data-operational-file="${escapeHtml(payload.operational_file)}" data-file-url="${escapeHtml(payload.file_url)}">${escapeHtml(translate("Download simulation NC"))}</button>` : ""}
        `;
        const download = host.querySelector("[data-cnc-download-nc]");
        if (download && context && context.frm) {
            download.addEventListener("click", () => {
                downloadServerNc(
                    context.frm,
                    download.getAttribute("data-operational-file"),
                    download.getAttribute("data-file-url")
                );
            });
        }
    }

    function applyGenerateNcControl(root, state) {
        const button = root && typeof root.querySelector === "function"
            ? root.querySelector("[data-cnc-generate-nc]")
            : null;
        if (!button) return null;
        button.disabled = Boolean(state.disabled);
        button.setAttribute("title", state.reason || "");
        return button;
    }

    function loadProgramForIssues(args) {
        return new Promise(resolve => {
            if (!window.frappe || typeof frappe.call !== "function") {
                resolve(null);
                return;
            }
            frappe.call({
                method: `${METHOD}.get_cnc_sheet_program`,
                args: {
                    order_name: args.order_name,
                    sheet_no: args.sheet_no,
                    operation_presets: args.operation_presets,
                    path_overrides: args.path_overrides,
                    operation_order: args.operation_order,
                    cut_path_early_confirmed: args.cut_path_early_confirmed,
                    viewed_plan_token: args.viewed_plan_token,
                },
                callback(response) {
                    resolve((response && response.message) || null);
                },
                error() {
                    resolve(null);
                },
            });
        });
    }

    function bindGenerateNc(dialog, root, context) {
        if (!root || !context) return;
        const canPrepare = Boolean(context.canPrepare);
        const control = generateNcControlState({ canPrepare });
        const generate = applyGenerateNcControl(root, control);
        root.querySelectorAll("[data-cnc-dialog-download]").forEach(button => {
            button.onclick = () => downloadServerNc(
                context.frm,
                button.getAttribute("data-cnc-dialog-download"),
                button.getAttribute("data-file-url")
            );
        });
        if (!generate) return;
        generate.onclick = null;
        if (!canPrepare) return;
        generate.onclick = () => {
            if (!window.frappe || typeof frappe.call !== "function") return;
            if (cutPathIsEarly(context.state.order) && !context.state.confirmed) {
                frappe.msgprint(translate("Cutting first may let the pieces move after they separate from the board."));
                return;
            }
            const conflict = toolConflict(context.workspace, context.sheet, context.state);
            if (conflict) {
                frappe.msgprint(translate(CONFLICT_MESSAGES[conflict]));
                return;
            }
            const request = (dialog._cncNcRequest || 0) + 1;
            dialog._cncNcRequest = request;
            applyGenerateNcControl(root, {
                disabled: true,
                reason: translate("Preparing the simulation NC file..."),
            });
            const args = sheetGenerateArgs(
                context.frm,
                context.workspace,
                context.sheet,
                context.state
            );
            frappe.call({
                method: `${METHOD}.generate_cnc_sheet_nc`,
                args,
                callback(response) {
                    if (dialog._cncNcRequest !== request) return;
                    applyGenerateNcControl(root, generateNcControlState({ canPrepare: true }));
                    const payload = (response && response.message) || {};
                    if (payload.workspace && context.frm) {
                        const hostEl = host(context.frm);
                        if (hostEl) paint(context.frm, hostEl, payload.workspace);
                        const saved = (payload.workspace.sheets || []).find(
                            item => Number(item.sheet_no) === Number(context.sheetNo)
                        );
                        const live = dialog._almdinaSheet;
                        if (saved && live) {
                            live.workspace = payload.workspace;
                            live.sheet = saved;
                            const status = dialogRoot(dialog) && dialogRoot(dialog).querySelector("[data-sheet-nc-status]");
                            if (status) {
                                status.setAttribute("data-sheet-nc-status", saved.status || "");
                                status.textContent = statusLabel(saved.status);
                            }
                            syncSheetFooter(dialog, live.workspace, saved, live.state);
                        }
                    }
                    if (window.frappe && frappe.show_alert) {
                        frappe.show_alert({
                            message: translate("Simulation NC prepared. This file is not approved for a workshop machine."),
                            indicator: "green",
                        }, 7);
                    }
                    if (payload.operational_file && payload.file_url) {
                        frappe.confirm(
                            translate("Download the simulation NC file now? It is not approved for a workshop machine."),
                            () => downloadServerNc(context.frm, payload.operational_file, payload.file_url)
                        );
                    }
                },
                error(err) {
                    if (dialog._cncNcRequest !== request) return;
                    applyGenerateNcControl(root, generateNcControlState({ canPrepare: true }));
                    loadProgramForIssues(args).then(program => {
                        if (dialog._cncNcRequest !== request) return;
                        showGenerationIssueDialog(err, program, context.sheetNo);
                    });
                },
            });
        };
    }

    window.AlmdinaOperationalFilesUX = Object.freeze({
        render,
        cutPathIsEarly,
        effectivePreset,
        toolConflict,
        programMarkup,
        dialogMarkup,
        generateNcControlState,
        paintNcPanel,
        collectProgramIssues,
        sheetCardActions,
        sheetState,
        applyLayerPreset,
        restoreLayerPreset,
        restoreFactoryPresets,
        customizePath,
        clearPathPreset,
    });
})();
