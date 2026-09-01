# 14 — Frontend Refactor Closure

> **Status:** Canonical frontend ownership map after F4–F7  
> **Scope:** Structural ownership, lifecycle, rendering boundaries, and quality gates  
> **Lifecycle standard:** [15 — Project-wide Frontend Lifecycle Standard](15_FRONTEND_LIFECYCLE_STANDARD.md)
> **Non-goals:** UI redesign, business-rule changes, authorization changes, workflow changes, schema/data migration

## 1. لماذا أُغلقت مرحلة الـrefactor؟

هدف سلسلة F4–F7 لم يكن إضافة Features جديدة، بل إزالة الملكيات المتداخلة التي كانت تجعل إصلاح جزء من الواجهة قادرًا على كسر جزء آخر بعيد عنه. الإغلاق يعني أن المسارات الحرجة أصبحت تملك Owners معلنين، وأن الحدود محمية باختبارات وCI، وليس أن الواجهة لن تتطور لاحقًا.

بعد هذه النقطة، أي Feature أو Fix يجب أن يُنفّذ داخل الـOwner الحالي كلما أمكن. إنشاء Patch عالمي أو Observer موازٍ أو Orchestrator ضخم جديد ليس مسارًا افتراضيًا مقبولًا.

خريطة الملكية في هذه الوثيقة تحدد **من يملك ماذا** بعد F4–F7، بينما يحدد [15 — Frontend Lifecycle Standard](15_FRONTEND_LIFECYCLE_STANDARD.md) **كيف تُدار حياة الـowner** حسب عائلة الـsurface وكيف تُثبت certification دون فرض helper واحدة على المشروع.

## 2. خريطة الملكية النهائية

| المجال | الـOwner / الملف | المسؤولية |
|---|---|---|
| Frontend primitives | `public/js/frontend_foundation.js` | lifecycle scopes, latest-request gates, RPC helpers والأساس المشترك للـfrontend |
| Permission context | `public/js/permission_context.js` | سياق الصلاحيات القابل للاستهلاك من الواجهة؛ ليس بديلًا عن server authorization |
| Workspace entry visibility | `application/security/workspace_visibility.py` + `boot.py` + `workspace_api.py` | إسقاط shortcuts/sections/links غير المسموحة من payload الخادم قبل render |
| Workforce primary action visibility | `public/js/factory_workforce/controller.js` | fail-closed محليًا أثناء mount/refresh ثم يتبع `create_users` من console payload الحالي |
| DCO document freshness | `door_cutting_order/core/door_cutting_order_document_context.js` | هوية الوثيقة، generation/freshness، timers/frames/observers المرتبطة بعمر الوثيقة |
| DCO permission refresh | `door_cutting_order/core/door_cutting_order_permission_refresh_ux.js` | إعادة مزامنة واجهة DCO عند تغيّر permission context |
| Production settings | `public/js/production_routing_ux.js` | إعدادات وتحرير production routing فقط |
| Shared shop-floor actions | `public/js/shop_floor_quick_actions.js` | quick actions المشتركة خارج صفحة inbox؛ لا يملك صفحة inbox نفسها |
| Shop Floor Inbox transport | `public/js/shop_floor_inbox/api.js` | RPC transport الوحيد للصفحة |
| Shop Floor Inbox state | `public/js/shop_floor_inbox/state.js` | mutable page state، freshness gates، lifecycle scope |
| Shop Floor Inbox view-model | `public/js/shop_floor_inbox/view_model.js` | تحويل البيانات server-scoped إلى view models نقية |
| Shop Floor Inbox rendering | `public/js/shop_floor_inbox/renderer.js` | markup الخاص بالصفحة |
| Shop Floor Inbox interactions | `public/js/shop_floor_inbox/interactions.js` | delegated UI events وربطها بالـlifecycle |
| Shop Floor Inbox dialogs | `public/js/shop_floor_inbox/dialogs.js` | handoff/logout prompts ورسائل الصفحة |
| Shop Floor Inbox orchestration | `public/js/shop_floor_inbox/controller.js` | تنسيق API/state/view-model/renderers فقط؛ ليس transport أو renderer |
| Measurement scheduling/readiness | `door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js` | إلغاء frame/timer work القديم، feature-key ownership، document freshness، والمصالحة النهائية المسجلة بعد كل base render |
| Fast-entry base interaction | `door_cutting_order/order_entry/door_cutting_order_operator_ux.js` | row materialization/input sync وsingle-click edge toggle الأساسي |
| Qty + Enter keyboard flow | `measurements/door_cutting_order_fast_entry_keyboard_ux.js` | Qty normalization، تشغيل qty handler، ثم الانتقال إلى Width في السطر التالي |
| Multi-edge feature renderer | `edge_banding/door_cutting_order_multi_edge_ux.js` | واجهة/بيانات القشاط متعدد الأضلاع ووظائفه العامة |
| Edge profile controls | `edge_banding/door_cutting_order_edge_profile_controls_ux.js` | profile display/popover feature API |
| Edge single/double-click arbitration | `edge_banding/door_cutting_order_edge_profile_double_click_guard.js` | تأخير single click 260ms وإعادة تشغيله، وفتح profile selector عند double-click |
| Edge structural render runtime | `edge_banding/door_cutting_order_edge_render_owner.js` | المالك الوحيد لمراقبة structural DOM changes وجدولة إعادة زخرفة القشاط |
| Cutting-plan styles | `cutting_plan/door_cutting_order_plan_content_styles.js` | CSS الخاص بمحتوى خطة القص مع نفس install timing/style identity |
| Cutting-plan boards | `cutting_plan/door_cutting_order_plan_board_presenter.js` | board gallery layout، responsive columns، focus/zoom/interactions |
| Cutting-plan content orchestration | `cutting_plan/door_cutting_order_plan_content_ux.js` | snapshot/margin policy/duplicate cleanup/document lifecycle/observers فقط |

