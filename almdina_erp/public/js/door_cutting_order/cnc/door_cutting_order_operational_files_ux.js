(() => {
    "use strict";

    if (window.AlmdinaOperationalFilesUX) return;

    const METHOD = "almdina_erp.almdina_erp.services.cnc_operational_file_service";
    const SHEET_PAGE_ROUTE = "cnc-sheet-settings";
    const SHEET_PREVIEW_MAX_WIDTH_PX = 260;
    const SHEET_PAGE_PREVIEW_MIN_WIDTH_PX = 520;
    const CUT_PREVIEW_ZOOM = Object.freeze({
        MIN: 0.4,
        INITIAL: 0.55,
        MAX: 2.5,
        STEP: 0.15,
    });
    let cutPreviewScopeSeq = 0;

    function nextCutPreviewScope() {
        cutPreviewScopeSeq += 1;
        return `cnc-cut-${Date.now().toString(36)}-${cutPreviewScopeSeq}`;
    }

    function sheetSettingsUrl(orderName, sheetNo) {
        const order = String(orderName || "").trim();
        const sheet = String(sheetNo || "").trim();
        const parts = [SHEET_PAGE_ROUTE, order, sheet];
        if (window.frappe && frappe.router && typeof frappe.router.make_url === "function") {
            return frappe.router.make_url(parts);
        }
        return `/desk/${SHEET_PAGE_ROUTE}/${encodeURIComponent(order)}/${encodeURIComponent(sheet)}`;
    }

    function openSheetSettingsTab(orderName, sheetNo) {
        const url = sheetSettingsUrl(orderName, sheetNo);
        const popup = window.open(url, "_blank");
        if (!popup && window.frappe && typeof frappe.set_route === "function") {
            frappe.set_route(SHEET_PAGE_ROUTE, String(orderName || ""), String(sheetNo || ""));
        }
        return url;
    }
    const OPERATION_LABELS = Object.freeze({
        cut_path: "Cut between pieces",
        sheet_perimeter: "Sheet Perimeter Cut",
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

    const SHEET_PERIMETER_PATH_KEY = "cut_path:sheet_perimeter";
    const SHEET_PERIMETER_OPERATION_KEY = "sheet_perimeter";
    const CUT_PATH_INTERNAL_SEQUENCE_KEY = "cut_path:internals";

    function normalizePerimeterJoinMode(value) {
        return String(value || "").trim().toLowerCase() === "connected" ? "connected" : "separate";
    }

    function deriveCutPathSequenceFromOrder(order) {
        const keys = Array.isArray(order) ? order.map(key => String(key)) : [];
        const peri = keys.indexOf(SHEET_PERIMETER_OPERATION_KEY);
        const cut = keys.indexOf("cut_path");
        if (peri < 0 || cut < 0) return [];
        if (peri < cut) return [SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY];
        return [CUT_PATH_INTERNAL_SEQUENCE_KEY, SHEET_PERIMETER_PATH_KEY];
    }

    function normalizeCutPathSequence(sequence) {
        const keys = (Array.isArray(sequence) ? sequence : [])
            .map(key => String(key || "").trim())
            .filter(Boolean);
        if (!keys.length) return [CUT_PATH_INTERNAL_SEQUENCE_KEY, SHEET_PERIMETER_PATH_KEY];
        if (keys[0] === SHEET_PERIMETER_PATH_KEY) {
            return [SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY];
        }
        return [CUT_PATH_INTERNAL_SEQUENCE_KEY, SHEET_PERIMETER_PATH_KEY];
    }

    function sheetPerimeterPrecedesMilling(order) {
        const keys = Array.isArray(order) ? order.map(key => String(key)) : [];
        const peri = keys.indexOf(SHEET_PERIMETER_OPERATION_KEY);
        if (peri < 0) return false;
        return INTERNAL_OPERATIONS.some(key => {
            const at = keys.indexOf(key);
            return at >= 0 && at > peri;
        });
    }

    function perimeterIsEarly(orderOrSequence) {
        if (Array.isArray(orderOrSequence) && orderOrSequence.includes(SHEET_PERIMETER_OPERATION_KEY)) {
            return sheetPerimeterPrecedesMilling(orderOrSequence);
        }
        // Legacy sequence helpers still used by older tests/call sites.
        return Array.isArray(orderOrSequence)
            && orderOrSequence.length > 0
            && String(orderOrSequence[0] || "") === SHEET_PERIMETER_PATH_KEY;
    }

    function syncCutPathSequence(state) {
        if (normalizePerimeterJoinMode(state.perimeterJoinMode) !== "connected") {
            state.cutPathSequence = [];
            state.perimeterEarlyConfirmed = false;
            return;
        }
        state.cutPathSequence = deriveCutPathSequenceFromOrder(state.order);
        if (!sheetPerimeterPrecedesMilling(state.order)) {
            state.perimeterEarlyConfirmed = false;
        }
    }

    function ensureSheetPerimeterOperation(state) {
        if (!Array.isArray(state.order)) state.order = [];
        if (!state.order.includes(SHEET_PERIMETER_OPERATION_KEY)) {
            const cutAt = state.order.indexOf("cut_path");
            if (cutAt >= 0) state.order.splice(cutAt, 0, SHEET_PERIMETER_OPERATION_KEY);
            else state.order.push(SHEET_PERIMETER_OPERATION_KEY);
        }
        if (!state.operations) state.operations = {};
        if (!state.sources) state.sources = {};
        if (!state.factoryPresets) state.factoryPresets = {};
        if (!Object.prototype.hasOwnProperty.call(state.operations, SHEET_PERIMETER_OPERATION_KEY)) {
            state.operations[SHEET_PERIMETER_OPERATION_KEY] = state.operations.cut_path || "";
        }
        if (!state.sources[SHEET_PERIMETER_OPERATION_KEY]) {
            state.sources[SHEET_PERIMETER_OPERATION_KEY] = "factory";
        }
        if (!state.factoryPresets[SHEET_PERIMETER_OPERATION_KEY]) {
            state.factoryPresets[SHEET_PERIMETER_OPERATION_KEY] = state.factoryPresets.cut_path || "";
        }
        state.expanded[SHEET_PERIMETER_OPERATION_KEY] = true;
        syncCutPathSequence(state);
    }

    function removeSheetPerimeterOperation(state) {
        state.order = (state.order || []).filter(key => key !== SHEET_PERIMETER_OPERATION_KEY);
        if (state.operations) delete state.operations[SHEET_PERIMETER_OPERATION_KEY];
        if (state.sources) delete state.sources[SHEET_PERIMETER_OPERATION_KEY];
        if (state.factoryPresets) delete state.factoryPresets[SHEET_PERIMETER_OPERATION_KEY];
        if (state.expanded) delete state.expanded[SHEET_PERIMETER_OPERATION_KEY];
        state.cutPathSequence = [];
        state.perimeterEarlyConfirmed = false;
    }

    function applyPerimeterJoinMode(frm, dialog, workspace, sheet, state, mode) {
        state.perimeterJoinMode = normalizePerimeterJoinMode(mode);
        if (state.perimeterJoinMode === "connected") {
            ensureSheetPerimeterOperation(state);
        } else {
            removeSheetPerimeterOperation(state);
        }
        state.expanded.cut_path = true;
        if (dialog && dialog._almdinaSheet) {
            refreshDialog(
                frm,
                dialog,
                workspace,
                sheet,
                state,
                dialog._almdinaSheet.board
            );
        } else {
            const body = dialogRoot(dialog);
            const article = body && body.querySelector('.dco-operational-layer[data-layer="cut_path"]');
            if (article) {
                paintPerimeterJoinControls(article, state, Boolean(workspace.can_prepare));
            }
        }
        requestSheetProgramPreview(frm, dialog, workspace, sheet, state);
    }

    function paintPerimeterJoinControls(article, state, canPrepare) {
        if (!article) return;
        const markup = perimeterJoinControlsMarkup(state, canPrepare);
        const existing = article.querySelector("[data-perimeter-join]");
        if (!existing) {
            const head = article.querySelector(".dco-operational-layer__head");
            if (head) head.insertAdjacentHTML("afterend", markup);
            return;
        }
        const joinMode = normalizePerimeterJoinMode(state.perimeterJoinMode);
        existing.querySelectorAll("[data-perimeter-join-mode]").forEach(input => {
            input.checked = String(input.value || "") === joinMode;
            input.disabled = !canPrepare;
        });
        const early = joinMode === "connected" && sheetPerimeterPrecedesMilling(state.order);
        let warning = existing.querySelector("[data-perimeter-early-warning]");
        if (early && !warning) {
            existing.insertAdjacentHTML(
                "beforeend",
                `<div data-perimeter-early-warning>
                    <p class="dco-operational-sheet__warning" role="alert">${escapeHtml(translate("Cutting the sheet perimeter before milling may let pieces move after they separate from the board."))}</p>
                    <label class="dco-operational-sheet__confirm"><input type="checkbox" data-perimeter-confirm${state.perimeterEarlyConfirmed ? " checked" : ""}${canPrepare ? "" : " disabled"}> ${escapeHtml(translate("I understand and want to cut the sheet perimeter before liner, recessed handle, or rear groove."))}</label>
                </div>`
            );
        } else if (!early && warning) {
            warning.remove();
        } else if (warning) {
            const confirm = warning.querySelector("[data-perimeter-confirm]");
            if (confirm) {
                confirm.checked = Boolean(state.perimeterEarlyConfirmed);
                confirm.disabled = !canPrepare;
            }
        }
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
        const joinMode = normalizePerimeterJoinMode(sheet.perimeter_join_mode);
        const state = {
            operations,
            sources,
            factoryPresets,
            overrides,
            order,
            confirmed: Boolean(sheet.cut_path_early_confirmed),
            perimeterJoinMode: joinMode,
            cutPathSequence: [],
            perimeterEarlyConfirmed: Boolean(sheet.perimeter_cut_early_confirmed),
            cncMachine: String(sheet.cnc_machine || ""),
            offsetLeftCm: Number(sheet.offset_left_cm || 0),
            offsetBottomCm: Number(sheet.offset_bottom_cm || 0),
            sheetWidthCm: sheet.sheet_width_cm == null ? null : Number(sheet.sheet_width_cm),
            sheetLengthCm: sheet.sheet_length_cm == null ? null : Number(sheet.sheet_length_cm),
            expanded: {},
            customizing: {},
            selectedPathKey: "",
            selectedExecutionPathId: "",
            program: null,
        };
        if (joinMode === "connected") {
            ensureSheetPerimeterOperation(state);
            state.perimeterEarlyConfirmed = Boolean(sheet.perimeter_cut_early_confirmed)
                && sheetPerimeterPrecedesMilling(state.order);
        } else {
            removeSheetPerimeterOperation(state);
        }
        return state;
    }

    function stateSnapshot(state) {
        return JSON.stringify({
            operations: state.order.map(key => [key, state.operations[key] || ""]),
            sources: state.order.map(key => [key, (state.sources && state.sources[key]) || "factory"]),
            overrides: Object.keys(state.overrides).sort().map(key => [key, state.overrides[key] || ""]),
            order: state.order.slice(),
            confirmed: Boolean(state.confirmed) && cutPathIsEarly(state.order),
            perimeterJoinMode: normalizePerimeterJoinMode(state.perimeterJoinMode),
            cutPathSequence: Array.isArray(state.cutPathSequence) ? state.cutPathSequence.slice() : [],
            perimeterEarlyConfirmed: Boolean(state.perimeterEarlyConfirmed)
                && sheetPerimeterPrecedesMilling(state.order),
            cncMachine: String(state.cncMachine || ""),
            offsetLeftCm: Number(state.offsetLeftCm || 0),
            offsetBottomCm: Number(state.offsetBottomCm || 0),
        });
    }

    function findCncMachine(workspace, name) {
        const token = String(name || "").trim();
        return (workspace.cnc_machines || []).find(item => String(item.name || "") === token) || null;
    }

    function placementPreviewPayload(workspace, state) {
        const machine = findCncMachine(workspace, state.cncMachine);
        if (!machine) return null;
        return {
            machine_name: String(machine.machine_name || machine.name || ""),
            machine_width_cm: Number(machine.width_cm || 0),
            machine_length_cm: Number(machine.length_cm || 0),
            offset_left_cm: Number(state.offsetLeftCm || 0),
            offset_bottom_cm: Number(state.offsetBottomCm || 0),
            sheet_width_cm: state.sheetWidthCm == null ? null : Number(state.sheetWidthCm),
            sheet_length_cm: state.sheetLengthCm == null ? null : Number(state.sheetLengthCm),
        };
    }

    const PLACEMENT_MESSAGES = Object.freeze({
        offset_left_invalid: "The distance from the left must be zero or a positive number of centimetres.",
        offset_bottom_invalid: "The distance from the bottom must be zero or a positive number of centimetres.",
        sheet_exceeds_machine_width: "The sheet plus the left offset exceeds the machine width.",
        sheet_exceeds_machine_length: "The sheet plus the bottom offset exceeds the machine length.",
        cnc_machine_required: "Choose a CNC machine before generating the NC file.",
        cnc_machine_disabled: "The selected CNC machine is disabled.",
        placement_incomplete: "Sheet placement on the CNC machine is incomplete.",
    });

    function validateSheetPlacementFits(workspace, state, options = {}) {
        const requireMachine = Boolean(options.requireMachine);
        const machineName = String(state.cncMachine || "").trim();
        if (!machineName) {
            return requireMachine
                ? { ok: false, code: "cnc_machine_required", message: translate(PLACEMENT_MESSAGES.cnc_machine_required) }
                : { ok: true, code: "", message: "" };
        }
        const machine = findCncMachine(workspace, machineName);
        if (!machine) {
            return {
                ok: false,
                code: "cnc_machine_not_found",
                message: translate("The selected CNC machine was not found."),
            };
        }
        if (!Boolean(machine.enabled)) {
            return {
                ok: false,
                code: "cnc_machine_disabled",
                message: translate(PLACEMENT_MESSAGES.cnc_machine_disabled),
            };
        }
        const left = Number(state.offsetLeftCm);
        const bottom = Number(state.offsetBottomCm);
        if (!Number.isFinite(left) || left < 0) {
            return {
                ok: false,
                code: "offset_left_invalid",
                message: translate(PLACEMENT_MESSAGES.offset_left_invalid),
            };
        }
        if (!Number.isFinite(bottom) || bottom < 0) {
            return {
                ok: false,
                code: "offset_bottom_invalid",
                message: translate(PLACEMENT_MESSAGES.offset_bottom_invalid),
            };
        }
        const sheetW = Number(state.sheetWidthCm);
        const sheetL = Number(state.sheetLengthCm);
        const machineW = Number(machine.width_cm);
        const machineL = Number(machine.length_cm);
        if (!(sheetW > 0) || !(sheetL > 0) || !(machineW > 0) || !(machineL > 0)) {
            return {
                ok: false,
                code: "placement_incomplete",
                message: translate(PLACEMENT_MESSAGES.placement_incomplete),
            };
        }
        if (left + sheetW > machineW) {
            return {
                ok: false,
                code: "sheet_exceeds_machine_width",
                message: translate(PLACEMENT_MESSAGES.sheet_exceeds_machine_width),
            };
        }
        if (bottom + sheetL > machineL) {
            return {
                ok: false,
                code: "sheet_exceeds_machine_length",
                message: translate(PLACEMENT_MESSAGES.sheet_exceeds_machine_length),
            };
        }
        return { ok: true, code: "", message: "" };
    }

    function reportPlacementValidation(result) {
        if (!result || result.ok) return true;
        if (window.frappe && typeof frappe.msgprint === "function") {
            frappe.msgprint(result.message || translate(PLACEMENT_MESSAGES.placement_incomplete));
        }
        return false;
    }

    function placementControlsMarkup(workspace, state, canPrepare) {
        const machines = Array.isArray(workspace.cnc_machines) ? workspace.cnc_machines : [];
        const disabled = canPrepare ? "" : " disabled";
        const selected = String(state.cncMachine || "");
        const machine = findCncMachine(workspace, selected);
        const options = [`<option value="">${escapeHtml(translate("Choose a CNC machine"))}</option>`]
            .concat(machines.map(item => {
                const name = String(item.name || "");
                const label = String(item.machine_name || name);
                const enabled = Boolean(item.enabled);
                return `<option value="${escapeHtml(name)}"${name === selected ? " selected" : ""}${enabled ? "" : " disabled"}>${escapeHtml(label)}</option>`;
            }));
        const dims = machine
            ? `<p class="dco-operational-sheet__note" data-machine-dims>${escapeHtml(translate("Machine size: {0} cm × {1} cm (width × length)", [
                Number(machine.width_cm || 0),
                Number(machine.length_cm || 0),
            ]))}</p>`
            : `<p class="dco-operational-sheet__note" data-machine-dims>${escapeHtml(translate("Select a machine to show bed size and placement offsets."))}</p>`;
        const offsetsHidden = machine ? "" : " hidden";
        return `<section class="dco-operational-sheet__placement" data-sheet-placement>
            <h4>${escapeHtml(translate("Sheet placement on CNC machine"))}</h4>
            <label class="dco-operational-sheet__choice">${escapeHtml(translate("CNC machine"))}
                <select data-cnc-machine${disabled}>${options.join("")}</select>
            </label>
            ${dims}
            <div class="dco-operational-sheet__offsets" data-placement-offsets${offsetsHidden}>
                <label>${escapeHtml(translate("Distance from left (cm)"))}
                    <input type="number" min="0" step="0.001" inputmode="decimal" data-offset-left value="${escapeHtml(state.offsetLeftCm)}"${disabled}>
                </label>
                <label>${escapeHtml(translate("Distance from bottom (cm)"))}
                    <input type="number" min="0" step="0.001" inputmode="decimal" data-offset-bottom value="${escapeHtml(state.offsetBottomCm)}"${disabled}>
                </label>
            </div>
        </section>`;
    }

    function applyLayerPreset(state, key, name) {
        state.operations[key] = String(name || "");
        state.sources[key] = "sheet";
        return state;
    }

    function restoreLayerPreset(state, key) {
        state.sources[key] = "factory";
        let restored = String((state.factoryPresets && state.factoryPresets[key]) || "");
        if (key === SHEET_PERIMETER_OPERATION_KEY && !restored) {
            restored = String(state.operations.cut_path || state.factoryPresets.cut_path || "");
        }
        state.operations[key] = restored;
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
        const key = String(path.operation_key || "");
        const chosen = state.operations[key] || "";
        if (chosen) return chosen;
        if (key === SHEET_PERIMETER_OPERATION_KEY
            && (state.sources && state.sources[key]) !== "sheet") {
            return state.operations.cut_path || "";
        }
        return "";
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

    function fitBoard(board, options = {}) {
        if (!board) return board;
        let width = parseFloat(board.dataset.naturalWidth || "");
        let height = parseFloat(board.dataset.naturalHeight || "");
        if (!width || !height) {
            width = parseFloat(board.style.width) || 560;
            height = parseFloat(board.style.height) || 260;
            board.dataset.naturalWidth = String(width);
            board.dataset.naturalHeight = String(height);
        }
        const maxWidthPx = Number(options.maxWidthPx);
        if (Number.isFinite(maxWidthPx) && maxWidthPx > 0) {
            board.style.width = `${maxWidthPx}px`;
            board.style.maxWidth = `${maxWidthPx}px`;
        } else {
            board.style.width = "100%";
            board.style.maxWidth = "100%";
        }
        board.style.height = "auto";
        board.style.aspectRatio = `${width} / ${height}`;
        return board;
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

    function mountBoard(target, board, options = {}) {
        target.replaceChildren();
        if (!board) {
            target.innerHTML = `<p class="dco-operational-files__note">${escapeHtml(translate("Board preview is not available."))}</p>`;
            return;
        }
        const clone = board.cloneNode(true);
        if (board.dataset.naturalWidth) clone.dataset.naturalWidth = board.dataset.naturalWidth;
        if (board.dataset.naturalHeight) clone.dataset.naturalHeight = board.dataset.naturalHeight;
        fitBoard(clone, options);
        target.appendChild(clone);
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
                if (!frm || !frm.doc || !frm.doc.name || !sheetNo) return;
                openSheetSettingsTab(frm.doc.name, sheetNo);
            });
        });
        root.querySelectorAll("[data-cnc-card-download], [data-cnc-history-download]").forEach(button => {
            button.addEventListener("click", () => {
                const name = button.getAttribute("data-cnc-card-download") || button.getAttribute("data-cnc-history-download");
                downloadServerNc(frm, name, button.getAttribute("data-file-url"));
            });
        });
    }

    function isSheetPerimeterPath(path) {
        if (!path) return false;
        return Boolean(path.is_sheet_perimeter)
            || String(path.path_key || "") === SHEET_PERIMETER_PATH_KEY;
    }

    function pathDisplayLabel(path) {
        if (isSheetPerimeterPath(path)) {
            return translate("Sheet Perimeter Cut");
        }
        if (path && path.piece_label) {
            return translate("Piece {0}", [path.piece_label]);
        }
        if (path && path.shared) {
            return translate("Shared path");
        }
        return translate("Piece number is not available");
    }

    function selectionText(workspace, sheet, state) {
        const physical = findPhysicalPath(state && state.program, state && state.selectedExecutionPathId);
        if (physical) {
            const piece = pathDisplayLabel(physical);
            const preset = presetLabel(
                workspace,
                effectivePreset(state, {
                    path_key: physical.path_key,
                    operation_key: physical.operation_key,
                })
            );
            const passes = physical.pass_count > 1
                ? ` · ${translate("{0} passes", [physical.pass_count])}`
                : "";
            return `${translate("Path {0}", [physical.path_number])} · ${piece} · ${operationLabel(physical.operation_key)} · ${preset}${passes}`;
        }
        const path = (sheet.paths || []).find(item => item.path_key === state.selectedPathKey);
        if (!path) return translate("Select a path to see its piece, layer, and preset.");
        return `${pathDisplayLabel(path)} · ${operationLabel(path.operation_key)} · ${presetLabel(workspace, effectivePreset(state, path))}`;
    }

    function perimeterJoinControlsMarkup(state, canPrepare) {
        const joinMode = normalizePerimeterJoinMode(state.perimeterJoinMode);
        const disabled = canPrepare ? "" : " disabled";
        const early = joinMode === "connected" && sheetPerimeterPrecedesMilling(state.order);
        const warning = early
            ? `<div data-perimeter-early-warning>
                <p class="dco-operational-sheet__warning" role="alert">${escapeHtml(translate("Cutting the sheet perimeter before milling may let pieces move after they separate from the board."))}</p>
                <label class="dco-operational-sheet__confirm"><input type="checkbox" data-perimeter-confirm${state.perimeterEarlyConfirmed ? " checked" : ""}${disabled}> ${escapeHtml(translate("I understand and want to cut the sheet perimeter before liner, recessed handle, or rear groove."))}</label>
               </div>`
            : "";
        return `<fieldset class="dco-operational-perimeter" data-perimeter-join>
            <legend>${escapeHtml(translate("Sheet perimeter cut method"))}</legend>
            <label class="dco-operational-perimeter__option">
                <input type="radio" name="perimeter_join_mode" value="separate" data-perimeter-join-mode="separate"${joinMode === "separate" ? " checked" : ""}${disabled}>
                <span>${escapeHtml(translate("Disconnected perimeter"))}</span>
            </label>
            <label class="dco-operational-perimeter__option">
                <input type="radio" name="perimeter_join_mode" value="connected" data-perimeter-join-mode="connected"${joinMode === "connected" ? " checked" : ""}${disabled}>
                <span>${escapeHtml(translate("Connected perimeter"))}</span>
            </label>
            ${warning}
        </fieldset>`;
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
        const associations = ((sheet.machining || {}).associations) || [];
        const lastIndex = Math.max(0, associations.length - 1);
        const orderItems = associations.map((row, index) => {
            const earlierDisabled = !canPrepare || index === 0 ? " disabled" : "";
            const laterDisabled = !canPrepare || index === lastIndex ? " disabled" : "";
            const source = (row.selection && row.selection.kind === "sheet_perimeter")
                ? "Sheet Perimeter"
                : ((row.selection && row.selection.operation_key) || "");
            return `<li class="dco-operational-order__item" data-association-id="${escapeHtml(row.association_id)}">
            <span class="dco-operational-order__label">${escapeHtml(row.name || row.association_id)} <small>${escapeHtml(source)}</small></span>
            <span class="dco-operational-order__moves">
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-move="earlier" title="${escapeHtml(translate("Move earlier"))}" aria-label="${escapeHtml(translate("Move earlier"))}"${earlierDisabled}>${orderMoveIcon("up-line")}</button>
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-move="later" title="${escapeHtml(translate("Move later"))}" aria-label="${escapeHtml(translate("Move later"))}"${laterDisabled}>${orderMoveIcon("down-line")}</button>
            </span>
        </li>`;
        }).join("");
        const warning = early
            ? `<p class="dco-operational-sheet__warning" role="alert">${escapeHtml(translate("Cutting first may let the pieces move after they separate from the board."))}</p>
                <label class="dco-operational-sheet__confirm"><input type="checkbox" data-cut-confirm${state.confirmed ? " checked" : ""}${disabled}> ${escapeHtml(translate("I understand and want to keep this operation order."))}</label>`
            : "";
        if (!state.sections || state._artcamSheetNo !== Number(sheet && sheet.sheet_no)) {
            if (state._artcamSheetNo !== Number(sheet && sheet.sheet_no)) {
                state.artcamForm = null;
                state.vectorSelection = [];
                state.sections = null;
            }
            state._artcamSheetNo = Number(sheet && sheet.sheet_no);
        }
        if (!state.sections) state.sections = { placement: false, perimeter: false, associations: true, order: false };
        const section = (id, title, body) => {
            const open = Boolean(state.sections[id]);
            return `<section class="dco-sheet-acc${open ? "" : " is-collapsed"}" data-sheet-section="${id}">
                <div class="dco-sheet-acc__title">
                    <h4>${escapeHtml(translate(title))}</h4>
                    <button type="button" class="dco-sheet-acc__toggle" data-sheet-acc aria-expanded="${open ? "true" : "false"}" aria-label="${escapeHtml(translate(title))}"></button>
                </div>
                <div class="dco-sheet-acc__body">${body}</div>
            </section>`;
        };
        return `<div class="dco-operational-sheet">
            <div class="dco-operational-sheet__body">
                <div class="dco-operational-sheet__preview">
                    <div data-sheet-preview></div>
                    <p class="dco-operational-sheet__selection" role="status">${escapeHtml(selectionText(workspace, sheet, state))}</p>
                    <p class="dco-operational-files__status" data-sheet-nc-status="${escapeHtml(sheet.status || "")}">${escapeHtml(statusLabel(sheet.status))}</p>
                </div>
                <div class="dco-operational-sheet__settings">
                    ${section("placement", "Machine placement", placementControlsMarkup(workspace, state, canPrepare))}
                    ${section("perimeter", "Sheet Perimeter", perimeterJoinControlsMarkup(state, canPrepare))}
                    ${section("associations", "Vector Associations", window.AlmdinaArtcamMachining ? window.AlmdinaArtcamMachining.markup(workspace, sheet, state) : "")}
                    ${section("order", "Operation order", `<ol class="dco-operational-order">${orderItems || `<li class="dco-artcam-note">${escapeHtml(translate("Associations appear here after they are saved."))}</li>`}</ol>${warning}`)}
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

    function dialogScrollHost(dialog) {
        if (!dialog || !dialog.$wrapper || typeof dialog.$wrapper.find !== "function") return null;
        return dialog.$wrapper.find(".modal-body").get(0) || null;
    }

    function preserveDialogScroll(dialog, mutate) {
        const host = dialogScrollHost(dialog);
        const top = host ? host.scrollTop : 0;
        const result = typeof mutate === "function" ? mutate() : undefined;
        const restore = () => {
            const live = dialogScrollHost(dialog);
            if (live) live.scrollTop = top;
        };
        restore();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(restore);
        return result;
    }

    function ensureMetaParagraph(article, className, afterSelector) {
        let node = article.querySelector(`.${className}`);
        if (node) return node;
        node = document.createElement("p");
        node.className = className;
        const after = afterSelector ? article.querySelector(afterSelector) : null;
        if (after && after.parentNode === article) {
            after.insertAdjacentElement("afterend", node);
        } else {
            article.appendChild(node);
        }
        return node;
    }

    function paintLayerMeta(body, workspace, sheet, state, layerKey) {
        if (!body || !layerKey) return;
        const article = body.querySelector(`.dco-operational-layer[data-layer="${layerKey}"]`);
        if (!article) return;
        const selected = state.operations[layerKey] || "";
        const source = (state.sources && state.sources[layerKey]) === "sheet" ? "sheet" : "factory";
        const sourceEl = article.querySelector("[data-layer-source]");
        if (sourceEl) {
            sourceEl.setAttribute("data-layer-source", source);
            sourceEl.textContent = translate(source === "sheet" ? "Sheet choice" : "Factory default");
        }
        const factsText = presetFacts(workspace, selected);
        const facts = article.querySelector(".dco-operational-layer__facts");
        if (factsText) {
            const node = facts || ensureMetaParagraph(article, "dco-operational-layer__facts", ".dco-operational-layer__head");
            node.textContent = factsText;
        } else if (facts) {
            facts.remove();
        }
        const issueText = presetIssue(workspace, selected);
        const issue = article.querySelector(".dco-operational-layer__issue");
        if (issueText) {
            const node = issue || ensureMetaParagraph(article, "dco-operational-layer__issue", ".dco-operational-layer__facts, .dco-operational-layer__head");
            node.setAttribute("role", "status");
            node.textContent = issueText;
        } else if (issue) {
            issue.remove();
        }
        article.querySelectorAll(".dco-operational-path").forEach(row => {
            const pathKey = row.getAttribute("data-path-key");
            const executionId = row.getAttribute("data-execution-path-id");
            const operationKey = row.getAttribute("data-path-operation") || layerKey;
            const custom = Boolean(state.overrides[pathKey]);
            row.classList.toggle("is-custom", custom);
            row.setAttribute("data-custom", custom ? "1" : "0");
            if (executionId) {
                row.classList.toggle("is-selected", executionId === state.selectedExecutionPathId);
            } else {
                row.classList.toggle("is-selected", pathKey === state.selectedPathKey);
            }
            const badge = row.querySelector(".dco-operational-path__badge");
            if (badge) {
                badge.textContent = translate(custom ? "Custom preset" : "Uses the layer preset");
            }
            const effective = row.querySelector(".dco-operational-path__effective");
            if (effective) {
                effective.textContent = presetLabel(
                    workspace,
                    effectivePreset(state, { path_key: pathKey, operation_key: operationKey })
                );
            }
        });
        const selection = body.querySelector(".dco-operational-sheet__selection");
        const preview = body.querySelector("[data-sheet-preview]");
        if (selection) selection.textContent = selectionText(workspace, sheet, state);
        if (preview) highlightCutPreview(preview, state);
    }

    function bindDialog(frm, dialog, workspace, sheet, state, board) {
        const body = dialogRoot(dialog);
        if (!body) return;
        const canPrepare = Boolean(workspace.can_prepare);
        dialog._almdinaSheet = { frm, workspace, sheet, state, board };
        const preview = body.querySelector("[data-sheet-preview]");
        syncSheetFooter(dialog, workspace, sheet, state);
        requestSheetProgramPreview(frm, dialog, workspace, sheet, state);

        function liveContext() {
            return dialog._almdinaSheet || { frm, workspace, sheet, state, board };
        }

        function refreshSelection() {
            const live = liveContext();
            const selection = body.querySelector(".dco-operational-sheet__selection");
            if (selection) selection.textContent = selectionText(live.workspace, live.sheet, live.state);
            const livePreview = body.querySelector("[data-sheet-preview]") || preview;
            highlightCutPreview(livePreview, live.state);
            body.querySelectorAll(".dco-operational-path").forEach(row => {
                const executionId = row.getAttribute("data-execution-path-id");
                if (executionId) {
                    row.classList.toggle("is-selected", executionId === live.state.selectedExecutionPathId);
                    return;
                }
                row.classList.toggle("is-selected", row.getAttribute("data-path-key") === live.state.selectedPathKey);
            });
        }

        if (!body._cncSheetInteractionsBound) {
            body._cncSheetInteractionsBound = true;
            body.addEventListener("change", event => {
                const live = liveContext();
                const target = event.target;
                if (!live || !live.state || !target || typeof target.getAttribute !== "function") return;
                const joinMode = target.getAttribute("data-perimeter-join-mode");
                if (joinMode) {
                    if (!target.checked) return;
                    applyPerimeterJoinMode(
                        live.frm,
                        dialog,
                        live.workspace,
                        live.sheet,
                        live.state,
                        joinMode
                    );
                    return;
                }
                if (target.hasAttribute("data-perimeter-confirm")) {
                    live.state.perimeterEarlyConfirmed = Boolean(target.checked);
                    return;
                }
                if (target.hasAttribute("data-cut-confirm")) {
                    live.state.confirmed = Boolean(target.checked);
                    return;
                }
                if (target.hasAttribute("data-cnc-machine")) {
                    live.state.cncMachine = String(target.value || "");
                    const offsets = body.querySelector("[data-placement-offsets]");
                    const dims = body.querySelector("[data-machine-dims]");
                    const machine = findCncMachine(live.workspace, live.state.cncMachine);
                    if (offsets) offsets.hidden = !machine;
                    if (dims) {
                        dims.textContent = machine
                            ? translate("Machine size: {0} cm × {1} cm (width × length)", [
                                Number(machine.width_cm || 0),
                                Number(machine.length_cm || 0),
                            ])
                            : translate("Select a machine to show bed size and placement offsets.");
                    }
                    // Keep existing offsets; warn when they no longer fit the new bed.
                    if (machine) reportPlacementValidation(validateSheetPlacementFits(live.workspace, live.state));
                    requestSheetProgramPreview(live.frm, dialog, live.workspace, live.sheet, live.state);
                    return;
                }
                if (target.hasAttribute("data-offset-left") || target.hasAttribute("data-offset-bottom")) {
                    const leftInput = body.querySelector("[data-offset-left]");
                    const bottomInput = body.querySelector("[data-offset-bottom]");
                    live.state.offsetLeftCm = Number((leftInput && leftInput.value) || 0);
                    live.state.offsetBottomCm = Number((bottomInput && bottomInput.value) || 0);
                    reportPlacementValidation(validateSheetPlacementFits(live.workspace, live.state));
                    requestSheetProgramPreview(live.frm, dialog, live.workspace, live.sheet, live.state);
                }
            });
            body.addEventListener("input", event => {
                const live = liveContext();
                const target = event.target;
                if (!live || !live.state || !target || typeof target.getAttribute !== "function") return;
                if (target.hasAttribute("data-offset-left") || target.hasAttribute("data-offset-bottom")) {
                    const leftInput = body.querySelector("[data-offset-left]");
                    const bottomInput = body.querySelector("[data-offset-bottom]");
                    live.state.offsetLeftCm = Number((leftInput && leftInput.value) || 0);
                    live.state.offsetBottomCm = Number((bottomInput && bottomInput.value) || 0);
                    requestSheetProgramPreview(live.frm, dialog, live.workspace, live.sheet, live.state);
                }
            });
            body.addEventListener("click", event => {
                const live = liveContext();
                const target = event.target;
                if (!live || !live.state || !target || typeof target.closest !== "function") return;
                const accordion = target.closest("[data-sheet-acc]");
                if (accordion) {
                    const section = accordion.closest("[data-sheet-section]");
                    const id = section && section.getAttribute("data-sheet-section");
                    if (!id || !section) return;
                    const open = section.classList.contains("is-collapsed");
                    section.classList.toggle("is-collapsed", !open);
                    accordion.setAttribute("aria-expanded", open ? "true" : "false");
                    live.state.sections = Object.assign({}, live.state.sections, { [id]: open });
                    return;
                }
                const customize = target.closest("[data-customize-path]");
                if (customize) {
                    const pathKey = customize.getAttribute("data-customize-path");
                    live.state.customizing[pathKey] = true;
                    const row = customize.closest(".dco-operational-path");
                    const operationKey = row && row.getAttribute("data-path-operation");
                    if (operationKey) live.state.expanded[operationKey] = true;
                    refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
                    return;
                }
                const reset = target.closest("[data-reset-path]");
                if (reset) {
                    clearPathPreset(live.state, reset.getAttribute("data-reset-path"));
                    refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
                    return;
                }
                const listHit = target.closest("[data-select-execution]");
                if (listHit) {
                    applyExecutionSelection(
                        body,
                        live.workspace,
                        live.sheet,
                        live.state,
                        listHit.getAttribute("data-select-execution")
                    );
                    return;
                }
                const settingsHit = target.closest("[data-select-path]");
                if (settingsHit && !settingsHit.getAttribute("data-select-execution")) {
                    live.state.selectedPathKey = settingsHit.getAttribute("data-select-path") || "";
                    live.state.selectedExecutionPathId = "";
                    refreshSelection();
                    return;
                }
                const previewHit = target.closest("[data-sheet-preview] [data-execution-path]");
                if (previewHit && event.shiftKey) {
                    const source = body.querySelector("[data-artcam-editor] [data-field=\"source\"]");
                    if (!source || source.value !== "selected_vectors") return;
                    if (typeof event.preventDefault === "function") event.preventDefault();
                    const pathKey = previewHit.getAttribute("data-execution-path") || "";
                    if (!pathKey || pathKey === "cut_path:sheet_perimeter") return;
                    if (!Array.isArray(live.state.vectorSelection)) live.state.vectorSelection = [];
                    const selected = new Set(live.state.vectorSelection);
                    if (selected.has(pathKey)) selected.delete(pathKey);
                    else selected.add(pathKey);
                    live.state.vectorSelection = Array.from(selected);
                    if (window.AlmdinaArtcamMachining) window.AlmdinaArtcamMachining.ensureForm(live.state);
                    highlightVectorSelection(body, live.state);
                    const count = body.querySelector("[data-vector-count]");
                    if (count) count.textContent = `${live.state.vectorSelection.length} Vectors Selected`;
                    return;
                }
                if (previewHit) {
                    applyExecutionSelection(
                        body,
                        live.workspace,
                        live.sheet,
                        live.state,
                        previewHit.getAttribute("data-execution-path-id")
                    );
                    return;
                }
                const toggle = target.closest("[data-toggle-layer]");
                if (toggle) {
                    const key = toggle.getAttribute("data-toggle-layer");
                    live.state.expanded[key] = !live.state.expanded[key];
                    const article = body.querySelector(`.dco-operational-layer[data-layer="${key}"]`);
                    const paths = article && article.querySelector(".dco-operational-layer__paths");
                    if (paths) paths.hidden = !live.state.expanded[key];
                    toggle.setAttribute("aria-expanded", live.state.expanded[key] ? "true" : "false");
                    toggle.textContent = translate(live.state.expanded[key] ? "Hide paths" : "Show paths");
                    return;
                }
                const restoreLayer = target.closest("[data-restore-layer]");
                if (restoreLayer && live.workspace.can_prepare) {
                    const key = restoreLayer.getAttribute("data-restore-layer");
                    restoreLayerPreset(live.state, key);
                    onPresetChosen(
                        live.frm,
                        dialog,
                        live.workspace,
                        live.sheet,
                        live.state,
                        live.board,
                        () => {},
                        live.state.operations[key] || "",
                        { layers: [key], skipApply: true }
                    );
                    return;
                }
                const restoreSheet = target.closest("[data-restore-sheet]");
                if (restoreSheet && live.workspace.can_prepare) {
                    restoreFactoryPresets(live.state);
                    (live.state.order || []).forEach(key => paintLayerMeta(body, live.workspace, live.sheet, live.state, key));
                    remountPresetValues(dialog, live.workspace, live.sheet, live.state);
                    requestSheetProgramPreview(live.frm, dialog, live.workspace, live.sheet, live.state);
                    return;
                }
                const moveOp = target.closest("[data-move]");
                if (moveOp && live.workspace.can_prepare) {
                    const associationItem = moveOp.closest("[data-association-id]");
                    if (associationItem) {
                        const id = associationItem.getAttribute("data-association-id");
                        const rows = (live.sheet.machining && live.sheet.machining.associations) || [];
                        const index = rows.findIndex(row => row.association_id === id);
                        const targetIndex = index + (moveOp.getAttribute("data-move") === "earlier" ? -1 : 1);
                        if (index < 0 || targetIndex < 0 || targetIndex >= rows.length) return;
                        const [item] = rows.splice(index, 1);
                        rows.splice(targetIndex, 0, item);
                        const preferred = [];
                        rows.forEach(row => {
                            const selection = row.selection || {};
                            const key = selection.kind === "sheet_perimeter" ? "sheet_perimeter" : selection.operation_key;
                            if (key && !preferred.includes(key)) preferred.push(key);
                        });
                        live.state.order = preferred.concat((live.state.order || []).filter(key => !preferred.includes(key)));
                        refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
                        return;
                    }
                    const item = moveOp.closest("[data-operation-key]");
                    const key = item && item.getAttribute("data-operation-key");
                    const direction = moveOp.getAttribute("data-move");
                    if (!key) return;
                    moveOperation(live.state, key, direction === "earlier" ? -1 : 1);
                    refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
                    const current = dialogRoot(dialog);
                    const moved = current && current.querySelector(`[data-operation-key="${key}"] [data-move="${direction}"]`);
                    if (moved) moved.focus();
                }
            });
            let dragKey = "";
            body.addEventListener("dragstart", event => {
                const item = event.target && event.target.closest && event.target.closest(".dco-operational-order__item");
                if (!item) return;
                dragKey = item.getAttribute("data-operation-key") || "";
                item.classList.add("is-dragging");
            });
            body.addEventListener("dragend", event => {
                const item = event.target && event.target.closest && event.target.closest(".dco-operational-order__item");
                if (item) item.classList.remove("is-dragging");
            });
            body.addEventListener("dragover", event => {
                if (event.target && event.target.closest && event.target.closest(".dco-operational-order__item")) {
                    event.preventDefault();
                }
            });
            body.addEventListener("drop", event => {
                const live = liveContext();
                const item = event.target && event.target.closest && event.target.closest(".dco-operational-order__item");
                if (!live || !item) return;
                event.preventDefault();
                const target = item.getAttribute("data-operation-key");
                if (!dragKey || dragKey === target) return;
                const next = live.state.order.filter(key => key !== dragKey);
                next.splice(next.indexOf(target), 0, dragKey);
                live.state.order = next;
                if (!cutPathIsEarly(next)) live.state.confirmed = false;
                refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
            });
        }
        mountPresetControls(frm, dialog, workspace, sheet, state, board);
        if (!canPrepare) return;
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
        syncCutPathSequence(state);
    }

    function dialogRoot(dialog) {
        const wrapper = dialog && dialog.fields_dict && dialog.fields_dict.body && dialog.fields_dict.body.$wrapper;
        if (!wrapper) return null;
        return wrapper[0] || wrapper;
    }

    function remountPresetValues(dialog, workspace, sheet, state) {
        const links = dialog && dialog._cncPresetLinks;
        if (!Array.isArray(links)) return;
        links.forEach(link => {
            if (!link || typeof link.setValue !== "function") return;
            if (link.kind === "operation") {
                link.setValue(state.operations[link.operationKey] || "");
                return;
            }
            if (link.kind === "path") {
                link.setValue(effectivePreset(state, {
                    path_key: link.pathKey,
                    operation_key: link.operationKey,
                }));
            }
        });
    }

    function syncWorkspacePresets(frm, dialog, workspace, sheet, state, board, selectedName, applySelected, options = {}) {
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
                onPresetChosen(frm, dialog, workspace, sheet, state, board, () => {}, selectedName || "", {
                    layers: options.layers,
                    skipApply: true,
                    forceRemountLinks: true,
                });
            },
            error() {
                if (dialog._cncPresetRequest !== request) return;
                if (typeof applySelected === "function") applySelected(selectedName || "");
                onPresetChosen(frm, dialog, workspace, sheet, state, board, () => {}, selectedName || "", {
                    layers: options.layers,
                    skipApply: true,
                });
            },
        });
    }

    function onPresetChosen(frm, dialog, workspace, sheet, state, board, applySelected, name, options = {}) {
        const selected = String(name || "");
        if (!options.skipApply && selected && !presetByName(workspace).has(selected)) {
            syncWorkspacePresets(
                frm,
                dialog,
                workspace,
                sheet,
                state,
                board,
                selected,
                applySelected,
                options
            );
            return;
        }
        if (!options.skipApply && typeof applySelected === "function") applySelected(selected);
        if (options.fullRefresh) {
            refreshDialog(frm, dialog, workspace, sheet, state, board);
            return;
        }
        const body = dialogRoot(dialog);
        if (!body) {
            refreshDialog(frm, dialog, workspace, sheet, state, board);
            return;
        }
        const layers = Array.isArray(options.layers) && options.layers.length
            ? options.layers
            : (state.order || []);
        layers.forEach(key => paintLayerMeta(body, workspace, sheet, state, key));
        if (options.forceRemountLinks) {
            preserveDialogScroll(dialog, () => {
                disposePresetLinks(dialog);
                mountPresetControls(frm, dialog, workspace, sheet, state, board);
            });
        } else {
            remountPresetValues(dialog, workspace, sheet, state);
        }
        requestSheetProgramPreview(frm, dialog, workspace, sheet, state);
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
                        value,
                        { layers: [key] }
                    );
                },
            });
            if (link) {
                links.push({
                    kind: "operation",
                    operationKey: key,
                    dispose: () => link.dispose(),
                    setValue: value => link.setValue(value),
                });
            }
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
                        value,
                        { layers: [operationKey].filter(Boolean) }
                    );
                },
            });
            if (link) {
                links.push({
                    kind: "path",
                    pathKey,
                    operationKey,
                    dispose: () => link.dispose(),
                    setValue: value => link.setValue(value),
                });
            }
        });
        dialog._cncPresetLinks = links;
    }

    function sheetGenerateArgs(frm, workspace, sheet, state) {
        const overrides = {};
        Object.keys(state.overrides || {}).forEach(key => {
            if (state.overrides[key]) overrides[key] = state.overrides[key];
        });
        const joinMode = normalizePerimeterJoinMode(state.perimeterJoinMode);
        return {
            order_name: frm.doc.name,
            sheet_no: sheet.sheet_no,
            operation_presets: state.operations,
            path_overrides: overrides,
            operation_order: state.order,
            cut_path_early_confirmed: state.confirmed ? 1 : 0,
            viewed_plan_token: `${workspace.cutting_plan}::${workspace.plan_revision}`,
            operation_sources: state.sources || {},
            perimeter_join_mode: joinMode,
            cut_path_sequence: joinMode === "connected"
                ? deriveCutPathSequenceFromOrder(state.order)
                : null,
            perimeter_cut_early_confirmed: joinMode === "connected"
                && sheetPerimeterPrecedesMilling(state.order)
                && state.perimeterEarlyConfirmed ? 1 : 0,
            cnc_machine: String(state.cncMachine || ""),
            offset_left_cm: Number(state.offsetLeftCm || 0),
            offset_bottom_cm: Number(state.offsetBottomCm || 0),
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
            perimeter_unavailable: translate("Keep separate cut paths, or fix the outer cut network so one closed perimeter can be formed."),
            perimeter_not_closed: translate("Close the outer cut network, or keep separate cut paths."),
            perimeter_geometry_ambiguous: translate("Remove branches from the outer cut network, or keep separate cut paths."),
            perimeter_components_disconnected: translate("Join the separate outer cut components, or keep separate cut paths."),
            perimeter_geometry_invalid: translate("Keep the approved cut geometry unchanged, or keep separate cut paths."),
            perimeter_join_mode_invalid: translate("Choose either a separate or a connected sheet perimeter."),
            cut_path_sequence_invalid: translate("Restore a valid CUT_PATH order that includes every cut path on this sheet."),
            perimeter_cut_early_unconfirmed: translate("Confirm the warning before cutting the sheet perimeter before liner, recessed handle, or rear groove."),
            cnc_machine_required: translate(PLACEMENT_MESSAGES.cnc_machine_required),
            sheet_exceeds_machine_width: translate(PLACEMENT_MESSAGES.sheet_exceeds_machine_width),
            sheet_exceeds_machine_length: translate(PLACEMENT_MESSAGES.sheet_exceeds_machine_length),
            toolpath_exceeds_machine: translate("A cutter path would leave the machine travel area after placement."),
            offset_left_invalid: translate(PLACEMENT_MESSAGES.offset_left_invalid),
            offset_bottom_invalid: translate(PLACEMENT_MESSAGES.offset_bottom_invalid),
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

    function refreshDialog(frm, dialog, workspace, sheet, state) {
        refreshSheetUi(frm, dialog, workspace, sheet, state);
    }

    function orderFormStub(orderName) {
        return {
            doc: { name: String(orderName || "") },
            doctype: "Door Cutting Order",
            __almdinaOperationalFilesRequest: 0,
            is_new() { return false; },
        };
    }

    function pageShellMarkup(workspace, sheet) {
        const locale = window.AlmdinaLocale;
        const dir = locale && typeof locale.direction === "function"
            ? locale.direction()
            : (document.documentElement && document.documentElement.getAttribute("dir")) || "rtl";
        const canPrepare = Boolean(workspace && workspace.can_prepare);
        const canDownload = Boolean(sheet && sheet.can_download_current && sheet.operational_file);
        const downloadLabel = sheet && sheet.download_is_previous
            ? translate("Download previous simulation NC")
            : translate("Download simulation NC");
        return `<div class="dco-cnc-sheet-page" dir="${dir === "ltr" ? "ltr" : "rtl"}">
            <header class="dco-cnc-sheet-page__toolbar">
                <div class="dco-cnc-sheet-page__identity">
                    <h1>${escapeHtml(translate("Sheet {0}", [sheet.sheet_no]))}</h1>
                    <p>
                        ${escapeHtml(workspace.order_name || workspace.order || "")}
                        · ${escapeHtml(translate("Approved plan"))}: ${escapeHtml(workspace.cutting_plan || "")}
                        · ${escapeHtml(translate("Plan revision"))} ${escapeHtml(workspace.plan_revision || "")}
                    </p>
                    <p class="dco-operational-files__note">${escapeHtml(translate("Simulation NC is for review only. It is not approved for a workshop machine."))}</p>
                </div>
                <div class="dco-cnc-sheet-page__actions">
                    <button type="button" class="btn btn-default btn-sm" data-cnc-back-order>${escapeHtml(translate("Back to the order"))}</button>
                    <button type="button" class="btn btn-primary btn-sm" data-cnc-save-sheet${canPrepare ? "" : " disabled"}>${escapeHtml(translate("Save sheet settings"))}</button>
                    <button type="button" class="btn btn-default btn-sm" data-cnc-generate-nc data-cnc-page-action="generate"${canPrepare ? "" : " disabled"}>${escapeHtml(translate("Generate NC file"))}</button>
                    <button type="button" class="btn btn-default btn-sm" data-cnc-page-download data-operational-file="${escapeHtml((sheet && sheet.operational_file) || "")}" data-file-url="${escapeHtml((sheet && sheet.generated_file) || "")}"${canDownload ? "" : " hidden"}>${escapeHtml(downloadLabel)}</button>
                </div>
            </header>
            <div class="dco-cnc-sheet-page__workspace" data-sheet-body></div>
        </div>`;
    }

    function syncPageToolbar(ui, workspace, sheet, state) {
        if (!ui || !ui.root) return;
        const canPrepare = Boolean(workspace && workspace.can_prepare);
        const save = ui.root.querySelector("[data-cnc-save-sheet]");
        const generate = ui.root.querySelector("[data-cnc-generate-nc]");
        const download = ui.root.querySelector("[data-cnc-page-download]");
        const control = generateNcControlState({ canPrepare });
        if (save) save.disabled = !canPrepare;
        if (generate) {
            generate.disabled = Boolean(control.disabled);
            generate.setAttribute("title", control.reason || "");
        }
        if (download) {
            const canDownload = Boolean(sheet && sheet.can_download_current && sheet.operational_file);
            download.hidden = !canDownload;
            if (canDownload) {
                download.setAttribute("data-operational-file", sheet.operational_file || "");
                download.setAttribute("data-file-url", sheet.generated_file || "");
                download.textContent = translate(
                    sheet.download_is_previous ? "Download previous simulation NC" : "Download simulation NC"
                );
            }
        }
        bindGenerateNc(ui, ui.root, {
            canPrepare,
            args: sheetGenerateArgs(ui.frm, workspace, sheet, state),
            sheetNo: sheet.sheet_no,
            frm: ui.frm,
            state,
            sheet,
            workspace,
        });
    }

    function refreshSheetUi(frm, ui, workspace, sheet, state) {
        const wrapper = dialogRoot(ui);
        if (!wrapper) return;
        preserveDialogScroll(ui, () => {
            disposePresetLinks(ui);
            ui._almdinaSheet = { frm, workspace, sheet, state, board: null };
            wrapper.innerHTML = dialogMarkup(workspace, sheet, state);
            const preview = wrapper.querySelector("[data-sheet-preview]");
            if (preview && ui.mode === "page") preview.setAttribute("data-preview-layout", "page");
            bindDialog(frm, ui, workspace, sheet, state, null);
            if (window.AlmdinaArtcamMachining) {
                window.AlmdinaArtcamMachining.bind(wrapper, {
                    sheet,
                    workspace,
                    state,
                    getArgs() {
                        return sheetGenerateArgs(frm, workspace, sheet, state);
                    },
                    refresh() {
                        refreshSheetUi(frm, ui, workspace, sheet, state);
                    },
                    onWorkspace(message) {
                        const saved = (message.sheets || []).find(item => Number(item.sheet_no) === Number(sheet.sheet_no));
                        if (saved) refreshSheetUi(frm, ui, message, saved, state);
                    },
                });
            }
            if (ui.mode === "page") syncPageToolbar(ui, workspace, sheet, state);
        });
    }

    function saveSheetSettings(frm, ui, workspace, sheet, state, baselineHolder) {
        if (cutPathIsEarly(state.order) && !state.confirmed) {
            frappe.msgprint(translate("Cutting first may let the pieces move after they separate from the board."));
            return;
        }
        if (normalizePerimeterJoinMode(state.perimeterJoinMode) === "connected"
            && sheetPerimeterPrecedesMilling(state.order)
            && !state.perimeterEarlyConfirmed) {
            frappe.msgprint(translate("Cutting the sheet perimeter before milling may let pieces move after they separate from the board."));
            return;
        }
        if (!reportPlacementValidation(validateSheetPlacementFits(workspace, state))) return;
        const conflict = toolConflict(workspace, sheet, state);
        if (conflict) {
            frappe.msgprint(translate(CONFLICT_MESSAGES[conflict]));
            return;
        }
        const requestId = (frm.__almdinaOperationalFilesRequest || 0) + 1;
        frm.__almdinaOperationalFilesRequest = requestId;
        const identity = capture(frm);
        const saveButton = ui.mode === "page"
            ? ui.root && ui.root.querySelector("[data-cnc-save-sheet]")
            : (ui.get_primary_btn && ui.get_primary_btn());
        if (saveButton) {
            if (saveButton.prop) saveButton.prop("disabled", true);
            else saveButton.disabled = true;
        }
        frappe.call({
            method: `${METHOD}.save_cnc_operational_sheet`,
            args: sheetGenerateArgs(frm, workspace, sheet, state),
            callback(response) {
                if (frm.__almdinaOperationalFilesRequest !== requestId) return;
                if (ui.mode !== "page" && !stillCurrent(frm, identity)) return;
                const message = (response && response.message) || {};
                if (ui.mode !== "page") {
                    const root = host(frm);
                    if (root) paint(frm, root, message);
                }
                const saved = (message.sheets || []).find(item => Number(item.sheet_no) === Number(sheet.sheet_no));
                if (saved) {
                    const next = sheetState(saved);
                    state.operations = next.operations;
                    state.sources = next.sources;
                    state.factoryPresets = next.factoryPresets;
                    state.overrides = next.overrides;
                    state.order = next.order;
                    state.confirmed = next.confirmed;
                    state.perimeterJoinMode = next.perimeterJoinMode;
                    state.cutPathSequence = next.cutPathSequence;
                    state.perimeterEarlyConfirmed = next.perimeterEarlyConfirmed;
                    state.cncMachine = next.cncMachine;
                    state.offsetLeftCm = next.offsetLeftCm;
                    state.offsetBottomCm = next.offsetBottomCm;
                    state.sheetWidthCm = next.sheetWidthCm;
                    state.sheetLengthCm = next.sheetLengthCm;
                    baselineHolder.value = stateSnapshot(state);
                    refreshSheetUi(frm, ui, message, saved, state);
                }
                if (saveButton) {
                    if (saveButton.prop) saveButton.prop("disabled", false);
                    else saveButton.disabled = false;
                }
                if (window.frappe && frappe.show_alert) {
                    frappe.show_alert({ message: translate("Operational files saved."), indicator: "green" });
                }
            },
            error() {
                if (frm.__almdinaOperationalFilesRequest !== requestId) return;
                if (saveButton) {
                    if (saveButton.prop) saveButton.prop("disabled", false);
                    else saveButton.disabled = false;
                }
            },
        });
    }

    function mountSheetSettingsPage(main, options = {}) {
        if (!main) return null;
        const orderName = String(options.orderName || "").trim();
        const sheetNo = Number(options.sheetNo);
        if (!orderName || !Number.isFinite(sheetNo) || sheetNo <= 0) {
            main.innerHTML = `<div class="dco-cnc-sheet-page" role="alert"><p>${escapeHtml(translate("The sheet settings link is incomplete."))}</p></div>`;
            return null;
        }
        const request = (main.__cncSheetPageRequest || 0) + 1;
        main.__cncSheetPageRequest = request;
        main.innerHTML = `<div class="dco-cnc-sheet-page" role="status"><p>${escapeHtml(translate("Loading sheet settings..."))}</p></div>`;
        if (!window.frappe || typeof frappe.call !== "function") {
            main.innerHTML = `<div class="dco-cnc-sheet-page" role="alert"><p>${escapeHtml(translate("Sheet settings could not be loaded."))}</p></div>`;
            return null;
        }
        frappe.call({
            method: `${METHOD}.get_cnc_operational_workspace`,
            args: { order_name: orderName },
            callback(response) {
                if (main.__cncSheetPageRequest !== request) return;
                const workspace = (response && response.message) || {};
                workspace.order_name = workspace.order_name || orderName;
                if (!workspace.eligible) {
                    main.innerHTML = `<div class="dco-cnc-sheet-page" role="status"><p>${escapeHtml(workspace.message || translate("This order has no approved cutting plan. Operational files can be prepared only from the current approved plan, whether the system calculated it or it was uploaded and then approved."))}</p></div>`;
                    return;
                }
                const sheet = (workspace.sheets || []).find(item => Number(item.sheet_no) === sheetNo);
                if (!sheet) {
                    main.innerHTML = `<div class="dco-cnc-sheet-page" role="alert"><p>${escapeHtml(translate("This sheet is not available on the approved plan."))}</p></div>`;
                    return;
                }
                const frm = orderFormStub(orderName);
                const state = sheetState(sheet);
                const baselineHolder = { value: stateSnapshot(state), state };
                main.innerHTML = pageShellMarkup(workspace, sheet);
                const pageRoot = main.querySelector(".dco-cnc-sheet-page");
                const body = pageRoot && pageRoot.querySelector("[data-sheet-body]");
                if (!pageRoot || !body) return;
                const ui = {
                    mode: "page",
                    root: pageRoot,
                    frm,
                    fields_dict: { body: { $wrapper: [body] } },
                    $wrapper: null,
                    _cncPresetLinks: [],
                    _cncProgramPreviewRequest: 0,
                    _cncNcRequest: 0,
                    _cncPresetRequest: 0,
                };
                const back = pageRoot.querySelector("[data-cnc-back-order]");
                if (back) {
                    back.addEventListener("click", () => {
                        if (typeof frappe.set_route === "function") {
                            frappe.set_route("Form", "Door Cutting Order", orderName);
                        }
                    });
                }
                const save = pageRoot.querySelector("[data-cnc-save-sheet]");
                if (save) {
                    save.addEventListener("click", () => {
                        const live = ui._almdinaSheet || { workspace, sheet, state };
                        saveSheetSettings(frm, ui, live.workspace || workspace, live.sheet || sheet, live.state || state, baselineHolder);
                    });
                }
                const download = pageRoot.querySelector("[data-cnc-page-download]");
                if (download) {
                    download.addEventListener("click", () => {
                        downloadServerNc(
                            frm,
                            download.getAttribute("data-operational-file"),
                            download.getAttribute("data-file-url")
                        );
                    });
                }
                pageRoot.addEventListener("keydown", event => {
                    const live = ui._almdinaSheet;
                    const target = event.target;
                    if (!live || !live.workspace.can_prepare) return;
                    if (target && target.matches && target.matches("select, input, textarea")) return;
                    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                    const item = target && target.closest && target.closest("[data-operation-key]");
                    if (!item) return;
                    event.preventDefault();
                    const key = item.getAttribute("data-operation-key");
                    moveOperation(live.state, key, event.key === "ArrowUp" ? -1 : 1);
                    refreshSheetUi(frm, ui, live.workspace, live.sheet, live.state);
                    const row = dialogRoot(ui) && dialogRoot(ui).querySelector(`[data-operation-key="${key}"]`);
                    if (row) row.focus();
                });
                refreshSheetUi(frm, ui, workspace, sheet, state);
                main.__cncSheetPageUi = ui;
            },
            error() {
                if (main.__cncSheetPageRequest !== request) return;
                main.innerHTML = `<div class="dco-cnc-sheet-page" role="alert"><p>${escapeHtml(translate("Sheet settings could not be loaded."))}</p></div>`;
            },
        });
        return main;
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
        sheet_perimeter: "#0b7285",
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

    function clampCutPreviewZoom(value) {
        const zoom = Number(value);
        if (!Number.isFinite(zoom)) return CUT_PREVIEW_ZOOM.INITIAL;
        return Math.min(
            CUT_PREVIEW_ZOOM.MAX,
            Math.max(CUT_PREVIEW_ZOOM.MIN, Math.round(zoom * 100) / 100)
        );
    }

    function normalizeCutPreviewPan(pan) {
        if (!pan || typeof pan !== "object") return { x: 0, y: 0 };
        const x = Number(pan.x);
        const y = Number(pan.y);
        return {
            x: Number.isFinite(x) ? x : 0,
            y: Number.isFinite(y) ? y : 0,
        };
    }

    function clampCutPreviewPan(pan, zoom, viewportSize) {
        const normalized = normalizeCutPreviewPan(pan);
        const scale = clampCutPreviewZoom(zoom);
        const width = Math.max(0, Number(viewportSize && viewportSize.width) || 0);
        const height = Math.max(0, Number(viewportSize && viewportSize.height) || 0);
        if (!(width > 0 && height > 0) || scale <= 1.0001) {
            return { x: 0, y: 0 };
        }
        const maxX = (width * (scale - 1)) / 2;
        const maxY = (height * (scale - 1)) / 2;
        return {
            x: Math.max(-maxX, Math.min(maxX, normalized.x)),
            y: Math.max(-maxY, Math.min(maxY, normalized.y)),
        };
    }

    function scaleCutPreviewPan(pan, fromZoom, toZoom) {
        const current = normalizeCutPreviewPan(pan);
        const from = Number(fromZoom);
        const to = Number(toZoom);
        if (!(from > 0) || !Number.isFinite(to)) return current;
        const ratio = to / from;
        return {
            x: current.x * ratio,
            y: current.y * ratio,
        };
    }

    function cutPreviewSheetSignature(program) {
        const drawing = program || {};
        return [
            Number(drawing.sheet_width_mm) || 0,
            Number(drawing.sheet_length_mm) || 0,
        ].join("x");
    }

    function geometryFingerprint(points, closed) {
        const parts = (Array.isArray(points) ? points : []).map(point => (
            `${Number(point[0]).toFixed(3)},${Number(point[1]).toFixed(3)}`
        ));
        return `${closed ? "C" : "O"}:${parts.join(";")}`;
    }

    function buildExecutionPathId(operationKey, pathKey, sequence, fingerprint, groupIndex) {
        const base = [
            String(operationKey || ""),
            String(pathKey || ""),
            String(sequence == null ? 0 : sequence),
            String(fingerprint || ""),
        ].join("::");
        return groupIndex > 0 ? `${base}::g${groupIndex}` : base;
    }

    function collectCutExecutions(program) {
        const executions = [];
        let execution = 0;
        const operations = Array.isArray(program && program.operations) ? program.operations : [];
        operations.forEach(operation => {
            const operationKey = String(operation.operation_key || "");
            if (!PROGRAM_COLORS[operationKey]) return;
            (operation.toolpaths || []).forEach(path => {
                let current = null;
                const sequence = path.sequence == null ? 0 : Number(path.sequence);
                (path.motions || []).forEach(motion => {
                    const kind = String(motion && motion.kind || "");
                    if (kind === "plunge") {
                        execution += 1;
                        const start = [Number(motion.x_mm), Number(motion.y_mm)];
                        current = {
                            execution,
                            path_key: String(path.path_key || ""),
                            operation_key: operationKey,
                            sequence,
                            piece_instance_id: String(path.piece_instance_id || ""),
                            piece_label: String(path.piece_label || ""),
                            preset_name: String(path.preset_name || ""),
                            closed: Boolean(path.closed),
                            depth_mm: motion.depth_mm == null || motion.depth_mm === ""
                                ? null
                                : Number(motion.depth_mm),
                            ready: Boolean(path.ready),
                            issues: Array.isArray(path.issues) ? path.issues.slice() : [],
                            points: [start],
                            start,
                            end: start,
                        };
                        executions.push(current);
                        return;
                    }
                    if (kind === "cut" && current) {
                        const point = [Number(motion.x_mm), Number(motion.y_mm)];
                        current.points.push(point);
                        current.end = point;
                        return;
                    }
                    if (kind === "retract" || kind === "travel") {
                        current = null;
                    }
                });
            });
        });
        return executions;
    }

    function previewEndPoint(points, start, end, closed) {
        const finish = Array.isArray(end) ? end : (Array.isArray(points) ? points[points.length - 1] : start);
        if (!Array.isArray(start) || !Array.isArray(finish) || !Array.isArray(points) || points.length < 2) return finish || start;
        const dx = Number(finish[0]) - Number(start[0]);
        const dy = Number(finish[1]) - Number(start[1]);
        if (!closed || Math.hypot(dx, dy) > 0.5) return finish;
        const previous = points[points.length - 2];
        const incomingX = Number(finish[0]) - Number(previous[0]);
        const incomingY = Number(finish[1]) - Number(previous[1]);
        const length = Math.hypot(incomingX, incomingY) || 1;
        return [Number(finish[0]) - (incomingX / length) * 4, Number(finish[1]) - (incomingY / length) * 4];
    }

    function highlightVectorSelection(body, state) {
        const preview = body && body.querySelector("[data-sheet-preview]");
        if (!preview) return;
        const selected = new Set((state.vectorSelection || []).map(String));
        preview.querySelectorAll("[data-execution-path]").forEach(node => {
            node.classList.toggle("is-vector-picked", selected.has(node.getAttribute("data-execution-path") || ""));
        });
    }

    function collectPhysicalPaths(program) {
        const paths = [];
        let pathNumber = 0;
        let passOrdinal = 0;
        const operations = Array.isArray(program && program.operations) ? program.operations : [];
        operations.forEach(operation => {
            const operationKey = String(operation.operation_key || "");
            if (!PROGRAM_COLORS[operationKey]) return;
            (operation.toolpaths || []).forEach(toolpath => {
                const sequence = toolpath.sequence == null ? 0 : Number(toolpath.sequence);
                const pathKey = String(toolpath.path_key || "");
                const closed = Boolean(toolpath.closed);
                const passes = [];
                let current = null;
                (toolpath.motions || []).forEach(motion => {
                    const kind = String(motion && motion.kind || "");
                    if (kind === "plunge") {
                        passOrdinal += 1;
                        const start = [Number(motion.x_mm), Number(motion.y_mm)];
                        current = {
                            execution: passOrdinal,
                            depth_mm: motion.depth_mm == null || motion.depth_mm === ""
                                ? null
                                : Number(motion.depth_mm),
                            points: [start],
                            start,
                            end: start,
                        };
                        passes.push(current);
                        return;
                    }
                    if (kind === "cut" && current) {
                        const point = [Number(motion.x_mm), Number(motion.y_mm)];
                        current.points.push(point);
                        current.end = point;
                        return;
                    }
                    if (kind === "retract" || kind === "travel") {
                        current = null;
                    }
                });
                if (!passes.length && Array.isArray(toolpath.points) && toolpath.points.length >= 2) {
                    const points = toolpath.points.map(point => [Number(point[0]), Number(point[1])]);
                    passes.push({
                        execution: 1,
                        depth_mm: null,
                        points,
                        start: points[0],
                        end: points[points.length - 1],
                    });
                }
                if (!passes.length) return;
                const groups = [];
                passes.forEach(pass => {
                    const fingerprint = geometryFingerprint(pass.points, closed);
                    const last = groups[groups.length - 1];
                    if (last && last.fingerprint === fingerprint) {
                        last.passes.push(pass);
                        return;
                    }
                    groups.push({
                        fingerprint,
                        passes: [pass],
                        points: pass.points,
                        start: pass.start,
                        end: pass.end,
                    });
                });
                groups.forEach((group, groupIndex) => {
                    pathNumber += 1;
                    const executionPathId = buildExecutionPathId(
                        operationKey,
                        pathKey,
                        sequence,
                        group.fingerprint,
                        groups.length > 1 ? groupIndex : 0
                    );
                    const pieceLabel = String(toolpath.piece_label || "");
                    const pieceInstanceId = String(toolpath.piece_instance_id || "");
                    const sheetPerimeter = pathKey === SHEET_PERIMETER_PATH_KEY;
                    paths.push({
                        execution_path_id: executionPathId,
                        path_number: pathNumber,
                        path_key: pathKey,
                        operation_key: operationKey,
                        sequence,
                        piece_instance_id: pieceInstanceId,
                        piece_label: pieceLabel,
                        is_sheet_perimeter: sheetPerimeter,
                        shared: !sheetPerimeter && !pieceLabel && !pieceInstanceId,
                        closed,
                        ready: Boolean(toolpath.ready),
                        issues: Array.isArray(toolpath.issues) ? toolpath.issues.slice() : [],
                        preset_name: String(toolpath.preset_name || ""),
                        geometry_fingerprint: group.fingerprint,
                        points: group.points,
                        start: group.start,
                        end: group.end,
                        pass_count: group.passes.length,
                        passes: group.passes.map((pass, index) => ({
                            pass_index: index + 1,
                            execution: pass.execution,
                            depth_mm: pass.depth_mm,
                        })),
                    });
                });
            });
        });
        return paths;
    }

    function findPhysicalPath(program, executionPathId) {
        const selected = String(executionPathId || "");
        if (!selected) return null;
        return collectPhysicalPaths(program).find(item => item.execution_path_id === selected) || null;
    }

    function cutExecutionArrowSegment(points, closed) {
        if (!Array.isArray(points) || points.length < 2) return null;
        if (closed && points.length >= 3) {
            const index = Math.max(1, Math.min(points.length - 2, Math.floor((points.length - 1) * 0.35)));
            return { from: points[index], to: points[index + 1] };
        }
        return { from: points[points.length - 2], to: points[points.length - 1] };
    }

    function groupCutExecutionLabels(executionsOrPaths) {
        const groups = [];
        const indexByKey = new Map();
        (Array.isArray(executionsOrPaths) ? executionsOrPaths : []).forEach(item => {
            if (!item || !Array.isArray(item.start) || item.start.length < 2) return;
            const key = item.execution_path_id
                || [
                    item.operation_key || "",
                    item.path_key || "",
                    Number(item.start[0]).toFixed(2),
                    Number(item.start[1]).toFixed(2),
                ].join("|");
            if (indexByKey.has(key)) {
                groups[indexByKey.get(key)].items.push(item);
                return;
            }
            indexByKey.set(key, groups.length);
            groups.push({
                execution_path_id: String(item.execution_path_id || ""),
                path_number: item.path_number || null,
                operation_key: String(item.operation_key || ""),
                path_key: String(item.path_key || ""),
                x: Number(item.start[0]),
                y: Number(item.start[1]),
                items: [item],
                passes: Array.isArray(item.passes) ? item.passes.slice() : [],
            });
        });
        return groups;
    }

    function previewLegendMarkup(program, hiddenOperations) {
        const hidden = new Set(hiddenOperations || []);
        const present = new Set();
        (Array.isArray(program && program.operations) ? program.operations : []).forEach(operation => {
            const key = String(operation.operation_key || "");
            if (PROGRAM_COLORS[key]) present.add(key);
        });
        const order = [
            "liner",
            "recessed_handle_cutout",
            "back_groove",
            "sheet_perimeter",
            "cut_path",
        ];
        const items = order.filter(key => present.has(key)).map(key => {
            const checked = hidden.has(key) ? "" : " checked";
            return `<label class="dco-cnc-cut-preview__legend-item">
                <input type="checkbox" data-cut-layer="${escapeHtml(key)}"${checked}>
                <span class="dco-cnc-cut-preview__swatch" style="background:${PROGRAM_COLORS[key]}"></span>
                <span>${escapeHtml(operationLabel(key))}</span>
            </label>`;
        }).join("");
        if (!items) return "";
        return `<div class="dco-cnc-cut-preview__legend" role="group" aria-label="${escapeHtml(translate("Operation colors"))}">${items}</div>`;
    }

    function cutPreviewLayoutStyle(width, length, options = {}) {
        const pageLayout = String(options.layout || "") === "page";
        if (pageLayout) {
            return `inline-size:100%;min-inline-size:min(100%,${SHEET_PAGE_PREVIEW_MIN_WIDTH_PX}px);aspect-ratio:${width} / ${length}`;
        }
        return `max-inline-size:${SHEET_PREVIEW_MAX_WIDTH_PX}px;aspect-ratio:${width} / ${length}`;
    }

    function cutPathPreviewMarkup(program, options = {}) {
        const drawing = program || {};
        const placement = options.placement || null;
        const sheetWidth = Number(drawing.sheet_width_mm);
        const sheetLength = Number(drawing.sheet_length_mm);
        const offsetX = placement ? Number(placement.offset_left_cm || 0) * 10 : 0;
        const offsetY = placement ? Number(placement.offset_bottom_cm || 0) * 10 : 0;
        const width = placement && Number(placement.machine_width_cm) > 0
            ? Number(placement.machine_width_cm) * 10
            : sheetWidth;
        const length = placement && Number(placement.machine_length_cm) > 0
            ? Number(placement.machine_length_cm) * 10
            : sheetLength;
        const selectedExecutionPathId = String(options.selectedExecutionPathId || "");
        const selectedVectorIds = new Set((options.selectedVectorIds || []).map(String));
        const markerScope = String(options.markerScope || nextCutPreviewScope());
        const hiddenOperations = Array.isArray(options.hiddenOperations) ? options.hiddenOperations : [];
        const hidden = new Set(hiddenOperations.map(String));
        const allPaths = collectPhysicalPaths(drawing);
        const physicalPaths = allPaths.filter(item => !hidden.has(String(item.operation_key || "")));
        const geometryReady = Boolean(drawing.geometry_ready || drawing.ready);
        const notes = [];
        if (!geometryReady) {
            notes.push(translate("Cutting path preview is incomplete."));
        }
        const issueMessages = [];
        (Array.isArray(drawing.issues) ? drawing.issues : []).forEach(issue => {
            if (!issue) return;
            const message = issue.message || issue.code;
            if (message) issueMessages.push(String(message));
        });
        allPaths.forEach(item => {
            (item.issues || []).forEach(code => {
                if (code) issueMessages.push(String(code));
            });
        });
        const uniqueIssues = Array.from(new Set(issueMessages)).slice(0, 6);
        uniqueIssues.forEach(message => notes.push(message));
        const pageLayout = String(options.layout || "") === "page";
        const initialZoom = clampCutPreviewZoom(
            options.zoom == null ? CUT_PREVIEW_ZOOM.INITIAL : options.zoom
        );
        const zoomControls = pageLayout
            ? `<div class="dco-cnc-cut-preview__zoom" role="group" aria-label="${escapeHtml(translate("Preview zoom"))}">
                <button type="button" class="btn btn-default btn-xs" data-cut-zoom="out" title="${escapeHtml(translate("Zoom out"))}">−</button>
                <button type="button" class="btn btn-default btn-xs" data-cut-zoom="reset" title="${escapeHtml(translate("Fit to view"))}">${escapeHtml(translate("Fit"))}</button>
                <button type="button" class="btn btn-default btn-xs" data-cut-zoom="in" title="${escapeHtml(translate("Zoom in"))}">+</button>
               </div>`
            : "";
        const legend = pageLayout ? previewLegendMarkup(drawing, hiddenOperations) : "";
        const emptyMessage = translate("No machining paths are available for this sheet preview.");

        const boardSurface = (svgInner, labelInner) => {
            const stage = `<div class="dco-cnc-cut-preview__stage" data-cut-stage style="--cut-zoom:${initialZoom}">
                <svg class="dco-cnc-cut-preview__svg" viewBox="0 0 ${width} ${length}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHtml(svgInner.aria || emptyMessage)}">
                    ${svgInner.body || ""}
                </svg>
                ${labelInner || ""}
            </div>`;
            if (!pageLayout) return stage;
            return `<div class="dco-cnc-cut-preview__viewport" data-cut-viewport style="${cutPreviewLayoutStyle(width, length, options)}" role="region" aria-label="${escapeHtml(translate("Board preview viewport"))}">
                ${stage}
            </div>`;
        };
        const previewShellStyle = pageLayout
            ? "inline-size:100%;min-inline-size:0;"
            : cutPreviewLayoutStyle(width, length, options);

        if (!(width > 0 && length > 0)) {
            return `<div class="dco-cnc-cut-preview" role="status" data-marker-scope="${escapeHtml(markerScope)}">
                ${legend}
                <p class="dco-operational-files__note">${escapeHtml(emptyMessage)}</p>
            </div>`;
        }

        if (!physicalPaths.length) {
            return `<div class="dco-cnc-cut-preview" role="status" data-marker-scope="${escapeHtml(markerScope)}" style="${previewShellStyle}">
                ${legend}
                ${zoomControls}
                ${boardSurface({
                    aria: emptyMessage,
                    body: `<rect class="dco-cnc-cut-preview__frame" x="0" y="0" width="${width}" height="${length}" fill="none"/>`,
                })}
                <p class="dco-operational-files__note">${escapeHtml(emptyMessage)}</p>
                ${notes.map(note => `<p class="dco-cnc-program__error" role="status">${escapeHtml(note)}</p>`).join("")}
            </div>`;
        }

        const markers = physicalPaths.map(item => {
            const markerId = `${markerScope}-arrow-${item.path_number}`;
            const color = PROGRAM_COLORS[item.operation_key] || "#333";
            return `<marker id="${escapeHtml(markerId)}" markerUnits="strokeWidth" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="4" markerHeight="4" orient="auto">
                <path d="M0 0 L8 4 L0 8 Z" fill="${color}"/>
            </marker>`;
        }).join("");
        const strokes = physicalPaths.map(item => {
            const inspected = selectedExecutionPathId && item.execution_path_id === selectedExecutionPathId;
            const picked = selectedVectorIds.has(String(item.path_key || ""));
            const selected = `${inspected ? " is-cnc-path-selected" : ""}${picked ? " is-vector-picked" : ""}`;
            const markerId = `${markerScope}-arrow-${item.path_number}`;
            const color = PROGRAM_COLORS[item.operation_key] || "#333";
            const points = item.points.map(point => `${Number(point[0])},${Number(point[1])}`).join(" ");
            const start = item.start;
            const arrow = cutExecutionArrowSegment(item.points, item.closed);
            const depths = item.passes
                .map(pass => (pass.depth_mm == null ? "" : String(pass.depth_mm)))
                .filter(Boolean)
                .join(",");
            const arrowLine = arrow
                ? `<polyline class="dco-cnc-cut-preview__arrow" data-path-number="${item.path_number}" data-execution-path-id="${escapeHtml(item.execution_path_id)}" data-execution-path="${escapeHtml(item.path_key)}" data-operation-key="${escapeHtml(item.operation_key)}" points="${Number(arrow.from[0])},${Number(arrow.from[1])} ${Number(arrow.to[0])},${Number(arrow.to[1])}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke" marker-end="url(#${escapeHtml(markerId)})"/>`
                : "";
            const endPoint = previewEndPoint(item.points, item.start, item.end, item.closed);
            const ends = inspected
                ? `<circle class="dco-cnc-cut-preview__origin" cx="${Number(start[0])}" cy="${Number(start[1])}" r="3.2" fill="#16A34A"/>
                    <circle class="dco-cnc-cut-preview__finish" cx="${Number(endPoint[0])}" cy="${Number(endPoint[1])}" r="3.2" fill="#DC2626"/>`
                : "";
            return `<g class="dco-cnc-cut-preview__execution${selected}" data-path-number="${item.path_number}" data-execution-path-id="${escapeHtml(item.execution_path_id)}" data-execution-path="${escapeHtml(item.path_key)}" data-operation-key="${escapeHtml(item.operation_key)}" data-pass-count="${item.pass_count}" data-depth-mm="${escapeHtml(depths)}">
                <polyline class="dco-cnc-cut-preview__hit" points="${points}" fill="none" stroke="transparent" stroke-width="8" vector-effect="non-scaling-stroke"/>
                <polyline class="dco-cnc-cut-preview__path" points="${points}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
                ${arrowLine}
                ${ends}
            </g>`;
        }).join("");
        const labels = physicalPaths.map(item => {
            const selected = selectedExecutionPathId && item.execution_path_id === selectedExecutionPathId
                ? " is-cnc-path-selected"
                : "";
            const title = item.passes.map(pass => (
                pass.depth_mm == null
                    ? translate("Pass {0}", [pass.pass_index])
                    : translate("Pass {0}: Depth {1} mm", [pass.pass_index, pass.depth_mm])
            )).join(" · ");
            const labelX = Number(item.start[0]) + offsetX;
            const labelY = Number(item.start[1]) + offsetY;
            const left = width > 0 ? (labelX / width) * 100 : 0;
            const top = length > 0 ? ((length - labelY) / length) * 100 : 0;
            return `<button type="button" class="dco-cnc-cut-preview__badge${selected}" data-path-number="${item.path_number}" data-execution-path-id="${escapeHtml(item.execution_path_id)}" data-execution-path="${escapeHtml(item.path_key)}" data-operation-key="${escapeHtml(item.operation_key)}" data-label-x="${escapeHtml(item.start[0])}" data-label-y="${escapeHtml(item.start[1])}" style="left:${left}%;top:${top}%;" title="${escapeHtml(title)}"><span>${escapeHtml(item.path_number)}</span></button>`;
        }).join("");
        const sheetW = sheetWidth > 0 ? sheetWidth : width;
        const sheetL = sheetLength > 0 ? sheetLength : length;
        const leftDim = placement && offsetX > 0
            ? `<div class="dco-cnc-cut-preview__dim dco-cnc-cut-preview__dim--left" style="inset-inline-start:0;inset-block-end:${(offsetY / length) * 50}%;inline-size:${(offsetX / width) * 100}%;">${escapeHtml(String(Number(placement.offset_left_cm || 0)))} ${escapeHtml(translate("cm"))}</div>`
            : "";
        const bottomDim = placement && offsetY > 0
            ? `<div class="dco-cnc-cut-preview__dim dco-cnc-cut-preview__dim--bottom" style="inset-inline-start:${(offsetX / width) * 50}%;inset-block-end:0;inline-size:${(sheetW / width) * 100}%;block-size:${(offsetY / length) * 100}%;">${escapeHtml(String(Number(placement.offset_bottom_cm || 0)))} ${escapeHtml(translate("cm"))}</div>`
            : "";
        const machineFrame = placement
            ? `<rect class="dco-cnc-cut-preview__machine" x="0" y="0" width="${width}" height="${length}" fill="#f3f4f6" stroke="#111827" stroke-width="1.5"/>
                <rect class="dco-cnc-cut-preview__void" x="0" y="0" width="${Math.max(0, offsetX)}" height="${length}" fill="#e5e7eb"/>
                <rect class="dco-cnc-cut-preview__void" x="0" y="0" width="${width}" height="${Math.max(0, offsetY)}" fill="#e5e7eb"/>
                <rect class="dco-cnc-cut-preview__void" x="${offsetX + sheetW}" y="0" width="${Math.max(0, width - offsetX - sheetW)}" height="${length}" fill="#e5e7eb"/>
                <rect class="dco-cnc-cut-preview__void" x="0" y="${offsetY + sheetL}" width="${width}" height="${Math.max(0, length - offsetY - sheetL)}" fill="#e5e7eb"/>
                <rect class="dco-cnc-cut-preview__sheet" x="${offsetX}" y="${offsetY}" width="${sheetW}" height="${sheetL}" fill="#fff7ed" stroke="#9a3412" stroke-width="1"/>
                <circle class="dco-cnc-cut-preview__origin" cx="0" cy="0" r="3" fill="#111827"/>`
            : `<rect class="dco-cnc-cut-preview__frame" x="0" y="0" width="${width}" height="${length}" fill="none"/>`;
        const sheetGroup = `<g transform="translate(${offsetX},${offsetY})">${strokes}</g>`;
        const placementNote = placement
            ? `<p class="dco-operational-files__note" data-placement-caption>${escapeHtml(translate("Machine origin at bottom-left. Left offset {0} cm · Bottom offset {1} cm.", [
                Number(placement.offset_left_cm || 0),
                Number(placement.offset_bottom_cm || 0),
            ]))}</p>`
            : "";

        return `<div class="dco-cnc-cut-preview" data-marker-scope="${escapeHtml(markerScope)}" style="${previewShellStyle}">
            ${legend}
            ${zoomControls}
            ${boardSurface({
                aria: translate("Machining preview"),
                body: `<defs>${markers}</defs>
                    <g transform="translate(0,${length}) scale(1,-1)">
                        ${machineFrame}
                        ${sheetGroup}
                    </g>`,
            }, `<div class="dco-cnc-cut-preview__labels" aria-hidden="false">${labels}</div>
                <div class="dco-cnc-cut-preview__dims" aria-hidden="true">${leftDim}${bottomDim}</div>`)}
            ${placementNote}
            ${notes.map(note => `<p class="dco-cnc-program__error" role="status">${escapeHtml(note)}</p>`).join("")}
        </div>`;
    }

    function bindCutPreviewChrome(host, options = {}) {
        if (!host || typeof host.querySelector !== "function") return;
        const stage = host.querySelector("[data-cut-stage]");
        const viewport = host.querySelector("[data-cut-viewport]");
        if (!stage || !viewport) return;
        let zoom = clampCutPreviewZoom(
            options.initialZoom == null
                ? stage.style.getPropertyValue("--cut-zoom")
                : options.initialZoom
        );
        let pan = normalizeCutPreviewPan(
            options.initialPan == null ? host.__cutPreviewPan : options.initialPan
        );
        const outButton = host.querySelector('[data-cut-zoom="out"]');
        const inButton = host.querySelector('[data-cut-zoom="in"]');

        function viewportSize() {
            if (typeof viewport.getBoundingClientRect !== "function") {
                return {
                    width: Number(viewport.clientWidth) || 0,
                    height: Number(viewport.clientHeight) || 0,
                };
            }
            const rect = viewport.getBoundingClientRect();
            return { width: rect.width || 0, height: rect.height || 0 };
        }

        const apply = () => {
            zoom = clampCutPreviewZoom(zoom);
            pan = clampCutPreviewPan(pan, zoom, viewportSize());
            host.__cutPreviewZoom = zoom;
            host.__cutPreviewPan = { x: pan.x, y: pan.y };
            stage.style.setProperty("--cut-zoom", String(zoom));
            stage.style.setProperty("--cut-pan-x", `${pan.x}px`);
            stage.style.setProperty("--cut-pan-y", `${pan.y}px`);
            stage.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
            viewport.classList.toggle("is-panning-enabled", zoom > 1.0001);
            if (outButton) outButton.disabled = zoom <= CUT_PREVIEW_ZOOM.MIN + 0.0001;
            if (inButton) inButton.disabled = zoom >= CUT_PREVIEW_ZOOM.MAX - 0.0001;
        };

        host.querySelectorAll("[data-cut-zoom]").forEach(button => {
            button.addEventListener("click", () => {
                const action = button.getAttribute("data-cut-zoom");
                const previousZoom = zoom;
                if (action === "in") zoom = clampCutPreviewZoom(zoom + CUT_PREVIEW_ZOOM.STEP);
                else if (action === "out") zoom = clampCutPreviewZoom(zoom - CUT_PREVIEW_ZOOM.STEP);
                else {
                    zoom = CUT_PREVIEW_ZOOM.INITIAL;
                    pan = { x: 0, y: 0 };
                    apply();
                    return;
                }
                pan = scaleCutPreviewPan(pan, previousZoom, zoom);
                apply();
            });
        });
        host.querySelectorAll("[data-cut-layer]").forEach(input => {
            input.addEventListener("change", () => {
                const hidden = [];
                host.querySelectorAll("[data-cut-layer]").forEach(box => {
                    if (!box.checked) hidden.push(box.getAttribute("data-cut-layer"));
                });
                host.__cutPreviewHidden = hidden;
                paintCutPathPreview(host, {
                    status: "ready",
                    program: host.__cutPreviewProgram || {},
                    selectedExecutionPathId: host.__cutPreviewSelectedExecutionPathId || "",
                    selectedPathKey: host.__cutPreviewSelectedPathKey || "",
                    layout: host.__cutPreviewLayout || "",
                    zoom: host.__cutPreviewZoom,
                    pan: host.__cutPreviewPan,
                    hiddenOperations: hidden,
                });
            });
        });

        let dragging = false;
        let startX = 0;
        let startY = 0;
        let originPan = { x: 0, y: 0 };
        const interactiveSelector = "button, input, label, a, [data-execution-path-id], .dco-cnc-cut-preview__badge";

        viewport.addEventListener("pointerdown", event => {
            if (event.shiftKey) return;
            if (event.button != null && event.button !== 0) return;
            if (zoom <= 1.0001) return;
            const target = event.target;
            if (target && typeof target.closest === "function" && target.closest(interactiveSelector)) {
                return;
            }
            dragging = true;
            startX = Number(event.clientX) || 0;
            startY = Number(event.clientY) || 0;
            originPan = { x: pan.x, y: pan.y };
            viewport.classList.add("is-panning");
            if (typeof viewport.setPointerCapture === "function" && event.pointerId != null) {
                try {
                    viewport.setPointerCapture(event.pointerId);
                } catch (_error) {
                    // Ignore capture failures in non-DOM test hosts.
                }
            }
            if (typeof event.preventDefault === "function") event.preventDefault();
        });
        viewport.addEventListener("pointermove", event => {
            if (!dragging) return;
            const dx = (Number(event.clientX) || 0) - startX;
            const dy = (Number(event.clientY) || 0) - startY;
            pan = { x: originPan.x + dx, y: originPan.y + dy };
            apply();
        });
        const endPan = () => {
            if (!dragging) return;
            dragging = false;
            viewport.classList.remove("is-panning");
            apply();
        };
        viewport.addEventListener("pointerup", endPan);
        viewport.addEventListener("pointercancel", endPan);
        viewport.addEventListener("lostpointercapture", endPan);

        apply();
    }

    function collectMarkerIdsFromMarkup(markup) {
        const ids = [];
        const pattern = /\bid="([^"]+-arrow-\d+)"/g;
        let match = pattern.exec(markup);
        while (match) {
            ids.push(match[1]);
            match = pattern.exec(markup);
        }
        return ids;
    }

    function paintCutPathPreview(host, payload = {}) {
        if (!host) return;
        const status = String(payload.status || "ready");
        if (status === "loading") {
            host.innerHTML = `<div class="dco-cnc-cut-preview" role="status"><p class="dco-operational-files__note">${escapeHtml(translate("Loading cutting paths..."))}</p></div>`;
            return;
        }
        if (status === "error") {
            host.innerHTML = `<div class="dco-cnc-cut-preview" role="alert"><p class="dco-cnc-program__error">${escapeHtml(translate("Cutting paths could not be loaded."))}</p></div>`;
            return;
        }
        const markerScope = nextCutPreviewScope();
        const layout = payload.layout
            || (typeof host.getAttribute === "function" ? host.getAttribute("data-preview-layout") : "")
            || host.__cutPreviewLayout
            || "";
        const hiddenOperations = Array.isArray(payload.hiddenOperations)
            ? payload.hiddenOperations
            : (Array.isArray(host.__cutPreviewHidden) ? host.__cutPreviewHidden : []);
        const zoom = clampCutPreviewZoom(
            payload.zoom == null
                ? (host.__cutPreviewZoom == null ? CUT_PREVIEW_ZOOM.INITIAL : host.__cutPreviewZoom)
                : payload.zoom
        );
        const nextProgram = payload.program || {};
        const previousSignature = host.__cutPreviewSheetSignature || "";
        const nextSignature = cutPreviewSheetSignature(nextProgram);
        let pan = payload.pan == null
            ? normalizeCutPreviewPan(host.__cutPreviewPan)
            : normalizeCutPreviewPan(payload.pan);
        if (previousSignature && previousSignature !== nextSignature && payload.pan == null) {
            pan = { x: 0, y: 0 };
        }
        host.__cutPreviewProgram = nextProgram;
        host.__cutPreviewSheetSignature = nextSignature;
        host.__cutPreviewSelectedExecutionPathId = payload.selectedExecutionPathId || "";
        host.__cutPreviewSelectedPathKey = payload.selectedPathKey || "";
        host.__cutPreviewVectorIds = payload.selectedVectorIds || host.__cutPreviewVectorIds || [];
        host.__cutPreviewLayout = layout;
        host.__cutPreviewHidden = hiddenOperations;
        host.__cutPreviewZoom = zoom;
        host.__cutPreviewPan = pan;
        const placement = payload.placement
            || host.__cutPreviewPlacement
            || null;
        host.__cutPreviewPlacement = placement;
        host.innerHTML = cutPathPreviewMarkup(nextProgram, {
            selectedExecutionPathId: payload.selectedExecutionPathId || "",
            selectedPathKey: payload.selectedPathKey || "",
            selectedVectorIds: payload.selectedVectorIds || host.__cutPreviewVectorIds || [],
            markerScope,
            layout,
            zoom,
            hiddenOperations,
            placement,
        });
        bindCutPreviewChrome(host, { initialZoom: zoom, initialPan: pan });
    }

    function highlightCutPreview(preview, state) {
        if (!preview) return;
        const selected = state && state.selectedExecutionPathId ? String(state.selectedExecutionPathId) : "";
        preview.querySelectorAll("[data-execution-path-id]").forEach(node => {
            node.classList.toggle(
                "is-cnc-path-selected",
                Boolean(selected) && node.getAttribute("data-execution-path-id") === selected
            );
        });
    }

    function physicalPathRowMarkup(path, workspace, state, canPrepare, ownsSettings) {
        const custom = Boolean(state.overrides[path.path_key]);
        const editing = canPrepare && ownsSettings && (custom || Boolean(state.customizing && state.customizing[path.path_key]));
        const selected = effectivePreset(state, {
            path_key: path.path_key,
            operation_key: path.operation_key,
        });
        const piece = pathDisplayLabel(path);
        const passDetail = path.pass_count > 1
            ? `<span class="dco-operational-path__passes">${escapeHtml(translate("{0} passes", [path.pass_count]))}</span>`
            : "";
        const control = !ownsSettings
            ? `<span class="dco-operational-path__effective">${escapeHtml(presetLabel(workspace, selected))}</span>`
            : (editing
                ? `<div class="dco-operational-path__preset">
                    <div data-path-preset-host="${escapeHtml(path.path_key)}"></div>
                    <button type="button" class="btn btn-default btn-xs" data-reset-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Use the layer preset"))}</button>
                   </div>`
                : `<span class="dco-operational-path__effective">${escapeHtml(presetLabel(workspace, selected))}</span>
                    ${canPrepare ? `<button type="button" class="btn btn-default btn-xs" data-customize-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Customize this path"))}</button>` : ""}`);
        const selectedClass = path.execution_path_id === state.selectedExecutionPathId ? " is-selected" : "";
        return `<div class="dco-operational-path${custom ? " is-custom" : ""}${selectedClass}${isSheetPerimeterPath(path) ? " is-sheet-perimeter" : ""}" data-path-key="${escapeHtml(path.path_key)}" data-execution-path-id="${escapeHtml(path.execution_path_id)}" data-path-number="${path.path_number}" data-path-operation="${escapeHtml(path.operation_key)}" data-custom="${custom ? "1" : "0"}" data-sheet-perimeter="${isSheetPerimeterPath(path) ? "1" : "0"}">
            <button type="button" class="btn btn-link btn-xs dco-operational-path__pick" data-select-execution="${escapeHtml(path.execution_path_id)}" data-select-path="${escapeHtml(path.path_key)}">
                <span class="dco-operational-path__number">${escapeHtml(path.path_number)}</span>
                ${escapeHtml(piece)}
            </button>
            <span class="dco-operational-path__badge">${escapeHtml(translate(custom ? "Custom preset" : "Uses the layer preset"))}</span>
            ${passDetail}
            ${control}
        </div>`;
    }

    function syncPhysicalPathList(body, workspace, sheet, state, program, dialog) {
        if (!body) return;
        const physical = collectPhysicalPaths(program);
        state.program = program;
        if (state.selectedExecutionPathId
            && !physical.some(item => item.execution_path_id === state.selectedExecutionPathId)) {
            state.selectedExecutionPathId = "";
        }
        if (state.selectedExecutionPathId) {
            const selected = physical.find(item => item.execution_path_id === state.selectedExecutionPathId);
            if (selected) state.selectedPathKey = selected.path_key;
        } else if (state.selectedPathKey
            && !physical.some(item => item.path_key === state.selectedPathKey)) {
            state.selectedPathKey = "";
        }
        const owned = new Set();
        (state.order || []).forEach(key => {
            const article = body.querySelector(`.dco-operational-layer[data-layer="${key}"]`);
            if (!article) return;
            const container = article.querySelector(".dco-operational-layer__paths");
            if (!container) return;
            const rows = physical.filter(item => item.operation_key === key);
            if (key === "cut_path") syncCutPathSequence(state);
            container.innerHTML = rows.map(path => {
                const ownsSettings = Boolean(path.path_key) && !owned.has(path.path_key);
                if (path.path_key) owned.add(path.path_key);
                return physicalPathRowMarkup(path, workspace, state, Boolean(workspace.can_prepare), ownsSettings);
            }).join("");
            const count = article.querySelector(".dco-operational-layer__head span");
            if (count) count.textContent = translate("{0} paths", [rows.length]);
            if (key === "cut_path") {
                paintPerimeterJoinControls(article, state, Boolean(workspace.can_prepare));
            }
        });
        const selection = body.querySelector(".dco-operational-sheet__selection");
        if (selection) selection.textContent = selectionText(workspace, sheet, state);
        if (dialog) {
            disposePresetLinks(dialog);
            mountPresetControls(
                dialog._almdinaSheet && dialog._almdinaSheet.frm,
                dialog,
                workspace,
                sheet,
                state,
                dialog._almdinaSheet && dialog._almdinaSheet.board
            );
        }
    }

    function expandLayerForPath(body, state, operationKey) {
        if (!body || !operationKey) return;
        state.expanded[operationKey] = true;
        const article = body.querySelector(`.dco-operational-layer[data-layer="${operationKey}"]`);
        const pathsPanel = article && article.querySelector(".dco-operational-layer__paths");
        if (pathsPanel) pathsPanel.hidden = false;
        const toggle = body.querySelector(`[data-toggle-layer="${operationKey}"]`);
        if (toggle) {
            toggle.setAttribute("aria-expanded", "true");
            toggle.textContent = translate("Hide paths");
        }
    }

    function applyExecutionSelection(body, workspace, sheet, state, executionPathId) {
        const physical = findPhysicalPath(state.program, executionPathId);
        if (!physical) return false;
        state.selectedExecutionPathId = physical.execution_path_id;
        state.selectedPathKey = physical.path_key;
        expandLayerForPath(body, state, physical.operation_key);
        const selection = body.querySelector(".dco-operational-sheet__selection");
        if (selection) selection.textContent = selectionText(workspace, sheet, state);
        const preview = body.querySelector("[data-sheet-preview]");
        highlightCutPreview(preview, state);
        body.querySelectorAll(".dco-operational-path").forEach(row => {
            row.classList.toggle(
                "is-selected",
                row.getAttribute("data-execution-path-id") === state.selectedExecutionPathId
            );
        });
        const row = Array.from(body.querySelectorAll(".dco-operational-path[data-execution-path-id]"))
            .find(node => node.getAttribute("data-execution-path-id") === physical.execution_path_id);
        if (row && typeof row.scrollIntoView === "function") {
            row.scrollIntoView({ block: "nearest" });
        }
        return true;
    }

    function requestSheetProgramPreview(frm, dialog, workspace, sheet, state) {
        const body = dialogRoot(dialog);
        const preview = body && body.querySelector("[data-sheet-preview]");
        if (!preview) return;
        paintCutPathPreview(preview, { status: "loading" });
        const request = (dialog._cncProgramPreviewRequest || 0) + 1;
        dialog._cncProgramPreviewRequest = request;
        if (!window.frappe || typeof frappe.call !== "function") {
            paintCutPathPreview(preview, { status: "error" });
            return;
        }
        frappe.call({
            method: `${METHOD}.get_cnc_sheet_program`,
            args: sheetGenerateArgs(frm, workspace, sheet, state),
            callback(response) {
                if (dialog._cncProgramPreviewRequest !== request) return;
                const liveBody = dialogRoot(dialog);
                const livePreview = liveBody && liveBody.querySelector("[data-sheet-preview]");
                if (!livePreview) return;
                const program = (response && response.message) || {};
                if (dialog._almdinaSheet) dialog._almdinaSheet.program = program;
                state.program = program;
                const physical = collectPhysicalPaths(program);
                if (state.selectedExecutionPathId
                    && !physical.some(item => item.execution_path_id === state.selectedExecutionPathId)) {
                    state.selectedExecutionPathId = "";
                    state.selectedPathKey = "";
                } else if (state.selectedExecutionPathId) {
                    const selected = physical.find(item => item.execution_path_id === state.selectedExecutionPathId);
                    if (selected) state.selectedPathKey = selected.path_key;
                }
                syncPhysicalPathList(liveBody, workspace, sheet, state, program, dialog);
                paintCutPathPreview(livePreview, {
                    status: "ready",
                    program,
                    selectedExecutionPathId: state.selectedExecutionPathId || "",
                    selectedVectorIds: state.vectorSelection || [],
                    layout: livePreview.getAttribute("data-preview-layout") || livePreview.__cutPreviewLayout || "",
                    zoom: livePreview.__cutPreviewZoom,
                    pan: livePreview.__cutPreviewPan,
                    hiddenOperations: livePreview.__cutPreviewHidden,
                    placement: placementPreviewPayload(workspace, state),
                });
            },
            error() {
                if (dialog._cncProgramPreviewRequest !== request) return;
                const liveBody = dialogRoot(dialog);
                const livePreview = liveBody && liveBody.querySelector("[data-sheet-preview]");
                if (!livePreview) return;
                paintCutPathPreview(livePreview, { status: "error" });
            },
        });
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
                    perimeter_join_mode: args.perimeter_join_mode,
                    cut_path_sequence: args.cut_path_sequence,
                    perimeter_cut_early_confirmed: args.perimeter_cut_early_confirmed,
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
            if (normalizePerimeterJoinMode(context.state.perimeterJoinMode) === "connected"
                && sheetPerimeterPrecedesMilling(context.state.order)
                && !context.state.perimeterEarlyConfirmed) {
                frappe.msgprint(translate("Cutting the sheet perimeter before milling may let pieces move after they separate from the board."));
                return;
            }
            const conflict = toolConflict(context.workspace, context.sheet, context.state);
            if (conflict) {
                frappe.msgprint(translate(CONFLICT_MESSAGES[conflict]));
                return;
            }
            if (!reportPlacementValidation(
                validateSheetPlacementFits(context.workspace, context.state, { requireMachine: true })
            )) {
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
                            if (dialog.mode === "page") {
                                syncPageToolbar(dialog, live.workspace, saved, live.state);
                            } else {
                                syncSheetFooter(dialog, live.workspace, saved, live.state);
                            }
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
        SHEET_PERIMETER_PATH_KEY,
        SHEET_PERIMETER_OPERATION_KEY,
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        normalizePerimeterJoinMode,
        deriveCutPathSequenceFromOrder,
        normalizeCutPathSequence,
        perimeterIsEarly,
        sheetPerimeterPrecedesMilling,
        ensureSheetPerimeterOperation,
        removeSheetPerimeterOperation,
        syncCutPathSequence,
        applyPerimeterJoinMode,
        paintPerimeterJoinControls,
        pathDisplayLabel,
        isSheetPerimeterPath,
        perimeterJoinControlsMarkup,
        sheetGenerateArgs,
        applyLayerPreset,
        restoreLayerPreset,
        restoreFactoryPresets,
        customizePath,
        clearPathPreset,
        fitBoard,
        paintLayerMeta,
        dialogScrollHost,
        preserveDialogScroll,
        SHEET_PREVIEW_MAX_WIDTH_PX,
        SHEET_PAGE_ROUTE,
        CUT_PREVIEW_ZOOM,
        PROGRAM_COLORS,
        collectCutExecutions,
        collectPhysicalPaths,
        findPhysicalPath,
        geometryFingerprint,
        buildExecutionPathId,
        cutPathPreviewMarkup,
        paintCutPathPreview,
        highlightCutPreview,
        applyExecutionSelection,
        syncPhysicalPathList,
        groupCutExecutionLabels,
        cutExecutionArrowSegment,
        collectMarkerIdsFromMarkup,
        nextCutPreviewScope,
        clampCutPreviewZoom,
        normalizeCutPreviewPan,
        clampCutPreviewPan,
        scaleCutPreviewPan,
        sheetSettingsUrl,
        openSheetSettingsTab,
        mountSheetSettingsPage,
        findCncMachine,
        placementPreviewPayload,
        validateSheetPlacementFits,
    });
})();
