# P0 — اختلاط بيانات الطلبات: أدلة المرحلة الأولى

**Base `Develop`:** `17e526b6648d35983967c03549e2348b05cb2839`، وقت الاستنساخ 2026-10-13.
**النطاق:** اختبارات وتشخيص فقط؛ لم يتغير كود الإنتاج أو بيانات العملاء.
**القرار:** `RUNTIME CERTIFICATION BLOCKED`. وصل CI إلى Desk على Frappe 16.17.5 / ERPNext 16.17.0 وأنشأ بيانات اختبار فعلية، لكن فتح Form A توقف في Router قبل إنشاء `cur_frm`. لذلك لم تُختبر الطباعة أو Native Save/DB، ولا يُدمج هذا الـPR الأحمر.

## Change Contract

Goal: إثبات مسارات A→B بحالات قابلة للتكرار. In scope: VM يشغّل وحدات الإنتاج الفعلية وDeferred Promises وتقرير. Out of scope: إصلاح الإنتاج، Recovery، الصلاحيات، schema، DXF. Invariants: لا تتغير مسودة تحرير الطلب نفسه ولا ترقية NEW→Saved. Expected files: tests، workflow، report/log. Permission impact: لا تغيير. Data impact: لا بيانات فعلية. Rollback: حذف الاختبار/التوثيق فقط.

## A. Root Cause Evidence

المرجع في عمود الدليل مسار نسبي إلى `almdina_erp/public/js/door_cutting_order/`. استُخدم `before_load` الفعلي من Document Context مع نفس كائن `frm` وانتقال اسم الطلب، ووحدات Workspace Store/State/Presenter الإنتاجية نفسها؛ الـAPI فقط استبدل برد حتمي.

| ID | العيب | الدليل البرمجي | إعادة الإنتاج | التأثير | الأولوية |
|---|---|---|---|---|---|
| R1 | انتقال الهوية يفرغ بعض حقول الـForm والـHTML، ولا يصفر مخزني Plan وCost أو مفاتيح التحميل | `core/door_cutting_order_document_context.js:285-344,682-699` | نعم: A جاهز → `before_load(B)` → Presenter ما زال يرى A | أساس التلوث بين الطلبات | P0 |
| R2 | `snapshot(frm)` يعيد المخزن دون مقارنة `state.identity` بهوية `frm.doc`، والمستهلكون يأخذون البيانات مباشرة | `cutting_plan/door_cutting_order_plan_workspace_state.js:208-248`; `costing/door_cutting_order_cost_workspace_state.js:291-312`; مقدمتا الـPresenter `:10-39` | نعم للاثنين | عرض A داخل B، وإتاحة خطة A | P0 |
| R3 | Promise أحادي الرحلة موجود على `frm` بلا مالك للهوية؛ تحميل B دون `force` يعيد انتظار A | `cutting_plan/door_cutting_order_plan_workspace_state.js:145-162`; `costing/door_cutting_order_cost_workspace_state.js:203-222` | نعم: عدد طلبات API يبقى 1 بدل 2 | B لا يحصل على بياناته حتى التسوية/إعادة التحميل | P0 |
| R4 | رد A المتأخر عند تغير الهوية ينفذ `store.reset(B)` حتى إذا كان B جاهزًا | `cutting_plan/door_cutting_order_plan_workspace_state.js:88-95,179-191`; `costing/door_cutting_order_cost_workspace_state.js:108-115,258-270` | نعم: B جاهز ثم A متأخر → B يصبح `idle` | يمحو الحقيقة الجديدة ويجعل العرض يتعثر | P0 |
| R5 | قبول رد API لا يقارن `payload.order_name` بالاسم المطلوب؛ `resolveLoad` يتحقق من هوية المخزن ورقم الطلب الداخلي فقط | Plan `:179-191` وCost `:258-271`، و`core/door_cutting_order_workspace_store.js:90-104` | نعم بحقن حمولة B في طلب A | ضعف دفاعي عند استجابة غير متوقعة؛ لم نثبت أن API الحقيقي يعيد الاسم الخاطئ | P0 دفاع عمقي |
| R6 | Cost Presenter ينسخ كل حقول `order` إلى `frm.doc`، ويطابق القطع باسم الصف فقط | `costing/door_cutting_order_cost_workspace_presenter_adapter.js:76-127` | نعم مع Snapshot A عند B؛ اللوح والقطعة يتغيران داخل نموذج B | خطر وصول قيم خاطئة للحفظ؛ اختبار DB مفقود | P0 |
| R7 | Plan Presenter ينسخ هندسة الخطة إلى `frm.doc.cutting_plan_json`، و`ready()`/الطباعة لا يتحققان من هوية الحمولة | `cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js:160-208,272-313`; `cutting_plan/door_cutting_order_plan_tabs_ux.js:325-343` | نعم: أمر الطباعة يتلقى خطة A والنموذج على B | خطر مستند قص ذي هندسة خاطئة | P0 |
| R8 | `before_save` يفضل قيمة `$input.val()` على `frm.doc.board_description` بلا حارس هوية | `order_entry/door_cutting_order_board_text_ux.js:6-13,39-62,114` | نعم عندما يمثل الـDOM المدخل القديم A؛ لم تثبت إعادة الاستخدام الفعلية لذلك المدخل في متصفح Frappe | قد ينتقل اللون إلى حمولة حفظ B | P0 مشروط |
| R9 | Renderer يختار خطة/DOM قبل `await` ثم يقرأ `frm.doc` الحي بعده عند بناء المستند | `cutting_plan/door_cutting_order_cutting_plan_renderer.js:1104-1143` | استنتاج من ترتيب الكود؛ الاختبار البصري المتأخر معلق | احتمال جمع هندسة A مع بيانات B حتى لو كان المصدر صحيحًا أولًا | P0 مشروط |

