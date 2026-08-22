using Almdina.ScannerBridge.Core;
using Almdina.ScannerBridge.Infrastructure;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;

namespace Almdina.ScannerBridge;

internal sealed class BridgeApplicationContext : ApplicationContext
{
    private const string ErpUrl = "https://almadina-2.horizontechco.com";

    private readonly Control _uiDispatcher = new();
    private readonly Icon _appIcon;
    private readonly NotifyIcon _trayIcon;
    private readonly ToolStripMenuItem _startupItem;
    private readonly FileLogger _logger;
    private readonly AutostartManager _autostart = new();
    private readonly WiaScanner _scanner;
    private readonly LoopbackHttpServer _server;
    private readonly RegisteredWaitHandle _stopRegistration;
    private bool _disposed;

    public BridgeApplicationContext(EventWaitHandle stopEvent, FileLogger logger, bool showInstalledNotice, string version)
    {
        _logger = logger;
        _uiDispatcher.CreateControl();
        _scanner = new WiaScanner(_uiDispatcher, logger);

        var options = new BridgeOptions();
        var dispatcher = new BridgeRequestDispatcher(_scanner, options, version);
        _server = new LoopbackHttpServer(options, dispatcher, logger);
        _server.Start();
        _logger.Info($"Bridge {version} started on 127.0.0.1:{options.Port}.");

        _startupItem = new ToolStripMenuItem("تشغيل تلقائيًا مع Windows")
        {
            Checked = _autostart.IsEnabled(),
            CheckOnClick = true,
        };
        _startupItem.CheckedChanged += ToggleAutostart;

        var menu = new ContextMenuStrip { RightToLeft = RightToLeft.Yes };
        menu.Items.Add(new ToolStripMenuItem("الحالة: جاهز للمسح") { Enabled = false });
        menu.Items.Add(new ToolStripMenuItem("فتح نظام المدينة", null, (_, _) => OpenErp()));
        menu.Items.Add(new ToolStripMenuItem("اختبار السكانر", null, async (_, _) => await TestScannerAsync()));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(_startupItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("خروج مؤقت", null, (_, _) => ExitThread()));

        _appIcon = (Icon)(Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application).Clone();
        _trayIcon = new NotifyIcon
        {
            ContextMenuStrip = menu,
            Icon = _appIcon,
            Text = "سكانر المدينة — جاهز",
            Visible = true,
        };
        _trayIcon.DoubleClick += (_, _) => OpenErp();

        _stopRegistration = ThreadPool.RegisterWaitForSingleObject(
            stopEvent,
            (_, _) => RequestExit(),
            null,
            Timeout.Infinite,
            executeOnlyOnce: true
        );

        if (showInstalledNotice)
        {
            ShowBalloon("تم التثبيت", "برنامج السكانر جاهز وسيعمل تلقائيًا مع Windows.", ToolTipIcon.Info);
        }
    }

    private void OpenErp()
    {
        try
        {
            Process.Start(new ProcessStartInfo(ErpUrl) { UseShellExecute = true });
        }
        catch (Exception error)
        {
            _logger.Error("Could not open ERP URL.", error);
            ShowBalloon("تعذر فتح النظام", "افتح نظام المدينة من المتصفح ثم حاول مرة أخرى.", ToolTipIcon.Warning);
        }
    }

    private async Task TestScannerAsync()
    {
        ShowBalloon("اختبار السكانر", "اختر جهاز السكانر وأكمل مسح صفحة واحدة.", ToolTipIcon.Info);
        try
        {
            var result = await _scanner.AcquireJpegAsync(CancellationToken.None);
            ShowBalloon(
                result.Cancelled ? "تم الإلغاء" : "السكانر جاهز",
                result.Cancelled ? "لم تُحفظ أي صورة." : "نجح الاختبار. يمكنك الآن المسح من نظام المدينة.",
                result.Cancelled ? ToolTipIcon.Info : ToolTipIcon.Info
            );
        }
        catch (ScannerBusyException)
        {
            ShowBalloon("السكانر مشغول", "انتظر انتهاء عملية المسح الحالية ثم أعد المحاولة.", ToolTipIcon.Warning);
        }
        catch (Exception error)
        {
            _logger.Error("Scanner self-test failed.", error);
            ShowBalloon("فشل اختبار السكانر", "تأكد أن Windows يرى السكانر وأنه غير مستخدم من برنامج آخر.", ToolTipIcon.Error);
        }
    }

    private void ToggleAutostart(object? sender, EventArgs eventArgs)
    {
        try
        {
            _autostart.SetEnabled(_startupItem.Checked);
            ShowBalloon(
                "التشغيل التلقائي",
                _startupItem.Checked ? "سيعمل البرنامج تلقائيًا عند تسجيل الدخول." : "لن يعمل البرنامج تلقائيًا عند تسجيل الدخول.",
                ToolTipIcon.Info
            );
        }
        catch (Exception error)
        {
            _logger.Error("Could not update autostart setting.", error);
            _startupItem.CheckedChanged -= ToggleAutostart;
            _startupItem.Checked = _autostart.IsEnabled();
            _startupItem.CheckedChanged += ToggleAutostart;
            ShowBalloon("تعذر تغيير الإعداد", "أعد المحاولة أو تواصل مع مسؤول النظام.", ToolTipIcon.Error);
        }
    }

    private void RequestExit()
    {
        try
        {
            if (!_uiDispatcher.IsDisposed)
            {
                _uiDispatcher.BeginInvoke((Action)ExitThread);
            }
        }
        catch (InvalidOperationException)
        {
            // The UI is already closing.
        }
    }

    private void ShowBalloon(string title, string text, ToolTipIcon icon)
    {
        _trayIcon.BalloonTipTitle = title;
        _trayIcon.BalloonTipText = text;
        _trayIcon.BalloonTipIcon = icon;
        _trayIcon.ShowBalloonTip(3500);
    }

    protected override void ExitThreadCore()
    {
        if (!_disposed)
        {
            _disposed = true;
            _trayIcon.Visible = false;
            _stopRegistration.Unregister(null);
            _server.Dispose();
            _scanner.Dispose();
            _trayIcon.Dispose();
            _appIcon.Dispose();
            _uiDispatcher.Dispose();
            _logger.Info("Bridge stopped.");
        }
        base.ExitThreadCore();
    }
}
