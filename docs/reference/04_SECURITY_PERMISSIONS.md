# 04 — الصلاحيات والأمان

> **Status:** Canonical / Security-critical  
> **Audience:** مسؤولو النظام، developers, QA

## 1. النموذج الأمني في جملة واحدة

```text
Allowed action
= Business Capability
+ Document visibility/scope
+ Lifecycle state
+ Production stage operational role (عند الحاجة)
+ Current assignment (عند الحاجة)
+ Action-specific structural rules
```

إخفاء زر في الواجهة ليس Authorization.

## 2. Role وCapability ليسا الشيء نفسه

### Frappe Role

اسم/مجموعة تُسند للمستخدم. يمكن إنشاء Roles جديدة من الواجهة.

### Business Capability

مفتاح ثابت يعبّر عن فعل محدد مثل `edit_order`, `upload_dxf`, `view_costs`, `dispatch_order`.

الـRole يحصل على مجموعة Capabilities. لذلك لا نكتب كودًا جديدًا يقول: “إذا كان اسم الدور Cutting Operator فاسمح”.

### Operational Role

كل Stage في `Production Routing` يحمل `operational_role`. هذا يحدد نوع العامل المقبول للمرحلة.

### Assignment

حتى لو كان المستخدم يحمل الدور التشغيلي الصحيح، يجب في أفعال العامل اليومية أن تكون **المرحلة مسندة إليه** عندما يتطلب العقد ذلك.

## 3. Administrator وSystem Manager

- `Administrator`: Superuser صريح في النظام.
- `System Manager`: لا يحصل تلقائيًا على Factory business authority لمجرد الاسم.

Stage 12/14 تختبران أن Role name وحده لا يفتح الإنتاج أو التكلفة.

## 4. دورة إنشاء الصلاحيات المستهدفة

```mermaid
flowchart LR
    A[إنشاء Role] --> B[تحديد Capabilities للدور]
    B --> C[إنشاء/اختيار User]
    C --> D[إسناد Role أو Roles]
    D --> E[Runtime يجمع Capabilities]
    E --> F[Document/Stage scope يضيق الوصول]
```

لا يوجد “ملف تشغيلي” مخفي يجب على الإدارة فهمه قبل إنشاء المستخدم.

## 5. Capability catalog الرسمي

المصدر البرمجي: `domain/security/authorization.py`.

### Orders

`view_orders`, `view_all_orders`, `create_order`, `edit_order`, `create_order_revision`, `submit_order`, `approve_order`, `reject_order`, `cancel_order`, `resume_cancelled_order`.

### Costing & documents

`view_costs`, `edit_cost_settings`, `edit_special_price`, `approve_special_price`, `approve_final_price`, `cancel_final_price_approval`, `print_measurements`, `print_customer_invoice`, `print_internal_cost_report`.

`approve_final_price` يعتمد السعر النهائي لإجمالي طلب القص ويثبّت سجل اعتماد مستقل. هي مستقلة عن اعتماد أسعار الدرف الخاصة وعن اعتماد خطة القص، ولا تُمنح لأي دور افتراضيًا. يُسمح بالاعتماد في أي مرحلة إنتاجية (بما فيها ما بعد الرسم) مع نطاق الوصول و`view_costs` واكتمال/حداثة التسعير؛ لا يُشترط Draft ولا تُستخدم سياسات تحرير الطلب أو تسعير الدرف المقيدة بالمسودة. الاعتماد يغيّر حالة السعر فقط دون حالة الطلب أو مرحلته أو إسناده أو اعتماد خطة القص. **Approved وحدها لا تمنع** تحرير تفاصيل الطلب أو خطة القص أو إعدادات التكلفة (`board_rate_usd` / `cutting_cost_per_board_usd` / `offcut_price_usd`)؛ التحرير يبقى محكوماً بـ`edit_order` / `edit_cost_settings` ونطاق المستند ودورة حياة الطلب/الخطة. المرحلة الثانية تضيف `approve_order_final_price` مع رمز أساس سعر (`price_basis_token`) من `get_order_cost_snapshot`. المرحلة الثالثة تُبطل الاعتماد تلقائياً عند حفظ تغيير مؤثر في أساس التسعير (بما فيها أسعار اللوح/القص/الفضلة) دون منح `approve_final_price` أو `cancel_final_price_approval` لمنفّذ التغيير. استثناء محدد: تغيير خوارزمية القص الذي يُبقي عدد الألواح والأساس المالي كما هما لا يُبطل الاعتماد. المرحلة الرابعة تضيف زر الاعتماد وشارة حالة السعر في تاب التكلفة مع إشعار Toast خفيف عند الإبطال التلقائي الفعلي لمن يملك `approve_final_price` أو `cancel_final_price_approval`. المرحلة الخامسة تضيف فلتر قائمة الطلبات وشارة حالة السعر في القائمة من الحقل `price_approval_status` فقط دون كشف مالي إضافي.

