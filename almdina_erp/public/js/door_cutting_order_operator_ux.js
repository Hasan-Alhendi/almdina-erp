(() => {
    "use strict";

    const CHECK_FIELDS = new Set([
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ]);
    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const COMPACT_HEADERS = {
        allow_rotation: "تدوير",
        edge_long_right: "طول يمين",
        edge_long_left: "طول يسار",
        edge_width_top: "عرض أعلى",
        edge_width_bottom: "عرض أسفل",
    };

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

    function installStyles() {
        if (document.getElementById("dco-operator-ux-css")) return;
        $("head").append(`
            <style id="dco-operator-ux-css">
                .dco-operator-form .form-page,
                .dco-operator-form .form-layout,
                .dco-operator-form .layout-main-section,
                .dco-operator-form .layout-main-section-wrapper {
                    max-width: none !important;
                    width: 100% !important;
                }

                .dco-operator-form .form-tabs-list { gap: 8px; margin-bottom: 14px; }
                .dco-operator-form .form-tabs-list .nav-link {
                    min-height: 42px;
                    padding: 10px 18px !important;
                    border-radius: 10px !important;
                    font-weight: 700;
                }

                .dco-operator-form .dco-ui-card {
                    border: 1px solid var(--border-color, #dfe3e8);
                    border-radius: 14px;
                    margin: 12px 0;
                    padding: 4px 14px 14px;
                    background: var(--card-bg, var(--fg-color, #fff));
                    box-shadow: 0 1px 2px rgba(0,0,0,.035);
                }
                .dco-operator-form .dco-ui-card > .section-head {
                    font-size: 15px;
                    font-weight: 800;
                    padding-top: 12px;
                    margin-bottom: 10px;
                }
                .dco-operator-form .dco-ui-card .control-label { font-weight: 650; }
                .dco-operator-form .dco-ui-card .form-control,
                .dco-operator-form .dco-ui-card .input-with-feedback {
                    min-height: 38px;
                    border-radius: 8px;
                }

                .dco-status-strip,
                .dco-board-summary {
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 10px;
                    margin: 6px 0 14px;
                }
                .dco-board-summary { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 10px; }
                .dco-summary-tile {
                    border: 1px solid var(--border-color, #dfe3e8);
                    border-radius: 12px;
                    padding: 11px 13px;
                    background: var(--subtle-fg, #f8f9fa);
                    min-height: 68px;
                }
                .dco-summary-tile .dco-label { display:block; font-size:11px; opacity:.7; margin-bottom:5px; }
                .dco-summary-tile .dco-value { display:block; font-size:14px; font-weight:800; line-height:1.45; word-break:break-word; }
                .dco-status-badge {
                    display:inline-flex; align-items:center; gap:6px; border-radius:999px;
                    padding:4px 9px; background:var(--control-bg,#eef2f5);
                }
                .dco-status-dot { width:8px; height:8px; border-radius:50%; background:currentColor; }

                .dco-pieces-wide-control {
                    width:100% !important; max-width:none !important; flex:0 0 100% !important; grid-column:1/-1 !important;
                }
                .dco-pieces-wide-control .form-grid {
                    border-radius:12px;
                    overflow:hidden;
                    border:1px solid var(--border-color,#dfe3e8);
                }
                .dco-pieces-wide-control .grid-heading-row {
                    position:sticky; top:0; z-index:4;
                    background:var(--card-bg,var(--fg-color,#fff));
                }
                .dco-pieces-wide-control .grid-body { overflow-x:auto !important; }
                .dco-pieces-wide-control .grid-row,
                .dco-pieces-wide-control .grid-heading-row { min-width:1080px !important; }
                .dco-pieces-wide-control .grid-row { min-height:46px; transition:background .1s ease; }
                .dco-pieces-wide-control .grid-row:hover { background:var(--subtle-fg,rgba(0,0,0,.025)); }
                .dco-pieces-wide-control .grid-static-col,
                .dco-pieces-wide-control .grid-input { font-size:13px !important; }
                .dco-pieces-wide-control .grid-row [data-fieldname="width_cm"],
                .dco-pieces-wide-control .grid-row [data-fieldname="length_cm"] { min-width:112px !important; }
                .dco-pieces-wide-control .grid-row [data-fieldname="qty"] { min-width:70px !important; }
                .dco-pieces-wide-control .grid-row [data-fieldname="edge_type"] { min-width:155px !important; }
                .dco-pieces-wide-control .grid-row input,
                .dco-pieces-wide-control .grid-row select { min-height:36px; font-size:14px; }

                /* Checkbox columns remain real one-click controls even when the row is not active. */
                .dco-pieces-wide-control .grid-row [data-fieldtype="Check"] {
                    min-width:72px !important;
                    text-align:center !important;
                    cursor:default !important;
                    padding:3px !important;
                }
                .dco-fast-check {
                    width:30px;
                    height:30px;
                    border-radius:8px;
                    border:1.5px solid var(--border-color,#cbd3da);
                    background:var(--card-bg,#fff);
                    display:inline-flex;
                    align-items:center;
                    justify-content:center;
                    padding:0;
                    margin:2px auto;
                    cursor:pointer;
                    transition:transform .06s ease, background .08s ease, border-color .08s ease;
                    color:transparent;
                    font-size:19px;
                    line-height:1;
                    font-weight:900;
                    user-select:none;
                }
                .dco-fast-check:hover { border-color:var(--primary,#2490ef); transform:scale(1.04); }
                .dco-fast-check:active { transform:scale(.95); }
                .dco-fast-check.is-checked {
                    background:var(--primary,#2490ef);
                    border-color:var(--primary,#2490ef);
                    color:#fff;
                }
                .dco-fast-check:disabled { opacity:.55; cursor:not-allowed; transform:none; }
                .dco-fast-check:focus-visible { outline:2px solid var(--primary,#2490ef); outline-offset:2px; }

                .dco-grid-shortcuts {
                    display:flex; align-items:center; flex-wrap:wrap; gap:8px 14px;
                    padding:10px 12px; margin-bottom:8px; border-radius:10px;
                    background:var(--subtle-fg,#f8f9fa); border:1px solid var(--border-color,#dfe3e8); font-size:12px;
                }
                .dco-grid-shortcuts kbd {
                    border:1px solid var(--border-color,#ccd3da); border-bottom-width:2px; border-radius:5px;
                    padding:2px 6px; background:var(--card-bg,#fff); font-family:inherit; font-size:11px;
                }

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
            field.$wrapper.html(`<div class="dco-grid-shortcuts" style="margin-top:10px">${isArabic() ? "اختر صنف اللوح أولًا، وستظهر هنا المادة واللون والسماكة والمقاس تلقائيًا." : "Select a board item to load its material, color, thickness and size."}</div>`);
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
        const pieces = frm.fields_dict.pieces;
        if (pieces && pieces.grid) $(pieces.grid.wrapper).closest(".frappe-control").addClass("dco-pieces-wide-control");
    }

    function gridRowFor(grid, docname) {
        return grid && grid.grid_rows_by_docname ? grid.grid_rows_by_docname[docname] : null;
    }

    function rememberFocus(frm, docname, fieldname, ms = 5000) {
        frm._dco_operator_focus = { docname, fieldname, expires: Date.now() + ms };
    }

    function inputForGridField(gridRow, fieldname) {
        if (!gridRow) return null;
        const column = gridRow.columns && gridRow.columns[fieldname];
        if (!column) return null;
        if (!column.field) gridRow.make_control(column);
        const field = (gridRow.on_grid_fields_dict && gridRow.on_grid_fields_dict[fieldname]) || column.field;
        return field && field.$input && field.$input.length ? field.$input : null;
    }

    function focusGridFieldNow(frm, docname, fieldname, selectText = true) {
        const grid = frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        const gridRow = gridRowFor(grid, docname);
        if (!gridRow) return false;

        rememberFocus(frm, docname, fieldname);
        gridRow.toggle_editable_row(true);
        const $input = inputForGridField(gridRow, fieldname);
        if (!$input || !$input.length) return false;

        const element = $input.get(0);
        try { element.focus({ preventScroll: true }); } catch (error) { element.focus(); }
        if (selectText && $input.is("input[type='text'],input[type='number'],input:not([type])")) {
            try { element.select(); } catch (error) { /* no-op */ }
        }
        return document.activeElement === element;
    }

    function focusGridFieldFast(frm, docname, fieldname, selectText = true) {
        if (focusGridFieldNow(frm, docname, fieldname, selectText)) return;
        requestAnimationFrame(() => {
            if (focusGridFieldNow(frm, docname, fieldname, selectText)) return;
            requestAnimationFrame(() => focusGridFieldNow(frm, docname, fieldname, selectText));
        });
    }

    function restoreRememberedFocus(frm) {
        const state = frm._dco_operator_focus;
        if (!state || Date.now() > state.expires) return;
        const grid = frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        if (!grid || !grid.wrapper) return;
        const active = document.activeElement;
        const gridNode = $(grid.wrapper).get(0);
        if (active && active !== document.body && !gridNode.contains(active)) return;
        focusGridFieldFast(frm, state.docname, state.fieldname, true);
    }

    function addShortcutHint($gridWrapper) {
        if ($gridWrapper.find(".dco-grid-shortcuts").length) return;
        const html = isArabic()
            ? `<div class="dco-grid-shortcuts"><b>إدخال سريع جدًا:</b><span>العرض ثم <kbd>Tab</kbd> للطول فورًا، وبعد الطول <kbd>Enter</kbd> لإنشاء السطر التالي والبدء مباشرة من العرض.</span><span>القشاط والتدوير: نقرة واحدة فقط.</span></div>`
            : `<div class="dco-grid-shortcuts"><b>Fast entry:</b><span>Width, native <kbd>Tab</kbd> instantly to length, then <kbd>Enter</kbd> creates the next row and focuses width.</span><span>Edge/rotation toggles take one click.</span></div>`;
        $gridWrapper.prepend(html);
    }

    function setFastCheckVisual($button, checked) {
        $button.toggleClass("is-checked", Boolean(checked));
        $button.attr("aria-pressed", checked ? "true" : "false");
        $button.text(checked ? "✓" : "");
    }

    function renderFastCheckRow(frm, gridRow) {
        if (!gridRow || !gridRow.doc || !gridRow.columns) return;
        const editable = Boolean(gridRow.grid && gridRow.grid.is_editable()) && EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft");

        CHECK_FIELDS.forEach(fieldname => {
            const column = gridRow.columns[fieldname];
            if (!column || !column.static_area) return;

            // Keep checkbox cells independent from Frappe's active-row editor.
            // A direct button click must never first activate/select the row.
            column.field_area && column.field_area.hide();
            column.static_area.show();
            column.static_area.empty();

            const checked = Boolean(gridRow.doc[fieldname]);
            const $button = $("<button>", {
                type: "button",
                class: "dco-fast-check",
                "aria-label": COMPACT_HEADERS[fieldname] || fieldname,
                tabindex: -1,
                disabled: !editable,
            });
            setFastCheckVisual($button, checked);

            $button.on("mousedown.dco_fast_check pointerdown.dco_fast_check", event => {
                // Prevent drag/row-selection gestures; the click itself remains available.
                event.stopPropagation();
            });
            $button.on("click.dco_fast_check", event => {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                if (!editable) return false;

                const nextValue = gridRow.doc[fieldname] ? 0 : 1;
                setFastCheckVisual($button, nextValue);
                frm.dirty();

                // Model update happens after the visual toggle, so the operator sees
                // the check immediately even if validation/recalculation continues.
                Promise.resolve(frappe.model.set_value(gridRow.doc.doctype, gridRow.doc.name, fieldname, nextValue))
                    .catch(error => {
                        console.error("Failed to toggle grid checkbox", error);
                        setFastCheckVisual($button, Boolean(gridRow.doc[fieldname]));
                    })
                    .finally(() => requestAnimationFrame(() => renderFastCheckRow(frm, gridRow)));
                return false;
            });

            column.static_area.append($button);
        });
    }

    function patchGridRow(frm, gridRow) {
        if (!gridRow || gridRow._dcoOperatorPatched) {
            renderFastCheckRow(frm, gridRow);
            return;
        }
        gridRow._dcoOperatorPatched = true;
        const originalToggle = gridRow.toggle_editable_row;
        gridRow.toggle_editable_row = function (...args) {
            const result = originalToggle.apply(this, args);
            renderFastCheckRow(frm, this);
            return result;
        };
        renderFastCheckRow(frm, gridRow);
    }

    function compactGridHeaders(grid) {
        if (!isArabic() || !grid || !grid.wrapper) return;
        Object.entries(COMPACT_HEADERS).forEach(([fieldname, label]) => {
            const $cell = $(grid.wrapper).find(`.grid-heading-row .grid-row [data-fieldname="${fieldname}"]`).first();
            if (!$cell.length) return;
            $cell.find(".static-area").first().text(label);
            $cell.attr("title", label);
        });
    }

    function commitLengthWithoutWaiting(frm, docname, rawValue) {
        const row = (frm.doc.pieces || []).find(item => item.name === docname);
        if (!row) return;
        const parsed = frappe.utils.flt ? frappe.utils.flt(rawValue) : (parseFloat(rawValue) || 0);
        if (Number(row.length_cm || 0) === Number(parsed)) return;
        // Do not await scripts/server work. Local model mutation occurs immediately;
        // any calculations continue in the background while focus moves on.
        frappe.model.set_value(row.doctype, row.name, "length_cm", parsed).catch(error => console.error(error));
    }

    function moveToNextWidthImmediately(frm, currentDocname) {
        const grid = frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        if (!grid) return;
        const rows = frm.doc.pieces || [];
        const index = rows.findIndex(row => row.name === currentDocname);
        let target = index >= 0 && index < rows.length - 1 ? rows[index + 1] : null;

        if (!target) {
            // Native Grid.add_new_row refreshes synchronously. Use its returned child
            // document and activate the row directly instead of clicking a cell.
            target = grid.add_new_row(null, null, false, null, true);
        }
        if (!target) return;

        rememberFocus(frm, target.name, "width_cm", 5000);
        focusGridFieldFast(frm, target.name, "width_cm", true);
    }

    function setupGridKeyboard(frm, grid, $gridWrapper) {
        // Remove the old handler that intercepted Tab and introduced a visible delay.
        // Width -> Tab now uses the browser/Frappe native focus path with zero timeout.
        $gridWrapper.off("keydown.dco_enter_add_row");
        $gridWrapper.off("keydown.dco_operator_keyboard");
        $gridWrapper.on("keydown.dco_operator_keyboard", "input, textarea, select", function (event) {
            const $target = $(event.target);
            const fieldname = $target.closest("[data-fieldname]").attr("data-fieldname");
            const docname = $target.closest(".grid-row[data-name]").attr("data-name");
            if (!docname || !fieldname) return;

            if (event.key === "Tab" && !event.shiftKey && fieldname === "width_cm") {
                // Do not preventDefault and do not trigger a click. Native Tab is instant.
                rememberFocus(frm, docname, "length_cm", 5000);
                return;
            }

            if (event.key === "Enter" && fieldname === "length_cm") {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                commitLengthWithoutWaiting(frm, docname, $target.val());
                moveToNextWidthImmediately(frm, docname);
            }
        });

        $gridWrapper.off("focusin.dco_operator_focus");
        $gridWrapper.on("focusin.dco_operator_focus", ".grid-row[data-name] [data-fieldname] input, .grid-row[data-name] [data-fieldname] textarea, .grid-row[data-name] [data-fieldname] select", function () {
            const $input = $(this);
            const docname = $input.closest(".grid-row[data-name]").attr("data-name");
            const fieldname = $input.closest("[data-fieldname]").attr("data-fieldname");
            if (docname && fieldname) rememberFocus(frm, docname, fieldname, 5000);
        });

        $gridWrapper.off("change.dco_operator_restore");
        $gridWrapper.on("change.dco_operator_restore", () => requestAnimationFrame(() => restoreRememberedFocus(frm)));
    }

    function setupMeasurementsGrid(frm) {
        const field = frm.fields_dict.pieces;
        if (!field || !field.grid) return;
        const grid = field.grid;
        const $gridWrapper = $(grid.wrapper);

        $gridWrapper.closest(".frappe-control").addClass("dco-pieces-wide-control");
        addShortcutHint($gridWrapper);
        setupGridKeyboard(frm, grid, $gridWrapper);
        compactGridHeaders(grid);

        (grid.grid_rows || []).forEach(gridRow => patchGridRow(frm, gridRow));

        $(frm.wrapper)
            .off("grid-row-render.dco_operator_ux")
            .on("grid-row-render.dco_operator_ux", (event, gridRow) => {
                if (!gridRow || gridRow.grid !== grid) return;
                patchGridRow(frm, gridRow);
                compactGridHeaders(grid);
                requestAnimationFrame(() => restoreRememberedFocus(frm));
            });
    }

    function refreshOperatorUI(frm) {
        installStyles();
        decorateSections(frm);
        renderStatusStrip(frm);
        renderBoardSummary(frm);
        setupMeasurementsGrid(frm);
        requestAnimationFrame(() => restoreRememberedFocus(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refreshOperatorUI(frm); },
        refresh(frm) {
            refreshOperatorUI(frm);
            requestAnimationFrame(() => refreshOperatorUI(frm));
        },
        board_item(frm) { requestAnimationFrame(() => renderBoardSummary(frm)); },
        pieces_add(frm) { requestAnimationFrame(() => setupMeasurementsGrid(frm)); },
        pieces_remove(frm) { requestAnimationFrame(() => setupMeasurementsGrid(frm)); },
    });
})();
