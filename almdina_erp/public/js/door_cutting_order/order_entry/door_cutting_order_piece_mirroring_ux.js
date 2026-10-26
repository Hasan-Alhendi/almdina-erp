(() => {
    "use strict";

    if (window.AlmdinaPieceMirroringUX) return;

    const FIELDNAME = "allow_piece_mirroring";
    const NOT_ALLOWED = "not_allowed";
    const ALLOWED = "allowed";
    const QUESTION = "Does this board type allow piece mirroring?";
    const OPTIONS = Object.freeze([
        Object.freeze({ value: NOT_ALLOWED, label: "No, mirroring is not allowed" }),
        Object.freeze({ value: ALLOWED, label: "Yes, mirroring is allowed" }),
    ]);

    function fieldNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict[FIELDNAME];
        const wrapper = field && (field.$wrapper || field.wrapper);
        if (!wrapper) return null;
        return wrapper.nodeType ? wrapper : wrapper[0] || null;
    }

    function storedValue(frm) {
        return String((frm && frm.doc && frm.doc[FIELDNAME]) || "").trim();
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

    function hostOf(wrapper) {
        return wrapper.querySelector(".form-group") || wrapper;
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
        const host = hostOf(wrapper);
        let group = wrapper.querySelector(".dco-piece-mirroring-radios");
        if (!group) {
            group = document.createElement("div");
            group.className = "dco-piece-mirroring-radios";
            group.setAttribute("role", "radiogroup");
            group.setAttribute("aria-label", __(QUESTION));
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
                const next = String(input.value || "").trim();
                if (next !== NOT_ALLOWED && next !== ALLOWED) return;
                if (storedValue(active) === next) return;
                active.set_value(FIELDNAME, next);
            });
            host.appendChild(group);
        }
        return group;
    }

    function syncRadios(frm) {
        const group = ensureRadios(frm);
        if (!group) return;
        const value = storedValue(frm);
        const selected = value === ALLOWED ? ALLOWED : (value === NOT_ALLOWED || !value ? NOT_ALLOWED : "");
        const editable = isEditable(frm);
        group.querySelectorAll("input[type='radio']").forEach((input) => {
            input.checked = Boolean(selected) && input.value === selected;
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
        NOT_ALLOWED,
        ALLOWED,
    });
})();
