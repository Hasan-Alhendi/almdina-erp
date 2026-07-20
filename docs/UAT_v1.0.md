# Almdina ERP v1.0 — UAT & Go-Live Acceptance

هذه الوثيقة ليست إعلان اكتمال. الإصدار يبقى `1.0.0-dev` إلى أن تُنفّذ البنود التالية على بيئة ERPNext/Frappe v16 فعلية ويُسجّل لكل بند: **Pass / Fail / Evidence / Tester / Date**.

## 1. بيئة الاختبار المرجعية

يجب توثيق:

- Frappe version.
- ERPNext version.
- App commit SHA.
- Site name/domain.
- MariaDB version.
- Browser/version.
- نظام التشغيل لدى العامل.
- برنامج AutoCAD/Illustrator المستخدم للاختبار.
- اسم وإصدار برنامج CNC الفعلي في المعمل.
- نوع ماكينة/CNC إن وجد.

## 2. Install / Migrate / Upgrade

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-DEP-001 | تثبيت التطبيق على Site جديد | `bench --site <site> install-app almdina_erp` ينجح دون Traceback |
| UAT-DEP-002 | `bench migrate` | جميع DocTypes/Custom Fields/Patches تُطبّق بنجاح |
| UAT-DEP-003 | إعادة `bench migrate` | Idempotent ولا يكرر Master Data أو Routing أو Edge Types |
| UAT-DEP-004 | ترقية Site يحوي بيانات سابقة | Patch source identity/validated_on لا يعيد حساب Approved Plans ولا يغير التاريخ |
| UAT-DEP-005 | Clear cache/build assets | الواجهات والـJS الجديدة تعمل دون 404 أو stale bundle |

## 3. Master Data

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-MST-001 | Item MDF | Is MDF + dimensions + thickness + color + material + board USD rate تظهر وتُحفظ |
| UAT-MST-002 | Edge Banding | الأنواع الـ12 والأسعار المرجعية مطابقة حرفيًا للـBaseline |
| UAT-MST-003 | Edge stock mapping | كل نوع مستخدم مخزنيًا مربوط بـItem/UOM صحيح |
| UAT-MST-004 | Settings defaults | Kerf/Trim/Cutting Cost/Packing Mode تظهر كDefaults في طلب جديد |
| UAT-MST-005 | Production Routing | Baseline: Review/Preparation → Cutting → Edge Banding |

## 4. Door Cutting Order — Baseline Regression

اختبر نفس عينات الكود المرجعي القديم والجديد جنبًا إلى جنب.

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-ORD-001 | إدخال Width/Length/Qty | نفس الحسابات والـlabels `1.1`, `1.2`... |
| UAT-ORD-002 | Enter في grid | نفس السلوك Excel-like وعدم فقدان صف |
| UAT-ORD-003 | Area | `W × L × Qty / 10000` |
| UAT-ORD-004 | Edge meters | الحواف المحددة فقط × Qty |
| UAT-ORD-005 | Header default edge | الصف بلا override يأخذ Header |
| UAT-ORD-006 | Row edge override | صف مخصص لا يتغير عند تغيير Header |
| UAT-ORD-007 | Rotation=false | لا تدور القطعة |
| UAT-ORD-008 | Rotation=true | يسمح بالدوران فقط عند الحاجة/الخوارزمية |
| UAT-ORD-009 | Kerf/Trim | الرسم والحساب والمخرجات متطابقة مع القيم |
| UAT-ORD-010 | NaN/Infinity/negative | رفض Server-side برسالة واضحة |
| UAT-ORD-011 | Board Rate default | يأتي من Item عند إنشاء الطلب ويمكن تغييره حسب الصلاحية |
| UAT-ORD-012 | Explicit zero cost | الصفر يبقى صفرًا ولا يتحول تلقائيًا إلى 1 |

## 5. Optimization / Geometry

اختبر جميع الخوارزميات الـ17 وAuto على مجموعة ثابتة من الطلبات.

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-OPT-001 | كل Algorithm | لا overlap ولا out-of-bounds |
| UAT-OPT-002 | Auto | Valid أولًا ثم أقل Full Boards ثم أقل Waste وفق score المعتمد |
| UAT-OPT-003 | Oversized piece | Unplaced واضحة ويمنع Approval |
| UAT-OPT-004 | Duplicate/missing piece | Validator يرفض الخطة |
| UAT-OPT-005 | Rotation-only fit | يفشل بدون Allow Rotation وينجح عند السماح |
| UAT-OPT-006 | 200 expanded pieces | قياس الزمن على بيئة الإنتاج المرجعية وتوثيقه؛ الهدف ≤ 5 ثوانٍ أو اتخاذ قرار Background Job |