هذه العيوب في نسخة Base، لا تثبت بمفردها توقيت حادثة الإنتاج أو أن قاعدة بيانات عميل تضررت. R5 يتطلب رد API غير مطابق؛ الخدمتان الخلفيتان تردان `order_name` من الطلب الذي قرأته الخدمة، لذلك ليس هذا تفسيرًا مستقلًا مثبتًا للحادثة.

## B. ملكية البيانات

| البيانات | المالك الحالي | حد الهوية اللازم |
|---|---|---|
| هوية المستند ودورة NEW→Saved | Document Context + `frm.doc` | token مع generation/aliases؛ إعادة ضبط كل مستهلك متعلق بالمستند |
| حقول DCO وجدول القطع | `frm.doc` ثم Frappe Save؛ مدخلات النموذج | لا يقبل إسقاط read model عابر للطلب أو كتابة DOM قديم |
| Plan Snapshot | Plan Workspace Store والخدمة الخلفية | `state.identity`, `payload.order_name`, خطة `door_cutting_order` وإصدارها |
| Cost Snapshot | Cost Workspace Store والخدمة الخلفية | `state.identity`, `payload.order_name`, وإصدار المستند عند الحاجة |
| Preview | Plan Preview Session | هوية الطلب/الخطة وجيل الزيارة، وإبطاله عند الانتقال |
| مصدر الطباعة | Plan Presenter ثم Tabs UX ثم Renderer | لقطة ثابتة لمصدر الخطة والطلب واللوح حتى إكمال `await` |
| Recovery Draft | Local Checkpoint/Recovery | token سياق المستند و`draft_id`؛ لا يوجد في اختباراتنا دليل على أنه سبب R1–R7 |

## C. تسلسلات السباق

1. **الظهور الخاطئ:** `load(A)` → Store `ready(A)` → Frappe يعيد استخدام `frm` ويحمل B → `DocumentContext.synchronize` يمسح عناصر DOM لكنه لا يمس Store → `snapshot(B)` يعيد `ready(A)` → Cost `projectOrder/projectPieces` يكتب داخل B، أو Plan `project` يضع هندسة A ويتيح الطباعة.
2. **توقف تحميل B:** `load(A)` معلق → `before_load(B)` → `load(B)` يجد `frm[LOAD_PROMISE_KEY]` الخاص بـA → يعود به بلا GET لـB → الرد اللاحق لـA يصفر Store على هوية B.
3. **محو B الجاهز:** `load(A)` معلق → انتقال B مع `reset(B)` → `load(B)` يكتمل `ready(B)` → يكتمل A → `rejectIdentityTransition` يصفر Store إلى `idle(B)` بدل تجاهل رد A. اختبرنا هذا التسلسل رغم إضافة reset يدوية تمثل إصلاحًا محتملًا؛ يثبت أن reset وحده ليس إصلاحًا كافيًا.
4. **الطباعة عبر `await`:** يأخذ Renderer `planRoot` و`title` من حالة ما قبل الانتظار، ثم ينتظر هوية المصنع، ثم يبني HTML باستخدام `frm.doc` الحي. تحتاج هذه الحالة لاختبار DOM/نافذة طباعة للتثبت من الناتج النهائي.

