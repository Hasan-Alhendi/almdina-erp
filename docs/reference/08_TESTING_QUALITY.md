# 08 — الاختبارات وبوابات الجودة

> **Status:** Canonical QA policy  
> **Audience:** Developers, QA, release owners

## 1. لماذا لدينا أكثر من Workflow؟

لأن نجاح Unit Test واحد لا يثبت أن Frappe install أو الصلاحيات أو الرسم أو migrations سليمة. البوابات مقسمة حسب نوع الخطر.

## 2. GitHub Actions الأساسية

| Workflow | ماذا يحمي |
|---|---|
| `Static Checks` | syntax، contracts واسعة، JS/UI/optimizer ودورات regression كثيرة |
| `Security and Protected UI Regressions` | security/UI boundaries الحساسة |
| `Endpoint Authorization Contracts` | كل whitelisted endpoint مصنف وله owner للعقد الأمني |
| `Stage 12 Security Gate` | financial isolation، IDOR، Frappe surfaces، escalation، production/DXF auth |
| `Stage 13 Quality Gates` | Clean Architecture boundaries وعدم عودة fixed role gates |
| `Stage 14 End-to-End Regression` | رحلة factory متصلة عبر personas والحالات |
| `Frappe v16 Integration` | Bench حقيقي، install، migrate مرتين، schema، كامل اختبارات التطبيق |
| `Special Shape Documentation Checks` | عقد التوثيق والصورة والأشكال والقلم الذكي عند تغيير المحرر |
| `Stage 15 Documentation Freeze` | وجود المرجع وربطه بالـArchitecture Freeze |

وجود Workflow file لا يساوي نجاحه؛ الحكم هو نتيجة run على SHA المرشح للدمج.

## 3. Test pyramid في هذا المشروع

### Domain unit tests

الأسرع والأوضح لقواعد geometry/cost/lifecycle/authorization decisions.

### Application contract tests

تختبر commands/use cases باستخدام repositories/adapters وهمية stateful دون Frappe.

### Static architecture/security tests

تفحص AST/imports/contracts حتى تمنع نمطًا سيئًا قبل أن يصبح Bug runtime.

### UI/JavaScript simulations/contracts

تحمي keyboard behavior، button visibility، stale navigation، drawing interactions وغيرها.

### Frappe integration

يثبت أن كل ذلك يركب فعليًا على v16 ولا يكسر install/migrate/schema/hooks.

### Manual UAT

يبقى ضروريًا للأشياء التي تعتمد على جهاز/متصفح/طابعة/CNC وتجربة بشرية.

## 4. ماذا أشغّل حسب التغيير؟

| التغيير | الحد الأدنى قبل PR | بوابات إضافية مهمة |
|---|---|---|
| Domain formula/geometry | unit + related regression | Static + Frappe |
| Permission/endpoint | security tests + endpoint contract | Stage12 + Security/UI + Frappe |
| Production workflow | shop-floor commands/queries + E2E | Stage14 + Stage13 + Frappe |
| Drawing/DXF | geometry/import/export + drawing auth | Door Drawing + Security/UI + Frappe |
| DocType/schema | relevant tests | Frappe install + migrate twice إلزامي |
| UI only | JS/UX contracts | Static/Security UI حسب السطح |
| Documentation contract | Stage15 docs test | Static/Stage13 لتجنب وصف Architecture مكسورة |

## 5. لا تضعف Test

عند فشل Test بعد تعديل:

1. افهم أي Contract يحمي.
2. تحقق هل المتطلب الجديد يغيّر Contract عمدًا أم أن الكود كسره.
3. إذا Contract ما زال صحيحًا: أصلح الكود.
4. إذا Product Decision غيّر Contract: عدّل code + tests + canonical docs معًا واذكر القرار.

ممنوع `continue-on-error`, `|| true`, broad mocking أو حذف assertion فقط للحصول على Green CI.

## 6. Frappe Integration contract

البوابة الحقيقية يجب أن تثبت على الأقل:

- Frappe v16 toolchain.
- ERPNext v16 + app source.
- إنشاء site.
- install ERPNext + Almdina ERP.
- `migrate` مرتين لإثبات idempotency.
- installed apps/schema.
- كامل اختبارات Almdina المطلوبة.

Stage 14 baseline اجتاز هذه السلسلة قبل Stage 15.

## 7. Security regression personas

عند تغيير authorization فكر في Personas مستقلة:

- Order Entry.
- Drawing worker.
- CNC/production worker.
- Edge/Sanding worker.
- Production supervisor.
- Financial.
- Permission admin.
- Plain System Manager.
- Administrator.

لا تختبر Administrator فقط؛ كثير من bugs الأمنية لا تظهر معه.

## 8. أهم invariant أمني في الاختبارات

Persona لا يملك `VIEW_COSTS` يجب ألا يحصل على Internal factory cost عبر:

- Form fields.
- API JSON.
- Cutting/approved snapshot.
- Report.
- Print.
- Child row.
- File/export side channel.

## 9. Evidence في التقرير النهائي

لا تقل “تم الاختبار” بشكل عام. اذكر:

- اسم test/workflow.
- SHA الذي اختُبر.
- success/failure.
- ما لم يمكن اختباره آليًا.

## 10. Manual UAT بعد تغييرات عالية الأثر

يفضل اختبار فعلي عند المساس بـ:

- Print layout عربي/RTL.
- DXF مع البرامج/الماكينة الفعلية.
- Tablet/pen/drawing interactions.
- mobile shop floor.
- backups/restore.
- production deployment smoke paths.
