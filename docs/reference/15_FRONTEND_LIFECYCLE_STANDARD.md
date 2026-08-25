# 15 — Project-wide Frontend Lifecycle Standard

> **Status:** Canonical frontend lifecycle specialization
> **Audience:** Frontend developers, reviewers, QA, Coding AI
> **Parent frontend contract:** [13 — Frontend Architecture](13_FRONTEND_ARCHITECTURE.md)
> **Ownership baseline:** [14 — Frontend Refactor Closure](14_FRONTEND_REFACTOR_CLOSURE.md)
> **Scope:** Lifecycle governance, ownership, identity, async safety, cleanup, and certification
> **Non-goals:** Runtime migration, UI redesign, business-rule changes, authorization changes, backend changes

## 1. الهدف والسلطة

هذه الوثيقة هي المرجع الرسمي المتخصص لدورة حياة الواجهة في Almdina ERP. تبقى
[13 — Frontend Architecture](13_FRONTEND_ARCHITECTURE.md) الوثيقة الأعلى لتنظيم
Frontend architecture والحدود بين Entry وController وState وAPI وRenderer، بينما
تحدد هذه الوثيقة كيف تُدار حياة كل surface داخل تلك الحدود.

المبدأ الحاكم:

```text
Unified lifecycle rules
!=
One lifecycle implementation for everything
```

لا تفرض هذه الوثيقة `bindActivationLifecycle()` على كل surface، ولا تنشئ
`AlmdinaLifecycle` mega-framework فوق Frappe. تستخدم كل عائلة hooks وprimitives
الصغيرة المناسبة لهويتها الفعلية.

إذا تعارض تنفيذ قائم مع هذه الوثيقة، لا يعني ذلك أن التنفيذ يُعدل ضمن أي PR عابر.
تُسجل الفجوة، وتُرحّل في Change مستقل محدود مع runtime regressions مناسبة.

## 2. نموذج الحياة والمصطلحات

الحالات المفاهيمية المشتركة هي:

```text
Mounted -> Active <-> Inactive -> Disposed
```

- **Mounted:** المالك أنشأ state والموارد وربط dependencies اللازمة.
- **Active:** الـsurface هي السياق الحالي المسموح له بتحديث UI.
- **Inactive:** الـsurface باقية في الذاكرة أو DOM، لكنها ليست السياق الحالي.
- **Disposed:** انتهى المالك نهائيًا ونُظفت موارده؛ لا يجوز له استئناف العمل.
- **Identity:** السجل/المسار/الفلاتر/سياق العمل الذي بدأت العملية من أجله.
- **Generation:** نسخة متزايدة من حياة الهوية أو التفعيل تمنع العمل الأقدم من commit.
- **Commit:** أي تغيير في state أو DOM أو alert/dialog أو تنزيل ملف أو focus أو route
  ينتج عن async completion.

القاعدة الأساسية:

> **Deactivate != Dispose.**

Frappe Desk قد يبقي page أو form أو list mounted بعد مغادرتها. لذلك deactivation
يبطل العمل المرتبط بالزيارة الحالية، لكنه لا ينهي المالك أو يمحو state تلقائيًا.

## 3. Lifecycle families المعتمدة

| Family | الاسم | الهوية الأساسية |
|---|---|---|
| A | Cached Frappe Custom Page | wrapper + page route + activation generation |
| B | Frappe Form / Document | doctype + document name + document generation |
| C | Collection Surface | collection execution snapshot + generation |
| D | Stateful Special Workspace | workspace identity + open generation |
| E | Global / Shared Runtime | singleton module key + Desk session |

تنقسم Family C إلى عقدين متخصصين: **C1 — List View** بهوية
doctype + view/filter/order/page snapshot، و**C2 — Query Report** بهوية report +
filter snapshot + execution generation عند وجود custom async behavior.

Dialogs وPopovers وConfirm وPrompt وAudit Dialog وغيرها من **Transient Child Surfaces**
ليست lifecycle family مستقلة. الـsurface الأب يملك إنشاءها، وasync work
الخاص بها، وإغلاقها أو تجاهل completions التابعة لها عند deactivation/dispose.

## 4. Shared Lifecycle Contract

المعرفات التالية ثابتة. تغيير معناها Contract change مقصود.

### `FE-LC-001` — Mount ownership

