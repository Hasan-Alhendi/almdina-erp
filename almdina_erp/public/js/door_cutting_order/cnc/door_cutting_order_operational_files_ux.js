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
        return String(message == null ? "" : message);
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

    function presetOptions(workspace, selected) {
        const presets = Array.isArray(workspace.presets) ? workspace.presets : [];
        const options = [`<option value="">${escapeHtml(translate("Not specified"))}</option>`];
        presets.forEach(preset => {
            if (!preset || (!preset.enabled && preset.name !== selected)) return;
            const name = String(preset.name || "");
            const label = `${preset.preset_name || name} · ${preset.tool_number || ""}`;
            options.push(
                `<option value="${escapeHtml(name)}"${name === selected ? " selected" : ""}>${escapeHtml(label)}</option>`
            );
        });
        if (selected && !presets.some(preset => preset && preset.name === selected)) {
            options.push(`<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}</option>`);
        }
        return options.join("");
    }

    function presetLabel(workspace, name) {
        if (!name) return translate("Not specified");
        const preset = presetByName(workspace).get(name);
        if (!preset) return name;
        return `${preset.preset_name || preset.name} · ${preset.tool_number || ""}`;
    }

    function sheetState(sheet) {
        const operations = {};
        const order = [];
        (sheet.operations || []).forEach(operation => {
            const key = String(operation.operation_key || "");
            if (!key) return;
            order.push(key);
            operations[key] = String(operation.tool_preset || "");
        });
        const overrides = {};
        (sheet.paths || []).forEach(path => {
            const preset = String(path.tool_preset || "");
            if (preset) overrides[path.path_key] = preset;
        });
        return {
            operations,
            overrides,
            order,
            confirmed: Boolean(sheet.cut_path_early_confirmed),
            expanded: {},
            selectedPathKey: "",
        };
    }

    function stateSnapshot(state) {
        return JSON.stringify({
            operations: state.order.map(key => [key, state.operations[key] || ""]),
            overrides: Object.keys(state.overrides).sort().map(key => [key, state.overrides[key] || ""]),
            order: state.order.slice(),
            confirmed: Boolean(state.confirmed) && cutPathIsEarly(state.order),
        });
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

    function historicalHtml(rows) {
        if (!Array.isArray(rows) || !rows.length) return "";
        const body = rows.map(row => `<tr>
            <td>${escapeHtml(row.cutting_plan || "")}</td>
            <td>${escapeHtml(row.plan_revision || "")}</td>
            <td>${escapeHtml(row.sheet_no || "")}</td>
            <td>${escapeHtml(statusLabel(row.status))}</td>
        </tr>`).join("");
        return `<section class="dco-operational-files__history">
            <h3>${escapeHtml(translate("Earlier operational files"))}</h3>
            <p>${escapeHtml(translate("These files stay linked to the plan revision they were prepared for."))}</p>
            <table class="dco-operational-files__table">
                <thead><tr><th>${escapeHtml(translate("Cutting plan"))}</th><th>${escapeHtml(translate("Plan revision"))}</th><th>${escapeHtml(translate("Sheet"))}</th><th>${escapeHtml(translate("Status"))}</th></tr></thead>
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
            <button type="button" class="btn btn-default btn-sm dco-operational-files__open" data-sheet-no="${escapeHtml(sheet.sheet_no)}">${escapeHtml(translate("Open sheet settings"))}</button>
        </article>`).join("");
        root.innerHTML = `<div class="dco-operational-files">
            <p class="dco-operational-files__banner" role="status">${escapeHtml(approval)} ${escapeHtml(translate("This step saves machining settings only. It does not create a machine file."))}</p>
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

    function dialogMarkup(workspace, sheet, state) {
        const canPrepare = Boolean(workspace.can_prepare);
        const disabled = canPrepare ? "" : " disabled";
        const early = cutPathIsEarly(state.order);
        const orderItems = state.order.map(key => `<li class="dco-operational-order__item" tabindex="0" draggable="${canPrepare ? "true" : "false"}" data-operation-key="${escapeHtml(key)}">
            <span class="dco-operational-order__label">${escapeHtml(operationLabel(key))}</span>
            <button type="button" class="btn btn-default btn-xs" data-move="earlier"${disabled}>${escapeHtml(translate("Move earlier"))}</button>
            <button type="button" class="btn btn-default btn-xs" data-move="later"${disabled}>${escapeHtml(translate("Move later"))}</button>
        </li>`).join("");
        const layers = state.order.map(key => {
            const operation = (sheet.operations || []).find(item => item.operation_key === key) || {};
            const paths = (sheet.paths || []).filter(path => path.operation_key === key);
            const expanded = Boolean(state.expanded[key]);
            const pathRows = paths.map(path => {
                const custom = Boolean(state.overrides[path.path_key]);
                const selected = effectivePreset(state, path);
                const reset = custom && canPrepare
                    ? `<button type="button" class="btn btn-default btn-xs" data-reset-path="${escapeHtml(path.path_key)}">${escapeHtml(translate("Use the layer preset"))}</button>`
                    : "";
                return `<div class="dco-operational-path${custom ? " is-custom" : ""}${path.path_key === state.selectedPathKey ? " is-selected" : ""}" data-path-key="${escapeHtml(path.path_key)}" data-path-operation="${escapeHtml(key)}" data-custom="${custom ? "1" : "0"}">
                    <button type="button" class="btn btn-link btn-xs dco-operational-path__pick" data-select-path="${escapeHtml(path.path_key)}">${escapeHtml(path.piece_label ? translate("Piece {0}", [path.piece_label]) : translate("Piece number is not available"))}</button>
                    <span class="dco-operational-path__badge">${escapeHtml(translate(custom ? "Custom preset" : "Uses the layer preset"))}</span>
                    <select data-path-preset="${escapeHtml(path.path_key)}"${disabled}>${presetOptions(workspace, selected)}</select>
                    ${reset}
                </div>`;
            }).join("");
            return `<article class="dco-operational-layer" data-layer="${escapeHtml(key)}">
                <header class="dco-operational-layer__head">
                    <div>
                        <strong>${escapeHtml(operationLabel(key))}</strong>
                        <code>${escapeHtml(operation.dxf_layer || "")}</code>
                        <span>${escapeHtml(translate("{0} paths", [paths.length || operation.path_count || 0]))}</span>
                    </div>
                    <label>${escapeHtml(translate("Tool preset"))}
                        <select data-operation-key="${escapeHtml(key)}"${disabled}>${presetOptions(workspace, state.operations[key] || "")}</select>
                    </label>
                </header>
                <button type="button" class="btn btn-default btn-xs" data-toggle-layer="${escapeHtml(key)}" aria-expanded="${expanded ? "true" : "false"}">${escapeHtml(translate(expanded ? "Hide paths" : "Show paths"))}</button>
                <div class="dco-operational-layer__paths"${expanded ? "" : " hidden"}>${pathRows}</div>
            </article>`;
        }).join("");
        const warning = early
            ? `<p class="dco-operational-sheet__warning" role="alert">${escapeHtml(translate("Cutting first may let the pieces move after they separate from the board."))}</p>
                <label class="dco-operational-sheet__confirm"><input type="checkbox" data-cut-confirm${state.confirmed ? " checked" : ""}${disabled}> ${escapeHtml(translate("I understand and want to keep this operation order."))}</label>`
            : "";
        return `<div class="dco-operational-sheet">
            <div class="dco-operational-sheet__preview">
                <div data-sheet-preview></div>
                <p class="dco-operational-sheet__selection" role="status">${escapeHtml(selectionText(workspace, sheet, state))}</p>
            </div>
            <div class="dco-operational-sheet__settings">
                <section>
                    <h4>${escapeHtml(translate("Operation order"))}</h4>
                    <ol class="dco-operational-order">${orderItems}</ol>
                    ${warning}
                </section>
                <section class="dco-operational-layers">${layers}</section>
            </div>
        </div>`;
    }

    function bindDialog(frm, dialog, workspace, sheet, state, board) {
        const body = dialogRoot(dialog);
        if (!body) return;
        const canPrepare = Boolean(workspace.can_prepare);
        const preview = body.querySelector("[data-sheet-preview]");
        mountBoard(preview, board);
        highlightBoard(preview, sheet, state);
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
        if (!canPrepare) return;

        body.querySelectorAll("select[data-operation-key]").forEach(select => {
            select.addEventListener("change", () => {
                const key = select.getAttribute("data-operation-key");
                state.operations[key] = select.value;
                body.querySelectorAll(`[data-path-operation="${key}"]`).forEach(row => {
                    const pathKey = row.getAttribute("data-path-key");
                    if (state.overrides[pathKey]) return;
                    const pathSelect = row.querySelector("select");
                    if (pathSelect) pathSelect.value = select.value;
                });
                refreshSelection();
            });
        });
        body.querySelectorAll("select[data-path-preset]").forEach(select => {
            select.addEventListener("change", () => {
                const pathKey = select.getAttribute("data-path-preset");
                const row = select.closest(".dco-operational-path");
                const operationKey = row.getAttribute("data-path-operation");
                const layer = state.operations[operationKey] || "";
                if (select.value && select.value !== layer) state.overrides[pathKey] = select.value;
                else delete state.overrides[pathKey];
                refreshDialog(frm, dialog, workspace, sheet, state, board);
            });
        });
        body.querySelectorAll("[data-reset-path]").forEach(button => {
            button.addEventListener("click", () => {
                delete state.overrides[button.getAttribute("data-reset-path")];
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

    function refreshDialog(frm, dialog, workspace, sheet, state, board) {
        const wrapper = dialogRoot(dialog);
        if (!wrapper) return;
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

    window.AlmdinaOperationalFilesUX = Object.freeze({
        render,
        cutPathIsEarly,
        effectivePreset,
        toolConflict,
    });
})();