## D. خطر الحفظ والطباعة

`Cost API → Cost Store → Presenter.projectOrder → frm.doc.board_description → Frappe native Save → DB`:

- الخدمة الخلفية تبني `order_name` و`order` من المستند المقروء (`services/cost_permission_service.py:299-336`). Store/Presenter لا يفحصان تطابق هذا الاسم مع B. الكتابة الفعلية في النموذج تقع عند `projectOrder`، لا عند GET.
- `projectPieces` يكتب حقول القطعة ذات الاسم المطابق داخل `frm.doc.pieces`؛ في اختبارنا استخدمنا اسم صف واحدًا في الطلبين لإثبات الحاجة إلى هوية الأب. لا نجزم بحدوث تصادم أسماء child rows الحقيقية بين طلبين؛ ينبغي التحقق في Desk.
- إذا وقع Save لاحقًا، يمكن للحمولة المعدلة أن تُرسل باسم B و`modified` الخاص بـB. `DoorCuttingOrder.validate()` يستدعي `process_order_save` (`doctype/door_cutting_order/door_cutting_order.py:52-53`)، لكن هذا لا يثبت رفض `board_description` الخاطئ القابل للتعديل. لم تُجر كتابة DB؛ الاستنتاج **خطر حفظ** وليس إثبات فساد قاعدة البيانات.
- مسار مستقل مشروط: `board_text_ux.controlValue` يأخذ قيمة Input قديم → `before_save/syncInputs` يستدعي `frm.set_value` → Save. اختبرنا الشرط المصطنع فقط؛ يلزم اختبار DOM حقيقي لثبوت بقائه بعد تنقل Frappe.
- الطباعة: `Plan Store A → Presenter.ready(B)` صحيح زورًا → `project(B)` ينسخ هندسة A → `PlanTabsUX.printActivePlan(B)` يأخذ الخطة من Store A → Renderer يستقبل `frm B, plan A`. اختبرنا بلوغ أمر الطباعة بهذه الهوية المختلطة؛ لم نختبر صفحات الطباعة النهائية أو طابعة فعلية.

## E. تصميم المرحلة الثانية المقترح

1. **حد المستند:** يطلب Document Context من Plan/Cost/Preview مالكيها إبطال الجيل السابق عند انتقال هوية حقيقي؛ يظل NEW→Saved ترقية للجيل نفسه. يمنع أي Presenter من القراءة قبل اكتمال انتقال الهوية. لا يعتمد على refresh أو مؤقت.
2. **حماية القراءة:** تجعل `snapshot(frm)`, `planForTab`, `activePlan`, `settings`, `data`, `ready`, `canPresent`, `project` تفشل مغلقة إذا اختلفت هوية Store عن `formIdentity(frm)`، وتتحقق من `payload.order_name`. يعزل Keep Paint على الهوية نفسها فقط؛ تحافظ إعادة تحميل A على الرسم ومسودة التحرير الجارية.
3. **ملكية الطلبات المعلقة:** ربط Promise بـ`identity` و`generation` و`requestId`. طلب B لا ينتظر A؛ رد A يرفض تأثيره بلا `reset(B)`؛ استجابة B المتأخرة كذلك تُرفض بعد الانتقال التالي. تتطلب سياسة recovery عند load متروك عدم إحياء طلب قديم.
4. **فصل القراءة عن الكتابة:** مراجعة إسقاط Cost وPlan إلى حقول DCO؛ حقول الطلب والقطع لا تُنسخ من read model بلا حراسة الهوية والإصدار. يُفحص أثر تغييرات أسعار Cost على Edit Session والصلاحيات الديناميكية دون توسيعها.
5. **طباعة ذرية:** أمر الطباعة يتحقق من الطلب والخطة والنسخة ثم يلتقط بيانات العرض الثابتة قبل `await` ويعيد التحقق بعده؛ لا يمزج هندسة snapshot مع `frm.doc` المتغير أو DOM لمستند آخر. الخدمة الخلفية تتحقق من ارتباط الخطة بالطلب.
6. **الأمان قبل الدمج:** تحول اختبارات RED إلى GREEN دون تغيير توقعاتها، ثم اختبارات Desk على الإصدارين المثبتين، DOM/Save/Print، صلاحيات Cost، NEW/Recovery، التحرير، تبويبات متوازية، واختبار عدم تدهور الأداء.

