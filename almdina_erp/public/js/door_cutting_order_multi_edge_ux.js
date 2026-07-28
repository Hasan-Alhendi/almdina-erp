(() => {
    "use strict";

    const STYLE_ID = "dco-multi-edge-css";
    const AXES = {
        long: {
            field: "edge_long_type",
            sides: ["edge_long_right", "edge_long_left"],
            labelAr: "قشاط الطول",
            labelEn: "Long edge",
            sideLabelsAr: ["يمين", "يسار"],
        },
        width: {
            field: "edge_width_type",
            sides: ["edge_width_top", "edge_width_bottom"],
            labelAr: "قشاط العرض",
            labelEn: "Width edge",
            sideLabelsAr: ["أعلى", "أسفل"],
        },
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
        return round(value, decimals).toLocaleString("en-US", {
            maximumFractionDigits: decimals,
        });
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
        if (row || !tr || !String(tr.dataset.rowName || "").startsWith("__virtual__")) {
            return row;
        }
        const qtyInput = tr.querySelector("input[data-field='qty']");
        if (qtyInput) qtyInput.dispatchEvent(new Event("input", { bubbles: true }));
        return rowByName(frm, tr.dataset.rowName);
    }

    function axisCount(row, axis) {
        const config = AXES[axis];
        return config.sides.reduce((total, fieldname) => total + Number(Boolean(row && row[fieldname])), 0);
    }

    function selectedSideLabels(row, axis) {
        const config = AXES[axis];
        return config.sides
            .map((fieldname, index) => row && row[fieldname] ? config.sideLabelsAr[index] : "")
            .filter(Boolean);
    }

    function profiles(frm) {
        if (!(frm._dco_multi_edge_profiles instanceof Map)) {
            frm._dco_multi_edge_profiles = new Map();
        }
        return frm._dco_multi_edge_profiles;
    }

    function ensureProfiles(frm) {
        if (frm._dco_multi_edge_profiles_loaded) return Promise.resolve(profiles(frm));
        if (frm._dco_multi_edge_profiles_loading) return frm._dco_multi_edge_profiles_loading;

        frm._dco_multi_edge_profiles_loading = frappe.db.get_list("Edge Banding Type", {
            fields: [
                "name",
                "edge_type_name",
                "width_cm",
                "thickness_mm",
                "rate_usd_per_meter",
                "edge_color",
            ],
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
            frm._dco_multi_edge_profiles_loaded = true;
            schedule(frm);
            return map;
        }).catch(error => {
            console.error("Failed to load edge profiles", error);
            return profiles(frm);
        }).finally(() => {
            frm._dco_multi_edge_profiles_loading = null;
        });
        return frm._dco_multi_edge_profiles_loading;
    }

    function effectiveType(frm, row, axis) {
        if (!axisCount(row, axis)) return "";
        const fieldname = AXES[axis].field;
        return String((row && row[fieldname]) || frm.doc.default_edge_type || "").trim();
    }

    function profileFor(frm, row, axis) {
        const type = effectiveType(frm, row, axis);
        return type ? profiles(frm).get(type) || null : null;
    }

    function calculate(frm, row) {
        const finalWidth = num(row && row.width_cm);
        const finalLength = num(row && row.length_cm);
        const qtyValue = Math.max(1, Math.trunc(num(row && row.qty) || 1));
        const longCount = axisCount(row, "long");
        const widthCount = axisCount(row, "width");
        const longType = effectiveType(frm, row, "long");
        const widthType = effectiveType(frm, row, "width");
        const longProfile = profileFor(frm, row, "long");
        const widthProfile = profileFor(frm, row, "width");
        const longThickness = longProfile ? num(longProfile.thickness_mm) : 0;
        const widthThickness = widthProfile ? num(widthProfile.thickness_mm) : 0;
        const widthDeductionMm = longThickness * longCount;
        const lengthDeductionMm = widthThickness * widthCount;
        const cutWidth = round(finalWidth - widthDeductionMm / 10, 3);
        const cutLength = round(finalLength - lengthDeductionMm / 10, 3);
        const longMeters = round(finalLength * longCount * qtyValue / 100, 3);
        const widthMeters = round(finalWidth * widthCount * qtyValue / 100, 3);
        const longRate = longProfile ? num(longProfile.rate_usd_per_meter) : 0;
        const widthRate = widthProfile ? num(widthProfile.rate_usd_per_meter) : 0;
        const longCost = round(longMeters * longRate, 3);
        const widthCost = round(widthMeters * widthRate, 3);

        return {
            finalWidth,
            finalLength,
            qty: qtyValue,
            longCount,
            widthCount,
            longType,
            widthType,
            longProfile,
            widthProfile,
            longThickness,
            widthThickness,
            widthDeductionMm,
            lengthDeductionMm,
            cutWidth,
            cutLength,
            longMeters,
            widthMeters,
            edgeMeters: round(longMeters + widthMeters, 3),
            longRate,
            widthRate,
            longCost,
            widthCost,
            edgeCost: round(longCost + widthCost, 3),
            valid: finalWidth > 0 && finalLength > 0 && cutWidth > 0 && cutLength > 0,
            missingLongType: longCount > 0 && !longType,
            missingWidthType: widthCount > 0 && !widthType,
            unknownLongType: longCount > 0 && Boolean(longType) && !longProfile,
            unknownWidthType: widthCount > 0 && Boolean(widthType) && !widthProfile,
        };
    }

    function syncPreviewFields(row, result) {
        if (!row) return;
        row.edge_long_thickness_mm = result.longThickness;
        row.edge_width_thickness_mm = result.widthThickness;
        row.cut_width_cm = result.valid ? result.cutWidth : 0;
        row.cut_length_cm = result.valid ? result.cutLength : 0;
        row.cut_size_label = result.valid ? `${format(result.cutWidth)} × ${format(result.cutLength)}` : "";
        row.edge_long_meters = result.longMeters;
        row.edge_width_meters = result.widthMeters;
        row.edge_meters = result.edgeMeters;
        row.edge_long_rate_usd = result.longRate;
        row.edge_width_rate_usd = result.widthRate;
        row.edge_long_cost_usd = result.longCost;
        row.edge_width_cost_usd = result.widthCost;
        row.edge_cost_usd = result.edgeCost;
        const types = [result.longType, result.widthType].filter(Boolean);
        row.edge_type = types.length && new Set(types).size === 1 ? types[0] : "";
        const rates = [
            result.longCount ? result.longRate : null,
            result.widthCount ? result.widthRate : null,
        ].filter(value => value !== null);
        row.edge_rate_usd = rates.length && new Set(rates).size === 1 ? rates[0] : 0;
        const thicknesses = [
            result.longCount ? result.longThickness : null,
            result.widthCount ? result.widthThickness : null,
        ].filter(value => value !== null);
        row.edge_thickness_mm = thicknesses.length && new Set(thicknesses).size === 1 ? thicknesses[0] : 0;
    }

    function detailForAxis(frm, row, axis) {
        const result = calculate(frm, row);
        const config = AXES[axis];
        const isLong = axis === "long";
        const count = isLong ? result.longCount : result.widthCount;
        if (!count) return null;
        const type = isLong ? result.longType : result.widthType;
        const profile = isLong ? result.longProfile : result.widthProfile;
        return {
            axis,
            axis_label: isArabic() ? config.labelAr : config.labelEn,
            edge_type: type,
            sides: selectedSideLabels(row, axis),
            side_count: count,
            thickness_mm: isLong ? result.longThickness : result.widthThickness,
            meters: isLong ? result.longMeters : result.widthMeters,
            rate: isLong ? result.longRate : result.widthRate,
            amount: isLong ? result.longCost : result.widthCost,
            color: profile ? profile.edge_color : "",
        };
    }

    function details(frm, row) {
        return [detailForAxis(frm, row, "long"), detailForAxis(frm, row, "width")].filter(Boolean);
    }

    function optionHtml(frm, selected, active, axis) {
        const placeholder = active
            ? (isArabic() ? `اختر ${AXES[axis].labelAr}` : `Select ${AXES[axis].labelEn}`)
            : (isArabic() ? "لا توجد جهة محددة" : "No selected side");
        const values = new Map();
        profiles(frm).forEach(profile => values.set(profile.name, profile.label));
        if (selected && !values.has(selected)) values.set(selected, selected);
        return `<option value="">${esc(placeholder)}</option>` + [...values.entries()]
            .map(([value, label]) => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(label)}</option>`)
            .join("");
    }

    function axisMeta(frm, row, axis) {
        const count = axisCount(row, axis);
        if (!count) return isArabic() ? "غير مستخدم" : "Not used";
        const type = effectiveType(frm, row, axis);
        if (!type) return isArabic() ? "حدد النوع" : "Select type";
        const profile = profiles(frm).get(type);
        if (!profile) return frm._dco_multi_edge_profiles_loaded
            ? (isArabic() ? "نوع غير متاح" : "Unavailable type")
            : (isArabic() ? "تحميل البيانات…" : "Loading…");
        return `${format(profile.thickness_mm)} مم · $ ${money(profile.rate_usd_per_meter)}/م`;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table .dco-col-edge-type{width:238px!important;min-width:238px!important;max-width:238px!important}
            .dco-axis-edge-editor{display:grid;gap:4px}
            .dco-axis-edge-row{display:grid;grid-template-columns:45px minmax(0,1fr);gap:5px;align-items:center;padding:3px 4px;border:1px solid var(--border-color,#dfe3e8);border-radius:8px;background:var(--subtle-fg,#f8f9fa)}
            .dco-axis-edge-row.is-active{border-color:rgba(36,144,239,.25);background:rgba(36,144,239,.045)}
            .dco-axis-edge-label{font-size:10px;font-weight:900;text-align:center;line-height:1.2}
            .dco-axis-edge-control{min-width:0}
            .dco-axis-edge-select{width:100%;min-height:29px;border:1px solid var(--border-color,#ccd3da);border-radius:7px;background:var(--control-bg,#fff);padding:3px 6px;font-size:11px;outline:none}
            .dco-axis-edge-select:focus{border-color:var(--primary,#2490ef);box-shadow:0 0 0 2px rgba(36,144,239,.12)}
            .dco-axis-edge-select:disabled{opacity:.55;cursor:not-allowed}
            .dco-axis-edge-meta{display:block;margin-top:2px;color:var(--text-muted,#6c7680);font-size:8.5px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
            .dco-multi-edge-help{display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:999px;background:rgba(36,144,239,.08);font-weight:700}
            .dco-edge-detail-list{display:grid;gap:3px;min-width:150px}
            .dco-edge-detail-badge{display:flex;align-items:center;justify-content:space-between;gap:7px;padding:3px 6px;border-radius:7px;background:var(--subtle-fg,#f7f9fa);border:1px solid var(--border-color,#e2e6ea);font-size:10px}
            .dco-edge-detail-badge b{font-size:10px}.dco-edge-detail-badge span{color:var(--text-muted,#66717e)}
            @media(max-width:900px){.dco-fast-table .dco-col-edge-type{width:215px!important;min-width:215px!important;max-width:215px!important}}
        `;
        document.head.appendChild(style);
    }

    function renderAxisEditor(frm, tr, row, axis) {
        const active = axisCount(row, axis) > 0;
        const selected = effectiveType(frm, row, axis);
        const config = AXES[axis];
        const label = isArabic() ? (axis === "long" ? "الطول" : "العرض") : (axis === "long" ? "Long" : "Width");
        return `
            <div class="dco-axis-edge-row ${active ? "is-active" : ""}" data-axis="${axis}">
                <span class="dco-axis-edge-label">${label}</span>
                <span class="dco-axis-edge-control">
                    <select class="dco-axis-edge-select" data-axis-edge-field="${config.field}" data-axis="${axis}" ${active ? "" : "disabled"}>
                        ${optionHtml(frm, selected, active, axis)}
                    </select>
                    <small class="dco-axis-edge-meta">${esc(axisMeta(frm, row, axis))}</small>
                </span>
            </div>`;
    }

    function renderRow(frm, tr) {
        const row = rowByName(frm, tr.dataset.rowName) || {
            qty: 1,
            edge_long_right: tr.querySelector("[data-check-field='edge_long_right']")?.classList.contains("is-checked") ? 1 : 0,
            edge_long_left: tr.querySelector("[data-check-field='edge_long_left']")?.classList.contains("is-checked") ? 1 : 0,
            edge_width_top: tr.querySelector("[data-check-field='edge_width_top']")?.classList.contains("is-checked") ? 1 : 0,
            edge_width_bottom: tr.querySelector("[data-check-field='edge_width_bottom']")?.classList.contains("is-checked") ? 1 : 0,
        };
        const cell = tr.querySelector(":scope > td.dco-col-edge-type");
        if (!cell) return;
        const result = calculate(frm, row);
        syncPreviewFields(rowByName(frm, tr.dataset.rowName), result);
        const signature = JSON.stringify([
            result.longCount,
            result.widthCount,
            result.longType,
            result.widthType,
            frm._dco_multi_edge_profiles_loaded,
        ]);
        if (cell.dataset.multiEdgeSignature === signature) return;
        cell.dataset.multiEdgeSignature = signature;
        cell.innerHTML = `<div class="dco-axis-edge-editor">${renderAxisEditor(frm, tr, row, "long")}${renderAxisEditor(frm, tr, row, "width")}</div>`;
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        const header = root.querySelector(".dco-fast-table thead th.dco-col-edge-type");
        if (header) {
            header.textContent = isArabic() ? "نوعا القشاط" : "Edge profiles";
            header.title = isArabic()
                ? "نوع مستقل لقشاط الطول ونوع مستقل لقشاط العرض"
                : "Independent profiles for long and width edges";
        }
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => renderRow(frm, tr));
        const help = root.querySelector(".dco-fast-help");
        if (help && !help.querySelector(".dco-multi-edge-help")) {
            const hint = document.createElement("span");
            hint.className = "dco-multi-edge-help";
            hint.textContent = isArabic()
                ? "الافتراضي يُملأ تلقائيًا، غيّر الطول أو العرض عند الاستثناء"
                : "Default is automatic; change long or width only for exceptions";
            help.appendChild(hint);
        }
        bind(frm, root);
    }

    function normalizeAxisType(frm, row, axis) {
        const fieldname = AXES[axis].field;
        if (!axisCount(row, axis)) {
            if (row[fieldname]) row[fieldname] = "";
            return;
        }
        if (!row[fieldname] && frm.doc.default_edge_type) {
            row[fieldname] = frm.doc.default_edge_type;
        }
    }

    function notifyChanged(frm, row, fieldname) {
        frm.dirty();
        Promise.resolve(frm.script_manager.trigger(fieldname, row.doctype, row.name)).catch(() => {});
        const root = rootFor(frm);
        if (root) root.dispatchEvent(new CustomEvent("dco:multi-edge-change", { bubbles: true, detail: { row: row.name, fieldname } }));
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        schedule(frm);
    }

    function bind(frm, root) {
        if (root._dcoMultiEdgeBound) return;
        root._dcoMultiEdgeBound = true;

        root.addEventListener("change", event => {
            const select = event.target.closest("select[data-axis-edge-field]");
            if (!select || !root.contains(select)) return;
            const tr = select.closest("tr[data-row-name]");
            const row = materialize(frm, tr);
            if (!row) return;
            const fieldname = select.dataset.axisEdgeField;
            row[fieldname] = select.value || "";
            notifyChanged(frm, row, fieldname);
        });

        root.addEventListener("click", event => {
            const toggle = event.target.closest(".dco-check-toggle[data-check-field]");
            if (!toggle || !root.contains(toggle)) return;
            const fieldname = toggle.dataset.checkField || "";
            if (!fieldname.startsWith("edge_")) return;
            requestAnimationFrame(() => {
                const tr = toggle.closest("tr[data-row-name]");
                const row = rowByName(frm, tr && tr.dataset.rowName);
                if (!row) return;
                const axis = fieldname.startsWith("edge_long_") ? "long" : "width";
                normalizeAxisType(frm, row, axis);
                notifyChanged(frm, row, AXES[axis].field);
            });
        });

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
        root._dcoMultiEdgeObserver = observer;
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 120);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            ensureProfiles(frm).finally(() => schedule(frm));
        },
        refresh(frm) {
            ensureProfiles(frm).finally(() => schedule(frm));
        },
        default_edge_type(frm) {
            (frm.doc.pieces || []).forEach(row => {
                normalizeAxisType(frm, row, "long");
                normalizeAxisType(frm, row, "width");
            });
            schedule(frm);
        },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        edge_long_type(frm) { schedule(frm); },
        edge_width_type(frm) { schedule(frm); },
        edge_long_right(frm) { schedule(frm); },
        edge_long_left(frm) { schedule(frm); },
        edge_width_top(frm) { schedule(frm); },
        edge_width_bottom(frm) { schedule(frm); },
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
        detailForAxis,
        schedule,
        format,
        money,
    };
})();
