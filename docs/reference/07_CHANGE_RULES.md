# 07 — قواعد التطوير والتعديل بدون تخريب

> **Status:** Canonical engineering policy  
> **Audience:** كل مطور وCoding AI

## 1. القاعدة الأولى

**التعديل الجيد يحقق الهدف بأصغر Blast Radius يمكن إثباته.**

المشكلة المتكررة الأخطر ليست كتابة كود لا يعمل فقط، بل إصلاح Feature وتغيير Feature أخرى لا علاقة لها بسبب refactor واسع أو shared helper غير مفهوم.

## 2. Change Contract قبل الكود

لكل Feature/Fix اكتب:

```text
Goal:
User-visible behavior:
Localization/i18n impact:
In scope:
Out of scope:
Invariants that must stay unchanged:
Expected layers/files:
Permission/security impact:
Financial data impact:
Schema/migration impact:
Tests required:
Rollback risk:
Docs affected:
```

إذا بدأ Diff يخرج عن `Expected layers/files`، فهذا Signal للمراجعة وليس دعوة لتوسيع Scope تلقائيًا.

## 3. تصنيف التغيير

### Targeted feature/fix — الافتراضي بعد Stage 15

مسموح. عدّل العقد المطلوب فقط وأضف regressions.

### Local refactor

مسموح إذا:

- داخل boundary واحدة.
- لا يغير public/business contract.
- مغطى بالاختبارات.
- يقلل duplication فعليًا.

### Broad refactor

أي تغيير يغير layer boundaries أو authorization model أو order lifecycle أو snapshot architecture أو product scope. يحتاج ADR + موافقة صريحة قبل التنفيذ.

## 4. قواعد الطبقات

- Business rule جديد -> Domain.
- Workflow/use case -> Application.
- DB/Frappe/file -> Infrastructure adapter.
- RPC endpoint -> Service thin + explicit authorization contract.
- UI -> Presentation/Page/JS، بدون duplicate business formula.

لا تحل Dependency cycle بنقل المنطق عشوائيًا إلى Service.

## 5. قواعد الأمان

أي endpoint/action جديد يجب أن يجيب بوضوح:

1. ما Capability؟
2. ما Document scope؟
3. هل lifecycle يضيّق الفعل؟
4. هل operational role مطلوب؟
5. هل assignment مطلوب؟
6. هل payload يحوي تكلفة داخلية؟
7. هل File/child document scoped للparent؟
8. ما السلوك عند missing/invalid identifier؟ Fail closed.

## 6. قواعد الصلاحيات

- لا تضف `if "Role Name" in frappe.get_roles()` كAuthorization تجاري جديد.
- لا تجعل System Manager bypass عام.
- لا تعطي Supporting DocType permissive grants فقط لأن endpoint فشل؛ افهم Frappe grant + runtime narrowing.
- أي Capability جديدة تُضاف إلى catalog وتُعرض في إدارة الصلاحيات وتُختبر.

## 7. قواعد البيانات المالية

- لا تجعل `view_orders` تعني `view_costs`.
- لا تُرسل حقولًا حساسة ثم تخفيها CSS/JS.
- لا تضع Cost في Operational snapshot.
- إذا أضفت Print/Report جديدًا، صنفه Customer-facing أو Internal financial وحدد Capability مستقلة عند الحاجة.

## 8. قواعد Workflow

- لا hard-code ترتيب الأقسام إذا كان `Production Routing` يملكه.
- لا تسمح للعامل بتنفيذ Stage غير current أو غير مسندة إليه إذا كان action assignment-scoped.
- لا تُعيد فرض Review/Approve القديم كشرط mandatory دون قرار منتج جديد.
- Planning Stage يجب أن تحترم plan approval gate.

## 9. Schema وMigration

إذا أضفت/غيرت Field أو معنى بيانات محفوظة:

- هل البيانات القديمة تحتاج backfill؟
- هل patch idempotent؟
- هل تشغيل `migrate` مرتين آمن؟
- هل snapshot/history يجب أن يبقى كما هو بدل backfill؟
- هل rollback ممكن بعد migration؟

