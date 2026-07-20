# Almdina ERP

نظام إدارة معمل MDF والقص مبني على ERPNext / Frappe.

## Version 1.0 — Scope Lock

النسخة الأولى من المشروع يجب أن تطابق **وثيقة متطلبات نظام إدارة معمل MDF والقص v1.0** المعتمدة للمشروع حرفيًا من حيث النطاق والسلوك الوظيفي.

- لا تُضاف أي ميزة غير موجودة في المتطلبات المعتمدة للنسخة 1.0.
- لا يُحذف أو يُختصر أي متطلب معتمد للنسخة 1.0.
- أي تطوير أو توسعة مستقبلية تتم في إصدار لاحق وبشكل منفصل عن Baseline v1.0.
- `docs/REQUIREMENTS_v1.0.md` هو المرجع الرسمي للمتطلبات.
- `docs/UAT_v1.0.md` هو بوابة القبول الميداني وGo-Live.
- السلوك الموجود في Client Script المرجعي السابق يعد Baseline وظيفيًا إلزاميًا؛ لا يجوز أن تفقد إعادة الهندسة أي وظيفة منه.

**Current version:** `1.0.0-dev`

> وجود الكود لا يعني أن v1.0 أصبحت Production-ready. الانتقال إلى `1.0.0` يحتاج اجتياز UAT/Bench/CNC/Backup/Permissions بالكامل.

## Implemented in Code

### 1. Door Cutting Order / Legacy Baseline

- `Door Cutting Order` و`Door Cutting Order Detail` مع Revision وApproved Plan link.
- CM input، area m²، edge meters، quantity، notes، rotation، edge flags.
- Header Edge Type كـDefault وRow Edge Type كـOverride.
- Server-side numeric validation، بما فيه رفض `NaN` و`Infinity` والقيم السالبة غير المسموحة.
- MDF Item fields: dimensions، thickness، material، color، `Is MDF`، وBoard Rate USD.
- Factory Settings كمرجع لـKerf/Trim/Cutting Cost/Packing defaults.
- Explicit zero cost يبقى صفرًا ولا يُعاد قسرًا إلى 1.
- Live preview للطلبات القابلة للتعديل فقط؛ الطلب المعتمد/قيد الإنتاج يعيد Approved Order Snapshot ولا يعيد تشغيل optimizer تاريخيًا.
- الحفاظ على سلوك الـBaseline المرئي: الرسم، ترقيم النسخ `1.1`، خطوط القشاط، Excel-like Enter، الطباعة، القياسات، والأزرار الأصلية المطلوبة.

### 2. Optimization Engine

- جميع خوارزميات Baseline الـ17 + `Auto` Server-side.
- Kerf وTrim وAllow Rotation.
- Auto scoring يعتمد على صلاحية كاملة ثم عدد Full Boards ثم Waste وفق المحرك المعتمد.
- Independent geometry validation للحدود، overlap، العدد، IDs، dimensions، orientation، rotation، وUnplaced.
- Regression tests أولية ومتوسعة للمحرك والحالات الحدية.

### 3. Cutting Plan / Revision / Immutability

- `Cutting Plan` مستقلة عن Rendered HTML.
- Plan Kind: `Order` أو `Replacement`.
- Immutable Approved Snapshot.
- Engine/Method/Score/Revision/Validated On/Approval metadata.
- `Cutting Plan Source` يحفظ:
  - Full Board أو Remnant.
  - Board Item.
  - Material / Color / Thickness snapshot.
  - Full/usable dimensions.
  - source/used/waste areas.
- `Cutting Plan Piece` يحفظ label/x/y/w/h/original dimensions/rotation/edge snapshot.

### 4. Workflow / Production

- Draft → Pending Review → Approved مع Reject وإعادة Revision.
- `Production Routing` Master قابل للضبط.
- Baseline routing المزروع: Review/Preparation → Cutting → Edge Banding.
- `Production Stage`: Start/Pause/Resume/Finish، worker، timestamps، completed qty، notes، actual working time.
- منع تجاوز الترتيب إلا Override مصرح ومُسجل.
- `Production Stage Event` Append-only audit log.
- Order Status مشتق من مراحل الإنتاج والتعويضات المفتوحة.

