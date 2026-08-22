using System.Text;

namespace Almdina.ScannerBridge.Infrastructure;

internal sealed class FileLogger : IDisposable
{
    private const long MaxLogBytes = 1024 * 1024;
    private readonly object _gate = new();
    private readonly string _path;

    public FileLogger()
    {
        var directory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Almdina",
            "ScannerBridge",
            "logs"
        );
        _path = Path.Combine(directory, "bridge.log");
    }

    public void Info(string message) => Write("INFO", message);

    public void Error(string message, Exception error) => Write("ERROR", $"{message} {error.GetType().Name}: {error.Message}");

    private void Write(string level, string message)
    {
        try
        {
            lock (_gate)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
                RotateIfNeeded();
                File.AppendAllText(
                    _path,
                    $"{DateTimeOffset.Now:O} [{level}] {message}{Environment.NewLine}",
                    new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)
                );
            }
        }
        catch
        {
            // Logging must never stop scanner operation.
        }
    }

    private void RotateIfNeeded()
    {
        if (!File.Exists(_path) || new FileInfo(_path).Length < MaxLogBytes)
        {
            return;
        }

        var previous = _path + ".1";
        File.Move(_path, previous, overwrite: true);
    }

    public void Dispose() { }
}
