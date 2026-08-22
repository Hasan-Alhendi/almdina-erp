# 09 — التشغيل والإصدارات

> **Status:** Canonical release policy  
> **Audience:** DevOps, maintainers, release owners

هذه الوثيقة تصف **Contract الإصدار** ولا تحتوي Secrets أو تفاصيل خادم خاصة ببيئة واحدة.

## 1. الفروع

- `Develop`: Integration branch للتطوير المختبر.
- Feature branches: العمل الجاري وPRs.
- `main`: Release/promotion branch فقط، ولا يُعدّل لمجرد انتهاء Feature ما لم يصدر قرار Release صريح.

## 2. رحلة التغيير إلى الإنتاج

```mermaid
flowchart LR
    A[Feature branch] --> B[PR to Develop]
    B --> C[CI gates]
    C --> D[Merge to Develop]
    D --> E[Deploy test/staging target]
    E --> F[Smoke/UAT as needed]
    F --> G{Release approved?}
    G -- yes --> H[Promote/release main]
    G -- no --> I[Keep Develop as integration]
```

## 3. قبل Deployment

- حدد exact Git SHA، لا “latest” فقط.
- راجع PR/Diff.
- تحقق من CI على نفس SHA.
- اعرف هل هناك schema/patch/migration.
- خذ Backup مناسب قبل Migration عالية الأثر.
- تأكد أن rollback path معروف.

## 4. Frappe migration contract

الأوامر الدقيقة قد تختلف حسب Docker/Bench wrapper للبيئة، لكن التسلسل المنطقي:

```text
fetch/build exact app revision
install app only for new site
bench --site <site> migrate
build/refresh assets when frontend assets changed
clear/reload caches when required
restart relevant workers/services
smoke test
```

لا تنسخ أوامر `SETUP_v1.0.md` القديمة بشكل أعمى إذا تعارضت مع البيئة الحالية.

## 5. Migration rules

- Patch يجب أن يكون idempotent.
- اختبر `migrate` مرتين في CI.
- لا تعيد حساب historical approved snapshots بلا قرار migration صريح.
- إذا تغير معنى Field وليس شكله فقط، اكتب خطة data transition.
- بعد destructive migration، code rollback وحده قد لا يكفي؛ خطط للبيانات أيضًا.

## 6. Assets/UI

عند تعديل JS/CSS/workspace assets:

- تأكد أن build pipeline للبيئة أخذ commit الجديد.
- لا تشخص stale browser asset كـBusiness bug قبل فحص cache/build.
- لكن لا تستخدم cache كتبرير لبيانات DCO خاطئة بعد navigation؛ افصل asset-cache عن client state bug.

### إصدار تطبيق سكانر Windows

- ابنِ `AlmdinaScannerBridgeSetup.exe` من Workflow `Windows Scanner Bridge` على SHA المرشح نفسه.
- Artifact غير الموقّع مخصص لـUAT فقط؛ إصدار الموظفين يجب أن يمر بتوقيع Authenticode وtimestamp، ويمنع الـWorkflow نشر Release بلا توقيع.
- انشر tag بالشكل `scanner-bridge-v*` ليصبح المثبت الموقّع في رابط GitHub Release الثابت الذي تعرضه الواجهة.
- اختبر التثبيت per-user، التشغيل مع تسجيل الدخول، `/health`، WIA، الإلغاء، والإزالة على جهاز Windows فعلي.
- التطبيق لا يحتاج migration أو صلاحية مدير، ولا يجوز استبدال loopback بعنوان شبكي.

## 7. Smoke checklist

بعد deployment مهم، اختبر بحسابات غير Administrator أيضًا:

- Login/Desk/workspace.
- فتح DCO صحيح بالاسم وعدم ظهور بيانات طلب سابق.
- إنشاء/تعديل طلب حسب persona.
- Cutting Plan tab.
- Cost visibility للشخص المالي وعدم ظهورها للعامل.
- Shop Floor inbox للـassignee الصحيح.
- Start/Handoff إن كان release يمس الإنتاج.
- DXF/print إذا كانت الملفات تغيرت.
- Permission page إذا مس التغيير الصلاحيات.

## 8. Rollback

الـRollback المهني يحدد مسبقًا:

- previous known-good app SHA/image.
- DB backup point.
- هل migration backward-compatible؟
- هل ملفات/attachments تغيرت؟
- ما smoke tests بعد rollback؟

لا تعد بـRollback لحظي إذا كان migration غير قابل للعكس.

## 9. Logs وتشخيص المشاكل

عند incident اجمع:

- exact SHA/image.
- user/persona.
- DCO/stage identifiers.
- request/endpoint إن أمكن.
- browser/server error.
- whether refresh changes result.
- relevant worker/web logs.

تجنب تعديل عدة طبقات “للتجربة” قبل تحديد أول boundary يظهر فيها السلوك الخاطئ.

## 10. أسرار وإعدادات بيئية

- لا تضع passwords/tokens في repository docs.
- Server-specific paths/scripts يمكن توثيقها في Runbook خاص بالبيئة إذا لزم، لكن لا تجعل Architecture المرجعية تعتمد على اسم خادم واحد.
- Secrets تبقى في environment/secret management المعتمد.

## 11. Release note المطلوبة

لكل Release اذكر:

- from SHA -> to SHA.
- migrations/patches.
- user-visible changes.
- permission/security changes.
- known risks.
- CI/UAT evidence.
- rollback target.
