# 03 — دورة الطلب والإنتاج

> **Status:** Canonical  
> **Audience:** التشغيل، QA، developers

## 1. الفكرة الأساسية

الطلب لا يتحرك لأن اسم Role تغيّر، بل لأن **حالة الطلب + Production Route + Current Stage + Capability + Assignment** تسمح بالانتقال.

## 2. المسار التشغيلي الحالي

Stage 14 ثبّت المسار المرجعي التالي كرحلة E2E:

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> AtDrawing: Dispatch + valid cutting plan
    AtDrawing --> AtCNC: planning plan approved + handoff
    AtCNC --> AtSanding: CNC completes + handoff
    AtSanding --> ReadyForDelivery: final stage completes
    ReadyForDelivery --> Delivered: supervisor confirms delivery
```

الأسماء الفعلية للمراحل قابلة للضبط عبر `Production Routing`. المثال أعلاه يمثل Route يبدأ بمرحلة تخطيط Drawing ثم CNC ثم Sanding/تقشيط.

## 3. Draft وReview/Approve القديم

المسار الإجباري القديم `Draft -> Pending Review -> Approved` **لم يعد شرطًا إلزاميًا لإرسال الطلب إلى الإنتاج**.

الكود يقبل dispatch من حالات توافقية مثل `Draft`, `Rejected`, `Pending Review`, `Approved`، لكن التعليق الرسمي في Domain يوضح أن Review/Approve القديم Retired كشرط Workflow.

قد تبقى endpoints وصفحات Approval للتوافق أو تاريخ المنتج. لا تبنِ Feature جديدة على فرض أن `Approved` يجب أن يسبق dispatch ما لم يصدر Product Decision جديد.

**مهم:** هذا مختلف عن **اعتماد Cutting Plan**. إذا بدأ Production Route بمرحلة تخطيط، يجب اعتماد الخطة المختارة قبل handoff من مرحلة التخطيط إلى المرحلة التالية.

## 4. Dispatch

لإرسال الطلب للإنتاج يلزم، كحد أدنى وفق العقد الحالي:

- `DISPATCH_ORDER` capability.
- حالة قابلة للإرسال.
- الطلب غير dispatched مسبقًا.
- وجود Cutting Plan صالح.
- ألا تكون الخطة بحاجة لإعادة حساب.
- Route صالح.
- العامل المختار يملك `operational_role` المطلوب لأول مرحلة.

بعد dispatch ينشأ Current Production Stage ويُسند لمستخدم محدد.

## 5. تنفيذ المرحلة

### Start

العامل يحتاج:

- `START_ASSIGNED_STAGE`.
- المرحلة هي Current Stage للطلب.
- Role المستخدم يطابق `operational_role` للمرحلة أو Administrator.
- المرحلة مسندة لنفس المستخدم.
- Stage status يسمح بـStart، عادة `Pending`.

### Handoff / Finish

العامل يحتاج `HANDOFF_ASSIGNED_STAGE` ونفس شروط ownership. المسار الطبيعي للإنهاء يبقى من `In Progress` أو `Paused` إلى `Completed`.

يوجد استثناء مقصود للمرحلة `Pending`: إذا كانت المرحلة هي Current Stage ومسندة لنفس العامل، وكان العامل يملك `HANDOFF_ASSIGNED_STAGE` **ولا يملك** `START_ASSIGNED_STAGE`، يمكنه تنفيذ Handoff يدوي مباشر من `Pending` إلى `Completed` دون إنشاء Start وهمي. هذا لا يحدث تلقائيًا.

إذا كان العامل يملك الصلاحيتين `START_ASSIGNED_STAGE` و`HANDOFF_ASSIGNED_STAGE` معًا، فلا يجوز له تجاوز Start: في `Pending` يظهر/يُسمح Start أولًا، وبعد دخول المرحلة في حالة `In Progress` يصبح Handoff متاحًا.

إذا كانت المرحلة Planning Stage، تبقى Gate الإضافية كما هي: Production plan يجب أن يكون Approved وحديثًا حتى عند استخدام Handoff المباشر.

### Next stage

Application يقرأ المرحلة التالية من Route، لا من سلسلة `if` ثابتة. يتم إنشاء/تفعيل المرحلة التالية وإسنادها للعامل المناسب.

### Last stage

انتهاء آخر مرحلة يحوّل الطلب إلى `Ready for Delivery`، ثم `MARK_DELIVERED` يحوله إلى `Delivered`.

## 6. Inbox وArchive

العامل يرى العمل النشط المسند له في Inbox. بعد اكتمال مرحلته ينتقل سجله إلى Archive/التاريخ الشخصي، بينما يرى العامل التالي مرحلته الجديدة.

هذه ليست مجرد طريقة عرض؛ Stage 14 يختبر انتقال نفس الطلب بين commands وqueries معًا.

## 7. Supervisor actions

حسب Capabilities يمكن للمشرف:

- Dispatch order.
- Reassign worker لمرحلة نشطة.
- Revert إلى قسم/مرحلة سابقة مع شروط بنيوية.
- Return order to Draft.
- Mark Delivered.

Supervisor capability لا تلغي كل قواعد البنية تلقائيًا؛ بعض الإجراءات ما زالت تتطلب وجود target stage صالح أو status مناسب.

## 8. Drawing / planning handoff

إذا كان أول Stage `is_planning_stage=True`:

1. إذا كان العامل يملك `START_ASSIGNED_STAGE` يبدأ المرحلة؛ أما Handoff-only فيخضع لاستثناء `Pending` الموثق أعلاه.
2. يراجع System plan أو Uploaded/Custom plan حسب الصلاحيات.
3. يعالج Special Drawing/DXF إن كان مطلوبًا.
4. يعتمد Production Cutting Plan المختارة.
5. عند handoff فقط ينتقل الطلب للمرحلة التالية، مع بقاء Planning Handoff Gate إلزامية في الحالتين.

## 9. Revision

Revision تحافظ على تاريخ الطلب بدل تعديل حقيقة إنتاجية قديمة بصمت. أي تغيير يؤثر على geometry أو plan بعد نقطة اعتماد/إنتاج يجب أن يمر بالآلية المناسبة ويعيد حساب/اعتماد الخطة عند الحاجة.

لا تجعل Preview لطلب مقفل يعيد تشغيل optimizer وكأنه Draft؛ تاريخ الطلب يجب أن يبقى ثابتًا.

## 10. Incidents & Replacements

عند تلف/خطأ قطعة:

- يسجل `Production Incident` عند امتلاك Capability المناسبة.
- يمكن إنشاء `Replacement Piece` مرتبطة بالطلب/القطعة الأصلية.
- التعويض له Authorization وPlanning/Execution مستقلان.
- معرفة اسم Replacement أو DCO لا تكفي للوصول إليه؛ document scope يجب أن يثبت العلاقة.

## 11. State ownership

- Order lifecycle rules: `domain/orders/lifecycle.py`.
- Route model: `domain/orders/production_routing.py`.
- Production authorization facts: `domain/orders/production_authorization.py`.
- Commands: `application/shop_floor/commands.py`.
- Queries/Inbox/Archive: `application/shop_floor/queries.py`.

هذه الملفات هي أول مكان يقرأه المطور عند تعديل Workflow.