لا تستخدم runtime request كبديل دائم لMigration لازمة.

## 10. UI/UX

- حافظ على نفس البيانات الأساسية بين desktop/mobile، واختلف في layout فقط حيث يمكن.
- لا تجعل حل mobile يفسد جدول desktop أو العكس.
- حافظ على keyboard flow في شاشات الإدخال الكثيف.
- أي نص واجهة أو رسالة/تقرير/طباعة يُضاف أو يتغيّر يجب أن يستوفي `FE-ARCH-010 — Localization by Design` تلقائيًا؛ لا تُؤجل الترجمة لما بعد انتهاء الـFeature.
- Button visibility تأتي من permission/action context؛ Server يظل الحارس.
- عند إصلاح stale data بعد navigation، أصلح ownership/async lifecycle بدل إضافة `refresh()` عشوائي دائمًا.

## 11. الاختبارات

- Bug fix يبدأ Regression test يثبت الخطأ قدر الإمكان.
- لا تعدّل expected output لتطابق bug الجديد.
- إذا كشف Refactor Test قديمًا غير صحيح، وثق Contract change صراحة بدل إسكات الاختبار.
- شغّل tests المتخصصة ثم CI الكامل المناسب.

## 12. Git/PR

- Branch مستقلة من آخر `Develop`.
- لا تكتب مباشرة على `Develop` أثناء العمل الطويل.
- PR إلى `Develop`.
- راجع changed files كاملة.
- لا تلمس `main` إلا Release صريح.
- استخدم expected head SHA عند الدمج عندما تكون الأدوات تدعمه لتجنب race.

## 13. PR description المطلوبة

يجب أن تذكر:

- What changed.
- Why.
- What explicitly did not change.
- Security/permission impact.
- Data/migration impact.
- Tests/CI evidence.
- Known limits.

## 14. Definition of Done

Feature/Fix غير منتهية إذا كان أحد التالي مفقودًا:

- behavior صحيح.
- authorization صحيح.
- نصوص التطبيق الجديدة أو المعدلة الموجهة للمستخدم قابلة للترجمة، وترجماتها المطلوبة واختباراتها مستوفاة وفق `FE-ARCH-010`.
- unrelated regression غير موجود وفق الاختبارات المتاحة.
- migration آمنة إن وجدت.
- CI خضراء.
- docs محدثة عند تغير Contract.

## 15. عندما يستخدم AI المشروع

AI يجب أن:

- يقرأ `AGENTS.md`.
- لا يعتمد على محادثة سابقة وحدها كمصدر للكود الحالي.
- يقرأ الملفات الحالية قبل التعديل.
- يذكر مبكرًا إن اكتشف تضاربًا بين المطلوب والـArchitecture Freeze.
- ينفذ Stage/feature على branch، لا يخلط ميزتين كبيرتين في Diff واحدة.
- يقدم بعد كل مرحلة: Done / Next / Remaining / Tests.

## 16. بروتوكول التنفيذ المبني على الأدلة لـ Coding Agents

هذه القواعد تُكمّل Change Contract والحدود المجمدة أعلاه، ولا تغيّر Product Scope أو Business Contract أو تفرض Refactor عامًا.

### 16.1. فكّر وحدّد معيار النجاح قبل الكود

- ابدأ بسلوك مطلوب **قابل للملاحظة والاختبار**: المدخلات، النتيجة المتوقعة، شروط الرفض، وما يجب أن يبقى كما هو. استخدم معيارًا قصيرًا يناسب حجم المهمة، لا دراسة مطولة لكل تعديل صغير.
- ميّز بين الواقع المثبت من الكود/الاختبارات الحالية، والفرضية، والتفضيل التصميمي؛ اذكر الافتراض المؤثر عند الحاجة. ابحث عن أبسط حل يحترم العقود، دون abstractions أو configurability افتراضية.
- غموض غير مؤثر وقابل للعكس: اختر الافتراض الأدنى، صرّح به وتابع. تعارض يؤثر على سلامة التصنيع أو الصلاحيات أو البيانات المالية أو تاريخ الخطط أو migration غير قابلة للعكس: لا تنفّذ الجزء الخطر قبل حسم العقد، وقدّم الأدلة والبدائل بوضوح.

