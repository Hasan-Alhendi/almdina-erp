(() => {
    "use strict";

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
                text = text.split("{" + index + "}").join(String(value));
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


    const STYLE_ASSETS = Object.freeze([
        ["/assets/almdina_erp/css/factory_routing_workflow.css", "almdina-routing-workflow-style"],
        ["/assets/almdina_erp/css/factory_stage_library.css", "almdina-stage-library-style"],
    ]);
    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js?v=2";
    const DESIGN_SYSTEM = "/assets/almdina_erp/js/almdina_ui.js?v=2";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
    const METHODS = Object.freeze({
        load: "almdina_erp.almdina_erp.services.master_data_service.get_production_routing_console",
        save: "almdina_erp.almdina_erp.services.master_data_service.save_production_routing",
        toggle: "almdina_erp.almdina_erp.services.master_data_service.set_production_routing_disabled",
        remove: "almdina_erp.almdina_erp.services.master_data_service.delete_production_routing",
        saveStage: "almdina_erp.almdina_erp.services.master_data_service.save_production_stage_definition",
        toggleStage: "almdina_erp.almdina_erp.services.master_data_service.set_production_stage_definition_disabled",
        removeStageDefinition: "almdina_erp.almdina_erp.services.master_data_service.delete_production_stage_definition",
    });

    function bootstrapLoadingHtml() {
        return `
            <div class="prw-loading" data-almdina-loading-owner="factory-master-data-bootstrap" role="status" aria-live="polite">
                <span class="prw-spinner"></span>${translate("Loading production routes...")}
            </div>`;
    }

    class ProductionRoutingWorkflowPage {
        constructor(wrapper, page) {
            this.wrapper = wrapper;
            this.page = page;
            this.$main = $(wrapper).find(".layout-main-section");
            this.state = {
                data: null,
                section: "routings",
                search: "",
                status: "all",
                editor: null,
                saving: false,
                draggedStageId: null,
            };
            this.stageCounter = 0;
            this.editorCounter = 0;
            this.frontend = null;
            this.activation = null;
            this.lifecycle = null;
            this.readGate = null;
            this.mutationGate = null;
            this.libraryMutationGate = null;
            this.libraryMutationPending = null;
            this.initialized = false;
            this.disposed = false;
            this.bootstrapReady = false;
            this.bootstrapError = null;
            this.bootstrapRetry = null;
            this.bootstrapLoadingOwned = true;
            this.reconciliationPending = false;
            this.completedSave = null;
            this.pendingSave = null;
            this.ownedTransients = new Set();
            this.$refreshButton = null;
            this.toolbarControls = null;
            this.toolbarMounted = false;
            this.stageControls = null;
        }

        init() {
            if (this.initialized || this.disposed) return this;
            this.page.set_primary_action(translate("New production route"), () => this.openEditor(), "add");
            this.syncPrimaryAction();
            this.$refreshButton = this.page.add_inner_button(
                translate("Refresh"),
                () => this.refresh(),
                null,
                "refresh"
            );
            this.initialized = true;
            return this;
        }

        isOwner() {
            return !this.disposed && this.wrapper.__almdinaRoutingWorkflowPage === this;
        }

        isHostCurrent() {
            return Boolean(frappe.container && frappe.container.page === this.wrapper);
        }

        isActive() {
            return Boolean(this.isOwner() && this.activation && this.activation.isActive());
        }

        activeGeneration() {
            return this.isActive() ? this.activation.generation() : null;
        }

        isCurrentGeneration(generation) {
            return generation !== null
                && this.isActive()
                && this.activation.generation() === generation;
        }

        mount(frontend, lifecycleModule) {
            if (this.disposed || this.activation) return !this.disposed;
            if (
                !frontend
                || typeof frontend.createLatestRequestGate !== "function"
                || typeof frontend.createLifecycleScope !== "function"
                || !lifecycleModule
                || typeof lifecycleModule.bindActivationLifecycle !== "function"
            ) {
                throw new Error("Factory master data lifecycle dependencies are unavailable");
            }
            this.frontend = frontend;
            this.readGate = frontend.createLatestRequestGate();
            this.mutationGate = frontend.createLatestRequestGate();
            this.libraryMutationGate = frontend.createLatestRequestGate();
            this.lifecycle = frontend.createLifecycleScope();
            this.lifecycle.track(() => this.disposeToolbarControls(), "factory-master-data-toolbar-owner");
            this.lifecycle.track(() => this.disposeStageControls(), "factory-master-data-stage-owner");
            this.activation = lifecycleModule.bindActivationLifecycle(this.wrapper, {
                onActivate: () => this.activatePage(),
                onDeactivate: () => this.deactivatePage(),
            });
            if (!this.activation) throw new Error("Factory master data activation owner is unavailable");
            this.lifecycle.track(() => this.activation.dispose(), "factory-master-data-page-activation");
            $(this.wrapper).off(".prw-bootstrap-owner");
            if (this.activation.isActive()) this.activatePage();
            return true;
        }

        activatePage() {
            if (!this.isActive()) return Promise.resolve(null);
            if (!this.bootstrapReady) {
                if (this.bootstrapError) this.renderBootstrapError();
                return Promise.resolve(null);
            }
            this.init();
            const editor = this.state.editor;
            if (this.state.saving) {
                if (editor) this.renderEditor();
                return this.waitForSaveSettlement(this.activeGeneration());
            }
            if (editor && editor.dirty) {
                const completed = this.completedSave;
                if (
                    completed
                    && completed.workingId === editor.workingId
                    && completed.revision === editor.revision
                ) {
                    this.state.editor = null;
                    this.completedSave = null;
                    return this.load({discardEditor: true});
                }
                this.renderEditor();
                return Promise.resolve(null);
            }
            return this.load();
        }

        waitForSaveSettlement(generation) {
            const pending = this.pendingSave;
            if (!pending) return Promise.resolve(null);
            return Promise.resolve(pending).then(() => {
                if (!this.isCurrentGeneration(generation)) return null;
                const editor = this.state.editor;
                const completed = this.completedSave;
                if (
                    editor
                    && completed
                    && completed.workingId === editor.workingId
                    && completed.revision === editor.revision
                ) {
                    this.state.editor = null;
                    this.completedSave = null;
                    return this.load({discardEditor: true});
                }
                if (editor) this.renderEditor();
                else if (this.reconciliationPending) return this.reconcileWhenSafe();
                return null;
            });
        }

        deactivatePage() {
            if (this.readGate) this.readGate.invalidate();
            this.disposeToolbarControls();
            this.disposeStageControls();
            this.closeTransientSurfaces();
            this.clearDragState();
        }

        clearDragState() {
            this.state.draggedStageId = null;
            this.$main.find(".prw-story-row").removeClass("is-drag-over is-dragging");
        }

        completeBootstrap() {
            if (!this.isOwner()) return Promise.resolve(null);
            this.bootstrapReady = true;
            this.bootstrapError = null;
            this.bootstrapRetry = null;
            this.$main.off(".prw-bootstrap");
            $(this.wrapper).off(".prw-bootstrap-owner");
            return this.isActive() ? this.activatePage() : Promise.resolve(null);
        }

        restartBootstrap() {
            if (!this.isOwner()) return;
            this.bootstrapReady = false;
            this.bootstrapError = null;
            this.bootstrapRetry = null;
            const current = this.activation ? this.isActive() : this.isHostCurrent();
            if (current) {
                this.bootstrapLoadingOwned = true;
                this.$main.html(bootstrapLoadingHtml());
            }
        }

        failBootstrap(error, retry) {
            if (!this.isOwner()) return;
            this.bootstrapReady = false;
            this.bootstrapError = error;
            this.bootstrapRetry = retry;
            if (this.isActive() || (!this.activation && this.isHostCurrent())) {
                this.renderBootstrapError();
            }
        }

        renderBootstrapError() {
            const current = this.activation ? this.isActive() : this.isHostCurrent();
            if (!this.isOwner() || !current || !this.bootstrapError) return;
            const fallback = translate("Could not load the production route management layout.");
            const message = this.frontend && typeof this.frontend.errorMessage === "function"
                ? this.frontend.errorMessage(this.bootstrapError, fallback)
                : fallback;
            this.$main.html(this.errorStateHtml(fallback, message, "prw-bootstrap-retry"));
            this.$main
                .off(".prw-bootstrap")
                .on("click.prw-bootstrap", ".prw-bootstrap-retry", event => {
                    $(event.currentTarget).prop("disabled", true);
                    if (typeof this.bootstrapRetry === "function") this.bootstrapRetry();
                });
        }

        // Error paths must render even if the design-system builder failed to load.
        errorStateHtml(title, message, retryClassName) {
            const ui = window.AlmdinaUi;
            const retryLabel = translate("Retry");
            const retryHtml = ui && typeof ui.button === "function"
                ? ui.button({
                    label: retryLabel,
                    variant: "secondary",
                    className: retryClassName,
                })
                : `<button type="button" class="btn alm-btn-secondary ${retryClassName}">${this.esc(retryLabel)}</button>`;
            if (ui && typeof ui.state === "function") {
                return `<div class="almdina-ui">${ui.state({
                    kind: "error",
                    title,
                    message,
                    actionHtml: retryHtml,
                })}</div>`;
            }
            return `
                <div class="almdina-ui">
                    <div class="alm-state alm-state--error" role="alert">
                        <strong class="alm-state__title">${this.esc(title)}</strong>
                        <span class="alm-state__message">${this.esc(message)}</span>
                        <div class="alm-state__action">${retryHtml}</div>
                    </div>
                </div>`;
        }

        dispose() {
            if (this.disposed) return false;
            this.disposed = true;
            this.disposeToolbarControls();
            this.disposeStageControls();
            if (this.readGate) this.readGate.invalidate();
            if (this.mutationGate) this.mutationGate.invalidate();
            if (this.libraryMutationGate) this.libraryMutationGate.invalidate();
            this.libraryMutationPending = null;
            this.closeTransientSurfaces();
            this.clearDragState();
            this.$main.off(".prw").off(".prw-bootstrap");
            $(this.wrapper).off(".prw-bootstrap-owner");
            if (this.lifecycle) this.lifecycle.dispose();
            else if (this.activation) this.activation.dispose();
            if (this.$refreshButton && typeof this.$refreshButton.remove === "function") {
                this.$refreshButton.remove();
            }
            if (this.wrapper.__almdinaRoutingWorkflowPage === this) {
                this.wrapper.__almdinaRoutingWorkflowPage = null;
            }
            return true;
        }

        ownTransient(surface) {
            if (surface && typeof surface.hide === "function") this.ownedTransients.add(surface);
            return surface;
        }

        closeTransientSurfaces() {
            for (const surface of this.ownedTransients) surface.hide();
            this.ownedTransients.clear();
        }

        confirmForGeneration(message, generation, onConfirm, onCancel) {
            if (!this.isCurrentGeneration(generation)) return null;
            let surface = null;
            const invoke = callback => () => {
                if (surface) this.ownedTransients.delete(surface);
                if (!this.isCurrentGeneration(generation)) return null;
                return typeof callback === "function" ? callback() : null;
            };
            surface = frappe.confirm(message, invoke(onConfirm), invoke(onCancel));
            return this.ownTransient(surface);
        }

        showMessage(options) {
            if (!this.isActive()) return null;
            return this.ownTransient(frappe.msgprint(options));
        }

        esc(value) {
            const text = value === null || value === undefined ? "" : String(value);
            return frappe.utils && typeof frappe.utils.escape_html === "function"
                ? frappe.utils.escape_html(text)
                : $("<div>").text(text).html();
        }

        uiButton(options = {}) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.button !== "function") {
                throw new Error("AlmdinaUi.button is required for factory master data rendering");
            }
            return ui.button(options);
        }

        // Decorative only: Frappe sprite icons; missing sprite must not break rendering.
        uiIcon(name, size = "sm") {
            if (!frappe.utils || typeof frappe.utils.icon !== "function") return "";
            return frappe.utils.icon(name, size, "", "", "", true);
        }

        uiBadge(options = {}) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.badge !== "function") {
                throw new Error("AlmdinaUi.badge is required for factory master data rendering");
            }
            return ui.badge(options);
        }

        uiStatus(options = {}) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.status !== "function") {
                throw new Error("AlmdinaUi.status is required for factory master data rendering");
            }
            return ui.status(options);
        }

        uiControl(options = {}) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.control !== "function") {
                throw new Error("AlmdinaUi.control is required for factory master data rendering");
            }
            return ui.control(options);
        }

        uiFilterGroup(options = {}) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.filterGroup !== "function") {
                throw new Error("AlmdinaUi.filterGroup is required for factory master data rendering");
            }
            return ui.filterGroup(options);
        }

        statusFilterLabel(value) {
            const labels = {
                all: translate("All"),
                active: translate("Enabled"),
                disabled: translate("Disabled"),
            };
            return labels[String(value || "all")] || labels.all;
        }

        statusFilterValue(label) {
            const entries = [
                ["all", translate("All")],
                ["active", translate("Enabled")],
                ["disabled", translate("Disabled")],
            ];
            const match = entries.find(([, text]) => text === label);
            return match ? match[0] : "all";
        }

        statusFilterOptions() {
            return [translate("All"), translate("Enabled"), translate("Disabled")].join("\n");
        }

        disposeToolbarControls() {
            if (!this.toolbarControls) return;
            this.toolbarControls.dispose();
            this.toolbarControls = null;
            this.toolbarMounted = false;
        }

        disposeStageControls() {
            if (!this.stageControls) return;
            for (const control of this.stageControls) {
                if (control && typeof control.dispose === "function") control.dispose();
            }
            this.stageControls = null;
        }

        operationalRoleControlOptions($parent, stage) {
            const readOnly = Boolean(this.state.editor && this.state.editor.readOnly);
            return {
                parent: $parent,
                fieldname: "operational_role",
                fieldtype: "Link",
                options: "Role",
                placeholder: translate("Select role"),
                value: stage.operational_role || "",
                readOnly,
                required: !readOnly,
                onlyInput: true,
                className: "prw-stage-role-control",
                df: {
                    get_query: () => ({
                        query: "almdina_erp.almdina_erp.services.master_data_service.search_operational_roles",
                    }),
                },
                onChange: value => this.updateStageOperationalRole(stage.clientId, value),
            };
        }

        mountStageControls() {
            this.disposeStageControls();
            const editor = this.state.editor;
            if (!editor) return;
            const $mounts = this.$main.find(".prw-stage-role-mount");
            if (!$mounts.length) return;
            const controls = [];
            $mounts.each((_, element) => {
                const $mount = $(element);
                const stageId = String($mount.data("stageId") || "");
                const stage = editor.stages.find(row => row.clientId === stageId);
                if (!stage) return;
                controls.push(this.uiControl(this.operationalRoleControlOptions($mount, stage)));
            });
            this.stageControls = controls;
        }

        updateStageOperationalRole(stageId, value) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const stage = this.state.editor.stages.find(row => row.clientId === stageId);
            if (!stage) return;
            const next = String(value || "");
            if (String(stage.operational_role || "") === next) return;
            stage.operational_role = next;
            this.markDirty();
        }

        toolbarFilterFields() {
            const fields = [{
                fieldname: "search",
                fieldtype: "Data",
                label: translate("Search"),
                placeholder: translate("Search by name, stage, or role..."),
            }];
            if (this.state.section === "routings") {
                fields.push({
                    fieldname: "status",
                    fieldtype: "Select",
                    label: translate("Status"),
                    options: this.statusFilterOptions(),
                });
            }
            return fields;
        }

        toolbarFilterValues() {
            const values = { search: this.state.search || "" };
            if (this.state.section === "routings") {
                values.status = this.statusFilterLabel(this.state.status);
            }
            return values;
        }

        mountToolbarControls() {
            this.disposeToolbarControls();
            const $mount = this.$main.find(".prw-filter-group-mount");
            if (!$mount.length) return;

            const sectionClass = this.state.section === "routings" ? "is-routings" : "is-audit";
            this.toolbarControls = this.uiFilterGroup({
                parent: $mount,
                className: `prw-filter-group ${sectionClass}`,
                fields: this.toolbarFilterFields(),
                values: this.toolbarFilterValues(),
                onChange: (fieldname, value) => {
                    if (fieldname === "search") {
                        this.applyToolbarSearch(String(value || ""));
                        return;
                    }
                    if (fieldname === "status") {
                        this.applyStatusFilter(this.statusFilterValue(String(value || "")));
                    }
                },
            });
            this.toolbarMounted = true;
        }

        syncToolbarControlValues() {
            if (!this.toolbarControls) return;
            this.toolbarControls.setValues(this.toolbarFilterValues());
        }

        focusToolbarSearch() {
            if (this.toolbarControls && typeof this.toolbarControls.focus === "function") {
                this.toolbarControls.focus("search");
            }
        }

        applyToolbarSearch(value) {
            if (!this.isActive()) return;
            this.state.search = String(value || "");
            this.renderOverview({ preserveToolbar: true });
            this.focusToolbarSearch();
        }

        applyStatusFilter(value) {
            if (!this.isActive()) return;
            this.state.status = String(value || "all");
            this.renderOverview({ preserveToolbar: true });
        }

        updateOverviewContent() {
            this.$main.find(".prw-content").html(
                this.state.section === "audit" ? this.auditHtml() : this.routesHtml()
            );
        }

        call(method, args = {}, freezeMessage = "") {
            return frappe.call({
                method,
                args,
                freeze: Boolean(freezeMessage),
                freeze_message: freezeMessage,
            }).then(response => response.message || {});
        }

        can(capability) {
            return Boolean(
                this.state.data
                && this.state.data.permissions
                && this.state.data.permissions[capability]
            );
        }

        syncPrimaryAction() {
            const visible = this.can("create_production_routings") && !this.state.editor;
            if (this.page.btn_primary) this.page.btn_primary.toggle(visible);
        }

        canManageLibrary() {
            return this.can("edit_production_routings");
        }

        beginLibraryMutation(meta) {
            if (this.libraryMutationPending || !this.isActive() || !this.canManageLibrary()) return null;
            const generation = this.activeGeneration();
            const token = this.libraryMutationGate.begin({...meta, generation});
            this.libraryMutationPending = token;
            return {generation, token};
        }

        endLibraryMutation(token) {
            if (this.libraryMutationPending === token) this.libraryMutationPending = null;
        }

        load({discardEditor = false} = {}) {
            if (!this.isActive() || !this.bootstrapReady || this.state.saving) {
                return Promise.resolve(null);
            }
            if (this.state.editor && this.state.editor.dirty && !discardEditor) {
                this.reconciliationPending = true;
                return Promise.resolve(null);
            }
            const generation = this.activeGeneration();
            const token = this.readGate.begin({generation});
            const previousEditor = discardEditor ? null : this.state.editor;
            const bootstrapOwnsLoading = this.bootstrapLoadingOwned;
            this.bootstrapLoadingOwned = false;
            if (!bootstrapOwnsLoading) {
                this.disposeToolbarControls();
                this.disposeStageControls();
                this.$main.html(bootstrapLoadingHtml());
            }
            return this.call(METHODS.load)
                .then(data => {
                    if (!this.isCurrentGeneration(generation) || !this.readGate.isCurrent(token)) return null;
                    this.state.data = data || {};
                    this.state.editor = discardEditor
                        ? null
                        : this.reconcileCleanEditor(previousEditor);
                    this.reconciliationPending = false;
                    this.completedSave = null;
                    if (this.state.editor) this.renderEditor();
                    else this.renderOverview();
                    this.syncPrimaryAction();
                    return this.state.data;
                })
                .catch(error => {
                    if (!this.isCurrentGeneration(generation) || !this.readGate.isCurrent(token)) return null;
                    const message = error && error.message
                        ? error.message
                        : translate("Could not load production routes.");
                    this.disposeToolbarControls();
                    this.disposeStageControls();
                    this.$main.html(this.errorStateHtml(translate("Could not open route management"), message, "prw-retry"));
                    this.bind();
                    return null;
                });
        }

        refresh() {
            if (!this.isActive()) return null;
            if (this.state.editor && this.state.editor.dirty) {
                const generation = this.activeGeneration();
                const workingId = this.state.editor.workingId;
                return this.confirmForGeneration(
                    translate("You have unsaved changes. Do you want to discard them and refresh the page?"),
                    generation,
                    () => {
                        if (!this.state.editor || this.state.editor.workingId !== workingId) return null;
                        this.state.editor = null;
                        this.state.saving = false;
                        return this.load({discardEditor: true});
                    }
                );
            }
            return this.load();
        }

        renderOverview(options = {}) {
            if (options.preserveToolbar === true && this.toolbarMounted) {
                this.updateOverviewContent();
                this.syncToolbarControlValues();
                this.syncPrimaryAction();
                return;
            }
            const data = this.state.data || {};
            const summary = data.summary || {};
            this.disposeToolbarControls();
            this.disposeStageControls();
            this.$main.html(`
                <main class="almdina-ui prw-shell alm-page alm-page--workbench" dir="${uiDirection()}">
                    <section class="prw-hero alm-page-intro alm-page-intro--accented" aria-label="${translate("Overview")}">
                        <div class="prw-hero-badge-cell">
                            <span class="prw-hero-badge">
                                <span class="prw-hero-badge-dot" aria-hidden="true"></span>
                                ${translate("Production Workflow")}
                            </span>
                        </div>
                        <span class="prw-hero-divider" aria-hidden="true"></span>
                        <h2 class="prw-hero-title alm-page-intro__title">${translate("Design the order journey from the first stage to delivery")}</h2>
                        <span class="prw-hero-divider" aria-hidden="true"></span>
                        <p class="prw-hero-desc alm-page-intro__description">${translate("Arrange work stages visually, link each stage to the appropriate operational role, then use the route directly in the production board.")}</p>
                    </section>
                    <section class="prw-summary alm-summary-grid" aria-label="${translate("Production route summary")}">
                        ${this.statHtml(translate("Routes"), summary.routings || 0, "info", "route",
                            summary.routings && summary.active_routings !== undefined
                                ? `${Math.round(((summary.active_routings || 0) / (summary.routings || 1)) * 100)}% ${translate("Active")}`
                                : "")}
                        ${this.statHtml(translate("Enabled routes"), summary.active_routings || 0, "success", "circle-check", translate("Automatically protected"))}
                        ${this.statHtml(translate("Total stages"), summary.total_stages || 0, "neutral", "layers", translate("Roles"))}
                        ${this.statHtml(translate("Orders in production"), summary.in_flight_orders || 0, "warning", "zap", translate("Active now"))}
                    </section>
                    <section class="prw-toolbar alm-toolbar">
                        <div class="prw-view-switch" role="tablist">
                            <button type="button" class="prw-view-tab ${this.state.section === "routings" ? "is-active" : ""}" data-section="routings">${translate("Routes")} (${Number((data.routings || []).length)})</button>
                            <button type="button" class="prw-view-tab ${this.state.section === "audit" ? "is-active" : ""}" data-section="audit">${translate("Change log")}</button>
                        </div>
                        <div class="prw-filter-group-mount"></div>
                    </section>
                    <section class="prw-content">
                        ${this.state.section === "audit" ? this.auditHtml() : this.routesHtml()}
                    </section>
                </main>`);
            this.bind();
            this.mountToolbarControls();
            this.syncPrimaryAction();
        }

        statHtml(label, value, tone, icon = "", hint = "") {
            const iconHtml = icon ? `
                <div class="prw-stat-icon" aria-hidden="true">
                    ${this.uiIcon(icon, "md")}
                </div>` : "";
            const hintHtml = hint ? `<span class="prw-stat-hint">${this.esc(hint)}</span>` : "";
            return `
                <article class="prw-stat alm-summary-card" data-tone="${tone}">
                    ${iconHtml}
                    <div class="prw-stat-body">
                        <span class="prw-stat-label">${this.esc(label)}</span>
                        <div class="prw-stat-value-row">
                            ${hintHtml}<b class="prw-stat-value">${this.esc(String(value))}</b>
                        </div>
                    </div>
                </article>`;
        }

        filteredRoutes() {
            const query = String(this.state.search || "").trim().toLocaleLowerCase();
            return (this.state.data.routings || []).filter(route => {
                if (this.state.status === "active" && route.disabled) return false;
                if (this.state.status === "disabled" && !route.disabled) return false;
                if (!query) return true;
                const haystack = [
                    route.name,
                    route.label,
                    ...(route.stages || []).flatMap(stage => [
                        stage.stage_type,
                        stage.department_label,
                        stage.operational_role,
                    ]),
                ].join(" ").toLocaleLowerCase();
                return haystack.includes(query);
            });
        }

        routesHtml() {
            const routes = this.filteredRoutes();
            if (!routes.length) {
                return `
                    <div class="prw-empty alm-state alm-state--empty" role="status">
                        <span class="prw-empty-icon" aria-hidden="true">⇢</span>
                        <strong class="alm-state__title">${translate("No matching routes")}</strong>
                        <span class="alm-state__message">${translate("Change the search or filter, or create a new route to start organizing the production journey.")}</span>
                    </div>`;
            }
            return `<div class="prw-route-list">${routes.map(route => this.routeCardHtml(route)).join("")}</div>`;
        }

        routeCardHtml(route) {
            const stages = (route.stages || []).filter(stage => stage.required !== false);
            const canEdit = this.can("edit_production_routings");
            const canCreate = this.can("create_production_routings");
            const canDelete = this.can("delete_production_routings");
            const inFlight = Number(route.in_flight_orders || 0);
            const stageFlow = stages.length
                ? stages.map((stage, index) => `
                    <div class="prw-route-stage ${stage.is_planning_stage ? "is-planning" : ""}">
                        <span class="prw-route-stage-number">${index + 1}</span>
                        <div>
                            <b>${this.esc(stage.department_label || stage.stage_type)}</b>
                            <small>${this.esc(stage.operational_role || translate("Without a role"))}</small>
                        </div>
                        ${stage.is_planning_stage ? this.uiBadge({ label: translate("Planning"), tone: "warning", className: "prw-mini-badge" }) : ""}
                    </div>`).join('<span class="prw-flow-arrow" aria-hidden="true">←</span>')
                : `<span class="prw-no-stages">${translate("No effective stages")}</span>`;
            return `
                <article class="prw-route-card" data-route-name="${this.esc(route.name)}">
                    <header class="prw-route-head">
                        <div class="prw-route-head-start">
                            <div class="prw-route-title-line">
                                <h3>${this.esc(route.label)}</h3>
                                ${this.uiStatus({
                                    label: route.disabled ? translate("Disabled") : translate("Enabled"),
                                    tone: route.disabled ? "neutral" : "success",
                                    className: "prw-status",
                                })}
                                ${this.uiBadge({ label: `${stages.length} ${translate("Stages")}`, tone: "info", className: "prw-stage-count-badge" })}
                                ${inFlight ? this.uiBadge({ label: `${inFlight} ${translate("In production")}`, tone: "warning", className: "prw-inflight-badge" }) : ""}
                            </div>
                            <p class="prw-route-id-line">${this.esc(route.name)}</p>
                        </div>
                        <div class="prw-route-counts">
                            <div class="prw-card-actions">
                                ${this.uiButton({
                                    label: canEdit ? translate("Edit Workflow") : translate("Preview"),
                                    variant: "primary",
                                    className: "prw-edit-route",
                                    attrs: { "data-name": route.name },
                                })}
                                ${canDelete ? this.uiButton({
                                    label: translate("Delete"),
                                    variant: "danger",
                                    className: "prw-delete-route",
                                    attrs: {
                                        "data-name": route.name,
                                        "data-modified": route.modified || "",
                                    },
                                }) : ""}
                                ${canCreate ? this.uiButton({
                                    label: translate("Backups"),
                                    variant: "secondary",
                                    className: "prw-duplicate-route",
                                    attrs: { "data-name": route.name },
                                }) : ""}
                                ${canEdit ? this.uiButton({
                                    label: route.disabled ? translate("Enable") : translate("Disable"),
                                    variant: "secondary",
                                    className: "prw-toggle-route",
                                    attrs: {
                                        "data-name": route.name,
                                        "data-disabled": route.disabled ? 0 : 1,
                                        "data-modified": route.modified || "",
                                    },
                                }) : ""}
                            </div>
                        </div>
                    </header>
                    <div class="prw-route-flow" aria-label="${translate("Route stage sequence")}">${stageFlow}</div>
                    <footer class="prw-route-footer">
                        <div class="prw-route-meta">
                            <span>${translate("Last modified")}: <b>${this.esc(route.modified || "—")}</b></span>
                            <span>${translate("By")}: <b>${this.esc(route.modified_by || "—")}</b></span>
                        </div>
                    </footer>
                </article>`;
        }

        auditHtml() {
            const query = String(this.state.search || "").trim().toLocaleLowerCase();
            const rows = (this.state.data.audit || []).filter(row => {
                if (!query) return true;
                return JSON.stringify(row).toLocaleLowerCase().includes(query);
            });
            if (!rows.length) {
                return `<div class="prw-empty alm-state alm-state--empty" role="status"><span class="prw-empty-icon" aria-hidden="true">◷</span><strong class="alm-state__title">${translate("No recorded changes")}</strong><span class="alm-state__message">${translate("Every creation, edit, or deletion of production routes will appear here.")}</span></div>`;
            }
            return `<div class="prw-audit-list">${rows.map(row => `
                <article class="prw-audit-item">
                    <span class="prw-audit-dot" aria-hidden="true"></span>
                    <div class="prw-audit-body">
                        <div><b>${this.esc(row.target_name)}</b><time>${this.esc(row.changed_on)}</time></div>
                        <p>${this.esc(row.action)} · ${translate("By")} ${this.esc(row.changed_by)}</p>
                        ${row.changed_fields ? `<small>${translate("Changed fields")}: ${this.esc(row.changed_fields)}</small>` : ""}
                    </div>
                </article>`).join("")}</div>`;
        }

        newStageId() {
            this.stageCounter += 1;
            return `stage-${Date.now()}-${this.stageCounter}`;
        }

        stageDraft(stage = {}) {
            return {
                clientId: this.newStageId(),
                stage_definition: String(stage.stage_definition || stage.name || ""),
                stage_type: String(stage.stage_type || stage.stage_code || ""),
                department_label: String(stage.department_label || stage.label || stage.stage_label || ""),
                operational_role: String(stage.operational_role || ""),
                is_planning_stage: Boolean(Number(stage.is_planning_stage || 0)),
                notify_whatsapp_on_complete: Boolean(Number(stage.notify_whatsapp_on_complete || 0)),
            };
        }

        nextEditorId() {
            this.editorCounter += 1;
            return `routing-editor-${this.editorCounter}`;
        }

        editorDraft(source = null, {duplicate = false, workingId = ""} = {}) {
            const isNew = !source || duplicate;
            return {
                workingId: workingId || this.nextEditorId(),
                revision: duplicate ? 1 : 0,
                name: isNew ? null : source.name,
                routing_name: source
                    ? `${source.label}${duplicate ? ` - ${translate("Backup")}` : ""}`
                    : "",
                disabled: source ? Boolean(source.disabled) : false,
                expected_modified: isNew ? null : String(source.modified || ""),
                stages: source
                    ? (source.stages || []).filter(stage => stage.required !== false).map(stage => this.stageDraft(stage))
                    : [],
                dirty: Boolean(duplicate),
                readOnly: isNew
                    ? !this.can("create_production_routings")
                    : !this.can("edit_production_routings"),
            };
        }

        reconcileCleanEditor(previousEditor) {
            if (!previousEditor) return null;
            if (previousEditor.dirty) return previousEditor;
            if (!previousEditor.name) return previousEditor;
            const source = (this.state.data.routings || []).find(route => route.name === previousEditor.name);
            return source
                ? this.editorDraft(source, {workingId: previousEditor.workingId})
                : null;
        }

        openEditor(name = null, {duplicate = false} = {}) {
            if (!this.isActive()) return;
            const source = name
                ? (this.state.data.routings || []).find(route => route.name === name)
                : null;
            if (name && !source) {
                frappe.show_alert({message: translate("Could not find the route. Refresh the page."), indicator: "orange"});
                return;
            }
            this.state.editor = this.editorDraft(source, {duplicate});
            this.state.section = "routings";
            this.syncPrimaryAction();
            this.renderEditor();
        }

        renderEditor() {
            const editor = this.state.editor;
            if (!editor) {
                this.renderOverview();
                return;
            }
            this.disposeToolbarControls();
            this.disposeStageControls();
            const title = editor.name ? translate("Edit production route") : translate("Create new production route");
            const readOnly = editor.readOnly;
            this.syncPrimaryAction();
            this.$main.html(`
                <main class="almdina-ui prw-shell prw-editor-shell alm-page alm-page--workbench" dir="${uiDirection()}">
                    <header class="prw-editor-topbar">
                        <div class="prw-editor-heading">
                            <button type="button" class="btn btn-default prw-close-editor" aria-label="${translate("Back")}">→</button>
                            <div>
                                <span class="prw-eyebrow">${translate("Workflow Story")}</span>
                                <h2>${title}</h2>
                                ${editor.name ? `<p>${translate("Fixed identifier")}: ${this.esc(editor.name)}</p>` : `<p>${translate("Add stages in the actual order the order goes through.")}</p>`}
                            </div>
                        </div>
                        <div class="prw-editor-actions">
                            <span class="prw-save-state ${editor.dirty ? "is-dirty" : ""}">${editor.dirty ? translate("Unsaved changes") : translate("No changes")}</span>
                            <button type="button" class="btn btn-default prw-close-editor">${translate("Cancel")}</button>
                            ${readOnly ? "" : this.uiButton({
                                label: this.state.saving ? translate("Saving...") : translate("Save route"),
                                variant: "primary",
                                className: "prw-save-route",
                                disabled: this.state.saving || !editor.dirty,
                            })}
                        </div>
                    </header>
                    <div class="prw-editor-layout">
                        <section class="prw-editor-main">
                            <article class="prw-settings-card">
                                <div class="prw-section-heading">
                                    <div><span>01</span><h3>${translate("Route identity")}</h3></div>
                                    <p>${translate("A clear name shown when the order is sent to production.")}</p>
                                </div>
                                <div class="prw-settings-grid">
                                    <label class="prw-field prw-field-wide">
                                        <span>${translate("Production route name")} <em>*</em></span>
                                        <input class="form-control" data-editor-field="routing_name" value="${this.esc(editor.routing_name)}" placeholder="${translate("Example: Drawing → CNC → Peeling")}" ${readOnly ? "disabled" : ""}>
                                    </label>
                                    <label class="prw-switch-field">
                                        <input type="checkbox" data-editor-field="disabled" ${editor.disabled ? "checked" : ""} ${readOnly ? "disabled" : ""}>
                                        <span class="prw-switch" aria-hidden="true"></span>
                                        <span><b>${translate("Route is disabled")}</b><small>${translate("Not shown when sending a new order")}</small></span>
                                    </label>
                                </div>
                            </article>
                            <article class="prw-workflow-card">
                                <div class="prw-section-heading">
                                    <div><span>02</span><h3>${translate("Production flow story")}</h3></div>
                                    <p>${translate("Each card represents a workstation. The order here is the order that will appear in the production board.")}</p>
                                </div>
                                <div class="prw-workflow-story ${editor.stages.length ? "" : "is-empty"}">
                                    ${editor.stages.length
                                        ? editor.stages.map((stage, index) => this.editorStageHtml(stage, index, readOnly)).join("")
                                        : `<div class="prw-story-empty"><span>＋</span><b>${translate("Start by adding the first stage")}</b><p>${translate("Click any stage in the library to add it to the route immediately.")}</p></div>`}
                                </div>
                            </article>
                        </section>
                        ${this.stageLibraryHtml(readOnly)}
                    </div>
                </main>`);
            this.bind();
            this.mountStageControls();
        }

        stageLibraryHtml(readOnly) {
            const canManage = this.canManageLibrary() && !readOnly;
            const catalog = (this.state.data.stage_catalog || []).filter(stage => canManage || !stage.disabled);
            return `
                <aside class="prw-stage-library" aria-label="${translate("Production stage library")}">
                    <div class="prw-library-heading-row">
                        <div class="prw-section-heading prw-library-heading">
                            <div><span>03</span><h3>${translate("Stage library")}</h3></div>
                            <p>${translate("Click the stage to add it immediately. Stage names and codes are managed from the library only.")}</p>
                        </div>
                        ${canManage ? this.uiButton({
                            label: `＋ ${translate("Add stage")}`,
                            variant: "primary",
                            className: "prw-library-add",
                        }) : ""}
                    </div>
                    <div class="prw-library-list">
                        ${catalog.length
                            ? catalog.map(stage => this.stageLibraryCardHtml(stage, readOnly, canManage)).join("")
                            : `<div class="prw-empty alm-state alm-state--empty" role="status"><strong class="alm-state__title">${translate("Stage library is empty")}</strong><span class="alm-state__message">${canManage ? translate("Add the first stage to start building production routes.") : translate("Ask the route administrator to add stages to the library.")}</span></div>`}
                    </div>
                    <div class="prw-library-tip">
                        <b>${translate("Important rule")}</b>
                        <p>${translate("Only one planning stage can be selected, and it must be the first stage in the route.")}</p>
                    </div>
                </aside>`;
        }

        stageLibraryCardHtml(stage, readOnly, canManage) {
            const disabled = Boolean(stage.disabled);
            const name = this.esc(stage.name || stage.stage_definition || stage.stage_type);
            const clickable = !readOnly && !disabled;
            const roleAttrs = clickable
                ? `role="button" tabindex="0" aria-label="${this.esc(translate("Add the stage") + " " + (stage.label || stage.stage_type))}"`
                : `role="group" aria-disabled="${disabled ? "true" : "false"}"`;
            return `
                <div class="prw-library-card ${disabled ? "is-disabled" : ""}" ${roleAttrs} data-stage-definition="${name}">
                    <div class="prw-library-card-copy">
                        <div class="prw-library-card-title">
                            <b>${this.esc(stage.label || stage.stage_label || stage.stage_type)}</b>
                            <span class="prw-stage-code-chip">${this.esc(stage.stage_type || stage.stage_code || stage.name)}</span>
                            ${stage.planning ? `<span class="prw-stage-status-chip is-planning">${translate("Planning")}</span>` : ""}
                            ${disabled ? `<span class="prw-stage-status-chip is-disabled">${translate("Disabled")}</span>` : ""}
                        </div>
                        ${stage.description ? `<small>${this.esc(stage.description)}</small>` : ""}
                        ${clickable ? `<span class="prw-library-card-add-hint"><span aria-hidden="true">＋</span>${translate("Click to add immediately")}</span>` : ""}
                    </div>
                    ${canManage ? `
                        <div class="prw-library-card-actions" aria-label="${translate("Stage management")}">
                            <button type="button" class="prw-library-action prw-edit-stage-definition" data-name="${name}" title="${translate("Edit")}" aria-label="${translate("Edit stage")}">✎</button>
                            <button type="button" class="prw-library-action prw-toggle-stage-definition" data-name="${name}" data-disabled="${disabled ? 0 : 1}" data-modified="${this.esc(stage.modified || "")}" title="${disabled ? translate("Enable") : translate("Disable")}" aria-label="${disabled ? translate("Enable stage") : translate("Disable stage")}">${disabled ? "▶" : "⊘"}</button>
                            <button type="button" class="prw-library-action is-danger prw-delete-stage-definition" data-name="${name}" data-modified="${this.esc(stage.modified || "")}" title="${translate("Delete")}" aria-label="${translate("Delete stage")}">⌫</button>
                        </div>` : ""}
                </div>`;
        }

        editorStageHtml(stage, index, readOnly) {
            return `
                <div class="prw-story-row" draggable="${readOnly ? "false" : "true"}" data-stage-id="${stage.clientId}">
                    <div class="prw-story-rail">
                        <span>${index + 1}</span>
                        ${index < this.state.editor.stages.length - 1 ? `<i aria-hidden="true"></i>` : ""}
                    </div>
                    <article class="prw-stage-editor ${stage.is_planning_stage ? "is-planning" : ""}">
                        <header>
                            <div class="prw-stage-title">
                                <span class="prw-drag-handle" title="${translate("Drag to reorder")}" aria-hidden="true">⋮⋮</span>
                                <div>
                                    <b>${this.esc(stage.department_label || stage.stage_type || translate("Stage"))}</b>
                                    <small>${stage.is_planning_stage ? translate("Planning stage") : translate("Execution stage")}</small>
                                </div>
                            </div>
                            ${readOnly ? "" : `
                                <div class="prw-stage-actions">
                                    <button type="button" class="prw-icon-btn prw-move-stage" data-direction="-1" data-stage-id="${stage.clientId}" ${index === 0 ? "disabled" : ""} title="${translate("Move up")}">↑</button>
                                    <button type="button" class="prw-icon-btn prw-move-stage" data-direction="1" data-stage-id="${stage.clientId}" ${index === this.state.editor.stages.length - 1 ? "disabled" : ""} title="${translate("Move down")}">↓</button>
                                    <button type="button" class="prw-icon-btn is-danger prw-remove-stage" data-stage-id="${stage.clientId}" title="${translate("Delete from route")}">×</button>
                                </div>`}
                        </header>
                        <div class="prw-stage-fields">
                            <label class="prw-field">
                                <span>${translate("Stage")}</span>
                                <div class="prw-stage-identity">
                                    <b>${this.esc(stage.department_label || stage.stage_type)}</b>
                                    <span class="prw-stage-code-chip">${this.esc(stage.stage_type)}</span>
                                </div>
                            </label>
                            <label class="prw-field">
                                <span>${translate("Operational role")} <em>*</em></span>
                                <div class="prw-stage-role-mount" data-stage-id="${stage.clientId}"></div>
                            </label>
                            <label class="prw-switch-field prw-stage-planning-toggle">
                                <input type="checkbox" data-stage-field="is_planning_stage" data-stage-id="${stage.clientId}" ${stage.is_planning_stage ? "checked" : ""} ${readOnly ? "disabled" : ""}>
                                <span class="prw-switch" aria-hidden="true"></span>
                                <span><b>${translate("Planning stage")}</b><small>${translate("Require cutting plan approval before handoff to the next stage")}</small></span>
                            </label>
                            <label class="prw-switch-field prw-stage-whatsapp-toggle">
                                <input type="checkbox" data-stage-field="notify_whatsapp_on_complete" data-stage-id="${stage.clientId}" ${stage.notify_whatsapp_on_complete ? "checked" : ""} ${readOnly ? "disabled" : ""}>
                                <span class="prw-switch" aria-hidden="true"></span>
                                <span><b>${translate("Send WhatsApp on completion")}</b><small>${translate("This stage's text field appears in Factory settings → WhatsApp messages")}</small></span>
                            </label>
                        </div>
                    </article>
                </div>`;
        }

        bind() {
            const $root = this.$main;
            $root.off(".prw");
            $root.on("click.prw", ".prw-retry", () => this.load());
            $root.on("click.prw", ".prw-view-tab", event => {
                if (!this.isActive()) return;
                this.state.section = event.currentTarget.dataset.section;
                this.state.search = "";
                this.renderOverview();
            });
            $root.on("click.prw", ".prw-edit-route", event => this.openEditor(event.currentTarget.dataset.name));
            $root.on("click.prw", ".prw-duplicate-route", event => this.openEditor(event.currentTarget.dataset.name, {duplicate: true}));
            $root.on("click.prw", ".prw-toggle-route", event => this.toggleRoute(event.currentTarget.dataset));
            $root.on("click.prw", ".prw-delete-route", event => this.deleteRoute(event.currentTarget.dataset));
            $root.on("click.prw", ".prw-close-editor", () => this.closeEditor());
            $root.on("click.prw", ".prw-save-route", () => this.saveEditor());
            $root.on("click.prw", ".prw-library-card", event => {
                if ($(event.target).closest(".prw-library-card-actions").length) return;
                this.addStageDefinition(event.currentTarget.dataset.stageDefinition);
            });
            $root.on("keydown.prw", ".prw-library-card[role='button']", event => {
                if (event.key !== "Enter" && event.key !== " ") return;
                if ($(event.target).closest(".prw-library-card-actions").length) return;
                event.preventDefault();
                this.addStageDefinition(event.currentTarget.dataset.stageDefinition);
            });
            $root.on("click.prw", ".prw-library-add", event => {
                event.stopPropagation();
                this.openStageDefinitionDialog();
            });
            $root.on("click.prw", ".prw-edit-stage-definition", event => {
                event.stopPropagation();
                this.openStageDefinitionDialog(event.currentTarget.dataset.name);
            });
            $root.on("click.prw", ".prw-toggle-stage-definition", event => {
                event.stopPropagation();
                this.toggleStageDefinition(event.currentTarget.dataset);
            });
            $root.on("click.prw", ".prw-delete-stage-definition", event => {
                event.stopPropagation();
                this.deleteStageDefinition(event.currentTarget.dataset);
            });
            $root.on("click.prw", ".prw-remove-stage", event => this.removeStage(event.currentTarget.dataset.stageId));
            $root.on("click.prw", ".prw-move-stage", event => this.moveStage(
                event.currentTarget.dataset.stageId,
                Number(event.currentTarget.dataset.direction || 0)
            ));
            $root.on("input.prw change.prw", "[data-editor-field]", event => this.updateEditorField(event.currentTarget));
            $root.on("input.prw change.prw", "[data-stage-field]", event => this.updateStageField(event.currentTarget));
            $root.on("dragstart.prw", ".prw-story-row", event => this.dragStart(event));
            $root.on("dragover.prw", ".prw-story-row", event => this.dragOver(event));
            $root.on("dragleave.prw", ".prw-story-row", event => {
                if (this.isActive()) $(event.currentTarget).removeClass("is-drag-over");
            });
            $root.on("drop.prw", ".prw-story-row", event => this.dropStage(event));
            $root.on("dragend.prw", ".prw-story-row", () => this.clearDragState());
        }

        updateEditorField(element) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const field = element.dataset.editorField;
            this.state.editor[field] = element.type === "checkbox" ? element.checked : element.value;
            this.markDirty();
        }

        updateStageField(element) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const stage = this.state.editor.stages.find(row => row.clientId === element.dataset.stageId);
            if (!stage) return;
            const field = element.dataset.stageField;
            const value = element.type === "checkbox" ? element.checked : element.value;
            if (field === "is_planning_stage" && value) {
                const index = this.state.editor.stages.indexOf(stage);
                if (index !== 0) {
                    element.checked = false;
                    frappe.show_alert({
                        message: translate("The planning stage must be the first stage. Move the stage first."),
                        indicator: "orange",
                    });
                    return;
                }
                this.state.editor.stages.forEach(other => {
                    other.is_planning_stage = other.clientId === stage.clientId;
                });
            } else {
                stage[field] = value;
            }
            this.markDirty();
            if (field === "is_planning_stage") this.renderEditor();
        }

        markDirty() {
            if (!this.state.editor) return;
            this.state.editor.dirty = true;
            this.state.editor.revision += 1;
            const $state = this.$main.find(".prw-save-state");
            $state.addClass("is-dirty").text(translate("Unsaved changes"));
            this.$main.find(".prw-save-route").prop("disabled", this.state.saving);
        }

        catalogStage(name) {
            return (this.state.data.stage_catalog || []).find(stage => String(stage.name) === String(name));
        }

        addStageDefinition(name) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const definition = this.catalogStage(name);
            if (!definition || definition.disabled) return;
            const duplicate = this.state.editor.stages.some(
                stage => String(stage.stage_definition).toLocaleLowerCase() === String(name).toLocaleLowerCase()
            );
            if (duplicate) {
                frappe.show_alert({message: translate("Stage already exists"), indicator: "orange"});
                return;
            }
            const draft = this.stageDraft({
                stage_definition: definition.name,
                stage_type: definition.stage_type,
                department_label: definition.label,
                is_planning_stage: Boolean(
                    definition.planning && this.state.editor.stages.length === 0
                ),
            });
            this.state.editor.stages.push(draft);
            this.markDirty();
            this.renderEditor();
            frappe.show_alert({
                message: `${translate("Stage added")}: ${definition.label}`,
                indicator: "green",
            }, 3);
            const row = this.$main.find(`[data-stage-id="${draft.clientId}"]`).get(0);
            if (row) row.scrollIntoView({behavior: "smooth", block: "nearest"});
        }

        removeStage(stageId) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const stage = this.state.editor.stages.find(row => row.clientId === stageId);
            if (!stage) return;
            const generation = this.activeGeneration();
            const workingId = this.state.editor.workingId;
            return this.confirmForGeneration(
                `${translate("Delete stage from route")} «${stage.department_label || stage.stage_type}»?`,
                generation,
                () => {
                    if (!this.state.editor || this.state.editor.workingId !== workingId) return null;
                    this.state.editor.stages = this.state.editor.stages.filter(row => row.clientId !== stageId);
                    this.markDirty();
                    this.renderEditor();
                    return true;
                }
            );
        }

        moveStage(stageId, direction) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly || !direction) return;
            const index = this.state.editor.stages.findIndex(stage => stage.clientId === stageId);
            const target = index + direction;
            if (index < 0 || target < 0 || target >= this.state.editor.stages.length) return;
            const [stage] = this.state.editor.stages.splice(index, 1);
            this.state.editor.stages.splice(target, 0, stage);
            this.markDirty();
            this.renderEditor();
        }

        dragStart(event) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            this.state.draggedStageId = event.currentTarget.dataset.stageId;
            $(event.currentTarget).addClass("is-dragging");
            const originalEvent = event.originalEvent;
            if (originalEvent && originalEvent.dataTransfer) {
                originalEvent.dataTransfer.effectAllowed = "move";
                originalEvent.dataTransfer.setData("text/plain", this.state.draggedStageId);
            }
        }

        dragOver(event) {
            if (!this.isActive() || !this.state.draggedStageId) return;
            event.preventDefault();
            this.$main.find(".prw-story-row").removeClass("is-drag-over");
            $(event.currentTarget).addClass("is-drag-over");
        }

        dropStage(event) {
            event.preventDefault();
            if (!this.isActive() || !this.state.editor || !this.state.draggedStageId) return;
            const targetId = event.currentTarget.dataset.stageId;
            const sourceId = this.state.draggedStageId;
            if (sourceId === targetId) return;
            const sourceIndex = this.state.editor.stages.findIndex(stage => stage.clientId === sourceId);
            if (sourceIndex < 0) return;
            const [stage] = this.state.editor.stages.splice(sourceIndex, 1);
            const targetIndex = this.state.editor.stages.findIndex(row => row.clientId === targetId);
            this.state.editor.stages.splice(Math.max(0, targetIndex), 0, stage);
            this.clearDragState();
            this.markDirty();
            this.renderEditor();
        }

        validateEditor() {
            const editor = this.state.editor;
            const errors = [];
            if (!String(editor.routing_name || "").trim()) errors.push(translate("Production route name is required."));
            if (!editor.stages.length) errors.push(translate("Add at least one stage."));
            const seen = new Set();
            let planningCount = 0;
            editor.stages.forEach((stage, index) => {
                const number = index + 1;
                const definition = String(stage.stage_definition || "").trim();
                if (!definition) errors.push(`${translate("Stage")} ${number}: ${translate("Select the stage from the library.")}`);
                if (!String(stage.operational_role || "").trim()) errors.push(`${translate("Stage")} ${number}: ${translate("Operational role is required.")}`);
                const key = definition.toLocaleLowerCase();
                if (key && seen.has(key)) errors.push(`${translate("Duplicate stage")}: ${stage.department_label || stage.stage_type}`);
                if (key) seen.add(key);
                const catalog = this.catalogStage(definition);
                if (!catalog) errors.push(`${translate("Stage not found in the library")}: ${stage.department_label || stage.stage_type}`);
                if (catalog && catalog.disabled) errors.push(`${translate("Stage is disabled")}: ${catalog.label}`);
                if (stage.is_planning_stage) planningCount += 1;
                if (stage.is_planning_stage && index !== 0) errors.push(translate("The planning stage must be the first stage."));
            });
            if (planningCount > 1) errors.push(translate("Only one planning stage can be selected."));
            return [...new Set(errors)];
        }

        saveEditor() {
            const editor = this.state.editor;
            if (!this.isActive() || !editor || editor.readOnly || !editor.dirty || this.state.saving) {
                return Promise.resolve(false);
            }
            const errors = this.validateEditor();
            if (errors.length) {
                this.showMessage({
                    title: translate("Complete the route details"),
                    indicator: "orange",
                    message: `<ul class="prw-validation-list">${errors.map(error => `<li>${this.esc(error)}</li>`).join("")}</ul>`,
                });
                return Promise.resolve(false);
            }
            const completed = this.completedSave;
            if (completed && completed.workingId === editor.workingId) {
                const saved = completed.data || {};
                if (saved.name) editor.name = saved.name;
                if (saved.modified) editor.expected_modified = String(saved.modified);
                this.completedSave = null;
            }
            const generation = this.activeGeneration();
            const workingId = editor.workingId;
            const revision = editor.revision;
            const token = this.mutationGate.begin({type: "save", generation, workingId, revision});
            this.state.saving = true;
            this.$main.find(".prw-save-route").prop("disabled", true).text(translate("Saving..."));
            const payload = {
                name: editor.name,
                routing_name: String(editor.routing_name).trim(),
                disabled: Boolean(editor.disabled),
                expected_modified: editor.expected_modified,
                stages: editor.stages.map(stage => ({
                    stage_definition: String(stage.stage_definition).trim(),
                    operational_role: String(stage.operational_role).trim(),
                    is_planning_stage: Boolean(stage.is_planning_stage),
                    notify_whatsapp_on_complete: Boolean(stage.notify_whatsapp_on_complete),
                })),
            };
            const operation = this.call(METHODS.save, {payload}, translate("Saving production route..."))
                .then(data => {
                    const tokenCurrent = this.mutationGate.isCurrent(token);
                    const sameEditor = Boolean(
                        this.state.editor
                        && this.state.editor.workingId === workingId
                        && this.state.editor.revision === revision
                    );
                    if (tokenCurrent && this.state.editor && this.state.editor.workingId === workingId) {
                        this.state.saving = false;
                    }
                    if (!tokenCurrent || !sameEditor || !this.isCurrentGeneration(generation)) {
                        if (!this.disposed) {
                            this.reconciliationPending = true;
                            this.completedSave = {workingId, revision, data};
                        }
                        return data;
                    }
                    frappe.show_alert({message: translate("Production route saved successfully."), indicator: "green"});
                    this.state.editor = null;
                    this.completedSave = null;
                    this.reconciliationPending = true;
                    return this.reconcileWhenSafe().then(() => data);
                })
                .catch(error => {
                    const tokenCurrent = this.mutationGate.isCurrent(token);
                    const sameEditor = Boolean(
                        this.state.editor && this.state.editor.workingId === workingId
                    );
                    if (tokenCurrent && sameEditor) this.state.saving = false;
                    if (tokenCurrent && sameEditor && this.isCurrentGeneration(generation)) {
                        this.$main.find(".prw-save-route").prop("disabled", false).text(translate("Save route"));
                    }
                    console.error("Failed to save production routing", error);
                    return false;
                });
            this.pendingSave = operation;
            operation.finally(() => {
                if (this.pendingSave === operation) this.pendingSave = null;
            });
            return operation;
        }

        openStageDefinitionDialog(name = null) {
            if (!this.isActive() || !this.canManageLibrary()) return;
            const source = name ? this.catalogStage(name) : null;
            if (name && !source) {
                frappe.show_alert({message: translate("Could not find the stage. Refresh the page."), indicator: "orange"});
                return;
            }
            const dialog = new frappe.ui.Dialog({
                title: source ? translate("Edit a stage") : translate("Add new stage"),
                fields: [
                    {
                        fieldname: "stage_label",
                        fieldtype: "Data",
                        label: translate("Stage name"),
                        reqd: 1,
                        default: source ? source.label : "",
                    },
                    {
                        fieldname: "stage_code",
                        fieldtype: "Data",
                        label: translate("Stage code"),
                        reqd: 1,
                        read_only: Boolean(source),
                        default: source ? source.stage_type : "",
                        description: source
                            ? translate("Stage code is fixed after creation to protect route identity.")
                            : translate("Use a short, fixed code, such as CNC or Cutting."),
                    },
                    {
                        fieldname: "description",
                        fieldtype: "Small Text",
                        label: translate("Description"),
                        default: source ? source.description : "",
                    },
                    {
                        fieldname: "is_planning_default",
                        fieldtype: "Check",
                        label: translate("Planning stage by default"),
                        default: source && source.planning ? 1 : 0,
                    },
                ],
                primary_action_label: source ? translate("Save edit") : translate("Add the stage"),
                primary_action: values => {
                    this.saveStageDefinition(source, values).then(saved => {
                        if (saved) dialog.hide();
                    });
                },
            });
            this.ownTransient(dialog);
            if (dialog.$wrapper) {
                dialog.$wrapper.one("hidden.bs.modal", () => this.ownedTransients.delete(dialog));
            }
            dialog.show();
        }

        saveStageDefinition(source, values) {
            const mutation = this.beginLibraryMutation({type: "save-stage", name: source ? source.name : null});
            if (!mutation) return Promise.resolve(false);
            const payload = {
                name: source ? source.name : null,
                stage_code: String(values.stage_code || "").trim(),
                stage_label: String(values.stage_label || "").trim(),
                description: String(values.description || "").trim(),
                is_planning_default: Boolean(Number(values.is_planning_default || 0)),
                expected_modified: source ? source.modified : null,
            };
            const {generation, token} = mutation;
            const operation = this.call(METHODS.saveStage, {payload}, translate("Saving stage..."))
                .then(data => {
                    if (!this.libraryMutationGate.isCurrent(token) || !this.isCurrentGeneration(generation)) {
                        this.reconciliationPending = !this.disposed;
                        return true;
                    }
                    this.applyStageCatalog(data.stage_catalog || []);
                    frappe.show_alert({
                        message: source ? translate("Stage updated.") : translate("Stage added to the library."),
                        indicator: "green",
                    });
                    return true;
                })
                .catch(error => {
                    console.error("Failed to save production stage definition", error);
                    return false;
                });
            operation.finally(() => this.endLibraryMutation(token));
            return operation;
        }

        toggleStageDefinition(dataset) {
            const mutation = this.beginLibraryMutation({type: "toggle-stage", name: dataset.name});
            if (!mutation) return Promise.resolve(false);
            const disabled = Number(dataset.disabled || 0);
            const {generation, token} = mutation;
            const operation = this.call(METHODS.toggleStage, {
                name: dataset.name,
                disabled,
                expected_modified: dataset.modified,
            }, disabled ? translate("Disabling stage...") : translate("Enabling stage..."))
                .then(data => {
                    if (!this.libraryMutationGate.isCurrent(token) || !this.isCurrentGeneration(generation)) {
                        this.reconciliationPending = !this.disposed;
                        return true;
                    }
                    this.applyStageCatalog(data.stage_catalog || []);
                    frappe.show_alert({
                        message: disabled ? translate("Stage disabled.") : translate("Stage enabled."),
                        indicator: "green",
                    });
                    return true;
                })
                .catch(error => {
                    console.error("Failed to toggle production stage definition", error);
                    return false;
                });
            operation.finally(() => this.endLibraryMutation(token));
            return operation;
        }

        deleteStageDefinition(dataset) {
            if (!this.isActive() || !this.canManageLibrary()) return null;
            const stage = this.catalogStage(dataset.name);
            const generation = this.activeGeneration();
            return this.confirmForGeneration(
                `${translate("Permanently delete stage from the library")} «${stage ? stage.label : dataset.name}»?`,
                generation,
                () => {
                    const mutation = this.beginLibraryMutation({type: "delete-stage", name: dataset.name});
                    if (!mutation) return Promise.resolve(false);
                    const {generation: mutationGeneration, token} = mutation;
                    const operation = this.call(METHODS.removeStageDefinition, {
                        name: dataset.name,
                        expected_modified: dataset.modified,
                    }, translate("Deleting stage..."))
                        .then(data => {
                            if (!this.libraryMutationGate.isCurrent(token) || !this.isCurrentGeneration(mutationGeneration)) {
                                this.reconciliationPending = !this.disposed;
                                return true;
                            }
                            this.applyStageCatalog(data.stage_catalog || []);
                            frappe.show_alert({message: translate("Stage deleted from the library."), indicator: "green"});
                            return true;
                        })
                        .catch(error => {
                            console.error("Failed to delete production stage definition", error);
                            return false;
                        });
                    operation.finally(() => this.endLibraryMutation(token));
                    return operation;
                }
            );
        }

        applyStageCatalog(catalog) {
            if (!this.state.data) return;
            this.state.data.stage_catalog = Array.isArray(catalog) ? catalog : [];
            const editor = this.state.editor;
            if (editor) {
                editor.stages.forEach(stage => {
                    const definition = this.catalogStage(stage.stage_definition);
                    if (!definition) return;
                    stage.stage_type = String(definition.stage_type || definition.stage_code || definition.name || "");
                    stage.department_label = String(definition.label || definition.stage_label || stage.stage_type);
                });
                this.renderEditor();
            } else {
                this.renderOverview();
            }
        }

        closeEditor() {
            if (!this.isActive()) return null;
            const generation = this.activeGeneration();
            const workingId = this.state.editor ? this.state.editor.workingId : null;
            const close = () => {
                if (workingId && (!this.state.editor || this.state.editor.workingId !== workingId)) return null;
                this.state.editor = null;
                this.state.saving = false;
                this.completedSave = null;
                if (this.reconciliationPending) return this.reconcileWhenSafe();
                this.renderOverview();
                return true;
            };
            if (this.state.editor && this.state.editor.dirty) {
                return this.confirmForGeneration(
                    translate("Do you want to discard unsaved changes?"),
                    generation,
                    close
                );
            }
            return close();
        }

        toggleRoute(dataset) {
            if (!this.isActive()) return null;
            const generation = this.activeGeneration();
            const disabled = Number(dataset.disabled || 0);
            const action = disabled ? translate("Disable") : translate("Enable");
            return this.confirmForGeneration(
                `${action} ${translate("Production route")} «${dataset.name}»?`,
                generation,
                () => {
                    const token = this.mutationGate.begin({type: "toggle", generation, name: dataset.name});
                    return this.call(METHODS.toggle, {
                        name: dataset.name,
                        disabled,
                        expected_modified: dataset.modified,
                    }, translate("Updating route status..."))
                        .then(data => {
                            this.reconciliationPending = !this.disposed;
                            if (!this.mutationGate.isCurrent(token) || !this.isCurrentGeneration(generation)) return data;
                            frappe.show_alert({message: translate("Route status updated."), indicator: "green"});
                            return this.reconcileWhenSafe().then(() => data);
                        });
                }
            );
        }

        deleteRoute(dataset) {
            if (!this.isActive()) return null;
            const generation = this.activeGeneration();
            return this.confirmForGeneration(
                translate("Deletion will be rejected if the route is used in an order or setting. Do you want to continue?"),
                generation,
                () => {
                    const token = this.mutationGate.begin({type: "delete", generation, name: dataset.name});
                    return this.call(METHODS.remove, {
                        name: dataset.name,
                        expected_modified: dataset.modified,
                    }, translate("Verifying and deleting the route..."))
                        .then(data => {
                            this.reconciliationPending = !this.disposed;
                            if (!this.mutationGate.isCurrent(token) || !this.isCurrentGeneration(generation)) return data;
                            frappe.show_alert({message: translate("Production route deleted."), indicator: "green"});
                            return this.reconcileWhenSafe().then(() => data);
                        });
                }
            );
        }

        reconcileWhenSafe() {
            this.reconciliationPending = true;
            if (
                !this.isActive()
                || !this.bootstrapReady
                || this.state.saving
                || (this.state.editor && this.state.editor.dirty)
            ) {
                return Promise.resolve(null);
            }
            return this.load();
        }
    }

    frappe.pages["factory-master-data"].on_page_load = function (wrapper) {
        const previous = wrapper.__almdinaRoutingWorkflowPage;
        if (previous && typeof previous.dispose === "function") previous.dispose();
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: translate("Production route management"),
            single_column: true,
        });
        $(wrapper).find(".layout-main-section").html(bootstrapLoadingHtml());
        const workflowPage = new ProductionRoutingWorkflowPage(wrapper, page);
        wrapper.__almdinaRoutingWorkflowPage = workflowPage;
        return bootstrapRoutingWorkflowPage(workflowPage);
    };

    function resolveCore() {
        const frontend = window.AlmdinaFrontend;
        const ui = window.AlmdinaUi;
        const lifecycle = window.AlmdinaPageRevisit;
        if (
            !frontend
            || typeof frontend.ensureStylesheet !== "function"
            || typeof frontend.createLatestRequestGate !== "function"
            || typeof frontend.createLifecycleScope !== "function"
        ) {
            throw new Error("Almdina frontend foundation did not initialize");
        }
        if (!ui || typeof ui.button !== "function") {
            throw new Error("Almdina design system did not initialize");
        }
        if (!lifecycle || typeof lifecycle.bindActivationLifecycle !== "function") {
            throw new Error("Almdina page lifecycle did not initialize");
        }
        return {frontend, lifecycle};
    }

    function ensureCore() {
        const frontend = window.AlmdinaFrontend;
        const assets = [];
        if (!frontend || typeof frontend.ensureStylesheet !== "function") assets.push(FOUNDATION);
        if (!window.AlmdinaUi || typeof window.AlmdinaUi.button !== "function") assets.push(DESIGN_SYSTEM);
        if (!window.AlmdinaPageRevisit || typeof window.AlmdinaPageRevisit.bindActivationLifecycle !== "function") {
            assets.push(PAGE_LIFECYCLE);
        }
        if (!assets.length) return Promise.resolve(resolveCore());
        if (!frappe || typeof frappe.require !== "function") {
            return Promise.reject(new Error("Frappe asset loader is unavailable"));
        }
        const pending = frontend && typeof frontend.requireAssets === "function"
            ? frontend.requireAssets(assets)
            : frappe.require(assets);
        return Promise.resolve(pending).then(resolveCore);
    }

    function removeOwnedRoutingWorkflowStylesheets() {
        STYLE_ASSETS.forEach(([, id]) => {
            const stale = window.document && window.document.getElementById
                ? window.document.getElementById(id)
                : null;
            if (stale && typeof stale.remove === "function") stale.remove();
        });
    }

    function loadRoutingWorkflowAssets(workflowPage) {
        return ensureCore().then(core => {
            if (!workflowPage.isOwner()) return false;
            workflowPage.frontend = core.frontend;
            if (!workflowPage.mount(core.frontend, core.lifecycle)) return false;
            return Promise.all(
                STYLE_ASSETS.map(([asset, id]) => core.frontend.ensureStylesheet(asset, {id}))
            ).then(() => true);
        });
    }

    function bootstrapRoutingWorkflowPage(workflowPage, {resetStyle = false} = {}) {
        if (workflowPage.__almdinaStyleBootstrapPromise) {
            return workflowPage.__almdinaStyleBootstrapPromise;
        }
        if (resetStyle) {
            removeOwnedRoutingWorkflowStylesheets();
            workflowPage.restartBootstrap();
        }
        const retry = () => bootstrapRoutingWorkflowPage(workflowPage, {resetStyle: true});
        const pending = loadRoutingWorkflowAssets(workflowPage)
            .then(ready => ready ? workflowPage.completeBootstrap() : null)
            .catch(error => {
                workflowPage.failBootstrap(error, retry);
                return null;
            });
        workflowPage.__almdinaStyleBootstrapPromise = pending;
        pending.finally(() => {
            if (workflowPage.__almdinaStyleBootstrapPromise === pending) {
                workflowPage.__almdinaStyleBootstrapPromise = null;
            }
        });
        return pending;
    }
})();