لكل surface مالك mount واحد معلن. هو الذي ينشئ mutable state ويربط lifecycle
resources ويحدد public instance. لا تتنافس global وDOM وcontroller instances على
ملكية الحياة نفسها.

### `FE-LC-002` — Activation ownership

جهة واحدة تحدد الانتقال بين Active وInactive وفق hooks الحقيقية للعائلة. التفعيل
المتكرر للحالة النشطة نفسها لا يبدأ زيارة جديدة ولا يكرر listeners أو reads دون سبب.
Deactivation منفصل صراحةً عن disposal.

### `FE-LC-003` — Dispose ownership

للـsurface مسار dispose نهائي واحد، idempotent، ينظف كل الموارد التي يملكها ويبطل
tokens المتبقية. `hide` أو route change لا يساوي dispose إلا إذا كان host contract
يضمن أن الـsurface انتهت نهائيًا.

### `FE-LC-004` — Async request ownership

كل read أو mutation أو asset load أو file operation يتبع owner وهوية/generation
واضحين. يجب أن يعرّف المستهلك أين يمكن تخزين النتيجة، وأين يمكن رسمها، وما الذي
يبطلها.

### `FE-LC-005` — Current identity and generation

كل عملية قابلة لأن تصبح قديمة تلتقط token عند البدء. يضم token الهوية المناسبة
للعائلة وgeneration أو request sequence. المقارنة لا تعتمد على السرعة المتوقعة
للشبكة أو على بقاء DOM موجودًا.

### `FE-LC-006` — Stale response rejection

لا تستطيع نتيجة stale تغيير state أو DOM أو feedback لسياق أحدث. يجوز فصل شرط
**same identity** لتخزين data عن شرط **current/active identity** المطلوب للرسم، كما
يفعل `AlmdinaDocumentContext`، لكن الفصل يجب أن يكون صريحًا ومختبرًا.

### `FE-LC-007` — Event listener ownership

كل listener محلي أو global له owner وحد تنظيف. التسجيل يكون namespaced أو delegated
أو tracked، وإعادة التركيب تستبدل التسجيل السابق. Global singleton listeners تحل
السياق الحالي وقت التنفيذ ولا تحتفظ بوثيقة قديمة.

### `FE-LC-008` — Timer and RAF ownership

كل `setTimeout` و`setInterval` و`requestAnimationFrame` مرتبط بـsurface يملك key
وcleanup/current check. لا يرسم callback إذا تغيرت الهوية أو انتهى owner، ولا تنشئ
refreshes المتكررة سلسلة عمل مؤجل متضاعفة.

### `FE-LC-009` — MutationObserver ownership

لكل مسؤولية مراقبة owner واحد وmutation boundary ضيقة و`disconnect()` معروف. لا
يُنشأ Observer ثانٍ لإبطال Observer أول، ولا تُنقل مراقبة feature محلية إلى global
runtime لتسهيل الوصول إليها.

### `FE-LC-010` — Dirty-state policy

كل surface قابلة للتحرير تعلن سياسة dirty state: preserve أو prompt أو block أو
explicit discard. يمنع automatic reload أو server reconciliation من الكتابة فوق
تعديلات غير محفوظة أو تقديمها كأنها محفوظة.

### `FE-LC-011` — First-load contract

عندما يملك التطبيق Frappe Custom Page، ينشئ scaffold وحالة loading محايدة قبل أول
async boundary. أما Form/List/Report التي يملك Frappe shell الخاص بها فتحترم host
lifecycle ولا تعيد إنشاء shell موازٍ بلا حاجة.

### `FE-LC-012` — Revisit contract

كل family تعرّف معنى revisit ومتى تحتاج fresh read. العودة لا تعني remount، ولا
تبدأ أكثر من refresh واحد لنفس generation، وتحترم dirty-state policy وserver scope.

### `FE-LC-013` — UI-state transitions

الانتقال بين loading وready وempty وerror وsaving وdirty يكون صريحًا ومتسقًا. لا
تعيد stale completion واجهة أحدث إلى loading/error، ولا يبقى failure صامتًا مع data
قديمة تبدو current.

### `FE-LC-014` — Asset bootstrap ownership

Entry أو manifest معروف يملك dependencies وترتيبها. لا يعتمد correctness عرضيًا
على اكتمال `app_include` قبل page hook. تحفظ Form/DCO asset ordering المجمدة، وتُحمّل
page/workspace feature groups دون duplicate concurrent bootstrap.

### `FE-LC-015` — Remount idempotency

