# 06 — خريطة البيانات والواجهات

> **Status:** Canonical map  
> **Audience:** التشغيل، support، developers

هذه ليست Data Dictionary لكل Field. هدفها أن يعرف القارئ **أين توجد الحقيقة وأي واجهة تخدمها**.

## 1. الـAggregates/DocTypes الأساسية

| المجال | البيانات الأساسية | أين تُستخدم | ملاحظة |
|---|---|---|---|
| الطلب | `Door Cutting Order` + details | Form/List + خدمات الطلب | المحور المركزي |
| خطة القص | `Cutting Plan` + pieces/sources | Order planning / archive / print | Approved snapshot له قواعد immutability |
| المسارات | `Production Routing` + stage definitions | Master Data / settings | المراحل قابلة للضبط |
| التنفيذ | `Production Stage` + events | Shop Floor | Current assignment وstatus |
| الجودة | `Production Incident` | Control/production flow | سجل مشكلة إنتاج |
| التعويض | `Replacement Piece` | replacement workflow | مرتبط بطلب/قطعة أصلية |
| القشاط | `Edge Banding Type` | Order entry / master data | rates/defaults وفق الصلاحية |
| الإعدادات | `Almdina ERP Settings` | Production settings | أقسام settings بصلاحيات منفصلة |
| الصلاحيات | Role + Almdina capability state/audits | Factory Permissions | Capability matrix authority |
| المستخدمون | Frappe `User` | Factory Workforce | Roles تُسند للمستخدم |
| العملاء | Frappe `Customer` | Master Data / orders | CRUD محمي بCapabilities |

## 2. Workspaces الرئيسية في المصدر

- `Almdina ERP`
- `Almdina Control Center`
- `Shop Floor`
- `Almdina Reports`
- `Almdina Settings`
- `Almdina Go Live`

Visibility يجب أن يأتي من permission context/capabilities، لا من نسخ Workspace منفصل لكل اسم Role.

## 3. صفحات مهمة

### يومية/إدارية

- `shop_floor_inbox`: Inbox/Archive للعامل والإنتاج.
- `factory_permissions`: إدارة Capability matrix/roles.
- `factory_workforce`: المستخدمون وإسناد الأدوار.
- `factory_master_data`: البيانات الرئيسية ومنها Production Routing/Customer/Edge types حسب الصلاحيات.
- `factory_production_settings`: إعدادات المصنع المقسمة حسب Capabilities.
- `factory_plan_archive`: أرشيف الخطط المعتمدة.

- قائمة `Door Cutting Order`: بحث Frappe بالاسم/الزبون مع dropdown القسم الحالي (`current_department` عبر `custom_filter_configs`) بجانب زر فلترة Frappe على الويب والموبايل. الخيار الفارغ يعرض «كل الأقسام». العرض عربي من `department_label` في المسارات المفعّلة، والاستعلام يطابق `current_production_stage.stage_type` حتى لا تفشل التسميات المختلفة لنفس المرحلة. قيم التسليم المعروضة في العمود تُترجم إلى `status` عند الاستعلام. الفلتر Presentation فقط؛ query وdocument scope يبقيان عند Frappe. في وضع عرض جميع الطلبات (`view_all_orders` أو Administrator) تُرتَّب الصفوف غير المسلَّمة حسب `modified DESC` ثم تُوضع طلبات `Delivered` في الأسفل.

### مساندة/تشخيص

- Go-live workspace.

### Retired / Removed

- `factory_stock_settings`: أزيل Page source؛ بقيت aliases التاريخية fail-closed وبيانات optimizer المشتركة.
- `factory_system_preflight`: أزيل Page source؛ بقي alias التاريخي fail-closed.
- `factory_performance_benchmark`: أزيل Page source؛ بقي alias التاريخي fail-closed، بينما cutting engine واختبارات الأداء المشتركة بقيت.
- `factory_approval_queue`: أزيل Page source وروابطه بعد إثبات أن عدد طلبات `Pending Review` على الموقع الحي يساوي صفرًا؛ بقيت capability constants/grants، وأغلقت API القديمة دون حذف بيانات صلاحيات.

## 4. أين توجد الحقيقة لكل نوع بيانات؟

### Business formula