الملفات المتوقعة: `core/door_cutting_order_document_context.js`, `core/door_cutting_order_workspace_store.js` عند الحاجة إلى ملكية الطلب، `cutting_plan/door_cutting_order_plan_workspace_state.js`, `costing/door_cutting_order_cost_workspace_state.js`, كلا Presenter Adapter، `core/door_cutting_order_workspace_keep_paint.js`, `order_entry/door_cutting_order_board_text_ux.js`, `cutting_plan/door_cutting_order_plan_tabs_ux.js`, `cutting_plan/door_cutting_order_cutting_plan_renderer.js` والاختبارات المقابلة. لا تغيير صلاحيات أو مراحل الإنتاج أو مخطط DB متوقع.

## F. الاختبارات والبيئة

تشغيل: `node almdina_erp/tests/js/cross_order_p0_baseline.test.js` على Node 24.19.0. السجل الخام: [`cross_order_phase1_node_red.txt`](cross_order_phase1_node_red.txt). **15 حالة: 12 RED بسبب assertions الأمنية، 3 controls GREEN، صفر فشل Harness.** Workflow مستقل يستخدم Node 22 ويُتوقع فشله في Draft PR. اختبارات التحكم القديمة `document_context.test.js`, `cost_workspace_abandoned_load.test.js`, `workspace_keep_paint.test.js` نجحت على Base.

| Test ID | السيناريو | النتيجة الحالية | المطلوب | حالة التشغيل |
|---|---|---|---|---|
| 01 | A→B وSnapshot Plan/Cost | Presenter يقبل A | رفض القراءة والإسقاط | RED ×2 |
| 02 | A متأخر بعد B جاهز | B يصبح idle | بقاء B ready | RED ×2 |
| 03 | single-flight A/B | GET واحد لـA | GET مستقل لـB | RED ×2 |
| 04 | لون Cost | `frm.doc` يصبح أبيض بعد B | يبقى أسود | RED إسقاط مخصص؛ وPayload mismatch RED |
| 05 | القطع | قطعة B تأخذ مقاس A عند تطابق اسم الصف | حفظ قيمة B | RED إسقاط مخصص؛ اختبار أسماء حقيقية في Desk معلق |
| 06 | عرض Plan | `planForTab(B)` يعيد صف A؛ `project` يكتب الهندسة | null حتى B جاهز | RED إسقاط مخصص |
| 07 | أمر طباعة Plan | تمرير خطة A مع `frm B` | حجب الأمر | RED؛ HTML الفعلي بعد `await` معلق |
| 08 | A→NEW→Saved/Recovery | الترقية NEW مثبتة بالضابط | عدم كسرها؛ اختبار الاستعادة/الإلغاء | GREEN للترقية؛ Recovery/Desk معلق |
| 09 | مسودة التحرير لنفس الطلب | لا تمحى عند force load | تبقى | GREEN لخطة واحدة؛ Cost/Desk معلق |
| 10 | تبويبات واتصال بطيء | Formان منفصلان معزولان؛ نفس Form عند التنقل معيب | فصل كلي | GREEN منفصل؛ RED للسباق؛ متصفح متعدد التبويبات معلق |
| 11 | هوية payload من الخدمة | قبول حمولة B داخل Store A | رفضها | RED ×2؛ رد فعلي خاطئ من الخادم غير مثبت |
| 12 | DOM قبل الحفظ | input قديم A يكتب في doc B إذا ظل موجودًا | تجاهله | RED مشروط؛ دورة Frappe الحقيقية معلقة |

**ما يلزم لفك BLOCKED:** تشغيل اختبارات Desk/Browser على Frappe 16.17.5 وERPNext 16.17.0 ببيانات وهمية، التقاط صفحة الطباعة الناتجة بعد تغيير الطلب أثناء `await`، إثبات/نفي وصول اللون إلى حمولة Save ثم DB ضمن معاملة اختبار معزولة، وفحص مسار Recovery الحالي. لا بيانات إنتاج أو ادعاء بسبب الحادثة قبل ذلك.

## G. Phase 1B — شهادة التشغيل المعزول