إعادة mount على host نفسه إما تعيد instance الصالحة أو تتخلص من المالك السابق قبل
استبداله. لا تتضاعف state stores أو listeners أو timers أو observers أو primary
actions بعد remount/refresh/revisit.

## 5. Mutation completion contract

Leaving/deactivating a surface does not imply that a server mutation was cancelled.
Its stale UI completion must not commit to an inactive/superseded surface.
The surface reconciles from fresh server state when appropriate.

عمليًا:

- read يمكن إبطاله أو تجاهل نتيجته عند deactivation.
- mutation بدأت في الخادم قد تنجح حتى لو غادر المستخدم.
- نجاح/فشل mutation لا يرسم alert أو DOM في surface inactive أو بهوية superseded.
- لا يُعاد تنفيذ mutation تلقائيًا عند revisit.
- عند العودة، يجلب المالك fresh canonical state أو يطبق reconciliation معلنة مع
  حماية dirty state وoptimistic-concurrency tokens.

## 6. Surface-specific contracts

القواعد التالية تضيف semantics خاصة بكل family ولا تستبدل العقد المشترك.

### A — Cached Frappe Custom Page

#### `FE-LC-PAGE-001` — Wrapper identity

الـwrapper هو mount identity، ويضاف page route وactivation generation لتحديد الزيارة
الحالية. بقاء wrapper في DOM لا يعني أنه Active.

#### `FE-LC-PAGE-002` — Synchronous owned scaffold

عندما يملك التطبيق الصفحة، يجب إنشاء `frappe.ui.make_app_page` وحالة loading/error
الأولية قبل asset/API bootstrap غير المتزامن.

#### `FE-LC-PAGE-003` — Show/hide activation

أحداث `show` و`hide` أو contract مكافئ هي مالك التفعيل. `hide` ينقل الصفحة إلى
Inactive ولا ينفذ dispose أو يمحو state تلقائيًا.

#### `FE-LC-PAGE-004` — Read invalidation

deactivation يبطل page reads وdeferred render work التابعة للزيارة. كل completion
تتحقق من current request ومن Active state قبل commit البصري.

#### `FE-LC-PAGE-005` — Dirty-aware revisit

revisit ينفذ fresh refresh واحدًا عندما تسمح سياسة الصفحة. إذا كانت الصفحة dirty أو
saving، فلا يُستبدل working state بتحميل تلقائي؛ يطبق owner سياسة معلنة.

#### `FE-LC-PAGE-006` — Page remount

Controller واحد يملك wrapper. remount يتخلص من instance/lifecycle owner القديم أو
يعيد استخدام instance مثبتة؛ لا يُشترط helper بعينها إذا تحقق contract.

### B — Frappe Form / Document

#### `FE-LC-FORM-001` — Document identity

الهوية هي doctype + document name + document generation. لا يكفي الاحتفاظ بمرجع
`frm` لأن Frappe يمكن أن يعيد استخدام surface أثناء التنقل.

#### `FE-LC-FORM-002` — Same-document vs current-document

يجوز لنتيجة تخص نفس document generation أن تُخزن وفق owner policy، حتى أثناء route
transition. أما render/focus/feedback فيتطلب أن تكون الوثيقة هي الحالية.

#### `FE-LC-FORM-003` — Current render guard

كل async render يتحقق من document identity/generation ومن form الحالية. استجابة
Document A لا تستطيع تعديل DOM أو controls الخاصة بـDocument B.

#### `FE-LC-FORM-004` — Dirty document protection

لا ينفذ reload/reconcile أو تقدم `modified` token فوق local dirty document دون سياسة
صريحة. server state الأحدث يبقى قابلًا للكشف ولا يُخفى optimistic conflict.

#### `FE-LC-FORM-005` — Document-owned effects

timers وRAF وobservers وcleanups الخاصة بالوثيقة تُسجل بمفاتيح feature وتُلغى عند
تغير الهوية. الأعمال المؤجلة تتحقق من document generation قبل التنفيذ.

#### `FE-LC-FORM-006` — Existing DCO owner pattern

`AlmdinaDocumentContext` هو النمط المعتمد لهوية DCO وsame/current semantics وملكية
effects. `AlmdinaMeasurementLifecycle` و`AlmdinaWorkspaceSyncCoordinator` يبقيان
primitives متخصصة تحت هذا العقد، ولا يستبدلان lifecycle الخاصة بـFrappe Form.

