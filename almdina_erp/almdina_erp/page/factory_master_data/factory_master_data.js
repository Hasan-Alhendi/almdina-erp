(() => {
    "use strict";

    const STYLE_ASSET = "/assets/almdina_erp/css/factory_routing_workflow.css";
    const METHODS = Object.freeze({
        load: "almdina_erp.almdina_erp.services.master_data_service.get_production_routing_console",
        save: "almdina_erp.almdina_erp.services.master_data_service.save_production_routing",
        toggle: "almdina_erp.almdina_erp.services.master_data_service.set_production_routing_disabled",
        remove: "almdina_erp.almdina_erp.services.master_data_service.delete_production_routing",
    });

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
                requestId: 0,
                saving: false,
                draggedStageId: null,
            };
            this.stageCounter = 0;
        }

        init() {
            this.page.add_inner_button(__("تحديث"), () => this.refresh(), null, "refresh");
            return this.load();
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

        load() {
            const requestId = ++this.state.requestId;
            this.$main.html(`<div class="prw-loading"><span class="prw-spinner"></span>${__("جاري تحميل مسارات الإنتاج...")}</div>`);
            return this.call(METHODS.load)
                .then(data => {
                    if (requestId !== this.state.requestId) return;
                    this.state.data = data || {};
                    this.state.editor = null;
                    this.state.saving = false;
                    this.renderOverview();
                })
                .catch(error => {
                    if (requestId !== this.state.requestId) return;
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
                });
        }

        refresh() {
            if (this.state.editor && this.state.editor.dirty) {
                frappe.confirm(
                    __("لديك تغييرات غير محفوظة. هل تريد تجاهلها وتحديث الصفحة؟"),
                    () => this.load()
                );
                return;
            }
            this.load();
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

        openEditor(name = null, {duplicate = false} = {}) {
            const source = name
                ? (this.state.data.routings || []).find(route => route.name === name)
                : null;
            if (name && !source) {
                frappe.show_alert({message: __("تعذر العثور على المسار. حدّث الصفحة."), indicator: "orange"});
                return;
            }
            const isNew = !source || duplicate;
            this.state.editor = {
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
                this.state.section = event.currentTarget.dataset.section;
                this.state.search = "";
                this.renderOverview();
            });
            $root.on("input.prw", ".prw-search", event => {
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
            $root.on("dragleave.prw", ".prw-story-row", event => $(event.currentTarget).removeClass("is-drag-over"));
            $root.on("drop.prw", ".prw-story-row", event => this.dropStage(event));
            $root.on("dragend.prw", ".prw-story-row", () => {
                this.state.draggedStageId = null;
                this.$main.find(".prw-story-row").removeClass("is-drag-over is-dragging");
            });
        }

        updateEditorField(element) {
            if (!this.state.editor || this.state.editor.readOnly) return;
            const field = element.dataset.editorField;
            this.state.editor[field] = element.type === "checkbox" ? element.checked : element.value;
            this.markDirty();
        }

        updateStageField(element) {
            if (!this.state.editor || this.state.editor.readOnly) return;
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
            const $state = this.$main.find(".prw-save-state");
            $state.addClass("is-dirty").text(__("تغييرات غير محفوظة"));
            this.$main.find(".prw-save-route").prop("disabled", this.state.saving);
        }

        addTemplate(stageType) {
            if (!this.state.editor || this.state.editor.readOnly) return;
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
            if (!this.state.editor || this.state.editor.readOnly) return;
            this.state.editor.stages.push(this.stageDraft());
            this.markDirty();
            this.renderEditor();
            const $rows = this.$main.find(".prw-story-row");
            const last = $rows.get($rows.length - 1);
            if (last) last.scrollIntoView({behavior: "smooth", block: "center"});
        }

        removeStage(stageId) {
            if (!this.state.editor || this.state.editor.readOnly) return;
            const stage = this.state.editor.stages.find(row => row.clientId === stageId);
            if (!stage) return;
            frappe.confirm(
                `${__("حذف المرحلة")} «${stage.department_label || stage.stage_type || __("غير مسماة")}»؟`,
                () => {
                    this.state.editor.stages = this.state.editor.stages.filter(row => row.clientId !== stageId);
                    this.markDirty();
                    this.renderEditor();
                }
            );
        }

        moveStage(stageId, direction) {
            if (!this.state.editor || this.state.editor.readOnly || !direction) return;
            const index = this.state.editor.stages.findIndex(stage => stage.clientId === stageId);
            const target = index + direction;
            if (index < 0 || target < 0 || target >= this.state.editor.stages.length) return;
            const [stage] = this.state.editor.stages.splice(index, 1);
            this.state.editor.stages.splice(target, 0, stage);
            this.markDirty();
            this.renderEditor();
        }

        dragStart(event) {
            if (!this.state.editor || this.state.editor.readOnly) return;
            this.state.draggedStageId = event.currentTarget.dataset.stageId;
            $(event.currentTarget).addClass("is-dragging");
            const originalEvent = event.originalEvent;
            if (originalEvent && originalEvent.dataTransfer) {
                originalEvent.dataTransfer.effectAllowed = "move";
                originalEvent.dataTransfer.setData("text/plain", this.state.draggedStageId);
            }
        }

        dragOver(event) {
            if (!this.state.draggedStageId) return;
            event.preventDefault();
            this.$main.find(".prw-story-row").removeClass("is-drag-over");
            $(event.currentTarget).addClass("is-drag-over");
        }

        dropStage(event) {
            event.preventDefault();
            if (!this.state.editor || !this.state.draggedStageId) return;
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
            if (!editor || editor.readOnly || !editor.dirty || this.state.saving) return;
            const errors = this.validateEditor();
            if (errors.length) {
                frappe.msgprint({
                    title: __("أكمل بيانات المسار"),
                    indicator: "orange",
                    message: `<ul class="prw-validation-list">${errors.map(error => `<li>${this.esc(error)}</li>`).join("")}</ul>`,
                });
                return;
            }
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
            this.call(METHODS.save, {payload}, __("جاري حفظ مسار الإنتاج..."))
                .then(() => {
                    frappe.show_alert({message: __("تم حفظ مسار الإنتاج بنجاح."), indicator: "green"});
                    this.state.editor = null;
                    return this.load();
                })
                .catch(() => {
                    this.state.saving = false;
                    this.$main.find(".prw-save-route").prop("disabled", false).text(__("حفظ المسار"));
                });
        }

        closeEditor() {
            const close = () => {
                this.state.editor = null;
                this.state.saving = false;
                this.renderOverview();
            };
            if (this.state.editor && this.state.editor.dirty) {
                frappe.confirm(__("هل تريد تجاهل التغييرات غير المحفوظة؟"), close);
            } else {
                close();
            }
        }

        toggleRoute(dataset) {
            const disabled = Number(dataset.disabled || 0);
            const action = disabled ? __("تعطيل") : __("تفعيل");
            frappe.confirm(`${action} ${__("مسار الإنتاج")} «${dataset.name}»؟`, () => {
                this.call(METHODS.toggle, {
                    name: dataset.name,
                    disabled,
                    expected_modified: dataset.modified,
                }, __("جاري تحديث حالة المسار..."))
                    .then(() => {
                        frappe.show_alert({message: __("تم تحديث حالة المسار."), indicator: "green"});
                        this.load();
                    });
            });
        }

        deleteRoute(dataset) {
            frappe.confirm(
                __("سيُرفض الحذف إذا كان المسار مستخدمًا في طلب أو إعداد. هل تريد المتابعة؟"),
                () => {
                    this.call(METHODS.remove, {
                        name: dataset.name,
                        expected_modified: dataset.modified,
                    }, __("جاري التحقق وحذف المسار..."))
                        .then(() => {
                            frappe.show_alert({message: __("تم حذف مسار الإنتاج."), indicator: "green"});
                            this.load();
                        });
                }
            );
        }
    }

    frappe.pages["factory-master-data"].on_page_load = function (wrapper) {
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("إدارة مسارات الإنتاج"),
            single_column: true,
        });
        const workflowPage = new ProductionRoutingWorkflowPage(wrapper, page);
        wrapper.__almdinaRoutingWorkflowPage = workflowPage;
        Promise.resolve(frappe.require(STYLE_ASSET))
            .catch(() => null)
            .then(() => workflowPage.init());
    };
})();
