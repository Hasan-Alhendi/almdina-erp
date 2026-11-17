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

    function iconAction(iconName, label, attrs, alreadyTranslated) {
        const translated = alreadyTranslated ? label : __(label);
        return `<button type="button" class="alm-btn-secondary abe-tool-btn" ${attrs || ""} title="${esc(translated)}" aria-label="${esc(translated)}">${frappeIcon(iconName)}</button>`;
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
        const idle = !drawing.pathForm && !drawing.shapeForm && !drawing.referenceForm && drawing.tool !== "shapes" && drawing.tool !== "pen" && drawing.tool !== "node_edit";
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
            <button type="button" data-abe-drawing-action="select-problem">${esc(__("Select the problem path"))}</button>
            <button type="button" data-abe-drawing-action="clear-problem">${esc(__("Clear cut outline"))}</button>
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
        return `<div class="abe-drawing-actions">
            <button type="button" data-abe-drawing-action="finish"${drawing.canFinish ? "" : " disabled"}>${esc(__("Finish path"))}</button>
            <button type="button" data-abe-drawing-action="close"${drawing.canClose ? "" : " disabled"}>${esc(__("Close path"))}</button>
            <button type="button" data-abe-drawing-action="cancel"${drawing.canCancel ? "" : " disabled"}>${esc(__("Cancel path"))}</button>
        </div>`;
    }

    function pathFormHtml(drawing) {
        const form = drawing && drawing.pathForm;
        if (!form) return "";
        const role = form.role || "construction";
        const current = { construction: "role-construction", annotation: "role-annotation", manufacturing_outer: "role-manufacturing" }[role];
        const valid = role === "manufacturing_outer" && !(drawing.cutProblem && drawing.cutProblem.messageKey);
        const button = (value, label) => `<button type="button" class="${value === "role-manufacturing" && valid ? "is-valid-cut" : ""}" data-abe-drawing-action="${value}"${current === value ? ' aria-pressed="true"' : ""}>${esc(__(label))}</button>`;
        const clear = role === "manufacturing_outer"
            ? `<button type="button" data-abe-drawing-action="role-clear">${esc(__("Clear cut outline"))}</button>`
            : "";
        const validate = role === "manufacturing_outer"
            ? `<button type="button" data-abe-drawing-action="validate-path">${esc(__("Validate cut outline"))}</button>`
            : "";
        return `<div class="abe-path-form" data-abe-path-form="1">
            <span class="abe-prop-label">${esc(__("Path purpose"))}</span>
            <div class="abe-drawing-actions">
                ${button("role-construction", "Guide line")}
                ${button("role-annotation", "Note")}
                ${button("role-manufacturing", "Cut outline")}
                ${clear}
                ${validate}
            </div>
            <div class="abe-prop-grid">
                <label class="abe-metric">${esc(__("Move X (mm)"))}<input data-abe-path-dx="1" inputmode="decimal" dir="ltr" value="0"></label>
                <label class="abe-metric">${esc(__("Move Y (mm)"))}<input data-abe-path-dy="1" inputmode="decimal" dir="ltr" value="0"></label>
            </div>
            <button type="button" data-abe-drawing-action="move-path">${esc(__("Move path"))}</button>
        </div>`;
    }

    function shapeMenuHtml(drawing) {
        if (!drawing || drawing.tool !== "shapes") return "";
        const Space = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        const tools = Space && Space.shapeTools ? Space.shapeTools() : [];
        return `<div class="abe-shape-menu" role="group" aria-label="${esc(__("Shapes"))}">${tools.map((tool) => {
            const active = drawing.shapeKind === tool.id;
            return `<button type="button" class="abe-shape-kind${active ? " is-active" : ""}" data-abe-shape-kind="${esc(tool.id)}" aria-pressed="${active ? "true" : "false"}">${esc(__(tool.labelKey))}</button>`;
        }).join("")}</div>`;
    }

    function shapeFormHtml(drawing) {
        const form = drawing && drawing.shapeForm;
        const actions = form && form.actions || {};
        const hasActions = actions.convert || actions.copy || actions.paste || actions.remove || actions.insert;
        if (!form || ((!form.fields || !form.fields.length) && !hasActions)) return "";
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
            actions.convert ? `<button type="button" data-abe-drawing-action="convert" title="${esc(__("Convert the shape into independent nodes and segments so its geometry can be edited."))}">${esc(__("Convert to path"))}</button>` : "",
            actions.copy ? `<button type="button" data-abe-drawing-action="copy">${esc(__("Copy"))}</button>` : "",
            actions.paste ? `<button type="button" data-abe-drawing-action="paste">${esc(__("Paste"))}</button>` : "",
            actions.remove ? `<button type="button" data-abe-drawing-action="remove">${esc(__("Delete"))}</button>` : "",
            actions.insert ? `<button type="button" data-abe-drawing-action="insert-node">${esc(__("Add node"))}</button>` : "",
        ].join("");
        const actionRow = buttons ? `<div class="abe-drawing-actions">${buttons}</div>` : "";
        const grid = fields ? `<div class="abe-prop-grid">${fields}</div>` : "";
        return `<div class="abe-shape-form" data-abe-shape-form="1" data-abe-shape-mode="${esc(form.mode || "create")}" dir="${esc(pageDirection())}">${grid}${error}${actionRow}</div>`;
    }

    function penSettingsHtml(drawing, enabled) {
        if (!enabled || !drawing || drawing.tool !== "pen") return "";
        const Space = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        const levels = Space && Space.penTools ? Space.penTools() : [];
        const current = drawing.pen && drawing.pen.smoothing ? drawing.pen.smoothing : "low";
        const closeDisabled = drawing.pen && drawing.pen.canClose ? "" : " disabled";
        return `<div class="abe-pen-settings" data-abe-pen-settings="1" dir="${esc(pageDirection())}">
            <span class="abe-prop-label">${esc(__("Smoothing"))}</span>
            <div class="abe-drawing-actions" role="group" aria-label="${esc(__("Smoothing"))}">${levels.map((level) => {
                const active = current === level.id;
                return `<button type="button" class="abe-pen-level${active ? " is-active" : ""}" data-abe-pen-smoothing="${esc(level.id)}" aria-pressed="${active ? "true" : "false"}">${esc(__(level.labelKey))}</button>`;
            }).join("")}</div>
            <button type="button" data-abe-drawing-action="close-pen"${closeDisabled}>${esc(__("Close path"))}</button>
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
            <label><span>${esc(__("Grid spacing"))}</span><select data-abe-snap-spacing="1" aria-label="${esc(__("Grid spacing"))}">${options}</select></label>
        </div>`;
    }

    function referenceMenuHtml(drawing, enabled) {
        if (!enabled || !drawing || drawing.referenceMenuOpen !== true) return "";
        const rows = (drawing.references || []).map((reference, index) => {
            const selected = reference.selected ? " is-active" : "";
            const selectLabel = `${__("Reference image")} ${index + 1}`;
            return `<span class="abe-reference-row${selected}">
                ${iconAction("image", selectLabel, `data-abe-reference-select="${esc(reference.id)}"`, true)}
                ${iconAction(reference.hidden ? "eye" : "eye-off", reference.hidden ? "Show reference image" : "Hide reference image", `data-abe-reference-action="hide" data-abe-reference-id="${esc(reference.id)}"`)}
                ${iconAction(reference.locked ? "lock-open" : "lock", reference.locked ? "Unlock reference image" : "Lock reference image", `data-abe-reference-action="lock" data-abe-reference-id="${esc(reference.id)}"`)}
                ${iconAction("trash-2", "Delete reference image", `data-abe-reference-action="delete" data-abe-reference-id="${esc(reference.id)}"`)}
            </span>`;
        }).join("");
        return `<div class="abe-reference-menu" data-abe-reference-menu="1" dir="${esc(pageDirection())}">
            ${iconAction("upload", "Upload reference image", `data-abe-reference-upload="1"`)}
            <input type="file" accept="image/*,.svg,.heic" data-abe-reference-file="1" hidden />
            ${rows}
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
                ? `<p class="abe-reference-note">${esc(__(form.calibrationMessage || "Pick the first point on the image."))}${form.currentDistance != null ? ` <span dir="ltr">${esc(form.currentDistance)} mm</span>` : ""}</p>
                    <label><span>${esc(__("Known distance (mm)"))}</span><input type="text" inputmode="decimal" dir="ltr" data-abe-reference-known="1" value="${esc(form.knownText || "")}" /></label>
                    ${iconAction("crosshair", "Apply calibration", `data-abe-reference-action="apply-calibration"`)}`
                : "");
        return `<div class="abe-reference-form" data-abe-reference-form="1" dir="${esc(pageDirection())}">
            <div class="abe-prop-grid">
                ${field("x_mm", "Drawing X (mm)", form.x_mm)}
                ${field("y_mm", "Drawing Y (mm)", form.y_mm)}
                ${field("width_mm", "Width (mm)", form.width_mm)}
                ${field("height_mm", "Height (mm)", form.height_mm)}
                ${field("rotation_deg", "Angle (°)", form.rotation_deg)}
            </div>
            <label><span>${esc(__("Opacity (%)"))}</span><input type="range" min="0" max="100" step="1" dir="ltr" data-abe-reference-opacity="1" value="${esc(percent)}" aria-label="${esc(__("Opacity (%)"))}" /></label>
            <label><input type="checkbox" data-abe-reference-aspect="1"${form.aspectLocked !== false ? " checked" : ""} />${esc(__("Lock aspect ratio"))}</label>
            ${iconAction("crosshair", "Calibrate", `data-abe-reference-action="calibrate"`)}
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
            shape: drawing.shapeForm || null,
            pen: drawing.pen || null,
            snap: drawing.snapMenuOpen === true ? drawing.snapSettings || {} : false,
            referenceMenu: drawing.referenceMenuOpen === true,
            referenceForm: drawing.referenceForm || null,
            references: (drawing.references || []).map((row) => [row.id, row.selected, row.hidden, row.locked]),
            measure: drawing.tool === "polyline" ? null : drawing.measure || null,
            problem: drawing.cutProblem || null,
            finish: [drawing.canFinish, drawing.canClose, drawing.canCancel],
            open: openSections,
        });
    }

    function focusedField(root) {
        const active = root && root.ownerDocument ? root.ownerDocument.activeElement : null;
        if (!active || !root.contains || !root.contains(active)) return null;
        const attr = ["data-abe-shape-field", "data-abe-reference-field", "data-abe-path-dx", "data-abe-path-dy", "data-abe-reference-known", "data-abe-drawing-length", "data-abe-drawing-angle"].find((name) => active.hasAttribute && active.hasAttribute(name));
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
        root.querySelectorAll("[data-abe-shape-form], [data-abe-path-form], [data-abe-pen-settings], [data-abe-snap-menu], [data-abe-reference-menu], [data-abe-reference-form]").forEach((panel) => {
            panel.addEventListener("pointerdown", stop);
            panel.addEventListener("click", stop);
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
        const renderer = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.CanvasRenderer;
        if (renderer && typeof renderer.bindDrawingMeasure === "function") renderer.bindDrawingMeasure(root, handlers);
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

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingProperties = Object.freeze({
        render,
        reset,
        html,
    });
})();