### C1 — Collection Surface / List View

#### `FE-LC-LIST-001` — List execution identity

الهوية هي doctype + view/filter/order/page snapshot + generation. listview object
وحده لا يثبت أن response تخص query الحالية.

#### `FE-LC-LIST-002` — Refresh idempotency

`onload` يثبت owner، و`refresh` يعيد المزامنة دون مضاعفة buttons أو delegated events
أو observers أو timers.

#### `FE-LC-LIST-003` — Stale filter rejection

نتيجة filter/order/page generation قديمة لا تستبدل rows أو cards أو counters التابعة
لـsnapshot أحدث.

#### `FE-LC-LIST-004` — List-root ownership

DOM work وobservers تتبع list root/listview الحالية. عند استبدال root أو remount،
يُنظف owner القديم أو يعاد ربطه idempotently.

### C2 — Collection Surface / Query Report

#### `FE-LC-REPORT-001` — Frappe-owned default

التقارير declarative تعتمد lifecycle التي يملكها Frappe: filters وexecution وloading
وresult rendering. لا يحتاج التطبيق lifecycle موازية لمجرد وجود Report JS.

#### `FE-LC-REPORT-002` — No parallel lifecycle without behavior

لا تضاف custom timers/listeners/observers/request orchestration إلى report config ما
لم يوجد custom behavior حقيقي يحتاج owner معلنًا واختبارًا.

#### `FE-LC-REPORT-003` — Custom execution identity

عند إضافة custom async behavior تصبح الهوية report + immutable filter snapshot +
execution generation، وتُرفض completion التابعة لتنفيذ سابق.

### D — Stateful Special Workspace

#### `FE-LC-WORKSPACE-001` — Workspace identity

لكل فتح هوية domain/route صريحة وopen generation. في Door Drawing تتكون الهوية من
order name + piece name، ولا يكفي page wrapper وحده.

#### `FE-LC-WORKSPACE-002` — Open/suspend/destroy

`open(identity)` يبدأ generation جديدة، و`suspend()` يبطل العمل النشط وينظف موارد
الزيارة دون افتراض نهاية المالك، و`destroy()` هو الإنهاء النهائي idempotent.

#### `FE-LC-WORKSPACE-003` — Dirty history policy

history غير المحفوظة تُحفظ أو تُصان أو يُطلب تأكيد صريح قبل discard. navigation أو
suspend لا يفقدان الرسم/العمل بصمت.

#### `FE-LC-WORKSPACE-004` — Workspace resource ownership

الـworkspace owner يملك canvas وkeyboard/window events وscanner operations وfile
readers وtemporary uploads وrenderers وshell teardown.

#### `FE-LC-WORKSPACE-005` — Open-generation commit guard

load/upload/scan/save completion تتحقق من open generation والهوية وحالة suspend قبل
state أو UI commit. الملفات التي أنشأتها عملية stale تُنظف وفق سياسة آمنة.

### E — Global / Shared Runtime

#### `FE-LC-GLOBAL-001` — Singleton ownership

كل global module يملك singleton key/guard واضحًا ويثبت نفسه مرة واحدة لكل Desk
session. إعادة تقييم asset لا تضاعف runtime registrations.

#### `FE-LC-GLOBAL-002` — No permanent surface identity

global runtime لا يخزن page wrapper أو `frm` أو document identity كحقيقة دائمة.
feature state يبقى لدى owner المحلي.

#### `FE-LC-GLOBAL-003` — Resolve current surface at execution

global callbacks التي تحتاج current page/form تحلها وقت التنفيذ وتتحقق من النوع
والهوية قبل dispatch.

#### `FE-LC-GLOBAL-004` — No feature-local observer promotion

لا تُنقل feature-local observers أو timers إلى global runtime لتجاوز owner المحلي.
Shared runtime يوفر primitives فقط ولا يصبح orchestrator للميزات.

#### `FE-LC-GLOBAL-005` — Keyed replacement and idempotency

registries وglobal owners تستخدم keys مستقرة وتستبدل التسجيل المقصود بدل إضافة
نسخ متوازية. unregister/teardown يكون متاحًا عندما يحتاجه runtime أو الاختبار.

## 7. Existing primitives and owners

