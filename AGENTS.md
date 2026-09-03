# AGENTS.md — Almdina ERP Engineering Contract

هذا الملف ملزم لأي مطور أو Coding AI يعمل داخل مستودع Almdina ERP.

الهدف الأساسي:

> نفّذ المطلوب بأصغر Blast Radius يمكن إثباته، دون كسر سلوك غير مرتبط، ودون تجاوز Architecture أو Security أو Business Contracts الحالية.

نجاح Feature أو Fix لا يعني فقط أن المطلوب يعمل؛
يجب أيضًا التأكد أن السلوك المهم المجاور لم يتراجع.

---

# 1. مصادر الحقيقة

لا تعتمد على محادثة سابقة أو ذاكرة قديمة لتحديد حالة المشروع الحالية.

اقرأ بالترتيب:

1. `docs/reference/README.md`
2. `docs/PRODUCT_SCOPE_v1.1.md`
3. `docs/reference/02_ARCHITECTURE.md`
4. `docs/reference/07_CHANGE_RULES.md`
5. المرجع المتخصص حسب منطقة التغيير:
   - Workflow → `03_WORKFLOWS.md`
   - Security / Permissions → `04_SECURITY_PERMISSIONS.md`
   - Cutting / Drawing / DXF → `05_CUTTING_DRAWING_DXF.md`
   - Data / UI ownership → `06_DATA_UI_MAP.md`
   - Testing / CI → `08_TESTING_QUALITY.md`
   - Frontend → `13_FRONTEND_ARCHITECTURE.md`
   - Frontend ownership after refactor → `14_FRONTEND_REFACTOR_CLOSURE.md`

الترتيب العام عند التعارض:

1. Active Product Scope.
2. Architecture Freeze + Canonical contracts.
3. Current source code + executable tests.
4. Specialized reference documentation.
5. Historical documentation.
6. Previous conversations.

إذا طلب المستخدم صراحة تغيير Contract مجمد، لا ترفضه تلقائيًا؛
وضّح أنه Contract change وقد يحتاج ADR أو Migration أو Security review قبل التنفيذ.

---

# 2. القاعدة الأولى

**Existing behavior is a contract until proven otherwise.**

لا تغيّر سلوكًا خارج نطاق الطلب الحالي لأنك:

- وجدته غير مثالي.
- تستطيع تنظيفه.
- تريد توحيد الكود.
- رأيت فرصة Refactor.
- تعتقد أن UX آخر سيكون أفضل.
- وجدت Bug آخر أثناء العمل.

أي مشكلة غير مرتبطة تُذكر في التقرير فقط ولا تُصلح داخل نفس Scope،
إلا إذا كان إصلاح المطلوب مستحيلًا بدونها.

---

# 3. لا تبدأ بالكود

قبل أي تعديل:

1. افهم User-visible behavior المطلوب.
2. تتبع التنفيذ الحالي.
3. حدد Root Cause.
4. حدد الـPrimary Owner للسلوك.
5. اقرأ الاختبارات الحالية التي تحميه.
6. حدد الـAdjacent Surfaces التي قد تتأثر.
7. حدد أصغر مجموعة Layers/Files مطلوبة.
8. بعدها فقط ابدأ بالتعديل.

لا تستخدم تعديلات عشوائية عبر عدة طبقات للتجربة قبل فهم السبب.

---

# 4. Change Contract إلزامي

قبل Feature/Fix اكتب:

```text
Goal:
User-visible behavior:

Root cause:

In scope:
Out of scope:

Primary owner:
Adjacent owners / regression surfaces:

Invariants that must stay unchanged:

Expected layers/files:

Permission/security impact:
Financial data impact:
Schema/migration impact:

Targeted tests:
Adjacent regression tests:
Required CI:

Rollback risk:
Docs affected:
```

إذا احتاج التنفيذ ملفات أو Layers لم تكن متوقعة:

> لا توسع Scope تلقائيًا. افهم السبب أولًا.

---

# 5. Minimal Change

بعد Architecture Freeze، الوضع الافتراضي هو:

> Targeted Feature / Targeted Fix.

Local Refactor مقبول فقط عندما:

- يكون داخل Boundary واضحة.
- لا يغير Business/Public Contract.
- توجد اختبارات تحميه.
- وله سبب مباشر متعلق بالمهمة.

