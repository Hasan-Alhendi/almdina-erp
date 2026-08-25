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

- Go-live workspace.
- `factory_system_preflight`: **Retirement planned; removal pending**؛ endpoint التاريخية fail-closed، لذلك لا تُعامل كصفحة تشخيص نشطة ولا تُصرف عليها lifecycle migration.
- `factory_performance_benchmark`: **Retirement planned; removal pending**؛ benchmark التاريخية fail-closed وليست جزءًا من production user flow.

هذه ليست جزءًا من رحلة العامل اليومية. الصفحات المخطط لتقاعدها تبقى مؤقتًا فقط حتى يكتمل caller/navigation/Page-record audit في Change مستقل.

### Compatibility / scope caution

- `factory_approval_queue`: **Temporary migration utility** لمعالجة سجلات `Pending Review` التاريخية فقط؛ بقاؤها ليس دليلًا أن Review/Approve mandatory في المسار الحالي، وحذفها يحتاج runtime/data proof.
- `factory_stock_settings`: **Retirement planned; removal pending**؛ وجود الصفحة/الكود تاريخيًا لا يعيد المخزون إلى Active Scope v1.1، وحذفها يحتاج caller/navigation/Page-record audit مستقلًا.

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

## 10. Frontend Estate Retirement Audit

أُجري هذا التدقيق على `Develop` عند commit
`0bb7d0da2e5925b84792bdca20400b26fe1cb07e` بعد دمج PR #284. الدليل هنا
**static repository proof** فقط؛ لا توجد في بيئة التدقيق وصلة إلى قاعدة بيانات site
الحية، لذلك لا يجوز استنتاج عدد سجلات `Pending Review` منها.

### 10.1 Caller matrix

جميع الصفحات الخمس تملك فقط ملفات
`page/<page>/{__init__.py,<page>.js,<page>.json}`. لا توجد لها ملفات CSS أو HTML أو
templates أو Python controllers أو assets مستقلة خارج مجلد الصفحة.

| Surface | Navigation / JS callers | Backend boundary | Shared dependency finding | Product scope / Decision |
|---|---|---|---|---|
| `factory_stock_settings` | لا Workspace أو shortcut أو shared-shell route؛ route المباشر يأتي فقط من Standard Page. الـJS يستدعي `settings_access_service.get_stock_settings` و`update_stock_settings`. | الاسمان العامان محفوظان في `hooks.py` وموجهان إلى `legacy_endpoint_service.retired_product_endpoint`؛ implementation الأصلية محذوفة. | حقول stock القديمة محفوظة hidden/read-only، بينما حدود free-area في optimizer ما زالت مستخدمة هندسيًا. هذه الحقول والخدمات المشتركة ليست مملوكة للصفحة ولا تُحذف معها. | Inventory/Warehouse/Reservation/Consumption/Stock Entry/Board Remnant خارج Active Scope v1.1. **RETIRE-SAFE — High**. |
| `factory_system_preflight` | لا Workspace أو shortcut أو Control Center/Go-Live link أو shared-shell route؛ route مباشر فقط. الـJS يستدعي `preflight_service.run_factory_preflight`. | الاسم العام fail-closed عبر `retired_product_endpoint` وملف الخدمة الأصلي محذوف. | كانت الصفحة تفحص routing/core stages/roles/edge master/print formats/reports. لا diagnostics surface حديثة تستدعي هذه الخدمة ولا test تشغيلي يعتمد عليها. | ليست رحلة إنتاج نشطة، ولا يفرض Active Scope بديلًا in-product. **RETIRE-SAFE (REMOVE؛ لا replacement مطلوب حاليًا) — High**. |
| `factory_performance_benchmark` | لا Workspace أو shortcut أو shared-shell route؛ route مباشر فقط. الـJS هو caller الوحيد لـ`performance_service.benchmark_order_cutting_engine`. | الاسم العام fail-closed عبر `retired_product_endpoint` وملف الخدمة الأصلي محذوف. | لا caller من optimizer أو production flow إلى خدمة benchmark. الإشارة في `IMPLEMENTATION_MATRIX_v1.0.md` تاريخية/outdated وليست runtime dependency. | أداة UAT/developer تاريخية، لا production user flow. **RETIRE-SAFE — High**. |
| `factory_approval_queue` | Link + shortcut في `Almdina Control Center` و`Almdina Go-Live`، وroute guard في `shared_shell.js`، وsurface mapping في `surface_access.py` و`workspace_visibility.py`. | `approval_queue_service` نشطة: context/list يتطلبان `APPROVE_ORDER` أو `REJECT_ORDER`؛ reject يقفل الصف ثم يفوض إلى `order_review_service`. مسار approve موجود للتوافق لكنه يُرفض بسياسة lifecycle الحالية. | الكتابة الوحيدة غير الاختبارية لـ`Pending Review` هي `submit_order_for_review`، لكن `lifecycle_permissions.py` يرفض دائمًا submit/approve؛ DCO UI يزيل الزرين. `REJECT_ORDER` يبقى لمسح البيانات التاريخية، وcapabilities نفسها بيانات صلاحيات persisted لا تُحذف ضمن إزالة صفحة. | Review/Approve متقاعدان، لكن احتمال صفوف تاريخية يمنع الحذف دون count حي. **TEMPORARY-MIGRATION-UTILITY / RETIRE-AFTER-DATA-PROOF — High static, runtime blocked**. |
| `factory_plan_archive` | Link + shortcut في Control Center وGo-Live، وshared-shell guard وsurface mappings فعالة. | `archive_service.get_archive_context` و`archive_approved_plan_pdf` active ومحمية بـ`ARCHIVE_APPROVED_PLAN` + document read/scope. | تنشئ/تسترجع PDF خاصًا idempotently، تربطه بـ`Door Cutting Order`، وتتحقق أن الخطة المرتبطة `Approved` ومن نوع `Order`؛ كما تنقل attachment التاريخي من `Cutting Plan` بأمان. | ميزة منتج نشطة مرتبطة بالخطة المعتمدة. **KEEP — High**. |

