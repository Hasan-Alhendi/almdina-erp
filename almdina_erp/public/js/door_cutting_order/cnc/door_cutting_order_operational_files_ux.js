(() => {
    "use strict";

    const ASSET_REVISION = 1;
    if (window.AlmdinaOperationalFilesUX?.assetRevision === ASSET_REVISION) return;

    const METHOD = "almdina_erp.almdina_erp.services.cnc_operational_file_service";
    const SHEET_PAGE_ROUTE = "cnc-sheet-settings";
    const SHEET_PREVIEW_MAX_WIDTH_PX = 390;
    const SHEET_PAGE_PREVIEW_MIN_WIDTH_PX = 520;
    const CUT_PREVIEW_ZOOM = Object.freeze({
        MIN: 1,
        INITIAL: 1,
        MAX: 16,
        STEP: 0.5,
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
        "Not Configured": "Not Configured",
        "Settings Saved": "Settings Saved",
    });
    const INTERNAL_OPERATIONS = Object.freeze([
        "liner",
        "recessed_handle_cutout",
        "back_groove",
    ]);
    const CONFLICT_MESSAGES = Object.freeze({
        number: "One board file must keep the same physical tool number.",
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
        return translate(STATUS_LABELS[status] || status || "Not Configured");
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
        state.reportPerimeterIssues = true;
        state.perimeterJoinMode = normalizePerimeterJoinMode(mode);
        if (state.perimeterJoinMode === "connected") {
            ensureSheetPerimeterOperation(state);
        } else {
            removeSheetPerimeterOperation(state);
        }
        state.expanded.cut_path = true;
        state.perimeterGeometryReady = null;
        if (state.perimeterJoinMode !== "connected" && window.AlmdinaArtcamMachining
            && typeof window.AlmdinaArtcamMachining.clearEditingPerimeterSource === "function") {
            window.AlmdinaArtcamMachining.clearEditingPerimeterSource(state);
        }
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
        syncArtcamPerimeterSource(dialog, workspace, sheet, state);
        requestSheetProgramPreview(frm, dialog, workspace, sheet, state);
    }

    function syncArtcamPerimeterSource(dialog, workspace, sheet, state) {
        const artcam = window.AlmdinaArtcamMachining;
        const body = dialogRoot(dialog);
        if (!artcam || typeof artcam.syncPerimeterSource !== "function" || !body) return;
        artcam.syncPerimeterSource(body, { workspace, sheet, state });
    }

    function acceptPerimeterPreview(state, request, currentRequest, modeAtRequest, program) {
        if (!state || Number(request) !== Number(currentRequest)) return false;
        if (normalizePerimeterJoinMode(state.perimeterJoinMode) !== normalizePerimeterJoinMode(modeAtRequest)) {
            return false;
        }
        state.perimeterGeometryReady = normalizePerimeterJoinMode(modeAtRequest) === "connected"
            && perimeterIssues(program || {}).length === 0;
        if (state.perimeterGeometryReady === false && window.AlmdinaArtcamMachining
            && typeof window.AlmdinaArtcamMachining.clearEditingPerimeterSource === "function") {
            window.AlmdinaArtcamMachining.clearEditingPerimeterSource(state);
        }
        return true;
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
            sheetStops: sheet.sheet_stops && sheet.sheet_stops.width_stop_side ? {
                width_stop_side: String(sheet.sheet_stops.width_stop_side || ""),
                width_stop_cm: Number(sheet.sheet_stops.width_stop_cm),
                length_stop_side: String(sheet.sheet_stops.length_stop_side || ""),
                length_stop_cm: Number(sheet.sheet_stops.length_stop_cm),
            } : null,
            stopDraft: { width: null, length: null },
            settingsRevision: Number(sheet.settings_revision || 0),
            sheetWidthCm: sheet.sheet_width_cm == null ? null : Number(sheet.sheet_width_cm),
            sheetLengthCm: sheet.sheet_length_cm == null ? null : Number(sheet.sheet_length_cm),
            expanded: {},
            customizing: {},
            selectedPathKey: "",
            selectedExecutionPathId: "",
            selectedPathIdentity: null,
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
            sheetStops: state.sheetStops || null,
            stopDraft: state.stopDraft || null,
        });
    }

    function beginSheetMutation(state) {
        if (!state || state.sheetMutationInFlight) return 0;
        const request = Number(state.sheetMutationRequest || 0) + 1;
        state.sheetMutationRequest = request;
        state.sheetMutationInFlight = true;
        return request;
    }

    function sheetMutationIsCurrent(state, request) {
        return Boolean(state && request && Number(state.sheetMutationRequest) === Number(request));
    }

    function finishSheetMutation(state, request) {
        if (!sheetMutationIsCurrent(state, request)) return false;
        state.sheetMutationInFlight = false;
        return true;
    }

    function findCncMachine(workspace, name) {
        const token = String(name || "").trim();
        return (workspace.cnc_machines || []).find(item => String(item.name || "") === token) || null;
    }

    const WIDTH_STOP_SIDES = Object.freeze({ "Left Side": "left", "Right Side": "right" });
    const LENGTH_STOP_SIDES = Object.freeze({ "Bottom Side": "bottom", "Top Side": "top" });

    function activeStopValues(machine) {
        if (!machine) return null;
        const position = String(machine.work_zero_position || "Bottom Left");
        if (position === "Center") return { position, error: "work_zero_center_retired" };
        if (!["Bottom Left", "Bottom Right", "Top Left", "Top Right"].includes(position)) {
            return { position, error: "work_zero_invalid" };
        }
        const horizontalSide = WIDTH_STOP_SIDES[String(machine.width_stop_side || "")];
        const verticalSide = LENGTH_STOP_SIDES[String(machine.length_stop_side || "")];
        if (!horizontalSide || !verticalSide) {
            return { position, error: "cnc_machine_stop_sides_required" };
        }
        return { position, horizontalSide, verticalSide };
    }

    function defaultSheetStops(machine, sheetWidthCm, sheetLengthCm) {
        if (!machine) return null;
        const width = Number(machine.width_cm);
        const length = Number(machine.length_cm);
        const sheetW = Number(sheetWidthCm);
        const sheetL = Number(sheetLengthCm);
        if (!(width > 0) || !(length > 0) || !(sheetW > 0) || !(sheetL > 0)) return null;
        const widthGap = width - sheetW;
        const lengthGap = length - sheetL;
        if (widthGap < -1e-6) return { error: "sheet_exceeds_machine_width" };
        if (lengthGap < -1e-6) return { error: "sheet_exceeds_machine_length" };
        return {
            width_stop_side: String(machine.width_stop_side || ""),
            width_stop_cm: widthGap > 0 ? widthGap : 0,
            length_stop_side: String(machine.length_stop_side || ""),
            length_stop_cm: lengthGap > 0 ? lengthGap : 0,
        };
    }

    function activeSheetStops(workspace, state) {
        const machine = findCncMachine(workspace, state && state.cncMachine);
        const defaults = defaultSheetStops(machine, state && state.sheetWidthCm, state && state.sheetLengthCm);
        const saved = state && state.sheetStops;
        if (!saved) return defaults;
        return {
            width_stop_side: String(saved.width_stop_side || (defaults && defaults.width_stop_side) || ""),
            width_stop_cm: saved.width_stop_cm,
            length_stop_side: String(saved.length_stop_side || (defaults && defaults.length_stop_side) || ""),
            length_stop_cm: saved.length_stop_cm,
            error: defaults && defaults.error,
        };
    }

    function parseStopCm(raw, gap) {
        const text = String(raw == null ? "" : raw).trim();
        if (!/^[+]?(?:\d+\.?\d*|\.\d+)$/.test(text)) return { ok: false };
        const number = Number(text);
        if (!Number.isFinite(number) || number < 0 || number - Number(gap) > 1e-6) return { ok: false };
        return { ok: true, value: number };
    }

    function physicalSheetOffsetCm(machine, sheetWidthCm, sheetLengthCm, stops) {
        const machineStops = activeStopValues(machine);
        if (!machineStops || machineStops.error) {
            return machineStops && machineStops.error ? { error: machineStops.error, position: machineStops.position } : null;
        }
        const width = Number(machine.width_cm);
        const length = Number(machine.length_cm);
        const sheetW = Number(sheetWidthCm);
        const sheetL = Number(sheetLengthCm);
        if (!(width > 0) || !(length > 0) || !(sheetW > 0) || !(sheetL > 0)) return null;
        const horizontalCm = width - sheetW;
        const verticalCm = length - sheetL;
        if (horizontalCm < -1e-6) return { error: "sheet_exceeds_machine_width", position: machineStops.position };
        if (verticalCm < -1e-6) return { error: "sheet_exceeds_machine_length", position: machineStops.position };
        const widthGap = horizontalCm > 0 ? horizontalCm : 0;
        const lengthGap = verticalCm > 0 ? verticalCm : 0;
        const chosen = stops || {
            width_stop_side: machine.width_stop_side,
            width_stop_cm: widthGap,
            length_stop_side: machine.length_stop_side,
            length_stop_cm: lengthGap,
        };
        const horizontalSide = WIDTH_STOP_SIDES[String(chosen.width_stop_side || "")];
        const verticalSide = LENGTH_STOP_SIDES[String(chosen.length_stop_side || "")];
        if (!horizontalSide || !verticalSide) {
            return { error: "cnc_machine_stop_sides_required", position: machineStops.position };
        }
        const widthStop = Number(chosen.width_stop_cm);
        const lengthStop = Number(chosen.length_stop_cm);
        if (!Number.isFinite(widthStop) || widthStop < 0 || widthStop - widthGap > 1e-6) {
            return { error: "width_stop_invalid", position: machineStops.position };
        }
        if (!Number.isFinite(lengthStop) || lengthStop < 0 || lengthStop - lengthGap > 1e-6) {
            return { error: "length_stop_invalid", position: machineStops.position };
        }
        const offsetLeft = horizontalSide === "left" ? widthStop : widthGap - widthStop;
        const offsetBottom = verticalSide === "bottom" ? lengthStop : lengthGap - lengthStop;
        return {
            position: machineStops.position,
            offset_left_cm: offsetLeft,
            offset_bottom_cm: offsetBottom,
            horizontalCm: widthStop,
            verticalCm: lengthStop,
            horizontalSide,
            verticalSide,
            right_clearance_cm: widthGap - offsetLeft,
            top_clearance_cm: lengthGap - offsetBottom,
        };
    }

    function placementPreviewPayload(workspace, state) {
        const machine = findCncMachine(workspace, state.cncMachine);
        const origin = physicalSheetOffsetCm(
            machine,
            state.sheetWidthCm,
            state.sheetLengthCm,
            activeSheetStops(workspace, state)
        );
        if (!machine || !origin || origin.error) return null;
        return {
            machine_name: String(machine.machine_name || machine.name || ""),
            machine_width_cm: Number(machine.width_cm || 0),
            machine_length_cm: Number(machine.length_cm || 0),
            offset_left_cm: origin.offset_left_cm,
            offset_bottom_cm: origin.offset_bottom_cm,
            work_zero_position: origin.position,
            sheet_width_cm: state.sheetWidthCm == null ? null : Number(state.sheetWidthCm),
            sheet_length_cm: state.sheetLengthCm == null ? null : Number(state.sheetLengthCm),
            horizontal_stop_cm: origin.horizontalCm,
            vertical_stop_cm: origin.verticalCm,
            horizontal_stop_side: origin.horizontalSide,
            vertical_stop_side: origin.verticalSide,
            right_clearance_cm: origin.right_clearance_cm,
            top_clearance_cm: origin.top_clearance_cm,
        };
    }

    const PLACEMENT_MESSAGES = Object.freeze({
        offset_left_invalid: "The left stop must be zero or a positive number of centimetres.",
        offset_right_invalid: "The right stop must be zero or a positive number of centimetres.",
        offset_bottom_invalid: "The bottom stop must be zero or a positive number of centimetres.",
        offset_top_invalid: "The top stop must be zero or a positive number of centimetres.",
        sheet_exceeds_machine_width: "The board is larger than the machine width. NC cannot be generated.",
        sheet_exceeds_machine_length: "The board is larger than the machine length. NC cannot be generated.",
        cnc_machine_stops_unconfigured: "Set the two stops for this work zero on the CNC machine. A stop from another edge is not copied across.",
        cnc_machine_stop_sides_required: "Choose the width stop side and the length stop side on the CNC machine before generating a new file.",
        width_stop_invalid: "The width stop must be a number from 0 cm up to the gap between the machine and the full sheet.",
        length_stop_invalid: "The length stop must be a number from 0 cm up to the gap between the machine and the full sheet.",
        work_zero_center_retired: "This CNC machine still uses Center as its work zero. Choose Bottom Left, Bottom Right, Top Left, or Top Right before generating a new file.",
        work_zero_invalid: "The selected work zero is not supported.",
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
        const draft = state.stopDraft || {};
        if (draft.width != null) {
            return {
                ok: false,
                code: "width_stop_invalid",
                message: translate(PLACEMENT_MESSAGES.width_stop_invalid),
            };
        }
        if (draft.length != null) {
            return {
                ok: false,
                code: "length_stop_invalid",
                message: translate(PLACEMENT_MESSAGES.length_stop_invalid),
            };
        }
        const sheetW = Number(state.sheetWidthCm);
        const sheetL = Number(state.sheetLengthCm);
        const origin = physicalSheetOffsetCm(machine, sheetW, sheetL, activeSheetStops(workspace, state));
        if (!origin || origin.error) {
            const code = (origin && origin.error) || "cnc_machine_stop_sides_required";
            return {
                ok: false,
                code,
                message: translate(PLACEMENT_MESSAGES[code] || PLACEMENT_MESSAGES.placement_incomplete),
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

    function formatPlacementCm(value) {
        const number = Math.round(Number(value) * 1000) / 1000;
        if (!Number.isFinite(number)) return "";
        return String(number);
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
            : `<p class="dco-operational-sheet__note" data-machine-dims>${escapeHtml(translate("Select a machine to place the sheet with that machine's stops."))}</p>`;
        const fit = validateSheetPlacementFits(workspace, state, { requireMachine: Boolean(selected) });
        const warning = `<p class="dco-operational-sheet__warning" role="alert" data-placement-warning${fit.ok ? " hidden" : ""}>${fit.ok ? "" : escapeHtml(fit.message)}</p>`;
        return `<div class="dco-operational-sheet__placement" data-sheet-placement>
            <label class="dco-operational-sheet__choice">${escapeHtml(translate("CNC machine"))}
                <select class="form-control" data-cnc-machine${disabled}>${options.join("")}</select>
            </label>
            ${dims}
            ${stopFieldsMarkup(workspace, state, canPrepare)}
            ${warning}
        </div>`;
    }

    function stopOptionMarkup(pairs, selected) {
        return pairs.map(([value, label]) => (
            `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(translate(label))}</option>`
        )).join("");
    }

    function stopFieldsMarkup(workspace, state, canPrepare) {
        const machine = findCncMachine(workspace, state.cncMachine);
        const disabled = canPrepare ? "" : " disabled";
        const stops = activeSheetStops(workspace, state) || {};
        const hidden = machine ? "" : " hidden";
        return `<div class="dco-operational-sheet__stops" data-sheet-stops${hidden}>
            <div class="dco-operational-sheet__stop-row">
                <label>${escapeHtml(translate("Width Stop Side"))}
                    <select class="form-control" data-width-stop-side${disabled}>${stopOptionMarkup([
                        ["Left Side", "Left Side"],
                        ["Right Side", "Right Side"],
                    ], String(stops.width_stop_side || ""))}</select>
                </label>
                <label>${escapeHtml(translate("Width Stop (cm)"))}
                    <input class="form-control" data-width-stop-cm type="text" inputmode="decimal" autocomplete="off" value="${escapeHtml(formatPlacementCm(stops.width_stop_cm))}"${disabled}>
                </label>
            </div>
            <div class="dco-operational-sheet__stop-row">
                <label>${escapeHtml(translate("Length Stop Side"))}
                    <select class="form-control" data-length-stop-side${disabled}>${stopOptionMarkup([
                        ["Top Side", "Top Side"],
                        ["Bottom Side", "Bottom Side"],
                    ], String(stops.length_stop_side || ""))}</select>
                </label>
                <label>${escapeHtml(translate("Length Stop (cm)"))}
                    <input class="form-control" data-length-stop-cm type="text" inputmode="decimal" autocomplete="off" value="${escapeHtml(formatPlacementCm(stops.length_stop_cm))}"${disabled}>
                </label>
            </div>
            <button type="button" class="btn btn-default btn-xs" data-reset-sheet-stops${disabled}>${escapeHtml(translate("Restore default stops"))}</button>
        </div>`;
    }

    function writeStopControls(body, stops) {
        const root = body && body.querySelector("[data-sheet-stops]");
        if (!root || !stops || stops.error) return;
        const widthSide = root.querySelector("[data-width-stop-side]");
        const lengthSide = root.querySelector("[data-length-stop-side]");
        const widthCm = root.querySelector("[data-width-stop-cm]");
        const lengthCm = root.querySelector("[data-length-stop-cm]");
        if (widthSide) widthSide.value = String(stops.width_stop_side || "");
        if (lengthSide) lengthSide.value = String(stops.length_stop_side || "");
        if (widthCm) widthCm.value = formatPlacementCm(stops.width_stop_cm);
        if (lengthCm) lengthCm.value = formatPlacementCm(stops.length_stop_cm);
    }

    function refreshPlacementPreview(body, workspace, state, sheet) {
        const fit = validateSheetPlacementFits(workspace, state, {
            requireMachine: Boolean(state.cncMachine),
        });
        const warning = body.querySelector("[data-placement-warning]");
        if (warning) {
            warning.hidden = Boolean(fit.ok);
            warning.textContent = fit.ok ? "" : fit.message;
        }
        const preview = body.querySelector("[data-sheet-preview]");
        if (preview && preview.__cutPreviewProgram && fit.ok) {
            paintCutPathPreview(preview, {
                status: "ready",
                program: preview.__cutPreviewProgram,
                sheet: sheet || null,
                state,
                selectedExecutionPathId: state.selectedExecutionPathId || "",
                selectedVectorIds: state.vectorSelection || [],
                layout: preview.getAttribute("data-preview-layout") || preview.__cutPreviewLayout || "",
                zoom: preview.__cutPreviewZoom,
                pan: preview.__cutPreviewPan,
                hiddenOperations: preview.__cutPreviewHidden,
                placement: placementPreviewPayload(workspace, state),
            });
        }
        const stops = body.querySelector("[data-sheet-stops]");
        if (stops) stops.hidden = !findCncMachine(workspace, state.cncMachine);
    }

    function applyStopControl(state, workspace, target) {
        const machine = findCncMachine(workspace, state.cncMachine);
        const defaults = defaultSheetStops(machine, state.sheetWidthCm, state.sheetLengthCm);
        if (!defaults || defaults.error) return false;
        const current = activeSheetStops(workspace, state) || defaults;
        state.stopDraft = state.stopDraft || { width: null, length: null };
        if (target.hasAttribute("data-width-stop-side")) {
            state.sheetStops = Object.assign({}, current, { width_stop_side: String(target.value || "") });
            return true;
        }
        if (target.hasAttribute("data-length-stop-side")) {
            state.sheetStops = Object.assign({}, current, { length_stop_side: String(target.value || "") });
            return true;
        }
        if (target.hasAttribute("data-width-stop-cm")) {
            const parsed = parseStopCm(target.value, defaults && defaults.width_stop_cm);
            if (!parsed.ok) {
                state.stopDraft.width = String(target.value == null ? "" : target.value);
                return false;
            }
            state.stopDraft.width = null;
            state.sheetStops = Object.assign({}, current, { width_stop_cm: parsed.value });
            return true;
        }
        if (target.hasAttribute("data-length-stop-cm")) {
            const parsed = parseStopCm(target.value, defaults && defaults.length_stop_cm);
            if (!parsed.ok) {
                state.stopDraft.length = String(target.value == null ? "" : target.value);
                return false;
            }
            state.stopDraft.length = null;
            state.sheetStops = Object.assign({}, current, { length_stop_cm: parsed.value });
            return true;
        }
        return false;
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
        if (numbers.size > 1) return "number";
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
            boards.set(Number(sheet.sheet_no), card);
        });
        return boards;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    // Same breakpoints and board caps as AlmdinaPlanBoardPresenter.layoutBoardGallery.
    const OPERATIONAL_BOARD_GAP_PX = 8;
    const OPERATIONAL_BOARD_CARD_CHROME_PX = 12;
    const OPERATIONAL_BOARD_VIEWPORT_HEIGHT_RATIO = 0.68;

    function operationalBoardColumns(width) {
        const available = Number(width || 0);
        const viewport = Number((typeof window !== "undefined" && window.innerWidth) || available || 0);
        if (viewport <= 600 || available < 520) return 1;
        if (viewport <= 1024 || available < 760) return 2;
        if (available >= 1180) return 4;
        return 3;
    }

    function layoutOperationalGallery(surface) {
        if (!surface || typeof surface.querySelector !== "function") return;
        const gallery = surface.querySelector(":scope > .dco-board-gallery");
        if (!gallery) return;
        const rootWidth = surface.clientWidth || gallery.clientWidth || 0;
        const columns = operationalBoardColumns(rootWidth);
        surface.dataset.boardColumns = String(columns);
        const availableColumnWidth = rootWidth > 0
            ? Math.max(150, (rootWidth - OPERATIONAL_BOARD_GAP_PX * Math.max(0, columns - 1)) / columns - OPERATIONAL_BOARD_CARD_CHROME_PX)
            : 300;
        const viewportHeight = Math.max(480, (typeof window !== "undefined" && window.innerHeight) || 720);
        gallery.querySelectorAll(":scope > .dco-sheet-card").forEach(card => {
            const board = card.querySelector(":scope > .dco-sheet-board");
            if (!board || !board.style) return;
            const width = parseFloat(board.style.width) || 0;
            const height = parseFloat(board.style.height) || 0;
            const aspect = width > 0 && height > 0 ? width / height : 0.5;
            board.style.setProperty("--dco-board-aspect", `${aspect} / 1`);
            if (columns === 1) {
                board.style.removeProperty("--dco-board-screen-max-width");
                return;
            }
            const viewportWidthCap = viewportHeight * OPERATIONAL_BOARD_VIEWPORT_HEIGHT_RATIO * aspect;
            const widthCap = Math.max(145, Math.min(availableColumnWidth, viewportWidthCap));
            board.style.setProperty("--dco-board-screen-max-width", `${Math.round(widthCap)}px`);
        });
    }

    function bindOperationalGallery(root) {
        const surface = root && typeof root.querySelector === "function"
            ? root.querySelector(".dco-operational-files")
            : null;
        if (!surface) return;
        const layout = () => layoutOperationalGallery(surface);
        layout();
        if (root.__operationalGalleryObserver && typeof root.__operationalGalleryObserver.disconnect === "function") {
            root.__operationalGalleryObserver.disconnect();
        }
        if (typeof ResizeObserver !== "function") return;
        const observer = new ResizeObserver(() => layout());
        observer.observe(surface);
        root.__operationalGalleryObserver = observer;
    }

    function approvedBoardCount(layout) {
        const planSheets = Array.isArray(layout && layout.sheets) ? layout.sheets : [];
        return planSheets.filter(sheet => String((sheet && sheet.resource_kind) || "FULL_BOARD").toUpperCase() === "FULL_BOARD").length;
    }

    function attachSheetTools(card, sheet) {
        const title = card && typeof card.querySelector === "function"
            ? card.querySelector(":scope > .dco-sheet-title")
            : null;
        const host = title || card;
        if (!host || host.querySelector(".dco-operational-files__sheet-tools")) return;
        const tools = document.createElement("span");
        tools.className = "dco-operational-files__sheet-tools";
        const status = sheet && sheet.status
            ? `<span class="dco-operational-files__status" data-status="${escapeHtml(sheet.status)}">${escapeHtml(statusLabel(sheet.status))}</span>`
            : "";
        tools.innerHTML = `${status}${sheetCardActions(sheet)}`;
        host.appendChild(tools);
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

    function decodeBase64Bytes(value) {
        const binary = atob(String(value || ""));
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            bytes[index] = binary.charCodeAt(index);
        }
        return bytes;
    }

    function downloadGeneratedNc(filename, contentB64) {
        const name = String(filename || "").trim();
        const encoded = String(contentB64 || "").trim();
        if (!name || !encoded || !document.body) return false;
        const blob = new Blob([decodeBase64Bytes(encoded)], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = name;
        document.body.appendChild(anchor);
        anchor.click();
        setTimeout(() => {
            if (anchor.parentNode) anchor.parentNode.removeChild(anchor);
            URL.revokeObjectURL(url);
        }, 500);
        return true;
    }

    function sheetCardActions(sheet) {
        const ready = Boolean(sheet && sheet.nc_file_current);
        const readyMark = ready
            ? `<span class="dco-operational-files__nc-ready" role="img" title="${escapeHtml(translate("The operational file has been generated."))}" aria-label="${escapeHtml(translate("The operational file has been generated."))}">✓</span>`
            : "";
        return `${readyMark}<button type="button" class="dco-board-focus-trigger dco-operational-files__open" data-sheet-no="${escapeHtml(sheet.sheet_no)}" aria-label="${escapeHtml(translate("Open sheet settings"))}" title="${escapeHtml(translate("Open sheet settings"))}"><span aria-hidden="true">⤢</span></button>`;
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
        const boardCount = approvedBoardCount(workspace.layout);
        const direction = uiDirection();
        root.innerHTML = `<div class="dco-operational-files" dir="${direction}">
            <header class="dco-operational-files__header">
                <p class="dco-operational-files__meta">${escapeHtml(translate("Approved plan"))}: ${escapeHtml(workspace.cutting_plan || "")} · ${escapeHtml(translate("Plan revision"))} ${escapeHtml(workspace.plan_revision || "")} · ${sourceLabel(workspace.plan_source_type)}</p>
                <span class="dco-plan-context-chip is-boards" role="status" aria-label="${escapeHtml(translate("{0} sheets", [boardCount]))}"><span class="dco-plan-context-boards-value" style="direction:ltr;">${escapeHtml(boardCount)}</span><span class="dco-plan-context-boards-label">${escapeHtml(translate("Sheets"))}</span></span>
            </header>
            <div class="alert alert-warning dco-operational-files__banner" role="status">${escapeHtml(approval)}</div>
            <div class="dco-board-gallery"></div>
        </div>`;
        const gallery = root.querySelector(".dco-board-gallery");
        const cards = boardsBySheet(frm, workspace.layout);
        const operationalBySheet = new Map(sheets.map(sheet => [Number(sheet.sheet_no), sheet]));
        const planSheets = Array.isArray(workspace.layout && workspace.layout.sheets) ? workspace.layout.sheets : [];
        planSheets.forEach(planSheet => {
            const sheetNo = Number(planSheet && planSheet.sheet_no);
            const card = cards.get(sheetNo);
            if (!card || !gallery) return;
            attachSheetTools(card, operationalBySheet.get(sheetNo) || { sheet_no: sheetNo });
            gallery.appendChild(card);
        });
        if (gallery && !gallery.childElementCount) {
            sheets.forEach(sheet => {
                const fallback = document.createElement("article");
                fallback.className = "dco-sheet-card";
                fallback.innerHTML = `<p class="dco-operational-files__note">${escapeHtml(translate("Board preview is not available."))}</p>`;
                attachSheetTools(fallback, sheet);
                gallery.appendChild(fallback);
            });
        }
        bindOperationalGallery(root);
        root.querySelectorAll(".dco-operational-files__open").forEach(button => {
            button.addEventListener("click", () => {
                const sheetNo = Number(button.getAttribute("data-sheet-no"));
                if (!frm || !frm.doc || !frm.doc.name || !sheetNo) return;
                openSheetSettingsTab(frm.doc.name, sheetNo);
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
        if (name === "up-line" || name === "down-line") {
            const arrow = name === "up-line" ? "↑" : "↓";
            return `<span class="dco-operational-order__arrow" aria-hidden="true">${arrow}</span>`;
        }
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            const icon = frappe.utils.icon(name, "sm");
            if (icon && !String(icon).includes("es-icon-missing")) return icon;
        }
        if (name === "eye") return "◉";
        if (name === "eye-off") return "◌";
        if (name === "trash-2") return "✕";
        return "↓";
    }

    function exportControlsMarkup(workspace, sheet) {
        const canPrepare = Boolean(workspace && workspace.can_prepare);
        const control = generateNcControlState({
            canPrepare,
            canGenerateNc: Boolean(workspace && workspace.can_generate_nc),
            sheet,
        });
        const downloadLabel = translate("Download cutting file");
        const downloadTitle = control.disabled ? (control.reason || "") : downloadLabel;
        return `<div class="dco-operational-sheet__export" data-cnc-export-bar>
            <div class="dco-operational-sheet__export-actions almdina-ui">
                <button type="button" class="btn alm-btn-primary btn-sm" data-cnc-save-sheet${canPrepare ? "" : " disabled"}>${escapeHtml(translate("Save sheet settings"))}</button>
                <button type="button" class="btn btn-default btn-sm" data-cnc-generate-nc data-cnc-page-action="generate"${control.disabled ? " disabled" : ""} title="${escapeHtml(downloadTitle)}">${escapeHtml(downloadLabel)}</button>
            </div>
        </div>`;
    }

    function dialogMarkup(workspace, sheet, state, options) {
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
                : (row.selection && row.selection.kind === "selected_vectors")
                    ? "Selected Vectors"
                    : ((row.selection && row.selection.operation_key) || "");
            const profile = (((sheet.machining || {}).profiles) || []).find(item => item.profile_id === row.profile_id);
            const profileName = (profile && profile.name) || row.profile_id || "";
            const hidden = Boolean(state.hiddenAssociations && state.hiddenAssociations[row.association_id]);
            return `<li class="dco-operational-order__item" data-association-id="${escapeHtml(row.association_id)}">
            <button type="button" class="dco-operational-order__label" data-edit-association="${escapeHtml(row.association_id)}">
                <strong>${escapeHtml(row.name || row.association_id)}</strong>
                <small>${escapeHtml(source)}${profileName ? ` · ${escapeHtml(profileName)}` : ""}</small>
            </button>
            <span class="dco-operational-order__moves">
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-move="earlier" title="${escapeHtml(translate("Move earlier"))}" aria-label="${escapeHtml(translate("Move earlier"))}"${earlierDisabled}>${orderMoveIcon("up-line")}</button>
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-move="later" title="${escapeHtml(translate("Move later"))}" aria-label="${escapeHtml(translate("Move later"))}"${laterDisabled}>${orderMoveIcon("down-line")}</button>
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-association-visibility="${escapeHtml(row.association_id)}" aria-pressed="${hidden ? "true" : "false"}" title="${escapeHtml(translate(hidden ? "Show paths" : "Hide paths"))}" aria-label="${escapeHtml(translate(hidden ? "Show paths" : "Hide paths"))}">${orderMoveIcon(hidden ? "eye-off" : "eye")}</button>
                <button type="button" class="btn btn-default btn-xs dco-operational-order__move" data-delete-association="${escapeHtml(row.association_id)}" title="${escapeHtml(translate("Delete"))}" aria-label="${escapeHtml(translate("Delete"))}"${disabled}>${orderMoveIcon("trash-2")}</button>
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
                state.hiddenAssociations = {};
                state.sections = null;
            }
            state._artcamSheetNo = Number(sheet && sheet.sheet_no);
        }
        if (!state.sections) state.sections = { placement: false, perimeter: false, associations: true, order: true };
        const associationEditor = window.AlmdinaArtcamMachining
            ? window.AlmdinaArtcamMachining.markup(workspace, sheet, state) : "";
        const associationBody = canPrepare ? associationEditor
            : `<fieldset class="dco-artcam-readonly" disabled>${associationEditor}</fieldset>`;
        const exportBar = options && options.exportBar ? exportControlsMarkup(workspace, sheet) : "";
        const pageChrome = Boolean(exportBar);
        const previewToolbar = pageChrome
            ? `<div class="dco-cnc-preview-toolbar" dir="ltr">
                <div class="dco-cnc-sheet-page__actions" data-cnc-page-actions></div>
            </div>`
            : "";
        const previewStatus = pageChrome
            ? ""
            : `<p class="dco-operational-sheet__selection" role="status">${escapeHtml(selectionText(workspace, sheet, state))}</p>
                    <p class="dco-operational-files__status" data-sheet-nc-status="${escapeHtml(sheet.status || "")}">${escapeHtml(statusLabel(sheet.status))}</p>`;
        const section = (id, title, body) => (
            `<section class="dco-sheet-group" data-sheet-section="${id}">
                <h4 class="dco-sheet-group__title">${escapeHtml(translate(title))}</h4>
                <div class="dco-sheet-group__body">${body}</div>
            </section>`
        );
        return `<div class="dco-operational-sheet">
            <div class="dco-operational-sheet__body">
                <div class="dco-operational-sheet__preview">
                    ${previewToolbar}
                    <div data-sheet-preview></div>
                    ${previewStatus}
                    <div class="dco-path-menu" data-path-menu hidden role="menu">
                        <button type="button" data-reverse-path role="menuitem">${escapeHtml(translate("Reverse Direction"))}</button>
                    </div>
                </div>
                <div class="dco-operational-sheet__settings">
                    ${pageChrome ? sheetIdentityMarkup(workspace, sheet) : ""}
                    ${section("placement", "Machine placement", placementControlsMarkup(workspace, state, canPrepare))}
                    ${section("perimeter", "Sheet Perimeter", perimeterJoinControlsMarkup(state, canPrepare))}
                    ${section("associations", "Vector Associations", associationBody)}
                    ${section("order", "Operation order", `<ol class="dco-operational-order">${orderItems || `<li class="dco-artcam-note">${escapeHtml(translate("Associations appear here after they are saved."))}</li>`}</ol>${warning}`)}
                    ${exportBar}
                </div>
            </div>
        </div>`;
    }

    function sheetHasTrustedNcSettings(sheet) {
        if (!sheet) return false;
        if (sheet.persisted || sheet.operational_file) return true;
        const status = String(sheet.status || "");
        return status === "Settings Saved" || status === "Generated";
    }

    function generateNcControlState({ canPrepare, canGenerateNc, sheet }) {
        const generateAllowed = canGenerateNc == null
            ? Boolean(canPrepare)
            : Boolean(canGenerateNc);
        if (!generateAllowed) {
            return {
                disabled: true,
                reason: translate("You can review these settings. Preparing operational files is not available for your current permissions."),
            };
        }
        if (!canPrepare && !sheetHasTrustedNcSettings(sheet)) {
            return {
                disabled: true,
                reason: translate("Save the sheet settings before generating the NC file."),
            };
        }
        return {
            disabled: false,
            reason: translate("Generate NC file"),
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
                if (target.hasAttribute("data-width-stop-side")
                    || target.hasAttribute("data-length-stop-side")
                    || target.hasAttribute("data-width-stop-cm")
                    || target.hasAttribute("data-length-stop-cm")) {
                    applyStopControl(live.state, live.workspace, target);
                    refreshPlacementPreview(body, live.workspace, live.state, live.sheet);
                    return;
                }
                if (target.hasAttribute("data-cnc-machine")) {
                    live.state.cncMachine = String(target.value || "");
                    live.state.sheetStops = null;
                    live.state.stopDraft = { width: null, length: null };
                    const dims = body.querySelector("[data-machine-dims]");
                    const machine = findCncMachine(live.workspace, live.state.cncMachine);
                    if (dims) {
                        dims.textContent = machine
                            ? translate("Machine size: {0} cm × {1} cm (width × length)", [
                                Number(machine.width_cm || 0),
                                Number(machine.length_cm || 0),
                            ])
                            : translate("Select a machine to place the sheet with that machine's stops.");
                    }
                    const fit = validateSheetPlacementFits(live.workspace, live.state, {
                        requireMachine: Boolean(live.state.cncMachine),
                    });
                    const warning = body.querySelector("[data-placement-warning]");
                    if (warning) {
                        warning.hidden = Boolean(fit.ok);
                        warning.textContent = fit.ok ? "" : fit.message;
                    }
                    const preview = body.querySelector("[data-sheet-preview]");
                    if (preview && preview.__cutPreviewProgram) {
                        paintCutPathPreview(preview, {
                            status: "ready",
                            program: preview.__cutPreviewProgram,
                            sheet: live.sheet,
                            state: live.state,
                            selectedExecutionPathId: live.state.selectedExecutionPathId || "",
                            selectedVectorIds: live.state.vectorSelection || [],
                            layout: preview.getAttribute("data-preview-layout") || preview.__cutPreviewLayout || "",
                            zoom: preview.__cutPreviewZoom,
                            pan: preview.__cutPreviewPan,
                            hiddenOperations: preview.__cutPreviewHidden,
                            placement: placementPreviewPayload(live.workspace, live.state),
                        });
                    }
                    writeStopControls(body, machine ? defaultSheetStops(
                        machine,
                        live.state.sheetWidthCm,
                        live.state.sheetLengthCm
                    ) : null);
                    const stopRoot = body.querySelector("[data-sheet-stops]");
                    if (stopRoot) stopRoot.hidden = !machine;
                    if (machine) reportPlacementValidation(fit);
                    requestSheetProgramPreview(live.frm, dialog, live.workspace, live.sheet, live.state);
                }
            });
            body.addEventListener("input", event => {
                const live = liveContext();
                const target = event.target;
                if (!live || !live.state || !target || typeof target.hasAttribute !== "function") return;
                if (!target.hasAttribute("data-width-stop-cm") && !target.hasAttribute("data-length-stop-cm")) return;
                applyStopControl(live.state, live.workspace, target);
                refreshPlacementPreview(body, live.workspace, live.state, live.sheet);
            });
            body.addEventListener("click", event => {
                const live = liveContext();
                const target = event.target;
                if (!live || !live.state || !target || typeof target.closest !== "function") return;
                const resetStops = target.closest("[data-reset-sheet-stops]");
                if (resetStops) {
                    if (resetStops.disabled) return;
                    live.state.sheetStops = null;
                    live.state.stopDraft = { width: null, length: null };
                    const machine = findCncMachine(live.workspace, live.state.cncMachine);
                    writeStopControls(body, defaultSheetStops(
                        machine,
                        live.state.sheetWidthCm,
                        live.state.sheetLengthCm
                    ));
                    refreshPlacementPreview(body, live.workspace, live.state, live.sheet);
                    return;
                }
                const zone = boardPointerZone(target);
                const pathMenu = body.querySelector("[data-path-menu]");
                if (zone === "menu") {
                    const choosePath = target.closest("[data-choose-path]");
                    const reverse = target.closest("[data-reverse-path]");
                    const action = choosePath || reverse;
                    const pathKey = action
                        ? (action.getAttribute("data-path-key") || (pathMenu && pathMenu.getAttribute("data-path-key")) || "")
                        : "";
                    const shapeId = action ? (action.getAttribute("data-shape-id") || "") : "";
                    const executionId = action ? (action.getAttribute("data-execution-path-id") || "") : "";
                    if (pathMenu) pathMenu.hidden = true;
                    if (choosePath && executionId) {
                        applyExecutionSelection(body, live.workspace, live.sheet, live.state, executionId);
                    }
                    if (reverse && pathKey && live.workspace.can_prepare) {
                        if (executionId) {
                            ensureExecutionSelection(body, live.workspace, live.sheet, live.state, executionId);
                        }
                        requestPathReverse(
                            live.frm,
                            dialog,
                            live.workspace,
                            live.sheet,
                            live.state,
                            pathKey,
                            shapeId
                        );
                    }
                    return;
                }
                if (pathMenu) pathMenu.hidden = true;
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
                    live.state.selectedPathIdentity = null;
                    refreshSelection();
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
                const visibility = target.closest("[data-association-visibility]");
                if (visibility) {
                    const id = visibility.getAttribute("data-association-visibility");
                    if (!live.state.hiddenAssociations) live.state.hiddenAssociations = {};
                    live.state.hiddenAssociations[id] = !live.state.hiddenAssociations[id];
                    const preview = body.querySelector("[data-sheet-preview]");
                    if (preview) {
                        preview.__cutSheet = live.sheet;
                        preview.__hiddenAssociations = live.state.hiddenAssociations;
                        paintAssociationVisibility(preview);
                    }
                    visibility.setAttribute("aria-pressed", live.state.hiddenAssociations[id] ? "true" : "false");
                    visibility.innerHTML = orderMoveIcon(live.state.hiddenAssociations[id] ? "eye-off" : "eye");
                    return;
                }
                const editAssociation = target.closest("[data-edit-association]");
                if (editAssociation && window.AlmdinaArtcamMachining) {
                    const id = editAssociation.getAttribute("data-edit-association");
                    const row = ((live.sheet.machining || {}).associations || []).find(item => item.association_id === id);
                    if (!row) return;
                    const current = live.state.artcamForm;
                    const dirty = current && current.association_id !== id && (current.name || current.source);
                    if (dirty && !window.confirm(translate("Leave the current association without calculating it?"))) return;
                    window.AlmdinaArtcamMachining.loadAssociation(live.state, row);
                    live.state.sections = Object.assign({}, live.state.sections, { associations: true });
                    refreshDialog(live.frm, dialog, live.workspace, live.sheet, live.state, live.board);
                    return;
                }
                const deleteAssociation = target.closest("[data-delete-association]");
                if (deleteAssociation && live.workspace.can_prepare) {
                    const id = deleteAssociation.getAttribute("data-delete-association");
                    if (!window.confirm(translate("Remove this association from the operation order?"))) return;
                    const mutationRequest = beginSheetMutation(live.state);
                    if (!mutationRequest) return;
                    frappe.call({
                        method: `${METHOD}.delete_cnc_association`,
                        args: Object.assign({}, sheetGenerateArgs(live.frm, live.workspace, live.sheet, live.state), {
                            association_id: id,
                        }),
                        callback(response) {
                            if (!finishSheetMutation(live.state, mutationRequest)) return;
                            if (live.state.artcamForm && live.state.artcamForm.association_id === id) {
                                live.state.artcamForm = null;
                                live.state.vectorSelection = [];
                            }
                            const onWorkspace = dialog._almdinaOnWorkspace;
                            if (typeof onWorkspace === "function") onWorkspace((response && response.message) || {});
                        },
                        error(error) {
                            if (!finishSheetMutation(live.state, mutationRequest)) return;
                            showSheetIssueDialog(translate("The association could not be removed."), [{
                                problem: serverErrorText(error) || translate("The association could not be removed."),
                                target: id,
                                action: translate("Keep this association, or try removing it again."),
                            }]);
                        },
                    });
                    return;
                }
                const moveOp = target.closest("[data-move]");
                if (moveOp && live.workspace.can_prepare) {
                    const associationItem = moveOp.closest("[data-association-id]");
                    if (associationItem) {
                        const id = associationItem.getAttribute("data-association-id");
                        const rows = ((live.sheet.machining && live.sheet.machining.associations) || []).slice();
                        const index = rows.findIndex(row => row.association_id === id);
                        const targetIndex = index + (moveOp.getAttribute("data-move") === "earlier" ? -1 : 1);
                        if (index < 0 || targetIndex < 0 || targetIndex >= rows.length) return;
                        const next = rows.slice();
                        const [item] = next.splice(index, 1);
                        next.splice(targetIndex, 0, item);
                        const mutationRequest = beginSheetMutation(live.state);
                        if (!mutationRequest) return;
                        frappe.call({
                            method: `${METHOD}.save_cnc_operational_sheet`,
                            args: Object.assign({}, sheetGenerateArgs(live.frm, live.workspace, live.sheet, live.state), {
                                machining_profiles: (live.sheet.machining || {}).profiles || [],
                                vector_associations: next,
                            }),
                            callback(response) {
                                if (!finishSheetMutation(live.state, mutationRequest)) return;
                                const onWorkspace = dialog._almdinaOnWorkspace;
                                if (typeof onWorkspace === "function") onWorkspace((response && response.message) || {});
                            },
                            error() {
                                finishSheetMutation(live.state, mutationRequest);
                            },
                        });
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
                    return;
                }
                if (zone !== "board") return;
                if (live.workspace.can_prepare && applyBoardVectorClick(event, body, live.state)) return;
                const preview = body.querySelector("[data-sheet-preview]");
                const pointed = resolveBoardPointer(preview, event);
                if (pointed && pointed.ambiguous) {
                    openPathMenu(body, event, pointed.choices, "inspect");
                    return;
                }
                const previewHit = (pointed && pointed.hit) || boardVectorHit(target);
                if (!previewHit) return;
                applyExecutionSelection(
                    body,
                    live.workspace,
                    live.sheet,
                    live.state,
                    previewHit.getAttribute("data-execution-path-id")
                );
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
            body.addEventListener("contextmenu", event => {
                const live = liveContext();
                const menu = body.querySelector("[data-path-menu]");
                const zone = boardPointerZone(event.target);
                if (!menu) return;
                if (zone !== "board" || !live || !live.workspace || !live.workspace.can_prepare) {
                    if (zone !== "menu") menu.hidden = true;
                    return;
                }
                const preview = body.querySelector("[data-sheet-preview]");
                const pointed = resolveBoardPointer(preview, event);
                const hit = (pointed && pointed.hit)
                    || boardVectorHit(event.target);
                if (!hit && !(pointed && pointed.ambiguous)) {
                    menu.hidden = true;
                    return;
                }
                if (typeof event.preventDefault === "function") event.preventDefault();
                if (pointed && pointed.ambiguous) {
                    openPathMenu(body, event, pointed.choices, "reverse");
                    return;
                }
                openPathMenu(body, event, [{
                    path_key: hit.getAttribute("data-execution-path") || hit.getAttribute("data-vector-id") || "",
                    shape_id: hit.getAttribute("data-shape-id") || "",
                    execution_path_id: hit.getAttribute("data-execution-path-id") || "",
                    label: "",
                }], "reverse");
            });
            body.addEventListener("keydown", event => {
                if (event.key !== "Escape") return;
                const menu = body.querySelector("[data-path-menu]");
                if (menu) menu.hidden = true;
            });
        }
        mountPresetControls(frm, dialog, workspace, sheet, state, board);
        if (!canPrepare) return;
    }

    function reversePointList(value) {
        return String(value || "").trim().split(/\s+/).filter(Boolean).reverse().join(" ");
    }

    function reversePreviewPath(preview, pathKey) {
        if (!preview || !pathKey) return;
        preview.querySelectorAll(`g[data-execution-path="${pathKey}"] polyline`).forEach(line => {
            line.setAttribute("points", reversePointList(line.getAttribute("points")));
        });
        (preview.__cutPreviewPaths || []).forEach(item => {
            if (!item || item.path_key !== pathKey || !Array.isArray(item.points)) return;
            item.points = item.points.slice().reverse();
            item.start = item.points[0];
            item.end = item.points[item.points.length - 1];
        });
        paintPathMarkers(preview);
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
        const args = {
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
            base_revision: Number(state.settingsRevision || sheet.settings_revision || 0),
        };
        const stops = activeSheetStops(workspace, state);
        if (stops && !stops.error && String(state.cncMachine || "").trim()) {
            args.width_stop_side = stops.width_stop_side;
            args.width_stop_cm = stops.width_stop_cm;
            args.length_stop_side = stops.length_stop_side;
            args.length_stop_cm = stops.length_stop_cm;
        }
        return args;
    }

    function issueAction(code) {
        const actions = {
            tool_diameter_kerf_mismatch: translate("Choose a tool whose diameter matches the approved cutting plan."),
            tool_diameter_plan_mismatch: translate("Choose a tool whose diameter matches the approved cutting plan."),
            finished_geometry_missing: translate("Recalculate or re-approve the cutting plan so finished geometry is available."),
            geometry_invalid: translate("Fix the path geometry in the approved plan, then open this sheet again."),
            preset_disabled: translate("Enable the tool preset in factory settings, or choose another enabled preset."),
            preset_not_found: translate("Choose an available CNC tool preset."),
            tool_identity_conflict: translate("Use one physical tool number for every operation on this sheet."),
            mill_group_diameter_conflict: translate("Use one tool diameter for this milling group."),
            geometry_not_ready: translate("Resolve the listed geometry problems, then generate the NC file again."),
            mill_parameters_missing: translate("Complete the milling parameters on the approved plan, then try again."),
            liner_narrower_than_cutter: translate("Choose a narrower tool, or widen the milling band on the approved plan."),
            rear_groove_oversize_unsafe: translate("Run the rear groove along the open door edge, or choose a cutter that is not wider than the groove."),
            rear_groove_neighbor_conflict: translate("Separate the neighbouring door from the rear groove, or turn the groove toward an open edge."),
            perimeter_unavailable: translate("Keep separate cut paths, or fix the outer cut network so one closed perimeter can be formed."),
            perimeter_not_closed: translate("Close the outer cut network, or keep separate cut paths."),
            perimeter_geometry_ambiguous: translate("Remove branches from the outer cut network, or keep separate cut paths."),
            perimeter_components_disconnected: translate("Join the separate outer cut components, or keep separate cut paths."),
            perimeter_geometry_invalid: translate("Keep the approved cut geometry unchanged, or keep separate cut paths."),
            perimeter_join_mode_invalid: translate("Choose either a separate or a connected sheet perimeter."),
            cut_path_sequence_invalid: translate("Restore a valid CUT_PATH order that includes every cut path on this sheet."),
            perimeter_cut_early_unconfirmed: translate("Confirm the warning before cutting the sheet perimeter before liner, recessed handle, or rear groove."),
            cnc_machine_required: translate(PLACEMENT_MESSAGES.cnc_machine_required),
            cnc_machine_stops_unconfigured: translate(PLACEMENT_MESSAGES.cnc_machine_stops_unconfigured),
            sheet_exceeds_machine_width: translate(PLACEMENT_MESSAGES.sheet_exceeds_machine_width),
            sheet_exceeds_machine_length: translate(PLACEMENT_MESSAGES.sheet_exceeds_machine_length),
            offset_left_invalid: translate(PLACEMENT_MESSAGES.offset_left_invalid),
            offset_bottom_invalid: translate(PLACEMENT_MESSAGES.offset_bottom_invalid),
            path_reverse_unsupported: translate("This path cannot be reversed safely, so the NC file was not created."),
            path_reverse_stale: translate("A saved path direction belongs to an older geometry, so the NC file was not created."),
            path_reverse_missing: translate("A saved path direction no longer matches a path on this sheet, so the NC file was not created."),
            path_reverse_ambiguous: translate("A saved path direction matches more than one path, so the NC file was not created. Restore the direction, then set it again on the path you want."),
            sheet_perimeter_already_assigned: translate("The sheet perimeter already belongs to another association. Edit that association and release the sheet perimeter before assigning it on its own."),
            vector_already_assigned: translate("That vector or layer is already assigned."),
            mill_diameter_required: translate("This milling path needs the layer tool diameter before its cutter center can be calculated."),
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
                target: entry.target_message || [
                    sheetNo ? translate("Sheet {0}", [sheetNo]) : "",
                    entry.layer || "",
                    pieceLabel ? translate("Piece {0}", [pieceLabel]) : "",
                ].filter(Boolean).join(" — "),
                action: entry.action_message || issueAction(code),
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
                    const context = path.issue_context && path.issue_context[code];
                    remember({
                        code,
                        message: (context && context.problem) || messages[index] || code,
                        target_message: context && context.target,
                        action_message: context && context.action,
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
                rawCode: first.rawCode,
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
        const collectedFirst = collectProgramIssues(program, sheetNo);
        const diameterIssue = collectedFirst.issues.some(item => (
            item.rawCode === "tool_diameter_plan_mismatch" || item.rawCode === "tool_diameter_kerf_mismatch"
        ));
        const normalized = window.AlmdinaFrontend
            && typeof window.AlmdinaFrontend.normalizeError === "function"
            ? window.AlmdinaFrontend.normalizeError(error)
            : null;
        if (!diameterIssue && ui && typeof ui.errorDialog === "function" && error
            && normalized && normalized.issues && normalized.issues.length) {
            return ui.errorDialog(error, {
                title: translate("NC generation could not be completed"),
                fallback: translate("The NC file could not be prepared."),
                outcomeMessages: {
                    rejected: translate("No NC file was created."),
                },
            });
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
        const canGenerateNc = Boolean(workspace && workspace.can_generate_nc);
        const liveSheet = (dialog._almdinaSheet && dialog._almdinaSheet.sheet) || sheet;
        const control = generateNcControlState({ canPrepare, canGenerateNc, sheet: liveSheet });
        const generate = $(`<button type="button" class="btn btn-default btn-sm" data-cnc-footer-action="generate" data-cnc-generate-nc title="${escapeHtml(control.reason)}"></button>`);
        generate.text(translate("Generate NC file"));
        generate.prop("disabled", Boolean(control.disabled));
        actions.prepend(generate);
        const live = dialog._almdinaSheet;
        if (!live) return;
        bindGenerateNc(dialog, dialog.$wrapper[0], {
            canPrepare,
            canGenerateNc,
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

    function sheetIdentityMarkup(workspace, sheet) {
        return `<header class="dco-cnc-sheet-page__toolbar">
            <div class="dco-cnc-sheet-page__identity">
                <h1>${escapeHtml(translate("Sheet {0}", [sheet.sheet_no]))}</h1>
                <p class="dco-cnc-sheet-page__meta">
                    <span>${escapeHtml(workspace.order_name || workspace.order || "")}</span>
                    <span>${escapeHtml(translate("Approved plan"))}: ${escapeHtml(workspace.cutting_plan || "")}</span>
                    <span>${escapeHtml(translate("Plan revision"))} ${escapeHtml(workspace.plan_revision || "")}</span>
                </p>
            </div>
        </header>`;
    }

    function pageShellMarkup(workspace, sheet) {
        const locale = window.AlmdinaLocale;
        const dir = locale && typeof locale.direction === "function"
            ? locale.direction()
            : (document.documentElement && document.documentElement.getAttribute("dir")) || "rtl";
        return `<div class="dco-cnc-sheet-page" dir="${dir === "ltr" ? "ltr" : "rtl"}">
            <div class="dco-cnc-sheet-page__workspace" data-sheet-body></div>
        </div>`;
    }

    function placePageActions(ui) {
        if (!ui || ui.mode !== "page" || !ui.root || typeof ui.root.querySelector !== "function") return;
        const slot = ui.root.querySelector("[data-cnc-page-actions]");
        const body = ui.root.querySelector("[data-sheet-body]");
        const bar = body && typeof body.querySelector === "function"
            ? body.querySelector("[data-cnc-export-bar]")
            : null;
        if (slot && bar && typeof slot.replaceChildren === "function") slot.replaceChildren(bar);
    }

    function syncPageToolbar(ui, workspace, sheet, state) {
        if (!ui || !ui.root) return;
        placePageActions(ui);
        const canPrepare = Boolean(workspace && workspace.can_prepare);
        const canGenerateNc = Boolean(workspace && workspace.can_generate_nc);
        const save = ui.root.querySelector("[data-cnc-save-sheet]");
        const generate = ui.root.querySelector("[data-cnc-generate-nc]");
        const control = generateNcControlState({ canPrepare, canGenerateNc, sheet });
        if (save) save.disabled = !canPrepare;
        if (generate) {
            generate.disabled = Boolean(control.disabled);
            generate.setAttribute("title", control.disabled ? (control.reason || "") : translate("Download cutting file"));
        }
        bindGenerateNc(ui, ui.root, {
            canPrepare,
            canGenerateNc,
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
            ui._almdinaOnWorkspace = message => {
                const saved = (message.sheets || []).find(item => Number(item.sheet_no) === Number(sheet.sheet_no));
                if (!saved) return;
                const incomingRevision = Number(saved.settings_revision || 0);
                if (incomingRevision < Number(state.settingsRevision || 0)) return;
                state.settingsRevision = incomingRevision;
                refreshSheetUi(frm, ui, message, saved, state);
            };
            wrapper.innerHTML = dialogMarkup(workspace, sheet, state, { exportBar: ui.mode === "page" });
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
                    beginMutation() {
                        return beginSheetMutation(state);
                    },
                    finishMutation(request) {
                        return finishSheetMutation(state, request);
                    },
                    refresh() {
                        refreshSheetUi(frm, ui, workspace, sheet, state);
                    },
                    paintBoard() {
                        const root = dialogRoot(ui);
                        const preview = root && root.querySelector("[data-sheet-preview]");
                        if (preview) preview.__cutSheet = sheet;
                        paintBoardAppearance(root, sheet, state);
                    },
                    onWorkspace(message) {
                        ui._almdinaOnWorkspace(message);
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
        const mutationRequest = beginSheetMutation(state);
        if (!mutationRequest) return;
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
                if (frm.__almdinaOperationalFilesRequest !== requestId) {
                    finishSheetMutation(state, mutationRequest);
                    return;
                }
                if (!finishSheetMutation(state, mutationRequest)) return;
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
                    state.settingsRevision = next.settingsRevision;
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
                if (frm.__almdinaOperationalFilesRequest !== requestId) {
                    finishSheetMutation(state, mutationRequest);
                    return;
                }
                if (!finishSheetMutation(state, mutationRequest)) return;
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
                pageRoot.addEventListener("click", event => {
                    const save = event.target && event.target.closest
                        ? event.target.closest("[data-cnc-save-sheet]")
                        : null;
                    if (!save || save.disabled) return;
                    const live = ui._almdinaSheet || { workspace, sheet, state };
                    saveSheetSettings(frm, ui, live.workspace || workspace, live.sheet || sheet, live.state || state, baselineHolder);
                });
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

    const PATH_COLOR = "#C62828";
    const PROGRAM_COLORS = Object.freeze({
        liner: PATH_COLOR,
        recessed_handle_cutout: PATH_COLOR,
        back_groove: PATH_COLOR,
        sheet_perimeter: PATH_COLOR,
        cut_path: PATH_COLOR,
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
        const rounded = (Array.isArray(points) ? points : []).map(point => [
            Number(point[0]).toFixed(3),
            Number(point[1]).toFixed(3),
        ]).filter((point, index, all) => (
            index === 0 || point[0] !== all[index - 1][0] || point[1] !== all[index - 1][1]
        ));
        if (closed && rounded.length > 2) {
            const first = rounded[0];
            const last = rounded[rounded.length - 1];
            if (first[0] === last[0] && first[1] === last[1]) rounded.pop();
        }
        const rotate = (sequence) => {
            if (!closed || sequence.length < 3) return sequence;
            let best = 0;
            for (let index = 1; index < sequence.length; index += 1) {
                const point = sequence[index];
                const current = sequence[best];
                if (point[0] < current[0] || (point[0] === current[0] && point[1] < current[1])) best = index;
            }
            return sequence.slice(best).concat(sequence.slice(0, best));
        };
        const text = (sequence) => sequence.map(point => point.join(",")).join(";");
        const forward = text(rotate(rounded));
        const backward = text(rotate(rounded.slice().reverse()));
        return `${closed ? "C" : "O"}:${forward <= backward ? forward : backward}`;
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

    function previewEndPoint(points, start, end, closed, gap) {
        const finish = Array.isArray(end) ? end : (Array.isArray(points) ? points[points.length - 1] : start);
        if (!Array.isArray(start) || !Array.isArray(finish) || !Array.isArray(points) || points.length < 2) return finish || start;
        const dx = Number(finish[0]) - Number(start[0]);
        const dy = Number(finish[1]) - Number(start[1]);
        if (!closed || Math.hypot(dx, dy) > 0.5) return finish;
        const previous = points[points.length - 2];
        const incomingX = Number(finish[0]) - Number(previous[0]);
        const incomingY = Number(finish[1]) - Number(previous[1]);
        const length = Math.hypot(incomingX, incomingY) || 1;
        const separation = Number(gap) > 0 ? Number(gap) : 4;
        return [Number(finish[0]) - (incomingX / length) * separation, Number(finish[1]) - (incomingY / length) * separation];
    }

    function segmentDistance(px, py, start, end) {
        const dx = Number(end[0]) - Number(start[0]);
        const dy = Number(end[1]) - Number(start[1]);
        const lengthSq = dx * dx + dy * dy;
        if (!(lengthSq > 0)) return Math.hypot(px - Number(start[0]), py - Number(start[1]));
        const ratio = Math.max(0, Math.min(1, ((px - Number(start[0])) * dx + (py - Number(start[1])) * dy) / lengthSq));
        return Math.hypot(px - (Number(start[0]) + ratio * dx), py - (Number(start[1]) + ratio * dy));
    }

    function boardPointerZone(target) {
        if (!target || typeof target.closest !== "function") return "unknown";
        if (target.closest("[data-path-menu]")) return "menu";
        const controls = [
            "[data-sheet-acc]",
            "[data-customize-path]",
            "[data-reset-path]",
            "[data-select-execution]",
            "[data-select-path]",
            "[data-toggle-layer]",
            "[data-restore-layer]",
            "[data-restore-sheet]",
            "[data-association-visibility]",
            "[data-edit-association]",
            "[data-delete-association]",
            "[data-move]",
            "[data-artcam-root]",
            "[data-cnc-save-sheet]",
            "[data-cnc-generate-nc]",
            "[data-generate-nc]",
            "[data-cut-zoom]",
            ".dco-cnc-cut-preview__zoom",
        ];
        if (controls.some(selector => target.closest(selector))) return "control";
        if (target.closest("[data-sheet-geometry]")) return "board";
        const svg = target.closest("svg");
        if (svg && typeof svg.closest === "function" && svg.closest("[data-sheet-preview]")) return "board";
        return "outside";
    }

    function resolveBoardPointer(preview, event) {
        if (!preview || !event || event.clientX == null || typeof preview.querySelector !== "function") return null;
        const group = preview.querySelector("[data-sheet-geometry]");
        const svg = preview.querySelector(".dco-cnc-cut-preview__svg");
        if (!group || !svg || typeof group.getScreenCTM !== "function" || typeof svg.createSVGPoint !== "function") return null;
        const matrix = group.getScreenCTM();
        if (!matrix || typeof matrix.inverse !== "function") return null;
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const local = point.matrixTransform(matrix.inverse());
        const scale = Math.hypot(Number(matrix.a) || 0, Number(matrix.c) || 0) || 1;
        const tolerance = 14 / scale;
        const epsilon = 2 / scale;
        const ranked = [];
        (preview.__cutPreviewPaths || []).forEach(item => {
            if (!item || !Array.isArray(item.points) || item.points.length < 2) return;
            const node = preview.querySelector(`[data-execution-path-id="${item.execution_path_id}"]`);
            if (!node || (node.classList && (
                node.classList.contains("is-association-hidden")
                || node.classList.contains("is-assigned")
            ))) return;
            let distance = Infinity;
            previewPathSets(item).forEach(points => {
                for (let index = 1; index < points.length; index += 1) {
                    distance = Math.min(distance, segmentDistance(local.x, local.y, points[index - 1], points[index]));
                }
            });
            if (distance <= tolerance) {
                ranked.push({
                    distance,
                    node,
                    path_key: String(item.path_key || ""),
                    shape_id: String(item.shape_id || ""),
                    execution_path_id: String(item.execution_path_id || ""),
                    label: [item.operation_key || "", item.piece_label || item.path_key || ""].filter(Boolean).join(" · "),
                });
            }
        });
        ranked.sort((left, right) => left.distance - right.distance || left.path_key.localeCompare(right.path_key));
        if (!ranked.length) return { hit: null, ambiguous: false, choices: [] };
        const ambiguous = ranked.length > 1 && ranked[1].distance - ranked[0].distance <= epsilon;
        return { hit: ranked[0].node, ambiguous, choices: ranked.slice(0, 4) };
    }

    function openPathMenu(body, event, choices, mode) {
        const menu = body && body.querySelector("[data-path-menu]");
        if (!menu) return;
        const rows = (choices || []).filter(choice => choice && choice.path_key);
        if (!rows.length) {
            menu.hidden = true;
            return;
        }
        menu.innerHTML = rows.map(choice => {
            const label = mode === "inspect"
                ? (choice.label || choice.path_key)
                : (choice.label
                    ? `${translate("Reverse Direction")} · ${choice.label}`
                    : translate("Reverse Direction"));
            const action = mode === "inspect" ? "data-choose-path" : "data-reverse-path";
            return `<button type="button" ${action} data-path-key="${escapeHtml(choice.path_key)}" data-shape-id="${escapeHtml(choice.shape_id || "")}" data-execution-path-id="${escapeHtml(choice.execution_path_id || "")}">${escapeHtml(label)}</button>`;
        }).join("");
        menu.hidden = false;
        menu.setAttribute("data-path-key", rows[0].path_key);
        menu.style.left = `${Number(event.clientX) || 0}px`;
        menu.style.top = `${Number(event.clientY) || 0}px`;
    }

    function requestPathReverse(frm, dialog, workspace, sheet, state, pathKey, shapeId, clearSaved) {
        if (!pathKey || !state || state.reverseBusy) return;
        const assigned = assignedVectorIds(sheet, state.program);
        const locked = collectPhysicalPaths(state.program).some(path => (
            path.path_key === pathKey && assigned.has(String(path.vector_id || ""))
        ));
        if (locked) return;
        const mutationRequest = beginSheetMutation(state);
        if (!mutationRequest) return;
        state.reverseBusy = pathKey;
        frappe.call({
            method: `${METHOD}.set_cnc_path_direction`,
            args: Object.assign({}, sheetGenerateArgs(frm, workspace, sheet, state), {
                path_key: pathKey,
                shape_id: shapeId || "",
                clear_saved: clearSaved ? 1 : 0,
            }),
            callback(response) {
                if (!finishSheetMutation(state, mutationRequest)) return;
                state.reverseBusy = "";
                state.directionReport = pathKey;
                const message = (response && response.message) || {};
                const saved = (message.sheets || []).find(item => Number(item.sheet_no) === Number(sheet.sheet_no));
                if (saved) {
                    // Server wrote current settings and the new direction together.
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
                    state.sheetStops = next.sheetStops;
                    state.settingsRevision = next.settingsRevision;
                    state.sheetWidthCm = next.sheetWidthCm;
                    state.sheetLengthCm = next.sheetLengthCm;
                }
                const onWorkspace = dialog._almdinaOnWorkspace;
                if (typeof onWorkspace === "function") {
                    onWorkspace(message);
                }
            },
            error(error) {
                if (!finishSheetMutation(state, mutationRequest)) return;
                state.reverseBusy = "";
                const problem = serverErrorText(error) || translate("This path cannot be reversed safely, so the NC file was not created.");
                showSheetIssueDialog(translate("The path direction was not changed."), [{
                    problem,
                    target: pathKey,
                    action: problem,
                    code: "path_reverse_unsupported",
                }]);
            },
        });
    }

    function serverErrorText(error) {
        const ui = window.AlmdinaFrontend;
        if (ui && typeof ui.normalizeError === "function") {
            const normalized = ui.normalizeError(error);
            if (normalized && (normalized.message || normalized.exception)) return normalized.message || normalized.exception;
        }
        if (!error) return "";
        if (typeof error === "string") return error;
        return error.message || (error.responseJSON && (error.responseJSON.exception || error.responseJSON._error_message)) || "";
    }

    function showSheetIssueDialog(title, issues, options) {
        const rows = Array.isArray(issues) ? issues : [];
        const ui = window.AlmdinaUi;
        if (ui && typeof ui.errorDialog === "function" && options && options.error) {
            const shown = ui.errorDialog(options.error, {
                title,
                fallback: (rows[0] && rows[0].problem) || title,
            });
            if (shown) return shown;
        }
        if (!window.frappe || !frappe.ui || !frappe.ui.Dialog) {
            if (window.frappe && frappe.msgprint) frappe.msgprint((rows[0] && rows[0].problem) || title);
            return null;
        }
        const grouped = [];
        rows.forEach(item => {
            const code = String((item && item.code) || "");
            const existing = code ? grouped.find(row => row.code === code) : null;
            if (!existing) {
                grouped.push(Object.assign({}, item, { target: item && item.target ? String(item.target) : "" }));
                return;
            }
            if (item && item.target && existing.target.indexOf(String(item.target)) < 0) {
                existing.target = [existing.target, item.target].filter(Boolean).join(", ");
            }
        });
        const cards = grouped.map(item => `<section class="alm-error-card">
            <p><strong>${escapeHtml(translate("What is the problem?"))}</strong> ${escapeHtml(item.problem || "")}</p>
            ${item.target ? `<p><strong>${escapeHtml(translate("Where is it?"))}</strong> ${escapeHtml(item.target)}</p>` : ""}
            ${item.action ? `<p><strong>${escapeHtml(translate("What should I do?"))}</strong> ${escapeHtml(item.action)}</p>` : ""}
        </section>`).join("");
        const dialogBox = new frappe.ui.Dialog({
            title,
            size: "large",
            secondary_action_label: translate("Close"),
            secondary_action() { dialogBox.hide(); },
        });
        const restore = options && options.restorePath
            ? `<p><button type="button" class="btn btn-default btn-sm" data-restore-direction>${escapeHtml(translate("Restore the original direction"))}</button></p>`
            : "";
        dialogBox.$body.html(`<div class="almdina-ui"><div class="alm-error-summary" role="alert">${cards}${restore}</div></div>`);
        if (options && options.restorePath && dialogBox.$body) {
            dialogBox.$body.find("[data-restore-direction]").on("click", () => {
                dialogBox.hide();
                if (typeof options.onRestore === "function") options.onRestore(options.restorePath || "");
            });
        }
        dialogBox.show();
        return dialogBox;
    }

    function perimeterIssues(program) {
        const codes = {
            perimeter_unavailable: true,
            perimeter_not_closed: true,
            perimeter_geometry_ambiguous: true,
            perimeter_components_disconnected: true,
            perimeter_geometry_invalid: true,
            perimeter_join_mode_invalid: true,
        };
        const found = [];
        (Array.isArray(program && program.issues) ? program.issues : []).forEach(issue => {
            const code = String(issue && issue.code || "");
            if (!codes[code]) return;
            found.push({
                code,
                problem: issue.message || issueAction(code),
                target: issue.path_key || "SHEET_PERIMETER",
                action: issueAction(code),
            });
        });
        return found;
    }

    function boardVectorHit(target) {
        let node = target;
        while (node) {
            const vectorId = node.getAttribute && (
                node.getAttribute("data-vector-id") || node.getAttribute("data-execution-path")
            );
            const executionId = node.getAttribute && node.getAttribute("data-execution-path-id");
            if (vectorId && executionId) {
                let parent = node;
                while (parent) {
                    if (parent.classList && (
                        parent.classList.contains("is-association-hidden")
                        || parent.classList.contains("is-assigned")
                    )) return null;
                    if (parent.getAttribute && parent.getAttribute("data-sheet-preview") !== null
                        && parent !== node) return node;
                    parent = parent.parentElement || parent.parentNode || parent.parent || null;
                }
            }
            node = node.parentElement || node.parentNode || node.parent || null;
        }
        return null;
    }

    function applyBoardVectorClick(event, body, state) {
        if (!event || !event.shiftKey || !state) return false;
        const hit = boardVectorHit(event.target);
        if (!hit) return false;
        const source = body && typeof body.querySelector === "function"
            ? body.querySelector("[data-artcam-editor] [data-field=\"source\"]")
            : null;
        const mode = (source && source.value) || ((state.artcamForm || {}).source) || "";
        if (mode !== "selected_vectors") return false;
        if (typeof event.preventDefault === "function") event.preventDefault();
        const vectorId = hit.getAttribute("data-vector-id") || "";
        if (!vectorId) return true;
        const preview = body && typeof body.querySelector === "function"
            ? body.querySelector("[data-sheet-preview]")
            : null;
        if (preview && boardDisplayState(preview.__cutSheet, state, state.program).assigned.has(String(vectorId))) return true;
        if (!Array.isArray(state.vectorSelection)) state.vectorSelection = [];
        const selected = new Set(state.vectorSelection.map(String));
        if (selected.has(String(vectorId))) selected.delete(String(vectorId));
        else selected.add(String(vectorId));
        state.vectorSelection = Array.from(selected);
        if (window.AlmdinaArtcamMachining && typeof window.AlmdinaArtcamMachining.ensureForm === "function") {
            window.AlmdinaArtcamMachining.ensureForm(state);
        }
        paintBoardAppearance(body, null, state);
        const count = body && typeof body.querySelector === "function"
            ? body.querySelector("[data-vector-count]")
            : null;
        if (count) count.textContent = translate("{0} Vectors Selected", [state.vectorSelection.length]);
        return true;
    }

    function boardDisplayState(sheet, state, program) {
        const form = (state && state.artcamForm) || {};
        const source = String(form.source || "");
        let active = "";
        if (source === "sheet_perimeter") active = "sheet_perimeter";
        else if (source.indexOf("layer:") === 0) active = source.slice(6);
        const assigned = assignedVectorIds(sheet, program || (state && state.program));
        return {
            active,
            assigned,
            selected: new Set(((state && state.vectorSelection) || []).map(String)),
        };
    }

    function assignedVectorIds(sheet, program) {
        const assigned = new Set();
        const associations = ((((sheet || {}).machining) || {}).associations || []);
        associations.forEach(row => {
            if (!row) return;
            (row.vector_ids || []).forEach(id => assigned.add(String(id)));
        });
        const physical = program ? collectPhysicalPaths(program) : [];
        if (physical.length) {
            associations.forEach(row => {
                const selection = (row && row.selection) || {};
                if (selection.kind !== "layer" || !selection.operation_key) return;
                physical.forEach(path => {
                    if (String(path.operation_key || "") === String(selection.operation_key)) {
                        assigned.add(String(path.vector_id || ""));
                    }
                });
            });
        }
        assigned.delete("");
        return assigned;
    }

    function physicalPathIsAssigned(sheet, path, program) {
        return Boolean(path && assignedVectorIds(sheet, program).has(String(path.vector_id || "")));
    }

    function paintBoardAppearance(body, sheet, state) {
        const preview = body && body.querySelector("[data-sheet-preview]");
        if (!preview) return;
        const display = boardDisplayState(sheet || preview.__cutSheet, state, state && state.program);
        preview.querySelectorAll("[data-execution-path]").forEach(node => {
            const vectorId = node.getAttribute("data-vector-id") || "";
            const operation = node.getAttribute("data-operation-key") || "";
            const assigned = display.assigned.has(vectorId);
            const current = !assigned && display.selected.has(vectorId);
            node.classList.toggle("is-vector-picked", current);
            node.classList.toggle("is-assigned", assigned);
            node.classList.toggle(
                "is-layer-active",
                Boolean(display.active) && !current && !assigned && operation === display.active
            );
        });
    }

    function highlightVectorSelection(body, state) {
        paintBoardAppearance(body, null, state);
    }

    function collectPhysicalPaths(program) {
        const paths = [];
        let pathNumber = 0;
        let passOrdinal = 0;
        const operations = Array.isArray(program && program.operations) ? program.operations : [];
        const shapesByPathKey = new Map();
        operations.forEach(operation => {
            (operation.toolpaths || []).forEach(toolpath => {
                const pathKey = String(toolpath && toolpath.path_key || "");
                const shapeId = String(toolpath && toolpath.shape_id || "");
                if (!pathKey || !shapeId) return;
                if (!shapesByPathKey.has(pathKey)) shapesByPathKey.set(pathKey, new Set());
                shapesByPathKey.get(pathKey).add(shapeId);
            });
        });
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
                        shape_id: String(toolpath.shape_id || ""),
                        vector_id: String(toolpath.vector_id || (
                            toolpath.shape_id && (shapesByPathKey.get(pathKey) || new Set()).size > 1
                                ? `${pathKey}#${toolpath.shape_id}`
                                : pathKey
                        )),
                        display_paths: (Array.isArray(toolpath.display_paths) ? toolpath.display_paths : [])
                            .map(points => (Array.isArray(points) ? points.map(point => [Number(point[0]), Number(point[1])]) : []))
                            .filter(points => points.length >= 2),
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
        const keyCount = {};
        paths.forEach(path => {
            keyCount[path.path_key] = (keyCount[path.path_key] || 0) + 1;
        });
        paths.forEach(path => {
            if (!path.vector_id && keyCount[path.path_key] === 1) path.vector_id = path.path_key;
        });
        return paths;
    }

    function findPhysicalPath(program, executionPathId) {
        const selected = String(executionPathId || "");
        if (!selected) return null;
        return collectPhysicalPaths(program).find(item => item.execution_path_id === selected) || null;
    }

    function pathSelectionIdentity(path) {
        if (!path) return null;
        return {
            path_key: String(path.path_key || ""),
            shape_id: String(path.shape_id || ""),
            vector_id: String(path.vector_id || ""),
            geometry_fingerprint: String(path.geometry_fingerprint || ""),
            operation_key: String(path.operation_key || ""),
        };
    }

    function findPhysicalPathByIdentity(paths, identity) {
        const rows = Array.isArray(paths) ? paths : [];
        if (!identity) return null;
        const shape = String(identity.shape_id || "");
        const geometry = String(identity.geometry_fingerprint || "");
        const matches = (predicate) => {
            const found = rows.filter(predicate);
            return found.length === 1 ? found[0] : null;
        };
        if (identity.vector_id) {
            const vector = matches(path => (
                String(path.vector_id || "") === String(identity.vector_id)
                && (!shape || String(path.shape_id || "") === shape)
                && (!geometry || String(path.geometry_fingerprint || "") === geometry)
            ));
            if (vector) return vector;
        }
        if (identity.path_key) {
            const keyed = matches(path => (
                String(path.path_key || "") === String(identity.path_key)
                && (!shape || String(path.shape_id || "") === shape)
                && (!geometry || String(path.geometry_fingerprint || "") === geometry)
            ));
            if (keyed) return keyed;
        }
        if (shape && geometry) {
            return matches(path => (
                String(path.shape_id || "") === shape
                && String(path.geometry_fingerprint || "") === geometry
                && (!identity.operation_key
                    || String(path.operation_key || "") === String(identity.operation_key))
            ));
        }
        if (!shape && geometry) {
            return matches(path => (
                String(path.geometry_fingerprint || "") === geometry
                && (!identity.operation_key
                    || String(path.operation_key || "") === String(identity.operation_key))
            ));
        }
        return null;
    }

    function restoreSelectedPhysicalPath(state, paths) {
        if (!state) return null;
        const rows = Array.isArray(paths) ? paths : [];
        if (!state.selectedExecutionPathId && !state.selectedPathIdentity) return null;
        let selected = rows.find(path => (
            state.selectedExecutionPathId
            && path.execution_path_id === state.selectedExecutionPathId
        )) || null;
        if (!selected) selected = findPhysicalPathByIdentity(rows, state.selectedPathIdentity);
        if (!selected) {
            state.selectedExecutionPathId = "";
            state.selectedPathKey = "";
            state.selectedPathIdentity = null;
            return null;
        }
        state.selectedExecutionPathId = selected.execution_path_id;
        state.selectedPathKey = selected.path_key;
        state.selectedPathIdentity = pathSelectionIdentity(selected);
        return selected;
    }

    function cutExecutionArrowSegment(points, closed) {
        if (!Array.isArray(points) || points.length < 2) return null;
        if (closed && points.length >= 3) {
            const index = Math.max(1, Math.min(points.length - 2, Math.floor((points.length - 1) * 0.35)));
            return { from: points[index], to: points[index + 1] };
        }
        return { from: points[points.length - 2], to: points[points.length - 1] };
    }

    function previewPathSets(item) {
        if (item && item.ready && Array.isArray(item.points) && item.points.length >= 2) {
            return [previewPolylinePoints(item.points, item.closed)];
        }
        const display = item && Array.isArray(item.display_paths)
            ? item.display_paths.filter(points => Array.isArray(points) && points.length >= 2)
            : [];
        if (display.length) return display;
        return item && Array.isArray(item.points) && item.points.length >= 2
            ? [previewPolylinePoints(item.points, item.closed)]
            : [];
    }

    function previewPolylinePoints(points, closed) {
        const shown = (Array.isArray(points) ? points : []).map(point => [
            Number(point[0]),
            Number(point[1]),
        ]);
        if (!closed || shown.length < 3) return shown;
        const first = shown[0];
        const last = shown[shown.length - 1];
        if (Math.hypot(last[0] - first[0], last[1] - first[1]) > 0.05) {
            shown.push(first.slice());
        }
        return shown;
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

    function formatPreviewNumber(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "0";
        return String(Math.round(number * 1000) / 1000);
    }

    function cutPreviewViewBox(width, length, paths, offsetX, offsetY) {
        let minX = 0;
        let minY = 0;
        let maxX = Number(width) || 0;
        let maxY = Number(length) || 0;
        const radius = Math.max(6, Math.min(maxX || 100, maxY || 100) * 0.012);
        (Array.isArray(paths) ? paths : []).forEach(item => {
            previewPathSets(item).forEach(points => {
                points.forEach(point => {
                    const svgX = Number(offsetX || 0) + Number(point[0]);
                    const svgY = Number(length) - (Number(offsetY || 0) + Number(point[1]));
                    if (!Number.isFinite(svgX) || !Number.isFinite(svgY)) return;
                    minX = Math.min(minX, svgX);
                    maxX = Math.max(maxX, svgX);
                    minY = Math.min(minY, svgY);
                    maxY = Math.max(maxY, svgY);
                });
            });
        });
        const pad = radius + 2;
        minX -= pad;
        minY -= pad;
        maxX += pad;
        maxY += pad;
        return {
            minX,
            minY,
            width: Math.max(1, maxX - minX),
            height: Math.max(1, maxY - minY),
            text: [
                formatPreviewNumber(minX),
                formatPreviewNumber(minY),
                formatPreviewNumber(Math.max(1, maxX - minX)),
                formatPreviewNumber(Math.max(1, maxY - minY)),
            ].join(" "),
        };
    }

    function layoutTrimMm(layout, sheetRecord, axis) {
        const horizontal = axis === "x";
        const trimKey = horizontal ? "applied_trim_width_cm" : "applied_trim_length_cm";
        const fullKey = horizontal ? "full_width_cm" : "full_length_cm";
        const usableKey = horizontal ? "usable_width_cm" : "usable_length_cm";
        const planFullKey = horizontal ? "full_board_width_cm" : "full_board_length_cm";
        const planUsableKey = horizontal ? "usable_board_width_cm" : "usable_board_length_cm";
        const read = (source, key) => {
            if (!source || source[key] == null || source[key] === "") return null;
            const number = Number(source[key]);
            return Number.isFinite(number) ? number : null;
        };
        const explicit = read(sheetRecord, trimKey);
        if (explicit != null) return Math.max(0, explicit) * 10;
        const sheetFull = read(sheetRecord, fullKey) || 0;
        const sheetUsable = read(sheetRecord, usableKey) || 0;
        if (sheetFull > sheetUsable && sheetUsable > 0) return ((sheetFull - sheetUsable) / 2) * 10;
        const planTrim = read(layout, trimKey);
        if (planTrim != null) return Math.max(0, planTrim) * 10;
        const planFull = read(layout, planFullKey) || 0;
        const planUsable = read(layout, planUsableKey) || 0;
        if (planFull > planUsable && planUsable > 0) return ((planFull - planUsable) / 2) * 10;
        return Math.max(0, read(layout, "trim_cm") || 0) * 10;
    }

    function finiteRing(points) {
        return (Array.isArray(points) ? points : []).filter(point => (
            Array.isArray(point)
            && point.length >= 2
            && Number.isFinite(Number(point[0]))
            && Number.isFinite(Number(point[1]))
        )).map(point => [Number(point[0]), Number(point[1])]);
    }

    function pieceDisplayRings(piece) {
        const geometry = piece && piece.geometry;
        const space = geometry && geometry.coordinate_space;
        const unit = geometry && geometry.unit;
        const usableSpace = space == null || space === "" || space === "usable_sheet";
        const millimetres = unit == null || unit === "" || unit === "mm";
        if (geometry && usableSpace && millimetres) {
            const outer = finiteRing(geometry.outer);
            if (outer.length >= 3) {
                const holes = (Array.isArray(geometry.holes) ? geometry.holes : [])
                    .map(finiteRing)
                    .filter(ring => ring.length >= 3);
                return { outer, holes };
            }
        }
        const outline = finiteRing(piece && piece.placement_outline_cm).map(point => [point[0] * 10, point[1] * 10]);
        if (outline.length >= 3) return { outer: outline, holes: [] };
        const x = Number(piece && (piece.x != null ? piece.x : piece.x_cm));
        const y = Number(piece && (piece.y != null ? piece.y : piece.y_cm));
        const width = Number(piece && (piece.w != null ? piece.w : piece.width_cm));
        const height = Number(piece && (piece.h != null ? piece.h : piece.length_cm));
        if (![x, y, width, height].every(Number.isFinite) || !(width > 0) || !(height > 0)) return null;
        const left = x * 10;
        const top = y * 10;
        const right = left + width * 10;
        const bottom = top + height * 10;
        return {
            outer: [[left, top], [right, top], [right, bottom], [left, bottom]],
            holes: [],
        };
    }

    function usableRingToSheet(points, trimX, trimY, sheetLengthMm) {
        return points.map(point => [
            trimX + point[0],
            sheetLengthMm - trimY - point[1],
        ]);
    }

    function sheetRingPath(points) {
        return points.map((point, index) => (
            `${index ? "L" : "M"}${formatPreviewNumber(point[0])} ${formatPreviewNumber(point[1])}`
        )).join(" ") + " Z";
    }

    function previewBoardPiecesMarkup(options, sheetLengthMm) {
        const layout = options && options.boardLayout;
        const sheetNo = Number(options && options.sheetNo);
        const length = Number(sheetLengthMm);
        if (!layout || !Number.isFinite(sheetNo) || !(length > 0)) return "";
        const sheets = Array.isArray(layout.sheets) ? layout.sheets : [];
        const record = sheets.find((item, index) => Number((item && item.sheet_no) || index + 1) === sheetNo) || null;
        const pieces = record && Array.isArray(record.pieces) ? record.pieces : [];
        if (!pieces.length) return "";
        const trimX = layoutTrimMm(layout, record, "x");
        const trimY = layoutTrimMm(layout, record, "y");
        return pieces.map(piece => {
            const rings = pieceDisplayRings(piece);
            if (!rings) return "";
            const outer = usableRingToSheet(rings.outer, trimX, trimY, length);
            if (outer.length < 3) return "";
            const holes = rings.holes
                .map(hole => usableRingToSheet(hole, trimX, trimY, length))
                .filter(hole => hole.length >= 3);
            const path = [outer, ...holes].map(sheetRingPath).join(" ");
            const identity = piece.piece_instance_id || piece.id || piece.label || "";
            return `<path class="dco-cnc-cut-preview__piece" data-piece-id="${escapeHtml(identity)}" fill="none" fill-rule="evenodd" d="${path}"/>`;
        }).join("");
    }

    function cutPreviewLayoutStyle(width, length, options = {}) {
        const frameWidth = Number(options.frameWidth || width);
        const frameHeight = Number(options.frameHeight || length);
        const pageLayout = String(options.layout || "") === "page";
        const aspect = `aspect-ratio:${formatPreviewNumber(frameWidth)} / ${formatPreviewNumber(frameHeight)}`;
        if (pageLayout) return "inline-size:100%;max-inline-size:100%;";
        return `max-inline-size:${SHEET_PREVIEW_MAX_WIDTH_PX}px;${aspect}`;
    }

    function placementOverlayMarkup(placement, metrics) {
        if (!placement) return "";
        const width = Number(metrics.width);
        const length = Number(metrics.length);
        const offsetX = Number(metrics.offsetX);
        const offsetY = Number(metrics.offsetY);
        const sheetW = Number(metrics.sheetW);
        const sheetL = Number(metrics.sheetL);
        if (!(width > 0) || !(length > 0) || !(sheetW > 0) || !(sheetL > 0)) return "";
        const leftCm = Math.max(0, Number(placement.offset_left_cm || 0));
        const bottomCm = Math.max(0, Number(placement.offset_bottom_cm || 0));
        const rightCm = Math.max(0, Number(placement.right_clearance_cm || 0));
        const topCm = Math.max(0, Number(placement.top_clearance_cm || 0));
        const frameText = String(metrics.frameText || `0 0 ${width} ${length}`);
        const view = frameText.trim().split(/\s+/).map(Number);
        const box = view.length === 4 && view[2] > 0 && view[3] > 0
            ? { x: view[0], y: view[1], width: view[2], height: view[3] }
            : { x: 0, y: 0, width, height };
        const percent = (svgX, svgY) => {
            const left = ((svgX - box.x) / box.width) * 100;
            const top = ((svgY - box.y) / box.height) * 100;
            return `left:${formatPreviewNumber(left)}%;top:${formatPreviewNumber(top)}%`;
        };
        const midX = offsetX + sheetW / 2;
        const midY = length - (offsetY + sheetL / 2);
        const markerId = `${metrics.markerScope}-stop-arrow`;
        const arrow = (side, x1, y1, x2, y2) => (
            `<line data-stop-arrow="${side}" x1="${formatPreviewNumber(x1)}" y1="${formatPreviewNumber(y1)}" x2="${formatPreviewNumber(x2)}" y2="${formatPreviewNumber(y2)}" stroke="#1d4f91" stroke-width="2" vector-effect="non-scaling-stroke" marker-start="url(#${markerId})" marker-end="url(#${markerId})"/>`
        );
        const badge = (side, cm, svgX, svgY) => (
            cm > 0
                ? `<span class="dco-cnc-cut-preview__stop-badge" data-stop-badge="${side}" data-svg-x="${formatPreviewNumber(svgX)}" data-svg-y="${formatPreviewNumber(svgY)}" style="${percent(svgX, svgY)}">${escapeHtml(formatPlacementCm(cm))} ${escapeHtml(translate("cm"))}</span>`
                : ""
        );
        const zeros = {
            "Bottom Left": [0, length, "bottom-left"],
            "Bottom Right": [width, length, "bottom-right"],
            "Top Left": [0, 0, "top-left"],
            "Top Right": [width, 0, "top-right"],
        };
        const zero = zeros[placement.work_zero_position] || zeros["Bottom Left"];
        const rightGap = Math.max(0, width - offsetX - sheetW);
        const topEdge = length - offsetY - sheetL;
        return `<div class="dco-cnc-cut-preview__placement-overlay" data-placement-overlay data-work-zero="${escapeHtml(String(placement.work_zero_position || ""))}">
            <svg class="dco-cnc-cut-preview__measure" data-measure-layer viewBox="${escapeHtml(frameText)}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
                <defs><marker id="${escapeHtml(markerId)}" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse" markerUnits="strokeWidth"><path d="M0 1.5 L10 5 L0 8.5 Z" fill="#1d4f91"/></marker></defs>
                ${leftCm > 0 ? arrow("left", 0, midY, offsetX, midY) : ""}
                ${rightCm > 0 ? arrow("right", offsetX + sheetW, midY, width, midY) : ""}
                ${bottomCm > 0 ? arrow("bottom", midX, length, midX, length - offsetY) : ""}
                ${topCm > 0 ? arrow("top", midX, topEdge, midX, 0) : ""}
            </svg>
            ${badge("left", leftCm, offsetX / 2, midY)}
            ${badge("right", rightCm, offsetX + sheetW + rightGap / 2, midY)}
            ${badge("bottom", bottomCm, midX, length - offsetY / 2)}
            ${badge("top", topCm, midX, topEdge / 2)}
            <span class="dco-cnc-cut-preview__zero-label" data-work-zero-label="1" data-zero-anchor="${zero[2]}" data-svg-x="${formatPreviewNumber(zero[0])}" data-svg-y="${formatPreviewNumber(zero[1])}" style="${percent(zero[0], zero[1])}">(0,0)</span>
        </div>`;
    }

    function syncPlacementOverlay(host, svg) {
        if (!host || !svg || typeof host.querySelector !== "function" || typeof svg.getAttribute !== "function") return;
        const overlay = host.querySelector("[data-placement-overlay]");
        const measure = host.querySelector("[data-measure-layer]");
        if (!overlay || !measure) return;
        const boxText = String(svg.getAttribute("viewBox") || "");
        const parts = boxText.trim().split(/\s+/).map(Number);
        if (parts.length !== 4 || !(parts[2] > 0) || !(parts[3] > 0)) return;
        if (typeof measure.setAttribute === "function") measure.setAttribute("viewBox", boxText);
        overlay.querySelectorAll("[data-svg-x]").forEach(node => {
            const svgX = Number(node.getAttribute("data-svg-x"));
            const svgY = Number(node.getAttribute("data-svg-y"));
            if (!Number.isFinite(svgX) || !Number.isFinite(svgY) || !node.style) return;
            node.style.left = `${((svgX - parts[0]) / parts[2]) * 100}%`;
            node.style.top = `${((svgY - parts[1]) / parts[3]) * 100}%`;
        });
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
        const assignedVectorIds = new Set((options.assignedVectorIds || []).map(String));
        const activeOperation = String(options.activeOperation || "");
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
        const pageLayout = String(options.layout || "") === "page";
        const frame = cutPreviewViewBox(width, length, physicalPaths, offsetX, offsetY);
        const frameOptions = Object.assign({}, options, { frameWidth: frame.width, frameHeight: frame.height });
        const emptyMessage = translate("No machining paths are available for this sheet preview.");
        const boardSurface = (svgInner) => {
            const stage = `<div class="dco-cnc-cut-preview__stage" data-cut-stage>
                <svg class="dco-cnc-cut-preview__svg" viewBox="${frame.text}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHtml(svgInner.aria || emptyMessage)}">
                    ${svgInner.body || ""}
                </svg>
                ${svgInner.extra || ""}
            </div>`;
            const framed = `${stage}${svgInner.overlay || ""}`;
            if (!pageLayout) return `<div class="dco-cnc-cut-preview__canvas">${framed}</div>`;
            return `<div class="dco-cnc-cut-preview__viewport" data-cut-viewport style="${cutPreviewLayoutStyle(width, length, frameOptions)};overflow:hidden;contain:paint;clip-path:inset(0 round 8px)" role="region" aria-label="${escapeHtml(translate("Board preview viewport"))}">
                <div class="dco-cnc-cut-preview__zoom" dir="ltr" role="group" aria-label="${escapeHtml(translate("Board preview viewport"))}">
                    <button type="button" class="btn btn-default btn-xs" data-cut-zoom="out" aria-label="${escapeHtml(translate("Zoom out"))}" title="${escapeHtml(translate("Zoom out"))}">−</button>
                    <button type="button" class="btn btn-default btn-xs" data-cut-zoom="reset" aria-label="${escapeHtml(translate("Fit to view"))}" title="${escapeHtml(translate("Fit to view"))}">100%</button>
                    <button type="button" class="btn btn-default btn-xs" data-cut-zoom="in" aria-label="${escapeHtml(translate("Zoom in"))}" title="${escapeHtml(translate("Zoom in"))}">+</button>
                </div>
                ${framed}
            </div>`;
        };
        const previewShellStyle = pageLayout
            ? "inline-size:100%;min-inline-size:0;"
            : cutPreviewLayoutStyle(width, length, frameOptions);

        if (!(width > 0 && length > 0)) {
            return `<div class="dco-cnc-cut-preview" role="status" data-marker-scope="${escapeHtml(markerScope)}">
                <p class="dco-operational-files__note">${escapeHtml(emptyMessage)}</p>
            </div>`;
        }

        if (!physicalPaths.length) {
            return `<div class="dco-cnc-cut-preview" role="status" data-marker-scope="${escapeHtml(markerScope)}" style="${previewShellStyle}">
                ${boardSurface({
                    aria: emptyMessage,
                })}
                <p class="dco-operational-files__note">${escapeHtml(emptyMessage)}</p>
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
            const vectorId = String(item.vector_id || "");
            const inspected = selectedExecutionPathId && item.execution_path_id === selectedExecutionPathId;
            const assigned = assignedVectorIds.has(vectorId);
            const picked = !assigned && selectedVectorIds.has(vectorId);
            const layerActive = !picked && !assigned && activeOperation && item.operation_key === activeOperation;
            const displayGeometry = !item.ready && Array.isArray(item.display_paths) && item.display_paths.length
                ? " is-dxf-display-geometry"
                : "";
            const selected = `${inspected ? " is-cnc-path-selected" : ""}${picked ? " is-vector-picked" : ""}${assigned ? " is-assigned" : ""}${layerActive ? " is-layer-active" : ""}${displayGeometry}`;
            const markerId = `${markerScope}-arrow-${item.path_number}`;
            const color = PROGRAM_COLORS[item.operation_key] || "#333";
            const visiblePaths = previewPathSets(item);
            const arrow = cutExecutionArrowSegment(visiblePaths[0] || [], false);
            const depths = item.passes
                .map(pass => (pass.depth_mm == null ? "" : String(pass.depth_mm)))
                .filter(Boolean)
                .join(",");
            const arrowLine = arrow
                ? `<polyline class="dco-cnc-cut-preview__arrow" data-path-number="${item.path_number}" data-execution-path-id="${escapeHtml(item.execution_path_id)}" data-execution-path="${escapeHtml(item.path_key)}" data-operation-key="${escapeHtml(item.operation_key)}" points="${Number(arrow.from[0])},${Number(arrow.from[1])} ${Number(arrow.to[0])},${Number(arrow.to[1])}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke" marker-end="url(#${escapeHtml(markerId)})"/>`
                : "";
            const visibleStrokes = visiblePaths.map(path => {
                const points = path.map(point => `${Number(point[0])},${Number(point[1])}`).join(" ");
                return `<polyline class="dco-cnc-cut-preview__hit" data-vector-id="${escapeHtml(vectorId)}" data-execution-path="${escapeHtml(item.path_key)}" data-shape-id="${escapeHtml(item.shape_id || "")}" data-execution-path-id="${escapeHtml(item.execution_path_id)}" points="${points}" fill="none" stroke="transparent" stroke-width="14" vector-effect="non-scaling-stroke"/>
                <polyline class="dco-cnc-cut-preview__path" points="${points}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
            }).join("");
            return `<g class="dco-cnc-cut-preview__execution${selected}" data-path-number="${item.path_number}" data-execution-path-id="${escapeHtml(item.execution_path_id)}" data-execution-path="${escapeHtml(item.path_key)}" data-shape-id="${escapeHtml(item.shape_id || "")}" data-vector-id="${escapeHtml(vectorId)}" data-operation-key="${escapeHtml(item.operation_key)}" data-pass-count="${item.pass_count}" data-depth-mm="${escapeHtml(depths)}">
                ${visibleStrokes}
                ${arrowLine}
            </g>`;
        }).join("");
        const sheetW = sheetWidth > 0 ? sheetWidth : width;
        const sheetL = sheetLength > 0 ? sheetLength : length;
        const voidFill = pageLayout ? "" : ' fill="#dbeafe"';
        const machineFrame = placement
            ? `<rect class="dco-cnc-cut-preview__machine" x="0" y="0" width="${width}" height="${length}"${pageLayout ? ' fill="none"' : ' fill="#f3f4f6" stroke="#111827" stroke-width="1.5"'}/>
                <rect class="dco-cnc-cut-preview__void" x="0" y="0" width="${Math.max(0, offsetX)}" height="${length}"${voidFill}/>
                <rect class="dco-cnc-cut-preview__void" x="0" y="0" width="${width}" height="${Math.max(0, offsetY)}"${voidFill}/>
                <rect class="dco-cnc-cut-preview__void" x="${offsetX + sheetW}" y="0" width="${Math.max(0, width - offsetX - sheetW)}" height="${length}"${voidFill}/>
                <rect class="dco-cnc-cut-preview__void" x="0" y="${offsetY + sheetL}" width="${width}" height="${Math.max(0, length - offsetY - sheetL)}"${voidFill}/>
                <rect class="dco-cnc-cut-preview__sheet" x="${offsetX}" y="${offsetY}" width="${sheetW}" height="${sheetL}"${pageLayout ? ' fill="none"' : ' fill="#fff7ed"'}/>`
            : "";
        const overlay = placementOverlayMarkup(placement, {
            width,
            length,
            offsetX,
            offsetY,
            sheetW,
            sheetL,
            frameText: frame.text,
            markerScope,
        });
        const sheetWindowY = length - offsetY - sheetL;
        const gridPatternId = `${markerScope}-sheet-grid`;
        const showSheetHatch = pageLayout && sheetW > 0 && sheetL > 0;
        const gridPattern = showSheetHatch
            ? `<pattern id="${escapeHtml(gridPatternId)}" data-sheet-grid-pattern patternUnits="userSpaceOnUse" patternTransform="rotate(45)" width="8" height="8"><line class="dco-cnc-cut-preview__grid-line" x1="0" y1="0" x2="0" y2="8" fill="none" stroke="rgba(71,85,105,.18)" stroke-width="1" pointer-events="none"/></pattern>`
            : "";
        const machineBed = pageLayout && placement
            ? `<rect class="dco-cnc-cut-preview__machine-bed" x="0" y="0" width="${formatPreviewNumber(width)}" height="${formatPreviewNumber(length)}" fill="#e4e8ef" pointer-events="none"/>`
            : "";
        const sheetWindow = showSheetHatch
            ? `<rect class="dco-cnc-cut-preview__board-fill" data-sheet-window="1" x="${formatPreviewNumber(offsetX)}" y="${formatPreviewNumber(sheetWindowY)}" width="${formatPreviewNumber(sheetW)}" height="${formatPreviewNumber(sheetL)}" fill="#ffffff" pointer-events="none"/>
                    <rect class="dco-cnc-cut-preview__board-grid" x="${formatPreviewNumber(offsetX)}" y="${formatPreviewNumber(sheetWindowY)}" width="${formatPreviewNumber(sheetW)}" height="${formatPreviewNumber(sheetL)}" fill="url(#${escapeHtml(gridPatternId)})" pointer-events="none"/>`
            : "";
        const pieceMarkup = pageLayout ? previewBoardPiecesMarkup(options, sheetL) : "";
        const sheetGroup = `<g data-sheet-geometry transform="translate(${offsetX},${offsetY})">${pieceMarkup}${strokes}<g data-path-markers></g></g>`;

        return `<div class="dco-cnc-cut-preview" data-marker-scope="${escapeHtml(markerScope)}" style="${previewShellStyle}">
            ${boardSurface({
                aria: translate("Machining preview"),
                extra: "",
                overlay,
                body: `<defs>${markers}${gridPattern}</defs>
                    ${machineBed}
                    ${sheetWindow}
                    <g transform="translate(0,${length}) scale(1,-1)">
                        ${machineFrame}
                        ${sheetGroup}
                    </g>`,
            })}
            ${pageLayout ? "" : notes.map(note => `<p class="dco-operational-files__note" role="status">${escapeHtml(note)}</p>`).join("")}
        </div>`;
    }

    function syncBoardGrid(host, svg) {
        const pattern = svg && typeof svg.querySelector === "function"
            ? svg.querySelector("[data-sheet-grid-pattern]")
            : null;
        if (!pattern || typeof svg.getBoundingClientRect !== "function" || !svg.viewBox || !svg.viewBox.baseVal) return;
        const client = svg.getBoundingClientRect();
        const view = svg.viewBox.baseVal;
        if (!(client.width > 0) || !(client.height > 0) || !(view.width > 0) || !(view.height > 0)) return;
        const scale = Math.min(client.width / view.width, client.height / view.height);
        if (!(scale > 0)) return;
        const period = 8 / scale;
        const stroke = 1 / scale;
        pattern.setAttribute("width", formatPreviewNumber(period));
        pattern.setAttribute("height", formatPreviewNumber(period));
        const line = pattern.querySelector("line");
        if (line && typeof line.setAttribute === "function") {
            line.setAttribute("x1", "0");
            line.setAttribute("y1", "0");
            line.setAttribute("x2", "0");
            line.setAttribute("y2", formatPreviewNumber(period));
            line.setAttribute("stroke-width", formatPreviewNumber(stroke));
        }
    }

    function relocatePageZoomControls(host) {
        if (!host || typeof host.closest !== "function" || typeof host.querySelector !== "function") return host;
        const preview = host.closest(".dco-operational-sheet__preview");
        const slot = preview && typeof preview.querySelector === "function"
            ? preview.querySelector("[data-cnc-preview-zoom]")
            : null;
        const zoom = host.querySelector(".dco-cnc-cut-preview__zoom");
        if (!slot || !zoom || typeof slot.replaceChildren !== "function" || zoom.parentElement === slot) return slot || host;
        slot.replaceChildren(zoom);
        return slot;
    }

    function bindCutPreviewChrome(host, options = {}) {
        if (!host || typeof host.querySelector !== "function") return;
        const zoomRoot = relocatePageZoomControls(host);
        const stage = host.querySelector("[data-cut-stage]");
        const viewport = host.querySelector("[data-cut-viewport]");
        const svg = host.querySelector(".dco-cnc-cut-preview__svg");
        if (!stage || !stage.style) return;
        const baseViewBox = (() => {
            if (!svg || typeof svg.getAttribute !== "function") return null;
            const values = String(svg.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
            if (values.length !== 4 || values.some(value => !Number.isFinite(value))
                || !(values[2] > 0 && values[3] > 0)) return null;
            return { x: values[0], y: values[1], width: values[2], height: values[3] };
        })();
        let zoom = clampCutPreviewZoom(options.initialZoom == null
            ? host.__cutPreviewZoom
            : options.initialZoom);
        let pan = normalizeCutPreviewPan(options.initialPan == null
            ? host.__cutPreviewPan
            : options.initialPan);
        const viewportSize = () => {
            if (!viewport || typeof viewport.getBoundingClientRect !== "function") return { width: 0, height: 0 };
            const bounds = viewport.getBoundingClientRect();
            return { width: Number(bounds.width) || 0, height: Number(bounds.height) || 0 };
        };
        const apply = () => {
            pan = clampCutPreviewPan(pan, zoom, viewportSize());
            host.__cutPreviewZoom = zoom;
            host.__cutPreviewPan = pan;
            if (svg && baseViewBox && typeof svg.setAttribute === "function") {
                const size = viewportSize();
                const viewWidth = baseViewBox.width / zoom;
                const viewHeight = baseViewBox.height / zoom;
                const shiftX = size.width > 0 ? (pan.x * baseViewBox.width) / (size.width * zoom) : 0;
                const shiftY = size.height > 0 ? (pan.y * baseViewBox.height) / (size.height * zoom) : 0;
                svg.setAttribute("viewBox", [
                    baseViewBox.x + (baseViewBox.width - viewWidth) / 2 - shiftX,
                    baseViewBox.y + (baseViewBox.height - viewHeight) / 2 - shiftY,
                    viewWidth,
                    viewHeight,
                ].map(formatPreviewNumber).join(" "));
                stage.style.transform = "none";
                syncPlacementOverlay(host, svg);
            } else {
                stage.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
            }
            syncBoardGrid(host, svg);
            if (typeof stage.style.setProperty === "function") {
                stage.style.setProperty("--cut-zoom", String(zoom));
            }
            if (viewport && viewport.classList) {
                viewport.classList.toggle("is-panning-enabled", zoom > 1.0001);
            }
            const out = zoomRoot.querySelector('[data-cut-zoom="out"]');
            const inside = zoomRoot.querySelector('[data-cut-zoom="in"]');
            const reset = zoomRoot.querySelector('[data-cut-zoom="reset"]');
            if (out) out.disabled = zoom <= CUT_PREVIEW_ZOOM.MIN;
            if (inside) inside.disabled = zoom >= CUT_PREVIEW_ZOOM.MAX;
            if (reset) reset.textContent = `${Math.round(zoom * 100)}%`;
        };
        const setZoom = (next, anchor) => {
            const previous = zoom;
            const target = clampCutPreviewZoom(next);
            if (target === previous) return;
            if (anchor && previous > 0) {
                const ratio = target / previous;
                pan = {
                    x: anchor.x - ratio * (anchor.x - pan.x),
                    y: anchor.y - ratio * (anchor.y - pan.y),
                };
            } else {
                pan = scaleCutPreviewPan(pan, previous, target);
            }
            zoom = target;
            apply();
        };
        const out = zoomRoot.querySelector('[data-cut-zoom="out"]');
        const inside = zoomRoot.querySelector('[data-cut-zoom="in"]');
        const reset = zoomRoot.querySelector('[data-cut-zoom="reset"]');
        if (out && typeof out.addEventListener === "function") {
            out.addEventListener("click", () => setZoom(zoom - CUT_PREVIEW_ZOOM.STEP));
        }
        if (inside && typeof inside.addEventListener === "function") {
            inside.addEventListener("click", () => setZoom(zoom + CUT_PREVIEW_ZOOM.STEP));
        }
        if (reset && typeof reset.addEventListener === "function") {
            reset.addEventListener("click", () => {
                zoom = CUT_PREVIEW_ZOOM.INITIAL;
                pan = { x: 0, y: 0 };
                apply();
            });
        }
        if (viewport && typeof viewport.addEventListener === "function") {
            viewport.addEventListener("wheel", event => {
                if (typeof event.preventDefault === "function") event.preventDefault();
                const bounds = viewport.getBoundingClientRect();
                setZoom(
                    zoom + (Number(event.deltaY) < 0 ? CUT_PREVIEW_ZOOM.STEP : -CUT_PREVIEW_ZOOM.STEP),
                    {
                        x: Number(event.clientX) - Number(bounds.left || 0) - Number(bounds.width || 0) / 2,
                        y: Number(event.clientY) - Number(bounds.top || 0) - Number(bounds.height || 0) / 2,
                    }
                );
            }, { passive: false });
            let drag = null;
            viewport.addEventListener("pointerdown", event => {
                const target = event.target;
                if (target && typeof target.closest === "function" && target.closest(".dco-cnc-cut-preview__zoom")) return;
                if (event.shiftKey || Number(event.button) !== 0 || zoom <= 1.0001) return;
                drag = {
                    x: Number(event.clientX),
                    y: Number(event.clientY),
                    pan: normalizeCutPreviewPan(pan),
                    moved: false,
                };
                if (viewport.classList) viewport.classList.add("is-panning");
                if (typeof viewport.setPointerCapture === "function" && event.pointerId != null) {
                    viewport.setPointerCapture(event.pointerId);
                }
                if (typeof event.preventDefault === "function") event.preventDefault();
            });
            viewport.addEventListener("pointermove", event => {
                if (!drag) return;
                const dx = Number(event.clientX) - drag.x;
                const dy = Number(event.clientY) - drag.y;
                if (Math.hypot(dx, dy) > 3) drag.moved = true;
                pan = { x: drag.pan.x + dx, y: drag.pan.y + dy };
                apply();
            });
            const finish = () => {
                if (!drag) return;
                host.__cutPreviewDragged = drag.moved;
                drag = null;
                if (viewport.classList) viewport.classList.remove("is-panning");
            };
            viewport.addEventListener("pointerup", finish);
            viewport.addEventListener("pointercancel", finish);
            viewport.addEventListener("click", event => {
                if (!host.__cutPreviewDragged) return;
                host.__cutPreviewDragged = false;
                if (typeof event.preventDefault === "function") event.preventDefault();
                if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
            }, true);
        }
        apply();
        if (viewport && typeof ResizeObserver === "function") {
            const observer = new ResizeObserver(() => syncBoardGrid(host, svg));
            observer.observe(viewport);
        }
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
            if (host.__cutPreviewProgram && host.innerHTML) {
                if (typeof host.setAttribute === "function") host.setAttribute("aria-busy", "true");
                return;
            }
            host.innerHTML = `<div class="dco-cnc-cut-preview" role="status"><p class="dco-operational-files__note">${escapeHtml(translate("Loading cutting paths..."))}</p></div>`;
            return;
        }
        if (status === "error") {
            if (host.__cutPreviewProgram && host.innerHTML) {
                if (typeof host.removeAttribute === "function") host.removeAttribute("aria-busy");
                if (typeof host.setAttribute === "function") host.setAttribute("data-preview-error", "true");
                return;
            }
            host.innerHTML = `<div class="dco-cnc-cut-preview" role="alert"><p class="dco-operational-files__note">${escapeHtml(translate("Cutting paths could not be loaded."))}</p></div>`;
            return;
        }
        if (typeof host.removeAttribute === "function") {
            host.removeAttribute("aria-busy");
            host.removeAttribute("data-preview-error");
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
        const boardLayout = payload.boardLayout || host.__cutBoardLayout || null;
        host.__cutBoardLayout = boardLayout;
        const sheetNo = payload.sheetNo != null
            ? payload.sheetNo
            : (host.__cutSheetNo != null
                ? host.__cutSheetNo
                : (payload.sheet && payload.sheet.sheet_no));
        host.__cutSheetNo = sheetNo;
        host.__cutPreviewPaths = collectPhysicalPaths(nextProgram);
        host.__cutPreviewWidth = Number(nextProgram.sheet_width_mm || nextProgram.machine_width_mm || 0);
        host.__cutPreviewHeight = Number(nextProgram.sheet_length_mm || nextProgram.machine_length_mm || 0);
        host.__cutPreviewSelectedExecutionPathId = payload.selectedExecutionPathId || "";
        const display = boardDisplayState(payload.sheet || host.__cutSheet, payload.state || {
            vectorSelection: payload.selectedVectorIds || host.__cutPreviewVectorIds || [],
        }, nextProgram);
        host.innerHTML = cutPathPreviewMarkup(nextProgram, {
            selectedExecutionPathId: payload.selectedExecutionPathId || "",
            selectedPathKey: payload.selectedPathKey || "",
            selectedVectorIds: payload.selectedVectorIds || host.__cutPreviewVectorIds || [],
            assignedVectorIds: payload.assignedVectorIds || Array.from(display.assigned),
            activeOperation: payload.activeOperation || display.active,
            markerScope,
            layout,
            zoom,
            hiddenOperations,
            placement,
            boardLayout,
            sheetNo,
        });
        bindCutPreviewChrome(host, { initialZoom: zoom, initialPan: pan });
        paintPathMarkers(host);
        paintAssociationVisibility(host);
    }

    function hiddenAssociationVectorIds(sheet, state, program) {
        const flags = (state && state.hiddenAssociations) || {};
        const associations = ((((sheet || {}).machining) || {}).associations || [])
            .filter(row => row && flags[row.association_id]);
        return assignedVectorIds({ machining: { associations } }, program);
    }

    function paintAssociationVisibility(preview) {
        if (!preview || typeof preview.querySelectorAll !== "function") return;
        const hidden = hiddenAssociationVectorIds(
            preview.__cutSheet,
            { hiddenAssociations: preview.__hiddenAssociations || {} },
            preview.__cutPreviewProgram
        );
        preview.querySelectorAll("[data-vector-id]").forEach(node => {
            const vectorId = node.getAttribute("data-vector-id") || "";
            node.classList.toggle("is-association-hidden", hidden.has(vectorId));
        });
    }

    function paintPathMarkers(preview) {
        if (!preview || typeof preview.querySelector !== "function") return;
        const group = preview.querySelector("[data-path-markers]");
        if (!group) return;
        const selected = String(preview.__cutPreviewSelectedExecutionPathId || "");
        const item = (preview.__cutPreviewPaths || []).find(row => row && row.execution_path_id === selected);
        if (!item || !Array.isArray(item.start)) {
            group.innerHTML = "";
            return;
        }
        const shown = previewPathSets(item)[0] || item.points;
        const start = shown[0];
        const end = previewEndPoint(shown, start, shown[shown.length - 1], false, 0);
        const marker = (className, point, color) => `<path class="${className}" d="M ${Number(point[0])} ${Number(point[1])} h 0.001" fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round" vector-effect="non-scaling-stroke" pointer-events="none"></path>`;
        group.innerHTML = marker("dco-cnc-cut-preview__start-mark", start, "#16A34A")
            + marker("dco-cnc-cut-preview__finish", end, "#DC2626");
    }

    function highlightCutPreview(preview, state) {
        if (!preview) return;
        const selected = state && state.selectedExecutionPathId ? String(state.selectedExecutionPathId) : "";
        preview.__cutPreviewSelectedExecutionPathId = selected;
        preview.querySelectorAll("[data-execution-path-id]").forEach(node => {
            node.classList.toggle(
                "is-cnc-path-selected",
                Boolean(selected) && node.getAttribute("data-execution-path-id") === selected
            );
        });
        paintPathMarkers(preview);
    }

    function physicalPathRowMarkup(path, workspace, state, canPrepare, ownsSettings, locked) {
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
        const control = locked
            ? `<span class="dco-operational-path__effective">${escapeHtml(presetLabel(workspace, selected))}</span>`
            : (!ownsSettings
            ? `<span class="dco-operational-path__effective">${escapeHtml(presetLabel(workspace, selected))}</span>`
            : (editing
                ? `<div class="dco-operational-path__preset">
                    <div data-path-preset-host="${escapeHtml(path.path_key)}"></div>
                    <button type="button" class="btn btn-default btn-xs" data-reset-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Use the layer preset"))}</button>
                   </div>`
                : `<span class="dco-operational-path__effective">${escapeHtml(presetLabel(workspace, selected))}</span>
                    ${canPrepare ? `<button type="button" class="btn btn-default btn-xs" data-customize-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Customize this path"))}</button>` : ""}`));
        const selectedClass = path.execution_path_id === state.selectedExecutionPathId ? " is-selected" : "";
        const pick = locked
            ? `<span class="dco-operational-path__pick" aria-disabled="true">
                <span class="dco-operational-path__number">${escapeHtml(path.path_number)}</span>
                ${escapeHtml(piece)}
            </span>`
            : `<button type="button" class="btn btn-link btn-xs dco-operational-path__pick" data-select-execution="${escapeHtml(path.execution_path_id)}" data-select-path="${escapeHtml(path.path_key)}">
                <span class="dco-operational-path__number">${escapeHtml(path.path_number)}</span>
                ${escapeHtml(piece)}
            </button>`;
        return `<div class="dco-operational-path${custom ? " is-custom" : ""}${selectedClass}${locked ? " is-assigned" : ""}${isSheetPerimeterPath(path) ? " is-sheet-perimeter" : ""}" data-path-key="${escapeHtml(path.path_key)}" data-execution-path-id="${escapeHtml(path.execution_path_id)}" data-path-number="${path.path_number}" data-path-operation="${escapeHtml(path.operation_key)}" data-custom="${custom ? "1" : "0"}" data-sheet-perimeter="${isSheetPerimeterPath(path) ? "1" : "0"}">
            ${pick}
            <span class="dco-operational-path__badge">${escapeHtml(translate(custom ? "Custom preset" : "Uses the layer preset"))}</span>
            ${passDetail}
            ${control}
        </div>`;
    }

    function syncPhysicalPathList(body, workspace, sheet, state, program, dialog) {
        if (!body) return;
        const physical = collectPhysicalPaths(program);
        const assigned = assignedVectorIds(sheet, program);
        state.program = program;
        const selectedPhysical = restoreSelectedPhysicalPath(state, physical);
        if (selectedPhysical && assigned.has(String(selectedPhysical.vector_id || ""))) {
            state.selectedExecutionPathId = "";
            state.selectedPathKey = "";
            state.selectedPathIdentity = null;
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
                return physicalPathRowMarkup(
                    path,
                    workspace,
                    state,
                    Boolean(workspace.can_prepare),
                    ownsSettings,
                    assigned.has(String(path.vector_id || ""))
                );
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

    function applyExecutionSelection(body, workspace, sheet, state, executionPathId, options = {}) {
        const physical = findPhysicalPath(state.program, executionPathId);
        if (!physical || physicalPathIsAssigned(sheet, physical, state.program)) return false;
        const deselect = options.toggle !== false
            && state.selectedExecutionPathId === physical.execution_path_id;
        state.selectedExecutionPathId = deselect ? "" : physical.execution_path_id;
        state.selectedPathKey = deselect ? "" : physical.path_key;
        state.selectedPathIdentity = deselect ? null : pathSelectionIdentity(physical);
        if (!deselect) expandLayerForPath(body, state, physical.operation_key);
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
        const row = deselect
            ? null
            : Array.from(body.querySelectorAll(".dco-operational-path[data-execution-path-id]"))
                .find(node => node.getAttribute("data-execution-path-id") === physical.execution_path_id);
        if (row && typeof row.scrollIntoView === "function") {
            row.scrollIntoView({ block: "nearest" });
        }
        return true;
    }

    function ensureExecutionSelection(body, workspace, sheet, state, executionPathId) {
        return applyExecutionSelection(
            body,
            workspace,
            sheet,
            state,
            executionPathId,
            { toggle: false }
        );
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
        const modeAtRequest = normalizePerimeterJoinMode(state.perimeterJoinMode);
        frappe.call({
            method: `${METHOD}.get_cnc_sheet_program`,
            args: sheetGenerateArgs(frm, workspace, sheet, state),
            callback(response) {
                if (!acceptPerimeterPreview(state, request, dialog._cncProgramPreviewRequest, modeAtRequest, (response && response.message) || {})) return;
                const liveBody = dialogRoot(dialog);
                const livePreview = liveBody && liveBody.querySelector("[data-sheet-preview]");
                if (!livePreview) return;
                livePreview.__cutSheet = sheet;
                livePreview.__hiddenAssociations = state.hiddenAssociations || {};
                const program = (response && response.message) || {};
                if (dialog._almdinaSheet) dialog._almdinaSheet.program = program;
                state.program = program;
                const physical = collectPhysicalPaths(program);
                restoreSelectedPhysicalPath(state, physical);
                syncPhysicalPathList(liveBody, workspace, sheet, state, program, dialog);
                paintCutPathPreview(livePreview, {
                    status: "ready",
                    program,
                    sheet,
                    state,
                    selectedExecutionPathId: state.selectedExecutionPathId || "",
                    selectedVectorIds: state.vectorSelection || [],
                    layout: livePreview.getAttribute("data-preview-layout") || livePreview.__cutPreviewLayout || "",
                    zoom: livePreview.__cutPreviewZoom,
                    pan: livePreview.__cutPreviewPan,
                    hiddenOperations: livePreview.__cutPreviewHidden,
                    placement: placementPreviewPayload(workspace, state),
                    boardLayout: workspace.layout || livePreview.__cutBoardLayout || null,
                    sheetNo: sheet.sheet_no,
                });
                paintBoardAppearance(liveBody, sheet, state);
                syncArtcamPerimeterSource(dialog, workspace, sheet, state);
                state.shownPreviewFailure = false;
                if (state.reportPerimeterIssues) {
                    state.reportPerimeterIssues = false;
                    const perimeter = perimeterIssues(program);
                    if (perimeter.length) {
                        showSheetIssueDialog(
                            translate("The connected sheet perimeter could not be formed."),
                            perimeter
                        );
                    }
                }
            },
            error(error) {
                if (dialog._cncProgramPreviewRequest !== request) return;
                const liveBody = dialogRoot(dialog);
                const livePreview = liveBody && liveBody.querySelector("[data-sheet-preview]");
                if (!livePreview) return;
                paintCutPathPreview(livePreview, { status: "error" });
                if (state.shownPreviewFailure) return;
                state.shownPreviewFailure = true;
                const problem = serverErrorText(error) || translate("The cutting preview could not be loaded.");
                showSheetIssueDialog(translate("The cutting preview could not be loaded."), [{
                    problem,
                    target: String((sheet && sheet.sheet_no) || ""),
                    action: translate("Open the sheet again. If this continues, the approved plan or the sheet settings need to be checked."),
                }]);
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
            drawing.nc_export_ready ? translate("NC export ready") : translate("NC export not ready"),
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
            let title = translate("{0} geometry problems block NC generation.", [items.length]);
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
                <p class="dco-cnc-program__error">${escapeHtml(translate("{0} geometry problems block NC generation.", [uniqueCount]))}</p>
                ${groupHtml}
               </div>`
            : (!geometryReady
                ? `<p class="dco-cnc-program__error" role="status">${escapeHtml(translate("Geometry is not ready, so NC generation stays disabled."))}</p>`
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

    function paintNcPanel(host, packagePayload) {
        if (!host) return;
        const payload = packagePayload || {};
        const verification = payload.verification || {};
        const summary = [
            translate("NC"),
            payload.tool_number || "",
            payload.spindle_speed_rpm ? translate("{0} RPM", [payload.spindle_speed_rpm]) : "",
            payload.path_count ? translate("{0} paths", [payload.path_count]) : "",
            payload.pass_count ? translate("{0} depth passes", [payload.pass_count]) : "",
            verification.ok ? translate("NC matches the intermediate program") : translate("NC verification failed"),
            payload.status ? statusLabel(payload.status) : "",
        ].filter(Boolean).join(" · ");
        const warnings = (payload.warnings || []).map(code => `<p class="dco-cnc-program__error">${escapeHtml(translate(String(code)))}</p>`).join("");
        host.innerHTML = `
            <p class="dco-cnc-program__note">${escapeHtml(summary)}</p>
            ${warnings}
            <p class="dco-cnc-program__note">${escapeHtml(payload.message || "")}</p>
        `;
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
                silent: true,
            });
        });
    }

    function bindGenerateNc(dialog, root, context) {
        if (!root || !context) return;
        const canPrepare = Boolean(context.canPrepare);
        const canGenerateNc = context.canGenerateNc == null
            ? canPrepare
            : Boolean(context.canGenerateNc);
        const control = generateNcControlState({
            canPrepare,
            canGenerateNc,
            sheet: context.sheet,
        });
        const generate = applyGenerateNcControl(root, control);
        if (!generate) return;
        generate.onclick = null;
        if (!canGenerateNc) return;
        generate.onclick = () => {
            if (!window.frappe || typeof frappe.call !== "function") return;
            if (dialog._cncNcInFlight) return;
            if (!canPrepare && !sheetHasTrustedNcSettings(context.sheet)) {
                frappe.msgprint(translate("Save the sheet settings before generating the NC file."));
                return;
            }
            if (canPrepare) {
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
                const machine = findCncMachine(context.workspace, context.state.cncMachine);
                if (!machine || !String(machine.post_processor || "").trim()) {
                    frappe.msgprint(translate("Complete the CNC machine settings. Choose the post processor on the machine before generating a new NC file."));
                    return;
                }
            }
            const request = (dialog._cncNcRequest || 0) + 1;
            dialog._cncNcRequest = request;
            dialog._cncNcInFlight = true;
            applyGenerateNcControl(root, {
                disabled: true,
                reason: translate("Preparing the NC file..."),
            });
            const liveWorkspace = context.workspace || {};
            const args = canPrepare
                ? sheetGenerateArgs(
                    context.frm,
                    liveWorkspace,
                    context.sheet,
                    context.state
                )
                : {
                    order_name: (context.frm && context.frm.doc && context.frm.doc.name)
                        || liveWorkspace.order_name
                        || liveWorkspace.order
                        || "",
                    sheet_no: context.sheetNo || (context.sheet && context.sheet.sheet_no),
                    viewed_plan_token: `${liveWorkspace.cutting_plan || ""}::${liveWorkspace.plan_revision || ""}`,
                };
            frappe.call({
                method: `${METHOD}.generate_cnc_sheet_nc`,
                args,
                callback(response) {
                    if (dialog._cncNcRequest !== request) return;
                    dialog._cncNcInFlight = false;
                    applyGenerateNcControl(root, generateNcControlState({
                        canPrepare,
                        canGenerateNc,
                        sheet: context.sheet,
                    }));
                    const payload = (response && response.message) || {};
                    const verification = payload.verification || {};
                    if (!payload.filename || !payload.content_b64 || verification.ok !== true) {
                        showGenerationIssueDialog(
                            { message: payload.message || translate("The NC file could not be prepared.") },
                            null,
                            context.sheetNo
                        );
                        return;
                    }
                    let downloaded = false;
                    try {
                        downloaded = downloadGeneratedNc(payload.filename, payload.content_b64);
                    } catch (error) {
                        downloaded = false;
                    }
                    if (!downloaded) {
                        showGenerationIssueDialog(
                            { message: translate("The NC file could not be prepared.") },
                            null,
                            context.sheetNo
                        );
                        return;
                    }
                    if (payload.nc_file_current && context.sheet) context.sheet.nc_file_current = true;
                    if (window.frappe && frappe.show_alert) {
                        frappe.show_alert({
                            message: translate("NC file generated successfully."),
                            indicator: "green",
                        }, 7);
                    }
                    if (context.frm) render(context.frm);
                },
                error(err) {
                    if (dialog._cncNcRequest !== request) return;
                    dialog._cncNcInFlight = false;
                    applyGenerateNcControl(root, generateNcControlState({
                        canPrepare,
                        canGenerateNc,
                        sheet: context.sheet,
                    }));
                    if (!canPrepare) {
                        if (window.frappe && typeof frappe.msgprint === "function") {
                            const fallback = translate("The NC file could not be prepared.");
                            const frontend = window.AlmdinaFrontend;
                            const message = frontend && typeof frontend.normalizeError === "function"
                                ? frontend.normalizeError(err, { fallback }).message
                                : fallback;
                            frappe.msgprint(message);
                        }
                        return;
                    }
                    loadProgramForIssues(args).then(program => {
                        if (dialog._cncNcRequest !== request) return;
                        showGenerationIssueDialog(err, program, context.sheetNo);
                    });
                },
                silent: true,
            });
        };
    }

    window.AlmdinaOperationalFilesUX = Object.freeze({
        assetRevision: ASSET_REVISION,
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
        acceptPerimeterPreview,
        physicalSheetOffsetCm,
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
        findPhysicalPathByIdentity,
        restoreSelectedPhysicalPath,
        geometryFingerprint,
        buildExecutionPathId,
        cutPathPreviewMarkup,
        cutPreviewViewBox,
        boardVectorHit,
        applyBoardVectorClick,
        paintBoardAppearance,
        assignedVectorIds,
        paintAssociationVisibility,
        showSheetIssueDialog,
        resolveBoardPointer,
        boardPointerZone,
        paintCutPathPreview,
        highlightCutPreview,
        applyExecutionSelection,
        ensureExecutionSelection,
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
        defaultSheetStops,
        placementPreviewPayload,
        syncPlacementOverlay,
        validateSheetPlacementFits,
        beginSheetMutation,
        sheetMutationIsCurrent,
        finishSheetMutation,
    });
})();
