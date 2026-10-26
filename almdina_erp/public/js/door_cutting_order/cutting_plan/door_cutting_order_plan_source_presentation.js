(() => {
    "use strict";

    if (window.AlmdinaPlanSourcePresentation) return;

    const RESOURCE_FULL_BOARD = "FULL_BOARD";
    const RESOURCE_OFFCUT = "OFFCUT";
    const SUPPORTED_OFFCUT_STATES = new Set([
        "UNASSIGNED",
        "CUSTOMER_FACTORY",
        "CUSTOMER_CUSTOMER",
        "FACTORY_FACTORY",
    ]);
    const UNASSIGNED_LABEL = "Unassigned";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function resourceKind(source) {
        const value = String((source && source.resource_kind) || RESOURCE_FULL_BOARD)
            .trim()
            .toUpperCase();
        return value === RESOURCE_OFFCUT ? RESOURCE_OFFCUT : RESOURCE_FULL_BOARD;
    }

    function positiveInteger(value) {
        const number = Number(value);
        if (!Number.isInteger(number) || number <= 0) return null;
        return number;
    }

    function assignmentsByPhysicalIdentity(plan) {
        const assignments = Array.isArray(plan && plan.__offcut_assignments)
            ? plan.__offcut_assignments
            : [];
        const byId = new Map();
        assignments.forEach(assignment => {
            const id = String((assignment && assignment.piece_instance_id) || "").trim();
            if (!id) return;
            byId.set(id, assignment);
        });
        return byId;
    }

    function canonicalAssignmentLabel(assignment) {
        if (!assignment) return translate(UNASSIGNED_LABEL);
        const state = String(assignment.business_state || "UNASSIGNED").trim().toUpperCase();
        if (!SUPPORTED_OFFCUT_STATES.has(state)) return translate(UNASSIGNED_LABEL);
        if (state === "UNASSIGNED") return translate(UNASSIGNED_LABEL);
        const label = String(assignment.business_state_label || "").trim();
        return label || translate(UNASSIGNED_LABEL);
    }

    function offcutContextLabels(source, assignmentIndex) {
        const labels = [];
        const seen = new Set();
        const pieces = Array.isArray(source && source.pieces) ? source.pieces : [];
        pieces.forEach(piece => {
            const id = String((piece && piece.piece_instance_id) || "").trim();
            const label = canonicalAssignmentLabel(id ? assignmentIndex.get(id) : null);
            if (!seen.has(label)) {
                seen.add(label);
                labels.push(label);
            }
        });
        if (!labels.length) labels.push(translate(UNASSIGNED_LABEL));
        return labels;
    }

    function project(plan) {
        const sources = Array.isArray(plan && plan.sheets) ? plan.sheets : [];
        const assignmentIndex = assignmentsByPhysicalIdentity(plan);
        let visibleBoardIndex = 0;

        return sources.map((source, sourceIndex) => {
            const kind = resourceKind(source);
            const isOffcut = kind === RESOURCE_OFFCUT;
            let fullBoardNo = null;
            if (!isOffcut) {
                visibleBoardIndex += 1;
                fullBoardNo = positiveInteger(source && source.full_board_no) || visibleBoardIndex;
            }
            const pieces = Array.isArray(source && source.pieces) ? source.pieces : [];
            return Object.freeze({
                source_index: sourceIndex,
                resource_kind: kind,
                sheet_no: source ? source.sheet_no : null,
                full_board_no: fullBoardNo,
                primary_label: isOffcut ? translate("Offcut") : translate("Board {0}", [fullBoardNo]),
                business_context_labels: Object.freeze(
                    isOffcut ? offcutContextLabels(source, assignmentIndex) : []
                ),
                piece_instance_ids: Object.freeze(
                    pieces
                        .map(piece => String((piece && piece.piece_instance_id) || "").trim())
                        .filter(Boolean)
                ),
            });
        });
    }

    function contextHtml(sourcePresentation) {
        const labels = sourcePresentation && sourcePresentation.business_context_labels;
        if (!Array.isArray(labels) || !labels.length) return "";
        const content = labels
            .map(label => `<span class="dco-offcut-business-context__state">${escapeHtml(label)}</span>`)
            .join('<span class="dco-offcut-business-context__separator" aria-hidden="true"> · </span>');
        return `<div class="dco-offcut-business-context" dir="${escapeHtml(uiDirection())}" style="font-size:10px;color:#64748b;font-weight:700;line-height:1.35;margin:-3px 0 7px;text-align:start;">${content}</div>`;
    }

    function decorateHtml(html, plan) {
        const projection = project(plan);
        if (!projection.length || !html) return String(html || "");

        let titleIndex = 0;
        let output = String(html).replace(
            /(<div class="dco-sheet-title"[^>]*>\s*<div>)([\s\S]*?)(<\/div>)/g,
            (match, prefix, _current, suffix) => {
                const source = projection[titleIndex++];
                if (!source) return match;
                return `${prefix}${escapeHtml(source.primary_label)}${suffix}`;
            }
        );

        let boardIndex = 0;
        output = output.replace(
            /(<div class="dco-sheet-board"[^>]*>)/g,
            (match) => {
                const source = projection[boardIndex++];
                if (!source) return match;
                return `${contextHtml(source)}${match}`;
            }
        );
        return output;
    }

    function install() {
        const renderer = window.AlmdinaCuttingPlanRender;
        if (!renderer || renderer.__almadina179SourcePresentation) return false;
        if (typeof renderer.build !== "function" || typeof renderer.print !== "function") return false;

        const decorated = {
            ...renderer,
            __almadina179SourcePresentation: true,
            build(frm, plan) {
                return decorateHtml(renderer.build(frm, plan), plan);
            },
            print(frm, planOverride = null, hint = null) {
                // Printing owns the real Form identity and revalidates the Plan
                // Workspace row. A displayed DOM plan is not an owned source.
                // Passing a synthetic Form would fail DocumentContext.isCurrent.
                return renderer.print(frm, planOverride, hint);
            },
        };
        window.AlmdinaCuttingPlanRender = decorated;
        return true;
    }

    window.AlmdinaPlanSourcePresentation = Object.freeze({
        project,
        decorateHtml,
        install,
    });

    install();
})();
