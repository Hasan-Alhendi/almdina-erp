# Almdina ERP

نظام إدارة عمليات معمل MDF مبني على **Frappe / ERPNext v16**، ويغطي إدخال الطلبات، حسابات القص، خطة القص، الرسم الخاص، DXF، مسارات الإنتاج، الصلاحيات، التعويضات، المستندات المالية والتقارير ضمن نطاق المنتج الحالي.

> **ابدأ من هنا:** المرجع الرسمي الحالي للمشروع هو [`docs/reference/README.md`](docs/reference/README.md).
>
> **Runtime architecture baseline:** `75dba93dd7dd9b21b4aeb4e32113c7e7061e748e` — آخر Runtime baseline بعد Stage 14 وقبل إضافة توثيق Stage 15.
>
> **Active product scope:** [`docs/PRODUCT_SCOPE_v1.1.md`](docs/PRODUCT_SCOPE_v1.1.md).

## لمن هذا المستودع؟

- **الإدارة وصاحب المنتج:** اقرأ [نظرة عامة على النظام](docs/reference/01_SYSTEM_OVERVIEW.md).
- **مدخل البيانات والمشرف التشغيلي:** اقرأ [دورة الطلب والإنتاج](docs/reference/03_WORKFLOWS.md) و[خريطة الواجهات والبيانات](docs/reference/06_DATA_UI_MAP.md).
- **مسؤول الصلاحيات:** اقرأ [الصلاحيات والأمان](docs/reference/04_SECURITY_PERMISSIONS.md).
- **عامل الرسم/CNC:** اقرأ [القص والرسم وDXF](docs/reference/05_CUTTING_DRAWING_DXF.md).
- **المطور أو Coding AI:** اقرأ [المعمارية](docs/reference/02_ARCHITECTURE.md)، ثم [قواعد التعديل](docs/reference/07_CHANGE_RULES.md)، ثم [`AGENTS.md`](AGENTS.md).
- **QA:** اقرأ [الاختبارات وبوابات الجودة](docs/reference/08_TESTING_QUALITY.md).
- **DevOps/الإصدار:** اقرأ [التشغيل والإصدارات](docs/reference/09_OPERATIONS_RELEASE.md).

## النطاق الحالي باختصار

### داخل النطاق

- Door Cutting Order وإدخال القياسات.
- الأشكال العادية، الزاوية المقصوصة، والدرف الخاصة.
- القشاط لكل ضلع وحساب مقاسات القص.
- Cutting Optimization وخطط القص المعتمدة.
- الرسم الخاص وDXF import/export.
- مسارات إنتاج قابلة للضبط ومراحل مسندة للعاملين.
- الحوادث وReplacement Pieces.
- تكلفة التشغيل، سعر/مستند الزبون، والطباعة مع فصل الصلاحيات المالية.
- إدارة المستخدمين والأدوار والـCapabilities.
- التقارير التشغيلية والمالية المحمية بالصلاحيات.

### خارج النطاق النشط

المخزون والمستودعات والحجوزات والاستهلاك وStock Entry وBoard Remnants **ليست جزءًا من المنتج النشط v1.1**. قد تبقى ملفات تاريخية مرتبطة بها في المصدر لحماية الترقيات القديمة، لكنها ليست مرجعًا لميزات جديدة. راجع [`docs/PRODUCT_SCOPE_v1.1.md`](docs/PRODUCT_SCOPE_v1.1.md).

## قاعدة المشروع الأساسية

```text
Business rules        -> domain/
Use-case coordination -> application/
Frappe/persistence    -> infrastructure/
Framework endpoints   -> services/, doctype/, page/, report/
UI rendering          -> presentation/, JS, workspace, print formats
```

`domain` و`application` لا يعتمدان على Frappe. الصلاحيات التجارية تعتمد على **Capabilities** وليس أسماء Roles ثابتة. تفاصيل هذه الحدود مثبتة في [Architecture Freeze](docs/reference/ARCHITECTURE_FREEZE.md).

## حالة الوثائق القديمة

الملفات الموجودة مباشرة داخل `docs/` لم تُحذف حفاظًا على التاريخ والتتبع. لمعرفة أي ملف Canonical وأي ملف Supporting أو Historical راجع [`docs/README.md`](docs/README.md).

## قبل أي تعديل على الكود

1. اقرأ [`AGENTS.md`](AGENTS.md).
2. حدد نطاق التعديل وInvariants التي يجب ألا تتغير.
3. اقرأ المرجع الخاص بالمجال الذي ستعدله.
4. عدّل أقل عدد ممكن من الطبقات والملفات.
5. أضف/حدّث الاختبارات المناسبة ولا تُضعف Test قائمًا لتجاوز فشل.
6. افتح PR إلى `Develop`، وشغّل بوابات CI ذات الصلة قبل الدمج.

بعد Stage 15، أي **Broad Refactor** جديد يحتاج قرار معماري صريح؛ التطوير الافتراضي يصبح Targeted Feature Development.