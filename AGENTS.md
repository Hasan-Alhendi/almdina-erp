# AGENTS.md — Almdina ERP Coding Contract

هذا الملف ملزم لأي مطور أو Coding AI يعمل داخل هذا المستودع.

## اقرأ قبل التعديل

بالترتيب:

1. `docs/reference/README.md`
2. `docs/PRODUCT_SCOPE_v1.1.md`
3. `docs/reference/02_ARCHITECTURE.md`
4. `docs/reference/07_CHANGE_RULES.md`
5. المرجع المتخصص للميزة: Workflow / Security / Cutting-DXF / Data-UI / Testing.

## قواعد غير قابلة للتفاوض

- لا تغيّر سلوكًا خارج نطاق الطلب الحالي بحجة “التنظيف”.
- بعد Stage 15، لا تبدأ Broad Refactor من نفسك. التغيير الافتراضي Targeted ومحدود.
- `domain/` يجب أن يبقى Framework-free ولا يستورد Frappe أو الطبقات الخارجية.
- `application/` يجب أن يبقى Framework-free ولا يعتمد على `services`, `infrastructure`, `doctype`, `page`, `report`, `presentation`.
- لا تضع Business Logic جديدًا في JavaScript أو Print Format أو Frappe handler إذا كان يمكن أن يعيش في Domain/Application.
- لا تستخدم Role name ثابتًا كسلطة تجارية. استخدم Capability + document scope + lifecycle + stage operational role + assignment حسب الحالة.
- `System Manager` ليس Factory Superuser تلقائيًا. `Administrator` هو الاستثناء الصريح.
- لا تكشف التكلفة الداخلية أو الحقول المالية لمستخدم لا يملك `view_costs` أو الـCapability المالية المطلوبة.
- لا تُدخل البيانات المالية داخل Operational/Cutting snapshots التي يراها غير الماليين.
- لا تعتمد على اسم Document أو File يرسله العميل وحده. تحقق من Document scope/parent/assignment لتجنب IDOR.
- لا توسّع Legacy compatibility facades ولا تبنِ Feature جديدًا فوق Tombstone/retired endpoint.
- لا تضف Stock/Warehouse/Reservation/Consumption/Board Remnant behavior جديدًا؛ هذه خارج Active Product Scope v1.1.
- لا تُضعف Test موجودًا كي يمر التعديل. أصلح السبب أو اشرح تعارض المتطلب مع الـContract.
- أي نص يملكه التطبيق ويُضاف أو يُعدّل للمستخدم (واجهة، زر، رسالة، تقرير، طباعة/PDF) يلتزم إلزاميًا بـ`FE-ARCH-010 — Localization by Design`، مع الترجمة والاختبارات، حتى دون طلب صريح من المستخدم.
- أي Schema/Data migration يجب أن يكون Idempotent ويُختبر مع `migrate` مرتين.

## بروتوكول التنفيذ المبني على الأدلة

- قبل التعديل، حدّد نتيجة قابلة للتحقق وافتراضاتك المؤثرة على صحة الحل، وافحص التنفيذ والاختبارات الحالية؛ لا تستنتج الحالة من محادثة سابقة.
- عند إصلاح Bug، أثبت المشكلة قدر الإمكان، وحدّد أول boundary تنكسر فيه القاعدة، ثم أضف Regression test مع أصغر إصلاح جذري صحيح. لا تُخفِ نقص الدليل بادعاء نجاح غير مثبت.
- لا تضحِّ بسلامة التصنيع أو Security أو تاريخ الخطط من أجل تحسين شكلي أو تقليل الأسطر/الملفات. صحة DXF الهندسية وحدها لا تثبت صلاحية NC للماكينة.
- عند تعارض طلب أو وثيقة مع عقد تصنيع/أمان/بيانات محفوظة، اذكر التعارض ولا تنفذ تغييرًا غير آمن ضمنيًا. في الغموض غير الحرج والقابل للعكس، وثّق الافتراض الأدنى وتابع ضمن النطاق.
- تحسينات الخوارزمية تُقيّم على حالات مرجعية ثابتة، بمدخلات وميزانية متماثلة ونتائج نجاح وتراجع معلنة؛ لا تدّعِ الوصول للأمثلية دون برهان.
- تفاصيل التنفيذ والاختبارات والعزل والتوثيق في `docs/reference/07_CHANGE_RULES.md` و`08_TESTING_QUALITY.md` و`09_OPERATIONS_RELEASE.md`. لا تنشئ نسخًا متعارضة من هذه القواعد.

## قبل كتابة الكود

اكتب Change Contract مختصرًا في تفكيرك/PR:

```text
Goal:
In scope:
Out of scope:
Invariants:
Localization/i18n impact:
Expected files/layers:
Permission impact:
Data/migration impact:
Tests required:
Rollback risk:
```

إذا وجدت أن التعديل يحتاج ملفات غير متوقعة أو يغير Invariant، توقف عن توسيع النطاق وراجع السبب أولًا.

## Definition of Done

- السلوك المطلوب يعمل.
- السلوك غير المرتبط لم يتغير.
- Architecture boundaries محفوظة.
- Security/financial boundaries محفوظة.
- أي نص جديد أو معدل ظاهر للمستخدم يستوفي `FE-ARCH-010` مع الترجمات المطلوبة وأدلة الاختبار المناسبة.
- اختبارات الوحدة/العقود ذات الصلة مضافة أو محدثة.
- GitHub Actions المطلوبة خضراء.
- Documentation تُحدّث إذا تغير Contract أو Workflow أو Capability أو UI entry point أو Deployment behavior.
- التقرير النهائي يذكر الملفات المتغيرة والاختبارات والمخاطر وأي شيء لم يتم التحقق منه.

## Git workflow

- Feature branch مستقلة.
- Target الافتراضي للتطوير: `Develop`.
- لا تعدّل `main` إلا ضمن Release صريح.
- افحص Diff كاملًا قبل الدمج.
- PR واحد = Scope مفهوم واحد قدر الإمكان.