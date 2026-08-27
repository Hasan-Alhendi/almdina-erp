# Almdina Scanner Bridge

تطبيق Windows صغير يربط محرر الدرفة الخاصة بسكانر WIA. يُثبَّت مرة واحدة، ويعمل في شريط النظام تلقائيًا عند تسجيل دخول الموظف؛ لا يحتاج الموظف إلى PowerShell أو صلاحيات مدير أو إبقاء نافذة مفتوحة.

## تثبيت الموظف

1. نزّل `AlmdinaScannerBridgeSetup.exe` من رابط **تنزيل برنامج السكانر** الظاهر في واجهة الدرفة الخاصة، أو استلمه من مسؤول النظام.
2. افتح الملف؛ يكتمل التثبيت تلقائيًا للمستخدم الحالي.
3. تظهر أيقونة البرنامج في شريط Windows ويصبح زر **مسح بالسكانر** جاهزًا.

يعمل التطبيق تلقائيًا مع تسجيل الدخول. يمكن فتح قائمته من أيقونة شريط النظام لاختبار السكانر، فتح نظام المدينة، تعطيل التشغيل التلقائي، أو الخروج مؤقتًا. الإزالة تتم من **Installed apps** في Windows أو اختصار الإزالة في قائمة ابدأ.

للنشر المركزي يمكن لمسؤول الأجهزة تشغيل المثبت بصمت:

```text
AlmdinaScannerBridgeSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

التثبيت لكل مستخدم داخل `%LOCALAPPDATA%` ولا يطلب elevation. التطبيق self-contained ويدعم Windows 10/11 x64، ولا يحتاج تثبيت .NET منفصلًا.

## لماذا يعمل كتطبيق شريط نظام؟

صفحة المتصفح لا تستطيع استدعاء WIA مباشرة. كما أن Windows Service لا يملك جلسة تفاعلية مناسبة لعرض نافذة اختيار الجهاز للموظف. لذلك يعمل الجسر داخل جلسة الموظف ويبدأ معها، لكنه لا يعرض نافذة أوامر.

## العقد الأمني

- يستمع عبر `TcpListener` على `127.0.0.1:17831` فقط؛ لا يستخدم HTTP.sys ولا يحتاج `netsh` أو URL ACL.
- يسمح فقط بالـOrigins الإنتاجية المحددة: `https://almadina-2.horizontechco.com` و`https://almadina-b2.horizontechco.com` و`https://almadina.horizontechco.com`.
- يتطلب Origin مسموحًا لـ`POST /scan`، ويعيد رؤوس CORS وPrivate Network Access اللازمة.
- لا يملك بيانات دخول Frappe ولا يحفظ صورًا دائمة ولا يكتب JSON.
- الصورة المؤقتة تُحذف فور قراءتها. يحوّل الجسر ناتج WIA الفعلي (BMP/TIFF/PNG/JPEG) إلى JPEG حقيقي ويضغطه تكيفيًا ضمن حد الرفع، ثم ترفعه واجهة ERP عبر خدمة `private File` المقيدة بالطلب والدرفة.
- الحد الأقصى للصورة 8 MB، والاستجابة المقبولة JPEG فقط.

## نقاط الاتصال

- `GET /health` — فحص الجاهزية والإصدار، ويمكن فتحه محليًا للتشخيص.
- `POST /scan` — يفتح واجهة WIA القياسية ويعيد JPEG واحدًا. الإلغاء يعيد HTTP 204.
- `OPTIONS` — preflight مقيد بالـOrigin.

## البناء والاختبار

الكود مقسم إلى Core مستقل عن Windows، وتطبيق WinForms للبنية الخارجية:

```text
src/Almdina.ScannerBridge.Core     origin policy + request dispatcher + scanner port
src/Almdina.ScannerBridge          tray UI + loopback TCP adapter + WIA adapter + JPEG normalization
tests/Almdina.ScannerBridge.Core.Tests
tests/Almdina.ScannerBridge.Windows.Tests
installer/AlmdinaScannerBridge.iss
```

الأوامر للمطورين:

```text
dotnet run --project tools/almdina_scanner_bridge/tests/Almdina.ScannerBridge.Core.Tests/Almdina.ScannerBridge.Core.Tests.csproj --configuration Release
dotnet run --project tools/almdina_scanner_bridge/tests/Almdina.ScannerBridge.Windows.Tests/Almdina.ScannerBridge.Windows.Tests.csproj --configuration Release
dotnet publish tools/almdina_scanner_bridge/src/Almdina.ScannerBridge/Almdina.ScannerBridge.csproj --configuration Release --runtime win-x64 --self-contained true --output tools/almdina_scanner_bridge/build/publish
```

Workflow باسم `Windows Scanner Bridge` يبني التطبيق على Windows، يشغل اختبارات البروتوكول والسياسة وتحويل الصور الفعلي، ينشئ المثبت، ويصدر SHA-256. Artifact غير الموقّع مخصص لـUAT فقط. إصدار production من tag بالشكل `scanner-bridge-v*` لا يُنشر ما لم تكن أسرار شهادة Authenticode التالية مضبوطة:

- `WINDOWS_SIGNING_CERTIFICATE_BASE64`
- `WINDOWS_SIGNING_CERTIFICATE_PASSWORD`

بعد إصدار tag موقّع يحدّث الـWorkflow قناة `scanner-bridge-latest`، ويبقى رابط الواجهة ثابتًا حتى مع إصدارات ERP الأخرى.

## التشخيص

- افتح `http://127.0.0.1:17831/health`؛ يجب أن ترى `ok: true`.
- إن لم يعمل، افتح **Almdina Scanner Bridge** من قائمة ابدأ، ولا تستخدم PowerShell.
- من أيقونة شريط النظام اختر **اختبار السكانر** للتأكد من تعريف الجهاز في Windows.
- السجل التشخيصي المحدود يوجد في `%LOCALAPPDATA%\Almdina\ScannerBridge\logs\bridge.log`، ويدور تلقائيًا عند 1 MB.