الـPage JSON لكل سطح هو `standard: "Yes"` و`module: "Almdina ERP"`، واسمه
هو route نفسه. `factory_stock_settings` مقيدة بأدوار Stock/Production/System Manager؛
preflight وbenchmark مقيدتان بـProduction/System Manager؛ queue وarchive لا تضعان
roles ثابتة وتعتمدان على capability context. Administrator قد يصل إلى route، لكن
endpoints المتقاعدة تبقى fail-closed ولا يستعيد System Manager behavior قديمًا.

### 10.2 Endpoint retirement policy

| Boundary | Classification | Later action |
|---|---|---|
| stock settings + preflight + benchmark historical method names | **B — keep fail-closed temporarily** | احذف Page callers لاحقًا، وأبقِ aliases إلى `retired_product_endpoint` لمنع old clients من الوصول لسلوك ملتبس أو resurrected. |
| `approval_queue_service` + `order_review_service` | **D — migration/deprecation window** | لا حذف قبل runtime count = 0 وسياسة واضحة للصفوف التاريخية. حافظ على row lock وdoctype/document capability checks أثناء فترة التصريف. |
| `order_approval_service` وsubmit/approve compatibility routes | **D — compatibility with retired action** | السياسة الحالية تمنع النجاح. تنظيف الأسماء العامة أو capability persisted هو تغيير lifecycle/permissions مستقل، لا يتبع حذف الصفحة تلقائيًا. |
| `archive_service` | **C — shared active implementation** | يبقى؛ اختبارات permission-aware list وdocument authorization وprivate attachment تبقى. |

لا توجد implementation من تصنيف A متبقية خلف الصفحات الثلاث الأولى: ملفات الخدمات
الأصلية حُذفت بالفعل. لذلك إزالة UI لاحقًا لا تبرر حذف fields أو optimizer/domain code
أو fail-closed aliases المشتركة.

### 10.3 Runtime data proof المطلوب

لا توجد site database داخل checkout. يجب تشغيل count read-only على الـsite المقصودة:

```bash
bench --site <site> execute frappe.client.get_count \
  --kwargs '{"doctype":"Door Cutting Order","filters":{"status":"Pending Review"}}'
```

- إذا كانت النتيجة أكبر من صفر: تبقى Approval Queue وروابطها و`REJECT_ORDER` حتى
  تصريف الصفوف أو اعتماد migration policy صريحة.
