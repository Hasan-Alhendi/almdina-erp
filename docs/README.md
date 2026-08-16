# خريطة توثيق Almdina ERP

هذا الملف يشرح **أي وثيقة يجب الوثوق بها ولماذا**. السبب في وجوده أن المستودع يحتوي وثائق من مراحل زمنية مختلفة، وبعضها يصف Features أو Architecture لم تعد ضمن المنتج النشط.

## 1. المرجع الرسمي الحالي — Canonical

ابدأ دائمًا من:

- [`reference/README.md`](reference/README.md) — بوابة المرجع.
- [`reference/01_SYSTEM_OVERVIEW.md`](reference/01_SYSTEM_OVERVIEW.md) — ماذا يفعل النظام.
- [`reference/02_ARCHITECTURE.md`](reference/02_ARCHITECTURE.md) — أين يعيش كل نوع من المنطق.
- [`reference/03_WORKFLOWS.md`](reference/03_WORKFLOWS.md) — دورة الطلب والإنتاج.
- [`reference/04_SECURITY_PERMISSIONS.md`](reference/04_SECURITY_PERMISSIONS.md) — Roles, Capabilities, scope, assignment.
- [`reference/05_CUTTING_DRAWING_DXF.md`](reference/05_CUTTING_DRAWING_DXF.md) — القص والرسم وDXF.
- [`reference/06_DATA_UI_MAP.md`](reference/06_DATA_UI_MAP.md) — DocTypes والواجهات ومصادر الحقيقة.
- [`reference/07_CHANGE_RULES.md`](reference/07_CHANGE_RULES.md) — قواعد التطوير بدون تخريب.
- [`reference/08_TESTING_QUALITY.md`](reference/08_TESTING_QUALITY.md) — CI والاختبارات.
- [`reference/09_OPERATIONS_RELEASE.md`](reference/09_OPERATIONS_RELEASE.md) — التشغيل والإصدار.
- [`reference/10_GLOSSARY.md`](reference/10_GLOSSARY.md) — قاموس المصطلحات.
- [`reference/ARCHITECTURE_FREEZE.md`](reference/ARCHITECTURE_FREEZE.md) — قرارات Stage 15 المجمدة.

## 2. حدود المنتج ومتطلبات العمل — Binding Business Sources

- [`PRODUCT_SCOPE_v1.1.md`](PRODUCT_SCOPE_v1.1.md): **الحدود الملزمة للنطاق الحالي**. ما هو Included/Excluded.
- [`REQUIREMENTS_v1.1_AR.md`](REQUIREMENTS_v1.1_AR.md): SRS عربي تفصيلي مهم لفهم نية العمل ومعايير القبول.
- [`USER_STORIES_v1.1_AR.md`](USER_STORIES_v1.1_AR.md): User Stories تفصيلية لفهم السيناريوهات.

> إذا كان هناك تفصيل تنفيذي قديم في Requirements/User Stories تعارض مع قرار معماري أحدث موثق في `reference/` ومثبت باختبارات حالية، لا تُرجع الكود تلقائيًا للسلوك القديم. اعتبره Documentation discrepancy يحتاج قرارًا صريحًا.

## 3. وثائق تخصصية داعمة — Supporting

- [`CUTTING_OPTIMIZER_V2.md`](CUTTING_OPTIMIZER_V2.md): سياق وتحليل محرك القص.
- [`SPECIAL_SHAPES.md`](SPECIAL_SHAPES.md): تفاصيل تاريخية/تخصصية للأشكال الخاصة.
- [`UAT_v1.0.md`](UAT_v1.0.md): سيناريوهات قبول ميدانية مفيدة، لكنها ليست مصدر Architecture.
- [`SETUP_v1.0.md`](SETUP_v1.0.md): إعداد قديم مفيد كمرجع، ويجب مقارنة أوامره مع `reference/09_OPERATIONS_RELEASE.md` قبل الاستخدام.
- [`permission-rollout-checklist.md`](permission-rollout-checklist.md): سجل/Checklist لمرحلة Rollout الصلاحيات.

## 4. سجلات تاريخية — Historical / Audit

هذه الملفات لا تُستخدم لتحديد السلوك الجديد وحدها:

- `REQUIREMENTS_v1.0.md`
- `IMPLEMENTATION_MATRIX_v1.0.md`
- `backend-legacy-audit.md`
- `backend-legacy-migration.md`
- `phase-13-final-security-report.md`

وجودها مقصود للتدقيق وتتبع القرارات السابقة.

## 5. ترتيب مصادر الحقيقة عند الاختلاف

1. **Active Product Scope** يحدد ما يجب أن يكون ضمن المنتج أصلًا.
2. **Architecture Freeze + Canonical Reference** يحدد الحدود الحالية وطريقة التنفيذ.
3. **Executable tests + current source code** يثبت السلوك الفعلي الحالي.
4. SRS/User Stories يشرح نية العمل التفصيلية؛ التعارض مع قرار أحدث يُرفع كقرار منتج/معمارية.
5. Supporting/Historical docs لا تتغلب على المصادر السابقة.

لا تصلح التعارض بصمت. سجّل ما تعارض ولماذا وأي مصدر تم اعتماده.