`cancel_final_price_approval` تلغي اعتماد السعر النهائي للطلب مع الاحتفاظ بسجل الموافقة وتفاصيلها. هي مستقلة عن `approve_final_price` وعن `edit_order` و`edit_cost_settings` وأسعار الدرف الخاصة و`view_all_orders`، ولا تُستنتج من أي قدرة حالية ولا تُمنح لأي دور أو قالب افتراضي. منحها يضيف `view_orders` و`view_costs` فقط مع الإبقاء على نطاق المستند. `Administrator` يبقى الاستثناء الصريح، و`System Manager` لا يصبح استثناء. الإبطال التلقائي الناتج عن تعديل مصرح به لا يتطلب قدرة الإلغاء اليدوي. حقل `approval_note` جزء من سجل الاعتماد التاريخي ويُحمى من التعديل عند الإبطال، ولا يدخل في بصمة التسعير.

أمر الاعتماد `approve_order_final_price(order_name, expected_price_basis_token, approval_note=None)` يقبل ملاحظة اختيارية (نص حتى 500 حرفاً، تُطبَّق عبر `normalize_approval_note`) وتُحفظ في سجل `Door Cutting Price Approval` فقط. إعادة الاعتماد لنفس الأساس تعيد الملاحظة الأصلية دون استبدالها. أمر الإلغاء اليدوي `cancel_order_final_price_approval(order_name, expected_current_price_approval)` يتطلب تطابق سجل الاعتماد الحالي؛ السبب الثابت `manual_price_approval_cancelled` مع `invalidated_by`؛ التكرار لنفس السجل الملغى لا يعيد كتابة الوقت/المنفّذ؛ موافقة أحدث تُرفض. الإلغاء اليدوي لا يطلق إشارة Toast الإبطال التلقائي. واجهة تاب التكلفة تربط النافذة/الزر بهذين الأمرين دون منح الصلاحيات أو إعادة بناء قواعد الأهلية في JavaScript.

### Cutting plan / drawing / DXF

`view_cutting_plan`, `view_system_cutting_plan`, `view_uploaded_cutting_plan`, `view_approved_cutting_plan`, `recalculate_plan`, `edit_optimizer_settings`, `print_cutting_plan`, `view_drawing_workspace`, `edit_special_drawing`, `export_dxf`, `upload_dxf`, `replace_dxf`, `approve_dxf`.

`approve_dxf` اسم تاريخي محفوظ للتوافق، ومعناه التجاري الحالي اعتماد Production Cutting Plan المختارة سواء كانت System أو imported/custom.

`archive_approved_plan` يفتح أرشيف الخطط المعتمدة ولا يمنح تعديل الخطة.

### Production

`dispatch_order`, `start_assigned_stage`, `handoff_assigned_stage`, `revert_department`, `return_order_to_draft`, `mark_delivered`, `reassign_worker`.

### Shop Floor visibility

`view_shop_floor_history` يتحكم فقط بعرض سجل الطلبات المنتهية داخل صالة الإنتاج.

العقد ثابت:

- لا يمنح دخول Shop Floor بمفرده؛ الدخول يبقى محكومًا بـ`SHOP_FLOOR_ACCESS_CAPABILITIES`.
- لا يمنح `view_orders` أو `view_all_orders` ولا يوسّع Document scope.
- لا يمنح أي Production action. صف `Ready for Delivery` الحالي قد يبقى ضمن بيانات اللوحة التشغيلية لأنه حالة عمل حية، وليس سجلًا تاريخيًا.
- للعامل ذي النطاق المسند، تُظهر قائمة الطلبات المرحلة الحالية النشطة فقط (`Pending` / `In Progress` / `Paused`) عند تعطيله. مرحلة حالية مكتملة بعد آخر مرحلة (`Ready for Delivery`) ليست عملًا نشطًا لذلك تخرج من العدد والقائمة ومن `has_permission`؛ عند تفعيله تُضاف الطلبات التي أكمل فيها مرحلة سابقة.
- فتح طلب تاريخي مباشرةً يخضع للعقد نفسه؛ معرفة اسم الطلب أو رابطه لا تتجاوز إخفاء السجل.
- هذا القيد يخص سطح سجل الطلب نفسه، ولا يلغي وصولًا مستقلًا ومصرحًا به إلى خطة قص مرتبطة بإسناد سابق مكتمل.

### Reports

تقارير الاستعلام التشغيلية والمالية لم تعد جزءًا من المنتج. قدرتا `view_operational_reports` و`view_financial_reports` متقاعدتان. عرض التكلفة الداخلية يبقى عبر `view_costs`، وطباعة تقرير التكلفة الداخلي للطلب تبقى عبر `print_internal_cost_report`.

### Workforce

`view_users`, `create_users`, `edit_users`, `assign_user_roles`, `enable_users`, `disable_users`, `reset_user_password`.

### Factory settings

`view_factory_settings`, `edit_factory_cutting_defaults`, `edit_factory_cost_defaults`, `edit_factory_production_controls`, `edit_factory_print_identity`, `manage_whatsapp_session` (إنشاء جلسة المصنع وربطها وإعادة الاتصال)، `edit_whatsapp_messages` (نصوص القياسات والفاتورة وإتمام المراحل)، `manage_backups` (الإعداد والجدولة والنسخ اليدوي واختبار SSH والسجل)، و`restore_backups` (الاستعادة المؤكدة فقط). عرض الإعدادات لا يمنح ربط الجلسة أو إدارة النسخ، و`manage_backups` لا يمنح الاستعادة. لا يحصل `System Manager` على أي منهما تلقائيًا؛ `Administrator` هو الاستثناء الصريح.

`manage_customer_bot_access` صلاحية مستقلة لاعتماد رقم إضافي لمتابعة العميل أو رفضه أو إلغاء اعتماده. لا تُستنتج من `manage_whatsapp_session` أو `edit_whatsapp_messages`، ولا تُمنح تلقائيًا لدور أو لـ`System Manager`. سجلات الطلب والوصول لا تُعدَّل من CRUD عام؛ القرار يمر بحالة الاستخدام، والقراءة تبقى مشروطة بهذه الصلاحية وبنطاق قراءة العميل.

اختيار نسخة للاستعادة يكون بمعرّف عملية محلية مكتملة من السجل، وليس بمسار يرسله العميل. يتحقق الخادم من نطاق ملفات النسخة وحجمها وchecksum، وينشئ نسخة أمان قبل استدعاء Frappe Restore. حقول SSH الحساسة من نوع `Password` وتبقى في مخزن Frappe المشفر؛ لا تُعاد قيمها إلى المتصفح أو السجل أو رسائل الخطأ.

### Master data

Production Routing CRUD, Customer CRUD, Edge Banding Type CRUD عبر مفاتيح `view/create/edit/delete_*` المقابلة.

### Administration

`manage_permissions`.

## 6. حماية التكلفة

`view_orders` لا يعني `view_costs`.

قواعد ثابتة:

- Financial scalar fields الحساسة تستخدم Permission Level أعلى حيث يلزم.
- API/preview يجب أن يحذف الحقول المالية لمستخدم غير مخول، لا أن يرسلها بقيمة صفر.
- Operational plan snapshots لا تحمل cost payload يلتف حول Permission Level.
- Customer-facing document منفصل عن Internal cost report.
- Reports المالية تتطلب Financial reporting capability.
- `edit_cost_settings` يُضيَّق بالقدرة ونطاق المستند (غير محفوظ / مقدَّم أو ملغى / نسخة مستبدلة)، ولا يُضيَّق بحالة الطلب التشغيلية. الأمر يحدّث الخطة المالية ذات الهندسة (المسودة إذا ملكت عدد ألواح، وإلا الخطة المعتمدة بعد الإنتاج) ولا ينشئ مراجعة خطة جديدة. تسعير الدرف الخاصة (`approve_special_price` / `edit_special_price`) يبقى Draft-only. اعتماد Production Cutting Plan لا يشترط إدخال أسعار أو تكلفة؛ شرط الأسعار الخاصة يبقى على طباعة الفاتورة والمستندات المالية.

## 7. Whitelisted endpoints

كل `@frappe.whitelist()` يجب أن يكون مصنفًا في Contract ثابت:

- `capability`: endpoint يملك authorization صريحًا.
- `delegate`: يفوض لطبقة أخرى تملك العقد.
- `fail_closed`: endpoint متقاعد أو غير قابل للاستخدام ويغلق افتراضيًا.
- `self_context`: يعيد Context خاصًا بالمستخدم الحالي دون فتح Document أجنبي.

`tests/security_endpoint_contracts.py` + CI تمنع إضافة Endpoint جديد بلا تصنيف.

## 8. IDOR / Document scope

لا يكفي أن يعرف المستخدم:

- اسم DCO.
- اسم Production Stage.
- اسم Cutting Plan.
- اسم/URL File.

قبل القراءة أو التعديل يجب التحقق من parent relationship وdocument access وassignment/capability المطلوبة. File/DXF يجب أن يبقى scoped للطلب المقصود، لا “أي File يعرف المستخدم اسمه”.

## 9. Frappe DocPerm مقابل Business Capability

سلطة منح القدرة للدور (Who) تُقرأ وتُكتب عبر أعمدة `Custom DocPerm` / Permission Types لأدوار المصنع القابلة للتعديل فقط. `Almdina Role Capability State` متقاعد من مسار التشغيل ويُستخدم فقط كتوافق ترحيل/تاريخي عند ترقية المواقع.

المبدأ:

- Frappe Custom DocPerm (لأدوار المصنع القابلة للتعديل) = من يملك القدرة.
- Almdina Domain/Application authorization = متى وعلى أي مستند/مرحلة يمكن استعمالها (lifecycle، scope، assignment، operational role، عزل التكلفة، IDOR).
- `frappe.has_permission` للمستند يُستخدم تضييقًا لنطاق Door Cutting Order / Cutting Plan بعد ثبوت المنح، وليس كبديل عن قراءة أعمدة القدرة.
- أدوار المنصة المحمية (`System Manager` وغيرها) لا تُحسب كمصدر سلطة مصنع. `Administrator` هو الاستثناء الصريح.
- غياب الصف/العمود = رفض (fail closed).

Hook يستطيع الرفض، لكنه لا يجب أن يُستخدم كطريقة عشوائية لتعويض غياب grant أساسي بلا تصميم.

## 10. Privilege escalation

عند تعديل إدارة المستخدمين/الصلاحيات اختبر خصوصًا:

- منح `manage_permissions`.
- تغيير أدوار المستخدم الحالي.
- تعطيل/تمكين المستخدمين.
- Roles النظام المحمية.
- Imports/bulk permission updates.
- Self-lockout.
- User لديه Production assignments نشطة.

## 11. Audit

تغييرات حساسة في المستخدمين/الصلاحيات/البيانات الرئيسية يجب أن تبقى قابلة للتدقيق عبر Audit DocTypes/Services الموجودة، ولا تُستبدل بتعديل DB مباشر.

## 12. Checklist لأي Feature

قبل الدمج اسأل:

- ما Capability المطلوبة؟
- هل القراءة تحتاج `view_all_orders` أم scope أضيق؟
- هل الفعل stage-scoped؟
- هل assignment مطلوب؟
- هل البيانات تحتوي Cost؟
- هل endpoint يمكن استدعاؤه مباشرة دون UI؟
- هل Document name أجنبي سيُرفض؟
- هل Administrator فقط له bypass، أم حتى هو يخضع لقاعدة بنيوية؟