| Owner / primitive | الاستخدام المعتمد |
|---|---|
| `AlmdinaFrontend.rpc` | RPC envelope موحد، وليس lifecycle owner |
| `AlmdinaFrontend.requireAssets` | batched/deduplicated asset bootstrap |
| `AlmdinaFrontend.createLatestRequestGate` | latest-request-wins والإبطال |
| `AlmdinaFrontend.createLifecycleScope` | keyed events/timers/observers/cleanup |
| `AlmdinaFrontend.ensureStylesheet` | stylesheet bootstrap idempotency |
| `AlmdinaPageRevisit.bindActivationLifecycle` | primitive مناسبة لـCached Custom Pages فقط |
| `AlmdinaPageRevisit.refreshOnRevisit` | compatibility facade؛ وجودها لا يمنح certification كاملة |
| `AlmdinaDocumentContext` | DCO document identity/generation وdata/render guards وeffects |
| `AlmdinaMeasurementLifecycle` | measurement feature-key scheduling/cancellation |
| `AlmdinaWorkspaceSyncCoordinator` | ordered invalidation/refresh/reconciliation للـDCO workspaces |
| Door Drawing `open/suspend/destroy` | foundation متخصصة للـStateful Workspace |

لا يُضاف shared primitive جديد إلا عند وجود duplication مثبت في أكثر من owner وبعد
إثبات أن primitives الحالية لا تكفي. لا يوجد قرار بإنشاء lifecycle platform جديدة.

## 8. Current Lifecycle Certification Status

**Certified** تعني أن الـsurface تحقق كامل contract عائلتها بالكود، بما في ذلك
async reads وما ينطبق عليها من mutation completion وTransient Child Surface
lifecycle، وأن هذه السيناريوهات مثبتة بـruntime regression tests مناسبة، وأن
Architecture/asset contracts ذات الصلة خضراء. إثبات read/activation lifecycle فقط
لا يكفي لـFull Certification، ووجود helper أو `requestId` منفرد لا يمنح certification.

| Surface | Family | Status | الملاحظة |
|---|---|---|---|
| Factory Workforce | PAGE | Certified | read/activation، visit-generation mutation completion، transient-child ownership، revisit reconciliation، وremount مثبتة runtime |
| Factory Permissions | PAGE | Certified | read/preview/import/export guards، dirty-aware revisit، save reconciliation، confirmation ownership، وremount مثبتة runtime |
| Factory Production Settings | PAGE | Certified | read/activation، visit-generation mutation reconciliation، edit/audit child ownership، وremount مثبتة runtime |
| Shop Floor Inbox | PAGE | Certified | synchronous first-load، activation/read invalidation، visit-generation mutation reconciliation، caller-owned QuickActions children، UI-state preservation، وremount مثبتة runtime |
| Factory Master Data | PAGE | Certified | synchronous bootstrap، activation/read invalidation، dirty editor preservation، visit-generation mutation reconciliation، transient-child ownership، وremount مثبتة runtime |
| Factory Plan Archive | PAGE | Keep; lifecycle migration pending | feature نشطة لأرشفة PDF الرسمي للخطة المعتمدة؛ تبقى ضمن estate وتُعتمد لاحقًا بتغيير محدود |
| Factory Approval Queue | PAGE | Temporary migration utility | Review/Approve القديم متقاعد؛ تبقى مؤقتًا فقط لمعالجة سجلات `Pending Review` التاريخية حتى يثبت runtime/data audit عدم الحاجة إليها |
| Factory Stock Settings | PAGE | Retired / Removed | أزيل Page source بعد إثبات أنها orphaned وخارج Active Product Scope؛ بقيت endpoints التاريخية fail-closed وحقول optimizer المشتركة دون تغيير |
| Factory System Preflight | PAGE | Retirement planned; removal pending | الصفحة تستدعي endpoint تاريخية متقاعدة/fail-closed؛ لا تُصرف عليها lifecycle migration قبل أي Product Decision جديد للتشخيص |
| Factory Performance Benchmark | PAGE | Retirement planned; removal pending | الصفحة تستدعي benchmark endpoint تاريخية متقاعدة/fail-closed؛ لا تُصرف عليها lifecycle migration |
| Door Cutting Order | FORM | Specialized lifecycle exists; certification pending | Document Context وmeasurement/workspace owners موجودة؛ project-wide FORM certification لم تُغلق |
| Door Cutting Order List | LIST | Certification pending | list-specific identity/refresh contract لم تُعتمد runtime بعد |
| Current Query Reports | REPORT | Frappe-owned/declarative; custom lifecycle not currently required | التقارير الحالية filters declarative ولا تملك custom async lifecycle |
| Door Drawing | WORKSPACE | Existing lifecycle foundation; hardening/certification pending | open generation وsuspend موجودان؛ dirty/late-bootstrap hardening خارج هذه المرحلة |
| Global runtimes | GLOBAL | Audit/certification pending | singleton primitives موجودة؛ project-wide global audit خارج هذه المرحلة |

