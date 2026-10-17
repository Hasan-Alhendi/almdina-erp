(() => {
    "use strict";

    const STYLE_ID = "dco-compact-edge-profile-controls-css";
    const POPOVER_ID = "dco-edge-profile-popover";
    const BULK_DEFAULT_VALUE = "__almdina_default__";
    const SIDE_CONFIG = [
        {
            side: "width_top",
            selectedField: "edge_width_top",
            overrideField: "edge_width_top_type_override",
            label: "Top width side",
        },
        {
            side: "width_bottom",
            selectedField: "edge_width_bottom",
            overrideField: "edge_width_bottom_type_override",
            label: "Bottom width side",
        },
        {
            side: "long_right",
            selectedField: "edge_long_right",
            overrideField: "edge_long_right_type_override",
            label: "Right length side",
        },
        {
            side: "long_left",
            selectedField: "edge_long_left",
            overrideField: "edge_long_left_type_override",
            label: "Left length side",
        },
    ];
    let activePopover = null;
    let dismissBound = false;


    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function materialize(frm, tr) {
        let row = rowByName(frm, tr && tr.dataset.rowName);
        if (row || !tr || !String(tr.dataset.rowName || "").startsWith("__virtual__")) {
            return row;
        }
        const qtyInput = tr.querySelector("input[data-field='qty']");
        if (qtyInput) qtyInput.dispatchEvent(new Event("input", { bubbles: true }));
        return rowByName(frm, tr.dataset.rowName);
    }

    function isEditable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0;
    }

    function moduleApi() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function profileMap(frm) {
        const api = moduleApi();
        if (!api || !api.profiles) return new Map();
        return api.profiles(frm);
    }

    function profileEntries(frm, current = "") {
        const values = new Map();
        profileMap(frm).forEach(profile => {
            const name = String((profile && profile.name) || "").trim();
            if (!name) return;
            values.set(name, String(profile.label || name));
        });
        if (current && !values.has(current)) values.set(current, current);
        return [...values.entries()];
    }

    function profileDetails(frm, value) {
        const profile = profileMap(frm).get(value);
        if (!profile) {
            return __("Previously saved profile");
        }
        const thickness = Number(profile.thickness_mm || 0).toLocaleString("en-US", {
            maximumFractionDigits: 3,
        });
        const rate = Number(profile.rate_usd_per_meter || 0).toLocaleString("en-US", {
            maximumFractionDigits: 2,
        });
        return __("{0} mm · $ {1}/m", [thickness, rate]);
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table tbody td{vertical-align:middle!important;padding-top:5px!important;padding-bottom:5px!important}
            .dco-fast-table .dco-col-edges{vertical-align:middle!important;overflow:visible!important}
            .dco-fast-table .dco-col-edge-bulk{
                width:122px!important;min-width:122px!important;max-width:122px!important;
                text-align:center;padding-inline:4px!important;vertical-align:middle!important
            }
            .dco-edge-bulk-toolbar,.dco-edge-direct-actions,.dco-edge-profile-grid{display:none!important}
            .dco-side-profile-trigger,.dco-all-sides-profile-select{display:none!important}
            .dco-edge-bulk-cell-content{display:flex;align-items:center;justify-content:center;min-height:38px;width:100%}
            .dco-all-sides-profile-button{
                width:100%;max-width:100%;height:38px;min-height:38px;display:flex;align-items:center;
                justify-content:center;gap:5px;border:1px solid color-mix(in srgb, var(--alm-primary, #172033) 38%, transparent);border-radius:7px;
                background:color-mix(in srgb, var(--alm-primary, #172033) 7%, transparent);color:var(--alm-text-strong,#101828);padding:2px 6px;
                font-size:9.5px;font-weight:850;line-height:1.1;cursor:pointer;outline:none
            }
            .dco-all-sides-profile-button:hover,.dco-all-sides-profile-button:focus{
                border-color:var(--alm-primary,#172033);background:color-mix(in srgb, var(--alm-primary, #172033) 6%, var(--alm-card,#ffffff));box-shadow:0 0 0 2px color-mix(in srgb, var(--alm-primary, #172033) 10%, transparent)
            }
            .dco-all-sides-profile-button:disabled{opacity:.48;cursor:not-allowed;box-shadow:none}
            .dco-all-sides-profile-button .dco-bulk-chevron{font-size:11px;line-height:1;opacity:.72}
            .dco-edge-buttons{padding-top:0!important;overflow:visible!important;align-items:stretch!important;margin:0!important}
            .dco-col-edges .dco-check-toggle{
                min-height:38px!important;height:38px!important;padding:4px!important;align-items:center!important;
                overflow:hidden!important;cursor:pointer;transition:background .14s ease,border-color .14s ease,box-shadow .14s ease,color .14s ease
            }
            .dco-col-edges .dco-check-toggle.dco-edge-profile-target.is-edge-custom{
                background:color-mix(in srgb, #c88a00 16%, var(--alm-card,#ffffff))!important;border-color:#c88a00!important;color:#c88a00!important;
                box-shadow:inset 0 0 0 1px rgba(200,138,0,.24),0 0 0 1px rgba(200,138,0,.08)!important
            }
            .dco-col-edges .dco-check-toggle.dco-edge-profile-target.is-edge-custom:hover{
                background:color-mix(in srgb, #aa7400 18%, var(--alm-card,#ffffff))!important;border-color:#aa7400!important
            }
            .dco-col-edges .dco-check-toggle.dco-edge-profile-target.is-edge-custom .dco-check-mark{color:#674900!important}
            .dco-col-edges .dco-check-toggle.dco-edge-profile-target.is-edge-missing{
                background:color-mix(in srgb, #d94a4a 12%, var(--alm-card,#ffffff))!important;border-color:#d94a4a!important;color:#d94a4a!important
            }
            #${POPOVER_ID}{
                position:fixed;z-index:1065;width:min(292px,calc(100vw - 20px));max-height:min(390px,calc(100vh - 20px));
                display:flex;flex-direction:column;border:1px solid var(--border-color,#cbd2d9);border-radius:12px;
                background:var(--alm-card,#ffffff);box-shadow:0 14px 38px rgba(15,23,42,.22);overflow:hidden;
                color:var(--text-color,#172033)
            }
            #${POPOVER_ID} .dco-edge-popover-head{
                flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 10px 7px;
                border-bottom:1px solid var(--alm-card-border,#e4e8ee);background:var(--alm-surface-muted,#f4f6f8)
            }
            #${POPOVER_ID} .dco-edge-popover-head strong{font-size:12px;line-height:1.25}
            #${POPOVER_ID} .dco-edge-popover-head small{display:block;margin-top:2px;color:var(--text-muted,#65717d);font-size:9px;font-weight:600}
            #${POPOVER_ID} .dco-edge-popover-close{
                flex:0 0 auto;width:26px;height:26px;border:0;border-radius:7px;background:transparent;color:inherit;
                font-size:18px;line-height:1;cursor:pointer
            }
            #${POPOVER_ID} .dco-edge-popover-close:hover{background:rgba(0,0,0,.07)}
            #${POPOVER_ID} .dco-edge-popover-options{
                flex:1 1 auto;min-height:0;max-height:min(304px,calc(100vh - 92px));display:grid;gap:3px;
                padding:7px;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;touch-action:pan-y;
                scrollbar-gutter:stable;scrollbar-width:thin
            }
            #${POPOVER_ID} .dco-edge-popover-options::-webkit-scrollbar{width:8px}
            #${POPOVER_ID} .dco-edge-popover-options::-webkit-scrollbar-thumb{
                background:rgba(100,116,139,.45);border-radius:999px;border:2px solid transparent;background-clip:padding-box
            }
            #${POPOVER_ID} .dco-edge-profile-option{
                width:100%;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:4px 8px;
                min-height:38px;padding:6px 8px;border:1px solid transparent;border-radius:8px;background:transparent;
                color:inherit;text-align:right;cursor:pointer
            }
            #${POPOVER_ID} .dco-edge-profile-option:hover,#${POPOVER_ID} .dco-edge-profile-option:focus{
                border-color:color-mix(in srgb, var(--alm-primary, #172033) 42%, transparent);background:color-mix(in srgb, var(--alm-primary, #172033) 6%, var(--alm-card,#ffffff));outline:0
            }
            #${POPOVER_ID} .dco-edge-profile-option.is-current{border-color:var(--alm-primary,#172033);background:color-mix(in srgb, var(--alm-primary, #172033) 8%, var(--alm-card,#ffffff))}
            #${POPOVER_ID} .dco-edge-profile-option.is-custom-current{border-color:#c88a00;background:color-mix(in srgb, #c88a00 14%, var(--alm-card,#ffffff))}
            #${POPOVER_ID} .dco-edge-profile-option b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}
            #${POPOVER_ID} .dco-edge-profile-option small{grid-column:1;color:var(--text-muted,#65717d);font-size:8.5px;line-height:1.2}
            #${POPOVER_ID} .dco-edge-profile-option span{grid-column:2;grid-row:1/3;font-size:13px;font-weight:900;color:var(--alm-primary,#172033)}
            #${POPOVER_ID} .dco-edge-profile-option.is-custom-current span{color:#8a6100}
            @media(max-width:900px){
                .dco-fast-table .dco-col-edge-bulk{width:112px!important;min-width:112px!important;max-width:112px!important}
                .dco-all-sides-profile-button{font-size:9px;padding-inline:4px}
            }
        `;
        document.head.appendChild(style);
    }

    function configForToggle(toggle) {
        const selectedField = toggle && toggle.dataset.checkField;
        return SIDE_CONFIG.find(config => config.selectedField === selectedField) || null;
    }

    function syncToggleVisuals(tr, row) {
        SIDE_CONFIG.forEach(config => {
            const toggle = tr.querySelector(`.dco-check-toggle[data-check-field='${config.selectedField}']`);
            if (!toggle) return;
            const checked = Boolean(row[config.selectedField]);
            toggle.classList.toggle("is-checked", checked);
            toggle.setAttribute("aria-pressed", checked ? "true" : "false");
            const mark = toggle.querySelector(".dco-check-mark");
            if (mark) mark.textContent = checked ? "✓" : "";
        });
    }

    function notifyChanged(frm, tr, row, fieldname, changedFields = []) {
        frm.dirty();
        syncToggleVisuals(tr, row);

        if (frm.script_manager && typeof frm.script_manager.trigger === "function") {
            changedFields.forEach(name => {
                Promise.resolve(frm.script_manager.trigger(name, row.doctype, row.name))
                    .catch(error => console.error(error));
            });
        }

        const root = rootFor(frm);
        if (root) {
            root.dispatchEvent(new CustomEvent("dco:side-edge-change", {
                bubbles: true,
                detail: { row: row.name, fieldname },
            }));
        }

        const api = moduleApi();
        if (api && api.schedule) api.schedule(frm);
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        if (window.AlmdinaMultiEdgeDocuments && window.AlmdinaMultiEdgeDocuments.patch) {
            window.AlmdinaMultiEdgeDocuments.patch(frm);
        }
        schedule(frm);
    }

    function lockedBreakSides(row) {
        const geometry = window.AlmdinaClippedCornerGeometry;
        if (
            !row
            || !geometry
            || typeof geometry.locksAdjacentSidesForBreak !== "function"
            || !geometry.locksAdjacentSidesForBreak(row)
            || typeof geometry.breakAdjacentSides !== "function"
        ) {
            return new Set();
        }
        return new Set(geometry.breakAdjacentSides(row.clipped_corner_position));
    }

    function applySideSelection(frm, tr, config, overrideType) {
        const row = materialize(frm, tr);
        if (!row) return;
        if (lockedBreakSides(row).has(config.selectedField)) return;
        const selectedType = String(overrideType || "").trim();
        const changedFields = [];
        if (Number(row[config.selectedField] || 0) !== 1) {
            row[config.selectedField] = 1;
            changedFields.push(config.selectedField);
        }
        if (String(row[config.overrideField] || "").trim() !== selectedType) {
            row[config.overrideField] = selectedType;
            changedFields.push(config.overrideField);
        }
        if (changedFields.length) {
            notifyChanged(frm, tr, row, config.overrideField, changedFields);
        }
    }

    function applyAllSides(frm, tr, selectedValue) {
        const row = materialize(frm, tr);
        if (!row) return;
        const overrideType = selectedValue === BULK_DEFAULT_VALUE
            ? ""
            : String(selectedValue || "").trim();
        const locked = lockedBreakSides(row);
        const changedFields = [];
        SIDE_CONFIG.forEach(config => {
            if (locked.has(config.selectedField)) return;
            if (Number(row[config.selectedField] || 0) !== 1) {
                row[config.selectedField] = 1;
                changedFields.push(config.selectedField);
            }
            if (String(row[config.overrideField] || "").trim() !== overrideType) {
                row[config.overrideField] = overrideType;
                changedFields.push(config.overrideField);
            }
        });
        if (changedFields.length) {
            notifyChanged(frm, tr, row, "all_side_edge_profiles", changedFields);
        }
    }

    function ensureBulkHeader(root) {
        const edgeTypeHeader = root.querySelector(".dco-fast-table thead th.dco-col-edge-type");
        if (!edgeTypeHeader) return;
        let header = root.querySelector(".dco-fast-table thead th.dco-col-edge-bulk");
        if (!header) {
            header = document.createElement("th");
            header.className = "dco-col-edge-bulk";
            edgeTypeHeader.insertAdjacentElement("afterend", header);
        }
        header.textContent = __("Apply to all four");
        header.title = __("Enable all four sides and apply one profile");
    }

    function ensureBulkButton(frm, tr) {
        const edgeTypeCell = tr.querySelector(":scope > td.dco-col-edge-type");
        if (!edgeTypeCell) return;

        let cell = tr.querySelector(":scope > td.dco-col-edge-bulk");
        if (!cell) {
            cell = document.createElement("td");
            cell.className = "dco-col-edge-bulk";
            edgeTypeCell.insertAdjacentElement("afterend", cell);
        }

        // Special / corner / rows without edge toggles still need this column so notes
        // stay on the same horizontal level as Regular rows.
        const hasEdgeButtons = Boolean(
            tr.querySelector(":scope > td.dco-col-edges .dco-edge-buttons")
        );
        if (!hasEdgeButtons) {
            cell.replaceChildren();
            return;
        }

        let content = cell.querySelector(":scope > .dco-edge-bulk-cell-content");
        if (!content) {
            content = document.createElement("div");
            content.className = "dco-edge-bulk-cell-content";
            cell.replaceChildren(content);
        }

        content.querySelectorAll(".dco-all-sides-profile-select").forEach(select => select.remove());

        let button = content.querySelector(".dco-all-sides-profile-button");
        if (!button) {
            button = document.createElement("button");
            button.type = "button";
            button.className = "dco-all-sides-profile-button";
            button.dataset.bulkEdgeProfileButton = "1";
            content.appendChild(button);
        }

        button.innerHTML = `<span>${__("Apply to all four")}</span><span class="dco-bulk-chevron">⌄</span>`;
        button.disabled = !isEditable(frm);
        button.title = __("Open a scrollable list and apply one profile to all four sides");
        button.setAttribute("aria-haspopup", "menu");
        button.setAttribute("aria-expanded", activePopover && activePopover.anchor === button ? "true" : "false");
    }

    function removeSideDropdownRows(cell) {
        cell.querySelectorAll(":scope > .dco-edge-profile-grid").forEach(grid => grid.remove());
    }

    function effectiveProfileLabel(frm, current) {
        const effective = current || String(frm.doc.default_edge_type || "").trim();
        if (!effective) return __("Not selected");
        const profile = profileMap(frm).get(effective);
        return String((profile && profile.label) || effective);
    }

    function decorateEdgeToggle(frm, row, toggle) {
        const config = configForToggle(toggle);
        if (!config) return;
        const current = String((row && row[config.overrideField]) || "").trim();
        const selected = Boolean(row && row[config.selectedField]);
        const effective = current || String(frm.doc.default_edge_type || "").trim();
        const missing = selected && (!effective || (frm._dco_side_edge_profiles_loaded && !profileMap(frm).has(effective)));
        const label = __(config.label);
        const mode = current
            ? (__("Custom"))
            : (__("Default"));
        const instruction = __("Click to toggle · Double-click to choose profile");

        toggle.dataset.edgeSide = config.side;
        toggle.classList.add("dco-edge-profile-target");
        toggle.classList.toggle("is-edge-custom", selected && Boolean(current));
        toggle.classList.toggle("is-edge-default", selected && !current);
        toggle.classList.toggle("is-edge-missing", missing);
        toggle.title = `${label} — ${mode}: ${effectiveProfileLabel(frm, current)} — ${instruction}`;
        toggle.setAttribute("aria-label", `${label}. ${instruction}`);
    }

    function removeObsoleteControls(cell) {
        cell.querySelectorAll(":scope > .dco-edge-bulk-toolbar,:scope > .dco-edge-direct-actions").forEach(element => element.remove());
        removeSideDropdownRows(cell);
    }

    function renderRow(frm, tr) {
        const cell = tr.querySelector(":scope > td.dco-col-edges");
        const edgeButtons = cell && cell.querySelector(":scope > .dco-edge-buttons");
        if (cell && edgeButtons) {
            removeObsoleteControls(cell);
            const row = rowByName(frm, tr.dataset.rowName) || {};
            edgeButtons.querySelectorAll(".dco-check-toggle[data-check-field]").forEach(toggle => {
                decorateEdgeToggle(frm, row, toggle);
            });
        }
        ensureBulkButton(frm, tr);
    }

    function renderHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help) return;
        let hint = help.querySelector(".dco-side-edge-help");
        if (!hint) {
            hint = document.createElement("span");
            hint.className = "dco-side-edge-help";
            help.appendChild(hint);
        }
        hint.textContent = __("Edge banding: click to toggle; double-click to choose a profile; lists are scrollable");
    }

    function closePopover() {
        if (!activePopover) return;
        const anchor = activePopover.anchor;
        activePopover.element.remove();
        activePopover = null;
        if (anchor && anchor.isConnected) {
            anchor.setAttribute("aria-expanded", "false");
        }
    }

    function bindPopoverDismiss() {
        if (dismissBound) return;
        dismissBound = true;
        document.addEventListener("pointerdown", event => {
            if (!activePopover || activePopover.element.contains(event.target)) return;
            closePopover();
        }, true);
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") closePopover();
        }, true);
        window.addEventListener("resize", closePopover, { passive: true });
        window.addEventListener("scroll", event => {
            if (!activePopover) return;
            if (event.target && activePopover.element.contains(event.target)) return;
            closePopover();
        }, { passive: true, capture: true });
    }

    function profileOptionHtml(value, label, description, current) {
        const isDefault = value === "";
        const selected = value === current;
        const customCurrent = selected && !isDefault;
        return `<button type="button" class="dco-edge-profile-option ${selected ? "is-current" : ""} ${customCurrent ? "is-custom-current" : ""}" data-profile-value="${escapeHtml(value)}" role="menuitemradio" aria-checked="${selected ? "true" : "false"}">
            <b>${escapeHtml(label)}</b>
            <small>${escapeHtml(description)}</small>
            <span>${selected ? "✓" : ""}</span>
        </button>`;
    }

    function bulkProfileOptionHtml(value, label, description) {
        return `<button type="button" class="dco-edge-profile-option" data-bulk-profile-value="${escapeHtml(value)}" role="menuitem">
            <b>${escapeHtml(label)}</b>
            <small>${escapeHtml(description)}</small>
            <span></span>
        </button>`;
    }

    function popoverOptionsHtml(frm, current) {
        const defaultType = String(frm.doc.default_edge_type || "").trim();
        const defaultLabel = __("Use default profile");
        const defaultDescription = defaultType
            ? `${__("Default")}: ${effectiveProfileLabel(frm, "")}`
            : (__("No order default selected"));
        return [
            profileOptionHtml("", defaultLabel, defaultDescription, current),
            ...profileEntries(frm, current).map(([value, label]) => (
                profileOptionHtml(value, label, profileDetails(frm, value), current)
            )),
        ].join("");
    }

    function bulkPopoverOptionsHtml(frm) {
        const defaultType = String(frm.doc.default_edge_type || "").trim();
        const defaultDescription = defaultType
            ? `${__("Default")}: ${effectiveProfileLabel(frm, "")}`
            : (__("No order default selected"));
        return [
            bulkProfileOptionHtml(
                BULK_DEFAULT_VALUE,
                __("Default for all four"),
                defaultDescription
            ),
            ...profileEntries(frm).map(([value, label]) => (
                bulkProfileOptionHtml(value, label, profileDetails(frm, value))
            )),
        ].join("");
    }

    function createPopover(title, subtitle, optionsHtml, ariaLabel) {
        const popover = document.createElement("div");
        popover.id = POPOVER_ID;
        popover.setAttribute("role", "menu");
        popover.setAttribute("aria-label", ariaLabel);
        const locale = window.AlmdinaLocale;
        const direction = locale && typeof locale.direction === "function" ? locale.direction() : "";
        if (direction === "ltr" || direction === "rtl") popover.setAttribute("dir", direction);
        popover.innerHTML = `
            <div class="dco-edge-popover-head">
                <div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(subtitle)}</small></div>
                <button type="button" class="dco-edge-popover-close" aria-label="${__("Close")}">×</button>
            </div>
            <div class="dco-edge-popover-options">${optionsHtml}</div>`;
        return popover;
    }

    function positionPopover(popover, anchor) {
        const margin = 8;
        const anchorRect = anchor.getBoundingClientRect();
        const rect = popover.getBoundingClientRect();
        const rtl = window.AlmdinaLocale ? AlmdinaLocale.isRTL() : document.documentElement.getAttribute("dir") !== "ltr";
        let left = rtl ? anchorRect.right - rect.width : anchorRect.left;
        left = Math.max(margin, Math.min(window.innerWidth - rect.width - margin, left));
        let top = anchorRect.bottom + 6;
        if (top + rect.height > window.innerHeight - margin) {
            top = anchorRect.top - rect.height - 6;
        }
        top = Math.max(margin, Math.min(window.innerHeight - rect.height - margin, top));
        popover.style.left = `${Math.round(left)}px`;
        popover.style.top = `${Math.round(top)}px`;
    }

    function mountPopover(popover, context) {
        document.body.appendChild(popover);
        activePopover = { element: popover, ...context };
        bindPopoverDismiss();
        context.anchor.setAttribute("aria-expanded", "true");
        positionPopover(popover, context.anchor);

        popover.addEventListener("pointerdown", event => event.stopPropagation(), true);
        popover.addEventListener("wheel", event => event.stopPropagation(), { passive: true });
        popover.addEventListener("touchmove", event => event.stopPropagation(), { passive: true });
    }

    function bindCloseButton(popover) {
        popover.addEventListener("click", event => {
            const close = event.target.closest(".dco-edge-popover-close");
            if (!close) return;
            event.preventDefault();
            closePopover();
        });
    }

    function openSidePopover(frm, tr, config, anchor) {
        if (!tr || !config || !anchor || !isEditable(frm)) return;
        closePopover();
        const row = materialize(frm, tr);
        if (!row) return;

        const current = String(row[config.overrideField] || "").trim();
        const label = __(config.label);
        const popover = createPopover(
            label,
            __("Choosing a profile enables the side"),
            popoverOptionsHtml(frm, current),
            __("Choose {0} profile", [label]),
        );
        mountPopover(popover, { frm, tr, config, anchor, kind: "side" });
        bindCloseButton(popover);

        popover.addEventListener("click", event => {
            const option = event.target.closest(".dco-edge-profile-option[data-profile-value]");
            if (!option) return;
            event.preventDefault();
            const value = option.dataset.profileValue || "";
            closePopover();
            applySideSelection(frm, tr, config, value);
        });

        const selected = popover.querySelector(".dco-edge-profile-option.is-current")
            || popover.querySelector(".dco-edge-profile-option");
        if (selected) selected.focus({ preventScroll: true });
    }

    function openBulkPopover(frm, tr, anchor) {
        if (!tr || !anchor || !isEditable(frm)) return;
        closePopover();
        if (!materialize(frm, tr)) return;

        const title = __("Apply to all four sides");
        const popover = createPopover(
            title,
            __("Scroll the list, then choose a profile"),
            bulkPopoverOptionsHtml(frm),
            title
        );
        mountPopover(popover, { frm, tr, anchor, kind: "bulk" });
        bindCloseButton(popover);

        popover.addEventListener("click", event => {
            const option = event.target.closest(".dco-edge-profile-option[data-bulk-profile-value]");
            if (!option) return;
            event.preventDefault();
            const value = option.dataset.bulkProfileValue || "";
            closePopover();
            applyAllSides(frm, tr, value);
        });

        const first = popover.querySelector(".dco-edge-profile-option");
        if (first) first.focus({ preventScroll: true });
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        ensureBulkHeader(root);
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => renderRow(frm, tr));
        renderHelp(root);
        bind(frm, root);
    }

    function bind(frm, root) {
        if (root._dcoCompactEdgeProfileControlsBound) return;
        root._dcoCompactEdgeProfileControlsBound = true;

        root.addEventListener("pointerdown", event => {
            const button = event.target.closest(".dco-all-sides-profile-button");
            if (!button || !root.contains(button)) return;
            event.stopPropagation();
        }, true);

        root.addEventListener("click", event => {
            const button = event.target.closest(".dco-all-sides-profile-button[data-bulk-edge-profile-button]");
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            const tr = button.closest("tr[data-row-name]");
            if (tr) openBulkPopover(frm, tr, button);
        }, true);

        root.addEventListener("dblclick", event => {
            const toggle = event.target.closest(".dco-check-toggle.dco-edge-profile-target[data-edge-side]");
            if (!toggle || !root.contains(toggle)) return;
            const config = SIDE_CONFIG.find(item => item.side === toggle.dataset.edgeSide);
            const tr = toggle.closest("tr[data-row-name]");
            if (!config || !tr) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            openSidePopover(frm, tr, config, toggle);
        }, true);

        let queued = false;
        const observer = new MutationObserver(() => {
            if (queued) return;
            queued = true;
            requestAnimationFrame(() => {
                queued = false;
                apply(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoCompactEdgeProfileControlsObserver = observer;
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 140);
    }

    function loadProfilesAndRender(frm) {
        const api = moduleApi();
        if (api && api.ensureProfiles) {
            Promise.resolve(api.ensureProfiles(frm)).finally(() => schedule(frm));
            return;
        }
        schedule(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { loadProfilesAndRender(frm); },
        refresh(frm) { loadProfilesAndRender(frm); },
        default_edge_type(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        edge_long_right(frm) { schedule(frm); },
        edge_long_left(frm) { schedule(frm); },
        edge_width_top(frm) { schedule(frm); },
        edge_width_bottom(frm) { schedule(frm); },
        edge_long_right_type_override(frm) { schedule(frm); },
        edge_long_left_type_override(frm) { schedule(frm); },
        edge_width_top_type_override(frm) { schedule(frm); },
        edge_width_bottom_type_override(frm) { schedule(frm); },
    });

    window.AlmdinaEdgeProfileControls = {
        apply,
        schedule,
        applySideSelection,
        applyAllSides,
        openSidePopover,
        openBulkPopover,
        closePopover,
    };
})();
