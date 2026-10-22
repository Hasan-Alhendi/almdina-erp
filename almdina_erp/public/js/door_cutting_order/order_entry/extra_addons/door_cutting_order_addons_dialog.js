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
                const draft = editor.draftFromRow(row, kind, { blankWhenMissing: true });
                draft.piece = piece;
                draft.edgeCm = editor.edgeLengthCm(piece, draft.side);
                if (draft.fullLength) draft.lengthCm = Math.max(0, draft.edgeCm - draft.startCm);
                if (draft.kind === "liner" && Array.isArray(draft.liners) && draft.liners[0]) {
                    draft.liners[0].side = draft.side;
                    draft.liners[0].edgeCm = draft.edgeCm;
                    draft.liners[0].startCm = draft.startCm;
                    draft.liners[0].lengthCm = draft.lengthCm;
                    draft.liners[0].fullLength = draft.fullLength;
                }
                draft.row = row;
                drafts[item.fieldname] = draft;
            });
        }
        const presenceOnly = String((row && row.piece_type) || "") === "Special";
        const flags = {
            extra_double: Number(row && row.extra_double) ? 1 : 0,
            extra_full_door_double: Number(row && row.extra_full_door_double) ? 1 : 0,
        };
        if (presenceOnly) {
            fields().forEach((item) => {
                if (flags[item.fieldname] === undefined) {
                    flags[item.fieldname] = Number(row && row[item.fieldname]) ? 1 : 0;
                }
            });
        }
        const doubleSides = editor && typeof editor.doubleEdgeSidesFromRow === "function"
            ? editor.doubleEdgeSidesFromRow(row)
            : [];
        const known = fields().some(item => item.fieldname === preferredField);
        const initial = {};
        Object.entries(drafts).forEach(([fieldname, draft]) => {
            initial[fieldname] = snapshotDraft(draft);
        });
        initial.extra_double = flags.extra_double;
        initial.extra_double_reference_sides = doubleSides.slice();
        if (presenceOnly) {
            Object.entries(flags).forEach(([fieldname, value]) => {
                initial[fieldname] = value ? 1 : 0;
            });
        }
        return {
            frm: frm || null,
            row,
            piece,
            presenceOnly,
            supported,
            flags,
            doubleSides,
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
        if (Boolean(draft.fullLength) !== Boolean(initial.fullLength)
            || Boolean(draft.legacyCheckboxOnly) !== Boolean(initial.legacyCheckboxOnly)) return true;
        if (["offsetCm", "widthCm", "startCm", "lengthCm"].some(key => Number(draft[key]) !== Number(initial[key]))) {
            return true;
        }
        return JSON.stringify(linerSnapshot(draft)) !== JSON.stringify(linerSnapshot(initial));
    }

    function doubleSidesDirty(session) {
        if (!session) return false;
        const initial = (session.initial && session.initial.extra_double_reference_sides) || [];
        return JSON.stringify(session.doubleSides || []) !== JSON.stringify(initial)
            || Number(session.flags.extra_double || 0) !== Number(session.initial.extra_double || 0);
    }

    function selectTab(session, fieldname) {
        if (!session || !fieldByName(fieldname)) return session;
        session.activeField = fieldname;
        return session;
    }

    function setEnabled(session, fieldname, enabled) {
        if (!session || !fieldByName(fieldname)) return session;
        const next = enabled ? 1 : 0;
        if (session.presenceOnly && !FLAG_FIELDS.includes(fieldname)) {
            session.flags[fieldname] = next;
            return session;
        }
        if (FLAG_FIELDS.includes(fieldname)) {
            const scratch = {};
            FLAG_FIELDS.forEach((name) => { scratch[name] = session.flags[name] ? 1 : 0; });
            const api = extras();
            if (api && typeof api.enforceMutualExclusivity === "function") {
                api.enforceMutualExclusivity(scratch, fieldname, Boolean(next));
            } else {
                scratch[fieldname] = next;
            }
            FLAG_FIELDS.forEach((name) => { session.flags[name] = scratch[name] ? 1 : 0; });
            return session;
        }
        const draft = session.drafts[fieldname];
        if (draft) {
            draft.enabled = Boolean(next);
            if (next) draft.legacyCheckboxOnly = false;
        }
        return session;
    }

    function enabledPreviewDrafts(session) {
        if (!session) return [];
        return fields().map(item => session.drafts[item.fieldname]).filter(draft => draft && draft.enabled);
    }

    function isEnabled(session, fieldname) {
        if ((session && session.presenceOnly) || FLAG_FIELDS.includes(fieldname)) {
            return Boolean(session.flags[fieldname]);
        }
        const draft = session.drafts[fieldname];
        return Boolean(draft && draft.enabled);
    }

    function invalidEnabledDraft(session) {
        const editor = editorApi();
        if (!session || !editor || typeof editor.validationMessage !== "function") return null;
        if (session.presenceOnly) return null;
        if (session.flags.extra_double && !(session.doubleSides || []).length) {
            return {
                code: "double_edge_sides_required",
                fieldname: "extra_double",
                field: "sides",
                fields: ["sides"],
                message: translate("Select at least one side for Double Edge."),
                label: translate("Double Edge"),
            };
        }
        const candidates = fields().filter((entry) => {
            const draft = session.drafts[entry.fieldname];
            return draft && draft.enabled;
        });
        candidates.sort((a, b) => Number(b.fieldname === session.activeField) - Number(a.fieldname === session.activeField));
        for (const item of candidates) {
            const draft = session.drafts[item.fieldname];
            const issue = typeof editor.validationIssue === "function"
                ? editor.validationIssue(draft)
                : (editor.validationMessage(draft)
                    ? { message: editor.validationMessage(draft), fields: [] }
                    : null);
            if (issue) return { ...issue, fieldname: item.fieldname, label: translate(item.button), draft };
        }
        return null;
    }

    function removalPending(session) {
        if (!session) return false;
        const fieldname = session.activeField;
        if (session.presenceOnly || FLAG_FIELDS.includes(fieldname)) {
            return !session.flags[fieldname] && Boolean(Number(session.row && session.row[fieldname]));
        }
        const initial = session.initial && session.initial[fieldname];
        const draft = session.drafts && session.drafts[fieldname];
        return Boolean(initial && initial.enabled && draft && !draft.enabled);
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
        if (session.presenceOnly) {
            return editor.previewSvg({
                piece: session.piece,
                row: session.row,
                kind: "",
                side: "",
                enabled: false,
            }, {
                multi: true,
                companions: [],
                doubleSides: [],
            });
        }
        const active = session.drafts[session.activeField];
        const carrier = active || {
            piece: session.piece,
            row: session.row,
            kind: "",
            side: "",
            enabled: false,
        };
        const companions = enabledPreviewDrafts(session).filter(draft => draft !== carrier).flatMap((draft) => {
            if (draft.kind !== "liner" || typeof editor.linerItems !== "function") return [draft];
            return editor.linerItems(draft).map(item => Object.assign({}, draft, item, {
                widthCm: draft.widthCm,
                liners: null,
            }));
        });
        return editor.previewSvg(carrier, {
            multi: true,
            companions,
            doubleSides: session.doubleSides,
            doubleInteractive: session.activeField === "extra_double",
        });
    }

    function settingsMarkup(session, editable) {
        const fieldname = session.activeField;
        const enabled = isEnabled(session, fieldname);
        const toggle = `<button type="button" class="dco-addons-enable ${enabled ? "is-on" : ""}" data-addon-enable="1" aria-pressed="${enabled ? "true" : "false"}" ${editable ? "" : "disabled"}>
            <span class="dco-addons-enable-mark" aria-hidden="true"></span>
            <span>${esc(translate("Add-on enabled"))}</span>
        </button>`;
        if (session.presenceOnly) {
            const body = `${toggle}
                <div class="dco-corner-help">${esc(translate("Selection is enough for a special door. Complete the add-on paths in the DXF before approval."))}</div>
                <div class="dco-corner-help">${esc(translate("Add-ons are available for every type; Double and Full Door Double are mutually exclusive."))}</div>`;
            return editable ? body : `<fieldset disabled>${body}</fieldset>`;
        }
        if (fieldname === "extra_double") {
            const geometry = window.AlmdinaLinerGeometry;
            const sides = geometry && typeof geometry.availableSides === "function"
                ? geometry.availableSides(session.piece && session.piece.pieceType)
                : [];
            const sideButtons = sides.map(side => {
                const selected = (session.doubleSides || []).includes(side);
                return `<button type="button" class="dco-corner-position ${selected ? "is-active" : ""}" data-double-side="${esc(side)}" aria-pressed="${selected ? "true" : "false"}">${esc(geometry.sideLabel(side, session.piece && session.piece.pieceType))}</button>`;
            }).join("");
            const body = `${toggle}
                <div class="dco-corner-help" data-addons-hint ${enabled && session.doubleSides.length ? "hidden" : ""}>${esc(enabled ? translate("Choose one or more sides.") : translate("Turn this add-on on to include it."))}</div>
                <div class="dco-corner-section-label">${esc(translate("Double Edge sides"))}</div>
                <div class="dco-corner-position-grid" data-double-sides>${sideButtons}</div>
                <div class="dco-corner-help">${esc(translate("Double Edge is shown as two purple lines on each selected side."))}</div>`;
            return editable ? body : `<fieldset disabled>${body}</fieldset>`;
        }
        if (FLAG_FIELDS.includes(fieldname)) {
            return `${toggle}
                <div class="dco-corner-help" data-addons-hint ${enabled ? "hidden" : ""}>${esc(translate("Turn this add-on on to include it."))}</div>
                <div class="dco-corner-help">${esc(translate("Add-ons are available for every type; Double and Full Door Double are mutually exclusive."))}</div>`;
        }
        if (!session.supported) {
            return `<div class="dco-corner-help">${esc(translate("This piece type does not support this add-on."))}</div>`;
        }
        const draft = session.drafts[fieldname];
        const editor = editorApi();
        const fieldsHtml = draft && editor && fieldname === "extra_liner" && typeof editor.linerSetHtml === "function"
            ? editor.linerSetHtml(draft)
            : (draft && editor && typeof editor.controlsHtml === "function"
                ? editor.controlsHtml(draft)
                : "");
        const hint = `<div class="dco-corner-help" data-addons-hint ${enabled ? "hidden" : ""}>${esc(translate("Turn this add-on on to include it."))}</div>`;
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
            <div class="dco-addons-error" data-addons-error hidden></div>
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
                    <button type="button" class="btn btn-default btn-sm" data-addons-cancel>${esc(translate(editable ? "Cancel" : "Close"))}</button>
                    <button type="button" class="btn btn-sm alm-btn-primary" data-addons-apply ${editable ? "" : "hidden"}>${esc(translate("Apply"))}</button>
                </div>
                <button type="button" class="btn btn-default btn-sm dco-addons-remove" data-addons-remove ${editable ? "" : "hidden"}>${esc(translate("Remove {0}", [removeName]))}</button>
            </footer>
        </div>`;
    }

    function captureActive(session, root, changedField, changedItemId) {
        const fieldname = session.activeField;
        const draft = session.drafts[fieldname];
        const editor = editorApi();
        if (!draft || !root || !editor || typeof editor.readDraft !== "function") return draft;
        const fieldsRoot = root.querySelector("[data-addon-fields]") || root;
        if (!fieldsRoot.querySelector("[data-liner-offset]")) return draft;
        const next = fieldname === "extra_liner" && typeof editor.readLinerSet === "function"
            ? editor.readLinerSet(fieldsRoot, session.piece, draft, changedField, changedItemId)
            : editor.readDraft(
                fieldsRoot,
                session.piece,
                draft.enabled,
                session.row,
                draft.kind,
                draft,
                changedField,
            );
        next.enabled = draft.enabled;
        session.drafts[fieldname] = next;
        return next;
    }

    function writeSpanInputs(root, draft) {
        const startInput = root.querySelector("[data-liner-start]");
        const lengthInput = root.querySelector("[data-liner-length]");
        const editor = editorApi();
        if (!editor) return;
        const format = value => editor.formatInputCm ? editor.formatInputCm(value) : String(value);
        if (startInput) startInput.value = format(draft.startCm);
        if (lengthInput) lengthInput.value = format(draft.lengthCm);
    }

    function showIssue(root, session, issue) {
        const banner = root && root.querySelector("[data-addons-error]");
        const help = root && root.querySelector("[data-liner-help]");
        const here = Boolean(issue && issue.fieldname === session.activeField);
        ["offset", "width", "start", "length"].forEach((field) => {
            (root ? root.querySelectorAll(`[data-liner-${field}]`) : []).forEach((input) => {
                input.removeAttribute("aria-invalid");
                const wrap = input.closest && input.closest(".dco-corner-input-wrap");
                if (wrap) wrap.classList.remove("is-error");
            });
        });
        const sideGroup = root && root.querySelector("[data-liner-sides]");
        if (sideGroup) sideGroup.removeAttribute("aria-invalid");
        const doubleSideGroup = root && root.querySelector("[data-double-sides]");
        if (doubleSideGroup) doubleSideGroup.removeAttribute("aria-invalid");
        if (issue && here) {
            const scope = issue.linerId && root
                ? root.querySelector(`[data-liner-item="${issue.linerId}"]`) || root
                : root;
            const scopedSide = scope && scope.querySelector("[data-liner-sides]");
            (issue.fields || (issue.field ? [issue.field] : [])).forEach((field) => {
                if (field === "side") {
                    if (scopedSide || sideGroup) (scopedSide || sideGroup).setAttribute("aria-invalid", "true");
                    return;
                }
                if (field === "sides") {
                    if (doubleSideGroup) doubleSideGroup.setAttribute("aria-invalid", "true");
                    return;
                }
                const input = (scope || root) && (scope || root).querySelector(`[data-liner-${field}]`);
                if (!input) return;
                input.setAttribute("aria-invalid", "true");
                const wrap = input.closest && input.closest(".dco-corner-input-wrap");
                if (wrap) wrap.classList.add("is-error");
            });
        }
        if (help) help.textContent = here ? issue.message : "";
        if (help) help.classList.toggle("is-error", here);
        if (!banner) return;
        if (!issue) {
            banner.hidden = true;
            banner.textContent = "";
            return;
        }
        banner.hidden = false;
        banner.textContent = !issue.label || here
            ? issue.message
            : translate("{0}: {1}", [issue.label, issue.message]);
    }

    function syncPreview(root, session) {
        const preview = root && root.querySelector("[data-addons-preview]");
        if (preview) preview.innerHTML = previewMarkup(session);
    }

    function syncTabs(root, session) {
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
    }

    function syncEnable(root, session, editable) {
        const button = root.querySelector("[data-addon-enable]");
        const enabled = isEnabled(session, session.activeField);
        if (button) {
            button.classList.toggle("is-on", enabled);
            button.setAttribute("aria-pressed", enabled ? "true" : "false");
            button.disabled = !editable;
        }
        const hint = root.querySelector("[data-addons-hint]");
        if (!hint) return;
        const draft = session.drafts && session.drafts[session.activeField];
        const pending = removalPending(session);
        if (pending) {
            hint.hidden = false;
            hint.textContent = translate("This removal is saved when you press Apply.");
            return;
        }
        if (!enabled && draft && !draft.side) {
            hint.hidden = false;
            hint.textContent = translate("Choose a reference side to include this add-on.");
            return;
        }
        if (session.activeField === "extra_double" && enabled && !(session.doubleSides || []).length) {
            hint.hidden = false;
            hint.textContent = translate("Choose one or more sides.");
            return;
        }
        hint.hidden = enabled;
        hint.textContent = translate("Turn this add-on on to include it.");
    }

    function syncRemove(root, session, editable) {
        const remove = root.querySelector("[data-addons-remove]");
        const definition = fieldByName(session.activeField);
        if (!remove || !definition) return;
        if (!session.saving) remove.textContent = translate("Remove {0}", [translate(definition.button)]);
        remove.hidden = !editable;
        remove.disabled = !editable || !isEnabled(session, session.activeField);
    }

    function syncSides(root, draft, session) {
        if (!root) return;
        if (session && session.activeField === "extra_double") {
            root.querySelectorAll("[data-double-side]").forEach((button) => {
                const selected = (session.doubleSides || []).includes(button.getAttribute("data-double-side"));
                button.classList.toggle("is-active", selected);
                button.setAttribute("aria-pressed", selected ? "true" : "false");
            });
            return;
        }
        if (!draft) return;
        const editor = editorApi();
        const items = draft.kind === "liner" && editor && typeof editor.linerItems === "function"
            ? editor.linerItems(draft)
            : [draft];
        root.querySelectorAll("[data-liner-item]").forEach((section, index) => {
            const item = items[index] || items[0];
            if (!item) return;
            section.querySelectorAll("[data-liner-side]").forEach((button) => {
                const selected = button.getAttribute("data-liner-side") === item.side;
                button.classList.toggle("is-active", selected);
                button.setAttribute("aria-pressed", selected ? "true" : "false");
            });
            const available = section.querySelector("[data-liner-available]");
            const direction = section.querySelector("[data-liner-direction]");
            if (available) {
                available.textContent = `${translate("Available Length")}: ${Math.round(Number(item.edgeCm) * 10) / 10} ${translate("cm")}`;
            }
            if (direction) {
                const directionKey = {
                    edge_long_right: "Top to bottom",
                    edge_long_left: "Top to bottom",
                    edge_width_top: "Left to right",
                    edge_width_bottom: "Left to right",
                }[item.side] || "Along the selected edge";
                direction.textContent = `${translate("Measurement Direction")}: ${translate(directionKey)}`;
            }
        });
        if (root.querySelector("[data-liner-item]")) return;
        root.querySelectorAll("[data-liner-side]").forEach((button) => {
            const selected = button.getAttribute("data-liner-side") === draft.side;
            button.classList.toggle("is-active", selected);
            button.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        const available = root.querySelector("[data-liner-available]");
        const direction = root.querySelector("[data-liner-direction]");
        if (available) {
            available.textContent = `${translate("Available Length")}: ${Math.round(Number(draft.edgeCm) * 10) / 10} ${translate("cm")}`;
        }
        if (direction) {
            const directionKey = {
                edge_long_right: "Top to bottom",
                edge_long_left: "Top to bottom",
                edge_width_top: "Left to right",
                edge_width_bottom: "Left to right",
            }[draft.side] || "Along the selected edge";
            direction.textContent = `${translate("Measurement Direction")}: ${translate(directionKey)}`;
        }
    }

    function syncApply(root, session, editable) {
        const apply = root.querySelector("[data-addons-apply]");
        if (!apply || session.saving) return;
        apply.disabled = !editable || Boolean(invalidEnabledDraft(session));
        apply.removeAttribute("aria-busy");
    }

    function syncChrome(root, session, editable) {
        if (!root) return;
        syncTabs(root, session);
        syncEnable(root, session, editable);
        syncRemove(root, session, editable);
        syncSides(root, session.drafts[session.activeField], session);
        if (editorApi() && typeof editorApi().syncHandleChoices === "function") {
            editorApi().syncHandleChoices(root, session.drafts[session.activeField]);
        }
        syncPreview(root, session);
        showIssue(root, session, invalidEnabledDraft(session));
        syncApply(root, session, editable);
    }

    function paintStructure(root, session, editable) {
        const settings = root && root.querySelector("[data-addons-settings]");
        if (settings) settings.innerHTML = settingsMarkup(session, editable);
        if (root) root._addonsField = session.activeField;
        syncChrome(root, session, editable);
    }

    function refreshTable(frm) {
        const fast = window.AlmdinaDoorCuttingFastEntry;
        if (fast && typeof fast.render === "function") fast.render(frm);
    }

    function linerSnapshot(draft) {
        const editor = editorApi();
        const items = draft && editor && typeof editor.linerItems === "function" && draft.kind === "liner"
            ? editor.linerItems(draft)
            : (draft && Array.isArray(draft.liners) ? draft.liners : []);
        return items.map(item => ({
            id: item.id,
            side: item.side,
            offsetCm: Number(item.offsetCm),
            startCm: Number(item.startCm),
            lengthCm: Number(item.lengthCm),
            fullLength: Boolean(item.fullLength),
        }));
    }

    function snapshotDraft(draft) {
        return {
            enabled: draft.enabled,
            side: draft.side,
            offsetCm: draft.offsetCm,
            widthCm: draft.widthCm,
            startCm: draft.startCm,
            lengthCm: draft.lengthCm,
            fullLength: Boolean(draft.fullLength),
            legacyCheckboxOnly: Boolean(draft.legacyCheckboxOnly),
            liners: linerSnapshot(draft),
        };
    }

    function collectValues(session) {
        if (session && session.presenceOnly) {
            const values = {};
            const touched = [];
            fields().forEach((item) => {
                const next = session.flags[item.fieldname] ? 1 : 0;
                const current = Number(session.row && session.row[item.fieldname] || 0) ? 1 : 0;
                if (next === current) return;
                values[item.fieldname] = next;
                touched.push(item.fieldname);
            });
            if (touched.length) {
                const engine = window.AlmdinaMachiningOverlay;
                (engine && engine.ADDONS ? engine.ADDONS : []).forEach((spec) => {
                    values[spec.side] = "";
                    values[spec.offset] = 0;
                    values[spec.width] = 0;
                    values[spec.start] = 0;
                    values[spec.length] = 0;
                    if (spec.specs) values[spec.specs] = "";
                });
                values.extra_double_reference_sides = "";
            }
            return { values, touched };
        }
        const values = {};
        const touched = [];
        if (doubleSidesDirty(session)) {
            values.extra_double = session.flags.extra_double ? 1 : 0;
            values.extra_double_reference_sides = session.flags.extra_double
                ? JSON.stringify(session.doubleSides || [])
                : "";
            touched.push("extra_double");
            touched.push("extra_double_reference_sides");
        }
        const flagsDirty = FLAG_FIELDS.some(fieldname => (
            Number(session.flags[fieldname] || 0) !== Number(session.row && session.row[fieldname] || 0)
        ));
        if (flagsDirty) {
            FLAG_FIELDS.forEach((fieldname) => {
                if (fieldname === "extra_double" && doubleSidesDirty(session)) return;
                values[fieldname] = session.flags[fieldname] ? 1 : 0;
                touched.push(fieldname);
            });
        }
        const editor = editorApi();
        if (session.supported && editor && typeof editor.valuesFor === "function") {
            fields().forEach((item) => {
                const draft = session.drafts[item.fieldname];
                if (!draft || !machiningDirty(session, item.fieldname)) return;
                const next = editor.valuesFor(draft.kind, draft, draft.enabled);
                if (sameValues(session.row, next)) return;
                Object.assign(values, next);
                touched.push(item.fieldname);
            });
        }
        return { values, touched };
    }

    function markClean(session) {
        Object.entries(session.drafts || {}).forEach(([fieldname, draft]) => {
            session.initial[fieldname] = snapshotDraft(draft);
        });
        session.initial.extra_double = session.flags.extra_double ? 1 : 0;
        session.initial.extra_double_reference_sides = (session.doubleSides || []).slice();
    }

    function failSave(session, root, issue, indicator) {
        if (issue && issue.fieldname && issue.fieldname !== session.activeField) {
            selectTab(session, issue.fieldname);
            if (root) paintStructure(root, session, session.editable !== false);
        } else if (root) {
            showIssue(root, session, issue);
            syncPreview(root, session);
        }
        if (typeof frappe !== "undefined" && frappe.msgprint) {
            frappe.msgprint({
                title: translate("Check add-on"),
                message: issue && issue.label
                    ? translate("{0}: {1}", [issue.label, issue.message])
                    : (issue && issue.message) || translate("Could not save the add-ons."),
                indicator: indicator || "orange",
            });
        }
        return false;
    }

    function controlAttached(node) {
        if (!node) return false;
        if (typeof node.isConnected === "boolean") return node.isConnected;
        return Boolean(node.parentNode || node.parent);
    }

    async function commitSession(session, root) {
        if (!session) return false;
        if (session.savePromise) return session.savePromise;
        captureActive(session, root);
        const invalid = invalidEnabledDraft(session);
        if (invalid) return failSave(session, root, invalid, "orange");
        const pending = collectValues(session);
        if (!pending.touched.length) return true;
        const run = (async () => {
            session.saving = true;
            const apply = root && root.querySelector("[data-addons-apply]");
            const applyLabel = apply ? apply.textContent : "";
            const locked = root ? Array.from(root.querySelectorAll("input, button")) : [];
            locked.forEach((node) => {
                node.addonsLock = node.disabled;
                node.disabled = true;
            });
            if (apply) {
                apply.setAttribute("aria-busy", "true");
                apply.textContent = translate("Saving");
            }
            try {
                const frm = session.frm;
                const corner = window.AlmdinaClippedCornerEditor;
                const row = corner && typeof corner.resolveChildRow === "function"
                    ? corner.resolveChildRow(frm, session.row)
                    : session.row;
                if (!row) {
                    return failSave(session, root, {
                        message: translate("This door piece is no longer in the order."),
                    }, "orange");
                }
                let live = row;
                if (corner && typeof corner.commitChildValues === "function") {
                    live = (await corner.commitChildValues(frm, row, pending.values)) || row;
                } else if (typeof frappe !== "undefined" && frappe.model && typeof frappe.model.set_value === "function") {
                    await frappe.model.set_value(row.doctype, row.name, pending.values);
                } else if (frm && typeof frm.dirty === "function") {
                    frm.dirty();
                }
                Object.assign(live, pending.values);
                session.row = live;
                markClean(session);
                if (frm && typeof frm.dirty === "function") frm.dirty();
                refreshTable(frm);
                return true;
            } catch (error) {
                return failSave(session, root, {
                    message: (error && error.message) || translate("Could not save the add-ons."),
                }, "red");
            } finally {
                session.saving = false;
                session.savePromise = null;
                locked.forEach((node) => {
                    if (!controlAttached(node)) return;
                    node.disabled = Boolean(node.addonsLock);
                });
                if (apply && controlAttached(apply)) {
                    apply.removeAttribute("aria-busy");
                    apply.textContent = applyLabel || translate("Apply");
                }
            }
        })();
        session.savePromise = run;
        return run;
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
        session.editable = editable;
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
        paintStructure(root, session, editable);
        root.addEventListener("click", (event) => {
            const tab = event.target.closest("[data-addon-tab]");
            if (tab && root.contains(tab)) {
                captureActive(session, root);
                selectTab(session, tab.getAttribute("data-addon-tab"));
                paintStructure(root, session, editable);
                return;
            }
            const enable = event.target.closest("[data-addon-enable]");
            if (enable && root.contains(enable) && editable) {
                captureActive(session, root);
                setEnabled(session, session.activeField, !isEnabled(session, session.activeField));
                syncChrome(root, session, editable);
                return;
            }
            const addLiner = event.target.closest("[data-add-liner]");
            if (addLiner && root.contains(addLiner) && editable && editor && typeof editor.addLiner === "function") {
                captureActive(session, root);
                const current = session.drafts.extra_liner;
                if (!current) return;
                session.drafts.extra_liner = editor.addLiner(current);
                setEnabled(session, "extra_liner", true);
                paintStructure(root, session, editable);
                const items = root.querySelectorAll("[data-liner-item]");
                const added = items[items.length - 1];
                const pane = root.querySelector("[data-addons-settings]");
                if (added && typeof added.scrollIntoView === "function") {
                    added.scrollIntoView({ behavior: "smooth", block: "nearest" });
                } else if (pane && added && typeof pane.scrollTo === "function") {
                    pane.scrollTo({ top: added.offsetTop, behavior: "smooth" });
                }
                return;
            }
            const removeItem = event.target.closest("[data-liner-remove-item]");
            if (removeItem && root.contains(removeItem) && editable && editor && typeof editor.removeLiner === "function") {
                captureActive(session, root);
                const current = session.drafts.extra_liner;
                if (!current) return;
                session.drafts.extra_liner = editor.removeLiner(current, removeItem.getAttribute("data-liner-remove-item"));
                paintStructure(root, session, editable);
                return;
            }
            const side = event.target.closest("[data-liner-side]");
            if (side && root.contains(side) && editable) {
                const item = side.closest("[data-liner-item]");
                const itemId = item && item.getAttribute("data-liner-item");
                const current = captureActive(session, root, "", itemId);
                if (!current || typeof editor.selectSide !== "function") return;
                if (itemId && Array.isArray(current.liners)) {
                    const target = current.liners.find(entry => entry.id === itemId);
                    if (target) {
                        editor.selectSide(target, session.piece, side.getAttribute("data-liner-side"));
                        target.legacyCheckboxOnly = false;
                        session.drafts[session.activeField] = editor.linerItems
                            ? Object.assign(current, { liners: current.liners })
                            : current;
                        if (current.liners[0] && current.liners[0].id === itemId) {
                            editor.selectSide(current, session.piece, side.getAttribute("data-liner-side"));
                        }
                    }
                } else {
                    const draft = editor.selectSide(current, session.piece, side.getAttribute("data-liner-side"));
                    session.drafts[session.activeField] = draft;
                }
                setEnabled(session, session.activeField, true);
                writeSpanInputs(item || root, itemId && current.liners
                    ? current.liners.find(entry => entry.id === itemId) || current
                    : current);
                syncChrome(root, session, editable);
                return;
            }
            const sizeButton = event.target.closest("[data-handle-size]");
            if (sizeButton && root.contains(sizeButton) && editable && editor) {
                const current = captureActive(session, root, "length");
                const sizeId = sizeButton.getAttribute("data-handle-size");
                const size = (editor.handleStandardSizes || []).find(item => item.id === sizeId);
                if (!current || !size || typeof editor.applyStandardHandleSize !== "function") return;
                const next = editor.applyStandardHandleSize(current, size);
                next.enabled = true;
                session.drafts[session.activeField] = next;
                setEnabled(session, session.activeField, true);
                editor.writeMachiningInputs(root, next);
                syncChrome(root, session, editable);
                return;
            }
            const centerButton = event.target.closest("[data-handle-center]");
            if (centerButton && root.contains(centerButton) && editable && editor) {
                const current = captureActive(session, root, "offset");
                if (!current || typeof editor.centerHandleDraft !== "function") return;
                const outcome = editor.centerHandleDraft(current);
                if (!outcome.ok) {
                    syncChrome(root, session, editable);
                    const message = outcome.message || editor.centerHandleMessage(outcome.code);
                    const help = root.querySelector("[data-liner-help]");
                    if (help) {
                        help.textContent = message;
                        help.classList.add("is-error");
                    }
                    const banner = root.querySelector("[data-addons-error]");
                    if (banner) {
                        banner.hidden = false;
                        banner.textContent = message;
                    }
                    if (typeof frappe !== "undefined" && frappe.msgprint) {
                        frappe.msgprint({
                            title: translate("Center Handle"),
                            message,
                            indicator: "orange",
                        });
                    }
                    return;
                }
                const next = Object.assign({}, outcome.draft, { enabled: true });
                session.drafts[session.activeField] = next;
                setEnabled(session, session.activeField, true);
                editor.writeMachiningInputs(root, next);
                syncChrome(root, session, editable);
                return;
            }
            const doubleSide = event.target.closest("[data-double-side]");
            if (doubleSide && root.contains(doubleSide) && editable) {
                const sideName = doubleSide.getAttribute("data-double-side");
                const current = new Set(session.doubleSides || []);
                if (current.has(sideName)) current.delete(sideName);
                else current.add(sideName);
                const geometry = window.AlmdinaLinerGeometry;
                const available = geometry && typeof geometry.availableSides === "function"
                    ? geometry.availableSides(session.piece && session.piece.pieceType)
                    : [];
                session.doubleSides = available.filter(sideNameValue => current.has(sideNameValue));
                setEnabled(session, "extra_double", true);
                syncChrome(root, session, editable);
                return;
            }
            if (event.target.closest("[data-addons-cancel]")) {
                dialog.hide();
                return;
            }
            if (event.target.closest("[data-addons-remove]") && editable) {
                captureActive(session, root);
                setEnabled(session, session.activeField, false);
                syncChrome(root, session, editable);
                return;
            }
            if (event.target.closest("[data-addons-apply]") && editable) {
                commitSession(session, root).then((saved) => {
                    if (saved) dialog.hide();
                });
            }
        });
        root.addEventListener("input", (event) => {
            if (!editable) return;
            const target = event && event.target;
            const changedField = ["offset", "width", "start", "length"].find(field => (
                target && target.matches && target.matches(`[data-liner-${field}]`)
            )) || "";
            const item = target && target.closest && target.closest("[data-liner-item]");
            const itemId = item ? item.getAttribute("data-liner-item") : "";
            const draft = captureActive(session, root, changedField, itemId);
            if (draft && changedField === "start") {
                const host = item && Array.isArray(draft.liners)
                    ? draft.liners.find(entry => entry.id === itemId)
                    : draft;
                if (host && host.fullLength) writeSpanInputs(item || root, host);
            }
            if (editor && typeof editor.syncHandleChoices === "function") editor.syncHandleChoices(root, draft);
            syncPreview(root, session);
            showIssue(root, session, invalidEnabledDraft(session));
            syncApply(root, session, editable);
        });
        return true;
    }

    function hasEnabledMachining(frm) {
        const rows = frm && frm.doc && Array.isArray(frm.doc.pieces) ? frm.doc.pieces : [];
        return rows.some(row => fields().some(item => {
            return Boolean(kindFor(item.fieldname)) && Boolean(Number(row && row[item.fieldname]));
        }));
    }

    function validateOrder(frm) {
        const editor = editorApi();
        const geometry = window.AlmdinaLinerGeometry;
        const rows = frm && frm.doc && Array.isArray(frm.doc.pieces) ? frm.doc.pieces : [];
        if (!editor || typeof editor.validationIssue !== "function" || !geometry) return null;
        for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
            const row = rows[rowIndex];
            if (!machiningSupported(row)) continue;
            const piece = typeof editor.hostPiece === "function"
                ? editor.hostPiece(frm, row)
                : geometry.pieceFromRow(row);
            for (const item of fields()) {
                const kind = kindFor(item.fieldname);
                if (!kind || !Number(row && row[item.fieldname])) continue;
                const draft = editor.draftFromRow(row, kind, { blankWhenMissing: true });
                draft.piece = piece;
                draft.edgeCm = editor.edgeLengthCm(piece, draft.side);
                if (draft.fullLength) draft.lengthCm = Math.max(0, draft.edgeCm - draft.startCm);
                const issue = editor.validationIssue(draft);
                if (!issue) continue;
                const rowNumber = row.piece_no || row.idx || rowIndex + 1;
                return {
                    ...issue,
                    row,
                    rowNumber,
                    fieldname: item.fieldname,
                    label: translate(item.button),
                    message: translate("Row {0}: {1}: {2}", [rowNumber, translate(item.button), issue.message]),
                };
            }
        }
        return null;
    }

    window.AlmdinaDoorAddonsDialog = Object.freeze({
        open,
        createSession,
        settingsMarkup,
        collectValues,
        selectTab,
        setEnabled,
        machiningDirty,
        doubleSidesDirty,
        enabledPreviewDrafts,
        previewMarkup,
        sameValues,
        commitSession,
        hasEnabledMachining,
        validateOrder,
    });
})();
