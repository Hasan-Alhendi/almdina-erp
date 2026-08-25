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

### مساندة/تشخيص

- `factory_system_preflight`.
- `factory_performance_benchmark`.
- Go-live workspace.

هذه ليست جزءًا من رحلة العامل اليومية.

### Compatibility / scope caution

- `factory_approval_queue`: قد يبقى لآثار Review/Approve، لكنه ليس دليلًا أن Review/Approve mandatory في المسار الحالي.
- `factory_stock_settings`: وجود الصفحة/الكود تاريخيًا لا يعيد المخزون إلى Active Scope v1.1.

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

- اختيار `Double` / `Liner` / تفريغ المسكة المخفية هو Customer requirement محفوظ على `Door Cutting Order Detail`.
- أسعار الوحدة والإجماليات حقول مالية محمية وتُحفظ كلقطة تاريخية على السطر، بينما الإجمالي التجاري يُعرض في Cost/فاتورة الزبون.
- `Almdina ERP Settings` هو مصدر أسعار المصنع للطلبات/الإضافات الجديدة؛ تعديل السعر لا يعيد تسعير اختيار محفوظ سابقًا.
- `Special + Liner` لا يستخدم مسار Extra: يكتب Liner في الملاحظات/الرسم ويظل السعر الخاص الشامل هو مصدر السعر.

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