Broad Refactor الذي يغير أحد التالي يحتاج موافقة صريحة وADR عند الحاجة:

- Layer boundaries.
- Authorization model.
- Order lifecycle.
- Production routing semantics.
- Snapshot architecture.
- Product scope.
- Aggregate ownership.
- Frontend architecture الأساسية.

---

# 6. Architecture Boundaries

## Domain

`domain/`:

- Framework-free.
- لا يستورد Frappe.
- لا يعتمد على Infrastructure أو Services أو UI.

Business Rules والحسابات الخالصة تعيش هنا.

## Application

`application/`:

- Framework-free.
- ينسق Use Cases.
- يعتمد على Domain وContracts/Ports الداخلية.

لا يعتمد على:

- `services`
- `infrastructure`
- `doctype`
- `page`
- `report`
- `presentation`

## Infrastructure

يمتلك:

- Frappe persistence.
- repositories.
- files.
- framework adapters.
- external integration details.

## Services / API

يجب أن تكون Thin boundaries:

- authorization.
- input translation.
- wiring.
- calling Application.

لا تكرر Business Rules الموجودة في Domain/Application.

## Frontend

Presentation layer فقط.

لا تجعل JavaScript مصدرًا موازيًا لـ:

- Business Rules.
- Authorization.
- Lifecycle.
- Financial formulas.

---

# 7. Owner-first Rule

قبل إنشاء:

- Helper.
- Patch.
- Observer.
- Store.
- Global state.
- API path.
- Renderer workaround.
- New orchestrator.

ابحث عن الـOwner الحالي.

القاعدة:

> Modify the owner; do not bypass the owner.

خصوصًا بعد Frontend Refactor:

- لا تنشئ Observer ثانيًا ينافس Observer موجودًا.
- لا تنشئ State ثانية لنفس الحقيقة.
- لا تستدعِ API مباشرة من Renderer إذا كان هناك API Adapter.
- لا تعيد إنشاء God Controller.
- لا تنشئ global patch لحل مشكلة محلية.
- لا تنقل Feature responsibility إلى shared foundation بلا سبب معماري.

إذا كان الـOwner الحالي غير قادر على استيعاب المطلوب بنيويًا، اشرح ذلك قبل تغيير Architecture.

---

# 8. Frontend Async & Lifecycle

افترض دائمًا أن المستخدم قد يغير الصفحة أو Document قبل وصول أي Async response.

أي request يمكن أن يصبح stale يجب أن يستخدم Contract مناسبًا مثل:

- request generation/token.
- latest-request-wins.
- document/page identity.
- cancellation.

ممنوع أن تحدث Response قديمة:

- Document جديد.
- Page غير فعالة.
- State لم تعد Current.
- UI يعود لسجل تمت مغادرته.

كذلك:

- Event registration يجب أن يكون idempotent أو له cleanup.
- Timers و`requestAnimationFrame` لها lifecycle ownership.
- MutationObserver له Owner واحد لكل Surface.
- Retry loops يجب أن تكون bounded.
- Hide/deactivation يجب أن تمنع stale commits عند الحاجة.
- Revisit لا يدمر dirty/unsaved state.
- لا تستخدم refresh loops كعلاج لمشكلة ownership.

خصوصًا في DCO:

> بيانات Order A يجب ألا تظهر مطلقًا داخل Order B بسبب cache أو async response قديمة.

وينطبق ذلك على:

- Order data.
- Cutting Plan.
- Costing.
- Permissions.
- Toolbar/actions.
- Drawing.
- DXF state.

---

# 9. Security & Permissions

Business authorization يعتمد على:

```text
Capability
+ Document scope
+ Lifecycle
+ Operational role when required
+ Assignment when required
+ Action-specific structural rules
```

ممنوع الاعتماد على Role name ثابت كسلطة تجارية.

لا تستخدم مثلًا:

```python
if "CNC Worker" in frappe.get_roles():
```

ولا في JavaScript:

```javascript
frappe.user_roles.includes("CNC Worker")
```

كبديل عن Authorization Contract.

`System Manager` ليس Factory Superuser تلقائيًا.

`Administrator` هو الاستثناء الصريح فقط حيث يسمح العقد.