## 3. عقود runtime التي لا يجوز كسرها

### 3.1 الترتيب مهم

`frontend_assets.py` هو manifest مركزي وترتيبه runtime-significant. لا تُنقل الوحدات اعتباطيًا.

داخل DCO، العقود الأساسية هي:

1. `door_cutting_order_operator_ux.js` قبل `door_cutting_order_fast_entry_keyboard_ux.js`.
2. Measurement lifecycle يُحمّل قبل الوحدات التي تستخدمه.
3. `multi_edge_ux` ثم `edge_profile_controls` ثم `edge_profile_double_click_guard` ثم `edge_render_owner` ثم `cut_dimensions`.
4. `plan_controls` ثم `plan_content_styles` ثم `plan_board_presenter` ثم `plan_content_ux` ثم `plan_tabs`.

### 3.2 لا تعيد Patch القديم

`door_cutting_order_operator_ux_patch.js` أزيل نهائيًا. إذا ظهرت Regression في Qty+Enter أو edge clicks، أصلح الـOwner المختص بدل إعادة Patch عالمي يلتقط الأحداث قبل بقية الوحدات.

### 3.3 Single click وDouble click

- الـsingle-click toggle الفعلي ملك `door_cutting_order_operator_ux.js`.
- الـdouble-click guard ينتظر `260 ms` لتمييز النقر المفرد من المزدوج.
- عند single click يعيد `toggle.click()` كي يمر السلوك عبر الـOwner الأصلي.
- عند double click يفتح profile controls.

لا تضف Toggle ثانٍ داخل edge render owner أو keyboard module.

### 3.4 Measurement lifecycle

العمل المؤجل الناتج عن refresh يجب أن يكون cancellable ومربوطًا بالوثيقة الحالية. لا تضف `setTimeout`/`requestAnimationFrame` متكررة على refresh كحل مستقل إذا كان يمكن جدولتها عبر `AlmdinaMeasurementLifecycle` أو `AlmdinaDocumentContext`.

جدول القياسات مسجل أيضًا كـdocument surface داخل `AlmdinaDocumentContext`. بعد كل base render يعلن Operator جيل render جديدًا، ثم يشغّل `AlmdinaMeasurementLifecycle` جميع feature reconcilers المسجلة بالترتيب نفسه قبل اعتماد الجاهزية. إذا أفرغ Frappe حقل HTML أو وصل feature asset متأخرًا، تفشل الجاهزية مغلقة وتعيد surface recovery بناء الجدول الحالي فقط؛ لا تستدعي `frm.refresh()` ولا تعيد تحميل الطلب ولا تسمح لعمل وثيقة قديمة بالكتابة في الحالية.

### 3.5 Cutting-plan content

`door_cutting_order_plan_content_ux.js` Orchestrator، وليس owner للـCSS أو focus dialog أو responsive board math. هذه المسؤوليات تعيش في `plan_content_styles.js` و`plan_board_presenter.js`.

### 3.6 Shop Floor Inbox

صفحة Shop Floor Inbox لها composition root صغير. لا تعيد `frappe.call()` أو server endpoints إلى renderer/controller/interactions؛ النقل ملك `api.js`، والحالة ملك `state.js`، والتحويل النقي ملك `view_model.js`.

