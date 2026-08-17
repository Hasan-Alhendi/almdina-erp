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

4. يقوم الـInstaller بتشغيل Bridge وفحص WIA مباشرة.
5. إذا كان Windows يرى Scanner عبر WIA سيظهر عدد الأجهزة التي تم العثور عليها.
6. افتح موقع Almdina وسجل الدخول ثم افتح رسمة درفة خاصة واضغط **سحب من Scanner**.
7. ستظهر نافذة Windows/WIA لاختيار الـScanner وتنفيذ المسح.
8. بعد المسح تظهر مباشرة واجهة **Crop** داخل الموقع.

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

يفضل إبقاء المنفذ `17654`. إذا تم تغييره، فيجب أن يستخدم Frontend نفس العنوان عبر `window.ALMDINA_SCANNER_BRIDGE_URL`؛ لذلك لا تغيّر المنفذ في أجهزة الإنتاج إلا إذا كان هناك سبب واضح.

## فحص التشغيل

من PowerShell:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:17654/health" `
  -Headers @{ "X-Almdina-Scanner-Bridge" = "1" }
```

مثال عندما يكون Scanner جاهزًا:

```json
{
  "ok": true,
  "version": "1.1.0",
  "provider": "wia",
  "device_count": 1,
  "ready": true
}
```

المعاني:

- `ok=true`: برنامج Almdina Scanner Bridge نفسه يعمل.
- `device_count`: عدد أجهزة Scanner التي يراها Windows عبر WIA.
- `ready=true`: يوجد Scanner واحد على الأقل ويمكن بدء المسح.

## تشخيص المشاكل

### 1. الموقع يقول إن Scanner Bridge غير متصل

تحقق من أن البرنامج يعمل:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:17654/health" `
  -Headers @{ "X-Almdina-Scanner-Bridge" = "1" }
```

إذا فشل الاتصال، أعد تشغيل Windows أو شغّل الملف المثبت يدويًا من:

```text
%LOCALAPPDATA%\AlmdinaScannerBridge\AlmdinaScannerBridge.ps1
```

### 2. Bridge يعمل لكن `device_count = 0`

هذا يعني أن المشكلة ليست في الموقع ولا في Almdina Scanner Bridge؛ Windows نفسه لا يرى Scanner عبر WIA.

- تأكد أن الـScanner موصول ويعمل.
- ثبّت تعريف الشركة المصنعة الكامل، وليس تعريف الطباعة فقط.
- تأكد أن الجهاز يظهر في Windows ويمكن المسح منه.
- افتح Services وتأكد أن **Windows Image Acquisition (WIA)** تعمل.
- بعد تثبيت التعريف أعد تشغيل Bridge أو Windows.

### 3. الجهاز يعمل ببرنامج الشركة لكنه لا يظهر في WIA

قد يكون التعريف **TWAIN-only**. لا نضع كود TWAIN داخل صفحة الرسم؛ نضيف Provider جديدًا خلف نفس `Scanner Provider` abstraction، وتبقى واجهة Almdina كما هي.

### 4. الموقع مرفوض رغم أن Bridge يعمل

راجع `allowedOrigins` داخل:

```text
%LOCALAPPDATA%\AlmdinaScannerBridge\config.json
```

ويجب أن يحتوي نطاق Almdina المستخدم فعليًا. بعد التعديل أعد تشغيل Bridge.

## الإزالة

شغّل PowerShell كمسؤول ثم:

```powershell
.\uninstall.ps1
```

يقرأ Uninstaller المنفذ الحالي من `config.json` قبل حذف الملفات، ثم يزيل URL reservation الصحيح.

## ملاحظات توافق

- المسار الحالي يستهدف أجهزة **Windows التي تظهر في WIA**.
- إذا كان Scanner معيّن يعمل بتعريف TWAIN فقط ولا يظهر في WIA، نضيف Provider جديدًا للـBridge بدل وضع كود TWAIN داخل واجهة الرسم.
- هذا يحافظ على فصل `Scanner Provider` عن الـWorkspace والـDrawing V4، بحيث تبقى الواجهة نفسها مهما تغير نوع الجهاز.
