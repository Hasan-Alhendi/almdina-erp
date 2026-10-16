(() => {
    "use strict";

    if (window.AlmdinaPlanContentUX) return;

    const ZERO_MARGIN_EPSILON_MM = 0.001;
    // Compatibility: historical rendered plan headers. Used only to detect and remove legacy duplicates.
    const LEGACY_HEADER_ORDER = "الطلب:";
    const LEGACY_HEADER_CUSTOMER = "الزبون:";
    const LEGACY_HEADER_BOARD = "اللوح:";
    const LEGACY_HEADER_ITEM = "الصنف:";
    const LEGACY_HEADER_FULL_BOARD_SIZE = "مقاس اللوح الكامل";
    const LEGACY_HEADER_KERF = "سماكة القص";
    const LEGACY_METHOD_LABEL = "طريقة الترتيب:";

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

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function styles() {
        const owner = window.AlmdinaPlanContentStyles;
        if (!owner || typeof owner.install !== "function") {
            throw new Error("AlmdinaPlanContentStyles must load before AlmdinaPlanContentUX");
        }
        return owner;
    }

    function boardPresenter() {
        const presenter = window.AlmdinaPlanBoardPresenter;
        if (
            !presenter
            || typeof presenter.layoutBoardGallery !== "function"
            || typeof presenter.installInteractions !== "function"
        ) {
            throw new Error("AlmdinaPlanBoardPresenter must load before AlmdinaPlanContentUX");
        }
        return presenter;
    }

    function capture(frm) {
        const context = documentContext();
        return context && typeof context.capture === "function"
            ? context.capture(frm)
            : `${frm.doctype || ""}::${frm.doc && frm.doc.name || "__new__"}`;
    }

    function isCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return Boolean(window.cur_frm === frm);
    }

    function tokenKey(token) {
        if (!token || typeof token !== "object") return String(token || "");
        return `${String(token.identity || "")}::${Number(token.generation || 0)}`;
    }

    function scheduleFrame(frm, key, callback) {
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, key, callback);
        }
        const token = capture(frm);
        return window.requestAnimationFrame(() => {
            if (isCurrent(frm, token)) callback(frm, token);
        });
    }

    function schedule(frm, key, callback, delay) {
        const context = documentContext();
        if (context && typeof context.schedule === "function") {
            return context.schedule(frm, key, callback, delay);
        }
        const token = capture(frm);
        return window.setTimeout(() => {
            if (isCurrent(frm, token)) callback(frm, token);
        }, delay);
    }

    function sectionElement(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        if (!field || !field.$wrapper) return $();
        const section = field.$wrapper.closest(".form-section");
        return section.length ? section : field.$wrapper;
    }

    function installStyles() {
        styles().install();
    }

    function applyArabicPlanLabels(frm) {
        const labels = {
            cut_geometry_section: translate("Cut execution settings"),
            optimizer_section: translate("Cutting plan engine"),
            plan_result_section: translate("Current plan result"),
            plan_section: translate("Piece layout on boards"),
            totals_section: translate("Calculation and cost details"),
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.fields_dict[fieldname];
            if (field && field.df && field.df.label !== label) {
                frm.set_df_property(fieldname, "label", label);
            }
        });
    }

    function stabilizePlanActionsLayout(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const section = sectionElement(frm, "plan_actions_section");
        if (!field || !field.$wrapper || !field.$wrapper.length) return;

        // Keep the control inside Frappe's native layout. Moving a ControlHTML
        // wrapper into an ad-hoc row leaves it detached when Frappe repaints a
        // section, while fields_dict still points at the detached node.
        field.$wrapper.addClass("dco-plan-actions-native");
        if (section.length) section.addClass("dco-plan-actions-section hide-border");
        const layoutSection = sectionElement(frm, "plan_section");
        // Keep layout-card hooks attached so shared plan spacing CSS can target this section
        // even when the lazy Plan UX decorator has not run yet.
        if (layoutSection.length) {
            layoutSection.addClass(
                "hide-border dco-plan-layout-section dco-plan-section-card dco-layout-card"
            );
        }
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function parsePlanSnapshot(frm) {
        if (!frm || !frm.doc) return null;
        const tabs = window.AlmdinaPlanTabsUX;
        const activeTab = frm.__almdina_active_plan_tab;
        if (tabs && activeTab && typeof tabs.displayedPlanForTab === "function") {
            const active = tabs.displayedPlanForTab(frm, activeTab);
            if (active && typeof active === "object") return active;
        }
        const raw = frm.doc.system_plan_json || frm.doc.cutting_plan_json;
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function normalizedMarginNotes(plan) {
        if (!plan || typeof plan !== "object") return [];
        const policy = plan.margin_policy || {};
        const source = Array.isArray(plan.margin_notes)
            ? plan.margin_notes
            : (Array.isArray(policy.notes) ? policy.notes : []);
        return source
            .map(note => String(note || "").trim())
            .filter(Boolean);
    }

    function numericMargin(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function isZeroMargin(value) {
        const numeric = numericMargin(value);
        return numeric !== null && Math.abs(numeric) <= ZERO_MARGIN_EPSILON_MM;
    }

    function zeroMarginEdges(policy) {
        const source = policy || {};
        return [
            ["right", source.right_mm],
            ["left", source.left_mm],
            ["top", source.top_mm],
            ["bottom", source.bottom_mm],
        ]
            .filter(([, value]) => isZeroMargin(value))
            .map(([edge]) => edge);
    }

    function renderApi() {
        return window.AlmdinaCuttingPlanRender || null;
    }

    function sheetPhysicalMargins(plan, sheet) {
        const render = renderApi();
        if (!sheet || !render || typeof render.physicalMarginsMm !== "function") return null;
        return render.physicalMarginsMm(plan, sheet);
    }

    function sharedPhysicalMargins(plan) {
        const sheets = ((plan && plan.sheets) || []).filter(sheet => (sheet.pieces || []).length);
        const measured = sheets.map(sheet => sheetPhysicalMargins(plan, sheet)).filter(Boolean);
        if (!measured.length) {
            const policy = (plan && plan.margin_policy) || {};
            return {
                left: policy.left_mm,
                right: policy.right_mm,
                top: policy.top_mm,
                bottom: policy.bottom_mm,
                anyOriginal: zeroMarginEdges(policy).length > 0,
                everySheetOriginal: zeroMarginEdges(policy).length > 0,
            };
        }
        const margins = {};
        ["left", "right", "top", "bottom"].forEach(edge => {
            const values = measured.map(row => row[edge]);
            const same = values.every(value => Math.abs(value - values[0]) <= ZERO_MARGIN_EPSILON_MM);
            margins[edge] = same ? values[0] : null;
        });
        const zeroSets = measured.map(row => (
            ["left", "right", "top", "bottom"].filter(edge => isZeroMargin(row[edge])).join("|")
        ));
        margins.anyOriginal = zeroSets.some(value => value.length > 0);
        margins.everySheetOriginal = zeroSets.length > 0
            && zeroSets[0].length > 0
            && zeroSets.every(value => value === zeroSets[0]);
        return margins;
    }

    function marginPolicySignature(plan, notes) {
        return JSON.stringify({
            notes,
            margins: sharedPhysicalMargins(plan),
        });
    }

    function marginEdgeBadges(policy, edges) {
        return edges
            .filter(([, value]) => value !== null && value !== undefined && value !== "")
            .map(([label, value]) => {
                const zeroClass = isZeroMargin(value) ? " is-zero" : "";
                return `<span class="dco-margin-policy-alert__edge${zeroClass}" style="direction:ltr;">${escapeHtml(translate(label))}: ${escapeHtml(translate("{0} mm", [value]))}</span>`;
            })
            .join("");
    }

    function buildMarginPolicyAlert(plan, notes, signature) {
        const margins = sharedPhysicalMargins(plan);
        const hasOriginalEdge = Boolean(margins.anyOriginal);
        const summary = hasOriginalEdge
            ? translate("An original board edge was used; check that it is straight before cutting.")
            : translate("The margin was reduced automatically by the amount needed to keep the piece measurements.");
        const detailNotes = margins.everySheetOriginal ? notes : [];
        const horizontalEdges = marginEdgeBadges(margins, [
            ["Margin right", margins.right],
            ["Margin left", margins.left],
        ]);
        const verticalEdges = marginEdgeBadges(margins, [
            ["Margin top", margins.top],
            ["Margin bottom", margins.bottom],
        ]);
        const detailsHtml = detailNotes.length
            ? `<div class="dco-margin-policy-alert__details">${detailNotes.map(note => `<div class="dco-margin-policy-alert__note">${escapeHtml(note)}</div>`).join("")}</div>`
            : "";
        const alert = document.createElement("div");
        alert.dir = uiDirection();
        alert.className = "dco-margin-policy-alert";
        alert.dataset.marginSignature = signature;
        alert.setAttribute("role", "status");
        alert.setAttribute("aria-live", "polite");
        alert.innerHTML = `
            <span class="dco-margin-policy-alert__icon" aria-hidden="true">⚠</span>
            <div class="dco-margin-policy-alert__body">
                <div class="dco-margin-policy-alert__row">
                    <div class="dco-margin-policy-alert__copy">
                        <strong class="dco-margin-policy-alert__title">${escapeHtml(translate("Trim margin warning"))}</strong>
                        <span class="dco-margin-policy-alert__summary">${escapeHtml(summary)}</span>
                    </div>
                    <div class="dco-margin-policy-alert__edges">${horizontalEdges}</div>
                </div>
                <div class="dco-margin-policy-alert__row">
                    <div class="dco-margin-policy-alert__copy">${detailsHtml}</div>
                    <div class="dco-margin-policy-alert__edges">${verticalEdges}</div>
                </div>
            </div>
        `;
        return alert;
    }

    function ensureMarginPolicyAlert(planRoot, plan) {
        const existing = planRoot.querySelector(":scope > .dco-margin-policy-alert");
        const notes = normalizedMarginNotes(plan);
        if (!notes.length) {
            if (existing) existing.remove();
            return;
        }

        const signature = marginPolicySignature(plan, notes);
        if (existing && existing.dataset.marginSignature === signature) return;

        const alert = buildMarginPolicyAlert(plan, notes, signature);
        if (existing) {
            existing.replaceWith(alert);
            return;
        }

        const firstSheet = planRoot.querySelector(":scope > .dco-sheet-card");
        const gallery = planRoot.querySelector(":scope > .dco-board-gallery");
        const anchor = firstSheet || gallery;
        if (anchor) {
            planRoot.insertBefore(alert, anchor);
        } else {
            planRoot.appendChild(alert);
        }
    }

    function originalEdgeLabel(edge) {
        const labels = {
            right: "Original edge · right",
            left: "Original edge · left",
            top: "Original edge · top",
            bottom: "Original edge · bottom",
        };
        return translate(labels[edge] || "Original edge");
    }

    function orderedOriginalEdges(edges) {
        const present = new Set(edges || []);
        return ["top", "bottom", "right", "left"].filter(edge => present.has(edge));
    }

    function buildOriginalEdgeCaption(edges) {
        const ordered = orderedOriginalEdges(edges);
        const caption = document.createElement("div");
        caption.className = "dco-board-original-edges";
        caption.setAttribute("aria-hidden", "true");
        ordered.forEach(edge => {
            const marker = document.createElement("span");
            marker.className = `dco-board-original-edge dco-board-original-edge--${edge}`;
            marker.textContent = originalEdgeLabel(edge);
            caption.appendChild(marker);
        });
        return caption;
    }

    function originalEdgesForSheet(plan, sheet) {
        const render = renderApi();
        if (sheet && render && typeof render.originalEdges === "function") {
            return render.originalEdges(plan, sheet);
        }
        return zeroMarginEdges((plan && plan.margin_policy) || {});
    }

    function ensureOriginalBoardEdges(planRoot, plan) {
        const sheets = (plan && plan.sheets) || [];
        const cards = [...planRoot.querySelectorAll(".dco-sheet-card")];
        cards.forEach((card, index) => {
            const board = card.querySelector(":scope > .dco-sheet-board");
            if (!board) return;
            const edges = originalEdgesForSheet(plan, sheets[index]);
            const signature = edges.join("|");
            const caption = card.querySelector(":scope > .dco-board-original-edges");
            if (board.dataset.originalEdgeSignature === signature && (!edges.length || caption)) return;
            if (caption) caption.remove();
            board.querySelectorAll(":scope > .dco-board-original-edge").forEach(marker => marker.remove());
            if (edges.length) card.insertBefore(buildOriginalEdgeCaption(edges), board);
            board.dataset.originalEdgeSignature = signature;
        });
    }

    function cleanRenderedPlan(frm) {
        const token = capture(frm);
        if (!isCurrent(frm, token)) return false;
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return false;
        const root = field.$wrapper.get(0);
        if (!root) return false;
        root.dataset.almdinaOrder = String(frm.doc && frm.doc.name || "");

        const plan = parsePlanSnapshot(frm);
        const presenter = boardPresenter();
        root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
            const heading = planRoot.querySelector(":scope > h2");
            if (heading) heading.remove();

            planRoot.querySelectorAll(
                ":scope > .dco-plan-header-cards, :scope > .dco-summary-grid, :scope > .dco-piece-groups"
            ).forEach(el => el.remove());

            [...planRoot.children].forEach(child => {
                if (!(child instanceof HTMLElement)) return;
                if (child.classList.contains("dco-sheet-card")) return;
                if (child.classList.contains("dco-board-gallery")) return;
                if (child.classList.contains("dco-plan-meta-strip")) return;
                if (child.classList.contains("dco-special-raw-coverage")) return;
                if (child.classList.contains("dco-margin-policy-alert")) return;
                const text = (child.textContent || "").replace(/\s+/g, " ").trim();
                const isDuplicatedHeader =
                    (text.includes(LEGACY_HEADER_ORDER) && (text.includes(LEGACY_HEADER_CUSTOMER) || text.includes(LEGACY_HEADER_BOARD) || text.includes(LEGACY_HEADER_ITEM))) ||
                    (text.includes(LEGACY_HEADER_FULL_BOARD_SIZE) && text.includes(LEGACY_HEADER_KERF));
                const isMethodDuplicate = child.classList.contains("dco-plan-method-line")
                    || text.includes("Layout method:")
                    || text.includes(LEGACY_METHOD_LABEL);
                if (isDuplicatedHeader || isMethodDuplicate) child.remove();
            });

            ensureMarginPolicyAlert(planRoot, plan);
            presenter.layoutBoardGallery(planRoot);
            ensureOriginalBoardEdges(planRoot, plan);
        });

        root.querySelectorAll(
            ".dco-drawing-plan-panel-host, .dco-drawing-plan-panel"
        ).forEach(el => el.remove());
        presenter.installInteractions(root);
        return true;
    }

    function isReady(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const root = field && field.$wrapper && field.$wrapper.get(0);
        const orderName = String(frm && frm.doc && frm.doc.name || "");
        if (!root || root.dataset.almdinaOrder !== orderName) return false;
        const planRoots = [...root.querySelectorAll(".dco-cutting-plan")];
        return planRoots.every(planRoot => {
            if (String(planRoot.getAttribute("data-almdina-order") || "") !== orderName) {
                return false;
            }
            const directCards = planRoot.querySelectorAll(":scope > .dco-sheet-card");
            if (directCards.length) return false;
            const cards = planRoot.querySelectorAll(".dco-sheet-card");
            if (cards.length && !planRoot.querySelector(":scope > .dco-board-gallery")) return false;
            return ![...planRoot.children].some(child =>
                child.classList.contains("dco-plan-method-line")
                || String(child.textContent || "").replace(/\s+/g, " ").includes("Layout method:")
                || String(child.textContent || "").replace(/\s+/g, " ").includes(LEGACY_METHOD_LABEL)
            );
        });
    }

    function installObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;
        const identity = capture(frm);
        const identityKey = tokenKey(identity);
        if (
            root._dcoPlanContentObserver
            && root._dcoPlanContentObserverIdentity === identityKey
        ) return;
        if (root._dcoPlanContentObserver) root._dcoPlanContentObserver.disconnect();

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (!isCurrent(frm, identity)) return;
            if (scheduled) return;
            scheduled = true;
            scheduleFrame(frm, "plan-content-observer-frame", () => {
                scheduled = false;
                cleanRenderedPlan(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoPlanContentObserver = observer;
        root._dcoPlanContentObserverIdentity = identityKey;
        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "plan-content-observer", observer);
        }
    }

    function installResizeObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;
        const identity = capture(frm);
        const identityKey = tokenKey(identity);
        if (
            root._dcoPlanContentResizeObserver
            && root._dcoPlanContentResizeObserverIdentity === identityKey
        ) return;
        if (root._dcoPlanContentResizeObserver) root._dcoPlanContentResizeObserver.disconnect();

        let scheduled = false;
        const relayout = () => {
            if (!isCurrent(frm, identity)) return;
            if (scheduled) return;
            scheduled = true;
            scheduleFrame(frm, "plan-content-resize-frame", () => {
                scheduled = false;
                root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
                    boardPresenter().layoutBoardGallery(planRoot);
                });
            });
        };

        if (typeof ResizeObserver === "function") {
            const observer = new ResizeObserver(relayout);
            observer.observe(root);
            root._dcoPlanContentResizeObserver = observer;
            const context = documentContext();
            if (context && typeof context.registerObserver === "function") {
                context.registerObserver(frm, "plan-content-resize-observer", observer);
            }
        } else {
            window.addEventListener("resize", relayout);
            const fallback = { disconnect() { window.removeEventListener("resize", relayout); } };
            root._dcoPlanContentResizeObserver = fallback;
            const context = documentContext();
            if (context && typeof context.registerObserver === "function") {
                context.registerObserver(frm, "plan-content-resize-observer", fallback);
            }
        }
        root._dcoPlanContentResizeObserverIdentity = identityKey;
    }

    function apply(frm) {
        const identity = capture(frm);
        if (!isCurrent(frm, identity)) return false;
        installStyles();
        applyArabicPlanLabels(frm);
        stabilizePlanActionsLayout(frm);
        cleanRenderedPlan(frm);
        installObserver(frm);
        installResizeObserver(frm);
        scheduleFrame(frm, "plan-content-apply-frame", () => {
            stabilizePlanActionsLayout(frm);
            cleanRenderedPlan(frm);
        });
        schedule(frm, "plan-content-apply-delay", () => {
            stabilizePlanActionsLayout(frm);
            cleanRenderedPlan(frm);
        }, 350);
        return isReady(frm);
    }

    window.AlmdinaPlanContentUX = Object.freeze({
        apply,
        cleanRenderedPlan,
        isReady,
        parsePlanSnapshot,
    });

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { apply(frm); },
        refresh(frm) { apply(frm); },
        cutting_plan_json(frm) { apply(frm); },
        packing_mode(frm) { scheduleFrame(frm, "plan-content-packing-mode", () => stabilizePlanActionsLayout(frm)); },
        optimization_time_limit_sec(frm) { scheduleFrame(frm, "plan-content-optimizer-time", () => stabilizePlanActionsLayout(frm)); },
        refresh_plan_controls(frm) { scheduleFrame(frm, "plan-content-refresh-controls", () => apply(frm)); },
    });

    if (window && typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") apply(frm);
        });
    }
})();
