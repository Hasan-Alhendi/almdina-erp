# Almdina ERP

نظام إدارة معمل MDF والقص مبني على ERPNext / Frappe.

## Version 1.0 — Scope Lock

النسخة الأولى من المشروع يجب أن تطابق **وثيقة متطلبات نظام إدارة معمل MDF والقص v1.0** المعتمدة للمشروع حرفيًا من حيث النطاق والسلوك الوظيفي.

- لا تُضاف أي ميزة غير موجودة في المتطلبات المعتمدة للنسخة 1.0.
- لا يُحذف أو يُختصر أي متطلب معتمد للنسخة 1.0.
- أي تطوير أو توسعة مستقبلية تتم في إصدار لاحق وبشكل منفصل عن Baseline v1.0.
- وثيقة المتطلبات الموجودة في `docs/REQUIREMENTS_v1.0.md` هي المرجع الرسمي لقبول النسخة الأولى واختبارها.
- السلوك الموجود في Client Script المرجعي السابق يعد Baseline وظيفيًا إلزاميًا؛ لا يجوز أن تفقد إعادة الهندسة أي وظيفة منه.

**Baseline:** v1.0

## Implementation Status

التطوير مستمر مباشرة على فرع `main`. ما يلي منفذ حاليًا، لكنه **ليس إعلانًا عن اكتمال v1.0**:

### الطلب والقص
- Frappe/ERPNext v16 app package scaffold.
- `Door Cutting Order` و`Door Cutting Order Detail` مع Revision وقفل التعديل بعد الاعتماد.
- حسابات Server-side للمساحة والقشاط والتكلفة وKerf/Trim.
- محرك القص Server-side لجميع خوارزميات Baseline الـ17 بالإضافة إلى `Auto`.
- Geometry validator مستقل للحدود والتداخل وعدد القطع والدوران.
- Immutable `Cutting Plan` Snapshot مرتبط بالإصدار المعتمد.
- استعادة واجهة الكود المرجعي: Live preview، خطوط القشاط، Excel-like Enter، الأزرار الخمسة، طباعة خطة القص، طباعة القياسات، وDXF R12 بطبقتي `CUT_PATH` و`SHEET_OUTLINE`.
- دعم الرسم والطباعة وDXF لمصادر مختلفة المقاس عند استخدام Board Remnants مع إبقاء سلوك الألواح الكاملة مطابقًا للـBaseline.

### Master Data والمخزون
- `Edge Banding Type` مع الأنواع الـ12 والأسعار المرجعية نفسها وخصائص العرض/التشطيب/يدوي-آلي وربط صنف المخزون.
- حقول MDF على `Item`: الطول والعرض والسماكة واللون والمادة وعلامة Is MDF.
- `Almdina ERP Settings` لسياسات القص والمخزون والبقايا والإنتاج.
- فحص المخزون مع مراعاة الحجوزات النشطة للطلبات الأخرى.
- `Material Reservation` اختياري عند الاعتماد.
- `Material Consumption Log` وStock Entry Material Issue عند نقطة الاستهلاك المحددة.
- `Board Remnant` بحالات Available/Reserved/Consumed/Scrapped، حجز ذري، وإعادة استخدام البقايا المطابقة قبل الألواح الكاملة عند تفعيل السياسة.
- توليد بقايا مستطيلة غير متداخلة بعد انتهاء القص وفق حدود الحد الأدنى المحددة.

### Workflow والإنتاج
- Draft → Pending Review → Approved مع رفض وإعادة Revision.
- `Production Routing` Master مع Routing افتراضي مطابق لنواة v1: Review/Preparation → Cutting → Edge Banding.
- `Production Stage` مع Start/Pause/Resume/Finish والعامل والزمن الفعلي وطرح فترات التوقف.
- Append-only `Production Stage Event` لتدقيق أحداث المراحل.
- تسلسل المراحل إلزامي مع Override مضبوط بالصلاحية والإعداد.
- إلغاء طلب مضبوط مع تحرير الحجوزات وعكس Stock Entry صراحةً، ومنع العكس الوهمي بعد اكتمال القص وتغير المادة فعليًا.

### الأخطاء والتعويض
- `Production Incident` مرتبط بالطلب والمرحلة والقطعة والعامل والسبب.
- `Replacement Piece` مرتبط بالقطعة الأصلية مع نقل المقاس والقشاط وعدم تحميل خطأ المعمل على العميل.
- البحث عن Remnant مطابق وحجزه ذريًا للتعويضات.

### الجودة الآلية الحالية
- Regression tests أولية لمحرك القص.
- GitHub static workflow لفحص JSON وPython syntax وJavaScript syntax على تغييرات `main` وPull Requests.

## ما يزال غير مكتمل قبل إعلان v1.0

- إكمال Mini Cutting Plan ودورة اعتماد/استهلاك القطعة التعويضية بالكامل.
- إكمال Planned vs Actual Cost وربط تكلفة التعويض الفعلية بالطلب.
- استكمال تقارير v1 ولوحات المتابعة المطلوبة في SRS.
- استكمال الترجمة العربية/الإنجليزية للمصطلحات الأساسية واختبار RTL/LTR.
- استكمال اختبارات Unit/Integration/Permissions/Regression/UAT، بما فيها مقارنة نتائج الكود المرجعي حالة بحالة.
- اختبار تثبيت التطبيق و`bench migrate` على بيئة Frappe/ERPNext v16 فعلية، ثم اختبار Stock Entry/DXF/PDF/Printing end-to-end.
- Go-Live checklist وBackup/Restore test.

سيبقى الإصدار `1.0.0-dev` إلى أن تمر **كل** متطلبات SRS وكل وظائف الكود المرجعي باختبارات القبول دون نقص.