إخفاء زر في Frontend = UX فقط.

> Server/Application authorization هو الحارس الحقيقي.

أي endpoint محمي يجب أن يبقى محميًا حتى عند استدعائه مباشرة دون UI.

---

# 10. لا تستخدم ignore_permissions كحل

ممنوع استخدام:

```python
ignore_permissions=True
```

كحل لمشكلة Runtime authorization.

عند فشل Action لمستخدم:

- افحص Capability.
- DocPerm.
- Permission level.
- Document scope.
- Assignment.
- Lifecycle.
- Authorization gateway.

ولا تتجاوز النظام.

يمكن استخدام privileged persistence فقط داخل trusted installation/migration/infrastructure boundaries عندما يكون مطلوبًا Framework-wise ومبررًا بوضوح.

---

# 11. Financial Safety

`view_orders` لا يعني `view_costs`.

لا:

- ترسل Cost ثم تخفيها بالـCSS.
- ترسلها بقيمة صفر بدل حذفها.
- تضع Internal Cost داخل Operational snapshot.
- تسمح لـReport/Print/API أن يصبح side channel للبيانات المالية.

Customer-facing documents وInternal financial documents يجب أن يحافظا على حدود صلاحياتهما.

---

# 12. Workflow & Production

لا hard-code ترتيب الأقسام إذا كان `Production Routing` يملكه.

لا تسمح للعامل بتنفيذ Stage:

- ليست Current.
- غير مسندة له.
- لا يملك Capability المطلوبة لها.

إلا إذا كان العقد الخاص بالفعل يسمح بذلك صراحة.

لا تعيد فرض Review/Approve القديم كشرط Mandatory دون Product Decision.

Planning stage يجب أن تحترم Cutting Plan approval gate.

ابدأ/أنهِ/Handoff/Revert/Delivery من خلال Domain/Application contracts الحالية.

---

# 13. Cutting Plan / DXF / Costing

Kerf وTrim وCut Dimensions وEdge deductions هي Business/Geometry rules مركزية.

لا تعيد حسابها بصيغ منفصلة في:

- UI.
- DXF.
- Print.
- Costing.

يجب أن تستهلك جميعها نفس الحقيقة.

قواعد ثابتة:

- Approved Cutting Plan لا تُعدل تلقائيًا.
- Draft أحدث لا يستبدل Production Plan بصمت.
- لا تعيد تشغيل optimizer لعرض تاريخ Approved قديم.
- DXF validation مستقل عن مجرد نجاح فتح الملف.
- File identifier وحده لا يمنح الوصول.
- Costing يجب أن يرتبط بالOrder والCutting Plan الصحيحين.
- لا تعرض Cost أو Plan من Document سبق فتحه.

---

# 14. Bug Fix يحتاج Regression Protection

عند إصلاح Bug:

1. حاول كتابة Regression test يعيد إنتاج المشكلة.
2. اجعله يفشل قبل الإصلاح قدر الإمكان.
3. طبق أصغر Fix صحيح.
4. أثبت أن الاختبار أصبح ناجحًا.
5. شغّل اختبارات Adjacent surfaces المهمة.

إذا تعذر Test آلي عملي:

- اشرح السبب.
- حدد Manual/UAT المطلوبة.

لا تعتبر إصلاح Screenshot واحد دليلًا كافيًا أن المشكلة انتهت.

---

# 15. الاختبارات

ابدأ بالأضيق ثم وسع حسب Blast Radius:

```text
Owner tests
→ Adjacent regression tests
→ Architecture/Security contracts
→ Frontend simulations
→ Frappe Integration when required
```

لا تضعف الاختبارات للوصول إلى Green CI.

ممنوع:

- حذف assertion لحل الفشل.
- تغيير expected result لمطابقة Regression غير مقصود.
- broad mocking لإخفاء المشكلة.
- skip غير مبرر.
- `continue-on-error`.
- `|| true` لتجاوز Quality Gate.

إذا تغير Contract عمدًا:

> Code + Tests + Canonical Documentation يجب أن تتغير معًا.

---

# 16. Schema & Migration

عند تغيير Schema أو معنى بيانات محفوظة اسأل:

- هل هناك Backfill؟
- هل Migration idempotent؟
- هل `migrate` مرتين آمن؟
- ماذا يحدث للبيانات التاريخية؟
- هل Snapshot القديمة يجب أن تبقى كما هي؟
- هل Rollback ممكن؟

لا تستخدم Runtime request كبديل دائم عن Migration لازمة.

---

# 17. Diff Review

قبل إعلان التعديل جاهزًا، راجع كل Changed Files.

ابحث عن:

- ملفات لا علاقة لها بالمهمة.
- accidental deletion.
- duplicate logic.
- debug code.
- generated/cache files.
- changed defaults.
- permission widening.
- lifecycle change غير مقصود.
- API contract change.
- CSS leakage.
- stale imports.
- schema changes غير متوقعة.

قاعدة:

> Small request + unexpectedly large diff = Stop and reassess.

---

# 18. Git Workflow

- كل Feature/Fix على Branch مستقلة من أحدث `Develop`.
- لا تعمل مباشرة على `main`.
- لا تعمل مباشرة على `Develop` كتدفق تطوير عادي.
- Target الافتراضي للـPR هو `Develop`.
- PR واحدة = Scope منطقي واحد قدر الإمكان.

قبل Final CI والدمج:

- تأكد أن Branch محدثة مع أحدث `Develop`.
- لا تعتمد على CI قديمة قبل تحديث Base.
- إذا تغير HEAD بعد Sync أو Fix، أعد الاختبارات المطلوبة.
- كل CI evidence يجب أن تخص Final PR Head SHA.

استخدم Expected Head SHA عند الدمج إذا كانت الأداة تدعمه.

---

# 19. Human Approval Gate

Coding AI يستطيع:

- إنشاء branch.
- تعديل الكود.
- إضافة tests.
- Commit/Push إلى feature branch.
- فتح PR.
- إصلاح CI.
- معالجة Review comments.
- إعلان PR جاهزة للمراجعة.

لكن:

> ممنوع دمج PR إلى `Develop` أو `main` دون موافقة بشرية صريحة في المحادثة الحالية.

نجاح CI ليس موافقة دمج.

عدم وجود Review comments ليس موافقة دمج.

طلب المستخدم السابق للFeature ليس موافقة دمج.

يجب وجود أمر واضح مثل:

```text
ادمج
ادمج مع Develop
وافق على الدمج
```

لا تستخدم Auto-Merge من نفسك.

---

# 20. Definition of Done

لا تعتبر المهمة مكتملة إلا إذا:

- Root Cause مفهوم.
- المطلوب يعمل.
- Scope بقي مضبوطًا.
- Primary Owner استُخدم.
- السلوك غير المرتبط لم يتغير وفق الأدلة المتاحة.
- Architecture boundaries سليمة.
- Security boundaries سليمة.
- Financial isolation سليمة.
- Async/lifecycle safety محفوظة عند الحاجة.
- Regression protection موجودة.
- Targeted tests ناجحة.
- Adjacent regressions المهمة ناجحة.
- Required CI خضراء على Final Head.
- Branch محدثة مع `Develop`.
- Diff تمت مراجعته بالكامل.
- Documentation حدثت إذا تغير Contract.
- لا توجد debug/generated files غير مقصودة.

---

# 21. التقرير بعد التنفيذ

بعد كل مرحلة كبيرة قدم:

```text
Done:
Next:
Remaining:
Tests:
```

وعند اكتمال Feature/Fix قدم:

```text
Root Cause:
Changed:
Files:
Tests:
CI:
Regression Protection:
Security/Permission Impact:
Data/Migration Impact:
Risks:
Not Verified:
Unrelated Findings:
Final PR Head SHA:
```

لا تقل فقط:

> تم الاختبار بنجاح.

اذكر الاختبارات والـWorkflows والـSHA الذي تم التحقق منه.

---

# القاعدة النهائية

إذا كان أمامك خياران:

A. Fix سريع يعتمد على Workaround أو له Side Effects غير واضحة.

B. Fix صغير، داخل الـOwner الصحيح، وله Regression Protection واضحة.

اختر B.

> الهدف ليس كتابة أكبر كمية كود.
>
> الهدف هو أصغر تغيير صحيح يمكن إثبات سلامته مع بقاء Almdina ERP مستقرًا.
