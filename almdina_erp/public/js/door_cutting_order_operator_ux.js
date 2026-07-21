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

                .dco-operator-form .form-tabs-list {
                    gap: 8px;
                    margin-bottom: 14px;
                }
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
                .dco-operator-form .dco-ui-card .control-label {
                    font-weight: 650;
                }
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
                .dco-board-summary {
                    grid-template-columns: repeat(4, minmax(0, 1fr));
                    margin-top: 10px;
                }
                .dco-summary-tile {
                    border: 1px solid var(--border-color, #dfe3e8);
                    border-radius: 12px;
                    padding: 11px 13px;
                    background: var(--subtle-fg, #f8f9fa);
                    min-height: 68px;
                }
                .dco-summary-tile .dco-label {
                    display: block;
                    font-size: 11px;
                    opacity: .7;
                    margin-bottom: 5px;
                }
                .dco-summary-tile .dco-value {
                    display: block;
                    font-size: 14px;
                    font-weight: 800;
                    line-height: 1.45;
                    word-break: break-word;
                }
                .dco-status-badge {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    border-radius: 999px;
                    padding: 4px 9px;
                    background: var(--control-bg, #eef2f5);
                }
                .dco-status-dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    background: currentColor;
                }

                .dco-pieces-wide-control {
                    width: 100% !important;
                    max-width: none !important;
                    flex: 0 0 100% !important;
                    grid-column: 1/-1 !important;
                }
                .dco-pieces-wide-control .form-grid {
                    border-radius: 12px;
                    overflow: hidden;
                    border: 1px solid var(--border-color, #dfe3e8);
                }
                .dco-pieces-wide-control .grid-heading-row {
                    position: sticky;
                    top: 0;
                    z-index: 4;
                    background: var(--card-bg, var(--fg-color, #fff));
                }
                .dco-pieces-wide-control .grid-body {
                    overflow-x: auto !important;
                }
                .dco-pieces-wide-control .grid-row,
                .dco-pieces-wide-control .grid-heading-row {
                    min-width: 1080px !important;
                }
                .dco-pieces-wide-control .grid-row {
                    min-height: 44px;
                    transition: background .12s ease;
                }
                .dco-pieces-wide-control .grid-row:hover {
                    background: var(--subtle-fg, rgba(0,0,0,.025));
                }
                .dco-pieces-wide-control .grid-static-col,
                .dco-pieces-wide-control .grid-input {
                    font-size: 13px !important;
                }
                .dco-pieces-wide-control .grid-row [data-fieldname="width_cm"],
                .dco-pieces-wide-control .grid-row [data-fieldname="length_cm"] {
                    min-width: 110px !important;
                }
                .dco-pieces-wide-control .grid-row [data-fieldname="qty"] {
                    min-width: 72px !important;
                }
                .dco-pieces-wide-control .grid-row [data-fieldtype="Check"] {
                    cursor: pointer !important;
                    min-width: 78px !important;
                    user-select: none;
                }
                .dco-pieces-wide-control .grid-row [data-fieldtype="Check"]:hover {
                    background: rgba(0, 120, 212, .08);
                }
                .dco-pieces-wide-control .grid-row [data-fieldtype="Check"] .static-area,
                .dco-pieces-wide-control .grid-row [data-fieldtype="Check"] .field-area {
                    min-height: 38px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .dco-pieces-wide-control input[type="checkbox"] {
                    width: 19px;
                    height: 19px;
                    cursor: pointer;
                }
                .dco-pieces-wide-control .grid-row [data-fieldname="edge_type"] {
                    min-width: 160px !important;
                }
                .dco-pieces-wide-control .grid-row input,
                .dco-pieces-wide-control .grid-row select {
                    min-height: 36px;
                    font-size: 14px;
                }
                .dco-grid-shortcuts {
                    display: flex;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 8px 14px;
                    padding: 10px 12px;
                    margin-bottom: 8px;
                    border-radius: 10px;
                    background: var(--subtle-fg, #f8f9fa);
                    border: 1px solid var(--border-color, #dfe3e8);
                    font-size: 12px;
                }
                .dco-grid-shortcuts kbd {
                    border: 1px solid var(--border-color, #ccd3da);
                    border-bottom-width: 2px;
                    border-radius: 5px;
                    padding: 2px 6px;
                    background: var(--card-bg, #fff);
                    font-family: inherit;
                    font-size: 11px;
                }

                @media (max-width: 900px) {
                    .dco-status-strip,
                    .dco-board-summary {
                        grid-template-columns: 1fr 1fr;
                    }
                }
                @media (max-width: 600px) {
                    .dco-status-strip,
                    .dco-board-summary {
                        grid-template-columns: 1fr;
                    }
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
            ? `<a href="/app/cutting-plan/${encodeURIComponent(plan)}"><b>${escapeHtml(plan)}</b></a>`
            : escapeHtml(noPlan);

        field.$wrapper.html(`
            <div class="dco-status-strip">
                <div class="dco-summary-tile">
                    <span class="dco-label">${__("Status")}</span>
                    <span class="dco-value"><span class="dco-status-badge"><span class="dco-status-dot"></span>${escapeHtml(status)}</span></span>
                </div>
                <div class="dco-summary-tile">
                    <span class="dco-label">${__("Revision")}</span>
                    <span class="dco-value">${escapeHtml(revision)}</span>
                </div>
                <div class="dco-summary-tile">
                    <span class="dco-label">${__("Approved Cutting Plan")}</span>
                    <span class="dco-value">${planValue}</span>
                </div>
            </div>
        `);
    }

    function renderBoardSummary(frm) {
        const field = frm.fields_dict.board_summary_html;
        if (!field || !field.$wrapper) return;

        if (!frm.doc.board_item) {
            field.$wrapper.html(`
                <div class="dco-grid-shortcuts" style="margin-top:10px">
                    ${isArabic() ? "اختر صنف اللوح أولًا، وستظهر هنا المادة واللون والسماكة والمقاس تلقائيًا." : "Select a board item to load its material, color, thickness and size."}
                </div>
            `);
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

        field.$wrapper.html(`
            <div class="dco-board-summary">
                ${tiles.map(([label, value]) => `
                    <div class="dco-summary-tile">
                        <span class="dco-label">${escapeHtml(label)}</span>
                        <span class="dco-value">${escapeHtml(value)}</span>
                    </div>
                `).join("")}
            </div>
        `);
    }

    function decorateSections(frm) {
        $(frm.wrapper).addClass("dco-operator-form");
        ["order_details_section", "board_section", "cutting_settings_section", "pieces_section", "totals_section", "plan_section", "technical_section"].forEach(fieldname => {
            const field = frm.fields_dict[fieldname];
            if (!field || !field.wrapper) return;
            $(field.wrapper).closest(".form-section").addClass("dco-ui-card");
        });

        const pieces = frm.fields_dict.pieces;
        if (pieces && pieces.grid) {
            $(pieces.grid.wrapper).closest(".frappe-control").addClass("dco-pieces-wide-control");
        }
    }

    function gridRowFor(grid, docname) {
        return grid && grid.grid_rows_by_docname ? grid.grid_rows_by_docname[docname] : null;
    }

    function rememberFocus(frm, docname, fieldname, ms = 1100) {
        frm._dco_operator_focus = {
            docname,
            fieldname,
            expires: Date.now() + ms,
        };
    }

    function focusGridField(frm, docname, fieldname, selectText = true) {
        const grid = frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        if (!grid || !docname) return;
        const gridRow = gridRowFor(grid, docname);
        if (!gridRow || !gridRow.wrapper) return;
        const $cell = gridRow.wrapper.find(`[data-fieldname="${fieldname}"]`).first();
        if (!$cell.length) return;

        rememberFocus(frm, docname, fieldname);
        $cell.trigger("click");

        const focusInput = () => {
            const $input = $cell.find("input:visible, textarea:visible, select:visible").first();
            if (!$input.length) return false;
            $input.trigger("focus");
            if (selectText && $input.is("input[type='text'], input:not([type])")) {
                try { $input[0].select(); } catch (error) { /* no-op */ }
            }
            return true;
        };

        if (!focusInput()) {
            setTimeout(() => {
                if (!focusInput()) setTimeout(focusInput, 80);
            }, 25);
        }
    }

    function restoreRememberedFocus(frm) {
        const state = frm._dco_operator_focus;
        if (!state || Date.now() > state.expires) return;
        const active = document.activeElement;
        const grid = frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        if (!grid || !grid.wrapper) return;
        const gridNode = $(grid.wrapper).get(0);

        // Only restore when a grid refresh temporarily dropped focus, or while the
        // user is still working inside the measurements grid. Never steal focus
        // from another form field the operator intentionally moved to.
        if (active && active !== document.body && !gridNode.contains(active)) return;
        focusGridField(frm, state.docname, state.fieldname, true);
    }

    function addShortcutHint($gridWrapper) {
        if ($gridWrapper.find(".dco-grid-shortcuts").length) return;
        const html = isArabic()
            ? `<div class="dco-grid-shortcuts"><b>إدخال سريع:</b><span>اكتب العرض ثم <kbd>Tab</kbd> للطول، وبعد الطول اضغط <kbd>Enter</kbd> لإنشاء سطر جديد والعودة مباشرة إلى خانة العرض.</span><span>القشاط والتدوير: نقرة واحدة على المربع.</span></div>`
            : `<div class="dco-grid-shortcuts"><b>Fast entry:</b><span>Enter width, press <kbd>Tab</kbd> for length, then <kbd>Enter</kbd> to create the next row and focus width.</span><span>Edge/rotation checks toggle with one click.</span></div>`;
        $gridWrapper.prepend(html);
    }

    function moveToNextWidth(frm, currentDocname) {
        const grid = frm.fields_dict.pieces && frm.fields_dict.pieces.grid;
        if (!grid) return;
        const rows = frm.doc.pieces || [];
        const index = rows.findIndex(row => row.name === currentDocname);
        let target = index >= 0 && index < rows.length - 1 ? rows[index + 1] : null;

        if (!target) {
            target = grid.add_new_row();
        }
        if (!target) return;

        rememberFocus(frm, target.name, "width_cm", 1400);
        setTimeout(() => focusGridField(frm, target.name, "width_cm", true), 30);
    }

    function setupGridKeyboard(frm, grid, $gridWrapper) {
        // Remove the legacy broad Enter handler. The high-speed operator workflow
        // is intentionally precise: Width -> Tab -> Length -> Enter -> next Width.
        $gridWrapper.off("keydown.dco_enter_add_row");
        $gridWrapper.off("keydown.dco_operator_keyboard");
        $gridWrapper.on("keydown.dco_operator_keyboard", "input, textarea, select", function (event) {
            const $target = $(event.target);
            const $cell = $target.closest("[data-fieldname]");
            const fieldname = $cell.attr("data-fieldname");
            const $row = $target.closest(".grid-row[data-name]");
            const docname = $row.attr("data-name");
            if (!docname || !fieldname) return;

            if (event.key === "Tab" && !event.shiftKey && fieldname === "width_cm") {
                event.preventDefault();
                event.stopPropagation();
                $target.trigger("change");
                rememberFocus(frm, docname, "length_cm", 1200);
                setTimeout(() => focusGridField(frm, docname, "length_cm", true), 20);
                return;
            }

            if (event.key === "Enter" && fieldname === "length_cm") {
                event.preventDefault();
                event.stopPropagation();
                $target.trigger("change");
                setTimeout(() => moveToNextWidth(frm, docname), 25);
            }
        });

        $gridWrapper.off("focusin.dco_operator_focus");
        $gridWrapper.on("focusin.dco_operator_focus", ".grid-row[data-name] [data-fieldname] input, .grid-row[data-name] [data-fieldname] textarea, .grid-row[data-name] [data-fieldname] select", function () {
            const $input = $(this);
            const docname = $input.closest(".grid-row[data-name]").attr("data-name");
            const fieldname = $input.closest("[data-fieldname]").attr("data-fieldname");
            if (docname && fieldname) rememberFocus(frm, docname, fieldname, 850);
        });

        $gridWrapper.off("change.dco_operator_restore");
        $gridWrapper.on("change.dco_operator_restore", () => {
            setTimeout(() => restoreRememberedFocus(frm), 35);
        });
    }

    function setupOneClickChecks(frm, grid, $gridWrapper) {
        const node = $gridWrapper.get(0);
        if (!node) return;

        if (node._dcoOneClickCheckHandler) {
            node.removeEventListener("click", node._dcoOneClickCheckHandler, true);
        }

        const handler = event => {
            const cell = event.target.closest(".grid-row[data-name] [data-fieldtype='Check'][data-fieldname]");
            if (!cell || !node.contains(cell)) return;
            const fieldname = cell.getAttribute("data-fieldname");
            if (!CHECK_FIELDS.has(fieldname)) return;
            if (!grid.is_editable() || !EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft")) return;

            const rowElement = cell.closest(".grid-row[data-name]");
            const docname = rowElement && rowElement.getAttribute("data-name");
            const row = (frm.doc.pieces || []).find(item => item.name === docname);
            if (!row) return;

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();

            const nextValue = row[fieldname] ? 0 : 1;
            const gridRow = gridRowFor(grid, row.name);
            if (gridRow && typeof gridRow.refresh_field === "function") {
                gridRow.refresh_field(fieldname, nextValue);
            }

            frappe.model.set_value(row.doctype, row.name, fieldname, nextValue).catch(error => {
                console.error("Failed to toggle grid checkbox", error);
                if (gridRow && typeof gridRow.refresh_field === "function") {
                    gridRow.refresh_field(fieldname, row[fieldname] ? 1 : 0);
                }
            });
        };

        node._dcoOneClickCheckHandler = handler;
        node.addEventListener("click", handler, true);
    }

    function setupMeasurementsGrid(frm) {
        const field = frm.fields_dict.pieces;
        if (!field || !field.grid) return;
        const grid = field.grid;
        const $gridWrapper = $(grid.wrapper);

        $gridWrapper.closest(".frappe-control").addClass("dco-pieces-wide-control");
        addShortcutHint($gridWrapper);
        setupGridKeyboard(frm, grid, $gridWrapper);
        setupOneClickChecks(frm, grid, $gridWrapper);
    }

    function refreshOperatorUI(frm) {
        installStyles();
        decorateSections(frm);
        renderStatusStrip(frm);
        renderBoardSummary(frm);
        setupMeasurementsGrid(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            refreshOperatorUI(frm);
        },
        refresh(frm) {
            refreshOperatorUI(frm);
            setTimeout(() => refreshOperatorUI(frm), 250);
        },
        board_item(frm) {
            setTimeout(() => renderBoardSummary(frm), 350);
        },
        pieces_add(frm) {
            setTimeout(() => setupMeasurementsGrid(frm), 30);
        },
        pieces_remove(frm) {
            setTimeout(() => setupMeasurementsGrid(frm), 30);
        },
    });
})();