Domain. مثال تكلفة أو cut dimension لا يُنسخ في JS.

### Use-case state transition

Application command/use case.

### Persisted document

Frappe DocType + Infrastructure repository/adapter.

### Authorization

Capability catalog + authorization/application policy + Frappe/document scope.

### Visible UI state

يُشتق من permission context وdocument/order state؛ لا يقرر السلطة من نفسه.

## 5. البيانات المالية

صنّف الحقول قبل استخدامها:

- **Operational:** قياسات، حالة، مرحلة، assignee، geometry اللازمة للعمل.
- **Customer-facing sales:** ما يلزم عرض/طباعة مستند الزبون وفق capability.
- **Internal financial:** board/cutting/edge/internal cost breakdown وغيرها من بيانات التكلفة المحمية.

لا تخلط Internal Financial داخل payload تشغيلية عامة فقط لتسهيل الـfrontend.

### Extra door add-ons

- اختيار `دبل قشاط` / `دبل كامل الدرفة` / `Liner` / `فرزة ظهر` / `حفر مسكة غطس` هو Customer requirement محفوظ على `Door Cutting Order Detail`.
- نوع الدرفة يبقى Native dropdown بالقيم `عادية / خاصة / زاوية / زاوية L / Extra`. اختيار `Extra` يفتح Flyout صغيرًا ملاصقًا للسطر لاختيار `دبل قشاط` / `دبل كامل الدرفة` / `لاينر` / `فرزة ظهر` / `حفر مسكة غطس` بشكل متعدد، مع زر صغير لإعادة فتح الإضافات لاحقًا؛ لا تُستبدل قائمة نوع الدرفة بقائمة مخصصة مستقلة.
- أسعار الوحدة والإجماليات حقول مالية محمية وتُحفظ كلقطة تاريخية على السطر، بينما الإجمالي التجاري يُعرض في Cost/فاتورة الزبون.
- `Almdina ERP Settings` هو مصدر أسعار المصنع للطلبات/الإضافات الجديدة؛ تعديل السعر لا يعيد تسعير اختيار محفوظ سابقًا.
- أسعار المصنع الحالية في قسم إضافات Extra: دبل قشاط، أجرة دبل كامل الدرفة (`default_extra_full_door_double_unit_price_usd` لكل درفة أصلية)، Liner، فرزة ظهر (`default_extra_back_groove_unit_price_usd`)، وتفريغ المسكة المخفية.
- حفظ قسم واحد من `factory_production_settings` يكتب الحقول المرسلة فقط؛ الحقول الإلزامية لأقسام أخرى (مثل هوية الطباعة) لا تمنع حفظ أسعار الإضافات أو التكلفة.
- `qty` على السطر تبقى كمية الزبون الأصلية. عند اختيار دبل كامل الدرفة تصبح كمية القص المادية `qty × 2` في المحسّن وقائمة القص ومتطلبات التصنيع، بينما بند الأجرة يبقى `السعر الملتقط × الكمية الأصلية`. أمتار القشاط لا تُضاعف.
- `Special + Liner` أو `Special + فرزة ظهر` لا يستخدم مسار Extra: تُكتب الإضافة في الملاحظات/الرسم ويظل السعر الخاص الشامل هو مصدر السعر.

## 6. Snapshots

Snapshot ليس cache عشوائيًا. له معنى تاريخي/تشغيلي:

- Approved plan snapshot يمثل خطة معتمدة.
- يجب Sanitization للحقول غير التابعة للـcontract.
- تغيير schema للsnapshot يحتاج backward compatibility أو migration مدروس.
- لا تعدّل snapshot تاريخية لمجرد أن formula الحالية تغيرت ما لم يكن هناك قرار migration واضح.

## 7. Audit data

DocTypes مثل Permission/User/Master Data audits موجودة لتتبع تغييرات حساسة. لا تستبدلها بـ`frappe.db.set_value` مبعثر يتجاوز service/audit contract.

## 8. Historical/inactive data

`Board Remnant` وInventory-related modules قد توجد لحماية installations قديمة. قاعدة المنتج الحالية: **لا active UI/workflow/costing جديد يعتمد عليها**.

## 9. عند البحث عن سبب Bug

ابدأ من نوع العرض:

