# Stage 15 — Architecture Freeze & Documentation

> **Status:** Canonical Architecture Freeze  
> **Freeze date:** 2026-08-16  
> **Runtime baseline:** `75dba93dd7dd9b21b4aeb4e32113c7e7061e748e`  
> **Active scope:** `docs/PRODUCT_SCOPE_v1.1.md`

## 1. ماذا يعني Freeze؟

لا يعني أن المشروع انتهى أو أن الكود ممنوع تغييره. يعني أن **الحدود الأساسية التي نتوقع أن تبقى مستقرة أصبحت مكتوبة ومحمية باختبارات**، وبالتالي لا يعاد Refactor المشروع كاملًا مع كل Feature جديدة.

بعد Stage 15، المسار الافتراضي هو **Targeted Feature Development**.

## 2. ما الذي سبق الـFreeze؟

- **Stage 11:** إغلاق/عزل Backend legacy مع إبقاء compatibility boundaries المقصودة.
- **Stage 12:** Permissions & Authorization hardening، financial isolation، endpoint contracts، IDOR/native surfaces/escalation/production-DXF security.
- **Stage 13:** Quality gates وClean Architecture enforcement.
- **Stage 14:** Full connected E2E regression لرحلة المصنع على personas متعددة + Frappe v16 integration.
- **Stage 15:** توثيق المرجع وتجميد القرارات الأساسية.

## 3. القرارات المجمدة

### A. Product Scope

Inventory/Warehouse/Reservation/Consumption/Stock Entry/Board Remnant behavior ليس جزءًا من Active Scope v1.1. إعادة إدخاله تحتاج Product Scope decision، لا Feature جانبية.

### B. Clean Architecture direction

- Domain Framework-free.
- Application Framework-free ولا يعتمد على adapters.
- Infrastructure يملك Frappe/persistence adapters.
- Services/UI حدود خارجية ولا تكرر Business rules.

### C. Authorization model

Business authority = Capabilities، وليس fixed business role names. Context يمكن أن يضيف document/lifecycle/stage/assignment restrictions. `Administrator` استثناء superuser صريح؛ `System Manager` ليس Factory superuser تلقائيًا.

### D. Financial isolation

`VIEW_COSTS`/financial capabilities تبقى منفصلة عن order/production access. Operational snapshots لا تصبح قناة بديلة للتكلفة.

### E. Endpoint contract

كل whitelisted endpoint مصنف Capability/Delegate/Fail-Closed/Self-Context، وأي endpoint جديد يجب إدخاله في العقد واختباره.

### F. Document scope / IDOR

معرفة identifier لا تمنح وصولًا. DCO, Stage, Plan, Replacement, File يجب أن تخضع لعلاقة/Scope صحيحة.

### G. Production model

Production Routing قابل للضبط. Stage تحمل operational role، وinstance تحمل assignee. العامل ينفذ current assigned stage وفق capability. لا hard-code sequence في UI/service.

### H. Review/Approve legacy

Review/Approve القديم ليس شرطًا mandatory للإرسال للإنتاج في baseline الحالي. لا يعاد فرضه دون Product Decision. Plan approval داخل planning stage عقد مستقل ومهم.

### I. Compatibility boundaries

Legacy facades/tombstones لا تتوسع إلى مسارات Business Logic جديدة.

### J. Quality gates

Architecture/Security/E2E/Frappe integration tests ليست optional convenience؛ هي جزء من Definition of Done للتغييرات ذات الصلة.

## 4. ما التغييرات التي لا تحتاج ADR؟

- Feature جديدة داخل scope تستخدم الحدود الحالية.
- Bug fix محدد.
- UI/UX improvement لا يغير business/security contract.
- Local refactor داخل layer واحدة مع tests.
- Performance optimization لا يغير semantics.
- Documentation/testing improvements.

## 5. ما التغييرات التي تحتاج ADR وموافقة صريحة؟

- جعل Domain/Application يعتمد على Frappe.
- استبدال capability model بـfixed roles أو permission model جديد.
- إعادة تصميم lifecycle الإجباري للطلبات.
- تغيير Production Routing إلى sequence hard-coded.
- دمج financial/internal data داخل operational payloads.
- تغيير semantics للApproved snapshots/history.
- إعادة المخزون/المستودعات/البقايا إلى Active Scope.
- إزالة compatibility boundary قبل إثبات عدم وجود callers/data تحتاجها.
- Broad rewrite لوحدة كبيرة دون Targeted migration plan.

## 6. ADR template

```markdown
# ADR-XXX — العنوان

Status: Proposed / Accepted / Rejected / Superseded
Date:
Owner:

## Context
لماذا لا تكفي الحدود الحالية؟

## Decision
ما القرار الجديد بالضبط؟

## Invariants preserved
ما الذي لن يتغير؟

## Alternatives considered
ما البدائل ولماذا لم تعتمد؟

## Security/data implications
Capabilities, IDOR, financial fields, migrations.

## Migration plan
كيف تنتقل البيانات/callers؟

## Test plan
ما البوابات المطلوبة؟

## Rollback
كيف نتراجع؟

## Documentation updates
ما الملفات التي تصبح obsolete أو تحتاج تحديثًا؟
```

## 7. Documentation governance

يجب تحديث Canonical docs عند تغيير واحد من التالي:

- Active scope.
- architecture boundary.
- capability catalog أو معنى capability.
- mandatory workflow transition.
- production route semantics.
- financial visibility contract.
- primary UI entry point.
- schema/snapshot contract له أثر على integrators/operators.
- release/deployment requirements.

لا تحتاج docs تحديثًا لكل rename داخلي لا يغير فهم القارئ.

## 8. Baseline rule

`75dba93...` هو **Runtime architecture baseline** الذي اجتاز Stage 14 قبل Stage 15. Commit Stage 15 نفسه يضيف Documentation/CI contract فقط ما لم يذكر PR خلاف ذلك.

إذا تغيّر Runtime أثناء Stage 15، يجب تحديث baseline وإعادة التحقق قبل إعلان Freeze مكتمل.