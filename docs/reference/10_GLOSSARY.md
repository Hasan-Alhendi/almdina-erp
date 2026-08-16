# 10 — قاموس مصطلحات Almdina ERP

> **Status:** Canonical glossary

| المصطلح | المعنى في المشروع |
|---|---|
| **DCO** | اختصار `Door Cutting Order`، المستند المركزي للطلب |
| **درفة / Piece** | قطعة/درفة مطلوبة بأبعاد وكمية وخصائص قشاط/شكل |
| **Board** | اللوح الخام الموصوف في الطلب؛ Active Scope لا يشترط ERPNext Stock Item |
| **Edge / قشاط** | تلبيس حافة القطعة؛ قد يكون لكل ضلع اختيار مختلف |
| **Cut Dimensions** | أبعاد القص الفعلية بعد تطبيق قواعد القشاط/السماكة |
| **Kerf** | عرض المادة المفقودة بسبب أداة القص/المنشار بين المسارات |
| **Trim Margin** | هامش تشذيب/أمان حول اللوح وفق إعدادات التخطيط |
| **Cutting Plan** | توزيع القطع على لوح/ألواح مع Geometry وmetadata |
| **System Plan** | خطة أنشأها optimizer داخل النظام |
| **Custom/Uploaded Plan** | خطة جاءت من تدخل/ملف خارجي وفق validation |
| **Approved Production Plan** | الخطة المختارة والمثبتة للإنتاج؛ ليست نفس مفهوم Approval القديم للطلب |
| **Snapshot** | تمثيل محفوظ للحقيقة في لحظة معينة؛ يستخدم للتاريخ/الإنتاج ولا يعاد تفسيره عشوائيًا |
| **DXF** | ملف CAD هندسي للتبادل مع أدوات التصميم/CNC؛ Geometry التشغيلية بالـmm |
| **Special Drawing** | رسم توضيحي/هندسي للدرفة الخاصة مرتبط بالطلب |
| **Production Routing** | تعريف قابل للضبط لتسلسل مراحل الإنتاج |
| **Routing Stage** | تعريف مرحلة داخل Route: sequence + stage type + label + operational role |
| **Production Stage** | Instance فعلية لمرحلة على طلب معين، لها status وassignee |
| **Current Stage** | المرحلة النشطة حاليًا للطلب |
| **Operational Role** | Role المطلوب وظيفيًا لتنفيذ مرحلة Route |
| **Assignee** | المستخدم المحدد الذي أُسندت إليه Stage فعلية |
| **Role** | Frappe Role يُعطى للمستخدم ويجمع صلاحيات/Capabilities |
| **Capability** | مفتاح سلطة تجارية محدد مثل `upload_dxf` أو `view_costs` |
| **DocPerm** | نظام Frappe الأساسي لصلاحيات DocType/permlevel؛ ليس كامل Business Authorization وحده |
| **Permlevel** | مستوى حماية Field في Frappe، يستخدم مثلًا لفصل بعض البيانات المالية |
| **Document Scope** | هل هذا المستخدم يحق له الوصول إلى هذا المستند تحديدًا، وليس DocType عمومًا فقط |
| **IDOR** | ثغرة وصول لكائن أجنبي بمجرد تغيير ID/name في الطلب |
| **Incident** | حادث/خطأ إنتاج مسجل على طلب/قطعة/مرحلة |
| **Replacement Piece** | قطعة تعويض مرتبطة بقطعة/حادث أصلي ولها workflow خاص |
| **Inbox** | العمل النشط المسند للمستخدم |
| **Archive** | تاريخ العمل المنتهي للمستخدم/السياق المعروض |
| **Revision** | نسخة جديدة من الطلب لحفظ التاريخ بدل تعديل حقيقة سابقة بصمت |
| **Legacy** | كود/سلوك قديم باقٍ مؤقتًا للتوافق أو migration |
| **Compatibility facade** | واجهة رقيقة تبقي caller قديمًا يعمل دون أن تصبح مكانًا لBusiness Logic جديد |
| **Tombstone** | endpoint/module متقاعد يبقى كعلامة/رفض آمن بدل حذف قد يكسر caller قديم |
| **Fail closed** | عند عدم القدرة على إثبات السماح، يرفض النظام بدل السماح الافتراضي |
| **Canonical** | المرجع الرسمي الحالي الذي يجب البدء منه |
| **Historical** | وثيقة/كود للتاريخ والتدقيق، لا يحدد Feature جديدة وحده |
| **Invariant** | قاعدة يجب ألا تتغير أثناء تعديل غير مخصص لتغييرها |
| **Blast Radius** | مساحة التأثير المحتملة للتعديل عبر ملفات/طبقات/Features |
| **ADR** | Architecture Decision Record؛ قرار مكتوب مطلوب قبل تغيير معماري واسع بعد Stage 15 |
| **CI** | الاختبارات الآلية على GitHub Actions |
| **UAT** | User Acceptance Testing، اختبار قبول المستخدم/البيئة الفعلية |
| **Runtime baseline** | Commit يمثل آخر حالة Runtime مجتازة قبل توثيق/freeze معين |

## أسماء الحالات

بعض الحالات مثل `Pending Review` و`Approved` قد تبقى في البيانات أو compatibility. لا تستنتج من وجود اسم Status أن المسار الإجباري الحالي يمر بها. المرجع الحالي هو [Workflow](03_WORKFLOWS.md) + Domain tests.