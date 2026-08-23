# 12 — دليل التشخيص وحل المشاكل

> **Status:** Canonical support guide  
> **Audience:** Support، developers، QA، المشرفون

هدف هذا الدليل هو **تحديد أول Boundary خاطئة قبل تعديل الكود**. لا نعالج المشكلة بتغيير عدة طبقات دفعة واحدة أو إضافة `refresh()`/Role bypass عشوائي ثم نأمل أن تختفي.

## 1. قاعدة التشخيص الذهبية

لكل مشكلة اسأل:

```text
هل البيانات الصحيحة موجودة في الخادم؟
  ↓
هل authorization يعيد القرار الصحيح؟
  ↓
هل query/API تعيد payload الصحيح؟
  ↓
هل client يربط payload بالطلب الحالي؟
  ↓
هل UI يعرضه بصورة صحيحة؟
```

ابدأ من أول نقطة يمكن إثبات أنها خاطئة.

## 2. بيانات طلب سابق تظهر عند فتح DCO آخر

### لا تفترض

لا تفترض أن قاعدة البيانات خلطت الطلبين ولا أن الحل `refresh()` دائم.

### افحص بالترتيب

1. رقم DCO في URL/route الحالي.
2. request/endpoint الذي جلب البيانات ورقم DCO المرسل.
3. response الفعلي من الخادم.
4. client state/cache وasync callbacks: هل response لطلب سابق وصل بعد التنقل؟
5. lifecycle cleanup عند تغيير route/form.

إذا كان Refresh يُصلح العرض بينما API المباشر صحيح، فالمشكلة غالبًا في client ownership/state لا في Formula أو optimizer.

## 3. زر غير ظاهر أو فعل غير متاح

افحص:

1. Capability المطلوبة.
2. permission context الذي وصل للواجهة.
3. order/status/lifecycle gate.
4. current production stage.
5. operational role للمرحلة.
6. assignee الحالي.
7. هل الـUI يستخدم context حديثًا أم stale state؟

**ممنوع كحل سريع:** إضافة اسم Role إلى Exception عام قبل فهم أي شرط فشل.

## 4. عامل يرى طلبات لا تخصه

هذه Security issue وليست مشكلة ترتيب فقط.

افحص:

- هل المستخدم يملك `view_all_orders`؟
- هل query repository يفلتر بالـassignment/scope المقصود؟
- هل archive يستخدم نفس ownership contract؟
- هل endpoint يأخذ user من client بدل session؟
- هل document detail endpoint يعيد DCO أجنبيًا بمجرد معرفة الاسم؟

اكتب Negative regression بــDCO/Stage أجنبي قبل الإصلاح قدر الإمكان.

## 5. المستخدم لا يرى بيانات يجب أن يراها رغم إعطائه Role

لا تساوِ Role بالصلاحية مباشرة.

افحص:

1. هل Role حصل فعلًا على Capability المطلوبة؟
2. هل User يحمل Role بعد الحفظ؟
3. هل permission cache/context أعيد بناؤه كما ينبغي؟
4. هل Frappe DocPerm الأساسي يسمح بالسطح المطلوب؟
5. هل Document scope أو lifecycle يرفض هذا المستند تحديدًا؟

اختبر بحساب المستخدم نفسه بعد التعديل.

## 6. تغييرات الصلاحيات لا تظهر إلا بعد Refresh

حدد أولًا هل المشكلة Server cache أم Client state:

- افتح/استدعِ permission context مباشرة بعد الحفظ.
- إذا كان response محدثًا والواجهة قديمة: أصلح invalidation/render lifecycle في client.
- إذا كان response نفسه قديمًا: افحص cache invalidation/server projection.

لا تضف Reload كامل لكل Save إذا كان يمكن تحديث المصدر الصحيح محليًا بصورة آمنة.

## 7. تكلفة داخلية ظهرت لعامل غير مالي

تعامل معها كـHigh-severity security regression.

افحص كل القنوات، لا الشاشة فقط:

- Form/permlevel.
- API/preview JSON.
- system/custom/approved plan snapshots.
- reports.
- prints.
- child rows.
- downloads/files/exports.

المستخدم بدون `view_costs` يجب ألا يستلم القيمة أصلًا. CSS hiding ليس إصلاحًا.

## 8. Cutting Plan لا تتحدث أو Dispatch مرفوض

افحص:

- هل تغيرت القياسات/القشاط/board dimensions أو inputs مؤثرة؟
- `plan_needs_recalculation`.
- وجود Cutting Plan صالحة.
- هل الطلب dispatched مسبقًا؟
- Capability `dispatch_order`.
- Route والعامل الأول.

إذا Route يبدأ Planning Stage، تذكر أن **اعتماد الخطة قبل handoff** مختلف عن Review/Approve القديم للطلب.

## 9. DXF يفتح لكن النظام يرفضه

فتح الملف في برنامج CAD لا يثبت صلاحيته للإنتاج.

افحص:

1. units = mm في Geometry التشغيلية.
2. طبقات `SHEET_OUTLINE` و`CUT_PATH` المطلوبة حسب العقد.
3. entity types المدعومة.
4. contours/connectivity.
5. dimensions والتسامحات.
6. overlap/bounds.
7. rotation rules.
8. عدد القطع ومطابقتها مع DCO.
9. kerf/distance rules.
10. File مرتبط بالطلب الصحيح ورفع بواسطة persona مخولة.

لا تخفّض tolerance عشوائيًا لحل ملف واحد قبل فهم الفرق الهندسي.

## 10. العامل لا يستطيع Start أو Handoff

اجمع الحقائق التالية:

- stage name/type/status.
- current stage للطلب.
- operational role للمرحلة.
- actor roles.
- assigned_to.
- capabilities.
- هل هذه Planning Stage؟ وهل plan approved/current؟

ثم قارنها بعقد `application/shop_floor/commands.py` و`domain/orders/production_authorization.py` بدل تعديل صفحة Shop Floor فقط.

## 11. مرحلة انتهت لكن الطلب لم ينتقل

افحص Route نفسها أولًا:

- هل next stage موجودة؟
- sequence صحيح وفريد؟
- stage type مكرر؟
- worker التالي يملك operational role؟
- هل آخر مرحلة فعلًا؟
- هل incident/replacement مفتوح يغير الحالة المشتقة؟

لا hard-code اسم المرحلة التالية كحل.

## 12. Drawing/DXF action يعمل لمستخدم خاطئ

هذه authorization regression. اختبر منفصلًا:

- capability.
- هل الطلب في drawing/planning context؟
- current assignee.
- operational role.
- هل production DXF موجود وبالتالي المطلوب `replace_dxf` بدل `upload_dxf`؟
- plan lock/approval state.

## 13. زر «مسح بالسكانر» لا يتصل

لا تطلب من الموظف تشغيل PowerShell.

1. إذا لم يُثبت البرنامج، استخدم رابط **تنزيل برنامج السكانر — تثبيت مرة واحدة** داخل واجهة الدرفة.
2. إذا كان مثبتًا، افتح **Almdina Scanner Bridge** من قائمة ابدأ وتأكد من ظهور أيقونته في شريط النظام.
3. افتح `http://127.0.0.1:17831/health` على الجهاز نفسه؛ يجب أن يظهر `ok: true`.
4. من أيقونة شريط النظام اختر **اختبار السكانر** وتأكد أن Windows يعرف الجهاز.
5. إذا ظهر رفض Origin، تحقق أن إصدار التطبيق يسمح بعنوان بيئة ERP الحالي؛ لا توسع الاستماع إلى الشبكة.
6. افحص `%LOCALAPPDATA%\Almdina\ScannerBridge\logs\bridge.log` وأرسل الإصدار والوقت لمسؤول النظام.

## 14. مشكلة بعد Deploy أو Migrate

اجمع:

- exact app SHA/image.
- Frappe/ERPNext version.
- هل `migrate` نجح؟
- هل assets بُنيت إذا تغير JS/CSS؟
- installed apps.
- schema/patch errors.
- worker/web logs.

إذا migration فشل، لا تكرر أوامر destructive عشوائيًا؛ اعرف آخر patch اكتمل وراجع idempotency/backup.

## 15. GitHub CI أحمر

لا تبدأ بتعديل الـWorkflow لتجاوزه.

1. حدد أول job/step فشل.
2. اقرأ failure الحقيقي.
3. اعرف أي Contract يحميه.
4. شغّل/فكر في test المتخصص أولًا.
5. أصلح code/docs السبب.
6. لا تستخدم `continue-on-error`, `|| true`, حذف assertion أو mock واسع فقط للحصول على Green.

## 16. قالب بلاغ مشكلة احترافي

```text
Title:
Environment / site:
Exact Git SHA or image:
User/persona:
Roles + relevant capabilities:
DCO / Stage / Plan / Replacement / File identifiers:
Current order status:
Current stage + assignee:
Expected behavior:
Actual behavior:
Exact reproduction steps:
Does browser refresh change it?:
Does another persona reproduce it?:
Network/API response if relevant:
Console/server error:
Screenshot/video:
Approximate occurrence time:
Business impact:
Security/financial impact:
```

## 17. تصنيف الأولوية

- **Critical:** تسريب مالي/صلاحيات واسع، corruption، تنفيذ إنتاج خاطئ غير قابل للاحتواء.
- **High:** وصول أجنبي/IDOR، تكلفة تظهر لغير مخول، طلب ينتقل لمستخدم/مرحلة خاطئة، DXF إنتاجي خاطئ.
- **Medium:** وظيفة مهمة مكسورة مع workaround آمن أو stale UI لا يغير server truth.
- **Low:** مشكلة عرض/نص/تنسيق بلا أثر على القرار أو البيانات.

الأولوية النهائية تعتمد على أثر الحالة الفعلية، وليس الاسم وحده.

## 18. متى نفتح ADR بدل Bug fix؟

إذا تبين أن “الحل” يتطلب تغيير Capability model أو layer boundaries أو lifecycle الإجباري أو semantics للـsnapshots أو إعادة inventory إلى scope، فهذا ليس Bug fix محليًا. ارجع إلى [Architecture Freeze](ARCHITECTURE_FREEZE.md) وافتح ADR قبل التنفيذ.
