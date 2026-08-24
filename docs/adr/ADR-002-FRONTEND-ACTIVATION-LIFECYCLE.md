# ADR-002 — توحيد دورة تفعيل واجهات Frappe

> **Status:** Accepted
> **Date:** 2026-08-23
> **Decision owner:** Almdina ERP frontend architecture
> **Applies to:** Frappe Pages, custom List/Form async presentation, bounded page adapters

## السياق

Frappe v16 لا ينتظر Promise المعادة من `on_page_load` قبل تبديل الـcontainer وإطلاق `show`.
كما أن Desk يحتفظ بالصفحة مركبة ويستخدم `show`/`hide` للزيارات اللاحقة بدل إعادة إنشائها.
هذا يجعل الأنماط التالية غير آمنة:

- إنشاء الصفحة بعد تحميل assets غير متزامن.
- اعتبار mount مساويًا لكون الصفحة نشطة.
- حماية request من request أحدث فقط دون إبطاله عند `hide`.
- إعادة تحميل Frappe Page عند الزيارة دون احترام dirty state.
- قبول استجابة Form/List بعد أن يصبح surface آخر هو النشط.

## القرار

1. تُنشأ Frappe Page وحالة bootstrap المحايدة قبل أول async boundary.
2. لكل wrapper مالك activation واحد عبر `AlmdinaPageRevisit.bindActivationLifecycle`.
3. mount طويل العمر، بينما كل انتقال `inactive → active` زيارة مستقلة.
4. `hide` ينفذ deactivation ويبطل read gates؛ لا ينفذ dispose ولا يلغي mutation بدأت بإرادة المستخدم.
5. نتيجة القراءة لا تكتب state/DOM إلا إذا كان token حديثًا والسطح ما زال نشطًا.
6. نتيجة mutation المخفية يمكنها مزامنة state الضرورية، لكنها لا ترسم ولا تفتح dialog/alert؛ الزيارة التالية تقرأ الحقيقة الجديدة.
7. dirty state لا يُستبدل بتحميل تلقائي عند العودة.
8. remount يستبدل المالك والمستمعين السابقين بدل مضاعفتهم.
9. Frappe Form/List يستخدمان document/list identity إضافة إلى active-surface guard؛ لا تُفرض بنية Frappe Page على الأنظمة المحدودة مثل Special Shape Documentation.
10. bootstrap failure على صفحة مخفية لا يعرض UI؛ تحتفظ الصفحة بمحاولة retry واحدة تبدأ عند الزيارة المرئية التالية.
11. dialog/confirm/prompt تابع للزيارة يملكه `createDialogOwner` أو مالك مكافئ؛ `deactivate` يغلقه ويمنع callback من بدء mutation جديدة بعد الإخفاء.

## النتائج

- التنقل السريع أو اكتمال assets بعد `hide` لا يسمح برسم صفحة مخفية.
- الحوارات التابعة للصفحة لا تبقى عائمة بعد انتقال مالكها إلى inactive.
- العودة للصفحة تبدأ قراءة حديثة واحدة، إلا إذا كان عقد dirty state يمنعها.
- يلزم اختبار ترتيب Frappe الحقيقي، وليس استدعاء `await on_page_load()` فقط.
- الصفحات التاريخية خارج Active Product Scope لا تعود إلى النطاق بسبب توحيد Lifecycle؛ التغيير تقني فقط.

## بدائل مرفوضة

- `location.reload()` أو refresh شامل لعلاج stale state.
- مستمعات `show` متفرقة بلا owner أو namespace.
- التخلص من controller عند كل `hide` وخسارة state المقصودة.
- إلغاء mutations على `hide` بعد أن قبلها الخادم.
- إعادة بناء DCO أو Special Shape Documentation داخل framework واجهة جديد.

## التحقق

العقد التنفيذي والجرد الكامل في:

`docs/reference/15_FRONTEND_LIFECYCLE_CLOSURE.md`
