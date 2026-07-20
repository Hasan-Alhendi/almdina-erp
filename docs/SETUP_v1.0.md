# Almdina ERP v1.0 — Production Setup Guide

هذه الوثيقة تصف ترتيب إعداد النظام بعد نجاح `install-app` و`bench migrate`. لا تتجاوز `docs/UAT_v1.0.md` ولا تعني أن البيئة أصبحت Production-ready تلقائيًا.

## 1. Company / Warehouse

1. تأكد من وجود Company صحيحة في ERPNext.
2. أنشئ Warehouse المواد الخام الذي ستخرج منه ألواح MDF والقشاط.
3. تأكد أن Warehouse مربوط بالـCompany الصحيحة.
4. من صفحة **Factory Stock Settings** عيّن `Default Warehouse`.

لا تبدأ Approval/Production قبل هذه الخطوة؛ خدمات المخزون ترفض العمل دون Warehouse واضح.

## 2. Units of Measure

### MDF Boards

- يجب أن يكون Stock UOM للألواح وحدة عددية كاملة مثل `Nos`/`Unit` مع `Must be Whole Number`.
- الاستهلاك المخطط للوح الكامل = عدد ألواح فيزيائية، وليس m².

### Edge Banding

الخيار الأبسط:

- Stock UOM = Meter.

أو إذا كان المخزون بوحدة Roll/غيرها:

- أضف UOM Conversion على Item بحيث يستطيع النظام تحويل الأمتار المخططة إلى Stock UOM.
- اختبر التحويل فعليًا قبل Go-Live.

## 3. MDF Board Items

لكل صنف لوح مستخدم في القص:

1. فعّل `Is MDF Board`.
2. أدخل:
   - Board Length MM.
   - Board Width MM.
   - Board Thickness MM.
   - Board Material.
   - Board Color.
   - Board Rate USD كقيمة افتراضية عند إنشاء الطلب.
3. اضبط Stock UOM كوحدة كاملة.
4. أدخل الرصيد الافتتاحي بالطريقة المحاسبية/المخزنية المعتمدة في ERPNext.

**مهم:** اللون/المادة/السماكة تصبح Snapshot في الطلب والخطة والبقايا؛ لا تستخدم صنفًا عامًا واحدًا لعدة ألوان إذا كان ذلك سيجعل الهوية الفيزيائية غامضة.

## 4. Edge Banding Stock Items

أنشئ Items للقشاط الذي تريد خصمه مخزنيًا، ثم اربط كل `Edge Banding Type` بصنفه.

الأنواع المرجعية الـ12 مزروعة بالأسماء والأسعار Baseline، لكن:

- السعر يمكن إدارته تشغيليًا بعد التثبيت.
- Disabled state لا يعاد تفعيله تلقائيًا في migrate.
- Stock Item/UOM لا تُستبدل بقيم Baseline أثناء migrate.

لا تعتمد طلبًا يستخدم Edge Type مخزنيًا بلا Item/UOM صحيحين.

## 5. Factory Stock Settings

اضبط:

- Default Warehouse.
- Reserve Stock On Approval:
  - ON: حجز Stock Items عند الاعتماد.
  - OFF: إعادة فحص واستهلاك المادة عند نقطة التنفيذ.
- Stock Consumption Point:
  - Cutting Start.
  - Cutting Finish.
- Prefer Matching Remnants Before Full Boards.
- Minimum Remnant Width MM.
- Minimum Remnant Length MM.
- Minimum Remnant Area M2.
- Remnant Cost Policy:
  - Zero.
  - Average Valuation.
  - Configured Rate.
- Configured Remnant Rate USD / M2 عند استخدام السياسة المناسبة.

بعد تغيير Policy، نفّذ سيناريو UAT جديد؛ لا تفترض أن طلبات قيد الإنتاج ستتغير تاريخيًا.

## 6. Cutting Defaults

في `Almdina ERP Settings` راجع:

- Default Kerf MM.
- Default Trim Margin MM.
- Default Cutting Cost / Board USD.
- Default Packing Mode.

هذه Defaults للطلبات الجديدة فقط. Approved Plans تحفظ Snapshot ولا تتغير بسبب تعديل الإعدادات لاحقًا.