## 4. ملاحظة توافق مهمة حول Edge Observers

وحدتا `door_cutting_order_multi_edge_ux.js` و`door_cutting_order_edge_profile_controls_ux.js` ما زالتا تحتويان إنشاء الـObservers التاريخية لأسباب توافق وتقليل blast radius أثناء F6.4. لكنهما **ليستا runtime owners لتلك المراقبة بعد الإغلاق**.

`door_cutting_order_edge_render_owner.js` يستدعي feature renderers، ثم يفصل الـObservers التاريخية (`_dcoSideEdgeObserver` و`_dcoCompactEdgeProfileControlsObserver`) ويحتفظ بStructural Observer واحد فقط.

قاعدة التطوير: لا تعِد تفعيل الـObservers القديمة كمالكين مستقلين. يمكن حذف construction code لاحقًا فقط ضمن refactor محلي مستقل لوحدتي القشاط مع اختبارات مناسبة.

## 5. Public APIs التي تعتمد عليها الحدود الحالية

- `window.AlmdinaFrontend`
- `window.AlmdinaDocumentContext`
- `window.AlmdinaMeasurementLifecycle`
- `window.AlmdinaTablePerformanceUX`
- `window.AlmdinaFastEntryKeyboardUX`
- `window.AlmdinaMultiEdgeBanding`
- `window.AlmdinaEdgeProfileControls`
- `window.AlmdinaEdgeRenderOwner`
- `window.AlmdinaPlanContentStyles`
- `window.AlmdinaPlanBoardPresenter`
- `window.AlmdinaPlanContentUX`
- Shop Floor Inbox APIs: `AlmdinaShopFloorInboxApi`, `State`, `ViewModel`, `Renderer`, `Interactions`, `Dialogs`, `Controller`.

تغيير اسم أو معنى API عام يحتاج regression coverage للمستهلكين، لا مجرد تعديل الملف المالك.

## 6. Quality Gates بعد الإغلاق

### F4
يحمي Permission frontend، DCO document context، production settings separation وsyntax/runtime contracts الأساسية.

### F5
يحمي Shop Floor Inbox composition، transport/state/view-model/rendering/interactions/controller boundaries والـview-model simulations.

### F6
يحمي Measurement lifecycle، cutting-plan ownership، operator/edge ownership، JavaScript syntax ومحاكاة cancellation/freshness/layout helpers.

### F7
`f7-refactor-closure.yml` هو Aggregate frontend closure gate. يعيد تشغيل العقود الخفيفة والقابلة للتشغيل بدون Frappe runtime من F4/F5/F6، ثم يشغّل `test_frontend_refactor_closure.py` لمنع structural regression في ownership map نفسه.

هذا لا يلغي اختبارات Frappe/server/domain الخاصة بكل Feature؛ بل يضيف Gate معماريًا سريعًا يمنع العودة إلى نفس نوع الـdebt الذي استهدفه الـrefactor.

## 7. بروتوكول التغيير بعد F7

عند تعديل هذه المسارات:

1. حدّد الـOwner من الجدول أعلاه قبل الكتابة.
2. لا تنشئ Patch أو Observer موازٍ قبل إثبات أن الـOwner الحالي لا يستطيع استيعاب السلوك.
3. حافظ على server authorization كمصدر الحقيقة؛ UI visibility ليست Authorization.
4. شغّل الاختبارات الخاصة بالـOwner ثم F7 closure gate عند تغييرات frontend واسعة.
5. أي تغيير في lifecycle model أو authorization model أو الحدود العامة يعد Broad Refactor ويحتاج ADR/موافقة صريحة وفق `07_CHANGE_RULES.md` و`ARCHITECTURE_FREEZE.md`.
6. الدمج يتم فقط بعد مراجعة الاختبارات والـdiff والموافقة على نطاق التغيير.

## 8. تعريف الإغلاق

تعتبر سلسلة F4–F7 مغلقة معماريًا عندما:

- لا يوجد legacy operator patch في runtime أو repository.
- لا يوجد duplicate DCO asset registration.
- كل DCO asset مسجل يشير إلى ملف موجود.
- Measurement work المتكرر له lifecycle owner.
- Edge structural rendering له runtime owner واحد.
- Cutting-plan content orchestrator لا يملك CSS/board-focus responsibilities.
- Shop Floor Inbox يبقى مفصولًا إلى transport/state/view-model/rendering/interactions/dialogs/controller.
- Aggregate F7 gate أخضر.

بعد تحقق ذلك، العمل التالي يكون Feature/Fix داخل الحدود الحالية، لا استمرار refactor مفتوح بلا نهاية.
