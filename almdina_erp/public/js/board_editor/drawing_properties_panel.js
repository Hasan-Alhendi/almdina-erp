/* Drawing properties are a view of the current drawing session. This module does not own selection, tools, or manufacturing geometry. */
(() => {
    "use strict";

    const openSections = {};
    let lastSignature = "";

    function esc(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }

    function frappeIcon(name) {
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "sm", "", "", "currentColor", true);
        }
        return `<svg class="icon icon-sm abe-tool-icon" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-${esc(name)}"></use></svg>`;
    }

    function propButton(label, attrs, tone) {
        const kind = tone || "secondary";
        return `<button type="button" class="abe-prop-btn is-${kind}" ${attrs || ""}>${esc(__(label))}</button>`;
    }

    function iconAction(iconName, label, attrs, alreadyTranslated, tone) {
        const translated = alreadyTranslated ? label : __(label);
        const kind = tone || "secondary";
        return `<button type="button" class="abe-prop-btn is-${kind} abe-prop-btn-icon" ${attrs || ""} title="${esc(translated)}" aria-label="${esc(translated)}">${frappeIcon(iconName)}</button>`;
    }

    function shapeGlyph(id) {
        const common = `viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"`;
        const marks = {
            rectangle: `<rect x="4" y="6" width="16" height="12" rx="1"/>`,
            circle: `<circle cx="12" cy="12" r="7"/>`,
            ellipse: `<ellipse cx="12" cy="12" rx="8" ry="5"/>`,
            arc: `<path d="M5 16a7 7 0 0 1 14 0"/>`,
            polygon: `<path d="M12 4 20 10 17 19H7L4 10Z"/>`,
            trapezoid: `<path d="M7 6h10l3 12H4Z"/>`,
            l_shape: `<path d="M5 4h6v8h8v8H5Z"/>`,
            clipped_corner: `<path d="M5 5h8l6 6v8H5Z"/>`,
            bezier: `<path d="M4 17C8 5 16 5 20 17"/><circle cx="4" cy="17" r="1.2" fill="currentColor" stroke="none"/><circle cx="20" cy="17" r="1.2" fill="currentColor" stroke="none"/>`,
        };
        return `<svg class="abe-shape-glyph" ${common}>${marks[id] || marks.rectangle}</svg>`;
    }

    function pageDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") return locale.direction();
        return (frappe.boot && frappe.boot.lang === "ar") ? "rtl" : "ltr";
    }

    function formatMeasureMm(value) {
        if (value == null || value === "") return "";
        const number = Number(value);
        if (!Number.isFinite(number)) return "";
        return String(Math.round(number * 1000) / 1000);
    }

    function formatMeasureAngle(value) {
        if (value == null || value === "") return "";
        const number = Number(value);
        if (!Number.isFinite(number)) return "";
        let wrapped = number % 360;
        if (wrapped < 0) wrapped += 360;
        if (Math.abs(wrapped) < 1e-9 || Math.abs(wrapped - 360) < 1e-9) wrapped = 0;
        return String(Math.round(wrapped * 1000) / 1000);
    }

    function section(id, title, body) {
        if (!body) return "";
        const open = openSections[id] !== false;
        return `<details class="abe-prop-section" data-abe-prop-section="${esc(id)}"${open ? " open" : ""}>
            <summary>${esc(__(title))}</summary>
            <div class="abe-prop-section-body">${body}</div>
        </details>`;
    }

    function doorSection(storeView, drawing, enabled) {
        const target = (storeView && storeView.drawingTarget) || {};
        const name = target.label ? `<strong class="abe-drawing-name">${esc(target.label)}</strong>` : "";
        const size = target.widthCm != null && target.lengthCm != null
            ? `<span class="abe-drawing-size" dir="ltr">${esc(target.widthCm)} × ${esc(target.lengthCm)} cm</span>`
            : "";
        const dirty = drawing.dirty
            ? `<span class="abe-drawing-dirty">${esc(__("Unsaved drawing"))}</span>`
            : (drawing.persisted ? `<span class="abe-drawing-saved">${esc(__("Saved drawing"))}</span>` : "");
        const message = __(drawing.messageKey || target.messageKey || "Select a special piece to start drawing.");
        const idle = !drawing.pathForm && !drawing.shapeForm && !drawing.referenceForm && !drawing.textForm && drawing.tool !== "shapes" && drawing.tool !== "pen" && drawing.tool !== "node_edit" && drawing.tool !== "text";
        const help = idle
            ? `<p class="abe-drawing-note">${esc(__("Draw on the door. Length and angle stay beside the segment."))}</p>`
            : "";
        return `<section class="abe-prop-door" data-abe-prop-door="1">
            <p class="abe-drawing-status">${name}${size}${dirty}</p>
            <p class="abe-prop-message">${esc(message)}</p>
            ${help}
        </section>`;
    }

    function cutProblemHtml(drawing) {
        const problem = drawing && drawing.cutProblem;
        if (!problem || !problem.messageKey) return "";
        const size = problem.widthCm != null && problem.lengthCm != null
            ? __("Door {0}. Size {1} × {2} cm. {3}")
                .replace("{0}", String(problem.label || ""))
                .replace("{1}", String(problem.widthCm))
                .replace("{2}", String(problem.lengthCm))
                .replace("{3}", __(problem.messageKey))
            : __(problem.messageKey);
        return `<div class="abe-cut-problem" data-abe-cut-problem="1" role="alert">
            <strong>${esc(__("Invalid cut outline"))}</strong>
            <span>${esc(size)}</span>
            ${propButton("Select the problem path", `data-abe-drawing-action="select-problem"`)}
            ${propButton("Clear cut outline", `data-abe-drawing-action="clear-problem"`, "danger")}
        </div>`;
    }

    function measureFieldsHtml(measure) {
        const source = measure || {};
        const enabled = source.enabled === true;
        const lengthValue = source.lengthLocked
            ? String(source.lengthText == null ? "" : source.lengthText)
            : formatMeasureMm(source.lengthMm);
        const angleValue = source.angleLocked
            ? String(source.angleText == null ? "" : source.angleText)
            : formatMeasureAngle(source.angleDeg);
        const disabled = enabled ? "" : " disabled";
        const lengthLocked = source.lengthLocked ? ` data-locked="1"` : "";
        const angleLocked = source.angleLocked ? ` data-locked="1"` : "";
        const lengthInvalid = source.errorField === "length" ? ` aria-invalid="true"` : "";
        const angleInvalid = source.errorField === "angle" ? ` aria-invalid="true"` : "";
        const error = source.errorKey
            ? `<p class="abe-drawing-measure-error" data-abe-drawing-measure-error="1" role="alert">${esc(__(source.errorKey))}</p>`
            : "";
        return `<div class="abe-drawing-measure abe-prop-grid" data-abe-drawing-measure="1" data-abe-measure-mode="${esc(source.mode || "edit")}" dir="${esc(pageDirection())}">
            <label class="abe-metric"><span>${esc(__("Length (mm)"))}</span><input type="text" inputmode="decimal" dir="ltr" autocomplete="off" spellcheck="false" data-abe-drawing-length="1" value="${esc(lengthValue)}"${disabled}${lengthLocked}${lengthInvalid} aria-label="${esc(__("Length (mm)"))}" /></label>
            <label class="abe-metric"><span>${esc(__("Angle (°)"))}</span><input type="text" inputmode="decimal" dir="ltr" autocomplete="off" spellcheck="false" data-abe-drawing-angle="1" value="${esc(angleValue)}"${disabled}${angleLocked}${angleInvalid} aria-label="${esc(__("Angle (°)"))}" /></label>
            ${error}
            ${source.hintKey ? `<p class="abe-drawing-closed">${esc(__(source.hintKey))}</p>` : ""}
        </div>`;
    }

    function segmentSection(drawing, enabled) {
        if (!enabled || !drawing || drawing.tool === "polyline") return "";
        const measure = drawing.measure;
        if (!measure || (measure.mode !== "edit" && measure.mode !== "closed")) return "";
        if (measure.mode === "closed") {
            return `<p class="abe-drawing-closed" data-abe-drawing-closed="1">${esc(__(measure.messageKey || "Closed paths cannot be resized one segment at a time."))}</p>`;
        }
        return measureFieldsHtml(measure);
    }

    function polylineActions(drawing, enabled) {
        if (!enabled || !drawing || drawing.tool !== "polyline") return "";
        return `<div class="abe-prop-actions">
            ${propButton("Finish path", `data-abe-drawing-action="finish"${drawing.canFinish ? "" : " disabled"}`, "primary")}
            ${propButton("Close path", `data-abe-drawing-action="close"${drawing.canClose ? "" : " disabled"}`)}
            ${propButton("Cancel path", `data-abe-drawing-action="cancel"${drawing.canCancel ? "" : " disabled"}`, "danger")}
        </div>`;
    }

    function pathFormHtml(drawing) {
        const form = drawing && drawing.pathForm;
        if (!form) return "";
        const role = form.role || "construction";
        const current = { construction: "role-construction", annotation: "role-annotation", manufacturing_outer: "role-manufacturing" }[role];
        const valid = role === "manufacturing_outer" && !(drawing.cutProblem && drawing.cutProblem.messageKey);
        const button = (value, label) => {
            const pressed = current === value;
            const classes = ["abe-prop-btn", "is-secondary", pressed ? "is-active" : "", value === "role-manufacturing" && valid ? "is-valid-cut" : ""].filter(Boolean).join(" ");
            return `<button type="button" class="${classes}" data-abe-drawing-action="${value}"${pressed ? ' aria-pressed="true"' : ""}>${esc(__(label))}</button>`;
        };
        const clear = role === "manufacturing_outer"
            ? propButton("Clear cut outline", `data-abe-drawing-action="role-clear"`, "danger")
            : "";
        const validate = role === "manufacturing_outer"
            ? propButton("Validate cut outline", `data-abe-drawing-action="validate-path"`, "primary")
            : "";
        return `<div class="abe-path-form" data-abe-path-form="1">
            <span class="abe-prop-label">${esc(__("Path purpose"))}</span>
            <div class="abe-prop-actions">
                ${button("role-construction", "Guide line")}
                ${button("role-annotation", "Note")}
                ${button("role-manufacturing", "Cut outline")}
                ${clear}
                ${validate}
            </div>
            <div class="abe-prop-grid">
                <label class="abe-metric"><span>${esc(__("Move X (mm)"))}</span><input data-abe-path-dx="1" inputmode="decimal" dir="ltr" value="0" aria-label="${esc(__("Move X (mm)"))}"></label>
                <label class="abe-metric"><span>${esc(__("Move Y (mm)"))}</span><input data-abe-path-dy="1" inputmode="decimal" dir="ltr" value="0" aria-label="${esc(__("Move Y (mm)"))}"></label>
            </div>
            ${propButton("Move path", `data-abe-drawing-action="move-path"`, "primary")}
        </div>`;
    }

    function shapeMenuHtml(drawing) {
        if (!drawing || drawing.tool !== "shapes") return "";
        const Space = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        const tools = Space && Space.shapeTools ? Space.shapeTools() : [];
        return `<div class="abe-shape-menu" role="group" aria-label="${esc(__("Shapes"))}">${tools.map((tool) => {
            const active = drawing.shapeKind === tool.id;
            const label = __(tool.labelKey);
            return `<button type="button" class="abe-prop-btn abe-shape-kind${active ? " is-active" : ""}" data-abe-shape-kind="${esc(tool.id)}" aria-pressed="${active ? "true" : "false"}" aria-label="${esc(label)}" title="${esc(label)}">${shapeGlyph(tool.id)}</button>`;
        }).join("")}</div>`;
    }

    function shapeFormHtml(drawing) {
        const form = drawing && drawing.shapeForm;
        const actions = form && form.actions || {};
        const hasActions = actions.convert || actions.copy || actions.paste || actions.remove || actions.insert;
        if (!form || ((!form.fields || !form.fields.length) && !form.transform && !hasActions)) return "";
        const corners = [
            ["top_left", "Top left"],
            ["top_right", "Top right"],
            ["bottom_left", "Bottom left"],
            ["bottom_right", "Bottom right"],
        ];
        const fields = (form.fields || []).map((field) => {
            if (field.key === "corner") {
                const options = corners.map(([value, label]) => (
                    `<option value="${esc(value)}"${String(field.value) === value ? " selected" : ""}>${esc(__(label))}</option>`
                )).join("");
                return `<label class="abe-metric"><span>${esc(__(field.labelKey))}</span><select data-abe-shape-field="${esc(field.key)}" aria-label="${esc(__(field.labelKey))}">${options}</select></label>`;
            }
            return `<label class="abe-metric"><span>${esc(__(field.labelKey))}</span><input type="text" inputmode="decimal" dir="ltr" autocomplete="off" spellcheck="false" data-abe-shape-field="${esc(field.key)}" value="${esc(field.value == null ? "" : field.value)}" aria-label="${esc(__(field.labelKey))}" /></label>`;
        }).join("");
        const error = form.errorKey
            ? `<p class="abe-drawing-measure-error" data-abe-shape-error="1" role="alert">${esc(__(form.errorKey))}</p>`
            : "";
        const buttons = [
            actions.convert ? propButton("Convert to path", `data-abe-drawing-action="convert" title="${esc(__("Convert the shape into independent nodes and segments so its geometry can be edited."))}"`, "primary") : "",
            actions.copy ? propButton("Copy", `data-abe-drawing-action="copy"`) : "",
            actions.paste ? propButton("Paste", `data-abe-drawing-action="paste"`) : "",
            actions.insert ? propButton("Add node", `data-abe-drawing-action="insert-node"`) : "",
            actions.remove ? propButton("Delete", `data-abe-drawing-action="remove"`, "danger") : "",
        ].join("");
        const actionRow = buttons ? `<div class="abe-prop-actions">${buttons}</div>` : "";
        const transform = form.transform;
        const metric = (key, label, value) => `<label class="abe-metric"><span>${esc(__(label))}</span><input type="text" inputmode="decimal" dir="ltr" autocomplete="off" spellcheck="false" data-abe-transform-field="${esc(key)}" value="${esc(key === "rotation" ? formatMeasureAngle(value) : formatMeasureMm(value))}" aria-label="${esc(__(label))}"${transform && transform.rotatable === false && key === "rotation" ? " disabled" : ""} /></label>`;
        const transformGrid = transform
            ? `<div class="abe-prop-grid" data-abe-transform-form="1">
                ${metric("x", "X (mm)", transform.x)}
                ${metric("y", "Y (mm)", transform.y)}
                ${metric("width", "Width (mm)", transform.width)}
                ${metric("height", "Height (mm)", transform.height)}
                ${metric("rotation", "Rotation (°)", transform.rotation)}
                <label class="abe-metric"><span>${esc(__("Lock aspect ratio"))}</span><input type="checkbox" data-abe-transform-aspect="1"${transform.aspectLocked || transform.uniform ? " checked" : ""}${transform.uniform ? " disabled" : ""} aria-label="${esc(__("Lock aspect ratio"))}" /></label>
            </div>`
            : "";
        const grid = fields ? `<div class="abe-prop-grid">${fields}</div>` : "";
        return `<div class="abe-shape-form" data-abe-shape-form="1" data-abe-shape-mode="${esc(form.mode || "create")}" dir="${esc(pageDirection())}">${transformGrid}${grid}${error}${actionRow}</div>`;
    }

    function penSettingsHtml(drawing, enabled) {
        if (!enabled || !drawing || drawing.tool !== "pen") return "";
        const Space = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        const levels = Space && Space.penTools ? Space.penTools() : [];
        const current = drawing.pen && drawing.pen.smoothing ? drawing.pen.smoothing : "low";
        const closeDisabled = drawing.pen && drawing.pen.canClose ? "" : " disabled";
        return `<div class="abe-pen-settings" data-abe-pen-settings="1" dir="${esc(pageDirection())}">
            <span class="abe-prop-label">${esc(__("Smoothing"))}</span>
            <div class="abe-prop-actions" role="group" aria-label="${esc(__("Smoothing"))}">${levels.map((level) => {
                const active = current === level.id;
                const label = __(level.labelKey);
                return `<button type="button" class="abe-prop-btn is-secondary abe-pen-level${active ? " is-active" : ""}" data-abe-pen-smoothing="${esc(level.id)}" aria-pressed="${active ? "true" : "false"}">${esc(label)}</button>`;
            }).join("")}</div>
            ${propButton("Close path", `data-abe-drawing-action="close-pen"${closeDisabled}`)}
        </div>`;
    }

    function snapMenuHtml(drawing, enabled) {
        if (!enabled || !drawing || drawing.snapMenuOpen !== true) return "";
        const settings = drawing.snapSettings || {};
        const box = (key, label) => {
            const checked = key === "grid" ? settings.grid === true : settings[key] !== false;
            return `<label><input type="checkbox" data-abe-snap-option="${esc(key)}"${checked ? " checked" : ""} />${esc(__(label))}</label>`;
        };
        const spacing = [1, 5, 10, 25, 50].indexOf(Number(settings.spacing)) >= 0 ? Number(settings.spacing) : 10;
        const options = [1, 5, 10, 25, 50].map((step) => (
            `<option value="${step}"${step === spacing ? " selected" : ""}>${step} mm</option>`
        )).join("");
        return `<div class="abe-snap-menu" data-abe-snap-menu="1" dir="${esc(pageDirection())}">
            ${box("enabled", "Smart Snap")}
            ${box("endpoint", "Endpoint")}
            ${box("midpoint", "Midpoint")}
            ${box("intersection", "Intersection")}
            ${box("alignment", "Horizontal / Vertical")}
            ${box("grid", "Grid")}
            <label class="abe-metric abe-metric-wide"><span>${esc(__("Grid spacing"))}</span><select data-abe-snap-spacing="1" aria-label="${esc(__("Grid spacing"))}">${options}</select></label>
        </div>`;
    }

    function referenceMenuHtml(drawing, enabled) {
        if (!enabled || !drawing) return "";
        const references = drawing.references || [];
        if (drawing.referenceMenuOpen !== true && !references.length) return "";
        const cards = references.map((reference, index) => {
            const label = `${__("Reference image")} ${index + 1}`;
            const thumb = reference.href
                ? `<img alt="" src="${esc(reference.href)}" />`
                : frappeIcon("image");
            return `<button type="button" class="abe-prop-btn abe-reference-pick${reference.selected ? " is-active" : ""}" data-abe-reference-select="${esc(reference.id)}" aria-pressed="${reference.selected ? "true" : "false"}" aria-label="${esc(label)}" title="${esc(label)}">${thumb}<span>${esc(label)}</span></button>`;
        }).join("");
        const selected = references.find((reference) => reference.selected);
        const actions = selected
            ? `<div class="abe-prop-actions" data-abe-reference-actions="1">
                ${iconAction(selected.hidden ? "eye" : "eye-off", selected.hidden ? "Show reference image" : "Hide reference image", `data-abe-reference-action="hide" data-abe-reference-id="${esc(selected.id)}"`)}
                ${iconAction(selected.locked ? "lock-open" : "lock", selected.locked ? "Unlock reference image" : "Lock reference image", `data-abe-reference-action="lock" data-abe-reference-id="${esc(selected.id)}"`)}
                ${iconAction("crosshair", "Calibrate", `data-abe-reference-action="calibrate" data-abe-reference-id="${esc(selected.id)}"`)}
                ${iconAction("trash-2", "Delete reference image", `data-abe-reference-action="delete" data-abe-reference-id="${esc(selected.id)}"`, false, "danger")}
            </div>`
            : "";
        const empty = references.length
            ? ""
            : `<p class="abe-drawing-note">${esc(__("Upload reference image"))}</p>`;
        return `<div class="abe-reference-menu" data-abe-reference-menu="1" dir="${esc(pageDirection())}">
            <div class="abe-reference-head">
                <span>${esc(__("Reference image"))}</span>
                ${iconAction("upload", "Upload reference image", `data-abe-reference-upload="1"`)}
                <input type="file" accept="image/*,.svg,.heic" data-abe-reference-file="1" hidden />
            </div>
            <div class="abe-reference-list">${cards}</div>
            ${empty}
            ${actions}
        </div>`;
    }

    function referenceFormHtml(drawing) {
        const form = drawing && drawing.referenceForm;
        if (!form) return "";
        const field = (key, label, value) => `<label class="abe-metric"><span>${esc(__(label))}</span><input type="text" inputmode="decimal" dir="ltr" autocomplete="off" spellcheck="false" data-abe-reference-field="${esc(key)}" value="${esc(value)}" aria-label="${esc(__(label))}" /></label>`;
        const percent = Math.round(Number(form.opacity) * 1000) / 10;
        const calibration = form.calibration
            ? `<p class="abe-reference-note" data-abe-reference-calibration="1">${esc(__("Calibrated"))}: <span dir="ltr">${esc(form.calibration.known_distance_mm)} mm</span></p>`
            : (form.calibrating
                ? `<div class="abe-reference-note">
                    <p>${esc(__(form.calibrationMessage || "Pick the first point on the image."))}${form.currentDistance != null ? ` <span dir="ltr">${esc(form.currentDistance)} mm</span>` : ""}</p>
                    <label class="abe-metric"><span>${esc(__("Known distance (mm)"))}</span><input type="text" inputmode="decimal" dir="ltr" data-abe-reference-known="1" value="${esc(form.knownText || "")}" aria-label="${esc(__("Known distance (mm)"))}" /></label>
                    ${iconAction("crosshair", "Apply calibration", `data-abe-reference-action="apply-calibration"`)}
                </div>`
                : "");
        return `<div class="abe-reference-form" data-abe-reference-form="1" dir="${esc(pageDirection())}">
            <div class="abe-prop-grid">
                ${field("x_mm", "Drawing X (mm)", form.x_mm)}
                ${field("y_mm", "Drawing Y (mm)", form.y_mm)}
                ${field("width_mm", "Width (mm)", form.width_mm)}
                ${field("height_mm", "Height (mm)", form.height_mm)}
                ${field("rotation_deg", "Angle (°)", form.rotation_deg)}
                <label class="abe-metric"><span>${esc(__("Lock aspect ratio"))}</span><input type="checkbox" data-abe-reference-aspect="1"${form.aspectLocked !== false ? " checked" : ""} aria-label="${esc(__("Lock aspect ratio"))}" /></label>
            </div>
            <label class="abe-opacity"><span>${esc(__("Opacity (%)"))}</span><input type="range" min="0" max="100" step="1" dir="ltr" data-abe-reference-opacity="1" value="${esc(percent)}" aria-label="${esc(__("Opacity (%)"))}" /><output dir="ltr">${esc(percent)}%</output></label>
            ${calibration}
        </div>`;
    }

    function signature(storeView) {
        const drawing = (storeView && storeView.drawingView) || {};
        const target = (storeView && storeView.drawingTarget) || {};
        return JSON.stringify({
            tool: drawing.tool || "",
            kind: drawing.shapeKind || "",
            dirty: drawing.dirty === true,
            persisted: drawing.persisted === true,
            message: drawing.messageKey || target.messageKey || "",
            label: target.label || "",
            size: [target.widthCm, target.lengthCm],
            path: drawing.pathForm || null,
            shape: drawing.shapeForm
                ? Object.assign({}, drawing.shapeForm, {
                    transform: drawing.resizing ? "live" : (drawing.shapeForm.transform || null),
                })
                : null,
            pen: drawing.pen || null,
            snap: drawing.snapMenuOpen === true ? drawing.snapSettings || {} : false,
            referenceMenu: drawing.referenceMenuOpen === true,
            referenceForm: drawing.referenceForm || null,
            textForm: drawing.textLive && drawing.textForm
                ? Object.assign({}, drawing.textForm, { text: "", widthMm: null, heightMm: null })
                : (drawing.textForm || null),
            references: (drawing.references || []).map((row) => [row.id, row.selected, row.hidden, row.locked, Boolean(row.href)]),
            measure: drawing.tool === "polyline" ? null : drawing.measure || null,
            problem: drawing.cutProblem || null,
            finish: [drawing.canFinish, drawing.canClose, drawing.canCancel],
            open: openSections,
        });
    }

    function focusedField(root) {
        const active = root && root.ownerDocument ? root.ownerDocument.activeElement : null;
        if (!active || !root.contains || !root.contains(active)) return null;
        const attr = ["data-abe-text-field", "data-abe-shape-field", "data-abe-transform-field", "data-abe-reference-field", "data-abe-path-dx", "data-abe-path-dy", "data-abe-reference-known", "data-abe-drawing-length", "data-abe-drawing-angle"].find((name) => active.hasAttribute && active.hasAttribute(name));
        if (!attr) return null;
        return {
            attr,
            value: active.getAttribute(attr),
            text: active.value,
            start: active.selectionStart,
            end: active.selectionEnd,
        };
    }

    function restoreField(root, remembered) {
        if (!remembered) return;
        const selector = remembered.value
            ? `[${remembered.attr}="${remembered.value}"]`
            : `[${remembered.attr}]`;
        const input = root.querySelector(selector);
        if (!input) return;
        if (remembered.text != null && input.value !== remembered.text) input.value = remembered.text;
        if (typeof input.focus === "function") input.focus();
        if (typeof input.setSelectionRange === "function" && remembered.start != null) {
            try { input.setSelectionRange(remembered.start, remembered.end); } catch (error) { /* number inputs */ }
        }
    }

    function bind(root, handlers) {
        if (!root || typeof root.querySelectorAll !== "function") return;
        const stop = (event) => event.stopPropagation();
        root.querySelectorAll("[data-abe-prop-section]").forEach((details) => {
            details.addEventListener("toggle", () => {
                openSections[details.getAttribute("data-abe-prop-section")] = details.open !== false;
            });
        });
        const collapse = root.querySelector("[data-abe-draw-props-toggle]");
        if (collapse) {
            collapse.addEventListener("click", (event) => {
                event.stopPropagation();
                if (handlers && handlers.toggleDrawingProperties) handlers.toggleDrawingProperties();
            });
        }
        root.querySelectorAll("[data-abe-drawing-action]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.stopPropagation();
                if (button.disabled) return;
                if (handlers && handlers.drawingAction) handlers.drawingAction(button.getAttribute("data-abe-drawing-action"));
            });
        });
        root.querySelectorAll("[data-abe-shape-kind]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.stopPropagation();
                if (handlers && handlers.setShapeKind) handlers.setShapeKind(button.getAttribute("data-abe-shape-kind"));
            });
        });
        root.querySelectorAll("[data-abe-shape-form], [data-abe-path-form], [data-abe-pen-settings], [data-abe-snap-menu], [data-abe-reference-menu], [data-abe-reference-form], [data-abe-text-form]").forEach((panel) => {
            panel.addEventListener("pointerdown", stop);
            panel.addEventListener("click", stop);
        });
        root.querySelectorAll("[data-abe-transform-aspect]").forEach((input) => {
            input.addEventListener("change", (event) => {
                event.stopPropagation();
                if (handlers && handlers.setTransformAspect) handlers.setTransformAspect(input.checked === true);
            });
        });
        root.querySelectorAll("[data-abe-transform-field]").forEach((input) => {
            input.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" && event.code !== "Enter" && event.code !== "NumpadEnter") return;
                event.preventDefault();
                event.stopPropagation();
                if (handlers && handlers.commitTransformField) handlers.commitTransformField(input.getAttribute("data-abe-transform-field"), input.value);
            });
            input.addEventListener("change", (event) => {
                event.stopPropagation();
                if (handlers && handlers.commitTransformField) handlers.commitTransformField(input.getAttribute("data-abe-transform-field"), input.value);
            });
        });
        root.querySelectorAll("[data-abe-shape-form] [data-abe-shape-field]").forEach((input) => {
            input.addEventListener("input", () => {
                if (handlers && handlers.onShapeInput) handlers.onShapeInput(input.getAttribute("data-abe-shape-field"), input.value);
            });
            input.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" && event.code !== "Enter" && event.code !== "NumpadEnter" && (event.keyCode || event.which) !== 13) return;
                event.preventDefault();
                event.stopPropagation();
                if (handlers && handlers.commitShapeForm) handlers.commitShapeForm(input.getAttribute("data-abe-shape-field"));
            });
        });
        root.querySelectorAll("[data-abe-pen-smoothing]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.stopPropagation();
                if (handlers && handlers.setPenSmoothing) handlers.setPenSmoothing(button.getAttribute("data-abe-pen-smoothing"));
            });
        });
        root.querySelectorAll("[data-abe-snap-option]").forEach((input) => {
            input.addEventListener("change", (event) => {
                event.stopPropagation();
                if (handlers && handlers.setSnapOption) handlers.setSnapOption(input.getAttribute("data-abe-snap-option"), input.checked === true);
            });
        });
        root.querySelectorAll("[data-abe-snap-spacing]").forEach((select) => {
            select.addEventListener("change", (event) => {
                event.stopPropagation();
                if (handlers && handlers.setSnapOption) handlers.setSnapOption("spacing", select.value);
            });
        });
        root.querySelectorAll("[data-abe-reference-upload]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.stopPropagation();
                if (handlers && handlers.openReferencePicker) {
                    handlers.openReferencePicker();
                    return;
                }
                const input = root.querySelector("[data-abe-reference-file]");
                if (input && input.click) input.click();
            });
        });
        root.querySelectorAll("[data-abe-reference-file]").forEach((input) => {
            input.addEventListener("change", () => {
                const files = input.files ? Array.prototype.slice.call(input.files) : [];
                if (handlers && handlers.uploadReferenceFiles && files.length) handlers.uploadReferenceFiles(files);
                input.value = "";
            });
        });
        root.querySelectorAll("[data-abe-reference-select]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.stopPropagation();
                if (handlers && handlers.selectReference) handlers.selectReference(button.getAttribute("data-abe-reference-select"));
            });
        });
        root.querySelectorAll("[data-abe-reference-action]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.stopPropagation();
                if (handlers && handlers.referenceAction) handlers.referenceAction(button.getAttribute("data-abe-reference-action"), button.getAttribute("data-abe-reference-id"));
            });
        });
        root.querySelectorAll("[data-abe-reference-field], [data-abe-reference-opacity], [data-abe-reference-known]").forEach((input) => {
            input.addEventListener("change", (event) => {
                event.stopPropagation();
                if (handlers && handlers.commitReferenceField) {
                    handlers.commitReferenceField(input.getAttribute("data-abe-reference-field") || (input.hasAttribute("data-abe-reference-opacity") ? "opacity" : "known"), input.value);
                }
            });
        });
        root.querySelectorAll("[data-abe-reference-aspect]").forEach((input) => {
            input.addEventListener("change", (event) => {
                event.stopPropagation();
                if (handlers && handlers.setReferenceAspect) handlers.setReferenceAspect(input.checked === true);
            });
        });
        root.querySelectorAll("[data-abe-text-form] [data-abe-text-field]").forEach((input) => {
            let composing = false;
            const commit = () => {
                if (handlers && handlers.commitTextField) {
                    handlers.commitTextField(input.getAttribute("data-abe-text-field"), input.type === "checkbox" ? input.checked : input.value);
                }
            };
            input.addEventListener("compositionstart", () => { composing = true; });
            input.addEventListener("compositionend", () => {
                composing = false;
                if (input.getAttribute("data-abe-text-field") === "text" && handlers && handlers.onTextInput) {
                    handlers.onTextInput(input.value);
                }
            });
            input.addEventListener("input", (event) => {
                event.stopPropagation();
                if (input.getAttribute("data-abe-text-field") !== "text" || composing) return;
                if (handlers && handlers.onTextInput) handlers.onTextInput(input.value);
            });
            input.addEventListener("change", (event) => {
                event.stopPropagation();
                if (input.getAttribute("data-abe-text-field") === "text") return;
                commit();
            });
            input.addEventListener("blur", () => {
                if (input.getAttribute("data-abe-text-field") === "text" && handlers && handlers.onTextBlur) handlers.onTextBlur();
            });
            input.addEventListener("keydown", (event) => {
                if (input.getAttribute("data-abe-text-field") === "text") return;
                if (event.key !== "Enter" && event.code !== "Enter" && event.code !== "NumpadEnter") return;
                event.preventDefault();
                event.stopPropagation();
                commit();
            });
        });
        const renderer = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.CanvasRenderer;
        if (renderer && typeof renderer.bindDrawingMeasure === "function") renderer.bindDrawingMeasure(root, handlers);
    }

    function textField(name, label, value, kind) {
        const wide = kind === "area" ? " abe-metric-wide" : "";
        const control = kind === "area"
            ? `<textarea data-abe-text-field="${esc(name)}" rows="3" dir="auto" aria-label="${esc(__(label))}">${esc(value)}</textarea>`
            : `<input type="text" inputmode="decimal" dir="ltr" autocomplete="off" spellcheck="false" data-abe-text-field="${esc(name)}" value="${esc(value)}" aria-label="${esc(__(label))}" />`;
        return `<label class="abe-metric${wide}"><span>${esc(__(label))}</span>${control}</label>`;
    }

    function textChoice(name, label, value, options) {
        const choices = options.map((option) => `<option value="${esc(option[0])}"${option[0] === value ? " selected" : ""}>${esc(__(option[1]))}</option>`).join("");
        return `<label class="abe-metric"><span>${esc(__(label))}</span><select data-abe-text-field="${esc(name)}" aria-label="${esc(__(label))}">${choices}</select></label>`;
    }

    function textSection(drawing) {
        const form = drawing && drawing.textForm;
        if (!form) return "";
        const vector = form.state === "vector";
        const actions = vector
            ? propButton(form.exportApproved ? "Clear text export approval" : "Approve text for export", `data-abe-drawing-action="approve-text"`, "primary")
            : propButton("Convert Text to Path", `data-abe-drawing-action="convert-text"`, "primary");
        return `<div data-abe-text-form="1" class="abe-prop-grid">
            ${textField("text", "Text", form.text, "area")}
            <label class="abe-metric abe-metric-wide"><span>${esc(__("Font Family"))}</span><select data-abe-text-field="font_id" aria-label="${esc(__("Font Family"))}"><option value="noto-naskh-arabic" selected>Noto Naskh Arabic</option></select></label>
            ${textField("font_size_mm", "Font Size (mm)", formatMeasureMm(form.fontSizeMm))}
            ${textChoice("font_weight", "Font Weight", form.fontWeight, [["regular", "Regular"], ["bold", "Bold"]])}
            ${textChoice("direction", "Text direction", form.direction, [["auto", "Auto"], ["rtl", "RTL"], ["ltr", "LTR"]])}
            ${textChoice("align", "Alignment", form.align, [["left", "Left"], ["center", "Center"], ["right", "Right"]])}
            ${textField("x_mm", "X (mm)", formatMeasureMm(form.xMm))}
            ${textField("y_mm", "Y (mm)", formatMeasureMm(form.yMm))}
            ${textField("width_mm", "Width (mm)", formatMeasureMm(form.widthMm))}
            ${textField("height_mm", "Height (mm)", formatMeasureMm(form.heightMm))}
            ${textField("rotation_deg", "Rotation (°)", formatMeasureAngle(form.rotationDeg))}
            <label class="abe-metric"><span>${esc(__("Lock aspect ratio"))}</span><input type="checkbox" data-abe-text-field="aspect_locked"${form.aspectLocked ? " checked" : ""} aria-label="${esc(__("Lock aspect ratio"))}" /></label>
            <p class="abe-drawing-note">${esc(vector ? __("Vector text outlines") : __("Editable text"))}</p>
            <div class="abe-prop-actions">${actions}
                ${propButton("Duplicate", `data-abe-drawing-action="duplicate"`)}
                ${propButton("Delete", `data-abe-drawing-action="remove"`, "danger")}
            </div>
        </div>`;
    }

    function html(storeView, collapsed) {
        const drawing = (storeView && storeView.drawingView) || {};
        const target = (storeView && storeView.drawingTarget) || {};
        const enabled = target.status === "special" && target.canEdit === true && drawing.ready !== false;
        const toggleLabel = collapsed ? __("Expand drawing properties") : __("Collapse drawing properties");
        if (collapsed) {
            return `<aside class="abe-draw-props is-collapsed" data-abe-draw-props="1" dir="${esc(pageDirection())}">
                <button type="button" class="alm-btn-secondary abe-tool-btn abe-draw-props-toggle" data-abe-draw-props-toggle="1" title="${esc(toggleLabel)}" aria-label="${esc(toggleLabel)}" aria-expanded="false">${frappeIcon("panel-right")}</button>
            </aside>`;
        }
        const formMode = drawing.shapeForm && drawing.shapeForm.mode;
        const shapeBody = formMode === "node" || formMode === "path"
            ? shapeMenuHtml(drawing)
            : `${shapeMenuHtml(drawing)}${shapeFormHtml(drawing)}`;
        const body = [
            doorSection(storeView, drawing, enabled),
            cutProblemHtml(drawing),
            section("segment", "Segment", segmentSection(drawing, enabled)),
            section("path", "Path", `${pathFormHtml(drawing)}${formMode === "path" ? shapeFormHtml(drawing) : ""}${drawing.tool === "polyline" ? polylineActions(drawing, enabled) : ""}`),
            section("shapes", "Shapes", shapeBody),
            section("node", "Node", formMode === "node" ? shapeFormHtml(drawing) : ""),
            section("pen", "Pen", penSettingsHtml(drawing, enabled)),
            section("snap", "Snap", snapMenuHtml(drawing, enabled)),
            section("reference", "Reference image", `${referenceMenuHtml(drawing, enabled)}${referenceFormHtml(drawing)}`),
            section("text", "Text", textSection(drawing)),
        ].join("");
        return `<aside class="abe-draw-props" data-abe-draw-props="1" dir="${esc(pageDirection())}">
            <header class="abe-prop-head">
                <h2>${esc(__("Drawing properties"))}</h2>
                <button type="button" class="alm-btn-secondary abe-tool-btn abe-draw-props-toggle" data-abe-draw-props-toggle="1" title="${esc(toggleLabel)}" aria-label="${esc(toggleLabel)}" aria-expanded="true">${frappeIcon("panel-right-close")}</button>
            </header>
            <div class="abe-draw-props-scroll">${body}</div>
        </aside>`;
    }

    function render(host, storeView, handlers, collapsed) {
        if (!host) return;
        const next = signature(storeView) + (collapsed ? ":collapsed" : "");
        if (next === lastSignature && host.querySelector("[data-abe-draw-props]")) return;
        const scroll = host.querySelector(".abe-draw-props-scroll");
        const scrollTop = scroll ? scroll.scrollTop : 0;
        const focus = focusedField(host);
        lastSignature = next;
        host.innerHTML = html(storeView, collapsed === true);
        const nextScroll = host.querySelector(".abe-draw-props-scroll");
        if (nextScroll) nextScroll.scrollTop = scrollTop;
        bind(host, handlers);
        restoreField(host, focus);
    }

    function reset() {
        lastSignature = "";
    }

    function patchTransform(host, transform) {
        if (!host || !transform) return;
        host.querySelectorAll("[data-abe-transform-field]").forEach((input) => {
            if (input === host.ownerDocument.activeElement) return;
            const key = input.getAttribute("data-abe-transform-field");
            const text = key === "rotation" ? formatMeasureAngle(transform[key]) : formatMeasureMm(transform[key]);
            if (text !== "" && input.value !== text) input.value = text;
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingProperties = Object.freeze({
        render,
        reset,
        html,
        patchTransform,
    });
})();
