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
        "edge_type",
        "notes",
    ]);
    let virtualSequence = 0;

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function num(value) {
        if (value === null || value === undefined || value === "") return 0;
        return Number(String(value).replace(",", ".")) || 0;
    }

    function isEditable(frm) {
        return frm.doc.docstatus === 0 && EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft");
    }

    function installStyles() {
        if (document.getElementById("dco-operator-ux-css")) return;
        $("head").append(`
            <style id="dco-operator-ux-css">
                .dco-operator-form .form-page,
                .dco-operator-form .form-layout,
                .dco-operator-form .layout-main-section,
                .dco-operator-form .layout-main-section-wrapper {
                    max-width:none!important;
                    width:100%!important;
                }
                .dco-operator-form .form-tabs-list { gap:8px; margin-bottom:14px; }
                .dco-operator-form .form-tabs-list .nav-link {
                    min-height:42px; padding:10px 18px!important; border-radius:10px!important; font-weight:700;
                }
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
                    direction:rtl; border:1px solid var(--border-color,#dfe3e8); border-radius:14px; overflow:hidden;
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
                .dco-fast-table { width:100%; min-width:1120px; border-collapse:separate; border-spacing:0; table-layout:fixed; }
                .dco-fast-table th {
                    position:sticky; top:0; z-index:5; background:var(--card-bg,#fff); border-bottom:1px solid var(--border-color,#dfe3e8);
                    padding:8px 5px; font-size:12px; font-weight:800; text-align:center; white-space:nowrap;
                }
                .dco-fast-table td { border-bottom:1px solid var(--border-color,#edf0f2); padding:4px; vertical-align:middle; }
                .dco-fast-table tbody tr:hover { background:var(--subtle-fg,rgba(0,0,0,.02)); }
                .dco-fast-table tbody tr.dco-virtual-row { background:rgba(36,144,239,.035); }
                .dco-fast-table .dco-col-no { width:54px; text-align:center; font-weight:800; }
                .dco-fast-table .dco-col-number { width:105px; }
                .dco-fast-table .dco-col-qty { width:70px; }
                .dco-fast-table .dco-col-rotate { width:72px; text-align:center; }
                .dco-fast-table .dco-col-edges { width:310px; }
                .dco-fast-table .dco-col-edge-type { width:160px; }
                .dco-fast-table .dco-col-calc { width:88px; text-align:center; font-variant-numeric:tabular-nums; }
                .dco-fast-table .dco-col-notes { width:160px; }
                .dco-fast-table .dco-col-delete { width:50px; text-align:center; }
                .dco-fast-input,.dco-fast-select {
                    width:100%; min-height:38px; border:1px solid var(--border-color,#ccd3da); border-radius:8px;
                    background:var(--control-bg,#fff); padding:6px 9px; font-size:15px; outline:none;
                }
                .dco-fast-input[type="number"] { direction:ltr; text-align:center; font-variant-numeric:tabular-nums; }
                .dco-fast-input:focus,.dco-fast-select:focus {
                    border-color:var(--primary,#2490ef); box-shadow:0 0 0 2px rgba(36,144,239,.13);
                }
                .dco-edge-buttons { display:grid; grid-template-columns:repeat(4,1fr); gap:4px; }
                .dco-check-toggle {
                    min-height:34px; border:1px solid var(--border-color,#ccd3da); border-radius:8px; background:var(--card-bg,#fff);
                    cursor:pointer; padding:3px 5px; font-size:11px; line-height:1.2; white-space:nowrap; user-select:none;
                    display:inline-flex; align-items:center; justify-content:center; gap:4px;
                    transition:background .08s ease,border-color .08s ease,transform .05s ease;
                }
                .dco-check-toggle:hover { border-color:var(--primary,#2490ef); }
                .dco-check-toggle:active { transform:scale(.97); }
                .dco-check-toggle.is-checked { background:var(--primary,#2490ef); border-color:var(--primary,#2490ef); color:#fff; font-weight:800; }
                .dco-check-toggle:disabled { opacity:.55; cursor:not-allowed; transform:none; }
                .dco-rotate-toggle { width:40px; height:34px; padding:0; font-size:17px; }
                .dco-delete-row {
                    width:32px; height:32px; border:0; border-radius:8px; background:transparent; cursor:pointer; font-size:18px; opacity:.6;
                }
                .dco-delete-row:hover { background:rgba(210,40,40,.09); opacity:1; }
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

    function renderStatusStrip(frm) {
        const field = frm.fields_dict.operator_status_strip;
        if (!field || !field.$wrapper) return;
        const status = __(frm.doc.status || "Draft");
        const revision = frm.doc.revision || 1;
        const plan = frm.doc.approved_plan;
        const noPlan = isArabic() ? "لم تعتمد خطة قص بعد" : "No cutting plan approved yet";
        const planValue = plan
            ? `<a href="/desk/cutting-plan/${encodeURIComponent(plan)}"><b>${escapeHtml(plan)}</b></a>`
            : escapeHtml(noPlan);
        field.$wrapper.html(`
            <div class="dco-status-strip">
                <div class="dco-summary-tile"><span class="dco-label">${__("Status")}</span><span class="dco-value"><span class="dco-status-badge"><span class="dco-status-dot"></span>${escapeHtml(status)}</span></span></div>
                <div class="dco-summary-tile"><span class="dco-label">${__("Revision")}</span><span class="dco-value">${escapeHtml(revision)}</span></div>
                <div class="dco-summary-tile"><span class="dco-label">${__("Approved Cutting Plan")}</span><span class="dco-value">${planValue}</span></div>
            </div>
        `);
    }

    function renderBoardSummary(frm) {
        const field = frm.fields_dict.board_summary_html;
        if (!field || !field.$wrapper) return;
        if (!frm.doc.board_item) {
            field.$wrapper.html(`<div class="dco-fast-entry-toolbar" style="margin-top:10px;border:1px solid var(--border-color,#dfe3e8);border-radius:10px">${isArabic() ? "اختر صنف اللوح أولًا، وستظهر هنا المادة واللون والسماكة والمقاس تلقائيًا." : "Select a board item to load its material, color, thickness and size."}</div>`);
            return;
        }
        const dimensions = frm.doc.full_board_width_mm && frm.doc.full_board_length_mm
            ? `${frm.doc.full_board_width_mm} × ${frm.doc.full_board_length_mm} ${isArabic() ? "مم" : "mm"}`
            : "—";
        const tiles = [
            [__("Board Material"), frm.doc.board_material || "—"],
            [__("Board Color"), frm.doc.board_color || "—"],
            [__("Board Thickness (MM)"), frm.doc.board_thickness_mm ? `${frm.doc.board_thickness_mm} ${isArabic() ? "مم" : "mm"}` : "—"],
            [isArabic() ? "المقاس الكامل للوح" : "Full Board Size", dimensions],
        ];
        field.$wrapper.html(`<div class="dco-board-summary">${tiles.map(([label,value]) => `<div class="dco-summary-tile"><span class="dco-label">${escapeHtml(label)}</span><span class="dco-value">${escapeHtml(value)}</span></div>`).join("")}</div>`);
    }

    function decorateSections(frm) {
        $(frm.wrapper).addClass("dco-operator-form");
        ["order_details_section","board_section","cutting_settings_section","pieces_section","totals_section","plan_section","technical_section"].forEach(fieldname => {
            const field = frm.fields_dict[fieldname];
            if (field && field.wrapper) $(field.wrapper).closest(".form-section").addClass("dco-ui-card");
        });
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
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
        const qty = Math.max(0, num(row.qty));
        const longSides = Number(Boolean(row.edge_long_right)) + Number(Boolean(row.edge_long_left));
        const widthSides = Number(Boolean(row.edge_width_top)) + Number(Boolean(row.edge_width_bottom));
        return ((longSides * num(row.length_cm)) + (widthSides * num(row.width_cm))) * qty / 100;
    }

    function updateCalculatedCells(tr, row) {
        if (!tr || !row) return;
        const area = tr.querySelector("[data-calc='area_m2']");
        const edge = tr.querySelector("[data-calc='edge_meters']");
        if (area) area.textContent = localArea(row).toFixed(3);
        if (edge) edge.textContent = localEdgeMeters(row).toFixed(3);
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
        const first = `<option value="">${isArabic() ? "القشاط الرئيسي" : "Use default edge"}</option>`;
        return first + [...values.entries()].map(([value,label]) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
    }

    function rowHtml(frm, row, virtual = false) {
        const editable = isEditable(frm);
        const disabled = editable ? "" : "disabled";
        const name = virtual ? `__virtual__${++virtualSequence}` : row.name;
        const index = virtual ? (frm.doc.pieces || []).length + 1 : (row.idx || row.piece_no || 1);
        const data = row || { qty:1 };
        const toggle = (field,label,extra="") => `
            <button type="button" class="dco-check-toggle ${data[field] ? "is-checked" : ""} ${extra}" data-check-field="${field}" aria-pressed="${data[field] ? "true" : "false"}" ${disabled}>
                <span class="dco-check-mark">${data[field] ? "✓" : ""}</span><span>${label}</span>
            </button>`;
        return `
            <tr data-row-name="${escapeHtml(name)}" class="${virtual ? "dco-virtual-row" : ""}">
                <td class="dco-col-no"><span class="dco-row-number">${index}</span></td>
                <td class="dco-col-number"><input class="dco-fast-input" type="number" inputmode="decimal" step="any" min="0" data-field="width_cm" value="${virtual ? "" : escapeHtml(data.width_cm || "")}" ${disabled}></td>
                <td class="dco-col-number"><input class="dco-fast-input" type="number" inputmode="decimal" step="any" min="0" data-field="length_cm" value="${virtual ? "" : escapeHtml(data.length_cm || "")}" ${disabled}></td>
                <td class="dco-col-qty"><input class="dco-fast-input" type="number" inputmode="numeric" step="1" min="1" data-field="qty" value="${virtual ? "1" : escapeHtml(data.qty || 1)}" ${disabled}></td>
                <td class="dco-col-rotate">${toggle("allow_rotation", "↻", "dco-rotate-toggle")}</td>
                <td class="dco-col-edges"><div class="dco-edge-buttons">
                    ${toggle("edge_long_right", isArabic() ? "طول يمين" : "Long R")}
                    ${toggle("edge_long_left", isArabic() ? "طول يسار" : "Long L")}
                    ${toggle("edge_width_top", isArabic() ? "عرض أعلى" : "Top")}
                    ${toggle("edge_width_bottom", isArabic() ? "عرض أسفل" : "Bottom")}
                </div></td>
                <td class="dco-col-edge-type"><select class="dco-fast-select" data-field="edge_type" ${disabled}>${edgeOptions(frm, virtual ? "" : (data.edge_type || ""))}</select></td>
                <td class="dco-col-calc" data-calc="area_m2">${virtual ? "0.000" : localArea(data).toFixed(3)}</td>
                <td class="dco-col-calc" data-calc="edge_meters">${virtual ? "0.000" : localEdgeMeters(data).toFixed(3)}</td>
                <td class="dco-col-notes"><input class="dco-fast-input" type="text" data-field="notes" value="${virtual ? "" : escapeHtml(data.notes || "")}" ${disabled}></td>
                <td class="dco-col-delete">${editable && !virtual ? `<button type="button" class="dco-delete-row" title="${isArabic() ? "حذف السطر" : "Delete row"}">×</button>` : ""}</td>
            </tr>`;
    }

    function shellHtml(frm) {
        const editable = isEditable(frm);
        const rows = (frm.doc.pieces || []).map(row => rowHtml(frm, row, false)).join("");
        const virtual = editable ? rowHtml(frm, { qty:1 }, true) : "";
        return `
            <div class="dco-fast-entry-shell">
                <div class="dco-fast-entry-toolbar">
                    <div class="dco-fast-help">
                        <b>${isArabic() ? "إدخال سريع:" : "Fast entry:"}</b>
                        <span>${isArabic() ? "العرض" : "Width"} → <kbd>Tab</kbd> → ${isArabic() ? "الطول" : "Length"} → <kbd>Enter</kbd> → ${isArabic() ? "العرض التالي فورًا" : "next width immediately"}</span>
                        <span>${isArabic() ? "القشاط والتدوير: نقرة واحدة مباشرة دون تفعيل السطر." : "Edges and rotation toggle in one click without activating a row."}</span>
                    </div>
                    ${editable ? "" : `<span class="dco-fast-readonly-note">${isArabic() ? "الطلب للعرض فقط" : "Read only"}</span>`}
                </div>
                <div class="dco-fast-entry-scroll">
                    <table class="dco-fast-table">
                        <thead><tr>
                            <th class="dco-col-no">#</th>
                            <th class="dco-col-number">${isArabic() ? "العرض (سم)" : "Width (CM)"}</th>
                            <th class="dco-col-number">${isArabic() ? "الطول (سم)" : "Length (CM)"}</th>
                            <th class="dco-col-qty">${isArabic() ? "العدد" : "Qty"}</th>
                            <th class="dco-col-rotate">${isArabic() ? "تدوير" : "Rotate"}</th>
                            <th class="dco-col-edges">${isArabic() ? "جهات القشاط" : "Edge sides"}</th>
                            <th class="dco-col-edge-type">${isArabic() ? "نوع القشاط" : "Edge type"}</th>
                            <th class="dco-col-calc">${isArabic() ? "المساحة" : "Area"}</th>
                            <th class="dco-col-calc">${isArabic() ? "متر قشاط" : "Edge m"}</th>
                            <th class="dco-col-notes">${isArabic() ? "ملاحظات" : "Notes"}</th>
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
            const current = this.value;
            this.innerHTML = edgeOptions(frm, current);
            this.value = current;
        });
    }

    function loadEdgeTypes(frm) {
        if (frm._dco_edge_types_loaded || frm._dco_edge_types_loading) return;
        frm._dco_edge_types_loading = true;
        frappe.db.get_list("Edge Banding Type", {
            fields:["name","edge_type_name"],
            filters:{ disabled:0 },
            order_by:"width_cm asc, edge_type_name asc",
            limit:100,
        }).then(rows => {
            frm._dco_edge_types = rows || [];
            frm._dco_edge_types_loaded = true;
            refreshEdgeSelects(frm);
        }).catch(error => console.error("Failed to load edge types", error)).finally(() => {
            frm._dco_edge_types_loading = false;
        });
    }

    function renderFastMeasurements(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        reindexPieces(frm);
        field.$wrapper.html(shellHtml(frm));
        bindFastMeasurements(frm);
        loadEdgeTypes(frm);
    }

    function getOrMaterializeRow(frm, tr) {
        if (!tr) return null;
        return materializeVirtualRow(frm, tr);
    }

    function syncInputToModel(frm, input, trigger = false) {
        const tr = input.closest("tr[data-row-name]");
        const fieldname = input.dataset.field;
        if (!tr || !fieldname) return null;
        const row = getOrMaterializeRow(frm, tr);
        if (!row) return null;
        let value = input.value;
        if (NUMBER_FIELDS.has(fieldname)) value = num(value);
        if (fieldname === "qty") value = Math.max(1, Math.trunc(value || 1));
        row[fieldname] = value;
        frm.dirty();
        updateCalculatedCells(tr, row);
        if (trigger) triggerChildField(frm, row, fieldname, 0);
        return row;
    }

    function focusWidth(tr) {
        if (!tr) return false;
        const input = tr.querySelector("input[data-field='width_cm']");
        if (!input) return false;
        input.focus({ preventScroll:true });
        input.select();
        return document.activeElement === input;
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

    function toggleCheck(frm, button) {
        const tr = button.closest("tr[data-row-name]");
        const fieldname = button.dataset.checkField;
        if (!tr || !CHECK_FIELDS.has(fieldname)) return;
        const row = getOrMaterializeRow(frm, tr);
        if (!row) return;
        const next = row[fieldname] ? 0 : 1;
        row[fieldname] = next;
        frm.dirty();
        button.classList.toggle("is-checked", Boolean(next));
        button.setAttribute("aria-pressed", next ? "true" : "false");
        const mark = button.querySelector(".dco-check-mark");
        if (mark) mark.textContent = next ? "✓" : "";
        updateCalculatedCells(tr, row);
        triggerChildField(frm, row, fieldname, 0);
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

    function bindFastMeasurements(frm) {
        const field = frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        root.addEventListener("input", event => {
            const input = event.target.closest(".dco-fast-input[data-field]");
            if (!input || !root.contains(input)) return;
            syncInputToModel(frm, input, false);
        });

        root.addEventListener("change", event => {
            const control = event.target.closest("[data-field]");
            if (!control || !root.contains(control)) return;
            const row = syncInputToModel(frm, control, false);
            if (row) triggerChildField(frm, row, control.dataset.field, 0);
        });

        root.addEventListener("blur", event => {
            const input = event.target.closest("input[data-field='width_cm'],input[data-field='length_cm']");
            if (!input || !root.contains(input)) return;
            const row = syncInputToModel(frm, input, false);
            if (row) triggerChildField(frm, row, input.dataset.field, 180);
        }, true);

        root.addEventListener("keydown", event => {
            const input = event.target.closest("input[data-field]");
            if (!input || !root.contains(input)) return;
            const fieldname = input.dataset.field;
            const tr = input.closest("tr[data-row-name]");

            // Width -> Tab is intentionally untouched. Because this is a plain HTML
            // editor, the browser moves directly to Length with zero Frappe row activation.
            if (event.key === "Tab" && !event.shiftKey && fieldname === "width_cm") return;

            if (event.key === "Enter" && fieldname === "width_cm") {
                event.preventDefault();
                const length = tr.querySelector("input[data-field='length_cm']");
                if (length) { length.focus({ preventScroll:true }); length.select(); }
                return;
            }

            if (event.key === "Enter" && fieldname === "length_cm") {
                event.preventDefault();
                event.stopPropagation();
                const row = syncInputToModel(frm, input, false);
                if (row) triggerChildField(frm, row, "length_cm", 0);
                moveToNextWidth(frm, tr);
            }
        });

        root.addEventListener("pointerdown", event => {
            const button = event.target.closest(".dco-check-toggle,.dco-delete-row");
            if (!button || !root.contains(button)) return;
            // No parent Frappe grid exists here, but stop pointer bubbling so no
            // surrounding form handler can turn a checkbox click into row activation.
            event.stopPropagation();
        }, true);

        root.addEventListener("click", event => {
            const check = event.target.closest(".dco-check-toggle[data-check-field]");
            if (check && root.contains(check)) {
                event.preventDefault();
                event.stopPropagation();
                toggleCheck(frm, check);
                return;
            }
            const del = event.target.closest(".dco-delete-row");
            if (del && root.contains(del)) {
                event.preventDefault();
                event.stopPropagation();
                deleteRow(frm, del.closest("tr[data-row-name]"));
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

    function refreshOperatorUI(frm) {
        installStyles();
        decorateSections(frm);
        renderStatusStrip(frm);
        renderBoardSummary(frm);
        renderFastMeasurements(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refreshOperatorUI(frm); },
        refresh(frm) { refreshOperatorUI(frm); },
        board_item(frm) { renderBoardSummary(frm); },
        default_edge_type(frm) { refreshEdgeSelects(frm); },
        before_save(frm) { pruneEmptyTrailingRows(frm); },
    });
})();
