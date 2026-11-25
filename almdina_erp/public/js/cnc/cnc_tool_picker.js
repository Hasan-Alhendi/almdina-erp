(() => {
    "use strict";

    if (window.AlmdinaCncToolPicker) return;

    function escapeHtml(value) {
        const labels = window.AlmdinaCncLabels;
        if (labels && typeof labels.escapeHtml === "function") return labels.escapeHtml(value);
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function markup(spec) {
        const options = spec || {};
        const tools = Array.isArray(options.tools) ? options.tools : [];
        const selected = String(options.selected || "");
        const selectedLabel = String(options.selectedLabel || "");
        const emptyLabel = String(options.emptyLabel || "Choose a tool");
        const face = selected ? (selectedLabel || selected) : emptyLabel;
        const changeLabel = String(options.changeLabel || options.label || "Tool");
        const selectName = String(options.selectAttribute || 'data-field="tool_preset"');
        const settingAttribute = String(options.settingAttribute || "data-field");
        const valueAttribute = options.valueAttribute ? ` ${options.valueAttribute}` : "";
        const label = options.showLabel === false
            ? ""
            : `<span class="dco-tool-picker__caption">${escapeHtml(options.label || "Tool")}</span>`;
        const toolOptions = [`<option value="">${escapeHtml(emptyLabel)}</option>`].concat(tools.map(row => {
            const value = String(row.value || "");
            return `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(row.label || value)}</option>`;
        })).join("");
        const notes = (options.readOnly || []).map(row => {
            return `<p class="dco-tool-picker__note" data-artcam-tool-summary>${escapeHtml(row.label)} ${escapeHtml(row.value == null ? "" : row.value)}</p>`;
        }).join("");
        const fields = (options.fields || []).map(row => {
            const name = String(row.name || "");
            return `<label class="dco-tool-picker__setting">${escapeHtml(row.label || name)}
                <input class="form-control" ${settingAttribute}="${escapeHtml(name)}" value="${escapeHtml(row.value == null ? "" : row.value)}">
            </label>`;
        }).join("");
        const settings = selected
            ? `<div class="dco-tool-picker__settings" data-tool-picker-settings>${notes}${fields}</div>`
            : `<div class="dco-tool-picker__settings" data-tool-picker-settings hidden></div>`;
        return `<div class="dco-tool-picker" data-tool-picker>
            ${label}
            <button type="button" class="dco-tool-picker__face" data-tool-picker-toggle aria-expanded="false" aria-haspopup="listbox">
                <span class="dco-tool-picker__value"${valueAttribute}>${escapeHtml(face)}</span>
                <span class="dco-tool-picker__chevron" aria-hidden="true"></span>
            </button>
            <div class="dco-tool-picker__panel" data-tool-picker-panel hidden>
                <label class="dco-tool-picker__change">
                    <span>${escapeHtml(changeLabel)}</span>
                    <select class="form-control" ${selectName} data-tool-picker-select data-empty-label="${escapeHtml(emptyLabel)}">${toolOptions}</select>
                </label>
                ${settings}
            </div>
        </div>`;
    }

    function setOpen(picker, open) {
        if (!picker) return;
        const panel = picker.querySelector("[data-tool-picker-panel]");
        const face = picker.querySelector("[data-tool-picker-toggle]");
        if (panel) panel.hidden = !open;
        if (face) face.setAttribute("aria-expanded", open ? "true" : "false");
    }

    const pickerRoots = new Set();

    function bind(root) {
        if (!root || root.dataset.toolPickerBound === "1") return;
        root.dataset.toolPickerBound = "1";
        pickerRoots.add(root);
        root.addEventListener("click", event => {
            const toggle = event.target && event.target.closest && event.target.closest("[data-tool-picker-toggle]");
            if (!toggle || !root.contains(toggle)) return;
            event.preventDefault();
            const picker = toggle.closest("[data-tool-picker]");
            const panel = picker && picker.querySelector("[data-tool-picker-panel]");
            setOpen(picker, Boolean(panel && panel.hidden));
        });
        root.addEventListener("keydown", event => {
            if (!event || event.key !== "Escape") return;
            root.querySelectorAll("[data-tool-picker]").forEach(picker => setOpen(picker, false));
        });
        const doc = root.ownerDocument || window.document;
        if (doc && typeof doc.addEventListener === "function" && !doc.__almdinaToolPickerOutside) {
            doc.__almdinaToolPickerOutside = true;
            doc.addEventListener("mousedown", event => {
                pickerRoots.forEach(host => {
                    if (host.ownerDocument && host.ownerDocument !== doc) return;
                    host.querySelectorAll("[data-tool-picker]").forEach(picker => {
                        if (!picker.contains(event.target)) setOpen(picker, false);
                    });
                });
            });
        }
    }

    function pickerRoot(container) {
        return container && container.querySelector ? container.querySelector("[data-tool-picker]") : null;
    }

    function controllerFor(container) {
        return {
            isOpen() {
                const panel = container.querySelector("[data-tool-picker-panel]");
                return Boolean(panel && !panel.hidden);
            },
            close() {
                setOpen(pickerRoot(container), false);
            },
            getValues() {
                const select = container.querySelector("[data-tool-picker-select]");
                const fields = {};
                container.querySelectorAll("[data-tool-picker-settings] input").forEach(input => {
                    const name = input.getAttribute("data-field")
                        || input.getAttribute("data-profile-tool")
                        || "";
                    if (name) fields[name] = input.value;
                });
                return { tool: select ? select.value : "", fields };
            },
            setTools(tools, selected, options) {
                const select = container.querySelector("[data-tool-picker-select]");
                if (!select || !select.ownerDocument) return;
                const settings = options || {};
                const emptyLabel = settings.emptyLabel != null
                    ? String(settings.emptyLabel)
                    : (select.getAttribute("data-empty-label") || "");
                if (emptyLabel) select.setAttribute("data-empty-label", emptyLabel);
                const rows = [{ value: "", label: emptyLabel }].concat(Array.isArray(tools) ? tools : []);
                select.innerHTML = "";
                rows.forEach(row => {
                    const option = select.ownerDocument.createElement("option");
                    option.value = String(row.value || "");
                    option.textContent = String(row.label || row.value || "");
                    select.appendChild(option);
                });
                // Document truth wins. Never keep a previous document's select value
                // when the caller provides the selected tool (including empty).
                const nextSelected = selected !== undefined
                    ? String(selected || "")
                    : String(select.value || "");
                select.value = nextSelected;
                const face = container.querySelector(".dco-tool-picker__value");
                if (face) {
                    if (!nextSelected) {
                        face.textContent = emptyLabel;
                    } else if (settings.selectedLabel != null && String(settings.selectedLabel)) {
                        face.textContent = String(settings.selectedLabel);
                    } else {
                        const match = rows.find(row => String(row.value || "") === nextSelected);
                        face.textContent = match ? String(match.label || nextSelected) : nextSelected;
                    }
                }
            },
            clearSelection(emptyLabel) {
                this.setTools(
                    Array.from(container.querySelectorAll("[data-tool-picker-select] option"))
                        .filter(option => option.value)
                        .map(option => ({ value: option.value, label: option.textContent })),
                    "",
                    { emptyLabel: emptyLabel || "" }
                );
                const settings = container.querySelector("[data-tool-picker-settings]");
                if (settings) {
                    settings.innerHTML = "";
                    settings.hidden = true;
                }
                setOpen(pickerRoot(container), false);
            },
            setState(next) {
                const state = next || {};
                const picker = pickerRoot(container);
                const open = state.open === true;
                if (typeof container.innerHTML === "string" && state.markup) {
                    container.innerHTML = state.markup;
                }
                setOpen(pickerRoot(container) || picker, open);
            },
        };
    }

    function mount(container, spec) {
        if (!container) return null;
        // Remounting must drop prior binders so document switches cannot reuse
        // listeners that close over a previous form/dialog.
        if (container.dataset) delete container.dataset.toolPickerBound;
        pickerRoots.delete(container);
        container.innerHTML = markup(spec);
        bind(container);
        const select = container.querySelector("[data-tool-picker-select]");
        if (select && typeof spec.onToolChange === "function") {
            select.addEventListener("change", () => {
                const value = String(select.value || "");
                if (value === String(spec.selected || "")) return;
                spec.selected = value;
                spec.onToolChange(value);
            });
        }
        container.querySelectorAll("[data-tool-picker-settings] input").forEach(input => {
            input.addEventListener("input", () => {
                if (typeof spec.onFieldInput !== "function") return;
                const name = input.getAttribute("data-field") || input.getAttribute("data-profile-tool") || "";
                spec.onFieldInput(name, input.value);
            });
        });
        return controllerFor(container);
    }

    window.AlmdinaCncToolPicker = Object.freeze({
        markup,
        bind,
        mount,
    });
})();