## 6. Approval / Revision / Immutability

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-WF-001 | Draft → Pending Review | لا خصم مخزون بسبب Preview/Recalculate |
| UAT-WF-002 | Reject → edit → resubmit | Revision يرتفع ولا تضيع الخطة السابقة |
| UAT-WF-003 | Approve | Approved Plan واحدة صحيحة ومثبتة للRevision |
| UAT-WF-004 | Approved edit attempt | Server يرفض التعديل المباشر |
| UAT-WF-005 | Change Item/Edge price بعد Approval | التاريخ والتكلفة والمخطط القديم لا تتغير |
| UAT-WF-006 | Replacement plan موجودة | Preview/Print للطلب الأساسي لا تختار Mini Plan بدل Approved Order Plan |

## 7. Remnant-First Planning

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-REM-001 | Remnant مطابق Item/Material/Color/Thickness | يُجرّب قبل فتح Full Board عند تفعيل Policy |
| UAT-REM-002 | نفس Item لكن لون مختلف | لا يُستخدم |
| UAT-REM-003 | نفس Item لكن سماكة مختلفة | لا يُستخدم |
| UAT-REM-004 | حجز متزامن من جلستين | نفس Remnant لا يُحجز لطلبين |
| UAT-REM-005 | Cancel قبل الاستهلاك | Remnant يعود Available |
| UAT-REM-006 | Cutting Finish | البقايا المؤهلة تُنشأ مرة واحدة فقط |
| UAT-REM-007 | Waste invariant | `Waste = Reusable Remnant Area + Scrap Area` |
| UAT-REM-008 | Parent lineage | بقايا ناتجة من Remnant تحتفظ بـParent Remnant |

## 8. Stock / Reservations / Actual Consumption

نفّذ الاختبارات بحسابات Stock Ledger فعلية.

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-STK-001 | Reserve On Approval = ON | Main order reservation تُنشأ مرة واحدة |
| UAT-STK-002 | Reserve On Approval = OFF | لا Reservation stock item عند Approval؛ Start يعيد فحص المخزون ثم يستهلك |
| UAT-STK-003 | Same-order replacement reservation | تقلل التوفر للطلب الأساسي ولا تُستثنى خطأً |
| UAT-STK-004 | Main order consumption | لا يحول Replacement reservations إلى Consumed |
| UAT-STK-005 | Double Start/Retry | لا Stock Entry مكرر |
| UAT-STK-006 | Edge UOM conversion | meters تتحول إلى Stock UOM بالقيمة الصحيحة |
| UAT-STK-007 | Actual > Planned | Additional Material Issue بالفرق فقط |
| UAT-STK-008 | Actual < Planned | Material Receipt يعيد الفرق فقط |
| UAT-STK-009 | Active reservations | Extra Issue لا يستهلك كمية محجوزة لعمل آخر |
| UAT-STK-010 | Stock Ledger traceability | Remarks/links تكفي لتتبع Order/Plan/Replacement |

## 9. Planned vs Actual Cost

المعادلة المقبولة:

`Actual Cost = Approved Planned Cost + Material Variance + Completed Internal Replacement Loss`

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-COST-001 | Approved Plan | Planned Cost ثابت Snapshot |
| UAT-COST-002 | Extra material | Material Variance يزيد Actual فقط |
| UAT-COST-003 | Material return | Material Variance يخفض Actual فقط |
| UAT-COST-004 | Internal replacement | Internal Loss منفصل ولا يرفع charge_customer |
| UAT-COST-005 | Remnant policy | Zero/Average Valuation/Configured Rate حسب الإعداد دون double charge |
| UAT-COST-006 | Screen vs report | نفس الأرقام تمامًا |

## 10. Production Stages / Audit

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-PROD-001 | Start | worker + start time + event |
| UAT-PROD-002 | Pause/Resume | pauses منفصلة وActual Time يستبعدها |
| UAT-PROD-003 | Finish | finish time + qty + notes + event |
| UAT-PROD-004 | Sequence | لا تبدأ مرحلة قبل السابقة إلا Override مصرح ومُسجل |
| UAT-PROD-005 | Edge not applicable | Auto-complete حسب Routing policy |
| UAT-PROD-006 | Order status | مشتق من المراحل ولا يتعارض معها |

## 11. Incident / Replacement Mini Plan

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-RPL-001 | Incident `2.3` | يعرف صف/نسخة القطعة الأصلية |
| UAT-RPL-002 | Replacement creation | ينسخ dimensions/rotation/edge snapshot |
| UAT-RPL-003 | Approval | Mini Cutting Plan مستقلة Validated/Approved |
| UAT-RPL-004 | Strict identity | Remnant مطابق Item/Material/Color/Thickness فقط |
| UAT-RPL-005 | Reservation policy ON/OFF | يعمل المساران ويخصمان المادة مرة واحدة |
| UAT-RPL-006 | Start twice | مرفوض ولا Stock Entry مكرر |
| UAT-RPL-007 | Complete | generated remnants + internal loss + incident resolved |
| UAT-RPL-008 | Open mandatory replacement | Order لا يصبح Completed |
| UAT-RPL-009 | Internal error | `charge_customer = 0` افتراضيًا |

