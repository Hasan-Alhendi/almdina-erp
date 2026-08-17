(() => {
    "use strict";

    const STYLE_ID = "dco-side-edge-profile-css";
    const SIDE_ORDER = ["width_top", "width_bottom", "long_right", "long_left"];
    const SIDES = {
        long_right: { selectedField: "edge_long_right", overrideField: "edge_long_right_type_override", labelAr: "الطول الأيمن", labelEn: "Right long edge", axis: "long" },
        long_left: { selectedField: "edge_long_left", overrideField: "edge_long_left_type_override", labelAr: "الطول الأيسر", labelEn: "Left long edge", axis: "long" },
        width_top: { selectedField: "edge_width_top", overrideField: "edge_width_top_type_override", labelAr: "العرض العلوي", labelEn: "Top width edge", axis: "width" },
        width_bottom: { selectedField: "edge_width_bottom", overrideField: "edge_width_bottom_type_override", labelAr: "العرض السفلي", labelEn: "Bottom width edge", axis: "width" },
    };

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang || ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function num(value) {
        if (value === null || value === undefined || value === "") return 0;
        const result = Number(String(value).replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function round(value, decimals = 3) {
        const factor = 10 ** decimals;
        return Math.round(num(value) * factor) / factor;
    }

    function format(value, decimals = 3) {
        return round(value, decimals).toLocaleString("en-US", { maximumFractionDigits: decimals });
    }

    function money(value) {
        return num(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
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
        if (row || !tr || !String(tr.dataset.rowName || "").startsWith("__virtual__")) return row;
        const qtyInput = tr.querySelector("input[data-field='qty']");
        if (qtyInput) qtyInput.dispatchEvent(new Event("input", { bubbles: true }));
        return rowByName(frm, tr.dataset.rowName);
    }

    function profiles(frm) {
        if (!(frm._dco_side_edge_profiles instanceof Map)) {
            frm._dco_side_edge_profiles = new Map();
        }
        return frm._dco_side_edge_profiles;
    }

    function ensureProfiles(frm) {
        if (frm._dco_side_edge_profiles_loaded) return Promise.resolve(profiles(frm));
        if (frm._dco_side_edge_profiles_loading) return frm._dco_side_edge_profiles_loading;

        frm._dco_side_edge_profiles_loading = frappe.db.get_list("Edge Banding Type", {
            fields: ["name", "edge_type_name", "width_cm", "thickness_mm", "rate_usd_per_meter", "edge_color"],
            filters: { disabled: 0 },
            order_by: "width_cm asc, edge_type_name asc",
            limit: 200,
        }).then(rows => {
            const map = profiles(frm);
            map.clear();
            (rows || []).forEach(row => {
                const name = String(row.name || row.edge_type_name || "").trim();
                if (!name) return;
                map.set(name, {
                    name,
                    label: String(row.edge_type_name || name),
                    width_cm: num(row.width_cm),
                    thickness_mm: num(row.thickness_mm),
                    rate_usd_per_meter: num(row.rate_usd_per_meter),
                    edge_color: String(row.edge_color || ""),
                });
            });
            frm._dco_side_edge_profiles_loaded = true;
            schedule(frm);
            return map;
        }).catch(error => {
            console.error("Failed to load edge profiles", error);
            return profiles(frm);
        }).finally(() => {
            frm._dco_side_edge_profiles_loading = null;
        });
        return frm._dco_side_edge_profiles_loading;
    }

    function sideSelected(row, side) {
        return Boolean(row && row[SIDES[side].selectedField]);
    }

    function overrideType(row, side) {
        return String((row && row[SIDES[side].overrideField]) || "").trim();
    }

    function effectiveType(frm, row, side) {
        if (!sideSelected(row, side)) return "";
        return overrideType(row, side) || String(frm.doc.default_edge_type || "").trim();
    }

    function profileFor(frm, row, side) {
        const type = effectiveType(frm, row, side);
        return type ? profiles(frm).get(type) || null : null;
    }

    function common(values) {
        const active = values.filter(value => value !== null && value !== undefined && value !== "");
        if (!active.length) return "";
        const unique = new Set(active);
        return unique.size === 1 ? active[0] : "";
    }

    function calculate(frm, row) {
        const finalWidth = num(row && row.width_cm);
        const finalLength = num(row && row.length_cm);
        const qtyValue = Math.max(1, Math.trunc(num(row && row.qty) || 1));
        const sides = {};

        SIDE_ORDER.forEach(side => {
            const config = SIDES[side];
            const selected = sideSelected(row, side);
            const type = effectiveType(frm, row, side);
            const profile = selected ? profileFor(frm, row, side) : null;
            const dimension = config.axis === "long" ? finalLength : finalWidth;
            const meters = selected ? round(dimension * qtyValue / 100, 3) : 0;
            const thickness = profile ? num(profile.thickness_mm) : 0;
            const rate = profile ? num(profile.rate_usd_per_meter) : 0;
            sides[side] = {
                side,
                selected,
                custom: Boolean(overrideType(row, side)),
                type,
                profile,
                thickness,
                meters,
                rate,
                amount: round(meters * rate, 3),
            };
        });

        const longSides = [sides.long_right, sides.long_left].filter(item => item.selected);
        const widthSides = [sides.width_top, sides.width_bottom].filter(item => item.selected);
        const selectedSides = SIDE_ORDER.map(side => sides[side]).filter(item => item.selected);
        const widthDeductionMm = round(longSides.reduce((sum, item) => sum + item.thickness, 0), 3);
        const lengthDeductionMm = round(widthSides.reduce((sum, item) => sum + item.thickness, 0), 3);
        const cutWidth = round(finalWidth - widthDeductionMm / 10, 3);
        const cutLength = round(finalLength - lengthDeductionMm / 10, 3);
        const longMeters = round(longSides.reduce((sum, item) => sum + item.meters, 0), 3);
        const widthMeters = round(widthSides.reduce((sum, item) => sum + item.meters, 0), 3);
        const longCost = round(longSides.reduce((sum, item) => sum + item.amount, 0), 3);
        const widthCost = round(widthSides.reduce((sum, item) => sum + item.amount, 0), 3);

        return {
            finalWidth,
            finalLength,
            qty: qtyValue,
            sides,
            selectedSides,
            widthDeductionMm,
            lengthDeductionMm,
            cutWidth,
            cutLength,
            longMeters,
            widthMeters,
            edgeMeters: round(longMeters + widthMeters, 3),
            longCost,
            widthCost,
            edgeCost: round(longCost + widthCost, 3),
            longType: common(longSides.map(item => item.type)),
            widthType: common(widthSides.map(item => item.type)),
            edgeType: common(selectedSides.map(item => item.type)),
            longThickness: common(longSides.map(item => item.thickness)) || 0,
            widthThickness: common(widthSides.map(item => item.thickness)) || 0,
            edgeThickness: common(selectedSides.map(item => item.thickness)) || 0,
            longRate: common(longSides.map(item => item.rate)) || 0,
            widthRate: common(widthSides.map(item => item.rate)) || 0,
            edgeRate: common(selectedSides.map(item => item.rate)) || 0,
            valid: finalWidth > 0 && finalLength > 0 && cutWidth > 0 && cutLength > 0,
            missingType: selectedSides.some(item => !item.type),
            unknownType: selectedSides.some(item => item.type && !item.profile),
        };
    }

    function syncPreviewFields(row, result) {
        if (!row) return;
        row.edge_long_type = result.longType;
        row.edge_width_type = result.widthType;
        row.edge_type = result.edgeType;
        row.edge_long_thickness_mm = result.longThickness;
        row.edge_width_thickness_mm = result.widthThickness;
        row.edge_thickness_mm = result.edgeThickness;
        row.cut_width_cm = result.valid ? result.cutWidth : 0;
        row.cut_length_cm = result.valid ? result.cutLength : 0;
        row.cut_size_label = result.valid ? `${format(result.cutWidth)} × ${format(result.cutLength)}` : "";
        row.edge_long_meters = result.longMeters;
        row.edge_width_meters = result.widthMeters;
        row.edge_meters = result.edgeMeters;
        row.edge_long_rate_usd = result.longRate;
        row.edge_width_rate_usd = result.widthRate;
        row.edge_rate_usd = result.edgeRate;
        row.edge_long_cost_usd = result.longCost;
        row.edge_width_cost_usd = result.widthCost;
        row.edge_cost_usd = result.edgeCost;
    }

    function detailForSide(frm, row, side) {
        const result = calculate(frm, row);
        const item = result.sides[side];
        if (!item || !item.selected) return null;
        const config = SIDES[side];
        return {
            side,
            side_label: isArabic() ? config.labelAr : config.labelEn,
            axis: config.axis,
            axis_label: config.axis === "long" ? "الطول" : "العرض",
            edge_type: item.type,
            custom: item.custom,
            thickness_mm: item.thickness,
            meters: item.meters,
            rate: item.rate,
            amount: item.amount,
            color: item.profile ? item.profile.edge_color : "",
        };
    }

    function details(frm, row) {
        return SIDE_ORDER.map(side => detailForSide(frm, row, side)).filter(Boolean);
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table th.dco-col-edge-type,
            .dco-fast-table td.dco-col-edge-type{display:none!important}
            .dco-fast-table .dco-col-edges{overflow:visible!important}
            .dco-edge-buttons{padding-top:7px!important;overflow:visible!important}
            .dco-col-edges .dco-check-toggle{overflow:visible!important;position:relative!important}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger{
                display:flex!important;position:absolute;z-index:4;top:-10px;inset-inline-end:-4px;
                align-items:center;justify-content:center;width:17px;height:17px;border-radius:999px;
                border:1px solid var(--border-color,#cbd2d9);background:var(--card-bg,#fff);
                color:var(--text-muted,#64707d);font-size:12px!important;font-weight:900;line-height:1;
                box-shadow:0 2px 5px rgba(15,23,42,.12);cursor:pointer;opacity:.42;
                transition:transform .12s ease,opacity .12s ease,border-color .12s ease,background .12s ease;
            }
            .dco-col-edges .dco-check-toggle.is-checked>.dco-side-profile-trigger{opacity:.9}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger:hover{opacity:1;transform:translateY(-1px);border-color:var(--primary,#2490ef)}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger.is-custom{opacity:1;background:#fff6db;border-color:#d7a514;color:#8b6400;box-shadow:0 2px 6px rgba(185,132,0,.2)}
            .dco-col-edges .dco-check-toggle>.dco-side-profile-trigger.is-missing{background:#fff0f0;border-color:#df5a5a;color:#b72d2d;opacity:1}
            .dco-side-edge-help{display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:999px;background:rgba(36,144,239,.08);font-weight:700}
            .dco-side-edge-help b{font-size:12px}
            .dco-side-profile-summary{padding:8px 10px;border:1px solid var(--border-color,#dfe3e8);border-radius:9px;background:var(--subtle-fg,#f7f9fb);line-height:1.7}
            .dco-side-profile-summary strong{display:block;font-size:13px}.dco-side-profile-summary span{font-size:11px;color:var(--text-muted,#66717e)}
        `;
        document.head.appendChild(style);
    }

    function sideFromToggle(toggle) {
        const selectedField = toggle && toggle.dataset.checkField;
        return SIDE_ORDER.find(side => SIDES[side].selectedField === selectedField) || "";
    }

    function indicatorTitle(frm, row, side) {
        const config = SIDES[side];
        const label = isArabic() ? config.labelAr : config.labelEn;
        if (!sideSelected(row, side)) {
            return isArabic() ? `${label}: فعّل القشاط أولًا` : `${label}: enable edge banding first`;
        }
        const type = effectiveType(frm, row, side);
        const profile = profileFor(frm, row, side);
        const mode = overrideType(row, side) ? (isArabic() ? "مخصص" : "Custom") : (isArabic() ? "افتراضي" : "Default");
        const meta = profile
            ? `${format(profile.thickness_mm)} مم · $ ${money(profile.rate_usd_per_meter)}/م`
            : (isArabic() ? "نوع غير متاح" : "Unavailable profile");
        return `${label} — ${type || "—"} — ${mode} — ${meta}`;
    }

    function decorateToggle(frm, row, toggle) {
        const side = sideFromToggle(toggle);
        if (!side) return;
        let indicator = toggle.querySelector(":scope > .dco-side-profile-trigger");
        if (!indicator) {
            indicator = document.createElement("span");
            indicator.className = "dco-side-profile-trigger";
            indicator.setAttribute("role", "button");
            indicator.setAttribute("aria-label", isArabic() ? "تخصيص نوع القشاط لهذا الضلع" : "Customize this edge profile");
            indicator.dataset.edgeSide = side;
            toggle.appendChild(indicator);
        }
        const selected = sideSelected(row, side);
        const custom = Boolean(overrideType(row, side));
        const type = effectiveType(frm, row, side);
        const missing = selected && (!type || (frm._dco_side_edge_profiles_loaded && !profileFor(frm, row, side)));
        indicator.textContent = custom ? "✦" : "⌄";
        indicator.classList.toggle("is-custom", custom);
        indicator.classList.toggle("is-missing", missing);
        indicator.title = indicatorTitle(frm, row, side);
        indicator.setAttribute("aria-pressed", custom ? "true" : "false");
    }

    function renderRow(frm, tr) {
        const row = rowByName(frm, tr.dataset.rowName) || {
            qty: 1,
            edge_long_right: tr.querySelector("[data-check-field='edge_long_right']")?.classList.contains("is-checked") ? 1 : 0,
            edge_long_left: tr.querySelector("[data-check-field='edge_long_left']")?.classList.contains("is-checked") ? 1 : 0,
            edge_width_top: tr.querySelector("[data-check-field='edge_width_top']")?.classList.contains("is-checked") ? 1 : 0,
            edge_width_bottom: tr.querySelector("[data-check-field='edge_width_bottom']")?.classList.contains("is-checked") ? 1 : 0,
        };
        syncPreviewFields(rowByName(frm, tr.dataset.rowName), calculate(frm, row));
        tr.querySelectorAll(".dco-check-toggle[data-check-field]").forEach(toggle => decorateToggle(frm, row, toggle));
        tr.querySelectorAll(":scope > td.dco-col-edge-type").forEach(cell => cell.setAttribute("aria-hidden", "true"));
    }

    function renderHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help) return;
        const old = help.querySelector(".dco-multi-edge-help");
        if (old) old.remove();
        let hint = help.querySelector(".dco-side-edge-help");
        if (!hint) {
            hint = document.createElement("span");
            hint.className = "dco-side-edge-help";
            help.appendChild(hint);
        }
        hint.innerHTML = isArabic()
            ? '<b>⌄</b><span>كل ضلع يأخذ الافتراضي؛ اضغط الرمز فوقه للتخصيص الاستثنائي</span>'
            : '<b>⌄</b><span>Each side uses the default; select its icon only for an exception</span>';
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        const header = root.querySelector(".dco-fast-table thead th.dco-col-edge-type");
        if (header) header.setAttribute("aria-hidden", "true");
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => renderRow(frm, tr));
        renderHelp(root);
        bind(frm, root);
    }

    function notifyChanged(frm, row, fieldname) {
        frm.dirty();
        Promise.resolve(frm.script_manager.trigger(fieldname, row.doctype, row.name)).catch(() => {});
        const root = rootFor(frm);
        if (root) root.dispatchEvent(new CustomEvent("dco:side-edge-change", {
            bubbles: true,
            detail: { row: row.name, fieldname },
        }));
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        schedule(frm);
    }

    function defaultSummary(frm) {
        const type = String(frm.doc.default_edge_type || "").trim();
        const profile = type ? profiles(frm).get(type) || null : null;
        if (!type) return isArabic() ? "لم يتم اختيار قشاط افتراضي للطلب." : "No default edge profile selected.";
        if (!profile) return `${esc(type)} — ${isArabic() ? "جاري تحميل البيانات أو النوع غير متاح" : "Loading or unavailable"}`;
        return `${esc(type)} — ${format(profile.thickness_mm)} مم — $ ${money(profile.rate_usd_per_meter)}/م`;
    }

    function openSideDialog(frm, tr, side) {
        const row = materialize(frm, tr);
        if (!row) return;
        const config = SIDES[side];
        const label = isArabic() ? config.labelAr : config.labelEn;
        if (!sideSelected(row, side)) {
            frappe.show_alert({
                message: isArabic() ? `فعّل قشاط ${label} أولًا.` : `Enable ${label} first.`,
                indicator: "orange",
            });
            return;
        }

        const dialog = new frappe.ui.Dialog({
            title: isArabic() ? `تخصيص قشاط ${label}` : `Customize ${label}`,
            fields: [
                {
                    fieldname: "default_summary",
                    fieldtype: "HTML",
                    options: `<div class="dco-side-profile-summary"><strong>${isArabic() ? "القشاط الافتراضي" : "Default profile"}</strong><span>${defaultSummary(frm)}</span></div>`,
                },
                {
                    fieldname: "edge_type_override",
                    fieldtype: "Link",
                    options: "Edge Banding Type",
                    label: isArabic() ? "نوع خاص لهذا الضلع" : "Custom profile for this side",
                    description: isArabic()
                        ? "اترك الحقل فارغًا ليستخدم هذا الضلع القشاط الافتراضي للطلب."
                        : "Leave empty to use the order default.",
                    default: overrideType(row, side),
                },
            ],
            primary_action_label: isArabic() ? "حفظ التخصيص" : "Save override",
            primary_action(values) {
                row[config.overrideField] = String(values.edge_type_override || "").trim();
                dialog.hide();
                notifyChanged(frm, row, config.overrideField);
            },
        });
        dialog.show();

        const footer = dialog.$wrapper && dialog.$wrapper.find(".modal-footer");
        if (footer && footer.length) {
            const reset = document.createElement("button");
            reset.type = "button";
            reset.className = "btn btn-default btn-sm";
            reset.textContent = isArabic() ? "استخدام الافتراضي" : "Use default";
            reset.addEventListener("click", () => {
                row[config.overrideField] = "";
                dialog.hide();
                notifyChanged(frm, row, config.overrideField);
            });
            footer.prepend(reset);
        }
    }

    function clearOverrideWhenDisabled(frm, row, side) {
        const config = SIDES[side];
        if (!sideSelected(row, side) && row[config.overrideField]) {
            row[config.overrideField] = "";
            notifyChanged(frm, row, config.overrideField);
            return true;
        }
        return false;
    }

    function bind(frm, root) {
        if (root._dcoSideEdgeBound) return;
        root._dcoSideEdgeBound = true;

        root.addEventListener("pointerdown", event => {
            const indicator = event.target.closest(".dco-side-profile-trigger");
            if (!indicator || !root.contains(indicator)) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
        }, true);

        // Capture phase is essential: the legacy edge-toggle handler is registered
        // earlier on the same root. The indicator must open its dialog without also
        // toggling the side underneath it.
        root.addEventListener("click", event => {
            const indicator = event.target.closest(".dco-side-profile-trigger");
            if (indicator && root.contains(indicator)) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                const tr = indicator.closest("tr[data-row-name]");
                openSideDialog(frm, tr, indicator.dataset.edgeSide);
                return;
            }

            const toggle = event.target.closest(".dco-check-toggle[data-check-field]");
            if (!toggle || !root.contains(toggle)) return;
            const side = sideFromToggle(toggle);
            if (!side) return;
            requestAnimationFrame(() => {
                const tr = toggle.closest("tr[data-row-name]");
                const row = rowByName(frm, tr && tr.dataset.rowName);
                if (!row) return;
                if (!clearOverrideWhenDisabled(frm, row, side)) schedule(frm);
            });
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
        root._dcoSideEdgeObserver = observer;
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 120);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { ensureProfiles(frm).finally(() => schedule(frm)); },
        refresh(frm) { ensureProfiles(frm).finally(() => schedule(frm)); },
        default_edge_type(frm) { schedule(frm); },
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
        width_cm(frm) { schedule(frm); },
        length_cm(frm) { schedule(frm); },
        qty(frm) { schedule(frm); },
    });

    window.AlmdinaMultiEdgeBanding = {
        ensureProfiles,
        profiles,
        effectiveType,
        profileFor,
        calculate,
        details,
        detailForSide,
        schedule,
        format,
        money,
    };
})();