### 5. Stock / Reservation / Consumption

- Reservation اختياري عند Approval حسب `Almdina ERP Settings`.
- Main-order reservations منفصلة عن Replacement reservations.
- availability = physical stock − competing active reservations.
- Row locks في العمليات الحرجة لمنع overbooking.
- ERPNext `Stock Entry` بدل تعديل `Bin` يدويًا.
- Full Board consumption كعدد صحيح بوحدة مخزون مناسبة.
- Edge Banding consumption بالمتر أو UOM Conversion واضح.
- Idempotency protection ضد تكرار الاستهلاك.
- `Material Consumption Log` مرتبط بالطلب والخطة والحركة.

### 6. Planned vs Actual Consumption

- تسجيل Actual Consumption بعد الاستهلاك المخطط.
- Actual > Planned → Additional `Material Issue` للفرق فقط.
- Actual < Planned → `Material Receipt` لإرجاع الفرق فقط.
- Extra Issue يحترم الحجوزات النشطة للطلبات/التعويضات الأخرى.
- Planned/Actual/Variance محفوظة لكل Item.
- لا تسمح بتسوية ثانية فوق الأولى دون معالجة واضحة.

### 7. Planned vs Actual Cost

المعادلة المركزية الحالية:

`Actual Cost = Approved Planned Cost + Material Consumption Variance + Completed Internal Replacement Loss`

- Approved prices/costs محفوظة Snapshot.
- MDF / Cutting / Edge breakdown.
- Material Variance منفصلة.
- Internal Replacement Loss منفصلة.
- خطأ المعمل لا يرفع `charge_customer` افتراضيًا.
- Remnant cost policy: Zero / Average Valuation / Configured Rate.

### 8. Board Remnants

- `Board Remnant` مع Available / Reserved / Consumed / Scrapped.
- dimensions/material/color/thickness/warehouse/location/source/parent lineage.
- Remnant-first planning حسب Policy.
- المطابقة ليست باسم Item فقط؛ تشمل Material + Color + Thickness snapshot.
- Atomic reservation لمنع استخدام نفس البقايا مرتين.
- توليد بقايا جديدة بعد القص مع lineage.
- Waste reconciliation المحفوظة:

`Approved Waste = Reusable Remnant Area + Scrap Area`

### 9. Incidents / Replacement Mini Workflow

- `Production Incident` للقطعة والمرحلة والعامل والسبب والوصف.
- `Replacement Piece` مرتبطة بالقطعة الأصلية مثل `2.3`.
- Pending Approval → Approved → In Progress → Completed/Cancelled.
- Mini `Cutting Plan` مستقلة ومعتمدة ومتحقق منها.
- Strict Remnant matching: Item + Material + Color + Thickness + fit.
- Remnant reservation دائم عند اختياره لمنع السباق.
- Stock-item reservation للتعويض يتبع سياسة Reserve On Approval.
- عند عدم الحجز مسبقًا يعاد فحص المخزون لحظة Start ثم يُستهلك فعليًا.
- منع Start المكرر / Stock Entry المكرر.
- توليد بقايا من مصدر التعويض.
- Internal Loss وتكلفة التعويض مرتبطة بـActual Cost للطلب.

### 10. DXF

- AutoCAD R12 ASCII، units = mm.
- `CUT_PATH` و`SHEET_OUTLINE` منفصلتان.
- Variable-size Full Boards/Remnants.
- Server-side validation إلزامي قبل التصدير:
  - bounds.
  - overlap.
  - missing/duplicate/unknown pieces.
  - dimensions/orientation/rotation.
  - Unplaced.
  - source Board Item / Material / Color / Thickness.
  - Remnant dimensions/identity snapshot.