**القرار المعماري:** لا يُعد VM في القسم F دليلًا على إعادة استخدام `frm` داخل Desk؛ تبقى R1–R4 وR6–R9 فرضيات تشغيلية مشروطة بنتيجة المتصفح. ينتج الاختبار الجديد طلبين مختلفين في موقع CI مؤقت بإصداري Frappe `v16.17.5` وERPNext `v16.17.0` مع تحقق SHA (`75baafaa0bde07a86bf28764383b93b5df97bc7e` و`7b494dc9e8e47d288de5427bae25ce8a52c37d96`). أسماء صفوف القطع يولدها Frappe ويتحقق fixture من اختلافها. لا يستعمل أي موقع إنتاج.

**التنفيذ:** `almdina_erp/tests/cross_order_p0_runtime_fixture.py` ينشئ A أبيض بمقاس 42×81 وكلفة 11 وB أسود بمقاس 57×93 وكلفة 19 ثم يحذف هذه السجلات في نهاية المهمة. `almdina_erp/tests/browser/test_cross_order_p0_runtime.py` يسجل أحداث `before_load/onload/refresh` ومراجع `frm` و`doc` وSnapshot وحقل الإدخال؛ يحقن Snapshot على B عبر Store/Presenter الإنتاجي ويعترض `savedocs` ثم يقرأ B من `frappe.client.get`. الحقن مضبوط ويُفصل صراحة عن التنقل الطبيعي. يمسك `window.open` قبل الطباعة ويحتفظ بـHTML النهائي بعد تأخير هوية المصنع وتنقل Desk. لا يرسل شيئًا إلى طابعة. تحتفظ مهمة CI بـ`runtime-evidence.json` و`final-print.html` ولقطة شاشة وسجلات الإعداد/المتصفح إذا وصلت إلى تلك المراحل.

**تدقيق مستقل:** فحص Python syntax و`git diff --check` ناجح؛ ضوابط Node الثلاثة السابقة ناجحة. فرق الملفات مع Base SHA يقتصر على الاختبارات، التقرير وWorkflow؛ لم يتغير كود إنتاج أو Recovery. صفوف القطع الحقيقية ذات أسماء متميزة، لذا لا يجوز نقل نتيجة اصطدام الاسم المصطنع في اختبار VM إلى حكم عن تلوث القطع الحقيقية. يحتاج اختبار Recovery الفعلي، ومسودات Plan/Cost، إلى نتائج Desk صريحة؛ مجرد ظهور API ليس إثبات restore/cancel.

**محاولتا Desk الأوليان:** نجح تثبيت الإصدارات وإنشاء الموقع والطلبين، ثم علق فتح A قبل دورة Form. السجل في Run `38425288478` حدد مهلة `cur_frm`; التشخيص المعزز في Run `38426381356` أظهر `/desk/door-cutting-order/26-00001` مع `cur_frm=null` و`Page door-cutting-order not found`، و`RangeError: Incorrect locale information provided` في `AltShortcutGroup` قبل إنشاء الصفحة. مصدر Frappe `v16.17.5` يستدعي `new Intl.Locale(navigator.language)` هناك؛ سياق Playwright الآن يحدد `en-US` ويتحقق من قابليته للتحليل قبل الملاحة. `socket.io` على `bench serve` أعاد 404 أيضًا، لكنه ليس سبب `RangeError` المثبت. لا نتيجة عن `frm` أو Save أو Print من هاتين المحاولتين.

**المحاولة الأخيرة:** Run `38427504655` ثبت نسختي `16.17.5` و`16.17.0` وأنشأ A `26-00001` أبيض وB `26-00002` أسود، وصفين مولدين باسمي `r6jr9719nq` و`r6kifgmbc7` مختلفين. زال خطأ Locale؛ بقيت استجابة `404` لـ`frappe.desk.desk_page.getpage`، وواجهة “Page door-cutting-order not found” للمسار `/desk/door-cutting-order/26-00001`، مع `cur_frm=null`. هذا **مانع Router في الموقع التجريبي قبل lifecycle**. في مصدر Frappe المثبت يبني `frappe.router.setup()` مسارات Doctype من `frappe.boot.user.can_read`، ثم يعامل slug غير المسجل كصفحة؛ نقص تسجيل مسار DCO في صلاحيات boot تفسير مرجح **لم يُقَس مباشرة**. يجب فحص `frappe.boot.user.can_read` و`frappe.router.routes['door-cutting-order']`، ثم منح مستخدم اختبار دور القراءة/القدرات اللازمة ضمن الموقع المعزول فقط. لا تُكرر محاولة بالمقدمات الحالية. `socket.io` 404 مستقل ولا يفسر سقوط Route.

