# Almdina Scanner Bridge — Windows

هذه الأداة الصغيرة تربط صفحة رسم الدرفة في المتصفح بالـScanner المتصل بجهاز Windows عبر **WIA**.

## لماذا توجد أداة محلية؟

المتصفح لا يملك وصولًا عامًا وآمنًا إلى TWAIN/WIA. لذلك تعمل الصفحة مع خدمة محلية محدودة جدًا:

- تستمع على `127.0.0.1` فقط، وليست متاحة لأجهزة الشبكة.
- المنفذ الافتراضي `17654`.
- تقبل الطلبات فقط من Origins الموجودة في `config.json`.
- تستخدم نافذة WIA الأصلية في Windows لاختيار جهاز الـScanner وتنفيذ المسح.
- لا تحفظ الصورة محليًا بعد انتهاء الطلب؛ الملف المؤقت يُحذف بعد تحويله إلى JPEG.
- الصورة تنتقل إلى صفحة Almdina ثم يختار المستخدم منطقة القص، وبعد التأكيد تُحفظ في Frappe كـ **Private File**.

## التثبيت

1. انسخ مجلد `tools/scanner_bridge/windows` إلى جهاز الموظف الموصول بالـScanner.
2. افتح PowerShell بواسطة **Run as administrator**.
3. نفّذ:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

4. يجب أن تظهر رسالة نجاح وفحص `health`.
5. افتح موقع Almdina وسجل الدخول ثم افتح رسمة درفة خاصة واضغط **سحب من Scanner**.
6. ستظهر نافذة Windows/WIA لاختيار الـScanner وتنفيذ المسح.
7. بعد المسح تظهر مباشرة واجهة **Crop** داخل الموقع.

بعد التثبيت يضاف اختصار إلى Startup ويبدأ Bridge تلقائيًا عند دخول المستخدم إلى Windows.

## الإعداد

أول تثبيت ينسخ `config.example.json` إلى:

```text
%LOCALAPPDATA%\AlmdinaScannerBridge\config.json
```

الافتراضي:

```json
{
  "port": 17654,
  "allowedOrigins": [
    "https://almadina-2.horizontechco.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
  ]
}
```

إذا تغير نطاق الموقع، أضفه إلى `allowedOrigins` ثم أعد تشغيل Bridge.

## فحص التشغيل

من PowerShell:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:17654/health" `
  -Headers @{ "X-Almdina-Scanner-Bridge" = "1" }
```

النتيجة المتوقعة تحتوي:

```json
{"ok":true,"provider":"wia"}
```

## الإزالة

شغّل PowerShell كمسؤول ثم:

```powershell
.\uninstall.ps1
```

## ملاحظات توافق

- المسار الحالي يستهدف أجهزة **Windows التي تظهر في WIA**.
- إذا كان Scanner معيّن يعمل بتعريف TWAIN فقط ولا يظهر في WIA، نضيف Provider جديدًا للـBridge بدل وضع كود TWAIN داخل واجهة الرسم.
- هذا يحافظ على فصل `Scanner Provider` عن الـWorkspace والـDrawing V4، بحيث تبقى الواجهة نفسها مهما تغير نوع الجهاز.
