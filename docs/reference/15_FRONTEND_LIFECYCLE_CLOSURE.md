# 15 — Frontend Lifecycle Closure

> **Status:** Canonical lifecycle contract
> **Framework:** Frappe / ERPNext v16
> **Non-goals:** UI redesign, business/authorization/workflow/schema changes, product-scope expansion

## 1. النموذج المعتمد

```text
Synchronous shell
        ↓
Long-lived mount
        ↓
inactive ⇄ active visits
        ↓
final remount/dispose
```

- shell موجود قبل أن يطلق Frappe أول `show`.
- `show` المكرر أثناء الزيارة نفسها لا يبدأ load ثانيًا.
- `hide` يبطل القراءات والعمل المؤجل المرتبط بالزيارة ولا يتلف state المقصودة.
- bootstrap failure المخفي يبقى بلا alert ويُعاد عند أول زيارة مرئية لاحقة.
- dialog/prompt/confirm تملكه الزيارة ويُغلق عند `hide`؛ callback مخفي لا يبدأ mutation جديدة.
- الزيارة الجديدة تقرأ server truth مرة واحدة، إلا عند وجود dirty edit session.

## 2. جرد Frappe Pages ومالكوها

| Page | Lifecycle owner | سياسة العودة |
|---|---|---|
| `factory-permissions` | controller + shared activation helper | تحميل حديث إذا كانت clean؛ الحفاظ على dirty role edit |
| `factory-workforce` | controller + shared activation helper | console حديث واحد |
| `factory-production-settings` | controller + shared activation helper | settings حديثة واحدة |
| `shop-floor-inbox` | Shop Floor controller/state | context + inbox/archive حديثة؛ الحفاظ على mode/search |
| `factory-master-data` | `ProductionRoutingWorkflowPage` | عدم استبدال dirty routing editor؛ تحميل حديث عند clean |
| `factory-approval-queue` | inline page activation owner | context/list حديثان |
| `factory-plan-archive` | inline page activation owner | archive context حديث |
| `factory-stock-settings` | inline compatibility owner | قراءة حديثة؛ لا يعيد الصفحة إلى Active Scope |
| `factory-system-preflight` | inline diagnostic owner | إعادة تشغيل الفحص عند كل زيارة |
| `factory-performance-benchmark` | inline diagnostic owner | لا تشغيل تلقائي؛ حماية نتيجة التشغيل من hidden commit |
| `door-drawing` | bounded documentation adapter + shared activation | route الأحدث فقط يُفتح لكل show صالح؛ bootstrap القديم لا يفتح بعد hide |

## 3. Form / List / Report surfaces

| Surface | العقد |
|---|---|
| Door Cutting Order Form | `AlmdinaDocumentContext` يملك identity/generation وtimers/frames/observers؛ أوامر الإنتاج/المراجعة/الاعتماد/DXF/الطباعة/edge override تتحقق من المستند النشط قبل UI أو mutation مؤجلة؛ اختبارات `A → B → A` إلزامية |
| Door Cutting Order List | role-flag response يحتاج generation حديثًا وList نشطة؛ hide يبطل العرض المجدول والطلب |
| Replacement Piece Form | request/name guard + `window.cur_frm === frm`؛ حوارات مملوكة للـroute وhidden mutation تُعلّم المستند لإعادة التحميل عند العودة |
| Production Routing / Edge Banding Type | hooks متزامنة؛ لا async lifecycle محلي |
| Query Reports | ملفات إعداد filters فقط؛ lifecycle القراءة ملك Frappe Query Report |
| Special Shape Documentation | يبقى bounded subsystem؛ page adapter فقط يربط تفعيله بـFrappe |

## 4. قواعد التنفيذ الإلزامية

1. لا تنشئ controller متأخرًا ثم تفترض أنه شاهد أول `show`.
2. استخدم `bindActivationLifecycle` مرة واحدة لكل wrapper؛ استبدال owner نشط ينفذ deactivation ثم dispose حتى لا تقبل قراءاته القديمة.
3. دالة load تبدأ فقط إذا كان surface نشطًا.
4. قبل كل state/DOM commit تحقق من request token ومن active surface.
5. `onDeactivate` يبطل كل read gate وtimer/frame متعلق بالزيارة.
6. لا تعرض success/error/dialog لعملية اكتملت على surface مخفي.
7. لا تعِد تحميل edit session dirty تلقائيًا.
8. route parameters قد تتغير مع `show` مكرر للـwrapper نفسه؛ الـroute-aware adapter يعالجها دون مضاعفة listeners.
9. لا تستخدم refresh كامل أو observer جديد كبديل عن ownership الصحيح.
10. أي Frappe Page جديدة تدخل جرد هذا الملف وتحصل على hide/show/stale/remount regression test.
11. أي dialog طويل العمر يُسجل لدى مالك مرئي (`createDialogOwner` أو مالك مكافئ) ويُغلق في `onDeactivate`.

## 5. Quality gate

الإغلاق محمي بـ:

- `tests/js/page_revisit_refresh.test.js`
- `tests/js/page_foundation_bootstrap.test.js`
- `tests/js/admin_page_lifecycle.test.js`
- `tests/js/project_frontend_lifecycle.test.js`
- `tests/test_project_frontend_lifecycle_contract.py`
- DCO document/navigation/list contracts القائمة
- Static Checks وF7 وSecurity regressions وFrappe v16 Integration

## 6. Definition of Done

لا تعتبر واجهة جديدة سليمة لمجرد أن الزيارة الأولى تعمل. يجب أن تثبت الاختبارات:

1. first show قبل/بعد اكتمال assets.
2. hide أثناء read ثم منع الاستجابة القديمة.
3. revisit يبدأ قراءة حديثة واحدة.
4. duplicate show لا يكرر العمل.
5. remount لا يضاعف listeners أو يسمح للمالك القديم بالكتابة.
6. dirty state محفوظ.
7. mutation مخفية لا تعرض UI قديمة، والزيارة التالية تستعيد server truth.
8. dialog مفتوح يُغلق عند hide، وbootstrap failure مخفي يُعاد بأمان عند revisit.
