/* Unified door-piece add-on dialog. Settings and geometry stay in the liner editor. */
(() => {
    "use strict";

    if (window.AlmdinaDoorAddonsDialog) return;

    const FLAG_FIELDS = Object.freeze(["extra_double", "extra_full_door_double"]);

    function translate(message, values) {
        if (typeof __ !== "function") return message;
        return values ? __(message, values) : __(message);
    }

    function esc(value) {
        if (window.frappe && frappe.utils && frappe.utils.escape_html) {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "");
    }

    function extras() {
        return window.AlmdinaExtraDoorAddonsUX;
    }

    function editorApi() {
        return window.AlmdinaLinerEditor;
    }

    function kindFor(fieldname) {
        const engine = window.AlmdinaMachiningOverlay;
        if (engine && typeof engine.kindForField === "function") return engine.kindForField(fieldname);
        return fieldname === "extra_liner" ? "liner" : "";
    }

    function fields() {
        const api = extras();
        return api && Array.isArray(api.FIELDS) ? api.FIELDS : [];
    }

    function fieldByName(fieldname) {
        return fields().find(item => item.fieldname === fieldname) || null;
    }

    function machiningSupported(row) {
        const geometry = window.AlmdinaLinerGeometry;
        const editor = editorApi();
        if (!geometry || !editor || typeof geometry.availableSides !== "function") return false;
        return geometry.availableSides((row && row.piece_type) || "Regular").length > 0;
    }

    function sameValues(row, values) {
        return Object.entries(values || {}).every(([key, value]) => {
            const current = row ? row[key] : undefined;
            if (typeof value === "number" || typeof current === "number") {
                return Number(current || 0) === Number(value || 0);
            }
            return String(current || "") === String(value || "");
        });
    }

    function createSession(frm, row, preferredField) {
        const editor = editorApi();
        const supported = machiningSupported(row);
        const piece = editor && typeof editor.hostPiece === "function"
            ? editor.hostPiece(frm, row)
            : (window.AlmdinaLinerGeometry && window.AlmdinaLinerGeometry.pieceFromRow(row));
        const drafts = {};
        if (supported && editor && typeof editor.draftFromRow === "function") {
            fields().forEach((item) => {
                const kind = kindFor(item.fieldname);
                if (!kind) return;
                const draft = editor.draftFromRow(row, kind);
                draft.piece = piece;
                draft.row = row;
                drafts[item.fieldname] = draft;
            });
        }
        const flags = {
            extra_double: Number(row && row.extra_double) ? 1 : 0,
            extra_full_door_double: Number(row && row.extra_full_door_double) ? 1 : 0,
        };
        const known = fields().some(item => item.fieldname === preferredField);
        const initial = {};
        Object.entries(drafts).forEach(([fieldname, draft]) => {
            initial[fieldname] = {
                enabled: draft.enabled,
                side: draft.side,
                offsetCm: draft.offsetCm,
                widthCm: draft.widthCm,
                startCm: draft.startCm,
                lengthCm: draft.lengthCm,
            };
        });
        return {
            frm: frm || null,
            row,
            piece,
            supported,
            flags,
            drafts,
            initial,
            activeField: known ? preferredField : (fields()[0] ? fields()[0].fieldname : ""),
        };
    }

    function machiningDirty(session, fieldname) {
        const draft = session && session.drafts && session.drafts[fieldname];
        const initial = session && session.initial && session.initial[fieldname];
        if (!draft || !initial) return false;
        if (Boolean(draft.enabled) !== Boolean(initial.enabled) || draft.side !== initial.side) return true;
        return ["offsetCm", "widthCm", "startCm", "lengthCm"].some(key => Number(draft[key]) !== Number(initial[key]));
    }

    function selectTab(session, fieldname) {
        if (!session || !fieldByName(fieldname)) return session;
        session.activeField = fieldname;
        return session;
    }

    function setEnabled(session, fieldname, enabled) {
        if (!session || !fieldByName(fieldname)) return session;
        const next = enabled ? 1 : 0;
        if (FLAG_FIELDS.includes(fieldname)) {
            session.flags[fieldname] = next;
            if (next) {
                const peer = fieldname === "extra_double" ? "extra_full_door_double" : "extra_double";
                session.flags[peer] = 0;
            }
            return session;
        }
        const draft = session.drafts[fieldname];
        if (draft) draft.enabled = Boolean(next);
        return session;
    }

    function enabledPreviewDrafts(session) {
        if (!session) return [];
        return fields().map(item => session.drafts[item.fieldname]).filter(draft => draft && draft.enabled);
    }

    function isEnabled(session, fieldname) {
        if (FLAG_FIELDS.includes(fieldname)) return Boolean(session.flags[fieldname]);
        const draft = session.drafts[fieldname];
        return Boolean(draft && draft.enabled);
    }

    function invalidEnabledDraft(session) {
        const editor = editorApi();
        if (!editor || typeof editor.validationMessage !== "function") return null;
        const found = fields().map(item => session.drafts[item.fieldname]).find(draft => (
            draft && draft.enabled && editor.validationMessage(draft)
        ));
        if (!found) return null;
        return { draft: found, message: editor.validationMessage(found) };
    }

    function pieceTypeLabel(row) {
        const api = extras();
        const value = (row && row.piece_type) || "Regular";
        const found = api && api.PIECE_TYPES
            ? api.PIECE_TYPES.find(item => item.value === value)
            : null;
        return translate(found ? found.label : "Regular");
    }

    function metaItems(frm, row) {
        const width = row && (row.width_cm || row.cut_width_cm);
        const length = row && (row.length_cm || row.cut_length_cm);
        const items = [
            [translate("Door piece"), row.piece_no || row.idx || ""],
            [translate("Piece type"), pieceTypeLabel(row)],
            [translate("Size"), `${width} × ${length} ${translate("cm")}`],
            [translate("Qty"), row.qty || 1],
        ];
        const board = frm && frm.doc && String(frm.doc.board_description || "").trim();
        if (board) items.push([translate("Board Item"), board]);
        return items.filter(item => item[1] !== "" && item[1] != null);
    }

    function previewMarkup(session) {
        const editor = editorApi();
        if (!editor || typeof editor.previewSvg !== "function" || !session.piece) return "";
        const active = session.drafts[session.activeField];
        const carrier = active || {
            piece: session.piece,
            row: session.row,
            kind: "",
            side: "",
            enabled: false,
        };
        const companions = enabledPreviewDrafts(session).filter(draft => draft !== carrier);
        return editor.previewSvg(carrier, { multi: true, companions });
    }

    function settingsMarkup(session, editable) {
        const fieldname = session.activeField;
        const enabled = isEnabled(session, fieldname);
        const toggle = `<button type="button" class="dco-addons-enable ${enabled ? "is-on" : ""}" data-addon-enable="1" aria-pressed="${enabled ? "true" : "false"}" ${editable ? "" : "disabled"}>
            <span class="dco-addons-enable-mark" aria-hidden="true"></span>
            <span>${esc(translate("Add-on enabled"))}</span>
        </button>`;
        if (FLAG_FIELDS.includes(fieldname)) {
            return `${toggle}
                <div class="dco-corner-help">${esc(translate("Add-ons are available for every type; Double and Full Door Double are mutually exclusive."))}</div>`;
        }
        if (!session.supported) {
            return `<div class="dco-corner-help">${esc(translate("This piece type does not support this add-on."))}</div>`;
        }
        const draft = session.drafts[fieldname];
        const editor = editorApi();
        const fieldsHtml = draft && editor && typeof editor.controlsHtml === "function"
            ? editor.controlsHtml(draft)
            : "";
        const hint = enabled
            ? ""
            : `<div class="dco-corner-help">${esc(translate("Turn this add-on on to include it."))}</div>`;
        const body = `${toggle}${hint}<div data-addon-fields>${fieldsHtml}</div>`;
        return editable ? body : `<fieldset disabled>${body}</fieldset>`;
    }

    function shellHtml(session, editable) {
        const tabs = fields().map((item) => {
            const selected = item.fieldname === session.activeField;
            const enabled = isEnabled(session, item.fieldname);
            const dot = enabled
                ? `<span class="dco-addons-tab-dot" aria-hidden="true"></span>`
                : "";
            return `<button type="button" class="dco-addons-tab ${selected ? "is-selected" : ""} ${enabled ? "is-enabled" : ""}" role="tab" data-addon-tab="${esc(item.fieldname)}" aria-selected="${selected ? "true" : "false"}">${esc(translate(item.button))}${dot}</button>`;
        }).join("");
        const meta = metaItems(session.frm, session.row).map(([name, value]) => (
            `<span class="dco-addons-meta-item"><span class="dco-addons-meta-label">${esc(name)}</span><span class="dco-addons-meta-value">${esc(value)}</span></span>`
        )).join(`<span class="dco-addons-meta-sep" aria-hidden="true"></span>`);
        const removeName = translate((fieldByName(session.activeField) || {}).button || "");
        return `<div class="dco-addons-shell almdina-ui" data-addons-dialog>
            <div class="dco-addons-meta">${meta}</div>
            <div class="dco-addons-tabs" role="tablist">${tabs}</div>
            <div class="dco-addons-body">
                <section class="dco-addons-settings" data-addons-settings>${settingsMarkup(session, editable)}</section>
                <section class="dco-addons-preview-pane">
                    <div class="dco-addons-preview-card">
                        <div class="dco-addons-preview-title">${esc(translate("Piece preview"))}</div>
                        <div class="dco-addons-preview" data-addons-preview dir="ltr">${previewMarkup(session)}</div>
                    </div>
                </section>
            </div>
            <footer class="dco-addons-footer">
                <div class="dco-addons-footer-main">
                    <button type="button" class="btn btn-default btn-sm" data-addons-cancel>${esc(translate("Cancel"))}</button>
                    <button type="button" class="btn btn-sm alm-btn-primary" data-addons-apply ${editable ? "" : "hidden"}>${esc(translate("Apply"))}</button>
                </div>
                <button type="button" class="btn btn-default btn-sm dco-addons-remove" data-addons-remove ${editable ? "" : "hidden"}>${esc(translate("Remove {0}", [removeName]))}</button>
            </footer>
        </div>`;
    }

    function captureActive(session, root) {
        const fieldname = session.activeField;
        const draft = session.drafts[fieldname];
        const editor = editorApi();
        if (!draft || !root || !editor || typeof editor.readDraft !== "function") return draft;
        const fieldsRoot = root.querySelector("[data-addon-fields]") || root;
        if (!fieldsRoot.querySelector("[data-liner-offset]")) return draft;
        const next = editor.readDraft(fieldsRoot, session.piece, draft.enabled, session.row, draft.kind);
        next.enabled = draft.enabled;
        session.drafts[fieldname] = next;
        return next;
    }

    function writeSpanInputs(root, draft) {
        const startInput = root.querySelector("[data-liner-start]");
        const lengthInput = root.querySelector("[data-liner-length]");
        const editor = editorApi();
        if (!editor) return;
        if (startInput) startInput.value = String(Math.round(Number(draft.startCm) * 10) / 10);
        if (lengthInput) lengthInput.value = String(Math.round(Number(draft.lengthCm) * 10) / 10);
    }

    function paintChrome(root, session, editable) {
        const settings = root.querySelector("[data-addons-settings]");
        const preview = root.querySelector("[data-addons-preview]");
        if (settings) settings.innerHTML = settingsMarkup(session, editable);
        if (preview) preview.innerHTML = previewMarkup(session);
        root.querySelectorAll("[data-addon-tab]").forEach((button) => {
            const fieldname = button.getAttribute("data-addon-tab");
            const selected = fieldname === session.activeField;
            const enabled = isEnabled(session, fieldname);
            button.classList.toggle("is-selected", selected);
            button.classList.toggle("is-enabled", enabled);
            button.setAttribute("aria-selected", selected ? "true" : "false");
            const existing = button.querySelector(".dco-addons-tab-dot");
            if (enabled && !existing) {
                button.insertAdjacentHTML("beforeend", `<span class="dco-addons-tab-dot" aria-hidden="true"></span>`);
            }
            if (!enabled && existing) existing.remove();
        });
        const remove = root.querySelector("[data-addons-remove]");
        const definition = fieldByName(session.activeField);
        if (remove && definition) {
            remove.textContent = translate("Remove {0}", [translate(definition.button)]);
            remove.hidden = !editable;
            remove.disabled = !isEnabled(session, session.activeField);
        }
        const apply = root.querySelector("[data-addons-apply]");
        const invalid = invalidEnabledDraft(session);
        if (apply) apply.disabled = Boolean(invalid);
        const editor = editorApi();
        const active = session.drafts[session.activeField];
        if (active && settings && editor && typeof editor.paint === "function") editor.paint(settings, active, null);
    }

    function refreshTable(frm) {
        const fast = window.AlmdinaDoorCuttingFastEntry;
        if (fast && typeof fast.render === "function") fast.render(frm);
    }

    async function commitFlags(frm, row, flags) {
        const api = extras();
        if (!api || typeof api.enforceMutualExclusivity !== "function") return;
        const changed = [];
        FLAG_FIELDS.forEach((fieldname) => {
            const want = flags[fieldname] ? 1 : 0;
            if (Number(row[fieldname] || 0) === want) return;
            api.enforceMutualExclusivity(row, fieldname, Boolean(want)).forEach((name) => {
                if (!changed.includes(name)) changed.push(name);
            });
        });
        if (!changed.length) return;
        if (typeof frm.dirty === "function") frm.dirty();
        changed.forEach((fieldname) => {
            if (frm.script_manager && typeof frm.script_manager.trigger === "function") {
                Promise.resolve(frm.script_manager.trigger(fieldname, row.doctype, row.name)).catch(() => {});
            }
        });
    }

    async function commitMachining(frm, row, session) {
        const editor = editorApi();
        if (!session.supported || !editor || typeof editor.applyLiner !== "function") return true;
        for (let index = 0; index < fields().length; index += 1) {
            const fieldname = fields()[index].fieldname;
            const draft = session.drafts[fieldname];
            if (!draft || typeof editor.valuesFor !== "function" || !machiningDirty(session, fieldname)) continue;
            const values = editor.valuesFor(draft.kind, draft, draft.enabled);
            if (sameValues(row, values)) continue;
            const saved = await editor.applyLiner(frm, row, values, draft.kind);
            if (!saved) return false;
        }
        return true;
    }

    async function commitSession(session, root) {
        captureActive(session, root);
        const invalid = invalidEnabledDraft(session);
        if (invalid) {
            const fieldname = fields().find(item => session.drafts[item.fieldname] === invalid.draft);
            if (fieldname) selectTab(session, fieldname.fieldname);
            frappe.msgprint({
                title: translate("Check add-on"),
                message: invalid.message,
                indicator: "orange",
            });
            return false;
        }
        const dirtyMachining = fields().some(item => machiningDirty(session, item.fieldname));
        const dirtyFlags = FLAG_FIELDS.some(fieldname => (
            Number(session.flags[fieldname] || 0) !== Number(session.row[fieldname] || 0)
        ));
        if (dirtyMachining) {
            const machiningSaved = await commitMachining(session.frm, session.row, session);
            if (!machiningSaved) return false;
        }
        if (dirtyFlags) {
            await commitFlags(session.frm, session.row, session.flags);
            refreshTable(session.frm);
        }
        return true;
    }

    let activeDialog = null;

    function open(frm, row) {
        const editor = editorApi();
        if (!frm || !row || !extras() || !editor) return false;
        const width = Number(row.width_cm) || Number(row.cut_width_cm);
        const length = Number(row.length_cm) || Number(row.cut_length_cm);
        if (!(width > 0 && length > 0)) {
            frappe.msgprint({
                title: translate("Enter dimensions first"),
                message: translate("Enter the piece width and length before editing add-ons."),
                indicator: "orange",
            });
            return false;
        }
        if (activeDialog) {
            try { activeDialog.hide(); } catch (error) { /* previous dialog */ }
            activeDialog = null;
        }
        const fast = window.AlmdinaDoorCuttingFastEntry;
        const editable = !(fast && typeof fast.isEditable === "function") || fast.isEditable(frm);
        const session = createSession(frm, row);
        const dialog = new frappe.ui.Dialog({
            title: translate("Door piece add-ons"),
            fields: [{ fieldname: "addons_editor", fieldtype: "HTML" }],
        });
        activeDialog = dialog;
        dialog.$wrapper.addClass("dco-addons-modal");
        dialog.show();
        dialog.$wrapper.find(".modal-footer").attr("hidden", "hidden");
        const field = dialog.get_field("addons_editor");
        field.$wrapper.html(shellHtml(session, editable));
        const root = field.$wrapper.find("[data-addons-dialog]").get(0);
        paintChrome(root, session, editable);
        root.addEventListener("click", (event) => {
            const tab = event.target.closest("[data-addon-tab]");
            if (tab && root.contains(tab)) {
                captureActive(session, root);
                selectTab(session, tab.getAttribute("data-addon-tab"));
                paintChrome(root, session, editable);
                return;
            }
            const enable = event.target.closest("[data-addon-enable]");
            if (enable && root.contains(enable) && editable) {
                captureActive(session, root);
                setEnabled(session, session.activeField, !isEnabled(session, session.activeField));
                paintChrome(root, session, editable);
                return;
            }
            const side = event.target.closest("[data-liner-side]");
            if (side && root.contains(side) && editable) {
                const current = captureActive(session, root);
                if (!current || typeof editor.selectSide !== "function") return;
                const draft = editor.selectSide(current, session.piece, side.getAttribute("data-liner-side"));
                session.drafts[session.activeField] = draft;
                writeSpanInputs(root, draft);
                paintChrome(root, session, editable);
                return;
            }
            if (event.target.closest("[data-addons-cancel]")) {
                dialog.hide();
                return;
            }
            if (event.target.closest("[data-addons-remove]") && editable) {
                captureActive(session, root);
                setEnabled(session, session.activeField, false);
                paintChrome(root, session, editable);
                return;
            }
            if (event.target.closest("[data-addons-apply]") && editable) {
                const button = event.target.closest("[data-addons-apply]");
                button.disabled = true;
                commitSession(session, root).then((saved) => {
                    if (saved) dialog.hide();
                    else {
                        paintChrome(root, session, editable);
                        button.disabled = Boolean(invalidEnabledDraft(session));
                    }
                });
            }
        });
        root.addEventListener("input", () => {
            const draft = captureActive(session, root);
            if (draft && typeof editor.paint === "function") editor.paint(root, draft, null);
            const preview = root.querySelector("[data-addons-preview]");
            if (preview) preview.innerHTML = previewMarkup(session);
            const apply = root.querySelector("[data-addons-apply]");
            if (apply) apply.disabled = Boolean(invalidEnabledDraft(session));
        });
        return true;
    }

    window.AlmdinaDoorAddonsDialog = Object.freeze({
        open,
        createSession,
        selectTab,
        setEnabled,
        machiningDirty,
        enabledPreviewDrafts,
        previewMarkup,
        sameValues,
        commitSession,
    });
})();