- إذا كانت صفرًا: تُعاد القراءة قرب وقت removal، ثم يمكن بدء PR تقاعد مستقل. الصفر
  وحده لا يصرح تلقائيًا بحذف Permission Types/legacy public method names.

### 10.4 Frappe v16 Page-record migration design

المشروع يدعم Frappe `>=16,<17`. في v16 يسير `bench migrate` بهذا الترتيب:

1. `sync_all()` يستورد ملفات Standard Page الموجودة.
2. `post_schema_updates()` يستدعي `remove_orphan_entities()`.
3. الـorphan cleanup يبني خريطة ملفات كل التطبيقات المثبتة، ثم يحذف فقط Page records
   المطابقة لـ`standard = "Yes"` إذا لم يعد لها JSON مصدر.

لذلك removal الآمن لاحقًا هو حذف مجلد المصدر المحدد وروابطه في commit واحد، ثم تشغيل
`bench migrate` مرتين واختبارات install/migrate. لا نضيف destructive patch أو
`delete_doc` مخصصًا؛ الـcustom Pages ذات `standard = "No"` ليست ضمن filter. يجب أخذ
site backup الاعتيادي قبل upgrade. rollback هو إعادة ملفات المصدر/الروابط من commit
السابق وتشغيل migrate؛ فيعيد `sync_all()` إنشاء الـStandard Page. لا يحمل أي من سجلات
Page الخمسة business data خاصة به.

### 10.5 Deletion graphs للـPRs اللاحقة

- **Factory Stock Settings:** `[DELETE]` page source + title translations + revisit
  entry + outdated setup link → `[MIGRATION]` Frappe orphan Page cleanup عبر migrate →
  `[KEEP compatibility]` hook aliases fail-closed → `[KEEP shared]` settings data،
  production-settings legacy read view، optimizer free-area inputs، وأي historical
  stock/remnant modules خارج ownership الصفحة.
- **System Preflight:** `[DELETE]` page source + title localization + schema-install
  expectation → `[MIGRATION]` orphan Page cleanup → `[KEEP compatibility]` fail-closed
  hook alias → `[KEEP active]` routing/roles/master-data/print/report tests نفسها؛ لا
  تُحذف لأنها كانت موضوع الفحص القديم.
- **Performance Benchmark:** `[DELETE]` page source + title localization +
  schema-install expectation + outdated implementation-matrix reference →
  `[MIGRATION]` orphan Page cleanup → `[KEEP compatibility]` fail-closed hook alias →
  `[KEEP active]` cutting engine وperformance regression tests.
- **Approval Queue:** `[DATA PROOF REQUIRED]` Pending Review count = 0 → `[DELETE]`
  Control Center/Go-Live links والـshortcuts + page source + shared-shell route + surface
  mappings + queue-specific tests → `[MIGRATION]` orphan Page cleanup →
  `[MIGRATION/DEPRECATION]` queue service و`REJECT_ORDER`/`APPROVE_ORDER` persisted
  grants والlegacy routes. لا يبدأ هذا graph قبل الدليل الحي.

Plan Archive ليست deletion candidate. تبقى source/navigation/surface policy/service
واختبارات security، وأي lifecycle certification لها يكون Change مستقلًا.

### 10.6 Test evolution عند removal

- `test_schema_install.py`: احذف توقع كل Page عند إزالة مصدرها؛ أبقِ Plan Archive،
  وApproval Queue حتى data proof.
- `test_page_revisit_refresh_contract.py`: احذف فقط entries للصفحات المحذوفة؛ أبقِ
  Plan Archive.
- `test_control_center_architecture.py` و`security_endpoint_contracts.py`: أبقِ
  archive/security contracts؛ حوّل queue assertions فقط بعد اكتمال تقاعدها.
- `test_product_scope_contract.py`: يبقى منع navigation وإغلاق stock endpoints، ثم
  يتحول أيضًا إلى absence contract بعد removal.
- `test_final_security_architecture.py` وbackend legacy contracts و
  `test_replacement_planning.py`: تبقى لأنها تحمي حذف implementations القديمة مع
  fail-closed compatibility، لا وجود الصفحة.
- اختبارات localization وfrontend lifecycle/schema التي تسمي صفحة محذوفة تُحدّث مع
  removal نفسه؛ لا تُحذف security regressions أو shared optimizer tests.