- Approved/production DXF يأتي من Immutable Approved Order Plan فقط.
- Draft/Rejected/Pending Review يحافظ على Legacy export لكن عبر strict server recalculation/validation بلا stock side effects.
- Manifest JSON مرافق: order/revision/plan/units/engine/method/sources/material identity.
- طبقة UI تزيل زر DXF القديم عند ظهوره وتفرض مسار التصدير الآمن الواحد.

### 11. Printing / Rendering

- Cutting Plan visual renderer.
- Source-aware rendering عند استخدام Remnants مختلفة المقاس.
- Edge markers مع Rotation.
- Cutting Plan print.
- Measurements print.
- الطلب المعتمد لا يعيد optimizer في Preview/Print؛ يعتمد على Approved Order Snapshot فقط.

### 12. Permissions / Audit

الأدوار الأساسية:

- Order Entry.
- Cutting Operator.
- Edge Operator.
- Production Manager.
- Stock Manager.
- Accounts Management.
- System Manager.

- الحركات الحساسة تتحقق Server-side من الأدوار والحالة.
- Cost fields على Permission Level أعلى من العامل.
- Approved Plans immutable.
- Stage event audit log.
- Controlled cancellation مع تحرير الحجوزات وعكس Stock Entry فقط عندما يكون ذلك آمنًا فيزيائيًا.
- يمنع الإلغاء الوهمي بعد اكتمال القص/تغير المادة فعليًا.

### 13. Reports

موجودة حاليًا:

- `Factory Order Analysis`.
- `Production Stage Performance`.
- `Remnant Inventory`.
- `Production Incidents and Replacements`.
- `Order Stock Availability`.

التقارير تستخدم نفس تعريفات Cost/Waste/Reservations الموجودة في الخدمات والمستندات، مع Drill-down إلى المستندات الأصلية حيث ينطبق.

### 14. Migration / Setup

- Required Roles seed.
- exact 12 Edge Banding baseline types/rates seed.
- default routing/settings seed.
- MDF Item custom fields sync on install/migrate.
- Patch مسجل لترقية البيانات الموجودة:
  - backfill Source Material Identity.
  - backfill validation timestamps.
  - لا يعيد حساب Approved historical plans.

### 15. Automated Checks Included

- Cutting engine regression tests.
- Replacement planning tests.
- DXF geometry validation tests.
- Waste/free-rectangle tests.
- Actual consumption variance cost tests.
- GitHub Actions static workflow لفحص:
  - JSON syntax.
  - Python compile syntax.
  - JavaScript syntax.

**مهم:** وجود Workflow في المستودع لا يعني أنه اجتاز بنجاح؛ يجب التحقق من نتيجة GitHub Actions الفعلية لكل Commit مرشح للإنتاج.

## Still Required Before `1.0.0`

هذه البنود ليست “ميزات برمجية ناقصة” بالضرورة؛ هي بوابات قبول لم تُثبت بعد في بيئة فعلية:

1. تثبيت التطبيق و`bench migrate` على Frappe/ERPNext v16 فعلي، جديد وترقية من بيانات موجودة.
2. تشغيل Integration/Permission tests على Bench حقيقي بحساب مستقل لكل Role.
3. Legacy regression حالة بحالة مقابل الكود المرجعي السابق.
4. إكمال تحويل النصوص المتبقية في الـLegacy renderer/print إلى Translation-driven دون تغيير المخرجات.
5. اختبار RTL/LTR والطباعة على المتصفحات المستخدمة فعليًا.
6. قياس Auto مع ~200 Expanded Pieces على بيئة الإنتاج المرجعية.
7. DXF UAT إلزامي على:
   - AutoCAD.
   - Illustrator.
   - برنامج CNC الفعلي.
   - قياس mm/scale/layers/source outlines.
8. Stock/Reservation concurrency UAT بجلسات متزامنة فعلية.
9. Backup/Restore test كامل للمستندات والمرفقات وStock Ledger والبقايا.
10. Go-Live checklist والتوقيع على `docs/UAT_v1.0.md`.

لن يتحول الإصدار من `1.0.0-dev` إلى `1.0.0` قبل اجتياز جميع Must requirements وLegacy regression وUAT دون Critical/High defects.