هذه القائمة status inventory وليست migration plan تلقائية. تغيير أي status إلى
Certified يحتاج PR مستقلًا يذكر contract المغلقة واختبارات الإثبات.

### 8.1 Frontend estate policy

- **Keep** يعني أن الـsurface جزء من المنتج الحالي، لذلك يمكن جدولة lifecycle certification لها عند أولوية مناسبة.
- **Temporary migration utility** ليست feature استثمارية جديدة؛ تبقى فقط لحماية بيانات/حالات تاريخية معروفة، وتُزال بعد runtime/data proof يثبت عدم وجود سجلات تحتاجها.
- **Retired / Removed** يعني أن Page source أزيلت، وأن `bench migrate` يزيل سجل Standard Page اليتيم؛ لا تُعاد إلى lifecycle inventory النشط ولا تُبنى لها replacement وهمية.
- **Retirement planned; removal pending** يعني أن الـsurface ليست مرشحًا للـlifecycle certification. الإزالة الفعلية تتم في Change مستقل بعد إثبات callers/navigation/Page-record/data migration ومتطلبات rollback، مع إبقاء أي compatibility endpoint لازمة fail-closed حتى يثبت إمكان حذفها أيضًا.
- لا تُحذف Page source أو Frappe Page record لمجرد أن الرابط غير ظاهر في Workspace؛ retirement يحتاج إثباتًا إيجابيًا مثل بقية legacy boundaries.

## 9. Enforcement model

### 9.1 ما يثبت Static بثقة

- وجود الوثيقة واكتشافها من canonical references.
- وجود shared rule IDs والعائلات والنطاقات مرة واحدة وبشكل قابل للمراجعة.
- بقاء shared foundation primitives الحالية هي primitives المعتمدة.
- Architecture boundaries وasset manifest order وpublic owner names.
- منع server endpoints من الانتشار إلى leaf renderers ضمن subsystems المهاجرة.
- منع إنشاء mega lifecycle framework كجزء من governance.

Static source markers لا تثبت async correctness ولا cleanup semantics وحدها. لا
يجوز كتابة test هشة تفرض helper بعينها على كل Page.

### 9.2 ما يحتاج Runtime Regression

- Page read لا يعمل UI commit أثناء Inactive.
- Document A response لا يرسم داخل Document B.
- same-document data commit منفصل عن current-document render.
- List filter A response لا يستبدل filter B.
- timers/RAF/observers لا يبقون بعد identity change أو dispose.
- remount لا يضاعف listeners.
- dirty state لا تُستبدل صامتًا.
- workspace `open(A) -> suspend -> open(B)` يرفض completions القديمة.
- cold bootstrap لا يعتمد على app-include timing.
- mutation completion أثناء deactivation لا يرسم UI stale وتليه reconciliation آمنة.

الاختبار يثبت semantics، لا اسم helper. Frappe v16 integration يبقى مطلوبًا عندما
تعتمد النتيجة على ترتيب hooks الحقيقي في Desk.

## 10. Review and certification protocol

عند إضافة أو تعديل Frontend surface:

1. صنفها ضمن family واحدة، وحدد transient children التابعة لها.
2. أعلن mount/activate/deactivate/dispose owners.
3. حدد identity وgeneration وcommit predicates للقراءات والـmutations.
4. حدد dirty، first-load، revisit، UI states، وasset owner.
5. أعد استخدام primitives الحالية قبل اقتراح primitive عامة.
6. أضف Static contract فقط لما يمكن إثباته نصيًا بثقة.
7. أضف runtime regression للـrace/cleanup/dirty semantics.
8. لا تغير certification table إلا مع evidence مناسب.

## 11. حدود Phase 1.1

هذه المرحلة Governance/Documentation/Architecture Contract فقط. لا تغير Runtime
behavior، ولا ترحّل Shop Floor أو Factory Master Data أو Door Drawing أو DCO أو List
أو Report أو global observers، ولا تغير CSS أو Backend أو Business Logic أو
Authorization أو Design System.