## 12. Visual Plan / Printing

| ID | الاختبار | معيار النجاح |
|---|---|---|
| UAT-PRN-001 | Board aspect ratio | لا تشويه للاتجاه |
| UAT-PRN-002 | Piece labels/dimensions | تطابق Snapshot |
| UAT-PRN-003 | Edge red marks + rotation | كل حافة في مكانها الفيزيائي الصحيح |
| UAT-PRN-004 | Full Board + variable Remnants | كل Source يرسم بحجمه الحقيقي |
| UAT-PRN-005 | Approved print | لا يعيد optimizer؛ يستخدم Approved Order Plan فقط |
| UAT-PRN-006 | Measurements print | group/width/length/qty/notes/rotation/edge indications واضحة |
| UAT-PRN-007 | RTL/LTR | العربية سليمة والمقاسات/الأرقام لا تنقلب |
| UAT-PRN-008 | A4 | كل Sheet واضح ولا ينقسم بشكل يربك العامل |

## 13. DXF — Mandatory Production UAT

يجب اختبار ملف من Full Board وملف يحتوي Remnant وملف Rotation.

| ID | التطبيق/الاختبار | معيار النجاح |
|---|---|---|
| UAT-DXF-001 | AutoCAD | يفتح دون Repair/Error |
| UAT-DXF-002 | Illustrator | يفتح وتظهر الأبعاد الصحيحة |
| UAT-DXF-003 | CNC software الفعلي | يفتح دون تغيير scale/unit |
| UAT-DXF-004 | Measure known piece | قطعة 500×900 mm تُقاس 500×900 فعليًا |
| UAT-DXF-005 | Layers | `CUT_PATH` منفصلة عن `SHEET_OUTLINE` |
| UAT-DXF-006 | Multiple sheets | لا overlap بين Sheets بعد offsets |
| UAT-DXF-007 | Remnant source | outline يساوي مقاس Remnant الحقيقي |
| UAT-DXF-008 | Server validation | فساد overlap/out-of-bounds/unplaced يمنع download |
| UAT-DXF-009 | Manifest | order/revision/plan/units/engine/sources صحيحة |
| UAT-DXF-010 | Legacy button | لا يوجد إلا مسار Export آمن واحد في الواجهة |

**لا يجوز اعتماد Go-Live للـCNC قبل توقيع UAT-DXF-001..010.**

## 14. Permissions

اختبر بحساب منفصل لكل Role، وليس System Manager فقط.

- Order Entry.
- Cutting Operator.
- Edge Operator.
- Production Manager.
- Stock Manager.
- Accounts Management.

يجب التحقق من:

- Direct URL.
- List/Form permissions.
- Direct whitelisted API call.
- Cost fields visibility.
- Approval/start/stock/replacement operations.

أي عملية حساسة تنجح من API لدور غير مصرح = **Fail / Blocker**.

## 15. Reports

اختبر Drill-down والأرقام مقابل المستندات الأصلية:

- Factory Order Analysis.
- Production Stage Performance.
- Remnant Inventory.
- Production Incidents and Replacements.
- Order Stock Availability.

المعيار: نفس تعريفات Waste/Cost/Stock الموجودة في المستندات والخدمات، لا معادلات مختلفة.

## 16. Backup / Restore

على نسخة Test حقيقية:

1. أنشئ Orders + Approved Plans + Stock Entries + Remnants + Attachments.
2. خذ Backup بالطريقة التشغيلية المعتمدة.
3. Restore على Site منفصل.
4. شغّل `bench migrate`.
5. قارن counts وروابط المستندات.
6. افتح Approved Plan/Print/DXF بعد restore.
7. تحقق من Attachments.
8. تحقق من Stock Ledger وRemnant lineage.

أي فقدان Document/Attachment/Stock link = **Blocker**.

## 17. Final Go-Live Gate

لا يتحول الإصدار من `1.0.0-dev` إلى `1.0.0` قبل:

- [ ] جميع Must requirements في SRS = Pass.
- [ ] جميع Legacy baseline regression cases = Pass.
- [ ] DXF CNC UAT = Pass وموقّع.
- [ ] Permission matrix = Pass بحسابات فعلية.
- [ ] Stock/Reservation concurrency = Pass.
- [ ] Backup/Restore = Pass.
- [ ] `bench migrate` على نسخة من Production Data = Pass.
- [ ] لا Critical/High open defects.
- [ ] Commit SHA المرشح للإنتاج مثبت في سجل القبول.

## 18. Evidence Record

لكل اختبار احفظ:

- Test ID.
- Pass/Fail.
- Screenshot/Video/File output.
- Order/Plan/Stock Entry IDs.
- Tester.
- Date/time.
- Commit SHA.
- Notes/defect link إن فشل.