### 16.2. الإصلاح الجذري والتغيير الجراحي

- شخّص أول boundary يظهر فيها الانحراف عن العقد، لا العرض النهائي فقط. أعد إنتاج العطل باختبار أو دليل موثق إن أمكن، ثم أثبت أن التعديل يمنع عودته.
- كل سطر متغير يجب أن يخدم الهدف أو اختباراته أو تحديث عقده. لا «تنظّف» كودًا مجاورًا، ولا تعِد كتابة وحدة كاملة لمجرد أنها قديمة، ولا تختزل كودًا على حساب Validation أو Error Handling له مدخلات ممكنة.
- نطاق التعديل هو **أصغر تغيير كامل وصحيح**، لا أقل عدد أسطر أو ملفات بأي ثمن. إذا استلزم الجذر تعديل عدة boundaries، التزم Change Contract وأعد تقييم النطاق قبل التوسيع.

### 16.3. الدليل في مسائل القص والتصنيع

- افصل بين `valid cutting layout` و`valid DXF geometry/export` و`machine-ready NC`؛ النجاح في مرحلة لا يثبت تلقائيًا ما بعدها. لا تعلن جاهزية تشغيل CNC دون قيود الماكينة والريشة والتثبيت وتسلسل التحرير والتحقق العملي المناسب.
- عند تغيير optimizer أو DXF أو التصنيع، أثبت الحفاظ على عدد وهوية الدرف، Kerf، سياسة الهامش **المعتمدة حاليًا**، اتجاهات الدوران، العلاقات بين الفتحات والقطع، وحقوق/حالة اعتماد الخطة. لا تخترع سياسة هندسية عند اختلاف المتطلب عن المرجع؛ ارفع discrepancy أولًا.
- لا تُغيّر بصمات/لقطات خطط تاريخية أو تُسقط بوابات `REVIEW_REQUIRED` / `PERSISTED_STALE` لإظهار نجاح تجريبي. طبّق `CUTTING_PLAN_RELEASE_SAFETY.md` عند أي إصدار ذي أثر على الخطط.

### 16.4. التحسين بمقارنة قابلة لإعادة الإنتاج

- قارِن Baseline والمرشح على corpus ثابت موثق مع نفس المدخلات وKerf والهامش والماكينة وميزانية الزمن؛ سجّل Seed/إعدادات التنفيذ عند وجود عشوائية، والنتائج السلبية والإيجابية معًا.
- سلامة خطة التصنيع واكتمال الدرف شروط قبول أولًا. قيّم الألواح والفضلات ثم التنظيم الهندسي وتشتت القطع وطول/تعقيد المسارات **كمقاييس منفصلة**؛ لا تخلط مقياسًا تقديريًا بزمن CNC فعلي.
- لا تصف نتيجة محدودة الوقت بأنها `optimal` دون شهادة/حدّ رياضي يثبت ذلك. عند تعادل عدد الألواح، يجوز تحسين الهندسة بشرط عدم الإضرار بالقيود غير القابلة للتفاوض.

### 16.5. الانضباط في الوقت والتقارير والقواعد

- اقرأ الملفات الإلزامية أولًا، ثم فتّش الملفات والاختبارات المرتبطة بالمشكلة بدل مسح المستودع عشوائيًا؛ نفّذ اختبارات محددة قبل الاختبارات الشاملة الملائمة. لا تطل البحث دون فرضية جديدة أو دليل مفيد.
- لا تدّعِ تشغيل Test أو أداة أو آلة لم تُشغّلها فعليًا. التقرير النهائي يفرق بين **verified** و**inferred** و**not checked**، ويذكر SHA، الفحوص، التحسن والتراجع، والحدود المتبقية.
- لا تنسخ تعليمات متوازية من مجموعات خارجية إلى `AGENTS.md` و`CLAUDE.md` وCursor. السلطة واحدة (`AGENTS.md` والمرجع المتخصص)، والتعديل الجديد يُدمج في موضعه المختص مع إزالة التكرار داخل نطاقه فقط.