- بيانات طلب خاطئة بعد التنقل: افحص lifecycle/cache/query/UI binding، لا optimizer أولًا.
- زر لا يظهر: افحص permission context + document state + client refresh، لا تضف Role exception.
- عامل يرى طلبًا أجنبيًا: افحص query repository + document scope + assignment.
- Cost ظهر لغير المالي: افحص serializer/snapshot/API وpermlevel.
- DXF لا يطابق الطلب: افحص geometry/units/matching، لا renderer فقط.

## 10. Frontend Estate Retirement Closure

أُغلق التدقيق النهائي بعد دمج PR #287 وإثبات runtime على
`almadina-2.horizontechco.com` أن عدد `Door Cutting Order` بالحالة
`Pending Review` يساوي **0**. هذا الدليل يخص إزالة Approval Queue فقط؛ لم تُحذف
capability constants أو grants المخزنة.

### 10.1 Caller matrix النهائي

| Surface | Caller / navigation result | Backend compatibility | القرار |
|---|---|---|---|
| `factory_stock_settings` | لا Page source أو navigation/workspace/shell caller. | aliases التاريخية إلى `retired_product_endpoint`. | **Retired / Removed** |
| `factory_system_preflight` | لا Page source أو navigation/workspace/shell caller. | alias التاريخي إلى `retired_product_endpoint`. | **Retired / Removed** |
| `factory_performance_benchmark` | لا Page source أو navigation/workspace/shell caller. | alias التاريخي إلى `retired_product_endpoint`؛ cutting engine واختبارات الأداء المشتركة باقية. | **Retired / Removed** |
| `factory_approval_queue` | أزيل Page source وروابط Control Center/Go-Live وshared-shell وsurface/workspace mappings. | أسماء `approval_queue_service` و`order_review_service.reject_order` باقية للتوافق لكنها تفشل عبر `reject_retired_approval_workflow` قبل أي قراءة أو كتابة. submit/approve القديمة تبقى محكومة بسياسة lifecycle التي ترفض الفعل دائمًا. | **Retired / Removed** |
| `factory_plan_archive` | Page source وروابط Control Center/Go-Live وshared-shell وsurface mappings باقية. | `archive_service` نشطة ومحمية بـ`ARCHIVE_APPROVED_PLAN` وdocument scope. | **KEEP** |

البحث النهائي شمل `factory-approval-queue` و`approval_queue_service` و
`approve_order_safely` و`reject_order_safely` و`get_pending_review_orders` و
`APPROVE_ORDER` و`REJECT_ORDER` و`Pending Review`. البقايا المقصودة ليست caller لصفحة:
capabilities/grants محفوظة، والحالات التاريخية المشتركة مع editability/revision/dispatch
بقيت، وأسماء API القديمة أصبحت fail-closed. لم يتغير DCO أو production workflow.

### 10.2 Endpoint retirement policy

| Boundary | الحالة الحالية |
|---|---|
| stock settings + preflight + benchmark historical method names | تبقى aliases fail-closed إلى `retired_product_endpoint`. |
| `approval_queue_service` + `order_review_service.reject_order` | تبقى الأسماء العامة للتوافق فقط؛ كل استدعاء يفشل قبل DB عبر `reject_retired_approval_workflow`. |
| submit/approve compatibility routes | تبقى الأسماء وcapabilities؛ `lifecycle_permissions.py` يرفض `SUBMIT_FOR_REVIEW` و`APPROVE` دائمًا، لذلك لا تعيد API القديمة تشغيل المسار. |
| `archive_service` | active؛ لم يتغير. |

### 10.3 Frappe v16 Page-record removal

الصفحات المحذوفة Standard Pages. في Frappe v16 ينفذ `bench migrate`:

1. `sync_all()` لمصادر Standard Page الموجودة.
2. `post_schema_updates()` ثم `remove_orphan_entities()`.
3. حذف Page records القياسية التي لم يعد لها JSON مصدر.

لا يوجد `delete_doc` patch مخصص. اختبار التكامل يثبت fresh absence، ثم يزرع سجلات
Standard Page تاريخية للصفحات المتقاعدة، ويشغل migrate مرتين مع فحص الغياب بعد كل
مرة. `factory_plan_archive` تبقى مطلوبة في schema/navigation tests.