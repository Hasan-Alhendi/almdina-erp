using System.Reflection;
using System.Windows.Forms;

namespace Almdina.ScannerBridge;

internal static class Program
{
    private const string SingleInstanceMutexName = @"Local\Almdina.ScannerBridge.SingleInstance";
    internal const string StopEventName = @"Local\Almdina.ScannerBridge.Stop";

    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Any(value => string.Equals(value, "--shutdown", StringComparison.OrdinalIgnoreCase)))
        {
            SignalShutdown();
            return;
        }

        using var mutex = new Mutex(initiallyOwned: true, SingleInstanceMutexName, out var isFirstInstance);
        if (!isFirstInstance)
        {
            if (!args.Any(value => string.Equals(value, "--background", StringComparison.OrdinalIgnoreCase)))
            {
                MessageBox.Show(
                    "برنامج سكانر المدينة يعمل بالفعل في الخلفية.",
                    "سكانر المدينة",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information,
                    MessageBoxDefaultButton.Button1,
                    MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign
                );
            }
            return;
        }

        ApplicationConfiguration.Initialize();
        using var logger = new Infrastructure.FileLogger();
        try
        {
            var showInstalledNotice = args.Any(value => string.Equals(value, "--installed", StringComparison.OrdinalIgnoreCase));
            using var stopEvent = new EventWaitHandle(false, EventResetMode.AutoReset, StopEventName);
            using var context = new BridgeApplicationContext(stopEvent, logger, showInstalledNotice, DisplayVersion());
            Application.Run(context);
        }
        catch (Exception error)
        {
            logger.Error("Bridge startup failed.", error);
            MessageBox.Show(
                "تعذر تشغيل برنامج سكانر المدينة. أغلق أي نسخة قديمة من البرنامج ثم حاول مرة أخرى.\n\nإذا استمرت المشكلة تواصل مع مسؤول النظام.",
                "تعذر تشغيل سكانر المدينة",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error,
                MessageBoxDefaultButton.Button1,
                MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign
            );
        }
        finally
        {
            try { mutex.ReleaseMutex(); } catch (ApplicationException) { }
        }
    }

    private static string DisplayVersion()
    {
        var informational = Assembly.GetExecutingAssembly()
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?
            .InformationalVersion;
        return string.IsNullOrWhiteSpace(informational)
            ? Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "unknown"
            : informational.Split('+', 2)[0];
    }

    private static void SignalShutdown()
    {
        try
        {
            using var stopEvent = EventWaitHandle.OpenExisting(StopEventName);
            stopEvent.Set();
            WaitForPrimaryInstanceToExit();
        }
        catch (WaitHandleCannotBeOpenedException)
        {
            // The bridge is not running; uninstall/upgrade can continue safely.
        }
    }

    private static void WaitForPrimaryInstanceToExit()
    {
        Mutex? mutex = null;
        try
        {
            mutex = Mutex.OpenExisting(SingleInstanceMutexName);
            if (mutex.WaitOne(TimeSpan.FromSeconds(10)))
            {
                mutex.ReleaseMutex();
            }
        }
        catch (WaitHandleCannotBeOpenedException)
        {
        }
        catch (AbandonedMutexException)
        {
            try { mutex?.ReleaseMutex(); } catch (ApplicationException) { }
        }
        finally
        {
            mutex?.Dispose();
        }
    }
}
