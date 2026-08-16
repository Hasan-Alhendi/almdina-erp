# Almdina ERP — المرجع الرسمي الحالي

> **Status:** Canonical Reference  
> **Audience:** الإدارة، التشغيل، التطوير، QA، DevOps، Coding AI  
> **Verified against runtime baseline:** `75dba93dd7dd9b21b4aeb4e32113c7e7061e748e`  
> **Framework:** Frappe / ERPNext `>=16,<17`  
> **Active scope:** `docs/PRODUCT_SCOPE_v1.1.md`

## لماذا يوجد هذا المرجع؟

الهدف أن يستطيع شخص جديد فهم المشروع دون الاعتماد على ذاكرة مطور أو محادثة سابقة، وأن يجد المطور/AI قواعد واضحة تمنعه من إصلاح شيء وكسر شيء آخر.

هذا المرجع يجيب عن سبعة أسئلة:

1. ما الذي يفعله النظام وما الذي لا يفعله؟
2. كيف تنتقل البيانات والطلبات بين المراحل؟
3. كيف ينفذ الموظف المهام اليومية الصحيحة؟
4. أين يجب أن يعيش كل نوع من المنطق في الكود؟
5. من يملك صلاحية ماذا، ولماذا؟
6. ما الاختبارات التي تحمي كل Contract؟
7. كيف نشخّص ونضيف Feature بدون تدمير سلوك غير مرتبط؟

## طريق القراءة حسب دورك

| أنت | اقرأ أولًا | ثم |
|---|---|---|
| صاحب المنتج/الإدارة | [01 — نظرة عامة](01_SYSTEM_OVERVIEW.md) | [03 — Workflow](03_WORKFLOWS.md) |
| موظف جديد/مدخل بيانات | [11 — المهام اليومية](11_COMMON_TASKS.md) | [03 — Workflow](03_WORKFLOWS.md) |
| عامل رسم/CNC | [05 — Cutting/Drawing/DXF](05_CUTTING_DRAWING_DXF.md) | [11 — المهام اليومية](11_COMMON_TASKS.md) |
| مشرف إنتاج | [11 — المهام اليومية](11_COMMON_TASKS.md) | [03 — Workflow](03_WORKFLOWS.md) |
| مسؤول صلاحيات | [04 — Security/Permissions](04_SECURITY_PERMISSIONS.md) | [11 — المهام اليومية](11_COMMON_TASKS.md) |
| Support | [12 — Troubleshooting](12_TROUBLESHOOTING.md) | [06 — UI/Data Map](06_DATA_UI_MAP.md) |
| Developer | [02 — Architecture](02_ARCHITECTURE.md) | [07 — Change Rules](07_CHANGE_RULES.md) + [13 — Frontend Architecture](13_FRONTEND_ARCHITECTURE.md) عند تعديل الواجهة |
| Coding AI | `AGENTS.md` | [02](02_ARCHITECTURE.md) + [07](07_CHANGE_RULES.md) + [13](13_FRONTEND_ARCHITECTURE.md) لأي Frontend change |
| QA | [08 — Testing/Quality](08_TESTING_QUALITY.md) | [03](03_WORKFLOWS.md) + [04](04_SECURITY_PERMISSIONS.md) |
| DevOps | [09 — Operations/Release](09_OPERATIONS_RELEASE.md) | [08 — Quality Gates](08_TESTING_QUALITY.md) |

## فهرس المرجع

- [01 — System Overview](01_SYSTEM_OVERVIEW.md)
- [02 — Architecture](02_ARCHITECTURE.md)
- [03 — Order & Production Workflows](03_WORKFLOWS.md)
- [04 — Security & Permissions](04_SECURITY_PERMISSIONS.md)
- [05 — Cutting, Drawing & DXF](05_CUTTING_DRAWING_DXF.md)
- [06 — Data Model & UI Map](06_DATA_UI_MAP.md)
- [07 — Development & Change Rules](07_CHANGE_RULES.md)
- [08 — Testing & Quality Gates](08_TESTING_QUALITY.md)
- [09 — Operations & Releases](09_OPERATIONS_RELEASE.md)
- [10 — Glossary](10_GLOSSARY.md)
- [11 — Common Tasks / دليل المهام اليومية](11_COMMON_TASKS.md)
- [12 — Troubleshooting / التشخيص](12_TROUBLESHOOTING.md)
- [13 — Frontend Architecture](13_FRONTEND_ARCHITECTURE.md)
- [Architecture Freeze](ARCHITECTURE_FREEZE.md)

## قاعدة “مصدر الحقيقة”

- **Scope** يجيب: هل هذه الميزة جزء من المنتج؟
- **Domain/Application code + tests** يجيب: ما السلوك الفعلي المحمي حاليًا؟
- **Canonical Reference** يشرح ويجمع العقود الحالية بطريقة مفهومة.
- **Frappe metadata/DocTypes** يحدد التخزين والواجهات، لكنه لا يجب أن يصبح مصدر Business Rules مستقلًا.
- **Historical docs/code** للتوافق والتدقيق فقط.

إذا تعارض المرجع مع الكود/الاختبارات الحالية، لا تغيّر الكود مباشرة لمطابقة النص ولا تعدّل النص لإخفاء المشكلة. افتح discrepancy وحدد هل الخطأ في Code أم Documentation أم Product Decision.

## قاعدة ما بعد Stage 15

Architecture Freeze لا تعني توقف التطوير. تعني أن **الحدود أصبحت معلنة ومختبرة**. بعد هذه المرحلة:

- Feature/Fix محدود: مسموح ومطلوب.
- Refactor محلي لإزالة duplication داخل نفس boundary: مسموح مع tests.
- Broad Refactor يغير الطبقات أو authorization model أو lifecycle model: يحتاج ADR وموافقة صريحة.

راجع [Architecture Freeze](ARCHITECTURE_FREEZE.md).