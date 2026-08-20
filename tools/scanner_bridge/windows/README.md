# Almdina Scanner Bridge — Windows WIA

هذا البرنامج المحلي يسمح لواجهة **رسم الدرفة الخاصة** بسحب صورة مباشرة من Scanner موصول بجهاز Windows.

## الفكرة

المتصفح لا يتعامل مع WIA مباشرة. لذلك يعمل Bridge صغير على جهاز مدخل البيانات فقط:

```text
Almadina ERP (Browser)
        ↓
http://127.0.0.1:17654
        ↓
Almadina Scanner Bridge
        ↓
Windows WIA
        ↓
Scanner
```

بعد المسح لا تُحفظ الصورة مباشرة. تعود إلى الموقع ثم تمر عبر **نفس شاشة الاقتصاص** المستخدمة عند رفع صورة من الجهاز، وبعد الاعتماد يحفظ الموقع الناتج كـ Private File.

## المتطلبات

- Windows 10 أو Windows 11.
- Windows PowerShell 5.1.
- Scanner مثبّت بتعريف يدعم **WIA**.
- خدمة **Windows Image Acquisition (WIA)** تعمل.
- المستخدم يدخل إلى نطاق Almadina المسموح في `config.json`.

> إذا كان جهاز Scanner لا يظهر عبر WIA وكان TWAIN-only فلن يعمل هذا Provider. عندها نضيف TWAIN Provider خلف نفس واجهة Scanner من دون تغيير Workspace.

## التثبيت

1. انسخ مجلد `tools/scanner_bridge/windows` إلى جهاز الموظف.
2. اضغط بزر الماوس الأيمن على PowerShell واختر **Run as administrator**.
3. انتقل إلى المجلد ثم شغّل:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

المثبت يقوم بـ:

- نسخ Bridge إلى `%LOCALAPPDATA%\AlmdinaScannerBridge`.
- إنشاء `config.json` من القالب إذا لم يكن موجودًا.
- حجز `http://127.0.0.1:17654/` للمستخدم الحالي فقط.
- إضافة تشغيل تلقائي عند تسجيل الدخول إلى Windows.
- تشغيل Bridge فورًا.
- تنفيذ Health Check وإظهار عدد أجهزة WIA التي يراها Windows.

## الإعدادات

الملف:

```text
%LOCALAPPDATA%\AlmdinaScannerBridge\config.json
```

مثال:

```json
{
  "port": 17654,
  "maxScanBytes": 16777216,
  "allowedOrigins": [
    "https://almadina-2.horizontechco.com"
  ]
}
```

لا تستخدم `*` في `allowedOrigins`. يجب إدخال الـOrigin كاملًا وبشكل صريح.

## الاختبار اليدوي

من PowerShell على الجهاز نفسه:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:17654/health" `
  -Headers @{ "X-Almdina-Scanner-Bridge" = "1" }
```

النتيجة الصحيحة تكون مثل:

```text
ok           : True
provider     : wia
device_count : 1
ready        : True
```

## الاستخدام من Almadina ERP

1. افتح الدرفة الخاصة.
2. اضغط **الصورة المرجعية**.
3. يجب أن ترى حالة السكانر في أسفل النافذة.
4. اضغط **سحب من السكانر**.
5. ستظهر نافذة Windows/WIA الأصلية لاختيار الجهاز وإعدادات المسح.
6. بعد انتهاء المسح تظهر شاشة الاقتصاص داخل الموقع.
7. قص الجزء المطلوب ثم اضغط **اعتماد الصورة**.

قد يطلب المتصفح في بعض الإصدارات إذنًا للوصول إلى جهاز/شبكة محلية. اسمح بالوصول للموقع الموثوق فقط.

## الأمان

- Bridge يستمع على `127.0.0.1` فقط، وليس على LAN.
- الطلبات القادمة من المتصفح تُقبل فقط من Origins الموجودة في `config.json`.
- لا توجد صلاحية عامة `*`.
- يلزم Header مخصص لكل طلب فعلي.
- حجم Request JSON محدود.
- حجم صورة Scanner محدود قبل إرسال Base64 إلى المتصفح.
- الناتج لا يذهب إلى DXF أو Cutting Plan؛ هو صورة مرجعية فقط.

## مشاكل شائعة

### البرنامج يعمل لكن `device_count = 0`

- تأكد أن Scanner يظهر في Windows.
- ثبّت تعريف الشركة المصنعة الكامل، وليس تعريف طباعة فقط.
- افتح `services.msc` وتأكد أن **Windows Image Acquisition (WIA)** تعمل.

### الموقع يقول إن Bridge غير متصل

- تحقق أن Bridge يعمل عبر Health Check أعلاه.
- تحقق أن `allowedOrigins` يحتوي بالضبط على نطاق الموقع.
- أغلق المتصفح وافتحه مجددًا إذا تغيرت صلاحية Local Network.

### Origin is not allowed

عدّل `config.json` وأضف الـOrigin الصحيح، ثم أعد تشغيل Bridge.

### الصورة كبيرة جدًا

اختر DPI أقل أو مساحة مسح أصغر. 300 DPI مناسب عادةً لورقة رسم الدرفة.

## الحذف

شغّل PowerShell كمسؤول ثم:

```powershell
.\uninstall.ps1
```

سيتم إيقاف Bridge وحذف Startup Shortcut وURL reservation والملفات المثبتة.
