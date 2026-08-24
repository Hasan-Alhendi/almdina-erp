(() => {
    "use strict";

    const STYLE_ASSET = "/assets/almdina_erp/css/factory_routing_workflow.css";
    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
    const STYLE_ID = "almdina-routing-workflow-style";
    const METHODS = Object.freeze({
        load: "almdina_erp.almdina_erp.services.master_data_service.get_production_routing_console",
        save: "almdina_erp.almdina_erp.services.master_data_service.save_production_routing",
        toggle: "almdina_erp.almdina_erp.services.master_data_service.set_production_routing_disabled",
        remove: "almdina_erp.almdina_erp.services.master_data_service.delete_production_routing",
    });

    function bootstrapLoadingHtml() {
        return `
            <div class="prw-loading" data-almdina-loading-owner="factory-master-data-bootstrap" role="status" aria-live="polite">
                <span class="prw-spinner"></span>${__("جاري تحميل مسارات الإنتاج...")}
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
            this.initialized = false;
            this.disposed = false;
            this.bootstrapReady = false;
            this.bootstrapError = null;
            this.bootstrapRetry = null;
            this.bootstrapLoadingOwned = true;
            this.reconciliationPending = false;
            this.completedSave = null;
            this.ownedTransients = new Set();
            this.$refreshButton = null;
        }

        init() {
            if (this.initialized || this.disposed) return this;
            this.$refreshButton = this.page.add_inner_button(
                __("تحديث"),
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
            this.lifecycle = frontend.createLifecycleScope();
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
            if (editor && editor.dirty) {
                const completed = this.completedSave;
                if (
                    completed
                    && completed.workingId === editor.workingId
                    && completed.revision === editor.revision
                    && !this.state.saving
                ) {
                    this.state.editor = null;
                    this.completedSave = null;
                    return this.load({discardEditor: true});
                }
                this.renderEditor();
                return Promise.resolve(null);
            }
            if (this.state.saving) {
                if (editor) this.renderEditor();
                return Promise.resolve(null);
            }
            return this.load();
        }

        deactivatePage() {
            if (this.readGate) this.readGate.invalidate();
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
                return;
            }
            if (!this.activation) {
                $(this.wrapper)
                    .off(".prw-bootstrap-owner")
                    .on("show.prw-bootstrap-owner", () => {
                        if (this.isOwner() && this.isHostCurrent()) this.renderBootstrapError();
                    });
            }
        }

        renderBootstrapError() {
            const current = this.activation ? this.isActive() : this.isHostCurrent();
            if (!this.isOwner() || !current || !this.bootstrapError) return;
            const fallback = __("تعذر تحميل تصميم إدارة مسارات الإنتاج.");
            const message = this.frontend && typeof this.frontend.errorMessage === "function"
                ? this.frontend.errorMessage(this.bootstrapError, fallback)
                : String(this.bootstrapError && this.bootstrapError.message ? this.bootstrapError.message : fallback);
            const safe = frappe.utils && typeof frappe.utils.escape_html === "function"
                ? frappe.utils.escape_html(message)
                : fallback;
            console.error("Factory master data stylesheet bootstrap failed", this.bootstrapError);
            this.$main.html(`
                <div class="frappe-card" style="padding:24px;text-align:center">
                    <b>${__("تعذر تحميل تصميم إدارة مسارات الإنتاج")}</b>
                    <p style="margin:12px 0">${safe}</p>
                    <button type="button" class="btn btn-default prw-bootstrap-retry">${__("إعادة المحاولة")}</button>
                </div>`);
            this.$main
                .off(".prw-bootstrap")
                .on("click.prw-bootstrap", ".prw-bootstrap-retry", event => {
                    if (!this.isActive() && this.activation) return;
                    $(event.currentTarget).prop("disabled", true);
                    if (typeof this.bootstrapRetry === "function") this.bootstrapRetry();
                });
            frappe.show_alert({message: fallback, indicator: "red"}, 7);
        }

        dispose() {
            if (this.disposed) return false;
            this.disposed = true;
            if (this.readGate) this.readGate.invalidate();
            if (this.mutationGate) this.mutationGate.invalidate();
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
                if (surface && this.ownedTransients) this.ownedTransients.delete(surface);
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
            return frappe.utils && frappe.utils.escape_html
                ? frappe.utils.escape_html(text)
                : $("<div>").text(text).html();
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
            if (!bootstrapOwnsLoading) this.$main.html(bootstrapLoadingHtml());
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
                    return this.state.data;
                })
                .catch(error => {
                    if (!this.isCurrentGeneration(generation) || !this.readGate.isCurrent(token)) return null;
                    const message = error && error.message
                        ? error.message
                        : __("تعذر تحميل مسارات الإنتاج.");
                    this.$main.html(`
                        <div class="prw-error">
                            <b>${__("تعذر فتح إدارة المسارات")}</b>
                            <span>${this.esc(message)}</span>
                            <button type="button" class="btn btn-default prw-retry">${__("إعادة المحاولة")}</button>
                        </div>`);
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
                    __("لديك تغييرات غير محفوظة. هل تريد تجاهلها وتحديث الصفحة؟"),
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

        renderOverview() {
            const data = this.state.data || {};
            const summary = data.summary || {};
            const canCreate = this.can("create_production_routings");
            this.$main.html(`
                <main class="prw-shell" dir="rtl">
                    <section class="prw-hero">
                        <div class="prw-hero-copy">
                            <span class="prw-eyebrow">${__("Production Workflow")}</span>
                            <h2>${__("صمّم رحلة الطلب من أول مرحلة حتى التسليم")}</h2>
                            <p>${__("رتّب مراحل العمل بصريًا، اربط كل مرحلة بالدور التشغيلي المناسب، ثم استخدم المسار مباشرة في لوحة الإنتاج.")}</p>
                        </div>
                        ${canCreate ? `
                            <button type="button" class="btn btn-primary prw-new-route">
                                <span aria-hidden="true">＋</span>${__("مسار إنتاج جديد")}
                            </button>` : ""}
                    </section>

                    <section class="prw-summary" aria-label="${__("ملخص مسارات الإنتاج")}">
                        ${this.statHtml(__("المسارات"), summary.routings || 0, "routes")}
                        ${this.statHtml(__("المسارات المفعّلة"), summary.active_routings || 0, "active")}
                        ${this.statHtml(__("إجمالي المراحل"), summary.total_stages || 0, "stages")}
                        ${this.statHtml(__("طلبات قيد الإنتاج"), summary.in_flight_orders || 0, "orders")}
                    </section>

                    <section class="prw-toolbar">
                        <div class="prw-view-switch" role="tablist">
                            <button type="button" class="prw-view-tab ${this.state.section === "routings" ? "is-active" : ""}" data-section="routings">${__("المسارات")}</button>
                            <button type="button" class="prw-view-tab ${this.state.section === "audit" ? "is-active" : ""}" data-section="audit">${__("سجل التغييرات")}</button>
                        </div>
                        <label class="prw-search-wrap">
                            <span class="sr-only">${__("بحث")}</span>
                            <span class="prw-search-icon" aria-hidden="true">⌕</span>
                            <input class="prw-search" type="search" value="${this.esc(this.state.search)}" placeholder="${__("ابحث بالاسم أو المرحلة أو الدور...")}">
                        </label>
                        ${this.state.section === "routings" ? `
                            <label class="prw-filter-wrap">
                                <span>${__("الحالة")}</span>
                                <select class="form-control prw-status-filter">
                                    <option value="all" ${this.state.status === "all" ? "selected" : ""}>${__("الكل")}</option>
                                    <option value="active" ${this.state.status === "active" ? "selected" : ""}>${__("مفعّل")}</option>
                                    <option value="disabled" ${this.state.status === "disabled" ? "selected" : ""}>${__("معطّل")}</option>
                                </select>
                            </label>` : ""}
                    </section>

                    <section class="prw-content">
                        ${this.state.section === "audit" ? this.auditHtml() : this.routesHtml()}
                    </section>
                </main>`);
            this.bind();
        }

        statHtml(label, value, tone) {
            return `
                <article class="prw-stat" data-tone="${tone}">
                    <span>${this.esc(label)}</span>
                    <b>${this.esc(value)}</b>
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
                    <div class="prw-empty">
                        <span class="prw-empty-icon" aria-hidden="true">⇢</span>
                        <b>${__("لا توجد مسارات مطابقة")}</b>
                        <p>${__("غيّر البحث أو الفلتر، أو أنشئ مسارًا جديدًا لبدء تنظيم رحلة الإنتاج.")}</p>
                    </div>`;
            }
            return `<div class="prw-route-list">${routes.map(route => this.routeCardHtml(route)).join("")}</div>`;
        }

        routeCardHtml(route) {
            const stages = (route.stages || []).filter(stage => stage.required !== false);
            const canEdit = this.can("edit_production_routings");
            const canCreate = this.can("create_production_routings");
            const canDelete = this.can("delete_production_routings");
            const stageFlow = stages.length
                ? stages.map((stage, index) => `
                    <div class="prw-route-stage ${stage.is_planning_stage ? "is-planning" : ""}">
                        <span class="prw-route-stage-number">${index + 1}</span>
                        <div>
                            <b>${this.esc(stage.department_label || stage.stage_type)}</b>
                            <small>${this.esc(stage.operational_role || __("دون دور"))}</small>
                        </div>
                        ${stage.is_planning_stage ? `<span class="prw-mini-badge">${__("تخطيط")}</span>` : ""}
                    </div>`).join('<span class="prw-flow-arrow" aria-hidden="true">←</span>')
                : `<span class="prw-no-stages">${__("لا توجد مراحل فعالة")}</span>`;
            return `
                <article class="prw-route-card" data-route-name="${this.esc(route.name)}">
                    <header class="prw-route-head">
                        <div>
                            <div class="prw-route-title-line">
                                <h3>${this.esc(route.label)}</h3>
                                <span class="prw-status ${route.disabled ? "is-disabled" : "is-active"}">${route.disabled ? __("معطّل") : __("مفعّل")}</span>
                            </div>
                            <p>${this.esc(route.name)}</p>
                        </div>
                        <div class="prw-route-counts">
                            <span><b>${stages.length}</b>${__("مراحل")}</span>
                            <span><b>${Number(route.in_flight_orders || 0)}</b>${__("قيد الإنتاج")}</span>
                        </div>
                    </header>
                    <div class="prw-route-flow" aria-label="${__("تسلسل مراحل المسار")}">${stageFlow}</div>
                    <footer class="prw-route-footer">
                        <div class="prw-route-meta">
                            <span>${__("آخر تعديل")}: <b>${this.esc(route.modified || "—")}</b></span>
                            <span>${__("بواسطة")}: <b>${this.esc(route.modified_by || "—")}</b></span>
                        </div>
                        <div class="prw-card-actions">
                            <button type="button" class="btn btn-primary prw-edit-route" data-name="${this.esc(route.name)}">${canEdit ? __("تحرير Workflow") : __("معاينة")}</button>
                            ${canCreate ? `<button type="button" class="btn btn-default prw-duplicate-route" data-name="${this.esc(route.name)}">${__("نسخ")}</button>` : ""}
                            ${canEdit ? `<button type="button" class="btn btn-default prw-toggle-route" data-name="${this.esc(route.name)}" data-disabled="${route.disabled ? 0 : 1}" data-modified="${this.esc(route.modified || "")}">${route.disabled ? __("تفعيل") : __("تعطيل")}</button>` : ""}
                            ${canDelete ? `<button type="button" class="btn btn-danger prw-delete-route" data-name="${this.esc(route.name)}" data-modified="${this.esc(route.modified || "")}">${__("حذف")}</button>` : ""}
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
                return `<div class="prw-empty"><span class="prw-empty-icon">◷</span><b>${__("لا توجد تغييرات مسجلة")}</b><p>${__("سيظهر هنا كل إنشاء أو تعديل أو حذف لمسارات الإنتاج.")}</p></div>`;
            }
            return `<div class="prw-audit-list">${rows.map(row => `
                <article class="prw-audit-item">
                    <span class="prw-audit-dot" aria-hidden="true"></span>
                    <div class="prw-audit-body">
                        <div><b>${this.esc(row.target_name)}</b><time>${this.esc(row.changed_on)}</time></div>
                        <p>${this.esc(row.action)} · ${__("بواسطة")} ${this.esc(row.changed_by)}</p>
                        ${row.changed_fields ? `<small>${__("الحقول المتغيرة")}: ${this.esc(row.changed_fields)}</small>` : ""}
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
                stage_type: String(stage.stage_type || ""),
                department_label: String(stage.department_label || ""),
                operational_role: String(stage.operational_role || ""),
                is_planning_stage: Boolean(Number(stage.is_planning_stage || 0)),
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
                    ? `${source.label}${duplicate ? ` - ${__("نسخة")}` : ""}`
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
                frappe.show_alert({message: __("تعذر العثور على المسار. حدّث الصفحة."), indicator: "orange"});
                return;
            }
            this.state.editor = this.editorDraft(source, {duplicate});
            this.state.section = "routings";
            this.renderEditor();
        }

        renderEditor() {
            const editor = this.state.editor;
            if (!editor) {
                this.renderOverview();
                return;
            }
            const title = editor.name ? __("تحرير مسار الإنتاج") : __("إنشاء مسار إنتاج جديد");
            const readOnly = editor.readOnly;
            this.$main.html(`
                <main class="prw-shell prw-editor-shell" dir="rtl">
                    <header class="prw-editor-topbar">
                        <div class="prw-editor-heading">
                            <button type="button" class="btn btn-default prw-close-editor" aria-label="${__("رجوع")}">→</button>
                            <div>
                                <span class="prw-eyebrow">${__("Workflow Story")}</span>
                                <h2>${title}</h2>
                                ${editor.name ? `<p>${__("المعرّف الثابت")}: ${this.esc(editor.name)}</p>` : `<p>${__("أضف المراحل بالترتيب الحقيقي الذي يمر به الطلب.")}</p>`}
                            </div>
                        </div>
                        <div class="prw-editor-actions">
                            <span class="prw-save-state ${editor.dirty ? "is-dirty" : ""}">${editor.dirty ? __("تغييرات غير محفوظة") : __("لا توجد تغييرات")}</span>
                            <button type="button" class="btn btn-default prw-close-editor">${__("إلغاء")}</button>
                            ${readOnly ? "" : `<button type="button" class="btn btn-primary prw-save-route" ${this.state.saving || !editor.dirty ? "disabled" : ""}>${this.state.saving ? __("جاري الحفظ...") : __("حفظ المسار")}</button>`}
                        </div>
                    </header>

                    <div class="prw-editor-layout">
                        <section class="prw-editor-main">
                            <article class="prw-settings-card">
                                <div class="prw-section-heading">
                                    <div><span>01</span><h3>${__("هوية المسار")}</h3></div>
                                    <p>${__("اسم واضح يظهر عند إرسال الطلب إلى الإنتاج.")}</p>
                                </div>
                                <div class="prw-settings-grid">
                                    <label class="prw-field prw-field-wide">
                                        <span>${__("اسم مسار الإنتاج")} <em>*</em></span>
                                        <input class="form-control" data-editor-field="routing_name" value="${this.esc(editor.routing_name)}" placeholder="${__("مثال: رسم ← CNC ← تقشيط")}" ${readOnly ? "disabled" : ""}>
                                    </label>
                                    <label class="prw-switch-field">
                                        <input type="checkbox" data-editor-field="disabled" ${editor.disabled ? "checked" : ""} ${readOnly ? "disabled" : ""}>
                                        <span class="prw-switch" aria-hidden="true"></span>
                                        <span><b>${__("المسار معطّل")}</b><small>${__("لا يظهر عند إرسال طلب جديد")}</small></span>
                                    </label>
                                </div>
                            </article>

                            <article class="prw-workflow-card">
                                <div class="prw-section-heading">
                                    <div><span>02</span><h3>${__("قصة سير الإنتاج")}</h3></div>
                                    <p>${__("كل بطاقة تمثل محطة عمل. الترتيب هنا هو الترتيب الذي سيظهر في لوحة الإنتاج.")}</p>
                                </div>
                                <div class="prw-workflow-story ${editor.stages.length ? "" : "is-empty"}">
                                    ${editor.stages.length
                                        ? editor.stages.map((stage, index) => this.editorStageHtml(stage, index, readOnly)).join("")
                                        : `<div class="prw-story-empty"><span>＋</span><b>${__("ابدأ بإضافة أول مرحلة")}</b><p>${__("اختر مرحلة جاهزة من المكتبة أو أنشئ مرحلة مخصصة.")}</p></div>`}
                                </div>
                                ${readOnly ? "" : `
                                    <button type="button" class="btn btn-default prw-add-custom-stage">
                                        ＋ ${__("إضافة مرحلة مخصصة")}
                                    </button>`}
                            </article>
                        </section>

                        <aside class="prw-stage-library">
                            <div class="prw-section-heading prw-library-heading">
                                <div><span>03</span><h3>${__("مكتبة المراحل")}</h3></div>
                                <p>${__("قوالب جاهزة لتسريع بناء المسار. يمكن تعديل الاسم والدور بعد الإضافة.")}</p>
                            </div>
                            <div class="prw-library-list">
                                ${(this.state.data.stage_catalog || []).map(stage => `
                                    <button type="button" class="prw-template" data-stage-template="${this.esc(stage.stage_type)}" ${readOnly ? "disabled" : ""}>
                                        <span class="prw-template-add">＋</span>
                                        <span><b>${this.esc(stage.label)}</b><small>${this.esc(stage.description)}</small></span>
                                        ${stage.planning ? `<em>${__("تخطيط")}</em>` : ""}
                                    </button>`).join("")}
                            </div>
                            <div class="prw-library-tip">
                                <b>${__("قاعدة مهمة")}</b>
                                <p>${__("يمكن تحديد مرحلة تخطيط واحدة فقط، ويجب أن تكون أول مرحلة في المسار.")}</p>
                            </div>
                        </aside>
                    </div>

                    <datalist id="prw-stage-types">
                        ${(this.state.data.stage_catalog || []).map(stage => `<option value="${this.esc(stage.stage_type)}">${this.esc(stage.label)}</option>`).join("")}
                    </datalist>
                </main>`);
            this.bind();
        }

        editorStageHtml(stage, index, readOnly) {
            const roleValues = new Set(this.state.data.operational_roles || []);
            if (stage.operational_role) roleValues.add(stage.operational_role);
            const roleOptions = [...roleValues].sort((left, right) => left.localeCompare(right)).map(role => `
                <option value="${this.esc(role)}" ${role === stage.operational_role ? "selected" : ""}>${this.esc(role)}</option>`).join("");
            return `
                <div class="prw-story-row" draggable="${readOnly ? "false" : "true"}" data-stage-id="${stage.clientId}">
                    <div class="prw-story-rail">
                        <span>${index + 1}</span>
                        ${index < this.state.editor.stages.length - 1 ? `<i aria-hidden="true"></i>` : ""}
                    </div>
                    <article class="prw-stage-editor ${stage.is_planning_stage ? "is-planning" : ""}">
                        <header>
                            <div class="prw-stage-title">
                                <span class="prw-drag-handle" title="${__("اسحب لتغيير الترتيب")}" aria-hidden="true">⋮⋮</span>
                                <div>
                                    <b>${this.esc(stage.department_label || stage.stage_type || __("مرحلة جديدة"))}</b>
                                    <small>${stage.is_planning_stage ? __("مرحلة تخطيط") : __("مرحلة تنفيذ")}</small>
                                </div>
                            </div>
                            ${readOnly ? "" : `
                                <div class="prw-stage-actions">
                                    <button type="button" class="prw-icon-btn prw-move-stage" data-direction="-1" data-stage-id="${stage.clientId}" ${index === 0 ? "disabled" : ""} title="${__("تحريك للأعلى")}">↑</button>
                                    <button type="button" class="prw-icon-btn prw-move-stage" data-direction="1" data-stage-id="${stage.clientId}" ${index === this.state.editor.stages.length - 1 ? "disabled" : ""} title="${__("تحريك للأسفل")}">↓</button>
                                    <button type="button" class="prw-icon-btn is-danger prw-remove-stage" data-stage-id="${stage.clientId}" title="${__("حذف المرحلة")}">×</button>
                                </div>`}
                        </header>
                        <div class="prw-stage-fields">
                            <label class="prw-field">
                                <span>${__("اسم القسم الظاهر")} <em>*</em></span>
                                <input class="form-control" data-stage-field="department_label" data-stage-id="${stage.clientId}" value="${this.esc(stage.department_label)}" placeholder="${__("مثال: فحص الجودة")}" ${readOnly ? "disabled" : ""}>
                            </label>
                            <label class="prw-field">
                                <span>${__("رمز المرحلة")} <em>*</em></span>
                                <input class="form-control" list="prw-stage-types" data-stage-field="stage_type" data-stage-id="${stage.clientId}" value="${this.esc(stage.stage_type)}" placeholder="Quality Check" ${readOnly ? "disabled" : ""}>
                            </label>
                            <label class="prw-field">
                                <span>${__("الدور التشغيلي")} <em>*</em></span>
                                <select class="form-control" data-stage-field="operational_role" data-stage-id="${stage.clientId}" ${readOnly ? "disabled" : ""}>
                                    <option value="">${__("اختر الدور المسؤول...")}</option>
                                    ${roleOptions}
                                </select>
                            </label>
                            <label class="prw-planning-check">
                                <input type="checkbox" data-stage-field="is_planning_stage" data-stage-id="${stage.clientId}" ${stage.is_planning_stage ? "checked" : ""} ${readOnly ? "disabled" : ""}>
                                <span><b>${__("مرحلة تخطيط")}</b><small>${__("تتطلب اعتماد خطة القص قبل التسليم للمرحلة التالية")}</small></span>
                            </label>
                        </div>
                    </article>
                </div>`;
        }

        bind() {
            const $root = this.$main;
            $root.off(".prw");
            $root.on("click.prw", ".prw-retry", () => this.load());
            $root.on("click.prw", ".prw-new-route", () => this.openEditor());
            $root.on("click.prw", ".prw-view-tab", event => {
                if (!this.isActive()) return;
                this.state.section = event.currentTarget.dataset.section;
                this.state.search = "";
                this.renderOverview();
            });
            $root.on("input.prw", ".prw-search", event => {
                if (!this.isActive()) return;
                this.state.search = String(event.currentTarget.value || "");
                const cursor = event.currentTarget.selectionStart;
                this.renderOverview();
                const input = this.$main.find(".prw-search").get(0);
                if (input) {
                    input.focus();
                    if (cursor !== null) input.setSelectionRange(cursor, cursor);
                }
            });
            $root.on("change.prw", ".prw-status-filter", event => {
                if (!this.isActive()) return;
                this.state.status = event.currentTarget.value;
                this.renderOverview();
            });
            $root.on("click.prw", ".prw-edit-route", event => this.openEditor(event.currentTarget.dataset.name));
            $root.on("click.prw", ".prw-duplicate-route", event => this.openEditor(event.currentTarget.dataset.name, {duplicate: true}));
            $root.on("click.prw", ".prw-toggle-route", event => this.toggleRoute(event.currentTarget.dataset));
            $root.on("click.prw", ".prw-delete-route", event => this.deleteRoute(event.currentTarget.dataset));
            $root.on("click.prw", ".prw-close-editor", () => this.closeEditor());
            $root.on("click.prw", ".prw-save-route", () => this.saveEditor());
            $root.on("click.prw", ".prw-template", event => this.addTemplate(event.currentTarget.dataset.stageTemplate));
            $root.on("click.prw", ".prw-add-custom-stage", () => this.addCustomStage());
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
            $root.on("dragend.prw", ".prw-story-row", () => {
                if (!this.isActive()) return;
                this.state.draggedStageId = null;
                this.$main.find(".prw-story-row").removeClass("is-drag-over is-dragging");
            });
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
                        message: __("مرحلة التخطيط يجب أن تكون أول مرحلة. حرّك المرحلة أولًا."),
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
            $state.addClass("is-dirty").text(__("تغييرات غير محفوظة"));
            this.$main.find(".prw-save-route").prop("disabled", this.state.saving);
        }

        addTemplate(stageType) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const template = (this.state.data.stage_catalog || []).find(stage => stage.stage_type === stageType);
            if (!template) return;
            const duplicate = this.state.editor.stages.some(stage => stage.stage_type.toLocaleLowerCase() === stageType.toLocaleLowerCase());
            if (duplicate) {
                frappe.show_alert({message: __("هذه المرحلة موجودة بالفعل داخل المسار."), indicator: "orange"});
                return;
            }
            this.state.editor.stages.push(this.stageDraft({
                stage_type: template.stage_type,
                department_label: template.label,
                is_planning_stage: Boolean(template.planning && this.state.editor.stages.length === 0),
            }));
            this.markDirty();
            this.renderEditor();
        }

        addCustomStage() {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            this.state.editor.stages.push(this.stageDraft());
            this.markDirty();
            this.renderEditor();
            const $rows = this.$main.find(".prw-story-row");
            const last = $rows.get($rows.length - 1);
            if (last) last.scrollIntoView({behavior: "smooth", block: "center"});
        }

        removeStage(stageId) {
            if (!this.isActive() || !this.state.editor || this.state.editor.readOnly) return;
            const stage = this.state.editor.stages.find(row => row.clientId === stageId);
            if (!stage) return;
            const generation = this.activeGeneration();
            const workingId = this.state.editor.workingId;
            return this.confirmForGeneration(
                `${__("حذف المرحلة")} «${stage.department_label || stage.stage_type || __("غير مسماة")}»؟`,
                generation,
                () => {
                    if (!this.state.editor || this.state.editor.workingId !== workingId) return null;
                    this.state.editor.stages = this.state.editor.stages.filter(row => row.clientId !== stageId);
                    this.markDirty();
                    this.renderEditor();
                    return true;
                },
                null
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
            this.state.draggedStageId = null;
            this.markDirty();
            this.renderEditor();
        }

        validateEditor() {
            const editor = this.state.editor;
            const errors = [];
            if (!String(editor.routing_name || "").trim()) errors.push(__("اسم مسار الإنتاج مطلوب."));
            if (!editor.stages.length) errors.push(__("أضف مرحلة واحدة على الأقل."));
            const seen = new Set();
            let planningCount = 0;
            editor.stages.forEach((stage, index) => {
                const number = index + 1;
                if (!String(stage.department_label || "").trim()) errors.push(`${__("المرحلة")} ${number}: ${__("اسم القسم الظاهر مطلوب.")}`);
                if (!String(stage.stage_type || "").trim()) errors.push(`${__("المرحلة")} ${number}: ${__("رمز المرحلة مطلوب.")}`);
                if (!String(stage.operational_role || "").trim()) errors.push(`${__("المرحلة")} ${number}: ${__("الدور التشغيلي مطلوب.")}`);
                const key = String(stage.stage_type || "").trim().toLocaleLowerCase();
                if (key && seen.has(key)) errors.push(`${__("رمز المرحلة مكرر")}: ${stage.stage_type}`);
                if (key) seen.add(key);
                if (stage.is_planning_stage) planningCount += 1;
                if (stage.is_planning_stage && index !== 0) errors.push(__("مرحلة التخطيط يجب أن تكون أول مرحلة."));
            });
            if (planningCount > 1) errors.push(__("يمكن تحديد مرحلة تخطيط واحدة فقط."));
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
                    title: __("أكمل بيانات المسار"),
                    indicator: "orange",
                    message: `<ul class="prw-validation-list">${errors.map(error => `<li>${this.esc(error)}</li>`).join("")}</ul>`,
                });
                return Promise.resolve(false);
            }
            const generation = this.activeGeneration();
            const workingId = editor.workingId;
            const revision = editor.revision;
            const token = this.mutationGate.begin({type: "save", generation, workingId, revision});
            this.state.saving = true;
            this.$main.find(".prw-save-route").prop("disabled", true).text(__("جاري الحفظ..."));
            const payload = {
                name: editor.name,
                routing_name: String(editor.routing_name).trim(),
                disabled: Boolean(editor.disabled),
                expected_modified: editor.expected_modified,
                stages: editor.stages.map(stage => ({
                    stage_type: String(stage.stage_type).trim(),
                    department_label: String(stage.department_label).trim(),
                    operational_role: String(stage.operational_role).trim(),
                    is_planning_stage: Boolean(stage.is_planning_stage),
                })),
            };
            return this.call(METHODS.save, {payload}, __("جاري حفظ مسار الإنتاج..."))
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
                            this.completedSave = {workingId, revision};
                        }
                        return data;
                    }
                    frappe.show_alert({message: __("تم حفظ مسار الإنتاج بنجاح."), indicator: "green"});
                    this.state.editor = null;
                    this.completedSave = null;
                    this.reconciliationPending = true;
                    return this.reconcileWhenSafe().then(() => data);
                })
                .catch(error => {
                    const tokenCurrent = this.mutationGate.isCurrent(token);
                    const sameEditor = Boolean(
                        this.state.editor
                        && this.state.editor.workingId === workingId
                    );
                    if (tokenCurrent && sameEditor) this.state.saving = false;
                    if (tokenCurrent && sameEditor && this.isCurrentGeneration(generation)) {
                        this.$main.find(".prw-save-route").prop("disabled", false).text(__("حفظ المسار"));
                    }
                    return false;
                });
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
                    __("هل تريد تجاهل التغييرات غير المحفوظة؟"),
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
            const action = disabled ? __("تعطيل") : __("تفعيل");
            return this.confirmForGeneration(
                `${action} ${__("مسار الإنتاج")} «${dataset.name}»؟`,
                generation,
                () => {
                    const token = this.mutationGate.begin({type: "toggle", generation, name: dataset.name});
                    return this.call(METHODS.toggle, {
                        name: dataset.name,
                        disabled,
                        expected_modified: dataset.modified,
                    }, __("جاري تحديث حالة المسار..."))
                        .then(data => {
                            this.reconciliationPending = !this.disposed;
                            if (!this.mutationGate.isCurrent(token) || !this.isCurrentGeneration(generation)) {
                                return data;
                            }
                            frappe.show_alert({message: __("تم تحديث حالة المسار."), indicator: "green"});
                            return this.reconcileWhenSafe().then(() => data);
                        })
                        .catch(error => {
                            if (this.mutationGate.isCurrent(token) && this.isCurrentGeneration(generation)) {
                                throw error;
                            }
                            return null;
                        });
                }
            );
        }

        deleteRoute(dataset) {
            if (!this.isActive()) return null;
            const generation = this.activeGeneration();
            return this.confirmForGeneration(
                __("سيُرفض الحذف إذا كان المسار مستخدمًا في طلب أو إعداد. هل تريد المتابعة؟"),
                generation,
                () => {
                    const token = this.mutationGate.begin({type: "delete", generation, name: dataset.name});
                    return this.call(METHODS.remove, {
                        name: dataset.name,
                        expected_modified: dataset.modified,
                    }, __("جاري التحقق وحذف المسار..."))
                        .then(data => {
                            this.reconciliationPending = !this.disposed;
                            if (!this.mutationGate.isCurrent(token) || !this.isCurrentGeneration(generation)) {
                                return data;
                            }
                            frappe.show_alert({message: __("تم حذف مسار الإنتاج."), indicator: "green"});
                            return this.reconcileWhenSafe().then(() => data);
                        })
                        .catch(error => {
                            if (this.mutationGate.isCurrent(token) && this.isCurrentGeneration(generation)) {
                                throw error;
                            }
                            return null;
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
            title: __("إدارة مسارات الإنتاج"),
            single_column: true,
        });
        $(wrapper).find(".layout-main-section").html(bootstrapLoadingHtml());
        const workflowPage = new ProductionRoutingWorkflowPage(wrapper, page);
        wrapper.__almdinaRoutingWorkflowPage = workflowPage;
        return bootstrapRoutingWorkflowPage(workflowPage);
    };

    function resolveCore() {
        const frontend = window.AlmdinaFrontend;
        const lifecycle = window.AlmdinaPageRevisit;
        if (
            !frontend
            || typeof frontend.ensureStylesheet !== "function"
            || typeof frontend.createLatestRequestGate !== "function"
            || typeof frontend.createLifecycleScope !== "function"
        ) {
            throw new Error("Almdina frontend foundation did not initialize");
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

    function removeOwnedRoutingWorkflowStylesheet() {
        const stale = window.document && window.document.getElementById
            ? window.document.getElementById(STYLE_ID)
            : null;
        if (stale && typeof stale.remove === "function") stale.remove();
    }

    function loadRoutingWorkflowAssets(workflowPage) {
        return ensureCore().then(core => {
            if (!workflowPage.isOwner()) return false;
            workflowPage.frontend = core.frontend;
            if (!workflowPage.mount(core.frontend, core.lifecycle)) return false;
            return core.frontend.ensureStylesheet(STYLE_ASSET, {id: STYLE_ID})
                .then(() => true);
        });
    }

    function bootstrapRoutingWorkflowPage(workflowPage, {resetStyle = false} = {}) {
        if (workflowPage.__almdinaStyleBootstrapPromise) {
            return workflowPage.__almdinaStyleBootstrapPromise;
        }
        if (resetStyle) {
            removeOwnedRoutingWorkflowStylesheet();
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
