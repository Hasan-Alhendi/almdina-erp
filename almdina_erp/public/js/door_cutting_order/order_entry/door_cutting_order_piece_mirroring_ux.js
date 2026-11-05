(() => {
    "use strict";

    if (window.AlmdinaPieceMirroringUX) return;

    const FIELDNAME = "allow_piece_mirroring";
    const OPTIONS = Object.freeze([
        Object.freeze({ value: "1", label: "Yes" }),
        Object.freeze({ value: "0", label: "No" }),
    ]);

    function fieldNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict[FIELDNAME];
        const wrapper = field && (field.$wrapper || field.wrapper);
        if (!wrapper) return null;
        return wrapper.nodeType ? wrapper : wrapper[0] || null;
    }

    function storedChoice(frm) {
        const value = frm && frm.doc ? frm.doc[FIELDNAME] : 0;
        if (value === 1 || value === true) return "1";
        const text = String(value == null ? "" : value).trim().toLowerCase();
        if (text === "1" || text === "true" || text === "allowed") return "1";
        return "0";
    }

    function isEditable(frm) {
        if (!frm || !frm.doc) return false;
        if (frm.is_new && frm.is_new()) return true;
        const api = window.AlmdinaOrderRevisionUX;
        if (api && typeof api.isEditableDraft === "function") {
            return Boolean(api.isEditableDraft(frm));
        }
        return false;
    }

    function watchWrapper(frm, wrapper) {
        if (!wrapper || wrapper.__dcoMirroringWatch) return;
        wrapper.__dcoMirroringWatch = true;
        const observer = new MutationObserver(() => {
            if (!wrapper.isConnected) return;
            if (wrapper.querySelector(".dco-piece-mirroring-radios")) return;
            schedule(frm);
        });
        observer.observe(wrapper, { childList: true, subtree: true });
    }

    function ensureRadios(frm) {
        const wrapper = fieldNode(frm);
        if (!wrapper) return null;
        wrapper.classList.add("dco-piece-mirroring-host");
        watchWrapper(frm, wrapper);
        let row = wrapper.querySelector(".dco-piece-mirroring-row");
        if (!row) {
            row = document.createElement("div");
            row.className = "dco-piece-mirroring-row";
            const caption = document.createElement("span");
            caption.className = "dco-piece-mirroring-caption";
            const group = document.createElement("div");
            group.className = "dco-piece-mirroring-radios";
            group.setAttribute("role", "radiogroup");
            group.setAttribute("aria-label", __("Mirrorable"));
            OPTIONS.forEach((option) => {
                const label = document.createElement("label");
                label.className = "dco-piece-mirroring-option";
                const input = document.createElement("input");
                input.type = "radio";
                input.name = "dco-allow-piece-mirroring";
                input.value = option.value;
                const text = document.createElement("span");
                text.textContent = __(option.label);
                label.appendChild(input);
                label.appendChild(text);
                group.appendChild(label);
            });
            group.addEventListener("change", (event) => {
                const active = window.cur_frm || frm;
                const input = event.target;
                if (!input || input.type !== "radio" || !isEditable(active)) return;
                const next = input.value === "1" ? 1 : 0;
                if (storedChoice(active) === String(next)) return;
                active.set_value(FIELDNAME, next);
            });
            row.appendChild(caption);
            row.appendChild(group);
            wrapper.appendChild(row);
        }
        const caption = row.querySelector(".dco-piece-mirroring-caption");
        const labelArea = wrapper.querySelector(".label-area");
        const label = String((labelArea && labelArea.textContent) || "").trim() || __("Mirrorable");
        if (caption && caption.textContent !== label) caption.textContent = label;
        const nativeInput = wrapper.querySelector("input[type='checkbox']");
        if (nativeInput) {
            nativeInput.tabIndex = -1;
            nativeInput.setAttribute("aria-hidden", "true");
        }
        return row.querySelector(".dco-piece-mirroring-radios");
    }

    function syncRadios(frm) {
        const group = ensureRadios(frm);
        if (!group) return;
        const selected = storedChoice(frm);
        const editable = isEditable(frm);
        group.querySelectorAll("input[type='radio']").forEach((input) => {
            input.checked = input.value === selected;
            input.disabled = !editable;
            const option = input.closest(".dco-piece-mirroring-option");
            if (option) option.classList.toggle("is-selected", input.checked);
        });
    }

    function apply(frm) {
        if (!frm || !frm.fields_dict || !frm.fields_dict[FIELDNAME]) return;
        syncRadios(frm);
    }

    function schedule(frm) {
        const run = () => apply(frm);
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "piece-mirroring", run);
            return;
        }
        requestAnimationFrame(() => {
            if (window.cur_frm === frm) run();
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        after_save(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        allow_piece_mirroring(frm) { schedule(frm); },
    });

    window.AlmdinaPieceMirroringUX = Object.freeze({
        apply,
        schedule,
    });
})();