## 7. Roles and Users

أنشئ مستخدم اختبار منفصل لكل دور قبل الإنتاج:

- Order Entry.
- Cutting Operator.
- Edge Operator.
- Production Manager.
- Stock Manager.
- Accounts Management.

لا تختبر كل شيء بحساب Administrator/System Manager فقط.

نفّذ Permission UAT:

- Form/List.
- Direct URL.
- Direct API.
- Cost visibility.
- Approval.
- Stage actions.
- Stock operations.
- Replacement operations.

## 8. Production Routing

يوجد Routing افتراضي:

1. Review / Preparation.
2. Cutting.
3. Edge Banding.

راجع أنه Active وأن `Default Production Routing` يشير إليه.

إن أضفت Drilling/Assembly/QC/Packing ضمن نطاق التشغيل، اختبر ترتيب المراحل والصلاحيات قبل اعتماده.

## 9. Initial Remnants

إن كان المعمل يملك بقايا فعلية قبل تشغيل النظام:

- أدخل كل Remnant بسجل مستقل.
- Board Item.
- Material/Color/Thickness مطابق للحقيقة الفيزيائية.
- Width/Length MM.
- Warehouse/Physical Location.
- Status = Available.

لا تسجل بقايا تقديرية؛ optimizer قد يعتمد عليها فعليًا لاحقًا.

## 10. First Controlled Test Order

ابدأ بطلب صغير معروف يدويًا:

- Board معروف المقاس.
- 3–5 مجموعات قطع.
- بعض القطع Qty > 1.
- قطعة Rotation allowed وأخرى غير مسموح.
- قشاط Header default + Row override.
- Kerf/Trim معروفان.

ثم اختبر بالتسلسل:

1. Draft live calculation.
2. Measurements print.
3. Draft validated DXF.
4. Send for Review.
5. Approve.
6. Approved Plan Snapshot.
7. Stock reservation/availability حسب Policy.
8. Start Cutting.
9. Stock Entry.
10. Finish Cutting.
11. Generated Remnants + Waste reconciliation.
12. Edge Banding stage.
13. Complete order.
14. Planned vs Actual Cost report.

## 11. Replacement Controlled Test

على طلب اختبار فقط:

1. سجل Incident على قطعة مثل `2.3`.
2. تحقق من نسخ dimensions/edge/rotation.
3. ضع Remnant مطابق وآخر بنفس Item لكن لون مختلف.
4. Approve Replacement.
5. يجب اختيار المطابق فقط.
6. Start مرة واحدة.
7. تحقق من Stock Entry/Remnant consumption.
8. Complete.
9. تحقق من Internal Loss وعدم تحميل العميل تلقائيًا.
10. تحقق من البقايا الناتجة.

## 12. Actual Consumption Test

بعد Material Issue الأساسي:

- حالة 1: Actual = Planned → لا adjustment entry.
- حالة 2: Actual > Planned → Additional Material Issue للفرق.
- حالة 3: Actual < Planned → Material Receipt للفرق.
- اعكس Actual Variance واختبر أن حركات الفرق تُلغى والتكلفة تعاد حسابها.

## 13. DXF Production Acceptance

قبل أي CNC حقيقي نفّذ كل `UAT-DXF-*` في `docs/UAT_v1.0.md`:

- AutoCAD.
- Illustrator.
- CNC software الفعلي.
- mm scale.
- CUT_PATH vs SHEET_OUTLINE.
- Multiple sources.
- Remnant outline.
- Manifest.

لا تجعل نجاح تنزيل الملف من المتصفح دليل قبول CNC.

## 14. Backup / Restore

قبل Go-Live:

- Backup قاعدة البيانات.
- Files/private files.
- Restore على Site منفصل.
- `bench migrate`.
- تحقق من Orders/Plans/Stock Entries/Remnants/Attachments.

## 15. Final Rule

لا تغير الإصدار إلى `1.0.0` إلا بعد:

- جميع Must = Pass.
- Legacy regression = Pass.
- Permission UAT = Pass.
- Stock concurrency = Pass.
- DXF/CNC = Pass.
- Backup/Restore = Pass.
- لا Critical/High defects مفتوحة.