| بوابة | نتيجة التشغيل | التصنيف |
|---|---|---|
| 1 — دورة Desk | أُنشئ الموقع والطلبان؛ تعذر دخول Form A بسبب `404` في Router و`cur_frm=null` قبل `before_load` | `NOT_TESTED`: إعادة استخدام `frm` ووقت hooks وSnapshot/DOM/model مجهولة |
| 2 — Native Save وDB | صفوف فعلية مختلفة الأسماء، لكن لم يفتح Form B ولم ترسل `savedocs` | `NOT_TESTED`: لا إثبات لحفظ اللون الخاطئ ولا نفيه |
| 3 — HTML النهائي | لم يصل Browser إلى زر الطباعة أو Renderer؛ لا `final-print.html` من التشغيل | `NOT_TESTED`: هوية الخطة/الإصدار والهندسة والترويسة غير معتمدة |
| 4 — Recovery وNEW/EDIT ومسودات | ستة اختبارات Node مركزة لـcheckpoint وNEW Save وprojection وEdit وPlan/Cost session نجحت على `Develop`؛ Desk restore/cancel قيد الإثبات. تشغيل Chromium للفرع `Recovery-test` في Run `38413457104` ألغي، ولا يثبت توافقًا هناك | جزئي؛ لا اعتماد تشغيلي |

### تصنيف إخفاقات CI السابقة على اختبار Desk المثبت

| المجموعة | دليل CI / مقارنة Base `17e526b` | التصنيف |
|---|---|---|
| `Cross-order P0 RED baseline` | 12 RED مقصودة، 3 controls ناجحة؛ بقيت توقعات RED دون تعديل | `Intentional RED` |
| `Frappe v16 Integration` | Run Base `38259469697` أنشأ الموقع ونفذ suite ثم أخفق في العقود الثلاثة نفسها المسجلة في Run PR `38412055297`: نص `loading/error/empty/disabled/dirty` الغائب، سجل style debt، ومواقع `ignore_permissions`. يستخدم workflow فرعي `version-16` المتحركين (في PR: Frappe `16.51.1` وERPNext `16.50.0`)، فلا يثبت الإصدارات المطلوبة ولا Browser Desk | `Baseline` |
| `Static Checks` | النص/debt الثابتان نفسيهما؛ ملفات العقد ومراجع الإنتاج لم تتغير في هذه PR | `Baseline` |
| `F6` و`F7` | `test_virtual_piece_type_change_materializes_one_row_without_rebuilding_table` يفشل في كلا المسارين؛ مصدره ومصدر الإنتاج ثابتان قياسًا بـBase | `Baseline` |
| `Security and Protected UI Regressions` | تحميل `almdina_erp/public/js/arabic_operator_ui.js` المفقود؛ خارج تغيير الاختبارات | `Baseline` |
| أي إخفاق في مهمة Desk المثبتة | يحدد بسجل تلك المهمة وحده؛ لا يخلط بإخفاقات العقود العامة | `New Regression` في أداة الإثبات حتى تشخيصه |

الأداة الجديدة لا تكفي وحدها بعد فتح Form: حقن Cost مضبوط وليس إعادة إنتاج طبيعية؛ وخطة A المستخدمة للطباعة في الأداة مصطنعة، لا استجابة GET متأخرة لخطة محفوظة. بعد إصلاح Route ينبغي أولًا قياس lifecycle ثم إضافة fixture لخطة A حقيقية وتأخير جوابها، تشغيل Print من تبويب B، وتوثيق HTML النهائي والهوية/المراجعة، ثم اختبار restore/cancel وNEW→Saved وEdit ومسودات Plan/Cost على Desk. ما لم ينفذ ذلك تبقى البوابات غير معتمدة. الفرع `Recovery-test` مرجع مستقل؛ لم يُدمج أي commit منه مع `Develop` ولم يتغير Recovery.

**Artifacts:** [المحاولة الأخيرة وسجلها](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38427504655)، [حزمة الأدلة والتشخيص](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38427504655/artifacts/11829302666)، [المحاولة ذات خطأ Locale](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38426381356)، [Base integration](https://github.com/Hasan-Alhendi/almdina-erp/actions/runs/38259469697). حزمة المحاولة الأخيرة تتضمن `runtime-evidence.json` و`last-desk.png` وسجلات bench/site/fixture/serve/browser؛ لا تتضمن HTML طباعة أو حمولة Save لأن Form لم يفتح. حُذفت سجلات A وB من موقع CI المؤقت في خطوة cleanup، وانتهى Runner.
