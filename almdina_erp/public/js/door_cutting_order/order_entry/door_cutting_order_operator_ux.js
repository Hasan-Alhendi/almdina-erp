(() => {
    "use strict";

    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const NUMBER_FIELDS = new Set(["width_cm", "length_cm", "qty"]);
    const CHECK_FIELDS = new Set([
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
        "edge_break",
        "edge_break_only",
        "extra_double",
        "extra_full_door_double",
        "extra_liner",
        "extra_back_groove",
        "extra_recessed_handle_cutout",
    ]);
    const RECALC_FIELDS = new Set([
        "width_cm",
        "length_cm",
        "qty",
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
        "edge_break",
        "edge_break_only",
        "edge_type",
        "piece_type",
        "notes",
        "extra_double",
        "extra_full_door_double",
        "extra_liner",
        "extra_back_groove",
        "extra_recessed_handle_cutout",
    ]);
    const CELL_LABELS = {
        row: "Row number",
        type: "Piece type",
        width: "Width (cm)",
        length: "Length (cm)",
        quantity: "Quantity",
        rotation: "Allow rotation",
        edges: "Edge sides",
        edgeType: "Edge type",
        shape: "Shape and drawing",
        area: "Area",
        edgeMeters: "Edge metres",
        notes: "Notes",
        remove: "Delete row",
    };
    let virtualSequence = 0;


    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function num(value) {
        if (value === null || value === undefined || value === "") return 0;
        return Number(String(value).replace(",", ".")) || 0;
    }

    function isEditable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0 && EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft");
    }

    function installStyles() {
        if (document.getElementById("dco-operator-ux-css")) return;
        $("head").append(`
            <style id="dco-operator-ux-css">
                .dco-operator-form .dco-ui-card {
                    border:1px solid var(--border-color,#dfe3e8); border-radius:14px; margin:12px 0;
                    padding:4px 14px 14px; background:var(--card-bg,var(--fg-color,#fff));
                    box-shadow:0 1px 2px rgba(0,0,0,.035);
                }
                .dco-operator-form .dco-ui-card > .section-head {
                    font-size:15px; font-weight:800; padding-top:12px; margin-bottom:10px;
                }
                .dco-operator-form .dco-ui-card .control-label { font-weight:650; }
                .dco-operator-form .dco-ui-card .form-control,
                .dco-operator-form .dco-ui-card .input-with-feedback { min-height:38px; border-radius:8px; }

                .dco-status-strip,.dco-board-summary {
                    display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:6px 0 14px;
                }
                .dco-board-summary { grid-template-columns:repeat(4,minmax(0,1fr)); margin-top:10px; }
                .dco-summary-tile {
                    border:1px solid var(--border-color,#dfe3e8); border-radius:12px; padding:11px 13px;
                    background:var(--subtle-fg,#f8f9fa); min-height:68px;
                }
                .dco-summary-tile .dco-label { display:block; font-size:11px; opacity:.7; margin-bottom:5px; }
                .dco-summary-tile .dco-value { display:block; font-size:14px; font-weight:800; line-height:1.45; word-break:break-word; }
                .dco-status-badge {
                    display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 9px;
                    background:var(--control-bg,#eef2f5);
                }
                .dco-status-dot { width:8px; height:8px; border-radius:50%; background:currentColor; }

                .dco-fast-entry-shell {
                    border:1px solid var(--border-color,#dfe3e8); border-radius:14px; overflow:hidden;
                    background:var(--card-bg,var(--fg-color,#fff));
                }
                .dco-fast-entry-toolbar {
                    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px 14px;
                    padding:10px 12px; background:var(--subtle-fg,#f8f9fa); border-bottom:1px solid var(--border-color,#dfe3e8);
                    font-size:12px;
                }
                .dco-fast-entry-toolbar .dco-fast-help { display:flex; align-items:center; flex-wrap:wrap; gap:6px 10px; }
                .dco-fast-entry-toolbar kbd {
                    border:1px solid var(--border-color,#ccd3da); border-bottom-width:2px; border-radius:5px;
                    padding:2px 6px; background:var(--card-bg,#fff); font-family:inherit; font-size:11px;
                }
                .dco-fast-entry-scroll { overflow:auto; max-height:68vh; }
                .dco-fast-table { width:100%; min-width:1360px; border-collapse:separate; border-spacing:0; table-layout:fixed; }
                .dco-fast-table th {
                    position:sticky; top:0; z-index:5; background:var(--card-bg,#fff); border-bottom:1px solid var(--border-color,#dfe3e8);
                    padding:8px 5px; font-size:12px; font-weight:800; text-align:center; white-space:nowrap;
                }
                .dco-fast-table td { border-bottom:1px solid var(--border-color,#edf0f2); padding:4px; vertical-align:middle; }
                .dco-fast-table tbody tr:hover { background:var(--subtle-fg,rgba(0,0,0,.02)); }
                .dco-fast-table tbody tr.dco-virtual-row { background:color-mix(in srgb, var(--alm-primary, #172033) 4%, transparent); }
                .dco-fast-table .dco-col-no { width:46px; text-align:center; font-weight:800; }
                .dco-fast-table .dco-col-number { width:92px; }
                .dco-fast-table .dco-col-qty { width:62px; }
                .dco-fast-table .dco-col-type { width:108px; }
                .dco-fast-table .dco-col-sketch { width:90px; text-align:center; }
                .dco-fast-table .dco-col-rotate { width:54px; text-align:center; }
                .dco-fast-table .dco-col-edges { width:240px; }
                .dco-fast-table .dco-col-edge-type { width:120px; }
                .dco-fast-table .dco-col-edge-bulk { width:92px; min-width:92px; max-width:92px; text-align:center; }
                .dco-fast-table .dco-col-calc { width:70px; text-align:center; font-variant-numeric:tabular-nums; }
                .dco-fast-table .dco-col-notes { width:150px; min-width:150px; }
                .dco-fast-table .dco-col-delete { width:40px; text-align:center; }
                .dco-fast-input,.dco-fast-select {
                    width:100%; min-height:38px; border:1px solid var(--border-color,#ccd3da); border-radius:8px;
                    background:var(--control-bg,#fff); padding:6px 9px; font-size:15px; outline:none;
                }
                .dco-fast-input[type="number"] { direction:ltr; text-align:center; font-variant-numeric:tabular-nums; }
                .dco-fast-input:focus,.dco-fast-select:focus {
                    border-color:var(--alm-primary,#172033); box-shadow:0 0 0 2px color-mix(in srgb, var(--alm-primary, #172033) 13%, transparent);
                }
                .dco-edge-buttons { display:grid; grid-template-columns:repeat(4,1fr); gap:4px; }
                .dco-check-toggle {
                    min-height:34px; border:1px solid var(--border-color,#ccd3da); border-radius:8px; background:var(--card-bg,#fff);
                    cursor:pointer; padding:3px 5px; font-size:11px; line-height:1.2; white-space:nowrap; user-select:none;
                    display:inline-flex; align-items:center; justify-content:center; gap:4px;
                    transition:background .08s ease,border-color .08s ease,transform .05s ease;
                }
                .dco-check-toggle:hover { border-color:var(--alm-primary,#172033); }
                .dco-check-toggle:active { transform:scale(.97); }
                .dco-check-toggle.is-checked { background:var(--alm-primary,#172033); border-color:var(--alm-primary,#172033); color:#fff; font-weight:800; }
                .dco-check-toggle:disabled { opacity:.55; cursor:not-allowed; transform:none; }
                .dco-rotate-toggle { width:40px; height:34px; padding:0; font-size:17px; }
                .dco-delete-row {
                    width:32px; height:32px; border:0; border-radius:8px; background:transparent; cursor:pointer; font-size:18px; opacity:.6;
                }
                .dco-delete-row:hover { background:rgba(210,40,40,.09); opacity:1; }
                .dco-special-sketch-button {
                    width:100%; min-height:36px; border:1px dashed rgba(111,78,55,.45); border-radius:9px;
                    background:linear-gradient(135deg,rgba(255,250,239,.95),rgba(248,239,219,.95)); color:#5d402d;
                    cursor:pointer; display:inline-flex; align-items:center; justify-content:center; gap:6px;
                    padding:5px 8px; font-size:11px; font-weight:800; transition:.15s ease;
                }
                .dco-special-sketch-button:hover { transform:translateY(-1px); border-style:solid; box-shadow:0 5px 14px rgba(83,58,40,.12); }
                .dco-special-sketch-button.is-documented { border-style:solid; border-color:rgba(31,130,82,.35); background:rgba(31,130,82,.08); color:#17643f; }
                .dco-special-sketch-button:disabled { opacity:.45; cursor:not-allowed; transform:none; box-shadow:none; }
                .dco-special-row { background:rgba(176,112,28,.035); }
                .dco-special-row .dco-col-edges,
                .dco-clipped-corner-row .dco-col-edges {
                    background:linear-gradient(135deg,rgba(255,248,229,.78),rgba(255,252,244,.42));
                }
                .dco-special-edges-disabled,
                .dco-corner-edges-summary{
                    display:flex;flex-direction:column;align-items:stretch;gap:3px;width:100%;
                    border:1px dashed rgba(176,112,28,.4);border-radius:10px;background:#fffaf0;
                    color:#8a5700;padding:6px 8px;font-size:10px;font-weight:800;line-height:1.35;
                    text-align:right;opacity:.85;
                }
                .dco-special-edges-disabled{cursor:not-allowed}
                .dco-corner-edges-summary{cursor:pointer}
                .dco-corner-edges-summary:hover{background:#fff3d6;border-color:rgba(176,112,28,.65);opacity:1}
                .dco-corner-edges-summary[disabled]{cursor:default;opacity:.7}
                .dco-special-edges-disabled small,
                .dco-corner-edges-summary small{font-weight:700;color:#a16207;opacity:.9}
                .dco-special-row select[data-field="edge_type"]:disabled{opacity:.55;cursor:not-allowed}
                .dco-fast-empty { padding:18px; text-align:center; color:var(--text-muted,#6c7680); }
                .dco-fast-readonly-note { font-weight:700; opacity:.75; }

                @media (max-width:900px) {
                    .dco-status-strip,.dco-board-summary { grid-template-columns:1fr 1fr; }
                }
                @media (max-width:600px) {
                    .dco-status-strip,.dco-board-summary { grid-template-columns:1fr; }
                }
            </style>
        `);
    }

    function renderStableHtml(field, cacheKey, html) {
        if (!field || !field.$wrapper) return false;
        const root = field.$wrapper.get(0);
        if (root && root[cacheKey] === html && field.$wrapper.children().length) {
            return false;
        }
        field.$wrapper.html(html);
        if (root) root[cacheKey] = html;
        return true;
    }

    function renderBoardSummary(frm) {
        const field = frm.fields_dict.board_summary_html;
        if (!field || !field.$wrapper) return;
        const boardDescription = String(frm.doc.board_description || "").trim();
        if (!boardDescription) {
            renderStableHtml(
                field,
                "_dcoBoardSummaryHtml",
                `<div class="dco-fast-entry-toolbar" style="margin-top:10px;border:1px solid var(--border-color,#dfe3e8);border-radius:10px">${__("Enter the board description and dimensions first.")}</div>`
            );
            return;
        }
        const lengthCm = Number(frm.doc.board_length_cm || 0);
        const widthCm = Number(frm.doc.board_width_cm || 0);
        const dimensions = lengthCm > 0 && widthCm > 0
            ? `${widthCm} × ${lengthCm} ${__("cm")}`
            : (frm.doc.full_board_width_mm && frm.doc.full_board_length_mm
                ? `${frm.doc.full_board_width_mm} × ${frm.doc.full_board_length_mm} ${__("mm")}`
                : "—");
        const tiles = [
            [__("Board Item"), boardDescription],
            [__("Full Board Size"), dimensions],
        ];
        renderStableHtml(
            field,
            "_dcoBoardSummaryHtml",
            `<div class="dco-board-summary">${tiles.map(([label,value]) => `<div class="dco-summary-tile"><span class="dco-label">${escapeHtml(label)}</span><span class="dco-value">${escapeHtml(value)}</span></div>`).join("")}</div>`
        );
    }

    function decorateSections(frm) {
        ["order_details_section","board_section","cutting_settings_section","pieces_section","totals_section","plan_section","technical_section"].forEach(fieldname => {
            const field = frm.fields_dict[fieldname];
            if (field && field.wrapper) $(field.wrapper).closest(".form-section").addClass("dco-ui-card");
        });
    }

    function rowByName(frm, name) {
        const requested = String(name || "").trim();
        const names = frappe.model && frappe.model.new_names || {};
        let current = requested;
        const visited = new Set();
        while (current && names[current] && !visited.has(current)) {
            visited.add(current);
            current = String(names[current] || "").trim();
        }
        return (frm.doc.pieces || []).find((row) => (
            row.name === requested || row.name === current
        )) || null;
    }

    function reindexPieces(frm) {
        (frm.doc.pieces || []).forEach((row, index) => {
            row.idx = index + 1;
            row.piece_no = index + 1;
        });
    }

    function createChildRow(frm) {
        const row = frappe.model.add_child(frm.doc, "Door Cutting Order Detail", "pieces");
        if (!row.qty) row.qty = 1;
        reindexPieces(frm);
        frm.dirty();
        Promise.resolve(frm.script_manager.trigger("pieces_add", row.doctype, row.name)).catch(() => {});
        return row;
    }

    function materializeVirtualRow(frm, tr) {
        // Detached rows appear when edit-session recover/replace races typing.
        // Never create a child against a wiped table row.
        if (!tr || !tr.isConnected || !isEditable(frm)) return null;
        const currentName = tr.dataset.rowName || "";
        if (!currentName.startsWith("__virtual__")) return rowByName(frm, currentName);
        const row = createChildRow(frm);
        tr.dataset.rowName = row.name;
        tr.classList.remove("dco-virtual-row");
        const no = tr.querySelector(".dco-row-number");
        if (no) no.textContent = row.idx;
        ensureSingleVirtualRow(frm);
        return row;
    }

    function localArea(row) {
        return (num(row.width_cm) * num(row.length_cm) * Math.max(0, num(row.qty))) / 10000;
    }

    function localEdgeMeters(row) {
        if ((row.piece_type || "Regular") === "Special") return 0;
        const qty = Math.max(0, num(row.qty));
        const longSides = Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left));
        const widthSides = Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom));
        return ((longSides * num(row.length_cm)) + (widthSides * num(row.width_cm))) * qty / 100;
    }

    function clearSpecialMeasurementEdges(row) {
        if (!row) return;
        row.edge_long_right = 0;
        row.edge_long_left = 0;
        row.edge_width_top = 0;
        row.edge_width_bottom = 0;
        row.edge_break = 0;
        row.edge_break_only = 0;
        row.edge_type = "";
        row.edge_long_right_type_override = "";
        row.edge_long_left_type_override = "";
        row.edge_width_top_type_override = "";
        row.edge_width_bottom_type_override = "";
    }

    function edgesCellHtml(frm, data, { editable = false, virtual = false } = {}) {
        const disabled = editable ? "" : "disabled";
        const pieceType = (data && data.piece_type) || "Regular";
        const isSpecial = pieceType === "Special";
        const cornerGeometry = window.AlmdinaClippedCornerGeometry;
        const isBreakCorner = Boolean(
            cornerGeometry
            && typeof cornerGeometry.isCornerCut === "function"
            && cornerGeometry.isCornerCut({ piece_type: pieceType })
        );
        const toggle = (field, label, extra = "") => `
            <button type="button" class="dco-check-toggle ${data && data[field] ? "is-checked" : ""} ${extra}" data-check-field="${field}" aria-pressed="${data && data[field] ? "true" : "false"}" ${disabled}>
                <span class="dco-check-mark">${data && data[field] ? "✓" : ""}</span><span>${label}</span>
            </button>`;
        if (isBreakCorner) {
            return `<button type="button" class="dco-corner-edges-summary" data-open-corner-edges="1" ${editable && !virtual ? "" : "disabled"} title="${__("Open the corner shape to choose banding sides")}">
                            <span>${escapeHtml((cornerGeometry && typeof cornerGeometry.edgeSelectionSummary === "function" && cornerGeometry.edgeSelectionSummary(data)) || (__("No banding")))}</span>
                            <small>${__("Choose banding on shape")}</small>
                        </button>`;
        }
        if (isSpecial) {
            return `<button type="button" class="dco-special-edges-disabled" disabled title="${__("Edge banding is disabled for special doors in the measurements table")}">
                            <span>${__("Unavailable")}</span>
                            <small>${__("Banding via special price")}</small>
                        </button>`;
        }
        return `<div class="dco-edge-buttons">
                    ${toggle("edge_width_top", __("Top"))}
                    ${toggle("edge_width_bottom", __("Bottom"))}
                    ${toggle("edge_long_right", __("Long R"))}
                    ${toggle("edge_long_left", __("Long L"))}
                </div>`;
    }

    function updateCalculatedCells(tr, row) {
        if (!tr || !row) return;
        const area = tr.querySelector("[data-calc='area_m2']");
        const edge = tr.querySelector("[data-calc='edge_meters']");
        if (area) area.textContent = localArea(row).toFixed(3);
        if (edge) edge.textContent = localEdgeMeters(row).toFixed(3);
        const glass = window.AlmdinaGlassShape;
        if (glass && typeof glass.syncShapeButton === "function") {
            glass.syncShapeButton(tr, row);
        }
    }

    function triggerChildField(frm, row, fieldname, delay = 0) {
        if (!row || !RECALC_FIELDS.has(fieldname)) return;
        frm._dco_fast_trigger_timers = frm._dco_fast_trigger_timers || {};
        const key = `${row.name}:${fieldname}`;
        if (frm._dco_fast_trigger_timers[key]) clearTimeout(frm._dco_fast_trigger_timers[key]);
        const run = () => {
            delete frm._dco_fast_trigger_timers[key];
            Promise.resolve(frm.script_manager.trigger(fieldname, row.doctype, row.name)).catch(error => console.error(error));
        };
        if (delay > 0) frm._dco_fast_trigger_timers[key] = setTimeout(run, delay);
        else run();
    }

    function edgeOptions(frm, selected) {
        const values = new Map();
        if (frm.doc.default_edge_type) values.set(frm.doc.default_edge_type, frm.doc.default_edge_type);
        (frm._dco_edge_types || []).forEach(item => {
            const name = item.name || item.edge_type_name;
            if (name) values.set(name, item.edge_type_name || name);
        });
        if (selected) values.set(selected, selected);
        const first = `<option value="">${__("Use default edge")}</option>`;
        return first + [...values.entries()].map(([value,label]) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
    }

    function rowHtml(frm, row, virtual = false) {
        const editable = isEditable(frm);
        const disabled = editable ? "" : "disabled";
        const name = virtual ? `__virtual__${++virtualSequence}` : row.name;
        const index = virtual ? (frm.doc.pieces || []).length + 1 : (row.idx || row.piece_no || 1);
        const data = row || { qty:1 };
        const pieceType = data.piece_type || "Regular";
        const isSpecial = pieceType === "Special";
        const cornerGeometry = window.AlmdinaClippedCornerGeometry;
        const isClipped = Boolean(cornerGeometry && cornerGeometry.isCornerCut({ piece_type: pieceType }));
        const extraAddons = window.AlmdinaExtraDoorAddonsUX;
        const labels = Object.fromEntries(
            Object.entries(CELL_LABELS).map(([key, message]) => [key, __(message)])
        );
        const toggle = (field, label, extra = "") => `
            <button type="button" class="dco-check-toggle ${data[field] ? "is-checked" : ""} ${extra}" data-check-field="${field}" aria-pressed="${data[field] ? "true" : "false"}" ${disabled}>
                <span class="dco-check-mark">${data[field] ? "✓" : ""}</span><span>${label}</span>
            </button>`;
        const shapeOutput = window.AlmdinaShapeOutputContract;
        const hasDrawing = Boolean(
            shapeOutput
            && shapeOutput.drawingFromPiece(data)
        );
        const hasExactGeometry = Boolean(
            isSpecial
            && shapeOutput
            && shapeOutput.hasExactCutPath(data)
        );
        const cornerSummary = isClipped && cornerGeometry
            ? cornerGeometry.summary(data)
            : "";
        const glassApi = window.AlmdinaGlassShape;
        const glassState = glassApi && typeof glassApi.shapeButtonState === "function"
            ? glassApi.shapeButtonState(data, { editable, virtual })
            : null;
        const shapeIcon = glassState
            ? glassState.icon
            : (isClipped
                ? (cornerGeometry && cornerGeometry.typeIcon(data)) || "⌑"
                : ((hasDrawing || hasExactGeometry) ? "✓" : "✎"));
        const shapeLabel = glassState
            ? glassState.label
            : (isClipped
                ? (__("Set"))
                : ((hasDrawing || hasExactGeometry)
                    ? (__("Documented"))
                    : (__("Document"))));
        const shapeTitle = glassState
            ? glassState.title
            : (isClipped
                ? `${__("Configure {0}", [cornerGeometry ? cornerGeometry.typeLabel(data) : __("corner")])}${cornerSummary ? ` — ${cornerSummary}` : ""}`
                : (__("Open image, measurements and notes documentation")));
        const shapeEnabled = glassState
            ? glassState.enabled
            : ((isSpecial || isClipped) && editable && !virtual);
        const nativePieceTypeSelect = `<select class="dco-fast-select" data-field="piece_type" ${disabled}>
            <option value="Regular" ${pieceType === "Regular" ? "selected" : ""}>${__("Regular")}</option>
            <option value="Special" ${pieceType === "Special" ? "selected" : ""}>${__("Special")}</option>
            <option value="Clipped Corner" ${pieceType === "Clipped Corner" ? "selected" : ""}>${__("Clipped corner")}</option>
            <option value="L-Shaped Corner" ${pieceType === "L-Shaped Corner" ? "selected" : ""}>${__("L-shaped corner")}</option>
            <option value="Glass" ${pieceType === "Glass" ? "selected" : ""}>${__("Glass")}</option>
        </select>`;
        const pieceTypeControl = extraAddons && typeof extraAddons.renderTypePicker === "function"
            ? extraAddons.renderTypePicker(data, { editable, virtual })
            : nativePieceTypeSelect;
        const edgeTypeDisabled = (!editable || isSpecial) ? "disabled" : "";
        return `
            <tr data-row-name="${escapeHtml(name)}" class="${virtual ? "dco-virtual-row" : ""} ${isSpecial ? "dco-special-row" : ""} ${isClipped ? "dco-clipped-corner-row" : ""}">
                <td class="dco-col-no" data-label="${labels.row}"><span class="dco-row-number">${index}</span></td>
                <td class="dco-col-type" data-label="${labels.type}">${pieceTypeControl}</td>
                <td class="dco-col-number dco-col-width" data-label="${labels.width}"><input class="dco-fast-input" type="number" inputmode="decimal" step="any" min="0" data-field="width_cm" value="${virtual ? "" : escapeHtml(data.width_cm || "")}" ${disabled}></td>
                <td class="dco-col-number dco-col-length" data-label="${labels.length}"><input class="dco-fast-input" type="number" inputmode="decimal" step="any" min="0" data-field="length_cm" value="${virtual ? "" : escapeHtml(data.length_cm || "")}" ${disabled}></td>
                <td class="dco-col-qty" data-label="${labels.quantity}"><input class="dco-fast-input" type="number" inputmode="numeric" step="1" min="1" data-field="qty" value="${virtual ? "1" : escapeHtml(data.qty || 1)}" ${disabled}></td>
                <td class="dco-col-rotate" data-label="${labels.rotation}">${toggle("allow_rotation", "↻", "dco-rotate-toggle")}</td>
                <td class="dco-col-edges" data-label="${labels.edges}">${edgesCellHtml(frm, data, { editable, virtual })}</td>
                <td class="dco-col-edge-type" data-label="${labels.edgeType}"><select class="dco-fast-select" data-field="edge_type" ${edgeTypeDisabled}>${edgeOptions(frm, virtual || isSpecial ? "" : (data.edge_type || ""))}</select></td>
                <td class="dco-col-edge-bulk" data-label="${__("Apply to all four")}"></td>
                <td class="dco-col-sketch" data-label="${labels.shape}"><button type="button" class="dco-special-sketch-button ${!glassState && (hasDrawing || hasExactGeometry) ? "is-documented" : ""} ${!glassState && hasExactGeometry ? "is-exact-geometry" : ""} ${!glassState && isClipped ? "is-clipped-corner" : ""} ${glassState ? "is-glass" : ""} ${glassState && glassState.incomplete ? "is-incomplete" : ""}" ${shapeEnabled ? "" : "disabled"} title="${escapeHtml(shapeTitle)}">
                    <span aria-hidden="true">${shapeIcon}</span>
                    <span>${shapeLabel}</span>
                </button></td>
                <td class="dco-col-calc" data-label="${labels.area}" data-calc="area_m2">${virtual ? "0.000" : localArea(data).toFixed(3)}</td>
                <td class="dco-col-calc" data-label="${labels.edgeMeters}" data-calc="edge_meters">${virtual ? "0.000" : localEdgeMeters(data).toFixed(3)}</td>
                ${extraAddons && typeof extraAddons.renderAddonSummary === "function"
                    ? `<td class="dco-col-addons" data-label="${escapeHtml(__("Add-ons"))}">${extraAddons.renderAddonSummary(data, { editable })}</td>`
                    : ""}
                <td class="dco-col-notes" data-label="${labels.notes}"><input class="dco-fast-input" type="text" data-field="notes" value="${virtual ? "" : escapeHtml(data.notes || "")}" ${disabled}></td>
                <td class="dco-col-delete" data-label="${labels.remove}">${editable && !virtual ? `<button type="button" class="dco-delete-row" title="${__("Delete row")}">×</button>` : ""}</td>
            </tr>`;
    }

    function shellDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const dir = document.documentElement && document.documentElement.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function shellHtml(frm) {
        const editable = isEditable(frm);
        const extraAddons = window.AlmdinaExtraDoorAddonsUX;
        const visit = documentContext()?.capture?.(frm);
        const rows = (frm.doc.pieces || []).map(row => rowHtml(frm, row, false)).join("");
        const virtual = editable ? rowHtml(frm, { qty:1 }, true) : "";
        return `
            <div class="dco-fast-entry-shell" data-almdina-order="${escapeHtml(frm.doc.name || "")}" data-almdina-generation="${Number(visit?.generation || 0)}" dir="${shellDirection()}">
                <div class="dco-fast-entry-toolbar">
                    <div class="dco-fast-help">
                        <b>${__("Fast entry:")}</b>
                        <span class="dco-keyboard-flow">${__("Width")} → <kbd>Tab</kbd> → ${__("Length")} → <kbd>Enter</kbd> → ${__("next width immediately")}</span>
                        <span class="dco-help-secondary">${__("Edges and rotation toggle in one click without activating a row.")}</span>
                        <span class="dco-help-secondary">${__("For a special door, edge sides are disabled in the table; banding is handled via the special price.")}</span>
                        <span class="dco-help-secondary">${__("Add-ons are available for every type; Double and Full Door Double are mutually exclusive.")}</span>
                    </div>
                    ${editable ? "" : `<span class="dco-fast-readonly-note">${__("Read only")}</span>`}
                </div>
                <div class="dco-fast-entry-scroll">
                    <table class="dco-fast-table">
                        <thead><tr>
                            <th class="dco-col-no">#</th>
                            <th class="dco-col-type">${__("Piece type")}</th>
                            <th class="dco-col-number">${__("Width (CM)")}</th>
                            <th class="dco-col-number">${__("Length (CM)")}</th>
                            <th class="dco-col-qty">${__("Qty")}</th>
                            <th class="dco-col-rotate">${__("Rotate")}</th>
                            <th class="dco-col-edges">${__("Edge sides")}</th>
                            <th class="dco-col-edge-type">${__("Edge type")}</th>
                            <th class="dco-col-edge-bulk">${__("Apply to all four")}</th>
                            <th class="dco-col-sketch">${__("Shape")}</th>
                            <th class="dco-col-calc">${__("Area")}</th>
                            <th class="dco-col-calc">${__("Edge m")}</th>
                            <th class="dco-col-addons">${__("Add-ons")}</th>
                            <th class="dco-col-notes">${__("Notes")}</th>
                            <th class="dco-col-delete"></th>
                        </tr></thead>
                        <tbody>${rows}${virtual}</tbody>
                    </table>
                </div>
            </div>`;
    }

    function ensureSingleVirtualRow(frm) {
        if (!isEditable(frm)) return;
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const tbody = field.$wrapper.find(".dco-fast-table tbody").get(0);
        if (!tbody) return;
        const virtualRows = tbody.querySelectorAll("tr.dco-virtual-row");
        if (virtualRows.length === 0) tbody.insertAdjacentHTML("beforeend", rowHtml(frm, { qty:1 }, true));
        for (let i = 1; i < virtualRows.length; i++) virtualRows[i].remove();
    }

    function refreshEdgeSelects(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        field.$wrapper.find("select[data-field='edge_type']").each(function () {
            const tr = this.closest("tr[data-row-name]");
            const row = tr ? rowByName(frm, tr.dataset.rowName || "") : null;
            const special = Boolean(row && (row.piece_type || "Regular") === "Special");
            const current = special ? "" : this.value;
            this.innerHTML = edgeOptions(frm, current);
            this.value = current;
            this.disabled = !isEditable(frm) || special;
        });
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function loadEdgeTypes(frm) {
        if (frm._dco_edge_types_loaded) return Promise.resolve(true);
        const context = documentContext();
        const token = context && typeof context.capture === "function"
            ? context.capture(frm)
            : null;
        const active = frm.__almdinaEdgeTypesRequest;
        if (
            active
            && (
                !context
                || typeof context.isSameDocument !== "function"
                || context.isSameDocument(frm, active.token)
            )
        ) {
            return active.promise;
        }

        const requestState = { token, promise: null };
        frm.__almdinaEdgeTypesRequest = requestState;
        frm._dco_edge_types_loading = true;
        const request = Promise.resolve(frappe.db.get_list("Edge Banding Type", {
            fields:["name","edge_type_name"],
            filters:{ disabled:0 },
            order_by:"width_cm asc, edge_type_name asc",
            limit:100,
        })).then(rows => {
            if (frm.__almdinaEdgeTypesRequest !== requestState) return false;
            if (context && !context.isCurrent(frm, token)) return false;
            frm._dco_edge_types = rows || [];
            frm._dco_edge_types_loaded = true;
            refreshEdgeSelects(frm);
            return true;
        }).catch(error => {
            if (!context || context.isCurrent(frm, token)) {
                console.error("Failed to load edge types", error);
            }
            return false;
        }).finally(() => {
            if (frm.__almdinaEdgeTypesRequest === requestState) {
                frm.__almdinaEdgeTypesRequest = null;
                frm._dco_edge_types_loading = false;
            }
        });
        requestState.promise = request;
        return request;
    }

    function renderFastMeasurements(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        reindexPieces(frm);
        const html = shellHtml(frm);
        const root = field.$wrapper.get(0);
        const force = Boolean(
            field.$wrapper._dcoForceHtmlReplace
            || (root && root._dcoForceHtmlReplace)
        );
        field.$wrapper._dcoForceHtmlReplace = false;
        if (root) root._dcoForceHtmlReplace = false;
        if (
            force
            || !root
            || root._dcoFastEntryHtml !== html
            || !field.$wrapper.find(".dco-fast-table").length
        ) {
            field.$wrapper.html(html);
            if (root) root._dcoFastEntryHtml = html;
        }
        bindFastMeasurements(frm);
        const extraAddons = window.AlmdinaExtraDoorAddonsUX;
        if (extraAddons && typeof extraAddons.bindTable === "function") {
            extraAddons.bindTable(frm, root);
        }
        loadEdgeTypes(frm);
        const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
        if (measurementLifecycle && typeof measurementLifecycle.rendered === "function") {
            measurementLifecycle.rendered(frm);
        }
    }

    function captureMeasurementView(root) {
        if (!root) return null;
        const focused = document.activeElement;
        const active = focused && root.contains(focused) ? focused : null;
        const row = active && typeof active.closest === "function"
            ? active.closest("tr[data-row-name]")
            : null;
        const scroller = root.querySelector(".dco-fast-entry-scroll");
        const page = document.scrollingElement;
        return {
            rowName: row && row.dataset ? row.dataset.rowName : "",
            fieldName: active && active.dataset ? active.dataset.field : "",
            selectionStart: active && Number.isInteger(active.selectionStart)
                ? active.selectionStart
                : null,
            selectionEnd: active && Number.isInteger(active.selectionEnd)
                ? active.selectionEnd
                : null,
            tableTop: scroller ? scroller.scrollTop : 0,
            tableLeft: scroller ? scroller.scrollLeft : 0,
            pageTop: page ? page.scrollTop : 0,
            pageLeft: page ? page.scrollLeft : 0,
        };
    }

    function restoreMeasurementView(root, state) {
        if (!root || !state) return;
        let control = null;
        if (state.rowName && state.fieldName) {
            const row = Array.from(root.querySelectorAll("tr[data-row-name]")).find(candidate => (
                candidate.dataset && candidate.dataset.rowName === state.rowName
            ));
            control = row && Array.from(row.querySelectorAll("[data-field]")).find(candidate => (
                candidate.dataset && candidate.dataset.field === state.fieldName
            ));
        }
        if (control && typeof control.focus === "function") {
            control.focus({ preventScroll: true });
            if (
                state.selectionStart !== null
                && state.selectionEnd !== null
                && typeof control.setSelectionRange === "function"
            ) {
                control.setSelectionRange(state.selectionStart, state.selectionEnd);
            }
        }

        const scroller = root.querySelector(".dco-fast-entry-scroll");
        if (scroller) {
            scroller.scrollTop = state.tableTop;
            scroller.scrollLeft = state.tableLeft;
        }
        if (document.scrollingElement) {
            document.scrollingElement.scrollTop = state.pageTop;
            document.scrollingElement.scrollLeft = state.pageLeft;
        }
    }

    function recoverFastMeasurements(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return false;
        const root = field.$wrapper.get(0);
        const view = captureMeasurementView(root);
        field.$wrapper._dcoForceHtmlReplace = true;
        renderFastMeasurements(frm);
        restoreMeasurementView(field.$wrapper.get(0), view);
        return true;
    }

    function getOrMaterializeRow(frm, tr) {
        if (!tr) return null;
        return materializeVirtualRow(frm, tr);
    }

    function valuesEqual(fieldname, previous, next) {
        if (NUMBER_FIELDS.has(fieldname)) return num(previous) === num(next);
        return String(previous ?? "") === String(next ?? "");
    }

    function virtualRowHasEnteredValue(tr) {
        if (!tr || !tr.classList.contains("dco-virtual-row")) return false;
        const width = tr.querySelector("input[data-field='width_cm']");
        const length = tr.querySelector("input[data-field='length_cm']");
        const notes = tr.querySelector("input[data-field='notes']");
        return num(width && width.value) > 0
            || num(length && length.value) > 0
            || String(notes && notes.value || "").trim() !== "";
    }

    function measurementInputOwned(frm, node) {
        const shell = node?.matches?.(".dco-fast-entry-shell")
            ? node : node?.closest?.(".dco-fast-entry-shell");
        if (!shell?.dataset?.almdinaOrder) return true;
        const visit = documentContext()?.capture?.(frm);
        return String(frm?.doc?.name || "") === shell.dataset.almdinaOrder
            && Number(visit?.generation || 0) === Number(shell.dataset.almdinaGeneration)
            && (!window.cur_frm || window.cur_frm === frm);
    }

    function syncInputToModel(frm, input, trigger = false) {
        if (!measurementInputOwned(frm, input)) return null;
        const tr = input.closest("tr[data-row-name]");
        const fieldname = input.dataset.field;
        if (!tr || !fieldname) return null;
        // Blurring an untouched placeholder (including its default qty=1) is
        // not a row creation. Keep note-only and partial measurement entry valid.
        if (tr.classList.contains("dco-virtual-row") && !virtualRowHasEnteredValue(tr)) {
            return null;
        }
        const row = getOrMaterializeRow(frm, tr);
        if (!row) return null;
        let value = input.value;
        if (NUMBER_FIELDS.has(fieldname)) value = num(value);
        if (fieldname === "qty") value = Math.max(1, Math.trunc(value || 1));
        if (!valuesEqual(fieldname, row[fieldname], value)) {
            row[fieldname] = value;
            frm.dirty();
        }
        updateCalculatedCells(tr, row);
        if (trigger) triggerChildField(frm, row, fieldname, 0);
        return row;
    }

    function captureCornerResizeSnapshot(tr, row) {
        const geometry = window.AlmdinaClippedCornerGeometry;
        if (!tr || !row || !geometry || typeof geometry.resizeSnapshot !== "function") return;
        if (tr._dcoCornerResizeBase) return;
        tr._dcoCornerResizeBase = geometry.resizeSnapshot(row);
    }

    function commitCornerResizeIfNeeded(frm, tr, row) {
        const geometry = window.AlmdinaClippedCornerGeometry;
        const previous = tr && tr._dcoCornerResizeBase;
        if (tr) delete tr._dcoCornerResizeBase;
        if (!row || !previous || !geometry || typeof geometry.preserveRemainingOnResize !== "function") {
            return false;
        }
        if (!geometry.preserveRemainingOnResize(row, previous)) return false;
        frm.dirty();
        const tablePerf = window.AlmdinaTablePerformanceUX;
        if (tablePerf && typeof tablePerf.refreshPieceTypeVisual === "function") {
            tablePerf.refreshPieceTypeVisual(frm, tr, row);
        }
        return true;
    }

    function flushMeasurementInputs(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        const root = field && field.$wrapper ? field.$wrapper.get(0) : null;
        if (!root || !root.querySelectorAll) return false;
        if (!measurementInputOwned(frm, root)) return false;
        let flushed = false;
        root.querySelectorAll(".dco-fast-input[data-field], .dco-fast-select[data-field]").forEach((control) => {
            const tr = control.closest("tr[data-row-name]");
            if (tr && tr.classList.contains("dco-virtual-row") && !virtualRowHasEnteredValue(tr)) return;
            if (syncInputToModel(frm, control, false)) flushed = true;
        });
        return flushed;
    }

    function focusWidth(tr) {
        if (!tr) return false;
        const input = tr.querySelector("input[data-field='width_cm']");
        if (!input) return false;
        input.focus({ preventScroll:true });
        input.select();
        return document.activeElement === input;
    }

    function requirePieceDimensions(row, tr) {
        if (num(row && row.width_cm) > 0 && num(row && row.length_cm) > 0) return true;
        frappe.msgprint({
            title: __("Enter dimensions first"),
            message: __("Enter the piece width and length before opening the shape."),
            indicator: "orange",
        });
        focusWidth(tr);
        return false;
    }

    function moveToNextWidth(frm, currentTr) {
        let next = currentTr.nextElementSibling;
        if (!next) {
            ensureSingleVirtualRow(frm);
            next = currentTr.nextElementSibling;
        }
        if (!next) return;
        // DOM insertion and focus are both synchronous: no timer, no grid refresh,
        // no server round-trip, and no simulated click.
        focusWidth(next);
        next.scrollIntoView({ block:"nearest", inline:"nearest" });
    }

    function applyCornerEdgeCheck(row, fieldname, cornerGeometry = window.AlmdinaClippedCornerGeometry) {
        if (
            !row
            || !["edge_break", "edge_break_only"].includes(fieldname)
            || !cornerGeometry
            || typeof cornerGeometry.toggleEdgeSelection !== "function"
        ) {
            return [];
        }
        const policyFields = [
            "edge_break",
            "edge_break_only",
            "edge_long_right",
            "edge_long_left",
            "edge_width_top",
            "edge_width_bottom",
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
        ];
        const previous = Object.fromEntries(
            policyFields.map((name) => [name, row[name]])
        );
        cornerGeometry.toggleEdgeSelection(row, fieldname);
        return policyFields.filter((name) => previous[name] !== row[name]);
    }

    function toggleCheck(frm, button) {
        const tr = button.closest("tr[data-row-name]");
        const fieldname = button.dataset.checkField;
        if (!tr || !CHECK_FIELDS.has(fieldname)) return;
        if (button.disabled || button.classList.contains("is-break-locked")) return;
        const row = getOrMaterializeRow(frm, tr);
        if (!row) return;
        const extraAddons = window.AlmdinaExtraDoorAddonsUX;
        const addonField = Boolean(
            extraAddons
            && extraAddons.FIELD_NAMES
            && extraAddons.FIELD_NAMES.has(fieldname)
        );
        if (
            (row.piece_type || "Regular") === "Special"
            && fieldname !== "allow_rotation"
            && !addonField
        ) {
            return;
        }
        const cornerGeometry = window.AlmdinaClippedCornerGeometry;
        if (
            !["edge_break", "edge_break_only"].includes(fieldname)
            && cornerGeometry
            && typeof cornerGeometry.locksAdjacentSidesForBreak === "function"
            && cornerGeometry.locksAdjacentSidesForBreak(row)
            && typeof cornerGeometry.breakAdjacentSides === "function"
            && cornerGeometry.breakAdjacentSides(row.clipped_corner_position).includes(fieldname)
        ) {
            return;
        }
        const machining = window.AlmdinaMachiningOverlay;
        const machiningKind = machining && typeof machining.kindForField === "function"
            ? machining.kindForField(fieldname)
            : (fieldname === "extra_liner" ? "liner" : "");
        if (
            machiningKind
            && (row.piece_type || "Regular") !== "Special"
            && window.AlmdinaLinerEditor
            && typeof window.AlmdinaLinerEditor.open === "function"
        ) {
            window.AlmdinaLinerEditor.open(frm, row, machiningKind);
            return;
        }
        if (
            ["edge_break", "edge_break_only"].includes(fieldname)
            && cornerGeometry
            && typeof cornerGeometry.toggleEdgeSelection === "function"
        ) {
            const changedFields = applyCornerEdgeCheck(row, fieldname, cornerGeometry);
            frm.dirty();
            updateCalculatedCells(tr, row);
            changedFields.forEach((name) => triggerChildField(frm, row, name, 0));
            renderFastMeasurements(frm);
            return;
        }
        const next = row[fieldname] ? 0 : 1;
        const changedFields = addonField && typeof extraAddons.enforceMutualExclusivity === "function"
            ? extraAddons.enforceMutualExclusivity(row, fieldname, next)
            : [fieldname];
        if (!addonField) row[fieldname] = next;
        frm.dirty();
        if (addonField && typeof extraAddons.syncAddonButtons === "function") {
            extraAddons.syncAddonButtons(tr, row, true);
        } else {
            button.classList.toggle("is-checked", Boolean(next));
            button.setAttribute("aria-pressed", next ? "true" : "false");
            const mark = button.querySelector(".dco-check-mark");
            if (mark) mark.textContent = next ? "✓" : "";
        }
        updateCalculatedCells(tr, row);
        changedFields.forEach(changedField => triggerChildField(frm, row, changedField, 0));
    }

    function deleteRow(frm, tr) {
        const name = tr.dataset.rowName || "";
        const row = rowByName(frm, name);
        if (!row) return;
        const index = (frm.doc.pieces || []).indexOf(row);
        if (index >= 0) frm.doc.pieces.splice(index, 1);
        try { frappe.model.clear_doc(row.doctype, row.name); } catch (error) { /* row already detached */ }
        frm.dirty();
        tr.remove();
        reindexPieces(frm);
        const field = frm.fields_dict.pieces_fast_entry;
        if (field && field.$wrapper) {
            field.$wrapper.find("tbody tr:not(.dco-virtual-row)").each(function (idx) {
                const number = this.querySelector(".dco-row-number");
                if (number) number.textContent = idx + 1;
            });
        }
        ensureSingleVirtualRow(frm);
        Promise.resolve(frm.script_manager.trigger("pieces_remove")).catch(() => {});
    }

    function openPieceAddons(frm, tr) {
        if (!frm || !tr || !isEditable(frm)) return;
        const widthInput = tr.querySelector("input[data-field='width_cm']");
        const lengthInput = tr.querySelector("input[data-field='length_cm']");
        if (tr.classList.contains("dco-virtual-row")) {
            if (!(num(widthInput && widthInput.value) > 0 && num(lengthInput && lengthInput.value) > 0)) {
                frappe.msgprint({
                    title: __("Enter dimensions first"),
                    message: __("Enter the piece width and length before editing add-ons."),
                    indicator: "orange",
                });
                focusWidth(tr);
                return;
            }
        }
        ["width_cm", "length_cm", "qty", "piece_type", "notes"].forEach((fieldname) => {
            const input = tr.querySelector(`[data-field='${fieldname}']`);
            if (input) syncInputToModel(frm, input, false);
        });
        const row = rowByName(frm, tr.dataset.rowName || "");
        const dialog = window.AlmdinaDoorAddonsDialog;
        if (row && dialog && typeof dialog.open === "function") dialog.open(frm, row);
    }

    function bindFastMeasurements(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        // Keep the live form identity even when this root is rebound after refresh.
        // Listeners must stay singular: html() replaces children, not this wrapper, so
        // re-attaching on every render would open stacked shape/corner dialogs.
        root._dcoFastEntryForm = frm;
        if (root._dcoFastMeasurementsBound) return;
        root._dcoFastMeasurementsBound = true;

        root.addEventListener("focusin", event => {
            const currentFrm = root._dcoFastEntryForm;
            const input = event.target.closest("input[data-field='width_cm'],input[data-field='length_cm']");
            if (!input || !root.contains(input) || !currentFrm) return;
            const tr = input.closest("tr[data-row-name]");
            const row = rowByName(currentFrm, tr && tr.dataset.rowName);
            if (row) captureCornerResizeSnapshot(tr, row);
        });

        root.addEventListener("input", event => {
            const currentFrm = root._dcoFastEntryForm;
            const input = event.target.closest(".dco-fast-input[data-field]");
            if (!input || !root.contains(input) || !currentFrm) return;
            syncInputToModel(currentFrm, input, false);
        });

        root.addEventListener("change", event => {
            const currentFrm = root._dcoFastEntryForm;
            const control = event.target.closest("[data-field]");
            if (!control || !root.contains(control) || !currentFrm) return;
            const row = syncInputToModel(currentFrm, control, false);
            if (row) {
                triggerChildField(currentFrm, row, control.dataset.field, 0);
                if (control.dataset.field === "piece_type") {
                    const extraAddons = window.AlmdinaExtraDoorAddonsUX;
                    if (extraAddons && typeof extraAddons.reconcilePieceType === "function") {
                        extraAddons.reconcilePieceType(currentFrm, row);
                    }
                    if ((row.piece_type || "Regular") === "Special") {
                        clearSpecialMeasurementEdges(row);
                    } else if (
                        window.AlmdinaClippedCornerGeometry
                        && typeof window.AlmdinaClippedCornerGeometry.isCornerCut === "function"
                        && window.AlmdinaClippedCornerGeometry.isCornerCut(row)
                        && typeof window.AlmdinaClippedCornerGeometry.applyEdgeBreakPolicy === "function"
                    ) {
                        window.AlmdinaClippedCornerGeometry.applyEdgeBreakPolicy(row);
                    } else {
                        row.edge_break = 0;
                        row.edge_break_only = 0;
                    }
                    renderFastMeasurements(currentFrm);
                }
            }
        });

        root.addEventListener("blur", event => {
            const currentFrm = root._dcoFastEntryForm;
            const input = event.target.closest("input[data-field='width_cm'],input[data-field='length_cm']");
            if (!input || !root.contains(input) || !currentFrm) return;
            const tr = input.closest("tr[data-row-name]");
            const row = syncInputToModel(currentFrm, input, false);
            if (!row) return;
            commitCornerResizeIfNeeded(currentFrm, tr, row);
            triggerChildField(currentFrm, row, input.dataset.field, 180);
        }, true);

        root.addEventListener("keydown", event => {
            const currentFrm = root._dcoFastEntryForm;
            const input = event.target.closest("input[data-field]");
            if (!input || !root.contains(input) || !currentFrm) return;
            const fieldname = input.dataset.field;
            const tr = input.closest("tr[data-row-name]");

            // Width -> Tab is intentionally untouched. Because this is a plain HTML
            // editor, the browser moves directly to Length with zero Frappe row activation.
            if (event.key === "Tab" && !event.shiftKey && fieldname === "width_cm") return;

            if (event.key === "Enter" && fieldname === "width_cm") {
                event.preventDefault();
                const row = syncInputToModel(currentFrm, input, false);
                if (row) commitCornerResizeIfNeeded(currentFrm, tr, row);
                const length = tr.querySelector("input[data-field='length_cm']");
                if (length) { length.focus({ preventScroll:true }); length.select(); }
                return;
            }

            if (event.key === "Enter" && fieldname === "length_cm") {
                event.preventDefault();
                event.stopPropagation();
                const row = syncInputToModel(currentFrm, input, false);
                if (row) {
                    commitCornerResizeIfNeeded(currentFrm, tr, row);
                    triggerChildField(currentFrm, row, "length_cm", 0);
                }
                moveToNextWidth(currentFrm, tr);
            }
        });

        root.addEventListener("pointerdown", event => {
            const button = event.target.closest(".dco-check-toggle,.dco-delete-row,.dco-addons-open");
            if (!button || !root.contains(button)) return;
            // No parent Frappe grid exists here, but stop pointer bubbling so no
            // surrounding form handler can turn a checkbox click into row activation.
            event.stopPropagation();
        }, true);

        root.addEventListener("click", event => {
            const currentFrm = root._dcoFastEntryForm;
            if (!currentFrm) return;
            const addonsButton = event.target.closest("[data-open-addons]");
            if (addonsButton && root.contains(addonsButton)) {
                event.preventDefault();
                event.stopPropagation();
                openPieceAddons(currentFrm, addonsButton.closest("tr[data-row-name]"));
                return;
            }
            const check = event.target.closest(".dco-check-toggle[data-check-field]");
            if (check && root.contains(check)) {
                event.preventDefault();
                event.stopPropagation();
                toggleCheck(currentFrm, check);
                return;
            }
            const del = event.target.closest(".dco-delete-row");
            if (del && root.contains(del)) {
                event.preventDefault();
                event.stopPropagation();
                deleteRow(currentFrm, del.closest("tr[data-row-name]"));
                return;
            }
            const sketch = event.target.closest(".dco-special-sketch-button, .dco-corner-edges-summary");
            if (sketch && root.contains(sketch)) {
                event.preventDefault();
                event.stopPropagation();
                const tr = sketch.closest("tr[data-row-name]");
                const row = rowByName(currentFrm, tr && tr.dataset.rowName);
                if (!row || !requirePieceDimensions(row, tr)) return;
                if (tr && tr.dataset.rowName !== row.name) tr.dataset.rowName = row.name;
                if (window.AlmdinaClippedCornerGeometry && window.AlmdinaClippedCornerGeometry.isCornerCut(row) && window.AlmdinaClippedCornerEditor) {
                    window.AlmdinaClippedCornerEditor.open(currentFrm, row);
                } else if (window.AlmdinaGlassShape && window.AlmdinaGlassShape.isGlass(row)) {
                    window.AlmdinaGlassShape.open(currentFrm, row);
                } else if (window.AlmdinaSpecialShapeEditor) {
                    window.AlmdinaSpecialShapeEditor.open(currentFrm, row);
                }
            }
        });
    }

    function pruneEmptyTrailingRows(frm) {
        const rows = frm.doc.pieces || [];
        let changed = false;
        for (let index = rows.length - 1; index >= 0; index--) {
            const row = rows[index];
            const empty = !num(row.width_cm) && !num(row.length_cm) && !String(row.notes || "").trim() &&
                !row.edge_long_right && !row.edge_long_left && !row.edge_width_top && !row.edge_width_bottom && !row.edge_type;
            if (!empty) break;
            rows.splice(index, 1);
            try { frappe.model.clear_doc(row.doctype, row.name); } catch (error) { /* no-op */ }
            changed = true;
        }
        if (changed) reindexPieces(frm);
    }

    function editSessionPhase(frm) {
        const coordinator = window.AlmdinaDcoEditSessionCoordinator;
        const snapshot = coordinator && typeof coordinator.snapshot === "function"
            ? coordinator.snapshot(frm)
            : null;
        return snapshot && snapshot.phase || "";
    }

    function refreshOperatorUI(frm) {
        installStyles();
        decorateSections(frm);
        // operator_status_strip is owned exclusively by ShopFloorOrderUX. Two
        // renderers used to replace each other after permissions/stage context
        // loaded, which made the summary cards appear, disappear, then change.
        renderBoardSummary(frm);
        renderFastMeasurements(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refreshOperatorUI(frm); },
        refresh(frm) { refreshOperatorUI(frm); },
        almdina_edit_session_changed(frm) {
            // Replacing the measurement table while Save is in-flight destroys
            // the focused cell and can swallow the original click.
            const phase = editSessionPhase(frm);
            if (phase === "saving") return;
            // Coordinator emits "starting" before the order adapter paints; skip
            // a readonly flash that would immediately be wiped again.
            if (phase === "starting") return;
            // refreshDependentUx owns a single recover for this transition.
            if (frm.__almdinaMeasurementRefreshOwned) {
                installStyles();
                decorateSections(frm);
                renderBoardSummary(frm);
                return;
            }
            refreshOperatorUI(frm);
        },
        default_edge_type(frm) { refreshEdgeSelects(frm); },
        before_save(frm) {
            flushMeasurementInputs(frm);
            pruneEmptyTrailingRows(frm);
        },
    });

    window.AlmdinaDoorCuttingFastEntry = Object.assign(
        window.AlmdinaDoorCuttingFastEntry || {},
        {
            render: renderFastMeasurements,
            recover: recoverFastMeasurements,
            flush: flushMeasurementInputs,
            loadEdgeTypes,
            clearSpecialMeasurementEdges,
            applyCornerEdgeCheck,
            edgesCellHtml,
            edgeOptions,
            isEditable,
        }
    );
})();
